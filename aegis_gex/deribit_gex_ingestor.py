"""
Deribit v2 Real-Options GEX Ingestor
====================================

Maintains a real dealer-gamma surface for BTC and ETH sourced from the
Deribit options chain (the only liquid crypto-options venue, ~85-90 % of
global BTC/ETH options OI).

Architecture
------------
- One REST poll per `refresh_sec` to `public/get_book_summary_by_currency`
  harvests the full option chain (instrument, OI, mark_iv) per currency.
- One WS connection to `wss://www.deribit.com/ws/api/v2` subscribes to
  the index-price channel `deribit_price_index.{ccy}_usd` for sub-second
  spot ticks (used in the Black-Scholes gamma calc and S² weighting).
- Per refresh cycle we compute:
      GEX_strike = sign(C/P) * gamma_BS * OI * multiplier * spot²
  where multiplier = 1 (Deribit BTC/ETH option contract size = 1 coin).
- Sum across all strikes → net_gex (USD-coin notional).
- call_wall  = strike above spot with max +GEX
- put_wall   = strike below spot with max |-GEX|
- gex_flip   = zero-crossing of cumulative GEX vs strike (linear interp);
               falls back to spot if no crossing exists.
- regime     = "FLIP ZONE" if |spot-flip|/spot < 0.5 %
               "POSITIVE"   if net_gex > 0
               "NEGATIVE"   if net_gex < 0
               "NEUTRAL"    otherwise.

Concurrency
-----------
- Internal state guarded by `asyncio.Lock`; safe for many concurrent
  consumers (signal filter, GEX scanner, persistence task).
- All public reads (`get`, `enrich_snapshot`) are O(1) lock-protected.
- Two background coroutines (`rest_loop`, `ws_loop`) are designed to be
  driven by the engine's `@watched_task` wrapper for auto-restart.

Failure modes
-------------
- Deribit unreachable → ingestor returns `None` from `get()`; the engine
  silently keeps using the AEGIS proxy for the affected symbol.
- Malformed instruments / zero OI / zero IV → row is skipped.
- WS disconnects → exponential backoff (1.0s → 30s cap), unlimited
  reconnects, never propagates the exception.

This module has zero hard imports of the rest of the codebase — it can be
unit-tested in isolation.
"""

from __future__ import annotations

import asyncio
import datetime as _dt
import json
import logging
import math
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

import aiohttp

try:
    import orjson as _orjson  # type: ignore
    def _loads(b): return _orjson.loads(b)
    def _dumps(o) -> str: return _orjson.dumps(o).decode()
except Exception:
    def _loads(b):
        if isinstance(b, (bytes, bytearray)):
            b = b.decode("utf-8", errors="replace")
        return json.loads(b)
    def _dumps(o) -> str: return json.dumps(o)

_log = logging.getLogger("UnityEngine.DeribitGEX")

DERIBIT_REST = "https://www.deribit.com/api/v2"
DERIBIT_WS   = "wss://www.deribit.com/ws/api/v2"

_MONTHS = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}

# Deribit currency-routing table:
#   INVERSE_BASES   → fetched via `currency={base}` (BTC, ETH inverse options)
#   LINEAR_USDC_BASES → fetched via `currency=USDC` then filtered by `{base}_USDC-`
#                       prefix (SOL, AVAX, XRP, TRX linear USDC options)
INVERSE_BASES     = {"BTC", "ETH"}
LINEAR_USDC_BASES = {"SOL", "AVAX", "XRP", "TRX"}


# ─── Math helpers (pure-python, no SciPy dep) ──────────────────────────

def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def _bs_gamma(S: float, K: float, T: float, sigma: float, r: float = 0.0) -> float:
    """Black-Scholes gamma — same for calls and puts."""
    if S <= 0 or K <= 0 or T <= 0 or sigma <= 0:
        return 0.0
    sqrt_T = math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * sqrt_T)
    return _norm_pdf(d1) / (S * sigma * sqrt_T)


def _parse_deribit_expiry(s: str) -> float:
    """Parse '26APR26' → unix timestamp at 08:00 UTC (Deribit settle time)."""
    if len(s) < 7:
        raise ValueError(f"bad expiry: {s}")
    day = int(s[:-5])
    mon = _MONTHS[s[-5:-2]]
    yr  = 2000 + int(s[-2:])
    return _dt.datetime(yr, mon, day, 8, 0, tzinfo=_dt.timezone.utc).timestamp()


# ─── Snapshot dataclass ────────────────────────────────────────────────

@dataclass
class RealGEXSnapshot:
    base: str                              # "BTC" | "ETH"
    spot: float
    timestamp: float

    net_gex: float                         # signed Σ γ·OI·multi·S²  (USD-coin notional)
    call_wall: Optional[float]
    put_wall:  Optional[float]
    gex_flip:  float                       # cumulative-GEX zero crossing strike

    regime: str = "NEUTRAL"                # "POSITIVE" | "NEGATIVE" | "FLIP ZONE" | "NEUTRAL"
    confidence: float = 0.0                # 0–100, derived from chain coverage
    by_strike: Dict[float, float] = field(default_factory=dict)
    n_strikes: int = 0
    n_expiries: int = 0


# ─── Ingestor ──────────────────────────────────────────────────────────

class DeribitGEXIngestor:
    """Real-options GEX surface for BTC + ETH from Deribit."""

    def __init__(
        self,
        currencies: Tuple[str, ...] = ("BTC", "ETH", "SOL"),
        refresh_sec: int = 30,
        max_age_sec: int = 180,
    ):
        # Validate every requested base is supported (inverse or linear-USDC).
        # Unknown bases are silently dropped with a debug log so adding new
        # bases via config never crashes the engine.
        cleaned: list = []
        for c in currencies:
            cu = c.upper()
            if cu in INVERSE_BASES or cu in LINEAR_USDC_BASES:
                cleaned.append(cu)
            else:
                _log.debug(
                    f"Deribit ingestor: dropping unsupported base '{cu}' "
                    f"(supported: inverse={sorted(INVERSE_BASES)}, "
                    f"linear={sorted(LINEAR_USDC_BASES)})"
                )
        self.currencies   = tuple(cleaned) or ("BTC", "ETH")
        self.refresh_sec  = max(10, int(refresh_sec))
        self.max_age_sec  = max(60, int(max_age_sec))

        self._snapshots: Dict[str, RealGEXSnapshot] = {}
        self._spot:      Dict[str, float] = {}
        self._lock       = asyncio.Lock()
        self._sess: Optional[aiohttp.ClientSession] = None
        self._stopped    = False

    # ── lifecycle ──────────────────────────────────────────────────────

    async def start(self) -> None:
        """Idempotent — initialises the aiohttp session and warms up the cache."""
        if self._sess is None or self._sess.closed:
            self._sess = aiohttp.ClientSession()
        try:
            await self._refresh_all()
        except Exception as e:
            _log.debug(f"initial Deribit refresh failed (non-fatal): {e}")

    async def close(self) -> None:
        self._stopped = True
        if self._sess and not self._sess.closed:
            try:
                await self._sess.close()
            except Exception:
                pass

    # ── public API ─────────────────────────────────────────────────────

    async def get(self, base: str) -> Optional[RealGEXSnapshot]:
        """Return fresh real-GEX snapshot for BTC/ETH, or None if stale/absent."""
        b = (base or "").upper()
        async with self._lock:
            snap = self._snapshots.get(b)
        if snap is None:
            return None
        if time.time() - snap.timestamp > self.max_age_sec:
            return None
        return snap

    def base_from_symbol(self, symbol: str) -> Optional[str]:
        """Map 'BTCUSDT'/'SOLUSDT'/'BTC-PERPETUAL' → 'BTC'/'SOL'/etc.

        Only returns a base if it's actually loaded in this ingestor's
        `currencies` tuple (so unknown bases don't trigger empty lookups).
        """
        if not symbol:
            return None
        s = symbol.upper()
        # longest-match-first: prevent 'AVAXUSDT' from matching 'AV' etc.
        for base in sorted(self.currencies, key=len, reverse=True):
            if s.startswith(base):
                return base
        return None

    async def enrich_snapshot(self, symbol: str, aegis_snap) -> None:
        """
        Splice real-options GEX values into an existing AEGIS GEXSnapshot
        in-place. No-op if the base is not BTC/ETH or Deribit data is stale.

        This is the single integration seam for the rest of the engine —
        downstream consumers (Gate 7, Quality bonuses, dashboard) keep
        reading the same `gex_flip` / `call_wall` / `put_wall` / `net_gex`
        / `regime` attributes; only their *origin* changes from "ATR
        proxy" to "real Deribit options chain".
        """
        base = self.base_from_symbol(symbol)
        if base is None or aegis_snap is None:
            return
        real = await self.get(base)
        if real is None:
            return

        try:
            # Splice real fields. Keep AEGIS proxy fields as graceful
            # fallback if any individual field is missing.
            if real.gex_flip and real.gex_flip > 0:
                aegis_snap.gex_flip = float(real.gex_flip)
            if real.call_wall is not None:
                aegis_snap.call_wall = float(real.call_wall)
            if real.put_wall is not None:
                aegis_snap.put_wall = float(real.put_wall)
            aegis_snap.net_gex = float(real.net_gex)

            # Regime override — only when the real chain is well-covered
            # (≥40 strikes ≈ confidence ≥20). Keeps the AEGIS proxy regime
            # whenever the options data is sparse.
            if real.confidence >= 30.0 and real.regime in (
                "POSITIVE", "NEGATIVE", "FLIP ZONE", "NEUTRAL"
            ):
                aegis_snap.regime = real.regime
                # Map regime → high-level gex_regime field used elsewhere.
                if real.regime == "POSITIVE":
                    aegis_snap.gex_regime = "LONG GAMMA"
                elif real.regime == "NEGATIVE":
                    aegis_snap.gex_regime = "SHORT GAMMA"
                elif real.regime == "FLIP ZONE":
                    aegis_snap.gex_regime = "FLIP ZONE"

            # Boost confidence when real options data backs the proxy
            # (capped at 100). This propagates to GEX_MIN_CONFIDENCE gate.
            try:
                old_conf = float(getattr(aegis_snap, "confidence", 0) or 0)
                aegis_snap.confidence = min(100.0, max(old_conf, real.confidence))
            except Exception:
                pass
        except Exception as e:
            # Never break the engine if a downstream attribute is
            # read-only or the snapshot dataclass shape changes.
            _log.debug(f"enrich_snapshot failed for {symbol}: {e}")

    def stats(self) -> Dict[str, dict]:
        """Lightweight diagnostics for the health server / persistence layer."""
        out: Dict[str, dict] = {}
        for ccy, snap in self._snapshots.items():
            out[ccy] = {
                "spot":       round(snap.spot, 2),
                "net_gex_m":  round(snap.net_gex / 1e6, 2),
                "gex_flip":   round(snap.gex_flip, 2),
                "call_wall":  snap.call_wall,
                "put_wall":   snap.put_wall,
                "regime":     snap.regime,
                "confidence": round(snap.confidence, 1),
                "n_strikes":  snap.n_strikes,
                "n_expiries": snap.n_expiries,
                "age_sec":    round(time.time() - snap.timestamp, 1),
            }
        return out

    # ── REST refresh loop (driven by @watched_task) ────────────────────

    async def rest_loop(self) -> None:
        """Long-running REST refresher. Wrap with @watched_task."""
        if self._sess is None or self._sess.closed:
            self._sess = aiohttp.ClientSession()
        try:
            while not self._stopped:
                await self._refresh_all()
                await asyncio.sleep(self.refresh_sec)
        except asyncio.CancelledError:
            raise
        finally:
            # Don't close session here — close() owns it for clean shutdown
            pass

    async def _refresh_all(self) -> None:
        for ccy in self.currencies:
            try:
                await self._refresh_one(ccy)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                _log.debug(f"Deribit refresh {ccy} failed (non-fatal): {e}")

    async def _refresh_one(self, ccy: str) -> None:
        if self._sess is None or self._sess.closed:
            self._sess = aiohttp.ClientSession()
        sess = self._sess

        is_linear = ccy in LINEAR_USDC_BASES
        # Linear bases (SOL, AVAX, …) are quoted in USDC on Deribit. The chain
        # endpoint is `currency=USDC` for ALL of them; we filter by instrument
        # prefix `{ccy}_USDC-` to isolate the requested base.
        chain_currency  = "USDC" if is_linear else ccy
        instr_prefix    = f"{ccy}_USDC-" if is_linear else f"{ccy}-"
        index_name      = f"{ccy.lower()}_usd"

        # 1. spot index price (REST fallback if WS not connected yet)
        spot = self._spot.get(ccy, 0.0)
        if spot <= 0:
            try:
                url = f"{DERIBIT_REST}/public/get_index_price?index_name={index_name}"
                async with sess.get(
                    url, timeout=aiohttp.ClientTimeout(total=10)
                ) as r:
                    raw = await r.read()
                    js = _loads(raw) or {}
                    spot = float((js.get("result") or {}).get("index_price") or 0.0)
                    if spot > 0:
                        self._spot[ccy] = spot
            except Exception:
                pass
        if spot <= 0:
            return

        # 2. full option chain summary
        url = (
            f"{DERIBIT_REST}/public/get_book_summary_by_currency"
            f"?currency={chain_currency}&kind=option"
        )
        async with sess.get(url, timeout=aiohttp.ClientTimeout(total=15)) as r:
            raw = await r.read()
            data = (_loads(raw) or {}).get("result") or []
        if not data:
            return

        now = time.time()
        by_strike: Dict[float, float] = {}
        n_strikes = 0
        expiries = set()

        for row in data:
            inst = row.get("instrument_name") or ""
            # Linear chain returns ALL USDC instruments; filter to this base.
            if is_linear and not inst.startswith(instr_prefix):
                continue
            parts = inst.split("-")
            if len(parts) != 4:
                continue
            try:
                expiry_str = parts[1]
                strike     = float(parts[2])
                kind       = parts[3]
            except (ValueError, IndexError):
                continue
            if kind not in ("C", "P"):
                continue

            try:
                oi = float(row.get("open_interest") or 0.0)
            except (TypeError, ValueError):
                continue
            if oi <= 0:
                continue

            try:
                # Deribit returns IV in percent (e.g. 65 → 0.65)
                mark_iv = float(row.get("mark_iv") or 0.0) / 100.0
            except (TypeError, ValueError):
                continue
            if mark_iv <= 0:
                continue

            try:
                exp_ts = _parse_deribit_expiry(expiry_str)
                T = (exp_ts - now) / (365.0 * 86400.0)
                if T <= 1e-6:
                    continue
            except Exception:
                continue

            expiries.add(expiry_str)
            gamma  = _bs_gamma(spot, strike, T, mark_iv)
            sign   = 1.0 if kind == "C" else -1.0
            multi  = 1.0   # Deribit BTC/ETH option contract = 1 coin
            gex_k  = gamma * oi * multi * spot * spot * sign
            by_strike[strike] = by_strike.get(strike, 0.0) + gex_k
            n_strikes += 1

        if not by_strike:
            return

        net_gex = sum(by_strike.values())

        above = {k: v for k, v in by_strike.items() if k > spot and v > 0}
        below = {k: v for k, v in by_strike.items() if k < spot and v < 0}
        call_wall = max(above, key=lambda k: above[k]) if above else None
        put_wall  = min(below, key=lambda k: below[k]) if below else None

        # zero-crossing of cumulative GEX vs strike (linear interp)
        sorted_k = sorted(by_strike.keys())
        cum, prev_cum, prev_k = 0.0, 0.0, sorted_k[0]
        flip = spot
        first = True
        for k in sorted_k:
            cum += by_strike[k]
            if not first and prev_cum * cum < 0:
                denom = (cum - prev_cum)
                if denom != 0:
                    frac = -prev_cum / denom
                    flip = prev_k + (k - prev_k) * max(0.0, min(1.0, frac))
                else:
                    flip = k
                break
            prev_cum, prev_k = cum, k
            first = False

        flip_dist_pct = abs(spot - flip) / spot if spot > 0 else 1.0
        if flip_dist_pct < 0.005:
            regime = "FLIP ZONE"
        elif net_gex > 0:
            regime = "POSITIVE"
        elif net_gex < 0:
            regime = "NEGATIVE"
        else:
            regime = "NEUTRAL"

        # confidence: chain coverage proxy — 200 strikes ≈ full chain → ~100
        confidence = max(20.0, min(100.0, len(by_strike) * 0.5))

        snap = RealGEXSnapshot(
            base=ccy, spot=spot, timestamp=now,
            net_gex=net_gex,
            call_wall=call_wall, put_wall=put_wall,
            gex_flip=flip, regime=regime, confidence=confidence,
            by_strike=by_strike, n_strikes=n_strikes,
            n_expiries=len(expiries),
        )
        async with self._lock:
            self._snapshots[ccy] = snap

        _log.info(
            f"📡 Deribit GEX {ccy}: spot=${spot:,.2f} net=${net_gex/1e6:+.1f}M "
            f"flip=${flip:,.0f} call_wall={call_wall} put_wall={put_wall} "
            f"regime={regime} strikes={n_strikes} exp={len(expiries)} "
            f"conf={confidence:.0f}"
        )

    # ── WS spot-index loop (driven by @watched_task) ───────────────────

    async def ws_loop(self) -> None:
        """
        Sub-second spot ticks via Deribit's index-price WS channel.
        Wrap with @watched_task so disconnects auto-reconnect at the
        engine level. Internal exponential backoff also keeps the
        coroutine alive across short network blips.
        """
        try:
            import websockets
        except ImportError:
            _log.warning("websockets library not installed — Deribit spot WS disabled")
            return

        backoff = 1.0
        while not self._stopped:
            try:
                async with websockets.connect(
                    DERIBIT_WS,
                    ping_interval=20,
                    ping_timeout=20,
                    close_timeout=10,
                    max_size=2 ** 22,
                ) as ws:
                    sub = {
                        "jsonrpc": "2.0", "id": 1,
                        "method":  "public/subscribe",
                        "params": {
                            "channels": [
                                f"deribit_price_index.{c.lower()}_usd"
                                for c in self.currencies
                            ]
                        },
                    }
                    await ws.send(_dumps(sub))
                    _log.info(
                        f"🔌 Deribit WS connected — index streams: "
                        f"{', '.join(self.currencies)}"
                    )
                    backoff = 1.0
                    async for msg in ws:
                        try:
                            js = _loads(msg)
                        except Exception:
                            continue
                        params = js.get("params") if isinstance(js, dict) else None
                        if not isinstance(params, dict):
                            continue
                        ch = params.get("channel") or ""
                        if not ch.startswith("deribit_price_index."):
                            continue
                        try:
                            ccy = ch.split(".", 1)[1].split("_", 1)[0].upper()
                            price = float((params.get("data") or {}).get("price") or 0.0)
                        except Exception:
                            continue
                        if price > 0 and ccy in self.currencies:
                            self._spot[ccy] = price
            except asyncio.CancelledError:
                break
            except Exception as e:
                _log.debug(f"Deribit WS reconnect in {backoff:.1f}s: {e}")
                try:
                    await asyncio.sleep(min(backoff, 30.0))
                except asyncio.CancelledError:
                    break
                backoff = min(backoff * 1.7, 30.0)

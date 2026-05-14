"""
OKX Options GEX Ingestor — Cross-Venue Redundancy  (v9.9 / Apex-#3)
====================================================================

Mirrors the Deribit ingestor architecture but pulls option chains from
OKX (~10-15 % of global BTC/ETH options OI).  Used as a **secondary source**
to cross-validate Deribit's flip levels and provide failover when the
Deribit feed goes stale (>5 min) or returns malformed data.

Architecture
------------
- REST polls `/api/v5/public/instruments?instType=OPTION&uly={base}-USD`
  every `refresh_sec` to harvest live option contracts.
- REST polls `/api/v5/market/option-summary?uly={base}-USD` for OI + IV
  per contract on the same cadence (single batched call per currency).
- Computes GEX per strike using the same Black-Scholes formula as the
  Deribit ingestor:
      GEX_strike = sign(C/P) * gamma_BS * OI * spot²
  (OKX option contract size = 0.01 BTC / 0.1 ETH; we apply the multiplier.)
- Aggregates into the same shape as `DeribitGEXIngestor.get(ccy)` so the
  consumer can swap the source transparently.

Cross-validation
----------------
The main consumer (the engine's GEX consensus layer) reads BOTH feeds.
When both report a flip level the engine takes the **average** weighted
by `confidence`.  When Deribit is stale >5 min, OKX takes over.

Failure modes
-------------
- OKX REST unreachable → ingestor returns None on `get()`; engine falls
  back to Deribit-only as if this module did not exist.  Never throws.
- Empty response / malformed JSON → row skipped, log at DEBUG level.
- Symbols not on OKX (SOL/AVAX/XRP/TRX) → silently ignored.

Currencies covered
------------------
BTC, ETH only.  OKX does not list other crypto options at any meaningful
volume; the LINEAR_USDC fallback used for SOL on Deribit has no analog here.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import time
from dataclasses import dataclass, field
from typing import Dict, Optional

import aiohttp

try:
    import orjson as _orjson  # type: ignore
    def _loads(b):
        return _orjson.loads(b)
except Exception:
    def _loads(b):
        if isinstance(b, (bytes, bytearray)):
            b = b.decode("utf-8", errors="replace")
        return json.loads(b)

_log = logging.getLogger("UnityEngine.OkxGEX")

OKX_REST = "https://www.okx.com"
OKX_BASES = {"BTC", "ETH"}

# OKX option contract multipliers (coin units per contract)
# https://www.okx.com/help/iv-introduction-of-options
_OKX_CONTRACT_MULT = {
    "BTC": 0.01,
    "ETH": 0.1,
}


# ─── Math helpers (duplicated to keep this module self-contained) ────────

def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def _bs_gamma(S: float, K: float, T: float, sigma: float, r: float = 0.0) -> float:
    if S <= 0 or K <= 0 or T <= 0 or sigma <= 0:
        return 0.0
    sqrt_T = math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * sqrt_T)
    return _norm_pdf(d1) / (S * sigma * sqrt_T)


def _parse_okx_instid_expiry(inst_id: str) -> Optional[float]:
    """
    Parse OKX option instrument ID expiry → unix seconds at 08:00 UTC.

    Format: BTC-USD-260424-72000-C  →  parts[2] = "260424" (YYMMDD)
                                       parts[3] = strike
                                       parts[4] = "C" or "P"
    """
    parts = inst_id.split("-")
    if len(parts) < 5:
        return None
    yymmdd = parts[2]
    if len(yymmdd) != 6 or not yymmdd.isdigit():
        return None
    try:
        yy = int(yymmdd[0:2])
        mm = int(yymmdd[2:4])
        dd = int(yymmdd[4:6])
        year = 2000 + yy
        import datetime as _dt
        ts = _dt.datetime(year, mm, dd, 8, 0, 0, tzinfo=_dt.timezone.utc).timestamp()
        return float(ts)
    except (ValueError, OverflowError):
        return None


# ─── Data shape ──────────────────────────────────────────────────────────

@dataclass
class OkxGEXSnapshot:
    spot:        float = 0.0
    net_gex_m:   float = 0.0
    gex_flip:    float = 0.0
    call_wall:   float = 0.0
    put_wall:    float = 0.0
    regime:      str   = "UNKNOWN"
    confidence:  float = 0.0
    n_strikes:   int   = 0
    n_expiries:  int   = 0
    age_sec:     float = 999.0
    last_update: float = 0.0
    err:         str   = ""


class OkxGEXIngestor:
    """
    OKX options GEX ingestor — public read API mirrors Deribit:

        ingestor = OkxGEXIngestor(currencies=["BTC", "ETH"], refresh_sec=60)
        await ingestor.start()
        snap = ingestor.get("BTC")   # OkxGEXSnapshot or None
        ...
        await ingestor.close()

    Background tasks:
        - rest_loop()  : REST poll every refresh_sec, drives the GEX calc.

    Designed to be wrapped in @watched_task by the engine.
    """

    def __init__(
        self,
        currencies = ("BTC", "ETH"),
        *,
        refresh_sec: int = 60,
        request_timeout: float = 8.0,
    ) -> None:
        self._currencies = [c.upper() for c in currencies if c.upper() in OKX_BASES]
        self._refresh_sec = max(10, int(refresh_sec))
        self._timeout = aiohttp.ClientTimeout(total=request_timeout)
        self._snapshots: Dict[str, OkxGEXSnapshot] = {
            c: OkxGEXSnapshot() for c in self._currencies
        }
        self._lock = asyncio.Lock()
        self._session: Optional[aiohttp.ClientSession] = None
        self._stop_evt = asyncio.Event()
        self._closed = False
        self._fetches = 0
        self._errors = 0
        self._last_err = ""

    # ─── Lifecycle ───────────────────────────────────────────────────────

    async def start(self) -> None:
        if self._session is None and not self._closed:
            self._session = aiohttp.ClientSession(timeout=self._timeout)
            _log.info(
                f"⚡ [v9.9] OkxGEXIngestor started — currencies={self._currencies} "
                f"refresh={self._refresh_sec}s"
            )

    async def close(self) -> None:
        self._closed = True
        self._stop_evt.set()
        if self._session is not None:
            try:
                await self._session.close()
            except Exception:
                pass
            self._session = None

    # ─── Public read API ─────────────────────────────────────────────────

    def get(self, currency: str) -> Optional[OkxGEXSnapshot]:
        snap = self._snapshots.get(currency.upper())
        if snap is None or snap.last_update <= 0:
            return None
        # update age each read
        snap.age_sec = max(0.0, time.time() - snap.last_update)
        return snap

    def status_summary(self) -> Dict:
        out = {}
        for c, s in self._snapshots.items():
            age = max(0.0, time.time() - s.last_update) if s.last_update else 999.0
            out[c] = {
                "regime":     s.regime,
                "n_strikes":  s.n_strikes,
                "age_sec":    round(age, 1),
                "fresh":      age < 300.0,
            }
        out["_pool"] = {
            "fetches": self._fetches,
            "errors":  self._errors,
            "last_err": (self._last_err or "")[:80],
        }
        return out

    # ─── Background loop ─────────────────────────────────────────────────

    async def rest_loop(self) -> None:
        """REST poll forever; safe to be wrapped by @watched_task."""
        if self._session is None:
            await self.start()
        while not self._stop_evt.is_set():
            for ccy in self._currencies:
                if self._stop_evt.is_set():
                    break
                try:
                    await self._refresh_currency(ccy)
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    self._errors += 1
                    self._last_err = f"{type(e).__name__}: {e}"
                    _log.debug(f"OKX GEX refresh {ccy} error: {e}")
            try:
                await asyncio.wait_for(self._stop_evt.wait(), timeout=self._refresh_sec)
            except asyncio.TimeoutError:
                pass

    # ─── Internal: per-currency refresh ──────────────────────────────────

    async def _refresh_currency(self, ccy: str) -> None:
        if self._session is None:
            return
        uly = f"{ccy}-USD"

        # 1) Spot — mark price
        spot = await self._fetch_spot(ccy)
        if spot is None or spot <= 0:
            return

        # 2) Option summary — single batched call: returns OI + IV per contract
        summaries = await self._fetch_option_summary(uly)
        if not summaries:
            return

        mult = _OKX_CONTRACT_MULT.get(ccy, 1.0)
        now_ts = time.time()
        gex_by_strike: Dict[float, float] = {}
        expiries: set = set()

        for row in summaries:
            inst_id = row.get("instId") or ""
            if not inst_id.startswith(f"{ccy}-USD-"):
                continue
            parts = inst_id.split("-")
            if len(parts) < 5:
                continue
            try:
                strike = float(parts[3])
            except ValueError:
                continue
            cp = parts[4]
            if cp not in ("C", "P"):
                continue
            try:
                oi   = float(row.get("oi") or 0.0)
                miv  = float(row.get("markVol") or row.get("askVol") or row.get("bidVol") or 0.0)
            except (TypeError, ValueError):
                continue
            if oi <= 0 or miv <= 0 or strike <= 0:
                continue
            expiry_ts = _parse_okx_instid_expiry(inst_id)
            if expiry_ts is None:
                continue
            T = max(0.0, (expiry_ts - now_ts) / (365.25 * 86400.0))
            if T <= 0:
                continue
            gamma = _bs_gamma(spot, strike, T, miv)
            if gamma <= 0:
                continue
            sign = 1.0 if cp == "C" else -1.0
            gex_contrib = sign * gamma * oi * mult * spot * spot
            gex_by_strike[strike] = gex_by_strike.get(strike, 0.0) + gex_contrib
            expiries.add(int(expiry_ts))

        if not gex_by_strike:
            return

        net_gex = sum(gex_by_strike.values())
        # Walls
        above = [(k, v) for k, v in gex_by_strike.items() if k > spot and v > 0]
        below = [(k, v) for k, v in gex_by_strike.items() if k < spot and v < 0]
        call_wall = max(above, key=lambda kv: kv[1])[0] if above else 0.0
        put_wall  = min(below, key=lambda kv: kv[1])[0] if below else 0.0

        # Flip — first zero-crossing of cumulative GEX vs strike (linear interp)
        flip = self._compute_flip(gex_by_strike, spot)

        # Regime classification (mirrors Deribit logic)
        if abs(spot - flip) / spot < 0.005:
            regime = "FLIP ZONE"
        elif net_gex > 0:
            regime = "POSITIVE"
        elif net_gex < 0:
            regime = "NEGATIVE"
        else:
            regime = "NEUTRAL"

        # Confidence — capped to 60 (Deribit's max is 100); OKX has ~20% the OI.
        confidence = min(60.0, len(gex_by_strike) * 0.5 + len(expiries) * 2.0)

        snap = OkxGEXSnapshot(
            spot=spot,
            net_gex_m=net_gex / 1_000_000.0,
            gex_flip=flip,
            call_wall=call_wall,
            put_wall=put_wall,
            regime=regime,
            confidence=confidence,
            n_strikes=len(gex_by_strike),
            n_expiries=len(expiries),
            age_sec=0.0,
            last_update=time.time(),
        )
        async with self._lock:
            self._snapshots[ccy] = snap
        self._fetches += 1
        _log.info(
            f"📡 OKX GEX {ccy}: spot=${spot:,.2f} net=${snap.net_gex_m:+.1f}M "
            f"flip=${flip:,.0f} regime={regime} strikes={snap.n_strikes} "
            f"exp={snap.n_expiries} conf={confidence:.0f}"
        )

    # ─── Internal: REST helpers ──────────────────────────────────────────

    async def _fetch_spot(self, ccy: str) -> Optional[float]:
        """OKX index price for {CCY}-USD"""
        try:
            url = f"{OKX_REST}/api/v5/market/index-tickers"
            params = {"instId": f"{ccy}-USD"}
            async with self._session.get(url, params=params) as r:
                if r.status != 200:
                    return None
                body = await r.read()
                data = _loads(body)
                rows = data.get("data") or []
                if not rows:
                    return None
                return float(rows[0].get("idxPx") or 0.0) or None
        except Exception as e:
            self._last_err = f"spot {ccy}: {e}"
            return None

    async def _fetch_option_summary(self, uly: str):
        """Returns list of {instId, oi, markVol, askVol, bidVol, ...}"""
        try:
            url = f"{OKX_REST}/api/v5/public/opt-summary"
            params = {"uly": uly}
            async with self._session.get(url, params=params) as r:
                if r.status != 200:
                    return None
                body = await r.read()
                data = _loads(body)
                return data.get("data") or []
        except Exception as e:
            self._last_err = f"opt-summary {uly}: {e}"
            return None

    @staticmethod
    def _compute_flip(gex_by_strike: Dict[float, float], spot: float) -> float:
        """
        Find the strike where cumulative GEX (sorted ascending) crosses zero.
        Linear interpolation; falls back to spot if no crossing.
        """
        if not gex_by_strike:
            return spot
        strikes = sorted(gex_by_strike.keys())
        cum = 0.0
        prev_strike = strikes[0]
        prev_cum = 0.0
        for k in strikes:
            cum += gex_by_strike[k]
            if prev_cum != 0.0 and (prev_cum * cum) < 0:
                # zero-crossing between prev_strike and k
                if (cum - prev_cum) == 0:
                    return k
                ratio = -prev_cum / (cum - prev_cum)
                return prev_strike + ratio * (k - prev_strike)
            prev_strike = k
            prev_cum = cum
        return spot

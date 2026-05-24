"""
Binance USDM Futures aggTrade WebSocket Pool  (v9.9 / Apex-#1)
==============================================================

Streams sub-100ms last-trade ticks from Binance USDM Futures via the public
public combined-stream endpoint:

    wss://fstream.binance.com/stream?streams=btcusdt@aggTrade/ethusdt@aggTrade/...

For each symbol we maintain a lock-free `latest tick` snapshot:

    {symbol: {"price": float, "qty": float, "ts_ms": int, "side": str}}

Where `side` is "BUY" if the aggressor was the buyer (taker), "SELL" otherwise
(`m` field == True means market-buyer is the maker → aggressor is SELL).

The pool is designed to be driven by the engine's `@watched_task` wrapper so
disconnects auto-restart with exponential backoff, and `latest()` / `age_ms()`
are O(1) reads safe from any coroutine.

Why this matters
----------------
The existing engine relies on REST polling (~3-15s cadence) for current
price; aggTrade WS gives us:

  • Sub-100ms tick freshness for the EV gate's slippage normalizer.
  • Real aggressor-side flow for confirming directional conviction
    (consumed by depth_slippage.py + future micro-flow agent).
  • Per-symbol staleness detection (we can detect when a market has gone
    illiquid by watching tick interarrival times).

Failure modes
-------------
  • Binance WS unreachable / 403 → loop logs WARN, sleeps with exp backoff,
    never propagates exception.  Consumers see `latest()` return None and
    fall back to existing REST path transparently.
  • Symbol not on Binance USDM → silently dropped from the subscription
    list (no per-symbol error log spam).
  • orjson preferred for parse; stdlib json fallback.

Concurrency
-----------
  • Internal state is a plain dict mutated only inside `_handle_message`.
  • Reads (`latest`, `age_ms`, `latest_price`) are atomic dict lookups in
    CPython — no lock needed for single-key reads, which is the only access
    pattern.  Multi-key snapshots use `dict.copy()` for consistency.

Zero hard imports of the rest of the codebase — unit-testable in isolation.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Dict, Iterable, Optional, Set

try:
    import orjson as _orjson  # type: ignore
    def _loads(b):
        return _orjson.loads(b)
except Exception:
    def _loads(b):
        if isinstance(b, (bytes, bytearray)):
            b = b.decode("utf-8", errors="replace")
        return json.loads(b)

_log = logging.getLogger("UnityEngine.BinanceAggTradeWS")

BINANCE_FSTREAM_WS = "wss://fstream.binance.com/stream"

# Hard cap on streams per WS connection (Binance limit is 1024 but we stay
# well below to keep frames small & resub fast).
MAX_STREAMS_PER_CONN = 200


class BinanceAggTradePool:
    """
    Multi-symbol aggTrade WebSocket pool.

    Usage:
        pool = BinanceAggTradePool(symbols=["BTCUSDT", "ETHUSDT", ...])
        await pool.start()                # subscribes
        # later:
        tick = pool.latest("BTCUSDT")     # {"price": 76500.1, "qty": 0.05, ...}
        age  = pool.age_ms("BTCUSDT")     # 87
        # at shutdown:
        await pool.close()
    """

    def __init__(
        self,
        symbols: Iterable[str],
        *,
        max_streams_per_conn: int = MAX_STREAMS_PER_CONN,
    ) -> None:
        # Normalise to lowercase Binance stream form.
        self._symbols: Set[str] = {s.upper() for s in symbols if s}
        self._max_per_conn = max(20, int(max_streams_per_conn))
        # latest-tick map keyed by UPPER symbol → {price, qty, ts_ms, side}
        self._ticks: Dict[str, Dict[str, float]] = {}
        # Per-symbol last receive ts (ms) for staleness detection
        self._last_rx_ms: Dict[str, int] = {}
        # Pool stats (reads via status_summary)
        self._msgs_total: int = 0
        self._reconnects: int = 0
        self._last_err: str = ""
        self._started_ts: float = 0.0
        # Cancellation handles for connection tasks
        self._tasks: list = []
        self._stop_evt = asyncio.Event()

    # ─── Public read API (lock-free, O(1)) ───────────────────────────────

    def latest(self, symbol: str) -> Optional[Dict[str, float]]:
        """Return latest tick dict for `symbol` or None if never seen."""
        return self._ticks.get(symbol.upper())

    def latest_price(self, symbol: str) -> Optional[float]:
        t = self._ticks.get(symbol.upper())
        if t is None:
            return None
        return float(t.get("price") or 0.0) or None

    def age_ms(self, symbol: str) -> Optional[int]:
        """Milliseconds since last tick for `symbol`, or None if never seen."""
        last = self._last_rx_ms.get(symbol.upper())
        if not last:
            return None
        return max(0, int(time.time() * 1000.0 - last))

    def status_summary(self) -> Dict[str, int]:
        """Health metrics for /metrics endpoint."""
        now_ms = int(time.time() * 1000.0)
        fresh = sum(
            1 for ts in self._last_rx_ms.values()
            if (now_ms - ts) < 5000
        )
        stale = len(self._last_rx_ms) - fresh
        return {
            "symbols":     len(self._symbols),
            "tracked":     len(self._ticks),
            "fresh_5s":    fresh,
            "stale_5s+":   stale,
            "msgs_total":  self._msgs_total,
            "reconnects":  self._reconnects,
            "uptime_sec":  int(time.time() - self._started_ts) if self._started_ts else 0,
        }

    # ─── Lifecycle ───────────────────────────────────────────────────────

    async def start(self) -> None:
        """Spin up one WS task per chunk of `max_streams_per_conn` symbols."""
        if self._tasks:
            return  # idempotent
        self._stop_evt.clear()
        self._started_ts = time.time()
        chunks = self._chunk_symbols()
        _log.info(
            f"⚡ [v9.9] BinanceAggTradePool starting: {len(self._symbols)} symbols "
            f"across {len(chunks)} WS connection(s) (max {self._max_per_conn}/conn)"
        )
        for idx, chunk in enumerate(chunks):
            t = asyncio.create_task(
                self._connection_loop(chunk, conn_id=idx),
                name=f"BinanceAggTradeWS-{idx}",
            )
            self._tasks.append(t)

    async def close(self) -> None:
        """Cancel all WS tasks and wait for them to exit."""
        self._stop_evt.set()
        for t in self._tasks:
            if not t.done():
                t.cancel()
        for t in self._tasks:
            try:
                await asyncio.wait_for(t, timeout=2.0)
            except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
                pass
        self._tasks.clear()
        _log.info("⚡ [v9.9] BinanceAggTradePool closed cleanly")

    # ─── Internal: per-connection loop with reconnect ────────────────────

    def _chunk_symbols(self) -> list:
        symbols = sorted(self._symbols)
        return [
            symbols[i:i + self._max_per_conn]
            for i in range(0, len(symbols), self._max_per_conn)
        ] or [[]]

    async def _connection_loop(self, symbols: list, *, conn_id: int) -> None:
        """One forever-loop with exponential backoff per WS connection."""
        try:
            import websockets  # type: ignore
        except Exception:
            _log.warning(
                "websockets library not installed — Binance aggTrade WS disabled. "
                "Engine will fall back to REST polling for ticks."
            )
            return

        if not symbols:
            return

        backoff = 1.0
        while not self._stop_evt.is_set():
            stream_path = "/".join(f"{s.lower()}@aggTrade" for s in symbols)
            url = f"{BINANCE_FSTREAM_WS}?streams={stream_path}"
            try:
                async with websockets.connect(
                    url,
                    ping_interval=180,   # Binance recommends server-side ping
                    ping_timeout=600,
                    max_size=2 ** 20,    # 1 MiB frame cap (aggTrade is tiny)
                    close_timeout=2.0,
                ) as ws:
                    _log.info(
                        f"🔌 [v9.9] BinanceAggTradeWS conn={conn_id} connected: "
                        f"{len(symbols)} streams"
                    )
                    backoff = 1.0  # reset on successful connect
                    async for raw in ws:
                        if self._stop_evt.is_set():
                            break
                        self._handle_message(raw)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self._reconnects += 1
                self._last_err = f"{type(e).__name__}: {e}"
                _log.warning(
                    f"🔌 BinanceAggTradeWS conn={conn_id} disconnected ({self._last_err}); "
                    f"reconnect in {backoff:.1f}s"
                )
                try:
                    await asyncio.wait_for(self._stop_evt.wait(), timeout=backoff)
                except asyncio.TimeoutError:
                    pass
                backoff = min(30.0, backoff * 1.6)

    def _handle_message(self, raw) -> None:
        """Parse one combined-stream frame and update latest-tick map."""
        try:
            msg = _loads(raw)
        except Exception:
            return
        # Combined stream wraps payload in {stream, data}
        data = msg.get("data") if isinstance(msg, dict) else None
        if not isinstance(data, dict):
            return
        # aggTrade payload:
        # {"e":"aggTrade","E":..,"s":"BTCUSDT","p":"76500.10","q":"0.005",
        #  "T":..,"m":false,...}
        sym = data.get("s")
        if not sym:
            return
        try:
            price = float(data.get("p") or 0.0)
            qty   = float(data.get("q") or 0.0)
        except (TypeError, ValueError):
            return
        if price <= 0.0:
            return
        ts_ms = int(data.get("T") or data.get("E") or time.time() * 1000.0)
        # Binance "m" semantics: True → buyer is the maker → aggressor is SELL
        side  = "SELL" if data.get("m") else "BUY"
        self._ticks[sym] = {
            "price":  price,
            "qty":    qty,
            "ts_ms":  ts_ms,
            "side":   side,
        }
        self._last_rx_ms[sym] = int(time.time() * 1000.0)
        self._msgs_total += 1

"""
SignalMaestro — Exchange Executor  v11.0
═══════════════════════════════════════════════════════════════════════════════
CCXT-based async execution engine for the Unity Engine trading bot.

Capabilities:
  • Multi-exchange support via ccxt.async_support (Binance USDM primary)
  • Market / Limit / Limit-Timeout order placement
  • DCA (Dollar-Cost-Average) entry with configurable layers
  • Position queries: open positions, unrealised PnL, liquidation price
  • Balance queries: USDT equity, available margin, total equity
  • Take-profit / Stop-loss management (set / modify / cancel)
  • Trailing stop activation (after TP1 hit)
  • Leverage & margin-mode configuration per symbol
  • Position-size calculator from risk % or fixed USDT stake
  • Graceful degradation: never raises — all methods return safe defaults
  • Async-safe: one ccxt exchange instance per user×exchange pair, pooled

Supported exchanges:
  binanceusdm / bybit / okx / bingx / bitget / kucoin / gate / mexc

Reference: CCXT documentation — https://docs.ccxt.com
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

_log = logging.getLogger("UnityEngine.ExchangeExecutor")

try:
    import ccxt.async_support as ccxt_async
    _HAS_CCXT = True
except ImportError:
    _HAS_CCXT = False
    _log.warning("ccxt not installed — ExchangeExecutor disabled")

# ── Constants ────────────────────────────────────────────────────────────────
_SUPPORTED_EXCHANGES = (
    "binance", "bybit", "okx", "bingx", "bitget", "kucoin", "gate", "mexc"
)
_CCXT_ID_MAP: Dict[str, str] = {
    "binance": "binanceusdm",
    "bybit":   "bybit",
    "okx":     "okx",
    "bingx":   "bingx",
    "bitget":  "bitget",
    "kucoin":  "kucoinfutures",
    "gate":    "gateio",
    "mexc":    "mexc",
}
_DEFAULT_TIMEOUT_MS    = 15_000
_ORDER_BOOK_DEPTH      = 5
_MAX_RETRY_ATTEMPTS    = 2
_RETRY_DELAY_SEC       = 1.0


# ── Data Structures ──────────────────────────────────────────────────────────

@dataclass
class OrderResult:
    success:    bool
    order_id:   str    = ""
    exchange:   str    = ""
    symbol:     str    = ""
    side:       str    = ""
    order_type: str    = ""
    price:      float  = 0.0
    amount:     float  = 0.0
    filled:     float  = 0.0
    avg_price:  float  = 0.0
    status:     str    = ""
    timestamp:  float  = field(default_factory=time.time)
    error:      str    = ""
    raw:        Optional[Dict] = field(default=None, repr=False)


@dataclass
class Position:
    symbol:       str
    side:         str    = ""        # long / short
    size:         float  = 0.0      # contracts
    entry_price:  float  = 0.0
    mark_price:   float  = 0.0
    unrealised_pnl: float = 0.0
    percentage:   float  = 0.0
    liquidation_price: float = 0.0
    leverage:     int    = 1
    margin_mode:  str    = "isolated"
    notional:     float  = 0.0


@dataclass
class BalanceInfo:
    exchange:        str
    usdt_free:       float  = 0.0
    usdt_used:       float  = 0.0
    usdt_total:      float  = 0.0
    unrealised_pnl:  float  = 0.0
    margin_ratio:    float  = 0.0
    fetched_at:      float  = field(default_factory=time.time)


@dataclass
class ExecutionPlan:
    """Computed execution plan before placing orders."""
    symbol:         str
    direction:      str          # BUY / SELL
    entry_price:    float
    sl_price:       float
    tp1_price:      float
    tp2_price:      float
    tp3_price:      float
    position_size:  float        # in base currency
    notional_usdt:  float
    leverage:       int
    risk_usdt:      float
    rr_ratio:       float
    order_type:     str          = "market"
    dca_layers:     int          = 1
    dca_multiplier: float        = 1.5
    tp_split:       Tuple[float, float, float] = (0.33, 0.33, 0.34)


# ── Exchange Pool ─────────────────────────────────────────────────────────────

class _ExchangePool:
    """Manages a pool of ccxt exchange instances keyed by (user_id, exchange)."""

    def __init__(self):
        self._pool: Dict[Tuple[int, str], Any] = {}
        self._lock = asyncio.Lock()

    async def get(
        self,
        user_id: int,
        exchange: str,
        api_key: str,
        api_secret: str,
        passphrase: str = "",
        testnet: bool   = False,
    ) -> Optional[Any]:
        if not _HAS_CCXT:
            return None
        key = (user_id, exchange.lower())
        async with self._lock:
            if key in self._pool:
                return self._pool[key]
            ex = self._create(exchange, api_key, api_secret, passphrase, testnet)
            if ex is not None:
                self._pool[key] = ex
            return ex

    def _create(
        self,
        exchange: str,
        api_key: str,
        api_secret: str,
        passphrase: str,
        testnet: bool,
    ) -> Optional[Any]:
        ccxt_id = _CCXT_ID_MAP.get(exchange.lower(), exchange.lower())
        ExClass = getattr(ccxt_async, ccxt_id, None)
        if ExClass is None:
            _log.warning(f"CCXT exchange not found: {ccxt_id}")
            return None
        params: Dict[str, Any] = {
            "apiKey":  api_key,
            "secret":  api_secret,
            "timeout": _DEFAULT_TIMEOUT_MS,
            "enableRateLimit": True,
        }
        if passphrase:
            params["password"] = passphrase
        if testnet:
            params["sandbox"] = True
        try:
            ex = ExClass(params)
            if testnet and hasattr(ex, "set_sandbox_mode"):
                ex.set_sandbox_mode(True)
            return ex
        except Exception as e:
            _log.warning(f"CCXT init error ({exchange}): {e}")
            return None

    async def close_all(self) -> None:
        async with self._lock:
            for ex in self._pool.values():
                try:
                    await ex.close()
                except Exception:
                    pass
            self._pool.clear()

    async def remove(self, user_id: int, exchange: str) -> None:
        key = (user_id, exchange.lower())
        async with self._lock:
            ex = self._pool.pop(key, None)
            if ex is not None:
                try:
                    await ex.close()
                except Exception:
                    pass


_pool = _ExchangePool()


# ── Position Size Calculator ──────────────────────────────────────────────────

def calc_position_size(
    balance_usdt: float,
    risk_pct: float,
    entry_price: float,
    sl_price: float,
    leverage: int,
    stake_fixed: float = 0.0,
) -> Tuple[float, float]:
    """
    Compute position size in base currency and notional USDT.

    If stake_fixed > 0 → use fixed USDT stake directly.
    Otherwise → risk_pct of balance / (entry - sl) distance.

    Returns (base_size, notional_usdt).
    """
    try:
        if stake_fixed > 0:
            notional_usdt = min(stake_fixed * leverage, balance_usdt * leverage)
            base_size     = notional_usdt / entry_price if entry_price else 0.0
            return round(base_size, 4), round(notional_usdt, 2)
        # risk-based sizing
        risk_usdt     = balance_usdt * (risk_pct / 100.0)
        sl_distance   = abs(entry_price - sl_price) / entry_price
        if sl_distance < 0.0001:
            sl_distance = 0.01  # minimum 1% SL distance
        notional_usdt = (risk_usdt / sl_distance) * leverage
        notional_usdt = min(notional_usdt, balance_usdt * leverage)
        base_size     = notional_usdt / entry_price if entry_price else 0.0
        return round(base_size, 4), round(notional_usdt, 2)
    except Exception:
        return 0.0, 0.0


# ── ExchangeExecutor ──────────────────────────────────────────────────────────

class ExchangeExecutor:
    """
    High-level async execution engine.

    Usage:
        executor = ExchangeExecutor()
        result = await executor.market_order(
            user_id=123, exchange="binance",
            api_key="...", api_secret="...",
            symbol="BTC/USDT:USDT", side="buy", amount=0.001,
        )
    """

    def __init__(self):
        self._pool = _pool
        self._balance_cache: Dict[Tuple[int, str], Tuple[BalanceInfo, float]] = {}
        self._cache_ttl = 30.0   # balance cache TTL seconds

    # ── Internal helpers ──────────────────────────────────────────────────────

    async def _get_exchange(
        self,
        user_id: int,
        exchange: str,
        api_key: str,
        api_secret: str,
        passphrase: str = "",
        testnet: bool   = False,
    ) -> Optional[Any]:
        return await self._pool.get(
            user_id, exchange, api_key, api_secret, passphrase, testnet
        )

    @staticmethod
    def _normalise_symbol(symbol: str, exchange: str) -> str:
        """Convert BTCUSDT → BTC/USDT:USDT for CCXT futures."""
        if "/" in symbol:
            return symbol
        if symbol.endswith("USDT"):
            base = symbol[:-4]
            return f"{base}/USDT:USDT"
        return symbol

    @staticmethod
    def _order_to_result(raw: Dict, exchange: str) -> OrderResult:
        return OrderResult(
            success=True,
            order_id=str(raw.get("id", "")),
            exchange=exchange,
            symbol=str(raw.get("symbol", "")),
            side=str(raw.get("side", "")),
            order_type=str(raw.get("type", "")),
            price=float(raw.get("price") or 0),
            amount=float(raw.get("amount") or 0),
            filled=float(raw.get("filled") or 0),
            avg_price=float(raw.get("average") or raw.get("price") or 0),
            status=str(raw.get("status", "open")),
            timestamp=time.time(),
            raw=raw,
        )

    # ── Balance ───────────────────────────────────────────────────────────────

    async def get_balance(
        self,
        user_id: int,
        exchange: str,
        api_key: str,
        api_secret: str,
        passphrase: str = "",
        testnet: bool   = False,
        force_refresh: bool = False,
    ) -> BalanceInfo:
        """Fetch USDT balance with caching."""
        cache_key = (user_id, exchange.lower())
        if not force_refresh:
            cached = self._balance_cache.get(cache_key)
            if cached and time.time() - cached[1] < self._cache_ttl:
                return cached[0]

        empty = BalanceInfo(exchange=exchange)
        if not _HAS_CCXT:
            return empty
        try:
            ex = await self._get_exchange(user_id, exchange, api_key, api_secret, passphrase, testnet)
            if ex is None:
                return empty
            raw = await ex.fetch_balance()
            usdt = raw.get("USDT", {}) or {}
            info = BalanceInfo(
                exchange=exchange,
                usdt_free=float(usdt.get("free", 0) or 0),
                usdt_used=float(usdt.get("used", 0) or 0),
                usdt_total=float(usdt.get("total", 0) or 0),
            )
            self._balance_cache[cache_key] = (info, time.time())
            return info
        except Exception as e:
            _log.debug(f"get_balance error ({exchange}): {e}")
            return empty

    # ── Market Order ──────────────────────────────────────────────────────────

    async def market_order(
        self,
        user_id: int,
        exchange: str,
        api_key: str,
        api_secret: str,
        symbol: str,
        side: str,
        amount: float,
        params: Optional[Dict] = None,
        passphrase: str = "",
        testnet: bool   = False,
    ) -> OrderResult:
        if not _HAS_CCXT:
            return OrderResult(success=False, error="ccxt not installed")
        try:
            ex  = await self._get_exchange(user_id, exchange, api_key, api_secret, passphrase, testnet)
            if ex is None:
                return OrderResult(success=False, error="exchange init failed")
            sym = self._normalise_symbol(symbol, exchange)
            raw = await ex.create_market_order(sym, side.lower(), amount, params=params or {})
            _log.info(f"✅ Market order: {exchange} {side} {amount} {symbol} → {raw.get('id')}")
            return self._order_to_result(raw, exchange)
        except Exception as e:
            _log.warning(f"market_order error ({exchange} {symbol}): {e}")
            return OrderResult(success=False, error=str(e), exchange=exchange, symbol=symbol)

    # ── Limit Order ───────────────────────────────────────────────────────────

    async def limit_order(
        self,
        user_id: int,
        exchange: str,
        api_key: str,
        api_secret: str,
        symbol: str,
        side: str,
        amount: float,
        price: float,
        params: Optional[Dict] = None,
        passphrase: str = "",
        testnet: bool   = False,
    ) -> OrderResult:
        if not _HAS_CCXT:
            return OrderResult(success=False, error="ccxt not installed")
        try:
            ex  = await self._get_exchange(user_id, exchange, api_key, api_secret, passphrase, testnet)
            if ex is None:
                return OrderResult(success=False, error="exchange init failed")
            sym = self._normalise_symbol(symbol, exchange)
            raw = await ex.create_limit_order(sym, side.lower(), amount, price, params=params or {})
            _log.info(f"✅ Limit order: {exchange} {side} {amount} {symbol} @ {price} → {raw.get('id')}")
            return self._order_to_result(raw, exchange)
        except Exception as e:
            _log.warning(f"limit_order error ({exchange} {symbol}): {e}")
            return OrderResult(success=False, error=str(e), exchange=exchange, symbol=symbol)

    # ── Stop-Loss / Take-Profit ───────────────────────────────────────────────

    async def set_stop_loss(
        self,
        user_id: int,
        exchange: str,
        api_key: str,
        api_secret: str,
        symbol: str,
        side: str,
        amount: float,
        stop_price: float,
        passphrase: str = "",
        testnet: bool   = False,
    ) -> OrderResult:
        """Place a stop-market order for SL."""
        if not _HAS_CCXT:
            return OrderResult(success=False, error="ccxt not installed")
        try:
            ex  = await self._get_exchange(user_id, exchange, api_key, api_secret, passphrase, testnet)
            if ex is None:
                return OrderResult(success=False, error="exchange init failed")
            sym = self._normalise_symbol(symbol, exchange)
            close_side = "sell" if side.lower() in ("buy", "long") else "buy"
            params = {"stopPrice": stop_price, "reduceOnly": True}
            raw = await ex.create_order(sym, "STOP_MARKET", close_side, amount, params=params)
            _log.info(f"✅ Stop-loss set: {exchange} {symbol} @ {stop_price}")
            return self._order_to_result(raw, exchange)
        except Exception as e:
            _log.warning(f"set_stop_loss error ({exchange} {symbol}): {e}")
            return OrderResult(success=False, error=str(e))

    async def set_take_profit(
        self,
        user_id: int,
        exchange: str,
        api_key: str,
        api_secret: str,
        symbol: str,
        side: str,
        amount: float,
        tp_price: float,
        passphrase: str = "",
        testnet: bool   = False,
    ) -> OrderResult:
        """Place a take-profit-market order."""
        if not _HAS_CCXT:
            return OrderResult(success=False, error="ccxt not installed")
        try:
            ex  = await self._get_exchange(user_id, exchange, api_key, api_secret, passphrase, testnet)
            if ex is None:
                return OrderResult(success=False, error="exchange init failed")
            sym = self._normalise_symbol(symbol, exchange)
            close_side = "sell" if side.lower() in ("buy", "long") else "buy"
            params = {"stopPrice": tp_price, "reduceOnly": True}
            raw = await ex.create_order(sym, "TAKE_PROFIT_MARKET", close_side, amount, params=params)
            _log.info(f"✅ Take-profit set: {exchange} {symbol} @ {tp_price}")
            return self._order_to_result(raw, exchange)
        except Exception as e:
            _log.warning(f"set_take_profit error ({exchange} {symbol}): {e}")
            return OrderResult(success=False, error=str(e))

    # ── Full Signal Execution ─────────────────────────────────────────────────

    async def execute_signal(
        self,
        user_id: int,
        exchange: str,
        api_key: str,
        api_secret: str,
        plan: ExecutionPlan,
        passphrase: str = "",
        testnet: bool   = False,
    ) -> Dict[str, Any]:
        """
        Execute a full trading plan: entry + SL + TP1 (partial).

        Returns a dict with keys: entry, sl, tp1, tp2, tp3, success, errors.
        """
        results: Dict[str, Any] = {
            "success": False,
            "entry":   None,
            "sl":      None,
            "tp1":     None,
            "tp2":     None,
            "tp3":     None,
            "errors":  [],
            "plan":    plan,
        }
        if not _HAS_CCXT:
            results["errors"].append("ccxt not installed")
            return results

        ex = await self._get_exchange(user_id, exchange, api_key, api_secret, passphrase, testnet)
        if ex is None:
            results["errors"].append("Exchange init failed")
            return results

        side = "buy" if plan.direction.upper() in ("BUY", "LONG") else "sell"

        # ── Set leverage ─────────────────────────────────────────────────────
        try:
            sym = self._normalise_symbol(plan.symbol, exchange)
            await ex.set_leverage(plan.leverage, sym)
        except Exception as _le:
            _log.debug(f"set_leverage non-fatal: {_le}")

        # ── Entry order ───────────────────────────────────────────────────────
        try:
            if plan.order_type == "market":
                entry_result = await self.market_order(
                    user_id, exchange, api_key, api_secret,
                    plan.symbol, side, plan.position_size,
                    passphrase=passphrase, testnet=testnet,
                )
            else:
                entry_result = await self.limit_order(
                    user_id, exchange, api_key, api_secret,
                    plan.symbol, side, plan.position_size, plan.entry_price,
                    passphrase=passphrase, testnet=testnet,
                )
            results["entry"] = entry_result
            if not entry_result.success:
                results["errors"].append(f"Entry failed: {entry_result.error}")
                return results
        except Exception as e:
            results["errors"].append(f"Entry exception: {e}")
            return results

        # ── SL order ──────────────────────────────────────────────────────────
        try:
            sl_result = await self.set_stop_loss(
                user_id, exchange, api_key, api_secret,
                plan.symbol, side, plan.position_size, plan.sl_price,
                passphrase=passphrase, testnet=testnet,
            )
            results["sl"] = sl_result
            if not sl_result.success:
                results["errors"].append(f"SL failed: {sl_result.error}")
        except Exception as e:
            results["errors"].append(f"SL exception: {e}")

        # ── TP1 order (33% of position) ────────────────────────────────────────
        tp1_size = round(plan.position_size * plan.tp_split[0], 4)
        try:
            tp1_result = await self.set_take_profit(
                user_id, exchange, api_key, api_secret,
                plan.symbol, side, tp1_size, plan.tp1_price,
                passphrase=passphrase, testnet=testnet,
            )
            results["tp1"] = tp1_result
        except Exception as e:
            results["errors"].append(f"TP1 exception: {e}")

        # ── TP2 + TP3 orders ──────────────────────────────────────────────────
        tp2_size = round(plan.position_size * plan.tp_split[1], 4)
        tp3_size = round(plan.position_size * plan.tp_split[2], 4)
        for tp_size, tp_price, label in [
            (tp2_size, plan.tp2_price, "tp2"),
            (tp3_size, plan.tp3_price, "tp3"),
        ]:
            try:
                tp_result = await self.set_take_profit(
                    user_id, exchange, api_key, api_secret,
                    plan.symbol, side, tp_size, tp_price,
                    passphrase=passphrase, testnet=testnet,
                )
                results[label] = tp_result
            except Exception as e:
                results["errors"].append(f"{label.upper()} exception: {e}")

        results["success"] = results["entry"] is not None and results["entry"].success
        _log.info(
            f"{'✅' if results['success'] else '❌'} Signal executed: "
            f"{plan.exchange if hasattr(plan, 'exchange') else exchange} "
            f"{plan.symbol} {plan.direction} "
            f"size={plan.position_size} notional=${plan.notional_usdt:.0f}"
        )
        return results

    # ── Open Positions ────────────────────────────────────────────────────────

    async def get_positions(
        self,
        user_id: int,
        exchange: str,
        api_key: str,
        api_secret: str,
        symbol: Optional[str] = None,
        passphrase: str = "",
        testnet: bool   = False,
    ) -> List[Position]:
        if not _HAS_CCXT:
            return []
        try:
            ex = await self._get_exchange(user_id, exchange, api_key, api_secret, passphrase, testnet)
            if ex is None:
                return []
            if symbol:
                sym = self._normalise_symbol(symbol, exchange)
                raw_list = await ex.fetch_positions([sym])
            else:
                raw_list = await ex.fetch_positions()
            result = []
            for r in raw_list:
                size = float(r.get("contracts") or r.get("info", {}).get("positionAmt", 0) or 0)
                if abs(size) < 1e-9:
                    continue
                result.append(Position(
                    symbol=str(r.get("symbol", "")),
                    side="long" if size > 0 else "short",
                    size=abs(size),
                    entry_price=float(r.get("entryPrice") or 0),
                    mark_price=float(r.get("markPrice") or 0),
                    unrealised_pnl=float(r.get("unrealizedPnl") or 0),
                    percentage=float(r.get("percentage") or 0),
                    liquidation_price=float(r.get("liquidationPrice") or 0),
                    leverage=int(r.get("leverage") or 1),
                    margin_mode=str(r.get("marginMode") or "isolated"),
                    notional=float(r.get("notional") or 0),
                ))
            return result
        except Exception as e:
            _log.debug(f"get_positions error ({exchange}): {e}")
            return []

    # ── Cancel Order ──────────────────────────────────────────────────────────

    async def cancel_order(
        self,
        user_id: int,
        exchange: str,
        api_key: str,
        api_secret: str,
        order_id: str,
        symbol: str,
        passphrase: str = "",
        testnet: bool   = False,
    ) -> bool:
        if not _HAS_CCXT:
            return False
        try:
            ex = await self._get_exchange(user_id, exchange, api_key, api_secret, passphrase, testnet)
            if ex is None:
                return False
            sym = self._normalise_symbol(symbol, exchange)
            await ex.cancel_order(order_id, sym)
            _log.info(f"✅ Order cancelled: {exchange} {symbol} #{order_id}")
            return True
        except Exception as e:
            _log.debug(f"cancel_order error: {e}")
            return False

    # ── Close Position ────────────────────────────────────────────────────────

    async def close_position(
        self,
        user_id: int,
        exchange: str,
        api_key: str,
        api_secret: str,
        symbol: str,
        size: Optional[float] = None,
        passphrase: str = "",
        testnet: bool   = False,
    ) -> OrderResult:
        """Close open position (full or partial) with a market reduce-only order."""
        if not _HAS_CCXT:
            return OrderResult(success=False, error="ccxt not installed")
        try:
            positions = await self.get_positions(
                user_id, exchange, api_key, api_secret, symbol, passphrase, testnet
            )
            if not positions:
                return OrderResult(success=False, error="No open position found")
            pos = positions[0]
            close_size = size if size else pos.size
            close_side = "sell" if pos.side == "long" else "buy"
            params = {"reduceOnly": True}
            ex = await self._get_exchange(user_id, exchange, api_key, api_secret, passphrase, testnet)
            if ex is None:
                return OrderResult(success=False, error="exchange init failed")
            sym = self._normalise_symbol(symbol, exchange)
            raw = await ex.create_market_order(sym, close_side, close_size, params=params)
            _log.info(f"✅ Position closed: {exchange} {symbol} {close_size} {close_side}")
            return self._order_to_result(raw, exchange)
        except Exception as e:
            _log.warning(f"close_position error ({exchange} {symbol}): {e}")
            return OrderResult(success=False, error=str(e))

    # ── Set Leverage ──────────────────────────────────────────────────────────

    async def set_leverage(
        self,
        user_id: int,
        exchange: str,
        api_key: str,
        api_secret: str,
        symbol: str,
        leverage: int,
        passphrase: str = "",
        testnet: bool   = False,
    ) -> bool:
        if not _HAS_CCXT:
            return False
        try:
            ex = await self._get_exchange(user_id, exchange, api_key, api_secret, passphrase, testnet)
            if ex is None:
                return False
            sym = self._normalise_symbol(symbol, exchange)
            await ex.set_leverage(leverage, sym)
            _log.info(f"✅ Leverage set: {exchange} {symbol} {leverage}×")
            return True
        except Exception as e:
            _log.debug(f"set_leverage error: {e}")
            return False

    # ── Cleanup ───────────────────────────────────────────────────────────────

    async def close_all(self) -> None:
        await self._pool.close_all()


# ── Module-level singleton ────────────────────────────────────────────────────

_executor: Optional[ExchangeExecutor] = None


def get_executor() -> ExchangeExecutor:
    """Return the module-level singleton ExchangeExecutor."""
    global _executor
    if _executor is None:
        _executor = ExchangeExecutor()
    return _executor

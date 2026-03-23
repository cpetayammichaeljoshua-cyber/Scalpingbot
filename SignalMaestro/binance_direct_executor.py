#!/usr/bin/env python3
"""
Binance Direct Executor — Production Grade
==========================================
Trades directly into Binance Futures account WITHOUT Cornix.
Still sends signals to Telegram channel in Cornix-compatible format.

Configuration (from Cornix images):
  • Risk Per Trade     : 2% of account balance
  • Direction          : Long + Short (Hedge Mode)
  • Leverage           : Isolated — reads from signal (channel leverage)
  • Skip No-SL Signals : Off (signals without SL still accepted; default SL applied)
  • Stop Timeout       : Off
  • Leveraged Trailing : Personal → Moving Target, Trigger: #1 (after TP1 hit)
  • Trailing Entry     : Without
  • Trailing Take Profit: Without
  • Stop Type          : Market
  • Position Mode      : Hedge Mode
  • Alternative USD Pairs: Off
  • Operation Hours    : 24/7 (Off = always on)

Regional Bypass:
  • Multiple Binance FAPI endpoint fallbacks
  • Optional HTTP/SOCKS5 proxy via BINANCE_PROXY env var
  • Custom timeout + retry with exponential backoff
  • CCXT 4.5 async_support
"""

import asyncio
import logging
import os
import time
import math
from decimal import Decimal, ROUND_DOWN, InvalidOperation
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
from dataclasses import dataclass, field

import ccxt.async_support as ccxt

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Configuration constants (image-derived)
# ─────────────────────────────────────────────────────────────────────────────

RISK_PERCENT          = float(os.getenv("DIRECT_RISK_PERCENT", "2.0"))   # 2% per trade
MIN_LEVERAGE          = int(os.getenv("DIRECT_MIN_LEVERAGE", "3"))
MAX_LEVERAGE          = int(os.getenv("DIRECT_MAX_LEVERAGE", "20"))
DEFAULT_LEVERAGE      = int(os.getenv("DIRECT_DEFAULT_LEVERAGE", "6"))   # isolated 6x from image
MARGIN_TYPE           = "ISOLATED"                                        # Isolated — Channel
POSITION_MODE         = "HEDGE"                                           # Hedge Mode
STOP_TYPE             = "MARKET"                                          # Market stop
TRAILING_ENTRY        = False                                             # Without
TRAILING_TP           = False                                             # Without
TRAILING_STOP_ENABLED = True                                              # Moving Target, Trigger #1
TRAILING_STOP_TRIGGER = 1                                                 # TP1 hit = trigger
SKIP_NO_SL            = False                                             # Off — always trade
DEFAULT_SL_PCT        = float(os.getenv("DIRECT_DEFAULT_SL_PCT", "1.5")) # fallback SL %

# Regional bypass: alternative FAPI base URLs
FAPI_ENDPOINTS = [
    "https://fapi.binance.com",
    "https://fapi1.binance.com",
    "https://fapi2.binance.com",
    "https://fapi3.binance.com",
]

# Request config
REQUEST_TIMEOUT_MS = 20_000
MAX_RETRIES        = 4
RETRY_DELAY_BASE   = 2.0   # seconds (exponential backoff)
RATE_LIMIT_MS      = 1_200  # Binance weight limit

# Position size limits (USDT)
MIN_NOTIONAL = float(os.getenv("DIRECT_MIN_NOTIONAL", "5.0"))  # Binance min $5


# ─────────────────────────────────────────────────────────────────────────────
# Data structures
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TradeRecord:
    symbol:       str
    direction:    str          # "LONG" or "SHORT"
    side:         str          # "buy" / "sell" (CCXT convention for hedge open)
    entry_price:  float
    quantity:     float
    leverage:     int
    stop_loss:    float
    take_profit_1: float
    take_profit_2: float
    take_profit_3: float
    sl_order_id:  Optional[str]  = None
    tp1_order_id: Optional[str]  = None
    tp2_order_id: Optional[str]  = None
    tp3_order_id: Optional[str]  = None
    opened_at:    datetime        = field(default_factory=datetime.utcnow)
    tp1_hit:      bool            = False
    tp2_hit:      bool            = False
    trailing_active: bool         = False
    trailing_price:  float        = 0.0   # highest/lowest price seen after trigger
    closed:       bool            = False


# ─────────────────────────────────────────────────────────────────────────────
# Moving Target Trailing Stop
# ─────────────────────────────────────────────────────────────────────────────

class MovingTargetTrailingStop:
    """
    Moving Target trailing stop — Trigger: #1 (activates after TP1 is hit).
    Logic:
      LONG:  track highest price since TP1; trail SL = highest * (1 - trail_pct)
      SHORT: track lowest  price since TP1; trail SL = lowest  * (1 + trail_pct)
    The trail_pct is derived from the original SL distance at time of TP1 hit.
    """

    def __init__(self, trade: TradeRecord, trigger_tp: float, trail_pct: Optional[float] = None):
        self.trade       = trade
        self.trigger_tp  = trigger_tp
        self.trail_pct   = trail_pct  # None = auto-compute from original SL distance
        self.active      = False
        self.extreme_price = 0.0      # max for LONG, min for SHORT
        self._auto_trail_pct: Optional[float] = None

    def activate(self, current_price: float):
        """Call once when TP1 is hit to start trailing."""
        self.active      = True
        self.extreme_price = current_price
        # Auto trail_pct: half the original SL-to-entry distance
        if self.trail_pct is None:
            entry = self.trade.entry_price
            sl    = self.trade.stop_loss
            if entry > 0:
                raw_dist = abs(entry - sl) / entry
                self._auto_trail_pct = max(raw_dist * 0.5, 0.003)  # min 0.3%
            else:
                self._auto_trail_pct = 0.005
        else:
            self._auto_trail_pct = self.trail_pct
        logger.info(
            f"🎯 Moving Target trailing ACTIVE for {self.trade.symbol} "
            f"{self.trade.direction} | trail_pct={self._auto_trail_pct:.3%}"
        )

    def update(self, current_price: float) -> Optional[float]:
        """
        Update with new price. Returns new SL if it moved up (LONG) / down (SHORT),
        else None.
        """
        if not self.active:
            return None

        pct = self._auto_trail_pct or 0.005
        if self.trade.direction == "LONG":
            if current_price > self.extreme_price:
                self.extreme_price = current_price
            new_sl = self.extreme_price * (1.0 - pct)
            if new_sl > self.trade.stop_loss:
                self.trade.stop_loss = new_sl
                return new_sl
        else:  # SHORT
            if current_price < self.extreme_price or self.extreme_price == 0:
                self.extreme_price = current_price
            new_sl = self.extreme_price * (1.0 + pct)
            if new_sl < self.trade.stop_loss or self.trade.stop_loss == 0:
                self.trade.stop_loss = new_sl
                return new_sl
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Binance Direct Executor
# ─────────────────────────────────────────────────────────────────────────────

class BinanceDirectExecutor:
    """
    Executes trades directly on Binance Futures (USDM Perpetual).
    No Cornix dependency — signals are still broadcast via Telegram.

    Key features:
    • Hedge Mode (simultaneous LONG + SHORT on same symbol)
    • Isolated margin per position
    • 2% risk-based position sizing
    • Moving Target trailing stop after TP1 hit
    • Market stop orders (faster fill, less slippage on stop)
    • Regional bypass: multiple FAPI endpoints + optional proxy
    • Full retry + circuit breaker
    """

    def __init__(self):
        self.api_key    = os.getenv("BINANCE_API_KEY", "").strip()
        self.api_secret = os.getenv("BINANCE_API_SECRET", "").strip()
        self.testnet    = os.getenv("BINANCE_TESTNET", "false").lower() == "true"
        self.proxy      = os.getenv("BINANCE_PROXY", "").strip() or None  # e.g. "http://user:pass@host:port"

        self.exchange: Optional[ccxt.binance] = None
        self._markets: Dict[str, Any]          = {}
        self._account_balance: float           = 0.0
        self._last_balance_fetch: float        = 0.0
        self._balance_ttl: float               = 30.0  # seconds

        # Active trade records: symbol+direction → TradeRecord
        self._trades: Dict[str, TradeRecord]   = {}
        # Moving target trailing stops: symbol+direction → MovingTargetTrailingStop
        self._trailing: Dict[str, MovingTargetTrailingStop] = {}

        # Circuit breaker
        self._consecutive_errors: int  = 0
        self._cb_tripped_until: float  = 0.0
        self._cb_threshold: int        = 5
        self._cb_cooldown: float       = 120.0  # 2 minutes

        # Hedge mode set flag (avoid re-calling every trade)
        self._hedge_mode_set: bool     = False
        # Margin type set per symbol
        self._margin_type_set: set     = set()
        # Leverage set per symbol
        self._leverage_set: Dict[str, int] = {}

        # Price monitor task
        self._monitor_task: Optional[asyncio.Task] = None
        self._running: bool = False

        logger.info(
            f"🔥 BinanceDirectExecutor initialized | "
            f"risk={RISK_PERCENT}% | mode=HEDGE | margin=ISOLATED | "
            f"trailing=Moving-Target(trigger=TP1) | "
            f"{'TESTNET' if self.testnet else 'MAINNET'} | "
            f"proxy={'YES' if self.proxy else 'none'}"
        )

    # ─────────────────────────────────────────
    # Lifecycle
    # ─────────────────────────────────────────

    async def initialize(self) -> bool:
        """Connect to Binance, load markets, configure account."""
        if not self.api_key or not self.api_secret:
            logger.warning("⚠️ No Binance API keys — executor in signal-only mode")
            return False

        for attempt, endpoint in enumerate(FAPI_ENDPOINTS, 1):
            try:
                opts: Dict[str, Any] = {
                    "apiKey":          self.api_key,
                    "secret":          self.api_secret,
                    "sandbox":         self.testnet,
                    "timeout":         REQUEST_TIMEOUT_MS,
                    "rateLimit":       RATE_LIMIT_MS,
                    "enableRateLimit": True,
                    "options": {
                        "defaultType":      "future",
                        "hedgeMode":        True,
                        "fetchPositions":   True,
                        "recvWindow":       10000,
                        "adjustForTimeDifference": True,
                    },
                }
                if self.proxy:
                    opts["proxies"] = {
                        "http":  self.proxy,
                        "https": self.proxy,
                    }
                if not self.testnet:
                    opts["urls"] = {
                        "api": {
                            "fapiPublic":  f"{endpoint}/fapi/v1",
                            "fapiPrivate": f"{endpoint}/fapi/v1",
                            "fapiPublicV2":  f"{endpoint}/fapi/v2",
                            "fapiPrivateV2": f"{endpoint}/fapi/v2",
                        }
                    }

                ex = ccxt.binance(opts)
                await ex.load_markets()
                self.exchange  = ex
                self._markets  = ex.markets or {}
                logger.info(
                    f"✅ Binance connected via {endpoint} | "
                    f"{len(self._markets)} futures markets loaded"
                )
                break
            except Exception as e:
                logger.warning(f"⚠️ Endpoint {endpoint} failed ({attempt}/{len(FAPI_ENDPOINTS)}): {e}")
                if attempt == len(FAPI_ENDPOINTS):
                    logger.error("❌ All FAPI endpoints failed — direct trading disabled")
                    return False
                await asyncio.sleep(RETRY_DELAY_BASE * attempt)

        try:
            await self._ensure_hedge_mode()
            self._running = True
            self._monitor_task = asyncio.create_task(self._position_monitor_loop())
            logger.info("✅ BinanceDirectExecutor fully online — position monitor running")
            return True
        except Exception as e:
            logger.error(f"❌ Account setup failed: {e}")
            return False

    async def aclose(self):
        """Graceful shutdown."""
        self._running = False
        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        if self.exchange:
            try:
                await self.exchange.close()
            except Exception:
                pass
        logger.info("🔌 BinanceDirectExecutor closed")

    # ─────────────────────────────────────────
    # Account Setup
    # ─────────────────────────────────────────

    async def _ensure_hedge_mode(self):
        """Set dual/hedge position mode if not already set."""
        if self._hedge_mode_set:
            return
        try:
            # CCXT 4.5: use set_position_mode for hedge mode
            # positionSide: True = hedge (dual), False = one-way
            await self.exchange.set_position_mode(True)
            logger.info("✅ Hedge mode (dual-side) enabled on account")
            self._hedge_mode_set = True
        except ccxt.AuthenticationError:
            logger.warning(
                "⚠️ Hedge mode: API key lacks futures permission.\n"
                "   ACTION REQUIRED: Enable 'Enable Futures' on your Binance API key at:\n"
                "   https://www.binance.com/en/my/settings/api-management\n"
                "   Direct trading is paused until this is fixed."
            )
            self._hedge_mode_set = True  # avoid repeated attempts
        except Exception as e:
            err = str(e)
            if "-4059" in err or "No need" in err or "already" in err.lower():
                logger.info("✅ Hedge mode already active (server confirmed)")
                self._hedge_mode_set = True
            elif "-2015" in err or "-2014" in err:
                logger.warning(
                    "⚠️ Hedge mode: Invalid API-key or insufficient permissions.\n"
                    "   Ensure your Binance API key has 'Enable Futures' permission.\n"
                    "   Visit: https://www.binance.com/en/my/settings/api-management"
                )
                self._hedge_mode_set = True
            else:
                logger.warning(f"⚠️ Hedge mode setup (non-fatal): {e}")
                self._hedge_mode_set = True

    async def _set_margin_type(self, symbol: str, leverage: int):
        """Set ISOLATED margin type + leverage for a symbol."""
        ccxt_sym = self._to_ccxt_symbol(symbol)
        if ccxt_sym in self._margin_type_set and self._leverage_set.get(ccxt_sym) == leverage:
            return

        def _check_auth_err(err: str, exc: Exception):
            """Raise AuthenticationError if -2015 detected."""
            if "-2015" in err or "-2014" in err:
                self._api_auth_failed = True
                raise ccxt.AuthenticationError(
                    "Binance -2015: Invalid API key or missing Futures permission. "
                    "Enable 'Enable Futures' at binance.com/my/settings/api-management"
                )

        # Set margin type
        try:
            await self._retry(
                self.exchange.set_margin_mode,
                "isolated", ccxt_sym
            )
            logger.debug(f"✅ ISOLATED margin set for {symbol}")
        except ccxt.AuthenticationError:
            raise  # propagate
        except Exception as e:
            err = str(e)
            _check_auth_err(err, e)
            if "already" in err.lower() or "-4046" in err:
                logger.debug(f"Margin already ISOLATED for {symbol}")
            else:
                logger.warning(f"⚠️ Margin type set warning for {symbol}: {e}")

        # Set leverage
        try:
            await self._retry(
                self.exchange.set_leverage,
                leverage, ccxt_sym, {"isolated": True}
            )
            self._leverage_set[ccxt_sym] = leverage
            logger.debug(f"✅ Leverage {leverage}x set for {symbol}")
        except ccxt.AuthenticationError:
            raise  # propagate
        except Exception as e:
            err = str(e)
            _check_auth_err(err, e)
            logger.warning(f"⚠️ Leverage set warning for {symbol}: {e}")

        self._margin_type_set.add(ccxt_sym)

    # ─────────────────────────────────────────
    # Balance
    # ─────────────────────────────────────────

    async def _get_usdt_balance(self) -> float:
        """Fetch free USDT balance (cached for balance_ttl seconds)."""
        now = time.time()
        if now - self._last_balance_fetch < self._balance_ttl and self._account_balance > 0:
            return self._account_balance
        try:
            bal = await self._retry(self.exchange.fetch_balance, {"type": "future"})
            self._account_balance = float(bal.get("USDT", {}).get("free", 0) or 0)
            self._last_balance_fetch = now
            return self._account_balance
        except Exception as e:
            logger.warning(f"⚠️ Balance fetch failed: {e}")
            return self._account_balance or 0.0

    # ─────────────────────────────────────────
    # Position Sizing
    # ─────────────────────────────────────────

    def _calc_quantity(
        self,
        entry: float,
        stop_loss: float,
        leverage: int,
        balance: float,
    ) -> float:
        """
        Risk-based position sizing: risk 2% of balance.
        quantity = (balance * risk_pct) / (|entry - sl| / leverage)
        Clamped to satisfy MIN_NOTIONAL.
        """
        if entry <= 0 or stop_loss <= 0:
            return 0.0
        risk_amount = balance * (RISK_PERCENT / 100.0)
        sl_distance = abs(entry - stop_loss)
        if sl_distance < 1e-12:
            logger.warning("⚠️ SL too close to entry — using default SL pct")
            sl_distance = entry * (DEFAULT_SL_PCT / 100.0)

        # With leverage, our margin = qty * entry / leverage
        # Loss per contract if SL hit = |entry - sl|
        # qty = risk_amount / sl_distance (no leverage needed in formula: pnl = qty * sl_dist)
        qty = risk_amount / sl_distance
        notional = qty * entry
        if notional < MIN_NOTIONAL:
            qty = MIN_NOTIONAL / entry
        return qty

    def _round_quantity(self, symbol: str, qty: float) -> float:
        """Round quantity to exchange precision."""
        ccxt_sym = self._to_ccxt_symbol(symbol)
        market = self._markets.get(ccxt_sym, {})
        precision = market.get("precision", {}).get("amount", 3)
        try:
            step = 10 ** (-precision)
            return math.floor(qty / step) * step
        except Exception:
            return round(qty, 3)

    def _round_price(self, symbol: str, price: float) -> float:
        """Round price to exchange tick size."""
        ccxt_sym = self._to_ccxt_symbol(symbol)
        market = self._markets.get(ccxt_sym, {})
        precision = market.get("precision", {}).get("price", 6)
        try:
            tick = 10 ** (-precision)
            return round(price / tick) * tick
        except Exception:
            return round(price, 6)

    # ─────────────────────────────────────────
    # Core Trade Execution
    # ─────────────────────────────────────────

    async def execute_signal(self, signal: Any) -> Dict[str, Any]:
        """
        Main entry point: execute a SwarmSignal directly on Binance.
        Returns a result dict with trade details.

        Args:
            signal: SwarmSignal (or any object with symbol, action, entry_price,
                    stop_loss, take_profit_1/2/3, leverage attributes)
        """
        if not self.exchange:
            return {"success": False, "reason": "executor_not_initialized"}

        if self._circuit_breaker_active():
            return {"success": False, "reason": "circuit_breaker"}

        symbol    = getattr(signal, "symbol", "BTCUSDT")
        direction = "LONG" if getattr(signal, "action", "BUY") in ("BUY", "LONG") else "SHORT"
        entry     = float(getattr(signal, "entry_price", 0))
        sl        = float(getattr(signal, "stop_loss",   0))
        tp1       = float(getattr(signal, "take_profit_1", 0))
        tp2       = float(getattr(signal, "take_profit_2", 0))
        tp3       = float(getattr(signal, "take_profit_3", 0))
        leverage  = int(getattr(signal, "leverage", DEFAULT_LEVERAGE))
        leverage  = max(MIN_LEVERAGE, min(MAX_LEVERAGE, leverage))

        if entry <= 0:
            return {"success": False, "reason": "invalid_entry_price"}

        # Apply default SL if missing
        if sl <= 0:
            if SKIP_NO_SL:
                return {"success": False, "reason": "no_stop_loss"}
            sl = entry * (1 - DEFAULT_SL_PCT / 100) if direction == "LONG" else entry * (1 + DEFAULT_SL_PCT / 100)
            logger.info(f"ℹ️  No SL in signal — using default SL: {sl:.6g}")

        # Check if API authentication previously failed — avoid repeated failures
        if getattr(self, "_api_auth_failed", False):
            return {"success": False, "reason": "api_key_missing_futures_permission"}

        # Check if we already have this position
        trade_key = f"{symbol}_{direction}"
        if trade_key in self._trades and not self._trades[trade_key].closed:
            logger.info(f"⏭️  Already have active {direction} on {symbol} — skipping")
            return {"success": False, "reason": "position_already_open"}

        try:
            # ── Setup margin + leverage ──
            await self._set_margin_type(symbol, leverage)

            # ── Get balance ──
            balance = await self._get_usdt_balance()
            if balance < MIN_NOTIONAL:
                return {"success": False, "reason": f"insufficient_balance_{balance:.2f}"}

            # ── Calculate quantity ──
            qty = self._calc_quantity(entry, sl, leverage, balance)
            qty = self._round_quantity(symbol, qty)
            if qty <= 0:
                return {"success": False, "reason": "quantity_zero"}

            notional = qty * entry
            logger.info(
                f"📊 {symbol} {direction} | qty={qty} entry≈{entry:.6g} "
                f"notional≈{notional:.2f} USDT | lev={leverage}x | "
                f"SL={sl:.6g} TP1={tp1:.6g} TP2={tp2:.6g} TP3={tp3:.6g}"
            )

            # ── Open position ──
            ccxt_sym = self._to_ccxt_symbol(symbol)
            order_side = "buy" if direction == "LONG" else "sell"
            position_side = "LONG" if direction == "LONG" else "SHORT"  # hedge mode

            order = await self._retry(
                self.exchange.create_order,
                ccxt_sym,
                "market",
                order_side,
                qty,
                None,
                {
                    "positionSide": position_side,
                    "reduceOnly": False,
                }
            )
            actual_entry = float(order.get("average") or order.get("price") or entry)
            logger.info(f"✅ Position opened: {symbol} {direction} @ {actual_entry:.6g}")
            self._reset_error_count()

            # ── Record trade ──
            trade = TradeRecord(
                symbol=symbol,
                direction=direction,
                side=order_side,
                entry_price=actual_entry,
                quantity=qty,
                leverage=leverage,
                stop_loss=sl,
                take_profit_1=tp1,
                take_profit_2=tp2,
                take_profit_3=tp3,
            )
            self._trades[trade_key] = trade

            # ── Place stop-loss order (market) ──
            sl_order = await self._place_stop_loss(trade)
            if sl_order:
                trade.sl_order_id = sl_order.get("id")

            # ── Place TP orders (limit) ──
            await self._place_take_profits(trade)

            # ── Initialize moving target trailing stop (inactive until TP1) ──
            self._trailing[trade_key] = MovingTargetTrailingStop(trade, tp1)

            return {
                "success":    True,
                "symbol":     symbol,
                "direction":  direction,
                "entry":      actual_entry,
                "quantity":   qty,
                "leverage":   leverage,
                "stop_loss":  sl,
                "take_profit_1": tp1,
                "take_profit_2": tp2,
                "take_profit_3": tp3,
                "notional":   notional,
                "risk_usdt":  balance * RISK_PERCENT / 100,
                "order_id":   order.get("id"),
            }

        except ccxt.InsufficientFunds as e:
            logger.error(f"❌ Insufficient funds for {symbol}: {e}")
            return {"success": False, "reason": "insufficient_funds"}
        except ccxt.InvalidOrder as e:
            logger.error(f"❌ Invalid order for {symbol}: {e}")
            self._increment_error()
            return {"success": False, "reason": f"invalid_order: {e}"}
        except ccxt.NetworkError as e:
            logger.error(f"❌ Network error for {symbol}: {e}")
            self._increment_error()
            return {"success": False, "reason": f"network_error: {e}"}
        except ccxt.AuthenticationError as e:
            self._api_auth_failed = True
            logger.error(
                f"🔑 API authentication failed — direct trading PAUSED.\n"
                f"   ACTION REQUIRED: Enable 'Enable Futures' permission at\n"
                f"   https://www.binance.com/en/my/settings/api-management"
            )
            return {"success": False, "reason": "api_authentication_failed_enable_futures"}
        except Exception as e:
            err_str = str(e)
            if "-2015" in err_str or "-2014" in err_str:
                self._api_auth_failed = True
                logger.error(
                    f"🔑 Binance error -2015: Invalid API key or missing futures permission.\n"
                    f"   ACTION: In Binance API settings, enable 'Enable Futures' for this key.\n"
                    f"   https://www.binance.com/en/my/settings/api-management"
                )
                return {"success": False, "reason": "api_key_missing_futures_permission"}
            logger.error(f"❌ Unexpected error executing {symbol}: {e}", exc_info=True)
            self._increment_error()
            return {"success": False, "reason": str(e)}

    # ─────────────────────────────────────────
    # Order Placement
    # ─────────────────────────────────────────

    async def _place_stop_loss(self, trade: TradeRecord) -> Optional[Dict]:
        """Place a STOP_MARKET stop-loss order (market type = faster fill)."""
        try:
            ccxt_sym  = self._to_ccxt_symbol(trade.symbol)
            stop_side = "sell" if trade.direction == "LONG" else "buy"
            pos_side  = "LONG" if trade.direction == "LONG" else "SHORT"
            sl_price  = self._round_price(trade.symbol, trade.stop_loss)

            order = await self._retry(
                self.exchange.create_order,
                ccxt_sym,
                "stop_market",
                stop_side,
                trade.quantity,
                None,
                {
                    "stopPrice":    sl_price,
                    "positionSide": pos_side,
                    "reduceOnly":   True,
                    "closePosition": False,
                }
            )
            logger.info(f"🛡️ Stop-Market SL set @ {sl_price:.6g} for {trade.symbol} {trade.direction}")
            return order
        except Exception as e:
            logger.warning(f"⚠️ SL order failed for {trade.symbol}: {e}")
            return None

    async def _place_take_profits(self, trade: TradeRecord):
        """Place TP1 (50%), TP2 (30%), TP3 (20%) limit orders."""
        if not trade.take_profit_1:
            return
        ccxt_sym  = self._to_ccxt_symbol(trade.symbol)
        tp_side   = "sell" if trade.direction == "LONG" else "buy"
        pos_side  = "LONG" if trade.direction == "LONG" else "SHORT"

        # TP allocation: 50/30/20 of position
        allocs = [
            (trade.take_profit_1, 0.50, "tp1"),
            (trade.take_profit_2, 0.30, "tp2") if trade.take_profit_2 else None,
            (trade.take_profit_3, 0.20, "tp3") if trade.take_profit_3 else None,
        ]
        allocs = [a for a in allocs if a is not None]

        remaining_qty = trade.quantity
        for i, (tp_price, alloc_pct, label) in enumerate(allocs):
            if tp_price <= 0:
                continue
            is_last = (i == len(allocs) - 1)
            qty = trade.quantity * alloc_pct if not is_last else remaining_qty
            qty = self._round_quantity(trade.symbol, qty)
            if qty <= 0:
                continue
            tp_price_r = self._round_price(trade.symbol, tp_price)
            try:
                order = await self._retry(
                    self.exchange.create_order,
                    ccxt_sym,
                    "limit",
                    tp_side,
                    qty,
                    tp_price_r,
                    {
                        "positionSide": pos_side,
                        "reduceOnly":   True,
                        "timeInForce":  "GTC",
                    }
                )
                oid = order.get("id")
                if label == "tp1":
                    trade.tp1_order_id = oid
                elif label == "tp2":
                    trade.tp2_order_id = oid
                elif label == "tp3":
                    trade.tp3_order_id = oid
                remaining_qty -= qty
                logger.info(f"🎯 {label.upper()} @ {tp_price_r:.6g} qty={qty} for {trade.symbol} {trade.direction}")
            except Exception as e:
                logger.warning(f"⚠️ {label.upper()} order failed for {trade.symbol}: {e}")

    # ─────────────────────────────────────────
    # Position Monitor (Moving Target Trailing)
    # ─────────────────────────────────────────

    async def _position_monitor_loop(self):
        """
        Background loop: monitor open positions for TP hits and update
        the Moving Target trailing stop.
        Runs every 15 seconds.
        """
        logger.info("🔍 Position monitor loop started")
        while self._running:
            try:
                await asyncio.sleep(15)
                if not self._trades:
                    continue
                await self._check_positions_and_trail()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"⚠️ Monitor loop error: {e}")
                await asyncio.sleep(30)
        logger.info("🔍 Position monitor loop stopped")

    async def _check_positions_and_trail(self):
        """Check all active positions and update trailing stops."""
        if not self.exchange:
            return
        try:
            positions = await self._retry(
                self.exchange.fetch_positions,
                None,
                {"type": "future"}
            )
        except Exception as e:
            logger.warning(f"⚠️ Position fetch failed: {e}")
            return

        # Build lookup: (symbol, positionSide) → position
        pos_lookup: Dict[Tuple[str, str], Dict] = {}
        for p in positions:
            sym  = p.get("symbol", "").replace("/", "").replace(":USDT", "")
            side = p.get("side", "")  # 'long' or 'short'
            qty  = float(p.get("contracts", 0) or 0)
            if qty > 0:
                pos_lookup[(sym, side.upper())] = p

        for trade_key, trade in list(self._trades.items()):
            if trade.closed:
                continue

            # Check if position is still open
            p_side  = trade.direction  # "LONG" or "SHORT"
            p_info  = pos_lookup.get((trade.symbol, p_side))
            if p_info is None or float(p_info.get("contracts", 0) or 0) == 0:
                trade.closed = True
                logger.info(f"✅ Position closed: {trade.symbol} {trade.direction}")
                continue

            # Current price
            current_price = float(p_info.get("markPrice") or p_info.get("lastPrice") or 0)
            if current_price <= 0:
                continue

            trailing = self._trailing.get(trade_key)
            if trailing is None:
                continue

            # Activate trailing if TP1 has been surpassed
            if not trailing.active and not trade.tp1_hit:
                if (trade.direction == "LONG"  and current_price >= trade.take_profit_1) or \
                   (trade.direction == "SHORT" and current_price <= trade.take_profit_1):
                    trade.tp1_hit = True
                    trailing.activate(current_price)
                    logger.info(
                        f"🎯 TP1 HIT → Trailing activated | "
                        f"{trade.symbol} {trade.direction} @ {current_price:.6g}"
                    )

            # Update trailing stop price
            if trailing.active:
                new_sl = trailing.update(current_price)
                if new_sl is not None:
                    await self._update_stop_loss(trade, new_sl)

    async def _update_stop_loss(self, trade: TradeRecord, new_sl: float):
        """Cancel existing SL order and place new one at new_sl."""
        try:
            # Cancel old SL
            if trade.sl_order_id:
                ccxt_sym = self._to_ccxt_symbol(trade.symbol)
                try:
                    await self._retry(
                        self.exchange.cancel_order,
                        trade.sl_order_id, ccxt_sym
                    )
                except Exception:
                    pass
                trade.sl_order_id = None

            # Place new SL
            trade.stop_loss = new_sl
            sl_order = await self._place_stop_loss(trade)
            if sl_order:
                trade.sl_order_id = sl_order.get("id")
            logger.info(
                f"🔼 Trailing SL updated → {new_sl:.6g} "
                f"for {trade.symbol} {trade.direction}"
            )
        except Exception as e:
            logger.warning(f"⚠️ SL update failed for {trade.symbol}: {e}")

    # ─────────────────────────────────────────
    # Retry / Circuit Breaker
    # ─────────────────────────────────────────

    async def _retry(self, fn, *args, **kwargs) -> Any:
        """Retry an async ccxt call with exponential backoff."""
        last_exc = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                if asyncio.iscoroutinefunction(fn):
                    return await fn(*args, **kwargs)
                else:
                    return fn(*args, **kwargs)
            except ccxt.RateLimitExceeded as e:
                wait = RETRY_DELAY_BASE * (2 ** attempt)
                logger.warning(f"⏳ Rate limit — waiting {wait:.1f}s (attempt {attempt})")
                await asyncio.sleep(wait)
                last_exc = e
            except (ccxt.NetworkError, ccxt.RequestTimeout) as e:
                wait = RETRY_DELAY_BASE * attempt
                logger.warning(f"🌐 Network error (attempt {attempt}/{MAX_RETRIES}): {e}")
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(wait)
                last_exc = e
            except ccxt.AuthenticationError as e:
                logger.error(f"🔑 Authentication error — check API keys: {e}")
                raise
            except ccxt.ExchangeNotAvailable as e:
                wait = RETRY_DELAY_BASE * (2 ** attempt)
                logger.warning(f"🔴 Exchange unavailable — waiting {wait:.1f}s: {e}")
                await asyncio.sleep(wait)
                last_exc = e
            except Exception as e:
                raise
        raise last_exc or RuntimeError("Max retries exceeded")

    def _circuit_breaker_active(self) -> bool:
        if self._consecutive_errors >= self._cb_threshold:
            if time.time() < self._cb_tripped_until:
                remaining = self._cb_tripped_until - time.time()
                logger.warning(f"🔴 Circuit breaker active — {remaining:.0f}s remaining")
                return True
            else:
                self._consecutive_errors = 0
                logger.info("🟢 Circuit breaker reset")
        return False

    def _increment_error(self):
        self._consecutive_errors += 1
        if self._consecutive_errors >= self._cb_threshold:
            self._cb_tripped_until = time.time() + self._cb_cooldown
            logger.error(f"🔴 Circuit breaker TRIPPED after {self._consecutive_errors} errors")

    def _reset_error_count(self):
        self._consecutive_errors = 0

    # ─────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────

    def _to_ccxt_symbol(self, symbol: str) -> str:
        """Convert BTCUSDT → BTC/USDT:USDT (CCXT perp format)."""
        symbol = symbol.upper().replace("/", "")
        if symbol.endswith("USDT"):
            base = symbol[:-4]
            return f"{base}/USDT:USDT"
        return symbol

    # ─────────────────────────────────────────
    # Status
    # ─────────────────────────────────────────

    def get_active_trades(self) -> List[Dict[str, Any]]:
        """Return list of active trade summaries."""
        result = []
        for k, t in self._trades.items():
            if not t.closed:
                trailing = self._trailing.get(k)
                result.append({
                    "symbol":          t.symbol,
                    "direction":       t.direction,
                    "entry":           t.entry_price,
                    "quantity":        t.quantity,
                    "leverage":        t.leverage,
                    "stop_loss":       t.stop_loss,
                    "take_profit_1":   t.take_profit_1,
                    "tp1_hit":         t.tp1_hit,
                    "trailing_active": trailing.active if trailing else False,
                    "opened_at":       t.opened_at.isoformat(),
                })
        return result

    def status_summary(self) -> str:
        """Human-readable status for Telegram commands."""
        trades = self.get_active_trades()
        if not trades:
            return "📊 No active direct trades"
        lines = [f"📊 Active Direct Trades ({len(trades)}):"]
        for t in trades:
            trail = "🎯 trailing" if t["trailing_active"] else ("✅TP1 hit" if t["tp1_hit"] else "⏳ waiting")
            lines.append(
                f"  {t['symbol']} {t['direction']} | entry={t['entry']:.4g} "
                f"SL={t['stop_loss']:.4g} | lev={t['leverage']}x | {trail}"
            )
        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Singleton accessor
# ─────────────────────────────────────────────────────────────────────────────

_executor_instance: Optional[BinanceDirectExecutor] = None


def get_direct_executor() -> BinanceDirectExecutor:
    global _executor_instance
    if _executor_instance is None:
        _executor_instance = BinanceDirectExecutor()
    return _executor_instance

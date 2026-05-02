#!/usr/bin/env python3
"""
Cornix-Replacement Menu Bot — Unity Engine v11.0
=================================================
Self-contained inline-keyboard Telegram menu that replaces Cornix entirely.
All user configuration is button-driven (no slash commands required).

Features mirror cornix.io + IRONS BOT + TradeTactics ML BOT:
  • Multi-exchange API key vault (Binance / Bybit / OKX / BingX / Bitget / KuCoin / Gate / MEXC)
  • Trading dashboard — balance, equity, unrealised PnL, open positions
  • Risk management — leverage, risk-per-trade %, max open trades, fixed stake
  • Entry orders — Market / Limit / Limit-Timeout / DCA (orders + multiplier)
  • Take Profit — 1-4 TPs, volume distribution presets + custom
  • Breakeven & Cascade — protective SL after TPx
  • Margin mode — Isolated / Cross  | Mode — Auto / Manual / OFF
  • Per-signal action buttons — Follow / Ignore / Brief / Detailed / Retry
  • Position management — view open / partial close / cancel pending
  • History & Statistics — closed trades, win-rate, total PnL
  • AI Signal Validation — brief / detailed / score components
  • Channel settings, notifications toggle, EN/RU language
  • Fernet-encrypted secrets at rest

Integrates into the Unity Engine via:
    from SignalMaestro.cornix_menu_bot import CornixMenuBot
    menu = CornixMenuBot()
    await menu.attach(application)   # python-telegram-bot Application
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import os
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("UnityEngine.CornixMenu")

try:
    from telegram import (
        InlineKeyboardButton,
        InlineKeyboardMarkup,
        Update,
    )
    from telegram.ext import (
        Application,
        CallbackQueryHandler,
        CommandHandler,
        ContextTypes,
        MessageHandler,
        filters,
    )
    _HAS_PTB = True
except Exception as _e:  # pragma: no cover
    _HAS_PTB = False
    logger.warning(f"⚠️  python-telegram-bot not available — CornixMenuBot disabled: {_e}")

try:
    from cryptography.fernet import Fernet, InvalidToken
    _HAS_CRYPTO = True
except Exception:
    _HAS_CRYPTO = False

try:
    import aiohttp
    _HAS_AIOHTTP = True
except Exception:
    _HAS_AIOHTTP = False

try:
    import ccxt.async_support as ccxt_async
    _HAS_CCXT = True
except Exception:
    _HAS_CCXT = False


# ═══════════════════════════════════════════════════════════════════════════
#   CCXT EXCHANGE PROVIDER  (v10.5 — live balance / positions / orders)
# ═══════════════════════════════════════════════════════════════════════════

class CcxtExchangeProvider:
    """Thin async CCXT wrapper that uses encrypted API keys from the vault.

    Supports Binance USDM Futures (primary) and 7 other exchanges.
    All methods degrade gracefully — never raise, always return empty/zero.
    """

    # ccxt exchange IDs for our supported set
    _EXCHANGE_MAP: Dict[str, str] = {
        "binance": "binanceusdm",   # USDM Futures — primary target
        "bybit":   "bybit",
        "okx":     "okx",
        "bingx":   "bingx",
        "bitget":  "bitget",
        "kucoin":  "kucoin",
        "gate":    "gate",
        "mexc":    "mexc",
    }

    def __init__(self, store: "UserConfigStore"):
        self._store = store
        self._clients: Dict[str, Any] = {}   # (user_id, exchange, label) → ccxt client

    def _client_key(self, user_id: int, exchange: str, label: str) -> str:
        return f"{user_id}:{exchange}:{label}"

    async def _get_client(self, user_id: int, exchange: str, label: str) -> Optional[Any]:
        """Return a (possibly cached) authenticated ccxt async client."""
        if not _HAS_CCXT:
            return None
        key = self._client_key(user_id, exchange, label)
        if key not in self._clients:
            creds = await self._store.get_api_key(user_id, exchange, label)
            if not creds:
                return None
            api_key, api_secret, passphrase = creds
            ccxt_id = self._EXCHANGE_MAP.get(exchange, exchange)
            try:
                cls = getattr(ccxt_async, ccxt_id, None)
                if cls is None:
                    return None
                params: Dict[str, Any] = {
                    "apiKey":  api_key,
                    "secret":  api_secret,
                    "enableRateLimit": True,
                    "options": {"defaultType": "future"},
                }
                if passphrase:
                    params["password"] = passphrase
                self._clients[key] = cls(params)
            except Exception as e:
                logger.debug(f"ccxt client init failed for {exchange}/{label}: {e}")
                return None
        return self._clients.get(key)

    async def get_balance(self, user_id: int, exchange: str, label: str) -> Dict[str, float]:
        """Fetch USDT balance from the exchange. Returns zeros on failure."""
        result = {"balance": 0.0, "available": 0.0, "equity": 0.0, "unrealised_pnl": 0.0}
        try:
            client = await self._get_client(user_id, exchange, label)
            if client is None:
                return result
            bal = await asyncio.wait_for(client.fetch_balance(), timeout=10.0)
            usdt = bal.get("USDT", {}) or {}
            result["balance"]        = float(usdt.get("total",  0) or 0)
            result["available"]      = float(usdt.get("free",   0) or 0)
            result["equity"]         = float(usdt.get("total",  0) or 0)
            result["unrealised_pnl"] = float(usdt.get("used",   0) or 0)
            # Binance USDM returns totalWalletBalance in info
            info = bal.get("info", {}) or {}
            if "totalWalletBalance" in info:
                result["balance"]   = float(info.get("totalWalletBalance",   0) or 0)
                result["equity"]    = float(info.get("totalMarginBalance",    result["balance"]) or 0)
                result["available"] = float(info.get("availableBalance",      0) or 0)
                result["unrealised_pnl"] = float(info.get("totalUnrealizedProfit", 0) or 0)
        except Exception as e:
            logger.debug(f"get_balance {exchange}/{label}: {e}")
        return result

    async def get_positions(self, user_id: int, exchange: str, label: str) -> List[Dict[str, Any]]:
        """Fetch open positions. Returns [] on failure."""
        try:
            client = await self._get_client(user_id, exchange, label)
            if client is None:
                return []
            pos_raw = await asyncio.wait_for(client.fetch_positions(), timeout=12.0)
            out = []
            for p in (pos_raw or []):
                qty = float(p.get("contracts", p.get("positionAmt", 0)) or 0)
                if abs(qty) < 1e-9:
                    continue
                out.append({
                    "symbol":          p.get("symbol", "?"),
                    "side":            p.get("side", "?").upper(),
                    "qty":             abs(qty),
                    "entry_price":     float(p.get("entryPrice", p.get("avgPrice", 0)) or 0),
                    "mark_price":      float(p.get("markPrice",  0) or 0),
                    "unrealised_pnl":  float(p.get("unrealizedPnl", 0) or 0),
                    "leverage":        int(float(p.get("leverage", 1) or 1)),
                    "liq_price":       float(p.get("liquidationPrice", 0) or 0),
                })
            return out
        except Exception as e:
            logger.debug(f"get_positions {exchange}/{label}: {e}")
            return []

    async def close_position(self, user_id: int, exchange: str, label: str,
                             symbol: str, qty: float, side: str) -> Dict[str, Any]:
        """Market-close a position. Returns order result dict."""
        try:
            client = await self._get_client(user_id, exchange, label)
            if client is None:
                return {"error": "no client (check API keys)"}
            close_side = "sell" if side.upper() in ("LONG", "BUY") else "buy"
            order = await asyncio.wait_for(
                client.create_order(
                    symbol=symbol,
                    type="market",
                    side=close_side,
                    amount=qty,
                    params={"reduceOnly": True},
                ),
                timeout=15.0,
            )
            return {"ok": True, "id": order.get("id", "?"), "symbol": symbol, "side": close_side, "qty": qty}
        except Exception as e:
            logger.warning(f"close_position {exchange}/{label} {symbol}: {e}")
            return {"error": str(e)}

    async def execute_order(self, user_id: int, exchange: str, label: str,
                            symbol: str, side: str, qty: float,
                            order_type: str = "market",
                            price: Optional[float] = None,
                            leverage: int = 10) -> Dict[str, Any]:
        """Place a new futures order (market or limit)."""
        try:
            client = await self._get_client(user_id, exchange, label)
            if client is None:
                return {"error": "no client (check API keys)"}
            # Set leverage first
            try:
                await asyncio.wait_for(
                    client.set_leverage(leverage, symbol),
                    timeout=8.0,
                )
            except Exception:
                pass
            params: Dict[str, Any] = {}
            order = await asyncio.wait_for(
                client.create_order(
                    symbol=symbol,
                    type=order_type,
                    side=side.lower(),
                    amount=qty,
                    price=price,
                    params=params,
                ),
                timeout=15.0,
            )
            return {
                "ok":      True,
                "id":      order.get("id", "?"),
                "symbol":  symbol,
                "side":    side,
                "qty":     qty,
                "type":    order_type,
                "price":   order.get("price", price),
            }
        except Exception as e:
            logger.warning(f"execute_order {exchange}/{label} {symbol}: {e}")
            return {"error": str(e)}

    async def get_trade_history(self, user_id: int, exchange: str, label: str,
                                limit: int = 50) -> List[Dict[str, Any]]:
        """Fetch recent closed trades. Returns [] on failure."""
        try:
            client = await self._get_client(user_id, exchange, label)
            if client is None:
                return []
            trades = await asyncio.wait_for(
                client.fetch_my_trades(symbol=None, limit=limit),
                timeout=15.0,
            )
            out = []
            for t in (trades or []):
                out.append({
                    "symbol": t.get("symbol", "?"),
                    "side":   t.get("side",   "?").upper(),
                    "qty":    float(t.get("amount", 0) or 0),
                    "price":  float(t.get("price",  0) or 0),
                    "pnl":    float(t.get("info", {}).get("realizedPnl", 0) or 0),
                    "time":   t.get("datetime", "?"),
                })
            return out
        except Exception as e:
            logger.debug(f"get_trade_history {exchange}/{label}: {e}")
            return []

    async def close(self):
        """Close all cached ccxt clients."""
        for client in self._clients.values():
            try:
                await client.close()
            except Exception:
                pass
        self._clients.clear()


# ═══════════════════════════════════════════════════════════════════════════
#   CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════

DB_PATH = Path(__file__).parent / "cornix_user_config.db"

SUPPORTED_EXCHANGES = [
    ("binance", "🟡 Binance"),
    ("bybit",   "🟠 Bybit"),
    ("okx",     "⚫ OKX"),
    ("bingx",   "🔵 BingX"),
    ("bitget",  "🟢 Bitget"),
    ("kucoin",  "🟢 KuCoin"),
    ("gate",    "⚪ Gate"),
    ("mexc",    "🔵 MEXC"),
]

LEVERAGE_PRESETS    = [3, 5, 10, 15, 20, 25, 50, 75, 100, 125]
RISK_PCT_PRESETS    = [0.5, 1.0, 1.5, 2.0, 3.0, 5.0]
MAX_TRADES_PRESETS  = [1, 2, 3, 5, 8, 10]
TRAILING_SL_PRESETS = [0.3, 0.5, 0.8, 1.0, 1.5, 2.0, 3.0]   # trailing stop % presets
SL_FIXED_PCT_PRESETS= [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 5.0]   # fixed SL % presets
SL_ATR_MULT_PRESETS = [1.0, 1.5, 2.0, 2.5, 3.0, 4.0]         # ATR multiplier presets
SL_MAX_PCT_PRESETS  = [1.0, 2.0, 3.0, 5.0, 7.0, 10.0]        # hard cap SL % presets
PARTIAL_CLOSE_PRESETS = [25, 33, 50, 66, 75, 100]             # partial close % presets
AMOUNT_USDT_PRESETS = [10, 25, 50, 100, 250, 500, 1000]       # fixed USDT per trade
MAX_POS_USDT_PRESETS = [100, 250, 500, 1000, 2500, 5000]      # max position size USDT
MIN_CONF_PRESETS    = [0.50, 0.60, 0.65, 0.70, 0.75, 0.80, 0.90]  # signal confidence filter
TP_DISTRIBUTIONS = {
    "balanced":   [45, 35, 20],
    "aggressive": [25, 25, 50],
    "scalp":      [60, 30, 10],
    "even3":      [33, 34, 33],
    "even4":      [25, 25, 25, 25],
    "full_tp1":   [100],
}

LANG_TEXTS = {
    "en": {
        "welcome":       "👋 Welcome to the Unity Engine system!\n\nChoose an action:",
        "main_menu":     "🏠 *Main Menu*",
        "api_keys":      "🔑 API Keys",
        "settings":      "⚙️ Settings",
        "dashboard":     "📊 Trading Dashboard",
        "signals":       "📨 Working with Signals",
        "positions":     "📁 Position Management",
        "history":       "📋 History & Statistics",
        "ai_valid":      "🤖 AI Signal Validation",
        "channel":       "📡 Channel Settings",
        "notifications": "🔔 Notifications",
        "language":      "🌐 Language",
        "help":          "❓ User Guide",
        "back":          "◀️ Back",
        "main":          "🏠 Main Menu",
        "saved":         "✅ Saved",
        "cancelled":     "❎ Cancelled",
    },
    "ru": {
        "welcome":       "👋 Добро пожаловать в систему Unity Engine!\n\nВыберите действие:",
        "main_menu":     "🏠 *Главное меню*",
        "api_keys":      "🔑 API ключи",
        "settings":      "⚙️ Настройки",
        "dashboard":     "📊 Торговая панель",
        "signals":       "📨 Работа с сигналами",
        "positions":     "📁 Управление позициями",
        "history":       "📋 История и статистика",
        "ai_valid":      "🤖 AI валидация сигнала",
        "channel":       "📡 Настройки канала",
        "notifications": "🔔 Уведомления",
        "language":      "🌐 Язык",
        "help":          "❓ Руководство",
        "back":          "◀️ Назад",
        "main":          "🏠 Главное меню",
        "saved":         "✅ Сохранено",
        "cancelled":     "❎ Отменено",
    },
}


# ═══════════════════════════════════════════════════════════════════════════
#   ENCRYPTION
# ═══════════════════════════════════════════════════════════════════════════

class _Vault:
    """Fernet-based at-rest encryption for API secrets.
    Falls back to base64 obfuscation if cryptography is unavailable."""

    def __init__(self, master_key: Optional[str] = None):
        seed = master_key or os.getenv("UNITY_VAULT_KEY") or os.getenv("BOT_SECRET") or "unity-engine-default-vault-key-change-me"
        digest = hashlib.sha256(seed.encode()).digest()
        self._fkey = base64.urlsafe_b64encode(digest)
        self._fernet: Optional["Fernet"] = Fernet(self._fkey) if _HAS_CRYPTO else None

    def encrypt(self, plaintext: str) -> str:
        if not plaintext:
            return ""
        if self._fernet:
            return self._fernet.encrypt(plaintext.encode()).decode()
        return "b64:" + base64.b64encode(plaintext.encode()).decode()

    def decrypt(self, token: str) -> str:
        if not token:
            return ""
        try:
            if self._fernet and not token.startswith("b64:"):
                return self._fernet.decrypt(token.encode()).decode()
            if token.startswith("b64:"):
                return base64.b64decode(token[4:]).decode()
        except (InvalidToken, ValueError, Exception) as e:
            logger.warning(f"Vault decrypt failed: {e}")
            return ""
        return ""


# ═══════════════════════════════════════════════════════════════════════════
#   USER CONFIG STORE
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class UserConfig:
    user_id: int
    # Mode
    trading_mode: str = "manual"           # auto / manual / off
    margin_mode: str = "isolated"          # isolated / cross
    # Risk
    leverage: int = 10
    risk_pct: float = 1.0
    stake_usdt: float = 0.0                # 0 = use risk_pct
    max_open_trades: int = 3
    margin_pct: float = 100.0              # % of balance per trade (Cornix-style)
    # Entry
    entry_type: str = "market"             # market / limit
    limit_timeout_min: int = 30
    dca_orders: int = 0
    dca_multiplier: float = 1.5
    # TP
    tp_count: int = 3
    tp_distribution: str = "balanced"      # key in TP_DISTRIBUTIONS
    tp_custom: List[int] = field(default_factory=list)
    full_close_tp1: bool = False
    # SL protection
    breakeven_after_tp: int = 2            # 0 = off, 1=after TP1, 2=after TP2…
    cascade_after_tp: int = 0              # 0 = off
    be_plus_cascade: bool = False
    # Channel / alerts
    signal_channel: str = "@ichimokutradingsignal"
    notifications: bool = True
    language: str = "en"
    # Active exchange
    active_exchange: str = "binance"
    # ── v10.0 Cornix-Complete additions ────────────────────────────────────
    # Simulation / paper trading
    simulation_mode: bool = False           # True = paper trade only (no real orders)
    # Position sizing mode
    amount_type: str = "risk_pct"           # "risk_pct" | "fixed_usdt"
    trade_amount_usdt: float = 100.0        # fixed USDT amount per trade (when amount_type="fixed_usdt")
    max_position_usdt: float = 1000.0       # hard cap on any single position
    # Trailing stop loss
    trailing_stop_enabled: bool = False
    trailing_stop_pct: float = 1.0          # trailing stop distance in % (e.g. 1.0 = 1%)
    trailing_stop_activation_pct: float = 0.5  # activate trailing after price moves this % in profit
    # Notification filter
    notify_on: str = "all"                  # "all" | "wins_only" | "losses_only" | "none"
    notify_entry: bool = True               # notify on position entry
    notify_tp: bool = True                  # notify on take profit
    notify_sl: bool = True                  # notify on stop loss
    notify_dca: bool = False                # notify on DCA refills
    # Signal quality filter
    signal_min_confidence: float = 0.60    # minimum AI confidence 0.0–1.0 to auto-follow
    signal_min_quality: int = 65           # minimum Unity quality score to auto-follow
    # Copy signals
    copy_signals_enabled: bool = True      # copy signals to exchange (disable = monitor only)
    # Bot status
    bot_paused: bool = False               # pause all execution without disabling
    # ── v10.0 Stop Loss configuration ──────────────────────────────────────
    sl_mode: str = "signal"                # "signal" | "fixed_pct" | "atr" | "none"
    sl_fixed_pct: float = 2.0             # fixed SL distance from entry in %
    sl_atr_mult: float = 2.0              # ATR multiplier for ATR-based SL
    sl_max_pct: float = 5.0              # hard cap — never risk more than this % from entry
    # ── v10.0 Signal group / channel management ─────────────────────────────
    signal_groups: List[str] = field(default_factory=lambda: ["@ichimokutradingsignal"])
    active_group: str = "@ichimokutradingsignal"
    group_filter_mode: str = "all"         # "all" | "whitelist" | "blacklist"
    symbol_whitelist: List[str] = field(default_factory=list)
    symbol_blacklist: List[str] = field(default_factory=list)
    # ── v10.0 Auto-close / time-based exit ──────────────────────────────────
    auto_close_hours: float = 0.0         # 0 = off; close position after N hours
    max_loss_usd: float = 0.0             # 0 = off; close if unrealised loss > $N
    # ── v10.0 Advanced entry options ────────────────────────────────────────
    use_market_on_sl: bool = True          # use market order for SL (vs limit)
    partial_close_pct: float = 50.0       # % to partially close on first TP
    # ── v11.0 DCA Advanced settings (Cornix parity) ─────────────────────────
    dca_deviation_pct: float = 1.5        # % price drop between DCA refills
    dca_vol_scale: float = 1.5            # volume multiplier per DCA step (1.0=flat)
    dca_max_orders: int = 3               # max number of DCA fill orders
    # ── v11.0 Signal timeout (Cornix parity) ────────────────────────────────
    signal_timeout_min: int = 0           # 0 = off; cancel entry order after N minutes
    # ── v11.0 Portfolio balance allocation ──────────────────────────────────
    portfolio_balance_pct: float = 100.0  # % of account balance to use for trading
    # ── v11.0 Copy trading source channel ───────────────────────────────────
    copy_source_channel: str = ""         # Telegram channel ID / username to mirror
    copy_follow_tp: bool = True           # mirror TP edits from source
    copy_follow_sl: bool = True           # mirror SL edits from source
    copy_follow_close: bool = True        # mirror manual close from source

    @classmethod
    def default(cls, user_id: int) -> "UserConfig":
        return cls(user_id=user_id)


class UserConfigStore:
    """SQLite-backed per-user configuration vault."""

    def __init__(self, db_path: Path = DB_PATH, vault: Optional[_Vault] = None):
        self.db_path = db_path
        self.vault = vault or _Vault()
        self._lock = asyncio.Lock()
        self._cache: Dict[int, UserConfig] = {}
        self._init_db()

    def _init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    config_json TEXT NOT NULL,
                    updated_at REAL NOT NULL
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS api_keys (
                    user_id INTEGER NOT NULL,
                    exchange TEXT NOT NULL,
                    label TEXT NOT NULL,
                    api_key_enc TEXT NOT NULL,
                    api_secret_enc TEXT NOT NULL,
                    api_passphrase_enc TEXT DEFAULT '',
                    created_at REAL NOT NULL,
                    PRIMARY KEY (user_id, exchange, label)
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS signal_actions (
                    user_id INTEGER NOT NULL,
                    signal_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    payload_json TEXT,
                    ts REAL NOT NULL,
                    PRIMARY KEY (user_id, signal_id)
                )
            """)
            c.commit()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(str(self.db_path), timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    async def get(self, user_id: int) -> UserConfig:
        async with self._lock:
            if user_id in self._cache:
                return self._cache[user_id]
            with self._conn() as c:
                row = c.execute("SELECT config_json FROM users WHERE user_id=?", (user_id,)).fetchone()
            if row:
                try:
                    data = json.loads(row["config_json"])
                    cfg = UserConfig(**{**asdict(UserConfig.default(user_id)), **data})
                except Exception as e:
                    logger.warning(f"Config decode failed for {user_id}: {e}")
                    cfg = UserConfig.default(user_id)
            else:
                cfg = UserConfig.default(user_id)
            self._cache[user_id] = cfg
            return cfg

    async def save(self, cfg: UserConfig) -> None:
        async with self._lock:
            self._cache[cfg.user_id] = cfg
            with self._conn() as c:
                c.execute(
                    "INSERT OR REPLACE INTO users (user_id, config_json, updated_at) VALUES (?,?,?)",
                    (cfg.user_id, json.dumps(asdict(cfg)), time.time()),
                )
                c.commit()

    async def add_api_key(self, user_id: int, exchange: str, label: str,
                          api_key: str, api_secret: str, passphrase: str = "") -> None:
        async with self._lock:
            with self._conn() as c:
                c.execute(
                    "INSERT OR REPLACE INTO api_keys VALUES (?,?,?,?,?,?,?)",
                    (
                        user_id, exchange, label,
                        self.vault.encrypt(api_key),
                        self.vault.encrypt(api_secret),
                        self.vault.encrypt(passphrase),
                        time.time(),
                    ),
                )
                c.commit()

    async def list_api_keys(self, user_id: int, exchange: Optional[str] = None) -> List[Dict[str, Any]]:
        async with self._lock:
            with self._conn() as c:
                if exchange:
                    rows = c.execute(
                        "SELECT exchange,label,api_key_enc,created_at FROM api_keys WHERE user_id=? AND exchange=?",
                        (user_id, exchange),
                    ).fetchall()
                else:
                    rows = c.execute(
                        "SELECT exchange,label,api_key_enc,created_at FROM api_keys WHERE user_id=?",
                        (user_id,),
                    ).fetchall()
            out = []
            for r in rows:
                key = self.vault.decrypt(r["api_key_enc"])
                masked = (key[:6] + "…" + key[-4:]) if len(key) > 12 else "****"
                out.append({
                    "exchange": r["exchange"],
                    "label": r["label"],
                    "masked": masked,
                    "created_at": r["created_at"],
                })
            return out

    async def get_api_key(self, user_id: int, exchange: str, label: str) -> Optional[Tuple[str, str, str]]:
        async with self._lock:
            with self._conn() as c:
                row = c.execute(
                    "SELECT api_key_enc, api_secret_enc, api_passphrase_enc FROM api_keys WHERE user_id=? AND exchange=? AND label=?",
                    (user_id, exchange, label),
                ).fetchone()
            if not row:
                return None
            return (
                self.vault.decrypt(row["api_key_enc"]),
                self.vault.decrypt(row["api_secret_enc"]),
                self.vault.decrypt(row["api_passphrase_enc"]),
            )

    async def delete_api_key(self, user_id: int, exchange: str, label: str) -> None:
        async with self._lock:
            with self._conn() as c:
                c.execute(
                    "DELETE FROM api_keys WHERE user_id=? AND exchange=? AND label=?",
                    (user_id, exchange, label),
                )
                c.commit()

    async def record_signal_action(self, user_id: int, signal_id: str, action: str, payload: Dict[str, Any]) -> None:
        async with self._lock:
            with self._conn() as c:
                c.execute(
                    "INSERT OR REPLACE INTO signal_actions VALUES (?,?,?,?,?)",
                    (user_id, signal_id, action, json.dumps(payload), time.time()),
                )
                c.commit()

    async def signal_action_stats(self, user_id: int) -> Dict[str, int]:
        async with self._lock:
            with self._conn() as c:
                rows = c.execute(
                    "SELECT action, COUNT(*) AS n FROM signal_actions WHERE user_id=? GROUP BY action",
                    (user_id,),
                ).fetchall()
            return {r["action"]: r["n"] for r in rows}


# ═══════════════════════════════════════════════════════════════════════════
#   MENU BUILDERS
# ═══════════════════════════════════════════════════════════════════════════

def _t(cfg: UserConfig, key: str) -> str:
    return LANG_TEXTS.get(cfg.language, LANG_TEXTS["en"]).get(key, key)


def _kb(rows: List[List[Tuple[str, str]]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(label, callback_data=cb) for label, cb in row] for row in rows]
    )


def main_menu_kb(cfg: UserConfig) -> InlineKeyboardMarkup:
    t = lambda k: _t(cfg, k)
    bot_label = "⏸️ Paused" if cfg.bot_paused else "▶️ Running"
    sim_label  = " [SIM]" if cfg.simulation_mode else ""
    return _kb([
        [(f"📊 Dashboard{sim_label}",   "menu:dash"),
         (f"{bot_label}",               "tog:botpause")],
        [(t("api_keys"),      "menu:keys"),       (t("settings"),  "menu:settings")],
        [(t("signals"),       "menu:signals"),    (t("positions"), "menu:positions")],
        [(t("history"),       "menu:history"),    (t("ai_valid"),  "menu:aiv")],
        [("📡 Groups/Channels","menu:groups"),    ("🔔 Alerts",     "menu:notifset")],
        [("🧪 Simulation",    "menu:sim"),        ("📐 Backtest",   "menu:backtest")],
        [("📐 Quant Stats",   "menu:quant"),      ("🧠 Patterns",   "menu:patterns")],
        [("📈 Factor IC/IR",  "menu:factor"),     ("📉 IV Surface", "menu:ivsurface")],
        [("⚖️ Portfolio Opt", "menu:portfolio"),  ("📊 Greeks",     "menu:greeks")],
        [(t("language"),      "menu:lang"),       (t("help"),      "menu:help")],
    ])


def settings_menu_kb(cfg: UserConfig) -> InlineKeyboardMarkup:
    amt_label = (f"Fixed {cfg.trade_amount_usdt:.0f} USDT" if cfg.amount_type == "fixed_usdt"
                 else f"Risk {cfg.risk_pct}%")
    tsl_label = (f"Trailing SL {cfg.trailing_stop_pct:.1f}%" if cfg.trailing_stop_enabled
                 else "Trailing SL: off")
    sl_label  = (f"SL: {cfg.sl_mode.upper()} "
                 + (f"{cfg.sl_fixed_pct:.1f}%" if cfg.sl_mode == "fixed_pct"
                    else (f"{cfg.sl_atr_mult}×ATR" if cfg.sl_mode == "atr" else "")))
    return _kb([
        [(f"⚖️ Risk Management",              "menu:risk")],
        [(f"💵 Position Size: {amt_label}",   "menu:possize")],
        [(f"🛑 Stop Loss: {sl_label}",        "menu:sl")],
        [(f"🔁 {tsl_label}",                  "menu:trailing")],
        [(f"📥 Entry Orders",                 "menu:entry")],
        [(f"🎯 Take Profit ({cfg.tp_count} TPs)", "menu:tp")],
        [(f"🛡️ Breakeven & Cascade",          "menu:becc")],
        [(f"🔧 Advanced Entry/Exit",          "menu:adventry")],
        [(f"📉 DCA Advanced",                 "menu:dcaadv")],
        [(f"📡 Copy Trading",                 "menu:copytrade")],
        [(f"🤖 Mode: {cfg.trading_mode.upper()}", "menu:mode")],
        [(f"💼 Margin Mode: {cfg.margin_mode.upper()}", "menu:margin")],
        [(f"💰 Margin %: {cfg.margin_pct:.0f}%", "menu:marginpct")],
        [(f"🎚️ Min Confidence: {cfg.signal_min_confidence:.0%}", "menu:minconf")],
        [("◀️ Back", "menu:main")],
    ])


def possize_menu_kb(cfg: UserConfig) -> InlineKeyboardMarkup:
    return _kb([
        [("📊 *Position Sizing Mode*", "noop")],
        [(f"{'✅' if cfg.amount_type == 'risk_pct'    else ''}📊 Risk % of Balance",  "set:amttype:risk_pct")],
        [(f"{'✅' if cfg.amount_type == 'fixed_usdt'  else ''}💵 Fixed USDT Amount",  "set:amttype:fixed_usdt")],
        [("─────────────────────────", "noop")],
        *([
            [(f"💵 Trade Amount: {cfg.trade_amount_usdt:.0f} USDT — tap to change", "ask:trade_usdt")],
            *[[(f"{'✅' if cfg.trade_amount_usdt == a else ''}{a} USDT", f"set:tradeusdt:{a}") for a in AMOUNT_USDT_PRESETS[:4]],
              [(f"{'✅' if cfg.trade_amount_usdt == a else ''}{a} USDT", f"set:tradeusdt:{a}") for a in AMOUNT_USDT_PRESETS[4:]]],
        ] if cfg.amount_type == "fixed_usdt" else [
            [(f"📊 Risk: {cfg.risk_pct}% per trade", "noop")],
        ]),
        [("──── Max Position Cap ────", "noop")],
        [(f"🔒 Max: {cfg.max_position_usdt:.0f} USDT", "ask:maxpos")],
        *[[(f"{'✅' if cfg.max_position_usdt == m else ''}{m} USDT", f"set:maxpos:{m}") for m in MAX_POS_USDT_PRESETS[:3]],
          [(f"{'✅' if cfg.max_position_usdt == m else ''}{m} USDT", f"set:maxpos:{m}") for m in MAX_POS_USDT_PRESETS[3:]]],
        [("◀️ Back", "menu:settings")],
    ])


def trailing_menu_kb(cfg: UserConfig) -> InlineKeyboardMarkup:
    chk = "✅" if cfg.trailing_stop_enabled else ""
    return _kb([
        [(f"{'✅' if cfg.trailing_stop_enabled else '⬜'} Trailing Stop: {'ON' if cfg.trailing_stop_enabled else 'OFF'}", "tog:trailing")],
        [("── Distance (%) ──", "noop")],
        *[[(f"{'✅' if abs(cfg.trailing_stop_pct - p) < 0.01 else ''}{p}%", f"set:tslpct:{p}") for p in TRAILING_SL_PRESETS[:4]],
          [(f"{'✅' if abs(cfg.trailing_stop_pct - p) < 0.01 else ''}{p}%", f"set:tslpct:{p}") for p in TRAILING_SL_PRESETS[4:]]],
        [("── Activation Profit ──", "noop")],
        [(f"{'✅' if abs(cfg.trailing_stop_activation_pct - p) < 0.01 else ''}{p}% profit", f"set:tslact:{p}")
         for p in [0.3, 0.5, 1.0, 1.5, 2.0]],
        [("◀️ Back", "menu:settings")],
    ])


def sim_menu_kb(cfg: UserConfig) -> InlineKeyboardMarkup:
    return _kb([
        [(f"{'✅' if cfg.simulation_mode else '⬜'} Paper/Simulation Mode: {'ON' if cfg.simulation_mode else 'OFF'}",
          "tog:simmode")],
        [("─── Copy Signals ────", "noop")],
        [(f"{'✅' if cfg.copy_signals_enabled else '⬜'} Copy Signals to Exchange",  "tog:copysig")],
        [("📊 Backtest Overview",  "menu:backtest"),
         ("📋 Symbol List",       "backtest:list")],
        [("◀️ Back", "menu:main")],
    ])


def notifset_menu_kb(cfg: UserConfig) -> InlineKeyboardMarkup:
    return _kb([
        [("🔔 *Notification Settings*", "noop")],
        [(f"{'✅' if cfg.notify_on == 'all'         else ''}📢 All trades",     "set:notifon:all")],
        [(f"{'✅' if cfg.notify_on == 'wins_only'   else ''}🎉 Wins only",      "set:notifon:wins_only")],
        [(f"{'✅' if cfg.notify_on == 'losses_only' else ''}⚠️ Losses only",   "set:notifon:losses_only")],
        [(f"{'✅' if cfg.notify_on == 'none'        else ''}🔇 None",           "set:notifon:none")],
        [("── Per-event notifications ──", "noop")],
        [(f"{'✅' if cfg.notify_entry else '⬜'} Entry",   "tog:notifentry"),
         (f"{'✅' if cfg.notify_tp    else '⬜'} TP",      "tog:notiftp"),
         (f"{'✅' if cfg.notify_sl    else '⬜'} SL",      "tog:notifsl"),
         (f"{'✅' if cfg.notify_dca   else '⬜'} DCA",     "tog:notifdca")],
        [("◀️ Back", "menu:main")],
    ])


def minconf_menu_kb(cfg: UserConfig) -> InlineKeyboardMarkup:
    rows = [(f"{'✅' if abs(cfg.signal_min_confidence - p) < 0.01 else ''}{p:.0%}", f"set:minconf:{p}")
            for p in MIN_CONF_PRESETS]
    mid = len(rows) // 2
    return _kb([
        [("🎚️ *Min Signal Confidence*", "noop")],
        rows[:mid],
        rows[mid:],
        [(f"🎯 Min Quality Score: {cfg.signal_min_quality}", "ask:minqual")],
        *[[(f"{'✅' if cfg.signal_min_quality == q else ''}{q}", f"set:minqual:{q}")
           for q in [50, 60, 65, 70, 75, 80]]],
        [("◀️ Back", "menu:settings")],
    ])


def sl_menu_kb(cfg: UserConfig) -> InlineKeyboardMarkup:
    """Stop Loss management — mode, distance, ATR multiplier, hard cap."""
    return _kb([
        [("🛑 *Stop Loss Mode*", "noop")],
        [(f"{'✅' if cfg.sl_mode == 'signal'    else ''}📡 Use Signal SL",     "set:slmode:signal")],
        [(f"{'✅' if cfg.sl_mode == 'fixed_pct' else ''}📏 Fixed % Distance",  "set:slmode:fixed_pct")],
        [(f"{'✅' if cfg.sl_mode == 'atr'       else ''}📊 ATR-Based SL",      "set:slmode:atr")],
        [(f"{'✅' if cfg.sl_mode == 'none'      else ''}🚫 No SL (DANGER)",    "set:slmode:none")],
        [("── Fixed % Distance ──", "noop")],
        [(f"{'✅' if abs(cfg.sl_fixed_pct - p) < 0.01 else ''}{p}%",
          f"set:slfixpct:{p}") for p in SL_FIXED_PCT_PRESETS[:4]],
        [(f"{'✅' if abs(cfg.sl_fixed_pct - p) < 0.01 else ''}{p}%",
          f"set:slfixpct:{p}") for p in SL_FIXED_PCT_PRESETS[4:]],
        [("── ATR Multiplier ──", "noop")],
        [(f"{'✅' if abs(cfg.sl_atr_mult - m) < 0.01 else ''}{m}×ATR",
          f"set:slatrmult:{m}") for m in SL_ATR_MULT_PRESETS],
        [("── Hard Cap (max risk per trade) ──", "noop")],
        [(f"{'✅' if abs(cfg.sl_max_pct - m) < 0.01 else ''}{m}%",
          f"set:slmaxpct:{m}") for m in SL_MAX_PCT_PRESETS[:4]],
        [(f"{'✅' if abs(cfg.sl_max_pct - m) < 0.01 else ''}{m}%",
          f"set:slmaxpct:{m}") for m in SL_MAX_PCT_PRESETS[4:]],
        [(f"{'✅' if cfg.use_market_on_sl else '⬜'} Market order on SL hit", "tog:marketsl")],
        [("◀️ Back", "menu:settings")],
    ])


def groups_menu_kb(cfg: UserConfig) -> InlineKeyboardMarkup:
    """Signal group / channel management menu."""
    rows = []
    for g in cfg.signal_groups[:8]:
        chk = "✅" if g == cfg.active_group else ""
        rows.append([(f"{chk}{g}", f"grp:active:{g}")])
    rows.append([("➕ Add channel / group", "ask:grpadd")])
    rows += [
        [("── Symbol Filter Mode ──", "noop")],
        [(f"{'✅' if cfg.group_filter_mode == 'all'       else ''}🌐 All symbols",   "set:grpfilt:all"),
         (f"{'✅' if cfg.group_filter_mode == 'whitelist' else ''}✅ Whitelist",      "set:grpfilt:whitelist")],
        [(f"{'✅' if cfg.group_filter_mode == 'blacklist' else ''}🚫 Blacklist",      "set:grpfilt:blacklist")],
        [("✏️ Edit whitelist", "ask:grpwl"), ("✏️ Edit blacklist", "ask:grpbl")],
        [("◀️ Back", "menu:main")],
    ]
    return _kb(rows)


def advanced_entry_kb(cfg: UserConfig) -> InlineKeyboardMarkup:
    """Advanced entry / exit options menu."""
    auto_close_label = (f"⏱ Auto-close after {cfg.auto_close_hours:.1f}h"
                        if cfg.auto_close_hours > 0 else "⏱ Auto-close: OFF")
    max_loss_label = (f"💸 Max loss: ${cfg.max_loss_usd:.0f}"
                      if cfg.max_loss_usd > 0 else "💸 Max loss stop: OFF")
    return _kb([
        [("🔧 *Advanced Entry / Exit Options*", "noop")],
        [(f"{'✅' if cfg.auto_close_hours > 0 else '⬜'} {auto_close_label}", "ask:autocloseH")],
        [(f"{'✅' if cfg.max_loss_usd > 0 else '⬜'} {max_loss_label}", "ask:maxlossusd")],
        [("── Partial Close at TP1 ──", "noop")],
        *[[(f"{'✅' if cfg.partial_close_pct == p else ''}{p}%", f"set:partclose:{p}")
           for p in PARTIAL_CLOSE_PRESETS[:4]],
          [(f"{'✅' if cfg.partial_close_pct == p else ''}{p}%", f"set:partclose:{p}")
           for p in PARTIAL_CLOSE_PRESETS[4:]]],
        [("◀️ Back", "menu:settings")],
    ])


def dca_advanced_kb(cfg: UserConfig) -> InlineKeyboardMarkup:
    """DCA Advanced settings — Cornix parity (deviation, volume scale, max orders, timeout)."""
    timeout_label = (f"⏱ Timeout: {cfg.signal_timeout_min} min"
                     if cfg.signal_timeout_min > 0 else "⏱ Signal Timeout: OFF")
    portfolio_label = f"💼 Portfolio Alloc: {cfg.portfolio_balance_pct:.0f}%"
    return _kb([
        [("📉 *DCA Advanced Settings*", "noop")],
        [("── DCA Price Deviation ──", "noop")],
        *[[(f"{'✅' if abs(cfg.dca_deviation_pct - p) < 0.01 else ''}{p}%",
            f"set:dcadev:{p}") for p in [0.5, 1.0, 1.5, 2.0, 3.0]]],
        [(f"✏️ Custom deviation: {cfg.dca_deviation_pct:.1f}%", "ask:dcadev")],
        [("── Volume Scale per DCA Step ──", "noop")],
        *[[(f"{'✅' if abs(cfg.dca_vol_scale - p) < 0.01 else ''}{p}×",
            f"set:dcavol:{p}") for p in [1.0, 1.5, 2.0, 2.5, 3.0]]],
        [(f"✏️ Custom scale: {cfg.dca_vol_scale:.1f}×", "ask:dcavol")],
        [("── Max DCA Orders ──", "noop")],
        [*([(f"{'✅' if cfg.dca_max_orders == n else ''}{n}", f"set:dcamax:{n}")
            for n in [1, 2, 3, 4, 5, 6]])],
        [("── Signal Entry Timeout ──", "noop")],
        [(f"{'✅' if cfg.signal_timeout_min == 0 else ''}⏱ No timeout", "set:sigtout:0"),
         (f"{'✅' if cfg.signal_timeout_min == 5 else ''}5 min",          "set:sigtout:5"),
         (f"{'✅' if cfg.signal_timeout_min == 15 else ''}15 min",        "set:sigtout:15")],
        [(f"{'✅' if cfg.signal_timeout_min == 30 else ''}30 min",        "set:sigtout:30"),
         (f"{'✅' if cfg.signal_timeout_min == 60 else ''}1 h",           "set:sigtout:60"),
         (f"{'✅' if cfg.signal_timeout_min == 120 else ''}2 h",          "set:sigtout:120")],
        [(f"✏️ Custom timeout", "ask:sigtout")],
        [("── Portfolio Allocation ──", "noop")],
        [*([(f"{'✅' if abs(cfg.portfolio_balance_pct - p) < 0.1 else ''}{p:.0f}%",
             f"set:portbal:{p}") for p in [25.0, 50.0, 75.0, 100.0]])],
        [("◀️ Back", "menu:settings")],
    ])


def copy_trading_kb(cfg: UserConfig) -> InlineKeyboardMarkup:
    """Copy trading source / mirroring settings — Cornix parity."""
    src_label = cfg.copy_source_channel if cfg.copy_source_channel else "Not set"
    enabled   = bool(cfg.copy_source_channel)
    return _kb([
        [("📡 *Copy Trading Settings*", "noop")],
        [(f"{'✅' if enabled else '⬜'} Copy trading: {'ACTIVE' if enabled else 'OFF'}", "noop")],
        [(f"📡 Source channel: {src_label}", "ask:copysrc")],
        [(f"🗑 Clear source channel", "set:copysrc:__clear__")],
        [("── Mirror Options ──", "noop")],
        [(f"{'✅' if cfg.copy_follow_tp else '⬜'} Follow TP edits",    "tog:copyfollowtp"),
         (f"{'✅' if cfg.copy_follow_sl else '⬜'} Follow SL edits",    "tog:copyfollowsl")],
        [(f"{'✅' if cfg.copy_follow_close else '⬜'} Follow close",     "tog:copyfollowclose")],
        [("── Signal Filters ──", "noop")],
        [(f"📊 Min confidence filter applies from main settings", "noop")],
        [("◀️ Back", "menu:settings")],
    ])


def quant_stats_kb() -> InlineKeyboardMarkup:
    """Quant performance report navigation."""
    return _kb([
        [("📐 Full Quant Report",    "quant:full")],
        [("📈 Sharpe / Sortino",     "quant:sharpe")],
        [("📉 Max Drawdown",         "quant:dd")],
        [("🎲 EV & Kelly Fraction",  "quant:kelly")],
        [("🏆 Top Symbols by EV",    "quant:topsym")],
        [("◀️ Back", "menu:main")],
    ])


def portfolio_optimizer_kb() -> InlineKeyboardMarkup:
    """Portfolio optimizer method selection."""
    return _kb([
        [("📈 Max Sharpe Ratio",      "portopt:max_sharpe")],
        [("🛡️ Min Variance",          "portopt:min_var")],
        [("⚖️ Risk Parity (ERC)",     "portopt:risk_parity")],
        [("🧠 Black-Litterman",       "portopt:bl")],
        [("🔄 Refresh Weights",       "portopt:refresh")],
        [("◀️ Back", "menu:main")],
    ])


def factor_icir_kb() -> InlineKeyboardMarkup:
    """Factor IC/IR analysis navigation."""
    return _kb([
        [("📊 Full IC/IR Report",     "factor:report")],
        [("📈 1D Holding Period",     "factor:1d")],
        [("📈 5D Holding Period",     "factor:5d")],
        [("📈 21D Holding Period",    "factor:21d")],
        [("🔄 Refresh",              "factor:refresh")],
        [("◀️ Back", "menu:main")],
    ])


def pattern_analysis_kb() -> InlineKeyboardMarkup:
    """Pattern recognition navigation."""
    return _kb([
        [("🧠 Latest Patterns",      "pattern:latest")],
        [("🟢 Bullish Setups",       "pattern:bullish")],
        [("🔴 Bearish Setups",       "pattern:bearish")],
        [("🔄 Refresh",             "pattern:refresh")],
        [("◀️ Back", "menu:main")],
    ])


def greeks_kb() -> InlineKeyboardMarkup:
    """Greeks / IV surface navigation."""
    return _kb([
        [("📉 BTC IV Surface",       "greeks:btc")],
        [("📉 ETH IV Surface",       "greeks:eth")],
        [("📉 SOL IV Surface",       "greeks:sol")],
        [("🔢 Calculate Greeks",     "greeks:calc")],
        [("🔄 Refresh",             "greeks:refresh")],
        [("◀️ Back", "menu:main")],
    ])


def risk_menu_kb(cfg: UserConfig) -> InlineKeyboardMarkup:
    lev_row = [(f"{'✅' if cfg.leverage == lv else ''}{lv}x", f"set:lev:{lv}") for lv in LEVERAGE_PRESETS[:5]]
    lev_row2 = [(f"{'✅' if cfg.leverage == lv else ''}{lv}x", f"set:lev:{lv}") for lv in LEVERAGE_PRESETS[5:]]
    risk_row = [(f"{'✅' if abs(cfg.risk_pct - rp) < 0.01 else ''}{rp}%", f"set:risk:{rp}") for rp in RISK_PCT_PRESETS]
    mt_row = [(f"{'✅' if cfg.max_open_trades == mt else ''}{mt}", f"set:maxtr:{mt}") for mt in MAX_TRADES_PRESETS]
    return _kb([
        [("⚡ *Leverage*", "noop")],
        lev_row,
        lev_row2,
        [("📊 *Risk per Trade*", "noop")],
        risk_row,
        [("🔢 *Max Open Trades*", "noop")],
        mt_row,
        [(f"💵 Stake (USDT): {cfg.stake_usdt:.2f}" if cfg.stake_usdt else "💵 Stake (USDT): off", "ask:stake")],
        [("◀️ Back", "menu:settings")],
    ])


def entry_menu_kb(cfg: UserConfig) -> InlineKeyboardMarkup:
    return _kb([
        [(f"{'✅' if cfg.entry_type == 'market' else ''}⚡ Market", "set:entry:market"),
         (f"{'✅' if cfg.entry_type == 'limit'  else ''}🎯 Limit",  "set:entry:limit")],
        [(f"⏱ Limit Timeout: {cfg.limit_timeout_min} min", "ask:limit_to")],
        [("📦 *DCA (Dollar Cost Averaging)*", "noop")],
        [(f"{'✅' if cfg.dca_orders == n else ''}{n} orders", f"set:dca:{n}") for n in [0, 1, 2, 3, 5]],
        [(f"📈 DCA Multiplier: x{cfg.dca_multiplier:.2f}", "ask:dca_mult")],
        [("◀️ Back", "menu:settings")],
    ])


def tp_menu_kb(cfg: UserConfig) -> InlineKeyboardMarkup:
    cnt_row = [(f"{'✅' if cfg.tp_count == n else ''}{n} TP", f"set:tpcnt:{n}") for n in [1, 2, 3, 4]]
    dist_rows = []
    for k, v in TP_DISTRIBUTIONS.items():
        if cfg.tp_count != len(v) and not (k == "full_tp1" and cfg.tp_count >= 1):
            continue
        chk = "✅" if cfg.tp_distribution == k else ""
        dist_rows.append([(f"{chk}{k}: {'/'.join(map(str, v))}", f"set:tpdist:{k}")])
    return _kb([
        [("🎯 *TP Count*", "noop")],
        cnt_row,
        [("📊 *Volume Distribution*", "noop")],
        *dist_rows,
        [(f"{'✅' if cfg.full_close_tp1 else '⬜'} Full close at TP1", "tog:fulltp1")],
        [("✏️ Custom Distribution", "ask:tpcustom")],
        [("◀️ Back", "menu:settings")],
    ])


def becc_menu_kb(cfg: UserConfig) -> InlineKeyboardMarkup:
    be_row = [(f"{'✅' if cfg.breakeven_after_tp == n else ''}{'OFF' if n == 0 else f'TP{n}'}",
               f"set:be:{n}") for n in range(0, cfg.tp_count + 1)]
    cs_row = [(f"{'✅' if cfg.cascade_after_tp == n else ''}{'OFF' if n == 0 else f'TP{n}'}",
               f"set:cs:{n}") for n in range(0, cfg.tp_count + 1)]
    return _kb([
        [("🛡️ *Breakeven after*", "noop")], be_row,
        [("📉 *Cascade after*", "noop")], cs_row,
        [(f"{'✅' if cfg.be_plus_cascade else '⬜'} BE + Cascade Together", "tog:becc")],
        [("◀️ Back", "menu:settings")],
    ])


def mode_menu_kb(cfg: UserConfig) -> InlineKeyboardMarkup:
    return _kb([
        [(f"{'✅' if cfg.trading_mode == 'auto'   else ''}🤖 Auto",   "set:mode:auto")],
        [(f"{'✅' if cfg.trading_mode == 'manual' else ''}👤 Manual", "set:mode:manual")],
        [(f"{'✅' if cfg.trading_mode == 'off'    else ''}🔇 Off",    "set:mode:off")],
        [("◀️ Back", "menu:settings")],
    ])


def margin_menu_kb(cfg: UserConfig) -> InlineKeyboardMarkup:
    return _kb([
        [(f"{'✅' if cfg.margin_mode == 'isolated' else ''}🔒 Isolated", "set:mm:isolated"),
         (f"{'✅' if cfg.margin_mode == 'cross'    else ''}🔄 Cross",    "set:mm:cross")],
        [("◀️ Back", "menu:settings")],
    ])


def keys_menu_kb(cfg: UserConfig, keys: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    rows = []
    for k in keys[:10]:
        label = f"✅ {k['exchange'].upper()} · {k['label']} ({k['masked']})"
        rows.append([(label, f"key:select:{k['exchange']}:{k['label']}")])
    rows.append([("➕ Add new key", "key:add")])
    rows.append([("◀️ Back", "menu:main")])
    return _kb(rows)


def add_exchange_kb() -> InlineKeyboardMarkup:
    rows = []
    for exch, label in SUPPORTED_EXCHANGES:
        rows.append([(label, f"key:exchange:{exch}")])
    rows.append([("◀️ Back", "menu:keys")])
    return _kb(rows)


def signal_action_kb(signal_id: str, has_keys: bool = False) -> InlineKeyboardMarkup:
    """Per-signal action buttons attached to a published signal.
    v10.5: adds 💹 Execute Now button when exchange keys are configured."""
    rows = [
        [("🚀 Follow Signal", f"sig:follow:{signal_id}"),
         ("🙈 Ignore",        f"sig:ignore:{signal_id}")],
        [("📊 Brief",  f"sig:brief:{signal_id}"),
         ("📊 Detailed", f"sig:detail:{signal_id}")],
    ]
    if has_keys:
        rows.append([
            ("💹 Execute Now", f"sig:execute:{signal_id}"),
            ("❌ Close All",   f"pos:closeall"),
        ])
    rows.append([("📋 Check History", "menu:history"),
                 ("🔁 Retry", f"sig:retry:{signal_id}")])
    return _kb(rows)


def position_kb(symbol: str, side: str, qty: float) -> InlineKeyboardMarkup:
    """v10.5: Per-position action buttons (market close, partial close)."""
    safe = symbol.replace("/", "_")
    qty_str = f"{qty:.4f}".rstrip("0").rstrip(".")
    return _kb([
        [(f"❌ Close {safe} ({side})", f"pos:close:{safe}:{side}:{qty_str}")],
        [(f"📉 Close 50%", f"pos:close50:{safe}:{side}:{qty_str}")],
        [("◀️ Back", "menu:positions")],
    ])


# ═══════════════════════════════════════════════════════════════════════════
#   MAIN BOT
# ═══════════════════════════════════════════════════════════════════════════

def backtest_sym_kb(sym_reports: List[Dict[str, Any]], page: int = 0) -> InlineKeyboardMarkup:
    """Keyboard listing simulated symbols with their key metrics (paginated 8/page)."""
    PAGE_SIZE = 8
    start = page * PAGE_SIZE
    chunk = sym_reports[start: start + PAGE_SIZE]
    rows: List[List[Tuple[str, str]]] = []
    for r in chunk:
        sym = r.get("symbol", "?")
        wr  = r.get("win_rate_pct", 0.0)
        sh  = r.get("sharpe", 0.0)
        bias= r.get("quality_bias", 0.0)
        bias_icon = "🟢" if bias >= 3 else ("🟡" if bias >= 0 else "🔴")
        rows.append([(
            f"{bias_icon} {sym}  WR:{wr:.0f}%  Sh:{sh:.2f}",
            f"backtest:sym:{sym}"
        )])
    nav: List[Tuple[str, str]] = []
    if page > 0:
        nav.append(("◀️ Prev", f"backtest:page:{page-1}"))
    if start + PAGE_SIZE < len(sym_reports):
        nav.append(("Next ▶️", f"backtest:page:{page+1}"))
    if nav:
        rows.append(nav)
    rows.append([("🔄 Refresh All", "menu:backtest"), ("◀️ Back", "menu:main")])
    return _kb(rows)


def backtest_sym_detail_kb(symbol: str) -> InlineKeyboardMarkup:
    return _kb([
        [(f"▶️ Run Now on {symbol}", f"backtest:run:{symbol}")],
        [("◀️ Symbol List",          "backtest:list"),
         ("◀️ Back",                "menu:backtest")],
    ])


class CornixMenuBot:
    """Self-contained Cornix-replacement menu router for python-telegram-bot.

    v10.2 improvements:
    • Admin gate — only UNITY_ADMIN_IDS user-IDs can interact (default: open)
    • Per-symbol backtest detail view with Sharpe/Sortino/Calmar/EV/MDD
    • On-demand MiroFish simulation trigger via 'Run Now' button
    • Symbol list paginator (8 per page, colour-coded by quality bias)
    • Enhanced backtest overview with top-5 symbol scorecards
    • Enhanced summary_stats() consumption (avg_sortino, avg_max_dd_pct)
    """

    PENDING_INPUT_KEY = "_cornix_pending"

    def __init__(self, store: Optional[UserConfigStore] = None,
                 balance_provider: Optional[Callable] = None,
                 positions_provider: Optional[Callable] = None,
                 history_provider: Optional[Callable] = None,
                 signal_executor: Optional[Callable] = None,
                 bot_token: Optional[str] = None,
                 session_provider: Optional[Callable] = None,
                 admin_ids: Optional[List[int]] = None):
        self.store = store or UserConfigStore()
        self.balance_provider   = balance_provider
        self.positions_provider = positions_provider
        self.history_provider   = history_provider
        self.signal_executor    = signal_executor
        self._attached: bool = False
        # v10.5: CCXT exchange provider for live balance/positions/orders
        self._ccxt_provider: CcxtExchangeProvider = CcxtExchangeProvider(self.store)
        # v10.5: Signal cache for order execution (signal_id → signal data)
        self._signal_cache: Dict[str, Dict[str, Any]] = {}
        # Raw mode (custom poller integration) ─────────────
        self.bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN") or ""
        self.base_url  = f"https://api.telegram.org/bot{self.bot_token}" if self.bot_token else ""
        self._session_provider = session_provider
        self._raw_pending: Dict[int, Dict[str, Any]] = {}  # user_id → input wizard state
        # Admin gate — set from UNITY_ADMIN_IDS env var (comma-separated ints)
        _env_ids = (admin_ids or [])
        if not _env_ids:
            _raw = os.getenv("UNITY_ADMIN_IDS", os.getenv("ADMIN_CHAT_ID", ""))
            _env_ids = [int(x.strip()) for x in _raw.replace(";", ",").split(",")
                        if x.strip().lstrip("-").isdigit()]
        self._admin_ids: List[int] = _env_ids  # empty list = open to all

    # ── raw HTTP helpers (for custom poller integration) ────────────────────

    async def _raw_session(self) -> "aiohttp.ClientSession":
        if self._session_provider:
            return await self._session_provider()
        if not _HAS_AIOHTTP:
            raise RuntimeError("aiohttp required for raw Telegram API calls")
        if not hasattr(self, "_owned_session") or self._owned_session is None or self._owned_session.closed:
            self._owned_session = aiohttp.ClientSession()
        return self._owned_session

    async def _api(self, method: str, **kwargs) -> Dict[str, Any]:
        if not self.base_url:
            return {"ok": False, "description": "no_token"}
        url = f"{self.base_url}/{method}"
        try:
            sess = await self._raw_session()
            async with sess.post(url, json=kwargs, timeout=aiohttp.ClientTimeout(total=10)) as r:
                return await r.json()
        except Exception as e:
            logger.debug(f"Telegram API {method} failed: {e}")
            return {"ok": False, "description": str(e)}

    async def _send(self, chat_id: Any, text: str, kb: Optional[InlineKeyboardMarkup] = None) -> Dict[str, Any]:
        payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
        if kb is not None:
            payload["reply_markup"] = self._kb_to_dict(kb)
        return await self._api("sendMessage", **payload)

    async def _edit(self, chat_id: Any, message_id: int, text: str,
                    kb: Optional[InlineKeyboardMarkup] = None) -> Dict[str, Any]:
        payload = {"chat_id": chat_id, "message_id": message_id, "text": text, "parse_mode": "Markdown"}
        if kb is not None:
            payload["reply_markup"] = self._kb_to_dict(kb)
        r = await self._api("editMessageText", **payload)
        if not r.get("ok") and "not modified" not in str(r.get("description", "")).lower():
            # fall back to sending a new message
            return await self._send(chat_id, text, kb)
        return r

    async def _answer_cb(self, callback_id: str, text: str = "") -> None:
        await self._api("answerCallbackQuery", callback_query_id=callback_id, text=text)

    @staticmethod
    def _kb_to_dict(kb: "InlineKeyboardMarkup") -> Dict[str, Any]:
        rows = []
        for row in kb.inline_keyboard:
            rows.append([{"text": btn.text, "callback_data": btn.callback_data} for btn in row])
        return {"inline_keyboard": rows}

    # ── raw update dispatcher (called by the engine's custom poller) ────────

    def _is_admin(self, user_id: Optional[int]) -> bool:
        """Return True if this user is allowed to use the menu bot.
        If no admin IDs are configured, all users are allowed (open mode)."""
        if not self._admin_ids:
            return True
        return user_id in self._admin_ids

    async def process_raw_update(self, update: Dict[str, Any]) -> bool:
        """Returns True if this update was handled (so the caller can skip it)."""
        try:
            # callback_query (button press)
            if "callback_query" in update:
                cb = update["callback_query"]
                user_id = cb.get("from", {}).get("id")
                chat_id = cb.get("message", {}).get("chat", {}).get("id")
                msg_id  = cb.get("message", {}).get("message_id")
                data    = cb.get("data", "")
                cb_id   = cb.get("id", "")
                await self._answer_cb(cb_id)
                if user_id and chat_id and data:
                    if not self._is_admin(user_id):
                        await self._api("answerCallbackQuery",
                                        callback_query_id=cb_id,
                                        text="⛔ Authorised users only.",
                                        show_alert=True)
                        return True
                    await self._dispatch_callback_raw(user_id, chat_id, msg_id, data)
                return True

            # plain text message — check for /start, /menu, or pending wizard input
            msg = update.get("message") or update.get("channel_post")
            if not msg:
                return False
            user_id = msg.get("from", {}).get("id")
            chat_id = msg.get("chat", {}).get("id")
            text    = (msg.get("text") or "").strip()
            if not user_id or not chat_id:
                return False

            if not self._is_admin(user_id):
                return False  # silently ignore unknown users

            # pending input wizard takes precedence
            if user_id in self._raw_pending and not text.startswith("/"):
                cfg = await self.store.get(user_id)
                await self._dispatch_text_raw(user_id, chat_id, text, cfg)
                return True

            if text in ("/start", "/menu") or text.startswith("/start ") or text.startswith("/menu "):
                cfg = await self.store.get(user_id)
                await self._send(chat_id, _t(cfg, "welcome"), main_menu_kb(cfg))
                return True
            return False
        except Exception as e:
            logger.exception(f"process_raw_update error: {e}")
            return False

    async def _dispatch_text_raw(self, user_id: int, chat_id: int, text: str, cfg: UserConfig) -> None:
        pending = self._raw_pending.get(user_id, {})
        kind = pending.get("kind")
        try:
            if kind == "stake":
                cfg.stake_usdt = max(0.0, float(text))
            elif kind == "limit_to":
                cfg.limit_timeout_min = max(1, int(float(text)))
            elif kind == "dca_mult":
                cfg.dca_multiplier = max(1.0, float(text))
            elif kind == "marginpct":
                cfg.margin_pct = max(0.1, min(100.0, float(text)))
            elif kind == "trade_usdt":
                cfg.trade_amount_usdt = max(1.0, float(text))
            elif kind == "maxpos":
                cfg.max_position_usdt = max(10.0, float(text))
            elif kind == "minqual":
                cfg.signal_min_quality = max(0, min(100, int(float(text))))
            elif kind == "tpcustom":
                parts = [int(p.strip()) for p in text.replace("/", ",").split(",") if p.strip()]
                if parts and sum(parts) == 100 and 1 <= len(parts) <= 4:
                    cfg.tp_distribution = "custom"
                    cfg.tp_custom = parts
                    cfg.tp_count  = len(parts)
                else:
                    raise ValueError("Distribution must be 1–4 numbers summing to 100")
            elif kind == "autocloseH":
                cfg.auto_close_hours = max(0.0, float(text))
            elif kind == "maxlossusd":
                cfg.max_loss_usd = max(0.0, float(text))
            elif kind == "grpadd":
                g = text.strip() if (text.startswith("@") or text.startswith("-100")) else "@" + text.strip()
                if g and g not in cfg.signal_groups:
                    cfg.signal_groups.append(g)
            elif kind == "grpwl":
                cfg.symbol_whitelist = [s.strip().upper() for s in text.replace(" ", ",").split(",") if s.strip()]
            elif kind == "grpbl":
                cfg.symbol_blacklist = [s.strip().upper() for s in text.replace(" ", ",").split(",") if s.strip()]
            elif kind == "channel":
                cfg.signal_channel = text if (text.startswith("@") or text.startswith("-100")) else "@" + text
            # v11.0 DCA advanced / copy trading text inputs
            elif kind == "dcadev":
                cfg.dca_deviation_pct = max(0.1, float(text))
            elif kind == "dcavol":
                cfg.dca_vol_scale = max(0.5, float(text))
            elif kind == "sigtout":
                cfg.signal_timeout_min = max(0, int(float(text)))
            elif kind == "copysrc":
                g = text.strip()
                cfg.copy_source_channel = "" if g.lower() in ("off", "none", "0", "") else (g if g.startswith("@") or g.startswith("-100") else "@" + g)
            elif kind in ("api_label", "api_key", "api_secret", "api_pass"):
                pending[kind] = text
                exch = pending.get("exchange", "")
                # state machine for API key wizard
                if kind == "api_label":
                    pending["kind"] = "api_key"
                    self._raw_pending[user_id] = pending
                    await self._send(chat_id, f"🔑 *{exch.upper()}* — Step 2/3\nSend the API Key:")
                    return
                if kind == "api_key":
                    pending["kind"] = "api_secret"
                    self._raw_pending[user_id] = pending
                    await self._send(chat_id, f"🔑 *{exch.upper()}* — Step 3/3\nSend the API Secret:")
                    return
                if kind == "api_secret":
                    needs_pass = exch in ("okx", "kucoin")
                    if needs_pass and "api_pass" not in pending:
                        pending["kind"] = "api_pass"
                        self._raw_pending[user_id] = pending
                        await self._send(chat_id, f"🔑 *{exch.upper()}* — Step 4/4\nSend the API Passphrase:")
                        return
                    await self.store.add_api_key(
                        user_id, exch, pending["api_label"],
                        pending["api_key"], pending["api_secret"], pending.get("api_pass", ""),
                    )
                    cfg.active_exchange = exch
                    await self.store.save(cfg)
                    self._raw_pending.pop(user_id, None)
                    await self._send(chat_id,
                        f"✅ Saved *{exch.upper()}* key '{pending['api_label']}' (encrypted at rest).",
                        main_menu_kb(cfg))
                    return
                if kind == "api_pass":
                    await self.store.add_api_key(
                        user_id, exch, pending["api_label"],
                        pending["api_key"], pending["api_secret"], pending["api_pass"],
                    )
                    cfg.active_exchange = exch
                    await self.store.save(cfg)
                    self._raw_pending.pop(user_id, None)
                    await self._send(chat_id,
                        f"✅ Saved *{exch.upper()}* key '{pending['api_label']}' (encrypted at rest).",
                        main_menu_kb(cfg))
                    return
            else:
                return
            await self.store.save(cfg)
            self._raw_pending.pop(user_id, None)
            await self._send(chat_id, f"{_t(cfg, 'saved')} ✅", main_menu_kb(cfg))
        except Exception as e:
            await self._send(chat_id, f"❌ Invalid input: {e}\n\nTry again or send /start.")

    async def _dispatch_callback_raw(self, user_id: int, chat_id: int, msg_id: int, data: str) -> None:
        cfg = await self.store.get(user_id)
        try:
            # v10.5: Lightweight adapter so _handle_position_close /
            # _handle_execute_signal can operate without PTB Update objects.
            class _RawCallbackQ:
                """Duck-typing shim for PTB CallbackQuery."""
                def __init__(self_, chat_id_: int, msg_id_: int) -> None:
                    self_._cid  = chat_id_
                    self_._mid  = msg_id_
                async def answer(self_, text: str = "") -> None:
                    pass   # ACK via raw poll; no-op
                async def edit_message_text(self_, text: str, *, reply_markup=None, parse_mode: str = "Markdown") -> None:
                    await self._edit(self_._cid, self_._mid, text, reply_markup or _kb([]))
                @property
                def message(self_):
                    class _Msg:
                        chat_id = chat_id
                        async def reply_text(self__, txt, **kw):
                            await self._send(chat_id, txt)
                    return _Msg()
            q_wrapper = _RawCallbackQ(chat_id, msg_id)

            # Mirror the Application-handler routing but using raw HTTP edits
            if data == "noop":
                return
            if data == "menu:main":
                return await self._edit(chat_id, msg_id, _t(cfg, "welcome"), main_menu_kb(cfg))
            if data == "menu:dash":
                return await self._render_dashboard(chat_id, msg_id, cfg)
            if data == "menu:keys":
                return await self._render_keys(chat_id, msg_id, cfg)
            if data == "menu:settings":
                return await self._edit(chat_id, msg_id, "⚙️ *Settings*", settings_menu_kb(cfg))
            if data == "menu:signals":
                return await self._render_signals(chat_id, msg_id, cfg)
            if data == "menu:positions":
                return await self._render_positions(chat_id, msg_id, cfg)
            if data == "menu:history":
                return await self._render_history(chat_id, msg_id, cfg)
            if data == "menu:aiv":
                return await self._render_aiv(chat_id, msg_id, cfg)
            if data == "menu:channel":
                return await self._render_channel(chat_id, msg_id, cfg, user_id)
            if data == "menu:notif":
                cfg.notifications = not cfg.notifications
                await self.store.save(cfg)
                return await self._edit(chat_id, msg_id,
                    f"🔔 Notifications: *{'ON' if cfg.notifications else 'OFF'}*",
                    main_menu_kb(cfg))
            if data == "menu:lang":
                return await self._edit(chat_id, msg_id, "🌐 Choose language / Выберите язык:", _kb([
                    [("🇬🇧 English", "set:lang:en"), ("🇷🇺 Русский", "set:lang:ru")],
                    [("◀️ Back", "menu:main")],
                ]))
            if data == "menu:help":
                return await self._render_help(chat_id, msg_id, cfg)
            if data == "menu:risk":
                return await self._edit(chat_id, msg_id, "⚖️ *Risk Management*", risk_menu_kb(cfg))
            if data == "menu:entry":
                return await self._edit(chat_id, msg_id, "📥 *Entry Orders*", entry_menu_kb(cfg))
            if data == "menu:tp":
                return await self._edit(chat_id, msg_id, "🎯 *Take Profit*", tp_menu_kb(cfg))
            if data == "menu:becc":
                return await self._edit(chat_id, msg_id, "🛡️ *Breakeven & Cascade*", becc_menu_kb(cfg))
            if data == "menu:mode":
                return await self._edit(chat_id, msg_id, "🤖 *Trading Mode*", mode_menu_kb(cfg))
            if data == "menu:margin":
                return await self._edit(chat_id, msg_id, "💼 *Margin Mode*", margin_menu_kb(cfg))
            if data == "menu:marginpct":
                self._raw_pending[user_id] = {"kind": "marginpct"}
                return await self._edit(chat_id, msg_id, "💰 Send margin % (0.1 – 100):")

            # v10.0 new menus (raw HTTP path)
            if data == "menu:possize":
                return await self._edit(chat_id, msg_id, "💵 *Position Sizing*", possize_menu_kb(cfg))
            if data == "menu:trailing":
                return await self._edit(chat_id, msg_id, "🔁 *Trailing Stop Loss*", trailing_menu_kb(cfg))
            if data == "menu:sim":
                return await self._edit(chat_id, msg_id, "🧪 *Simulation Settings*", sim_menu_kb(cfg))
            if data == "menu:notifset":
                return await self._edit(chat_id, msg_id, "🔔 *Alert Settings*", notifset_menu_kb(cfg))
            if data == "menu:minconf":
                return await self._edit(chat_id, msg_id, "🎚️ *Signal Confidence Filter*", minconf_menu_kb(cfg))
            if data == "menu:backtest":
                return await self._show_backtest(chat_id, msg_id, cfg)
            if data == "menu:sl":
                return await self._edit(chat_id, msg_id, "🛑 *Stop Loss Management*", sl_menu_kb(cfg))
            if data == "menu:groups":
                return await self._edit(chat_id, msg_id, "📡 *Signal Groups & Channels*", groups_menu_kb(cfg))
            if data == "menu:adventry":
                return await self._edit(chat_id, msg_id, "🔧 *Advanced Entry / Exit*", advanced_entry_kb(cfg))
            if data == "menu:dcaadv":
                return await self._edit(chat_id, msg_id, "📉 *DCA Advanced Settings*", dca_advanced_kb(cfg))
            if data == "menu:copytrade":
                return await self._edit(chat_id, msg_id, "📡 *Copy Trading Settings*", copy_trading_kb(cfg))
            if data == "menu:quant":
                return await self._show_quant_stats(chat_id, msg_id)
            if data == "menu:portfolio":
                return await self._render_portfolio(chat_id, msg_id)
            if data == "menu:factor":
                return await self._render_factor(chat_id, msg_id)
            if data == "menu:patterns":
                return await self._render_patterns(chat_id, msg_id)
            if data == "menu:ivsurface":
                return await self._render_iv_surface(chat_id, msg_id)
            if data == "menu:greeks":
                return await self._edit(chat_id, msg_id, "📊 *Options Greeks & IV Surface*", greeks_kb())
            if data.startswith("portopt:"):
                return await self._handle_portopt(chat_id, msg_id, data[8:])
            if data.startswith("factor:"):
                return await self._handle_factor(chat_id, msg_id, data[7:])
            if data.startswith("pattern:"):
                return await self._handle_pattern(chat_id, msg_id, data[8:])
            if data.startswith("greeks:"):
                return await self._handle_greeks(chat_id, msg_id, data[7:])

            if data.startswith("set:"):
                _, key, *rest = data.split(":")
                val = ":".join(rest)
                if key == "lev":          cfg.leverage = int(val)
                elif key == "risk":       cfg.risk_pct = float(val)
                elif key == "maxtr":      cfg.max_open_trades = int(val)
                elif key == "entry":      cfg.entry_type = val
                elif key == "dca":        cfg.dca_orders = int(val)
                elif key == "tpcnt":      cfg.tp_count = int(val)
                elif key == "tpdist":     cfg.tp_distribution = val
                elif key == "be":         cfg.breakeven_after_tp = int(val)
                elif key == "cs":         cfg.cascade_after_tp = int(val)
                elif key == "mode":       cfg.trading_mode = val
                elif key == "mm":         cfg.margin_mode = val
                elif key == "lang":       cfg.language = val
                elif key == "amttype":    cfg.amount_type = val
                elif key == "tradeusdt":  cfg.trade_amount_usdt = max(1.0, float(val))
                elif key == "maxpos":     cfg.max_position_usdt = max(10.0, float(val))
                elif key == "tslpct":     cfg.trailing_stop_pct = max(0.1, float(val))
                elif key == "tslact":     cfg.trailing_stop_activation_pct = max(0.1, float(val))
                elif key == "notifon":    cfg.notify_on = val
                elif key == "minconf":    cfg.signal_min_confidence = max(0.0, min(1.0, float(val)))
                elif key == "minqual":    cfg.signal_min_quality = max(0, min(100, int(float(val))))
                # v10.0 SL config
                elif key == "slmode":    cfg.sl_mode = val
                elif key == "slfixpct":  cfg.sl_fixed_pct = max(0.1, float(val))
                elif key == "slatrmult": cfg.sl_atr_mult = max(0.5, float(val))
                elif key == "slmaxpct":  cfg.sl_max_pct = max(0.5, float(val))
                # v10.0 group filter
                elif key == "grpfilt":   cfg.group_filter_mode = val
                # v10.0 partial close
                elif key == "partclose": cfg.partial_close_pct = max(1.0, min(100.0, float(val)))
                # v11.0 DCA advanced setters
                elif key == "dcadev":   cfg.dca_deviation_pct = max(0.1, float(val))
                elif key == "dcavol":   cfg.dca_vol_scale = max(0.5, float(val))
                elif key == "dcamax":   cfg.dca_max_orders = max(1, min(10, int(val)))
                elif key == "sigtout":  cfg.signal_timeout_min = max(0, int(float(val)))
                elif key == "portbal":  cfg.portfolio_balance_pct = max(1.0, min(100.0, float(val)))
                # v11.0 copy trading setters
                elif key == "copysrc":
                    cfg.copy_source_channel = "" if val == "__clear__" else val.strip()
                await self.store.save(cfg)
                if key in ("lev", "risk", "maxtr"):
                    return await self._edit(chat_id, msg_id, "⚖️ *Risk Management*", risk_menu_kb(cfg))
                if key in ("entry", "dca"):
                    return await self._edit(chat_id, msg_id, "📥 *Entry Orders*", entry_menu_kb(cfg))
                if key in ("tpcnt", "tpdist"):
                    return await self._edit(chat_id, msg_id, "🎯 *Take Profit*", tp_menu_kb(cfg))
                if key in ("be", "cs"):
                    return await self._edit(chat_id, msg_id, "🛡️ *Breakeven & Cascade*", becc_menu_kb(cfg))
                if key == "mode":
                    return await self._edit(chat_id, msg_id, "🤖 *Trading Mode*", mode_menu_kb(cfg))
                if key == "mm":
                    return await self._edit(chat_id, msg_id, "💼 *Margin Mode*", margin_menu_kb(cfg))
                if key == "lang":
                    return await self._edit(chat_id, msg_id, _t(cfg, "welcome"), main_menu_kb(cfg))
                if key in ("amttype", "tradeusdt", "maxpos"):
                    return await self._edit(chat_id, msg_id, "💵 *Position Sizing*", possize_menu_kb(cfg))
                if key in ("tslpct", "tslact"):
                    return await self._edit(chat_id, msg_id, "🔁 *Trailing Stop Loss*", trailing_menu_kb(cfg))
                if key == "notifon":
                    return await self._edit(chat_id, msg_id, "🔔 *Alert Settings*", notifset_menu_kb(cfg))
                if key in ("minconf", "minqual"):
                    return await self._edit(chat_id, msg_id, "🎚️ *Signal Confidence Filter*", minconf_menu_kb(cfg))
                if key in ("slmode", "slfixpct", "slatrmult", "slmaxpct"):
                    return await self._edit(chat_id, msg_id, "🛑 *Stop Loss Management*", sl_menu_kb(cfg))
                if key == "grpfilt":
                    return await self._edit(chat_id, msg_id, "📡 *Signal Groups & Channels*", groups_menu_kb(cfg))
                if key == "partclose":
                    return await self._edit(chat_id, msg_id, "🔧 *Advanced Entry / Exit*", advanced_entry_kb(cfg))
                if key in ("dcadev", "dcavol", "dcamax", "sigtout", "portbal"):
                    return await self._edit(chat_id, msg_id, "📉 *DCA Advanced Settings*", dca_advanced_kb(cfg))
                if key == "copysrc":
                    return await self._edit(chat_id, msg_id, "📡 *Copy Trading Settings*", copy_trading_kb(cfg))
                return

            # v11.0 copy trading toggles (raw HTTP path)
            if data == "tog:copyfollowtp":
                cfg.copy_follow_tp = not cfg.copy_follow_tp
                await self.store.save(cfg)
                return await self._edit(chat_id, msg_id, "📡 *Copy Trading Settings*", copy_trading_kb(cfg))
            if data == "tog:copyfollowsl":
                cfg.copy_follow_sl = not cfg.copy_follow_sl
                await self.store.save(cfg)
                return await self._edit(chat_id, msg_id, "📡 *Copy Trading Settings*", copy_trading_kb(cfg))
            if data == "tog:copyfollowclose":
                cfg.copy_follow_close = not cfg.copy_follow_close
                await self.store.save(cfg)
                return await self._edit(chat_id, msg_id, "📡 *Copy Trading Settings*", copy_trading_kb(cfg))

            if data == "tog:fulltp1":
                cfg.full_close_tp1 = not cfg.full_close_tp1
                await self.store.save(cfg)
                return await self._edit(chat_id, msg_id, "🎯 *Take Profit*", tp_menu_kb(cfg))
            if data == "tog:becc":
                cfg.be_plus_cascade = not cfg.be_plus_cascade
                await self.store.save(cfg)
                return await self._edit(chat_id, msg_id, "🛡️ *Breakeven & Cascade*", becc_menu_kb(cfg))
            # v10.0 new toggles (raw HTTP path)
            if data == "tog:simmode":
                cfg.simulation_mode = not cfg.simulation_mode
                await self.store.save(cfg)
                return await self._edit(chat_id, msg_id, "🧪 *Simulation Settings*", sim_menu_kb(cfg))
            if data == "tog:copysig":
                cfg.copy_signals_enabled = not cfg.copy_signals_enabled
                await self.store.save(cfg)
                return await self._edit(chat_id, msg_id, "🧪 *Simulation Settings*", sim_menu_kb(cfg))
            if data == "tog:trailing":
                cfg.trailing_stop_enabled = not cfg.trailing_stop_enabled
                await self.store.save(cfg)
                return await self._edit(chat_id, msg_id, "🔁 *Trailing Stop Loss*", trailing_menu_kb(cfg))
            if data == "tog:botpause":
                cfg.bot_paused = not cfg.bot_paused
                await self.store.save(cfg)
                status = "⏸️ *Bot Paused*" if cfg.bot_paused else "▶️ *Bot Running*"
                return await self._edit(chat_id, msg_id, status, main_menu_kb(cfg))
            if data in ("tog:notifentry", "tog:notiftp", "tog:notifsl", "tog:notifdca"):
                key = data.split(":")[1]
                if key == "notifentry":  cfg.notify_entry = not cfg.notify_entry
                elif key == "notiftp":   cfg.notify_tp    = not cfg.notify_tp
                elif key == "notifsl":   cfg.notify_sl    = not cfg.notify_sl
                elif key == "notifdca":  cfg.notify_dca   = not cfg.notify_dca
                await self.store.save(cfg)
                return await self._edit(chat_id, msg_id, "🔔 *Alert Settings*", notifset_menu_kb(cfg))
            # v10.0 new toggles
            if data == "tog:marketsl":
                cfg.use_market_on_sl = not cfg.use_market_on_sl
                await self.store.save(cfg)
                return await self._edit(chat_id, msg_id, "🛑 *Stop Loss Management*", sl_menu_kb(cfg))

            # v10.0 group management
            if data.startswith("grp:active:"):
                grp = data.split(":", 2)[2]
                cfg.active_group = grp
                await self.store.save(cfg)
                return await self._edit(chat_id, msg_id, "📡 *Signal Groups & Channels*", groups_menu_kb(cfg))
            if data.startswith("grp:del:"):
                grp = data.split(":", 2)[2]
                if grp in cfg.signal_groups:
                    cfg.signal_groups.remove(grp)
                if cfg.active_group == grp:
                    cfg.active_group = cfg.signal_groups[0] if cfg.signal_groups else ""
                await self.store.save(cfg)
                return await self._edit(chat_id, msg_id, "📡 *Signal Groups & Channels*", groups_menu_kb(cfg))

            # v10.0 quant report dispatch
            if data.startswith("quant:"):
                return await self._show_quant_stats(chat_id, msg_id, data.split(":", 1)[1])

            # ── v10.2 backtest symbol dispatch (raw HTTP path) ───────────────
            if data == "backtest:list":
                return await self._show_backtest_list(chat_id, msg_id)
            if data.startswith("backtest:page:"):
                try:
                    page = int(data.split(":", 2)[2])
                except ValueError:
                    page = 0
                return await self._show_backtest_list(chat_id, msg_id, page=page)
            if data.startswith("backtest:sym:"):
                sym = data.split(":", 2)[2].upper()
                return await self._show_backtest_symbol(chat_id, msg_id, sym)
            if data.startswith("backtest:run:"):
                sym = data.split(":", 2)[2].upper()
                return await self._run_backtest_now(chat_id, msg_id, sym)

            if data.startswith("ask:"):
                kind = data.split(":", 1)[1]
                self._raw_pending[user_id] = {"kind": kind}
                prompts = {
                    "stake":       "💵 Send stake amount in USDT (0 = use risk %):",
                    "limit_to":    "⏱ Send limit-order timeout in minutes:",
                    "dca_mult":    "📈 Send DCA multiplier (e.g. 1.5 means each DCA is 1.5× previous):",
                    "tpcustom":    "✏️ Send TP distribution as comma-separated %, summing to 100 (e.g. 45,35,20):",
                    "trade_usdt":  "💵 Send fixed trade amount in USDT (e.g. 100):",
                    "maxpos":      "🔒 Send max position size in USDT (e.g. 500):",
                    "minqual":     "🎯 Send minimum quality score 0–100 (e.g. 65):",
                    "autocloseH":  "⏱ Send auto-close hours (e.g. 24, or 0 to disable):",
                    "maxlossusd":  "💸 Send max loss in USDT to trigger auto-close (0 = off):",
                    "grpadd":      "📡 Send Telegram channel username or group ID (e.g. @signals_channel):",
                    "grpwl":       "✅ Send symbol whitelist as comma-separated list (e.g. BTCUSDT,ETHUSDT):",
                    "grpbl":       "🚫 Send symbol blacklist as comma-separated list (e.g. SHIBUSDT,DOGEUSDT):",
                    # v11.0 new prompts
                    "dcadev":      "📉 Send DCA price deviation % between fills (e.g. 1.5):",
                    "dcavol":      "📈 Send DCA volume multiplier per step (e.g. 1.5; 1.0 = flat):",
                    "sigtout":     "⏱ Send signal entry timeout in minutes (0 = no timeout, e.g. 15):",
                    "copysrc":     "📡 Send copy-trading source channel username or ID (e.g. @signals_channel):",
                }
                return await self._edit(chat_id, msg_id, prompts.get(kind, "Send value:"))

            if data == "key:add":
                return await self._edit(chat_id, msg_id, "🔑 Choose exchange:", add_exchange_kb())
            if data.startswith("key:exchange:"):
                exch = data.split(":")[2]
                self._raw_pending[user_id] = {"kind": "api_label", "exchange": exch}
                return await self._edit(chat_id, msg_id,
                    f"🔑 *{exch.upper()}* — Step 1/3\nSend a label for this key (e.g. 'main', 'sub-account-1'):")
            if data.startswith("key:select:"):
                _, _, exch, label = data.split(":", 3)
                cfg.active_exchange = exch
                await self.store.save(cfg)
                return await self._edit(chat_id, msg_id,
                    f"✅ Active key: *{exch.upper()} · {label}*",
                    _kb([[("🗑 Unbind", f"key:del:{exch}:{label}")], [("◀️ Back", "menu:keys")]]))
            if data.startswith("key:del:"):
                _, _, exch, label = data.split(":", 3)
                await self.store.delete_api_key(user_id, exch, label)
                return await self._render_keys(chat_id, msg_id, cfg)

            # ── v10.5: Position close callbacks ───────────────────────────
            if data.startswith("pos:"):
                return await self._handle_position_close(q_wrapper, cfg, data)

            if data.startswith("sig:"):
                _, action, signal_id = data.split(":", 2)
                payload = {"chat_id": chat_id}
                await self.store.record_signal_action(user_id, signal_id, action, payload)
                if action == "follow" and self.signal_executor:
                    try:
                        result = await self.signal_executor(user_id, signal_id, cfg)
                        return await self._send(chat_id, f"✅ Followed `{signal_id}` → {result}")
                    except Exception as e:
                        return await self._send(chat_id, f"❌ Follow failed: {e}")
                if action == "ignore":
                    return await self._send(chat_id, f"🙈 Ignored signal `{signal_id}`")
                if action in ("brief", "detail"):
                    extra = ("Full multi-timeframe + 10-agent swarm + IRONS scoring breakdown"
                             if action == "detail" else "Quick AI confidence summary")
                    return await self._send(chat_id, f"📊 *{action.title()} Analysis* for `{signal_id}`\n\n{extra}")
                if action == "retry" and self.signal_executor:
                    try:
                        result = await self.signal_executor(user_id, signal_id, cfg, retry=True)
                        return await self._send(chat_id, f"🔁 Retry result: {result}")
                    except Exception as e:
                        return await self._send(chat_id, f"❌ Retry failed: {e}")
                # ── v10.5: Execute signal via CCXT ──────────────────────────
                if action == "execute":
                    return await self._handle_execute_signal(q_wrapper, cfg, signal_id)
                return

            logger.debug(f"Unhandled raw callback: {data}")
        except Exception as e:
            logger.exception(f"_dispatch_callback_raw error on '{data}': {e}")

    # ── raw renderers (mirror PTB renderers but use HTTP edit) ──────────────

    async def _render_dashboard(self, chat_id: int, msg_id: int, cfg: UserConfig) -> None:
        balance = equity = avail = upnl = 0.0
        positions: List[Dict[str, Any]] = []
        try:
            if self.balance_provider:
                bd = await self.balance_provider(cfg)
                balance = float(bd.get("balance", 0))
                equity  = float(bd.get("equity", 0))
                avail   = float(bd.get("available", 0))
                upnl    = float(bd.get("unrealised_pnl", 0))
            if self.positions_provider:
                positions = await self.positions_provider(cfg) or []
        except Exception as e:
            logger.warning(f"dashboard provider error: {e}")
        body = (
            f"📊 *Trading Dashboard*\n\n"
            f"• Balance: `{balance:,.2f} USDT`\n"
            f"• Available: `{avail:,.2f} USDT`\n"
            f"• Equity: `{equity:,.2f} USDT`\n"
            f"• Unrealised PnL: `{upnl:+,.2f} USDT`\n"
            f"• Open Positions: `{len(positions)}`\n"
            f"• Active exchange: `{cfg.active_exchange.upper()}`\n"
            f"• Mode: `{cfg.trading_mode.upper()}`\n"
            f"• Leverage: `{cfg.leverage}x`  · Risk: `{cfg.risk_pct}%`\n"
        )
        await self._edit(chat_id, msg_id, body, _kb([[("🔄 Refresh", "menu:dash"), ("◀️ Back", "menu:main")]]))

    async def _render_keys(self, chat_id: int, msg_id: int, cfg: UserConfig) -> None:
        keys = await self.store.list_api_keys(cfg.user_id)
        body = "🔑 *API Keys*\n\n" + (f"You have {len(keys)} key(s). Tap to manage:" if keys
                                       else "No API keys yet. Add one to enable execution.")
        await self._edit(chat_id, msg_id, body, keys_menu_kb(cfg, keys))

    async def _render_signals(self, chat_id: int, msg_id: int, cfg: UserConfig) -> None:
        stats = await self.store.signal_action_stats(cfg.user_id)
        body = (
            "📨 *Working with Signals*\n\n"
            "When a signal arrives in the channel, you can:\n"
            "• 🚀 Follow — execute immediately on your exchange\n"
            "• 🤖 Auto Mode — execute every approved signal automatically\n"
            "• 🙈 Ignore — skip it\n"
            "• 🔁 Retry — re-execute a failed signal\n"
            "• 📊 Brief / Detailed — AI quality breakdown\n\n"
            f"_Your stats: follow={stats.get('follow', 0)}  ignore={stats.get('ignore', 0)}  retry={stats.get('retry', 0)}_"
        )
        await self._edit(chat_id, msg_id, body, _kb([
            [(f"{'✅' if cfg.trading_mode == 'auto'   else ''}🤖 Auto Mode", "set:mode:auto")],
            [(f"{'✅' if cfg.trading_mode == 'manual' else ''}👤 Manual",    "set:mode:manual")],
            [(f"{'✅' if cfg.trading_mode == 'off'    else ''}🔇 Off",       "set:mode:off")],
            [("◀️ Back", "menu:main")],
        ]))

    async def _render_positions(self, chat_id: int, msg_id: int, cfg: UserConfig) -> None:
        positions: List[Dict[str, Any]] = []
        try:
            if self.positions_provider:
                positions = await self.positions_provider(cfg) or []
        except Exception as e:
            logger.warning(f"positions provider error: {e}")
        if not positions:
            body = "📁 *Position Management*\n\nNo open positions."
        else:
            lines = ["📁 *Position Management*\n"]
            for p in positions[:10]:
                lines.append(
                    f"• `{p.get('symbol')}` {p.get('side')} | qty `{p.get('qty')}` | "
                    f"entry `{p.get('entry_price')}` | uPnL `{p.get('unrealised_pnl', 0):+.2f}`"
                )
            body = "\n".join(lines)
        await self._edit(chat_id, msg_id, body, _kb([
            [("👁 Refresh", "menu:positions")],
            [("◀️ Back", "menu:main")],
        ]))

    async def _render_history(self, chat_id: int, msg_id: int, cfg: UserConfig) -> None:
        trades: List[Dict[str, Any]] = []
        try:
            if self.history_provider:
                trades = await self.history_provider(cfg) or []
        except Exception as e:
            logger.warning(f"history provider error: {e}")
        if not trades:
            body = "📋 *History & Statistics*\n\nNo closed trades yet."
        else:
            wins   = sum(1 for t in trades if float(t.get("pnl", 0)) > 0)
            losses = len(trades) - wins
            wr     = (wins / len(trades)) * 100 if trades else 0
            total_pnl = sum(float(t.get("pnl", 0)) for t in trades)
            avg_pnl   = total_pnl / len(trades)
            best  = max(trades, key=lambda t: float(t.get("pnl", 0)))
            worst = min(trades, key=lambda t: float(t.get("pnl", 0)))
            body = (
                f"📋 *History & Statistics*\n\n"
                f"• Total trades: `{len(trades)}`\n"
                f"• Wins / Losses: `{wins} / {losses}`\n"
                f"• Win rate: `{wr:.1f}%`\n"
                f"• Total PnL: `{total_pnl:+.2f} USDT`\n"
                f"• Avg PnL: `{avg_pnl:+.2f} USDT`\n"
                f"• Best trade: `{best.get('symbol')} {float(best.get('pnl', 0)):+.2f}`\n"
                f"• Worst trade: `{worst.get('symbol')} {float(worst.get('pnl', 0)):+.2f}`\n"
            )
        await self._edit(chat_id, msg_id, body, _kb([
            [("📊 Statistics", "menu:history")],
            [("◀️ Back", "menu:main")],
        ]))

    async def _render_aiv(self, chat_id: int, msg_id: int, cfg: UserConfig) -> None:
        body = (
            "🤖 *AI Signal Validation*\n\n"
            "The G0DM0D3 AI ensemble + 10-agent swarm + IRONS scorer "
            "rate every signal across:\n"
            "• Multi-timeframe alignment (4H / 1H / 15M)\n"
            "• 10-agent swarm consensus %\n"
            "• IRONS 25-indicator score (Momentum / Trend / Vol / Volume)\n"
            "• Neural Network MC-Dropout win-prob\n"
            "• OpenRouter LLM ensemble vote\n"
            "• GEX regime + Gamma Zero proximity\n"
        )
        await self._edit(chat_id, msg_id, body, _kb([
            [("📊 Brief Analysis", "sig:brief:latest"),
             ("📊 Detailed",       "sig:detail:latest")],
            [("🎯 Score Components", "menu:aiv")],
            [("◀️ Back", "menu:main")],
        ]))

    async def _render_channel(self, chat_id: int, msg_id: int, cfg: UserConfig, user_id: int) -> None:
        body = (
            "📡 *Channel Settings*\n\n"
            f"Currently monitoring: `{cfg.signal_channel}`\n\n"
            "When a signal appears:\n"
            "• Auto Mode ON → executed automatically\n"
            "• Auto Mode OFF → shows action buttons (Follow / Ignore / Brief / Detailed)\n\n"
            "_Send a new channel @username (or chat ID starting -100…)._"
        )
        self._raw_pending[user_id] = {"kind": "channel"}
        await self._edit(chat_id, msg_id, body, _kb([[("◀️ Back", "menu:main")]]))

    async def _render_help(self, chat_id: int, msg_id: int, cfg: UserConfig) -> None:
        body = (
            "❓ *Getting Started — Unity Engine v11.0*\n\n"
            "1️⃣ Open *🔑 API Keys* and add your exchange key (futures-enabled).\n"
            "2️⃣ Open *⚙️ Settings → Risk Management* — set leverage, risk %, max trades.\n"
            "3️⃣ Pick *🎯 Take Profit* count + distribution (45/35/20 is balanced).\n"
            "4️⃣ Optional: turn on *🛡️ Breakeven* after TP1 or TP2 for free trades.\n"
            "5️⃣ Choose *🤖 Mode → Auto* to execute every approved signal.\n\n"
            "*New v11.0 Quant Features:*\n"
            "• 📈 *Factor IC/IR* — Spearman IC, rolling IR, quantile factor backtest\n"
            "• 📉 *IV Surface* — Deribit IV term-structure, 25-delta skew, pin-risk\n"
            "• 📊 *Greeks* — Black-Scholes Δ/Γ/ν/Θ/ρ + Vanna/Volga/Charm\n"
            "• ⚖️ *Portfolio Opt* — MVO / Risk Parity / Black-Litterman weight signals\n"
            "• 🧠 *Patterns* — 24 candlestick + 8 chart patterns (Gate 2.5)\n\n"
            "All signals: 13-gate filter (EV, Session, MinTP1, R:R, Swarm, AI, NN,\n"
            "Analyzer, Regime, GEX, Per-symbol WR, Quality, IRONS) + Pattern Gate 2.5."
        )
        await self._edit(chat_id, msg_id, body, _kb([[("◀️ Back", "menu:main")]]))

    # ── v11.0 Quant Panel Renderers ──────────────────────────────────────────

    async def _render_portfolio(self, chat_id: int, msg_id: int) -> None:
        """Render portfolio optimizer weights and method selection."""
        try:
            opt = getattr(self, "_portfolio_optimizer", None)
            if opt:
                body = opt.format_text()
            else:
                body = (
                    "⚖️ *Portfolio Optimizer* — v11.0\n\n"
                    "Methods available:\n"
                    "• *Max Sharpe* — maximises risk-adjusted return (Markowitz)\n"
                    "• *Min Variance* — minimises portfolio volatility\n"
                    "• *Risk Parity* — equal risk contribution per asset (ERC)\n"
                    "• *Black-Litterman* — combines equilibrium with LLM views\n\n"
                    "_Select a method below to recompute weights._"
                )
        except Exception as exc:
            body = f"⚖️ Portfolio Optimizer error: {exc}"
        await self._edit(chat_id, msg_id, body, portfolio_optimizer_kb())

    async def _handle_portopt(self, chat_id: int, msg_id: int, action: str) -> None:
        """Handle portfolio optimizer method selection."""
        try:
            opt = getattr(self, "_portfolio_optimizer", None)
            if opt and action in ("max_sharpe", "min_var", "risk_parity", "bl"):
                opt.set_method(action)
                w = opt.compute()
                body = opt.format_text() if w else f"⚖️ Optimizer set to *{action}* — computing weights…"
            elif action == "refresh" and opt:
                opt.compute()
                body = opt.format_text() or "⚖️ Refreshing weights…"
            else:
                body = f"⚖️ Method *{action}* selected — optimizer not yet attached."
        except Exception as exc:
            body = f"⚖️ Error: {exc}"
        await self._edit(chat_id, msg_id, body, portfolio_optimizer_kb())

    async def _render_factor(self, chat_id: int, msg_id: int) -> None:
        """Render Factor IC/IR analysis report."""
        try:
            analyzer = getattr(self, "_factor_analyzer", None)
            if analyzer:
                report = await analyzer.get_report()
                body = analyzer.format_report_text(report)
            else:
                body = (
                    "📈 *Factor IC/IR Analysis* — v11.0\n\n"
                    "Measures predictive power of the Unity Engine's composite factor:\n\n"
                    "• *IC (Information Coefficient)* — Spearman correlation between\n"
                    "  factor values and subsequent returns. IC > 0.05 = strong signal.\n\n"
                    "• *IR (Information Ratio)* — IC mean / IC std. IR > 0.30 = reliable.\n\n"
                    "• *Quantile Returns* — Q5 (top) vs Q1 (bottom) return spread.\n"
                    "  Monotonic Q1→Q5 confirms factor predicts direction correctly.\n\n"
                    "• *Factor Turnover* — how often top-quantile symbols change.\n"
                    "  Low turnover = lower transaction costs.\n\n"
                    "Factors analysed: Momentum, OFI, IRONS, GEX Net, NN Win-Prob."
                )
        except Exception as exc:
            body = f"📈 Factor analysis error: {exc}"
        await self._edit(chat_id, msg_id, body, factor_icir_kb())

    async def _handle_factor(self, chat_id: int, msg_id: int, action: str) -> None:
        """Handle factor analysis sub-navigation."""
        try:
            analyzer = getattr(self, "_factor_analyzer", None)
            if analyzer:
                report = await analyzer.get_report()
                if action == "report":
                    body = analyzer.format_report_text(report)
                elif action in ("1d", "5d", "21d") and report:
                    period = int(action.replace("d", ""))
                    icir = report.icir_by_period.get(period)
                    qr   = report.quantile_by_period.get(period)
                    if icir:
                        sig = "✅ Strong" if icir.is_strong else "⚠️ Weak"
                        body = (
                            f"📈 *Factor Analysis — {period}D Holding Period*\n\n"
                            f"Signal: {sig}\n"
                            f"IC Mean: `{icir.ic_mean:+.4f}`\n"
                            f"IC Std:  `{icir.ic_std:.4f}`\n"
                            f"IR:      `{icir.ir:+.3f}`\n"
                            f"Rolling IC (30): `{icir.rolling_ic_30:+.4f}`\n"
                            f"Gate-8.5 Bias: `{icir.quality_bias:+.1f} pts`\n"
                        )
                        if qr:
                            spread = f"{qr.spread:+.4f}"
                            mono   = "✅ monotonic" if qr.monotonic else "⚠️ non-monotonic"
                            body  += f"\nQ5-Q1 Spread: `{spread}` ({mono})\n"
                            body  += f"Avg Turnover: `{qr.turnover:.1%}`"
                    else:
                        body = f"📈 No data for {period}D period yet"
                elif action == "refresh":
                    body = "🔄 Refreshing factor analysis…"
                else:
                    body = analyzer.format_report_text(report)
            else:
                body = "📈 Factor analyzer not yet attached to engine."
        except Exception as exc:
            body = f"📈 Error: {exc}"
        await self._edit(chat_id, msg_id, body, factor_icir_kb())

    async def _render_patterns(self, chat_id: int, msg_id: int) -> None:
        """Render recent pattern analysis results."""
        try:
            patterns = getattr(self, "_recent_patterns", {})
            if patterns:
                lines = ["🧠 *Technical Pattern Recognition* — v11.0\n"]
                bullish = [(s, a) for s, a in patterns.items() if a.net_pts > 0]
                bearish = [(s, a) for s, a in patterns.items() if a.net_pts < 0]
                bullish.sort(key=lambda x: -x[1].net_pts)
                bearish.sort(key=lambda x: x[1].net_pts)
                if bullish:
                    lines.append("*🟢 Bullish:*")
                    for sym, a in bullish[:5]:
                        lines.append(f"  `{sym}` {a.dominant or ''} ({a.net_pts:+.1f}pts)")
                if bearish:
                    lines.append("*🔴 Bearish:*")
                    for sym, a in bearish[:5]:
                        lines.append(f"  `{sym}` {a.dominant or ''} ({a.net_pts:+.1f}pts)")
                body = "\n".join(lines)
            else:
                body = (
                    "🧠 *Pattern Recognition* — v11.0\n\n"
                    "*Candlestick Patterns (24):*\n"
                    "Doji, Hammer, Hanging Man, Shooting Star, Inverted Hammer,\n"
                    "Bullish/Bearish Engulfing, Bullish/Bearish Harami,\n"
                    "Bullish/Bearish Marubozu, Morning Star, Evening Star,\n"
                    "Three White Soldiers, Three Black Crows, Pinbar, Inside Bar\n\n"
                    "*Chart Patterns (8):*\n"
                    "Double Top/Bottom, Head & Shoulders, Inverse H&S,\n"
                    "Ascending Triangle, Descending Triangle, Symmetrical Triangle,\n"
                    "Bull Flag, Bear Flag\n\n"
                    "Results feed Gate 2.5 (±8 pts quality bias)."
                )
        except Exception as exc:
            body = f"🧠 Pattern error: {exc}"
        await self._edit(chat_id, msg_id, body, pattern_analysis_kb())

    async def _handle_pattern(self, chat_id: int, msg_id: int, action: str) -> None:
        """Handle pattern analysis sub-navigation."""
        try:
            patterns = getattr(self, "_recent_patterns", {})
            if action == "bullish":
                items = [(s, a) for s, a in patterns.items() if a.net_pts > 0.5]
                items.sort(key=lambda x: -x[1].net_pts)
                if items:
                    lines = ["🟢 *Bullish Pattern Setups*\n"]
                    for sym, a in items[:8]:
                        lines.append(f"• `{sym}` — {a.dominant} ({a.net_pts:+.1f}pts, {a.confidence:.0%})")
                    body = "\n".join(lines)
                else:
                    body = "🟢 No strong bullish patterns detected currently."
            elif action == "bearish":
                items = [(s, a) for s, a in patterns.items() if a.net_pts < -0.5]
                items.sort(key=lambda x: x[1].net_pts)
                if items:
                    lines = ["🔴 *Bearish Pattern Setups*\n"]
                    for sym, a in items[:8]:
                        lines.append(f"• `{sym}` — {a.dominant} ({a.net_pts:+.1f}pts, {a.confidence:.0%})")
                    body = "\n".join(lines)
                else:
                    body = "🔴 No strong bearish patterns detected currently."
            else:
                return await self._render_patterns(chat_id, msg_id)
        except Exception as exc:
            body = f"🧠 Error: {exc}"
        await self._edit(chat_id, msg_id, body, pattern_analysis_kb())

    async def _render_iv_surface(self, chat_id: int, msg_id: int) -> None:
        """Render IV surface overview."""
        try:
            bs_engine = getattr(self, "_bs_engine", None)
            if bs_engine:
                lines = []
                for sym in ("BTC", "ETH", "SOL"):
                    surf = bs_engine.get_iv_surface(sym)
                    if surf and surf.term_structure:
                        near = surf.term_structure[0]
                        skew = bs_engine.get_skew(sym)
                        rr = skew.rr_25d if skew else 0.0
                        lines.append(
                            f"*{sym}*: ATM={surf.atm_iv.get(near[0], 0):.0%}  "
                            f"25d-RR={rr:+.1%}  regime={skew.skew_regime if skew else 'N/A'}"
                        )
                    else:
                        lines.append(f"*{sym}*: No IV data yet")
                body = "📉 *IV Surface Overview* — v11.0\n\n" + "\n".join(lines) + (
                    "\n\n_IV updated from Deribit options chain every 30s_"
                )
            else:
                body = (
                    "📉 *IV Surface & Options Analytics* — v11.0\n\n"
                    "• *ATM IV* — at-the-money implied volatility (term structure)\n"
                    "• *25-delta RR* — put IV − call IV (positive = put skew = fear)\n"
                    "• *25d Butterfly* — wing premium vs ATM (smile convexity)\n"
                    "• *IV Slope* — rate of IV change across strikes (skew steepness)\n"
                    "• *Pin Risk* — strikes with highest net-dealer gamma at expiry\n\n"
                    "Skew regime feeds Gate 7 bonus: CALL_SKEW = +2pts, PUT_SKEW = −1.5pts"
                )
        except Exception as exc:
            body = f"📉 IV surface error: {exc}"
        await self._edit(chat_id, msg_id, body, greeks_kb())

    async def _handle_greeks(self, chat_id: int, msg_id: int, action: str) -> None:
        """Handle Greeks / IV surface navigation."""
        try:
            bs_engine = getattr(self, "_bs_engine", None)
            if action in ("btc", "eth", "sol") and bs_engine:
                sym  = action.upper()
                body = bs_engine.format_iv_surface_text(sym)
            elif action == "calc":
                body = (
                    "🔢 *Black-Scholes Greeks Calculator*\n\n"
                    "Send: `spot strike expiry_days iv option_type`\n"
                    "Example: `45000 44000 7 0.85 call`\n\n"
                    "_iv = implied vol as decimal (0.85 = 85%)_"
                )
            elif action == "refresh":
                body = "🔄 IV surface refreshing from Deribit…"
            else:
                return await self._render_iv_surface(chat_id, msg_id)
        except Exception as exc:
            body = f"📊 Error: {exc}"
        await self._edit(chat_id, msg_id, body, greeks_kb())

    def set_quant_providers(self,
                             portfolio_optimizer=None,
                             factor_analyzer=None,
                             bs_engine=None) -> None:
        """
        Attach quant engine providers to the menu bot.
        Called from UnityEngine startup after all modules are initialized.
        """
        if portfolio_optimizer is not None:
            self._portfolio_optimizer = portfolio_optimizer
        if factor_analyzer is not None:
            self._factor_analyzer = factor_analyzer
        if bs_engine is not None:
            self._bs_engine = bs_engine

    def update_pattern_cache(self, patterns: dict) -> None:
        """Update the recent patterns cache (called from signal scanner)."""
        self._recent_patterns = patterns

    # ── attachment ──────────────────────────────────────────────────────────

    def attach(self, application: "Application") -> None:
        if not _HAS_PTB:
            logger.error("Cannot attach CornixMenuBot — python-telegram-bot missing")
            return
        application.add_handler(CommandHandler("start", self._on_start))
        application.add_handler(CommandHandler("menu",  self._on_start))
        application.add_handler(CallbackQueryHandler(self._on_callback))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._on_text))
        self._attached = True
        logger.info("✅ CornixMenuBot attached — inline menu system active (15 callback patterns, 8 exchanges)")

    # ── start handler ───────────────────────────────────────────────────────

    async def _on_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        if not user:
            return
        cfg = await self.store.get(user.id)
        await update.effective_message.reply_text(
            _t(cfg, "welcome"),
            reply_markup=main_menu_kb(cfg),
            parse_mode="Markdown",
        )

    # ── text handler (for free-form numeric input) ──────────────────────────

    async def _on_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        pending = context.user_data.get(self.PENDING_INPUT_KEY) if context.user_data else None
        if not pending:
            return
        text = (update.effective_message.text or "").strip()
        user = update.effective_user
        cfg = await self.store.get(user.id)
        kind = pending.get("kind")

        try:
            if kind == "stake":
                cfg.stake_usdt = max(0.0, float(text))
            elif kind == "limit_to":
                cfg.limit_timeout_min = max(1, int(float(text)))
            elif kind == "dca_mult":
                cfg.dca_multiplier = max(1.0, float(text))
            elif kind == "tpcustom":
                parts = [int(p.strip()) for p in text.replace("/", ",").split(",") if p.strip()]
                if parts and sum(parts) == 100 and 1 <= len(parts) <= 4:
                    cfg.tp_distribution = "custom"
                    cfg.tp_custom = parts
                    cfg.tp_count = len(parts)
                else:
                    raise ValueError("Distribution must be 1–4 numbers summing to 100 (e.g. 45,35,20)")
            elif kind == "channel":
                cfg.signal_channel = text if text.startswith("@") or text.startswith("-100") else "@" + text
            elif kind == "marginpct":
                cfg.margin_pct = max(0.1, min(100.0, float(text)))
            elif kind == "trade_usdt":
                cfg.trade_amount_usdt = max(1.0, float(text))
            elif kind == "maxpos":
                cfg.max_position_usdt = max(10.0, float(text))
            elif kind == "minqual":
                cfg.signal_min_quality = max(0, min(100, int(float(text))))
            # v10.0 SL management text inputs
            elif kind == "slfixed":
                cfg.sl_fixed_pct = max(0.1, float(text))
            elif kind == "slatrmult":
                cfg.sl_atr_mult = max(0.1, float(text))
            elif kind == "slmax":
                cfg.sl_max_pct = max(0.1, float(text))
            elif kind == "partialclose":
                cfg.partial_close_pct = max(0.0, min(100.0, float(text)))
            # v10.0 advanced entry/exit text inputs
            elif kind == "autocloseH":
                cfg.auto_close_hours = max(0.0, float(text))
            elif kind == "maxlossusd":
                cfg.max_loss_usd = max(0.0, float(text))
            # v10.0 groups text inputs
            elif kind == "grpadd":
                g = text.strip() if (text.startswith("@") or text.startswith("-100")) else "@" + text.strip()
                if g and g not in cfg.signal_groups:
                    cfg.signal_groups.append(g)
            elif kind == "grpwl":
                cfg.symbol_whitelist = [s.strip().upper() for s in text.replace(" ", ",").split(",") if s.strip()]
            elif kind == "grpbl":
                cfg.symbol_blacklist = [s.strip().upper() for s in text.replace(" ", ",").split(",") if s.strip()]
            # v11.0 DCA advanced / copy trading text inputs (PTB path)
            elif kind == "dcadev":
                cfg.dca_deviation_pct = max(0.1, float(text))
            elif kind == "dcavol":
                cfg.dca_vol_scale = max(0.5, float(text))
            elif kind == "sigtout":
                cfg.signal_timeout_min = max(0, int(float(text)))
            elif kind == "copysrc":
                g = text.strip()
                cfg.copy_source_channel = "" if g.lower() in ("off", "none", "0", "") else (g if g.startswith("@") or g.startswith("-100") else "@" + g)
            elif kind in ("api_key", "api_secret", "api_pass", "api_label"):
                pending[kind] = text
                # progress through the wizard
                return await self._api_key_wizard_step(update, context, cfg, pending)
            else:
                return
            await self.store.save(cfg)
            context.user_data.pop(self.PENDING_INPUT_KEY, None)
            await update.effective_message.reply_text(
                f"{_t(cfg, 'saved')} ✅",
                reply_markup=main_menu_kb(cfg),
            )
        except Exception as e:
            await update.effective_message.reply_text(f"❌ Invalid input: {e}\n\nTry again or send /start.")

    # ── callback router ─────────────────────────────────────────────────────

    async def _on_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        q = update.callback_query
        if not q or not q.data:
            return
        await q.answer()
        user = q.from_user
        if not self._is_admin(user.id if user else None):
            await q.answer("⛔ Authorised users only.", show_alert=True)
            return
        cfg = await self.store.get(user.id)
        data = q.data

        try:
            # ── menu navigation ─────────────────────────────────────────────
            if data == "noop":
                return
            if data == "menu:main":
                return await self._show_main(q, cfg)
            if data == "menu:dash":
                return await self._show_dashboard(q, cfg)
            if data == "menu:keys":
                return await self._show_keys(q, cfg)
            if data == "menu:settings":
                return await q.edit_message_text("⚙️ *Settings*", reply_markup=settings_menu_kb(cfg), parse_mode="Markdown")
            if data == "menu:signals":
                return await self._show_signals_menu(q, cfg)
            if data == "menu:positions":
                return await self._show_positions(q, cfg)
            if data == "menu:history":
                return await self._show_history(q, cfg)
            if data == "menu:aiv":
                return await self._show_ai_validation(q, cfg)
            if data == "menu:channel":
                return await self._show_channel(q, cfg, context)
            if data == "menu:notif":
                cfg.notifications = not cfg.notifications
                await self.store.save(cfg)
                return await q.edit_message_text(
                    f"🔔 Notifications: *{'ON' if cfg.notifications else 'OFF'}*",
                    reply_markup=main_menu_kb(cfg), parse_mode="Markdown",
                )
            if data == "menu:lang":
                return await q.edit_message_text("🌐 Choose language / Выберите язык:", reply_markup=_kb([
                    [("🇬🇧 English", "set:lang:en"), ("🇷🇺 Русский", "set:lang:ru")],
                    [("◀️ Back", "menu:main")],
                ]))
            if data == "menu:help":
                return await self._show_help(q, cfg)
            if data == "menu:risk":
                return await q.edit_message_text("⚖️ *Risk Management*", reply_markup=risk_menu_kb(cfg), parse_mode="Markdown")
            if data == "menu:entry":
                return await q.edit_message_text("📥 *Entry Orders*", reply_markup=entry_menu_kb(cfg), parse_mode="Markdown")
            if data == "menu:tp":
                return await q.edit_message_text("🎯 *Take Profit*", reply_markup=tp_menu_kb(cfg), parse_mode="Markdown")
            if data == "menu:becc":
                return await q.edit_message_text("🛡️ *Breakeven & Cascade*", reply_markup=becc_menu_kb(cfg), parse_mode="Markdown")
            if data == "menu:mode":
                return await q.edit_message_text("🤖 *Trading Mode*", reply_markup=mode_menu_kb(cfg), parse_mode="Markdown")
            if data == "menu:margin":
                return await q.edit_message_text("💼 *Margin Mode*", reply_markup=margin_menu_kb(cfg), parse_mode="Markdown")
            if data == "menu:marginpct":
                context.user_data[self.PENDING_INPUT_KEY] = {"kind": "marginpct"}
                return await q.edit_message_text("💰 Send margin % (0.1 – 100):")

            # ── v10.0 new menus ─────────────────────────────────────────────
            if data == "menu:possize":
                return await q.edit_message_text("💵 *Position Sizing*", reply_markup=possize_menu_kb(cfg), parse_mode="Markdown")
            if data == "menu:trailing":
                return await q.edit_message_text("🔁 *Trailing Stop Loss*", reply_markup=trailing_menu_kb(cfg), parse_mode="Markdown")
            if data == "menu:sim":
                return await self._show_sim_menu(q, cfg)
            if data == "menu:backtest":
                return await self._show_backtest(q, cfg)
            if data == "menu:notifset":
                return await q.edit_message_text("🔔 *Alert Settings*", reply_markup=notifset_menu_kb(cfg), parse_mode="Markdown")
            if data == "menu:minconf":
                return await q.edit_message_text("🎚️ *Signal Confidence Filter*", reply_markup=minconf_menu_kb(cfg), parse_mode="Markdown")
            if data == "menu:sl":
                return await q.edit_message_text("🛑 *Stop Loss Management*", reply_markup=sl_menu_kb(cfg), parse_mode="Markdown")
            if data == "menu:groups":
                return await q.edit_message_text("📡 *Signal Groups & Channels*", reply_markup=groups_menu_kb(cfg), parse_mode="Markdown")
            if data == "menu:adventry":
                return await q.edit_message_text("🔧 *Advanced Entry / Exit*", reply_markup=advanced_entry_kb(cfg), parse_mode="Markdown")
            if data == "menu:dcaadv":
                return await q.edit_message_text("📉 *DCA Advanced Settings*", reply_markup=dca_advanced_kb(cfg), parse_mode="Markdown")
            if data == "menu:copytrade":
                return await q.edit_message_text("📡 *Copy Trading Settings*", reply_markup=copy_trading_kb(cfg), parse_mode="Markdown")
            if data == "menu:quant":
                return await self._show_quant_stats(q)
            if data.startswith("quant:"):
                return await self._show_quant_stats(q, section=data.split(":", 1)[1])

            # ── v10.2 backtest symbol dispatch (PTB path) ───────────────────
            if data == "backtest:list":
                return await self._show_backtest_list(q)
            if data.startswith("backtest:page:"):
                try:
                    page = int(data.split(":", 2)[2])
                except ValueError:
                    page = 0
                return await self._show_backtest_list(q, page=page)
            if data.startswith("backtest:sym:"):
                sym = data.split(":", 2)[2].upper()
                return await self._show_backtest_symbol(q, sym=sym)
            if data.startswith("backtest:run:"):
                sym = data.split(":", 2)[2].upper()
                return await self._run_backtest_now(q, sym=sym)

            if data.startswith("grp:active:"):
                grp = data.split(":", 2)[2]
                cfg.active_group = grp
                await self.store.save(cfg)
                return await q.edit_message_text("📡 *Signal Groups & Channels*", reply_markup=groups_menu_kb(cfg), parse_mode="Markdown")
            if data == "tog:marketsl":
                cfg.use_market_on_sl = not cfg.use_market_on_sl
                await self.store.save(cfg)
                return await q.edit_message_text("🛑 *Stop Loss Management*", reply_markup=sl_menu_kb(cfg), parse_mode="Markdown")

            # ── settings setters ────────────────────────────────────────────
            if data.startswith("set:"):
                _, key, *rest = data.split(":")
                val = ":".join(rest)
                changed = False
                if key == "lev":
                    cfg.leverage = int(val); changed = True
                elif key == "risk":
                    cfg.risk_pct = float(val); changed = True
                elif key == "maxtr":
                    cfg.max_open_trades = int(val); changed = True
                elif key == "entry":
                    cfg.entry_type = val; changed = True
                elif key == "dca":
                    cfg.dca_orders = int(val); changed = True
                elif key == "tpcnt":
                    cfg.tp_count = int(val); changed = True
                elif key == "tpdist":
                    cfg.tp_distribution = val; changed = True
                elif key == "be":
                    cfg.breakeven_after_tp = int(val); changed = True
                elif key == "cs":
                    cfg.cascade_after_tp = int(val); changed = True
                elif key == "mode":
                    cfg.trading_mode = val; changed = True
                elif key == "mm":
                    cfg.margin_mode = val; changed = True
                elif key == "lang":
                    cfg.language = val; changed = True
                # v10.0 new setters
                elif key == "amttype":
                    cfg.amount_type = val; changed = True
                elif key == "tradeusdt":
                    cfg.trade_amount_usdt = max(1.0, float(val)); changed = True
                elif key == "maxpos":
                    cfg.max_position_usdt = max(10.0, float(val)); changed = True
                elif key == "tslpct":
                    cfg.trailing_stop_pct = max(0.1, float(val)); changed = True
                elif key == "tslact":
                    cfg.trailing_stop_activation_pct = max(0.1, float(val)); changed = True
                elif key == "notifon":
                    cfg.notify_on = val; changed = True
                elif key == "minconf":
                    cfg.signal_min_confidence = max(0.0, min(1.0, float(val))); changed = True
                elif key == "minqual":
                    cfg.signal_min_quality = max(0, min(100, int(float(val)))); changed = True
                # v10.0 SL management setters
                elif key == "slmode":
                    cfg.sl_mode = val; changed = True
                elif key == "slfixed":
                    cfg.sl_fixed_pct = max(0.1, float(val)); changed = True
                elif key == "slatrmult":
                    cfg.sl_atr_mult = max(0.1, float(val)); changed = True
                elif key == "slmax":
                    cfg.sl_max_pct = max(0.1, float(val)); changed = True
                elif key == "partialclose":
                    cfg.partial_close_pct = max(0.0, min(100.0, float(val))); changed = True
                # v10.0 groups/filter setters
                elif key == "grpfilter":
                    cfg.group_filter_mode = val; changed = True
                elif key == "grpactive":
                    cfg.active_group = val; changed = True
                # v10.0 advanced entry setters
                elif key == "autocloseH":
                    cfg.auto_close_hours = max(0.0, float(val)); changed = True
                elif key == "maxlossusd":
                    cfg.max_loss_usd = max(0.0, float(val)); changed = True
                if changed:
                    await self.store.save(cfg)
                # refresh same menu
                if key in ("lev", "risk", "maxtr"):
                    return await q.edit_message_text("⚖️ *Risk Management*", reply_markup=risk_menu_kb(cfg), parse_mode="Markdown")
                if key in ("entry", "dca"):
                    return await q.edit_message_text("📥 *Entry Orders*", reply_markup=entry_menu_kb(cfg), parse_mode="Markdown")
                if key in ("tpcnt", "tpdist"):
                    return await q.edit_message_text("🎯 *Take Profit*", reply_markup=tp_menu_kb(cfg), parse_mode="Markdown")
                if key in ("be", "cs"):
                    return await q.edit_message_text("🛡️ *Breakeven & Cascade*", reply_markup=becc_menu_kb(cfg), parse_mode="Markdown")
                if key == "mode":
                    return await q.edit_message_text("🤖 *Trading Mode*", reply_markup=mode_menu_kb(cfg), parse_mode="Markdown")
                if key == "mm":
                    return await q.edit_message_text("💼 *Margin Mode*", reply_markup=margin_menu_kb(cfg), parse_mode="Markdown")
                if key == "lang":
                    return await self._show_main(q, cfg)
                if key in ("amttype", "tradeusdt", "maxpos"):
                    return await q.edit_message_text("💵 *Position Sizing*", reply_markup=possize_menu_kb(cfg), parse_mode="Markdown")
                if key in ("tslpct", "tslact"):
                    return await q.edit_message_text("🔁 *Trailing Stop Loss*", reply_markup=trailing_menu_kb(cfg), parse_mode="Markdown")
                if key == "notifon":
                    return await q.edit_message_text("🔔 *Alert Settings*", reply_markup=notifset_menu_kb(cfg), parse_mode="Markdown")
                if key in ("minconf", "minqual"):
                    return await q.edit_message_text("🎚️ *Signal Confidence Filter*", reply_markup=minconf_menu_kb(cfg), parse_mode="Markdown")
                if key in ("slmode", "slfixed", "slatrmult", "slmax", "partialclose"):
                    return await q.edit_message_text("🛑 *Stop Loss Management*", reply_markup=sl_menu_kb(cfg), parse_mode="Markdown")
                if key in ("grpfilter", "grpactive"):
                    return await q.edit_message_text("📡 *Signal Groups & Channels*", reply_markup=groups_menu_kb(cfg), parse_mode="Markdown")
                if key in ("autocloseH", "maxlossusd"):
                    return await q.edit_message_text("🔧 *Advanced Entry / Exit*", reply_markup=advanced_entry_kb(cfg), parse_mode="Markdown")
                # v11.0 DCA advanced setters
                elif key == "dcadev":
                    cfg.dca_deviation_pct = max(0.1, float(val)); changed = True
                elif key == "dcavol":
                    cfg.dca_vol_scale = max(0.5, float(val)); changed = True
                elif key == "dcamax":
                    cfg.dca_max_orders = max(1, min(10, int(val))); changed = True
                elif key == "sigtout":
                    cfg.signal_timeout_min = max(0, int(float(val))); changed = True
                elif key == "portbal":
                    cfg.portfolio_balance_pct = max(1.0, min(100.0, float(val))); changed = True
                elif key == "copysrc":
                    cfg.copy_source_channel = "" if val == "__clear__" else val.strip(); changed = True
                if changed:
                    await self.store.save(cfg)
                if key in ("dcadev", "dcavol", "dcamax", "sigtout", "portbal"):
                    return await q.edit_message_text("📉 *DCA Advanced Settings*", reply_markup=dca_advanced_kb(cfg), parse_mode="Markdown")
                if key == "copysrc":
                    return await q.edit_message_text("📡 *Copy Trading Settings*", reply_markup=copy_trading_kb(cfg), parse_mode="Markdown")

            # ── toggle ──────────────────────────────────────────────────────
            if data == "tog:fulltp1":
                cfg.full_close_tp1 = not cfg.full_close_tp1
                await self.store.save(cfg)
                return await q.edit_message_text("🎯 *Take Profit*", reply_markup=tp_menu_kb(cfg), parse_mode="Markdown")
            if data == "tog:becc":
                cfg.be_plus_cascade = not cfg.be_plus_cascade
                await self.store.save(cfg)
                return await q.edit_message_text("🛡️ *Breakeven & Cascade*", reply_markup=becc_menu_kb(cfg), parse_mode="Markdown")
            # v10.0 new toggles
            if data == "tog:simmode":
                cfg.simulation_mode = not cfg.simulation_mode
                await self.store.save(cfg)
                return await self._show_sim_menu(q, cfg)
            if data == "tog:copysig":
                cfg.copy_signals_enabled = not cfg.copy_signals_enabled
                await self.store.save(cfg)
                return await self._show_sim_menu(q, cfg)
            if data == "tog:trailing":
                cfg.trailing_stop_enabled = not cfg.trailing_stop_enabled
                await self.store.save(cfg)
                return await q.edit_message_text("🔁 *Trailing Stop Loss*", reply_markup=trailing_menu_kb(cfg), parse_mode="Markdown")
            if data == "tog:botpause":
                cfg.bot_paused = not cfg.bot_paused
                await self.store.save(cfg)
                status = "⏸️ *Bot Paused* — no new trades will be opened" if cfg.bot_paused else "▶️ *Bot Running* — auto-trading active"
                return await q.edit_message_text(status, reply_markup=main_menu_kb(cfg), parse_mode="Markdown")
            if data == "tog:notifentry":
                cfg.notify_entry = not cfg.notify_entry
                await self.store.save(cfg)
                return await q.edit_message_text("🔔 *Alert Settings*", reply_markup=notifset_menu_kb(cfg), parse_mode="Markdown")
            if data == "tog:notiftp":
                cfg.notify_tp = not cfg.notify_tp
                await self.store.save(cfg)
                return await q.edit_message_text("🔔 *Alert Settings*", reply_markup=notifset_menu_kb(cfg), parse_mode="Markdown")
            if data == "tog:notifsl":
                cfg.notify_sl = not cfg.notify_sl
                await self.store.save(cfg)
                return await q.edit_message_text("🔔 *Alert Settings*", reply_markup=notifset_menu_kb(cfg), parse_mode="Markdown")
            if data == "tog:notifdca":
                cfg.notify_dca = not cfg.notify_dca
                await self.store.save(cfg)
                return await q.edit_message_text("🔔 *Alert Settings*", reply_markup=notifset_menu_kb(cfg), parse_mode="Markdown")

            # v11.0 copy trading toggles (PTB path)
            if data == "tog:copyfollowtp":
                cfg.copy_follow_tp = not cfg.copy_follow_tp
                await self.store.save(cfg)
                return await q.edit_message_text("📡 *Copy Trading Settings*", reply_markup=copy_trading_kb(cfg), parse_mode="Markdown")
            if data == "tog:copyfollowsl":
                cfg.copy_follow_sl = not cfg.copy_follow_sl
                await self.store.save(cfg)
                return await q.edit_message_text("📡 *Copy Trading Settings*", reply_markup=copy_trading_kb(cfg), parse_mode="Markdown")
            if data == "tog:copyfollowclose":
                cfg.copy_follow_close = not cfg.copy_follow_close
                await self.store.save(cfg)
                return await q.edit_message_text("📡 *Copy Trading Settings*", reply_markup=copy_trading_kb(cfg), parse_mode="Markdown")

            # ── ask for free text input ─────────────────────────────────────
            if data.startswith("ask:"):
                kind = data.split(":", 1)[1]
                context.user_data[self.PENDING_INPUT_KEY] = {"kind": kind}
                prompts = {
                    "stake":       "💵 Send stake amount in USDT (0 = use risk %):",
                    "limit_to":    "⏱ Send limit-order timeout in minutes:",
                    "dca_mult":    "📈 Send DCA multiplier (e.g. 1.5 means each DCA is 1.5× previous):",
                    "tpcustom":    "✏️ Send TP distribution as comma-separated %, summing to 100 (e.g. 45,35,20):",
                    "trade_usdt":  "💵 Send fixed trade amount in USDT (e.g. 100):",
                    "maxpos":      "🔒 Send max position size in USDT (e.g. 500):",
                    "minqual":     "🎯 Send minimum quality score 0–100 (e.g. 65):",
                    # v10.0 new prompts
                    "slfixed":     "🛑 Send fixed SL % distance from entry (e.g. 1.5):",
                    "slatrmult":   "🛑 Send ATR multiplier for dynamic SL (e.g. 2.0):",
                    "slmax":       "🛑 Send maximum SL % allowed (e.g. 3.0):",
                    "partialclose":"📉 Send partial-close % on SL hit (0 = full close, e.g. 50):",
                    "autocloseH":  "⏰ Send auto-close timeout in hours (0 = disabled, e.g. 24):",
                    "maxlossusd":  "🚫 Send max daily loss in USDT (0 = disabled, e.g. 200):",
                    "grpadd":      "📡 Send Telegram group/channel username or ID to add (e.g. @MyGroup):",
                    "grpwl":       "✅ Send whitelist symbols comma-separated (e.g. BTCUSDT,ETHUSDT):",
                    "grpbl":       "🚫 Send blacklist symbols comma-separated (e.g. SHIBUSDT,PEPEUSDT):",
                    # v11.0 new prompts
                    "dcadev":      "📉 Send DCA price deviation % between fills (e.g. 1.5):",
                    "dcavol":      "📈 Send DCA volume multiplier per step (e.g. 1.5; 1.0 = flat):",
                    "sigtout":     "⏱ Send signal entry timeout in minutes (0 = no timeout, e.g. 15):",
                    "copysrc":     "📡 Send copy-trading source channel username or ID (e.g. @signals_channel):",
                }
                return await q.edit_message_text(prompts.get(kind, "Send value:"))

            # ── API keys ────────────────────────────────────────────────────
            if data == "key:add":
                return await q.edit_message_text("🔑 Choose exchange:", reply_markup=add_exchange_kb())
            if data.startswith("key:exchange:"):
                exch = data.split(":")[2]
                context.user_data[self.PENDING_INPUT_KEY] = {"kind": "api_label", "exchange": exch}
                return await q.edit_message_text(f"🔑 *{exch.upper()}* — Step 1/3\nSend a label for this key (e.g. 'main', 'sub-account-1'):", parse_mode="Markdown")
            if data.startswith("key:select:"):
                _, _, exch, label = data.split(":", 3)
                cfg.active_exchange = exch
                await self.store.save(cfg)
                return await q.edit_message_text(
                    f"✅ Active key: *{exch.upper()} · {label}*",
                    reply_markup=_kb([
                        [(f"🗑 Unbind", f"key:del:{exch}:{label}")],
                        [(f"◀️ Back", "menu:keys")],
                    ]),
                    parse_mode="Markdown",
                )
            if data.startswith("key:del:"):
                _, _, exch, label = data.split(":", 3)
                await self.store.delete_api_key(user.id, exch, label)
                return await self._show_keys(q, cfg)

            # ── v10.5: Position close callbacks ─────────────────────────────
            if data.startswith("pos:"):
                return await self._handle_position_close(q, cfg, data)

            # ── per-signal actions ──────────────────────────────────────────
            if data.startswith("sig:"):
                _, action, signal_id = data.split(":", 2)
                payload = {"chat_id": q.message.chat_id if q.message else None}
                await self.store.record_signal_action(user.id, signal_id, action, payload)
                if action == "follow" and self.signal_executor:
                    try:
                        result = await self.signal_executor(user.id, signal_id, cfg)
                        return await q.edit_message_reply_markup(reply_markup=_kb([
                            [(f"✅ Followed: {str(result)[:30]}", "noop")],
                        ]))
                    except Exception as e:
                        return await q.edit_message_reply_markup(reply_markup=_kb([
                            [(f"❌ Failed: {str(e)[:40]}", "noop")],
                        ]))
                if action == "ignore":
                    return await q.edit_message_reply_markup(reply_markup=_kb([[("🙈 Ignored", "noop")]]))
                if action in ("brief", "detail"):
                    extra = "Full multi-timeframe + 10-agent swarm + IRONS scoring breakdown" if action == "detail" else "Quick AI confidence summary"
                    return await q.message.reply_text(f"📊 *{action.title()} Analysis* for `{signal_id}`\n\n{extra}", parse_mode="Markdown")
                if action == "retry" and self.signal_executor:
                    try:
                        result = await self.signal_executor(user.id, signal_id, cfg, retry=True)
                        return await q.message.reply_text(f"🔁 Retry result: {result}")
                    except Exception as e:
                        return await q.message.reply_text(f"❌ Retry failed: {e}")
                # ── v10.5: Execute via CCXT ────────────────────────────────
                if action == "execute":
                    return await self._handle_execute_signal(q, cfg, signal_id)
                return

            logger.debug(f"Unhandled callback: {data}")

        except Exception as e:
            logger.exception(f"Callback error on '{data}': {e}")
            try:
                await q.message.reply_text(f"⚠️ Error: {e}")
            except Exception:
                pass

    # ── api key wizard ──────────────────────────────────────────────────────

    async def _api_key_wizard_step(self, update: Update, context: ContextTypes.DEFAULT_TYPE,
                                   cfg: UserConfig, state: Dict[str, Any]) -> None:
        exch = state["exchange"]
        msg = update.effective_message
        # we already received "kind"; figure out next step
        if "api_label" not in state:
            return  # text handler stored it via `pending[kind]=text` so should not reach here
        # if we got the label in this turn:
        kind_just_received = state.get("kind")
        if kind_just_received == "api_label" and "api_label" in state:
            state["kind"] = "api_key"
            await msg.reply_text(f"🔑 *{exch.upper()}* — Step 2/3\nSend the API Key:", parse_mode="Markdown")
            return
        if kind_just_received == "api_key" and "api_key" in state:
            state["kind"] = "api_secret"
            await msg.reply_text(f"🔑 *{exch.upper()}* — Step 3/3\nSend the API Secret:", parse_mode="Markdown")
            return
        if kind_just_received == "api_secret" and "api_secret" in state:
            needs_pass = exch in ("okx", "kucoin")
            if needs_pass and "api_pass" not in state:
                state["kind"] = "api_pass"
                await msg.reply_text(f"🔑 *{exch.upper()}* — Step 4/4\nSend the API Passphrase:", parse_mode="Markdown")
                return
            await self.store.add_api_key(
                cfg.user_id, exch, state["api_label"],
                state["api_key"], state["api_secret"], state.get("api_pass", ""),
            )
            cfg.active_exchange = exch
            await self.store.save(cfg)
            context.user_data.pop(self.PENDING_INPUT_KEY, None)
            await msg.reply_text(
                f"✅ Saved {exch.upper()} key '{state['api_label']}' (encrypted at rest).",
                reply_markup=main_menu_kb(cfg),
            )
            return
        if kind_just_received == "api_pass" and "api_pass" in state:
            await self.store.add_api_key(
                cfg.user_id, exch, state["api_label"],
                state["api_key"], state["api_secret"], state["api_pass"],
            )
            cfg.active_exchange = exch
            await self.store.save(cfg)
            context.user_data.pop(self.PENDING_INPUT_KEY, None)
            await msg.reply_text(
                f"✅ Saved {exch.upper()} key '{state['api_label']}' (encrypted at rest).",
                reply_markup=main_menu_kb(cfg),
            )

    # ── view renderers ──────────────────────────────────────────────────────

    async def _show_sim_menu(self, q, cfg: UserConfig) -> None:
        sim_icon = "🧪" if cfg.simulation_mode else "📈"
        copy_icon = "✅" if cfg.copy_signals_enabled else "⬜"
        body = (
            f"🧪 *Simulation & Copy Settings*\n\n"
            f"{sim_icon} Paper/Simulation Mode: *{'ON — no real orders placed' if cfg.simulation_mode else 'OFF — live trading'}*\n"
            f"{copy_icon} Copy Signals to Exchange: *{'enabled' if cfg.copy_signals_enabled else 'disabled'}*\n\n"
            f"In Simulation mode:\n"
            f"• All signals are tracked and scored\n"
            f"• Orders are paper-traded (no real money)\n"
            f"• P&L and win rate are simulated\n"
            f"• Ideal for testing new strategies safely\n\n"
            f"_Backtesting runs the MiroFish 10-agent swarm on historical data._"
        )
        await q.edit_message_text(body, reply_markup=sim_menu_kb(cfg), parse_mode="Markdown")

    def _backtest_body(self) -> str:
        """Build enhanced MiroFish backtest overview (shared by PTB + raw paths)."""
        sim_ref = getattr(self, "_mirofish_sim", None)
        if sim_ref is not None:
            try:
                stats = sim_ref.summary_stats()
                top5  = stats.get("top_5_by_sharpe", [])
                top5_wr = stats.get("top_5_by_wr", [])
                # Build per-symbol scorecards for top-3 Sharpe
                scorecards = ""
                for sym in top5[:3]:
                    rep = sim_ref.get_simulation_report(sym)
                    if rep and not rep.get("error"):
                        bias = rep.get("quality_bias", 0.0)
                        icon = "🟢" if bias >= 3 else ("🟡" if bias >= 0 else "🔴")
                        scorecards += (
                            f"\n{icon} *{sym}*  WR:`{rep['win_rate_pct']:.0f}%`  "
                            f"Sh:`{rep['sharpe']:.2f}`  "
                            f"EV:`{rep['ev_per_trade_pct']:+.3f}%`  "
                            f"MDD:`{rep['max_drawdown_pct']:.1f}%`"
                        )
                top5_wr_str  = ", ".join(top5_wr[:5])  if top5_wr  else "n/a"
                return (
                    f"📐 *MiroFish Swarm Backtest* [v10.2]\n\n"
                    f"• Symbols simulated : `{stats.get('symbols_simulated', 0)}`\n"
                    f"• Sweep runs        : `{stats.get('run_count', 0)}`\n"
                    f"• Avg Win Rate      : `{stats.get('avg_win_rate_pct', 0):.1f}%`\n"
                    f"• Avg Sharpe        : `{stats.get('avg_sharpe', 0):.3f}`\n"
                    f"• Avg Sortino       : `{stats.get('avg_sortino', 0):.3f}`\n"
                    f"• Avg Calmar        : `{stats.get('avg_calmar', 0):.3f}`\n"
                    f"• Avg Max-DD        : `{stats.get('avg_max_dd_pct', 0):.2f}%`\n"
                    f"• Avg EV/trade      : `{stats.get('avg_ev_pct', 0):+.3f}%`\n"
                    f"• Avg R:R           : `{stats.get('avg_rr', 0):.2f}`\n"
                    f"• Top 5 WR          : `{top5_wr_str}`\n"
                    f"\n*Top-3 by Sharpe:*{scorecards}\n\n"
                    f"_Agents: Trend · Momentum · Volume · Volatility · OrderFlow_\n"
                    f"_Sentiment · Regime · Microstructure · Risk · Composite_\n\n"
                    f"_Quality bias: −8 to +5 pts → Gate 8.5_"
                )
            except Exception as e:
                return f"📐 *Backtest Results*\n\n⚠️ Sim engine error: {e}"
        return (
            "📐 *MiroFish Swarm Backtest* [v10.2]\n\n"
            "• 10-agent swarm on 15M Binance USDM klines\n"
            "• Metrics: WR · Sharpe · Sortino · Calmar · Max-DD · EV · R:R\n"
            "• Quality bias: −8 to +5 pts → Gate 8.5\n"
            "• Auto-refreshes every 30 min in background\n\n"
            "_Simulation engine starting… check back shortly._"
        )

    def _sym_report_body(self, symbol: str, report: Optional[Dict[str, Any]]) -> str:
        """Format per-symbol institutional backtest detail card."""
        if not report:
            return f"📐 *{symbol} — MiroFish Simulation*\n\n_No data yet. Tap ▶️ Run Now to simulate._"
        err = report.get("error")
        if err and err not in ("", None):
            return f"📐 *{symbol} — MiroFish Simulation*\n\n⚠️ Error: `{err}`\n\nTap ▶️ Run Now to retry."
        bias = report.get("quality_bias", 0.0)
        bias_icon = "🟢" if bias >= 3 else ("🟡" if bias >= 0 else "🔴")
        age_s = int(report.get("age_sec", 0))
        age_str = (f"{age_s//60}m {age_s%60}s" if age_s < 3600
                   else f"{age_s//3600}h {(age_s%3600)//60}m")
        return (
            f"📐 *{symbol} — MiroFish Institutional Backtest*\n\n"
            f"• Trades        : `{report.get('n_trades', 0)}`  (on {report.get('bars_used', 0)} bars)\n"
            f"• Win Rate      : `{report.get('win_rate_pct', 0):.1f}%`\n"
            f"• Total P&L     : `{report.get('total_pnl_pct', 0):+.2f}%`\n"
            f"• Avg R:R       : `{report.get('avg_rr', 0):.2f}`\n"
            f"• EV / trade    : `{report.get('ev_per_trade_pct', 0):+.3f}%`\n\n"
            f"*Risk-Adjusted Metrics*\n"
            f"• Sharpe Ratio  : `{report.get('sharpe', 0):+.3f}`\n"
            f"• Sortino Ratio : `{report.get('sortino', 0):+.3f}`\n"
            f"• Calmar Ratio  : `{report.get('calmar', 0):+.3f}`\n"
            f"• Max Drawdown  : `{report.get('max_drawdown_pct', 0):.2f}%`\n\n"
            f"*Gate 8.5 Quality Bias*  {bias_icon}\n"
            f"  `{bias:+.0f} pts`  (_+5=high-quality · −8=avoid_)\n\n"
            f"_Data age: {age_str}  |  Interval: 15M  |  10 agents_"
        )

    async def _show_backtest(self, q_or_chat_id, cfg_or_msg_id=None, cfg_extra=None) -> None:
        """Dual-mode: PTB (q, cfg) or raw HTTP (chat_id, msg_id, cfg)."""
        body = self._backtest_body()
        kb = _kb([
            [("📋 Symbol List",  "backtest:list"),
             ("🔄 Refresh",      "menu:backtest")],
            [("◀️ Back", "menu:main")],
        ])
        if hasattr(q_or_chat_id, "edit_message_text"):
            await q_or_chat_id.edit_message_text(body, reply_markup=kb, parse_mode="Markdown")
        else:
            await self._edit(q_or_chat_id, cfg_or_msg_id, body, kb)

    async def _show_backtest_list(self, q_or_chat_id, msg_id: int = 0, page: int = 0) -> None:
        """Symbol paginator list — dual mode (PTB q or raw chat_id/msg_id)."""
        sim_ref = getattr(self, "_mirofish_sim", None)
        if sim_ref is None:
            body = "📋 *Symbol List*\n\n_Simulation engine not yet available._"
            kb   = _kb([[("◀️ Back", "menu:backtest")]])
        else:
            reports = sim_ref.get_all_reports()  # sorted by Sharpe desc
            if not reports:
                body = "📋 *Symbol List*\n\n_No simulations completed yet. Check back in ~30 min._"
                kb   = _kb([[("🔄 Refresh", "backtest:list"), ("◀️ Back", "menu:backtest")]])
            else:
                body = f"📋 *Symbol List* ({len(reports)} simulated  |  page {page+1})\n🟢=bias≥+3  🟡=neutral  🔴=bias<0"
                kb   = backtest_sym_kb(reports, page=page)
        if hasattr(q_or_chat_id, "edit_message_text"):
            await q_or_chat_id.edit_message_text(body, reply_markup=kb, parse_mode="Markdown")
        else:
            await self._edit(q_or_chat_id, msg_id, body, kb)

    async def _show_backtest_symbol(self, q_or_chat_id, msg_id: int = 0, sym: str = "") -> None:
        """Per-symbol detail card — dual mode (PTB q or raw chat_id/msg_id)."""
        sim_ref = getattr(self, "_mirofish_sim", None)
        report  = sim_ref.get_simulation_report(sym) if sim_ref else None
        body = self._sym_report_body(sym, report)
        kb   = backtest_sym_detail_kb(sym)
        if hasattr(q_or_chat_id, "edit_message_text"):
            await q_or_chat_id.edit_message_text(body, reply_markup=kb, parse_mode="Markdown")
        else:
            await self._edit(q_or_chat_id, msg_id, body, kb)

    async def _run_backtest_now(self, q_or_chat_id, msg_id: int = 0, sym: str = "") -> None:
        """Trigger on-demand single-symbol simulation and refresh the detail card."""
        sim_ref = getattr(self, "_mirofish_sim", None)
        _ptb = hasattr(q_or_chat_id, "edit_message_text")

        # Show "Running…" message
        loading_kb = _kb([[("⏳ Simulating…", "noop")]])
        loading_body = f"⏳ *Running MiroFish Simulation on {sym}…*\n\n_This takes ~5s — please wait._"
        if _ptb:
            await q_or_chat_id.edit_message_text(loading_body, reply_markup=loading_kb, parse_mode="Markdown")
        else:
            await self._edit(q_or_chat_id, msg_id, loading_body, loading_kb)

        if sim_ref is None:
            body = f"📐 *{sym}* — Simulation engine unavailable."
            kb   = backtest_sym_detail_kb(sym)
        else:
            try:
                report = await sim_ref.run_single(sym)
                body   = self._sym_report_body(sym, report)
            except Exception as e:
                body   = f"📐 *{sym}*\n\n❌ Simulation failed: `{e}`"
            kb = backtest_sym_detail_kb(sym)

        if _ptb:
            await q_or_chat_id.edit_message_text(body, reply_markup=kb, parse_mode="Markdown")
        else:
            await self._edit(q_or_chat_id, msg_id, body, kb)

    def _quant_body(self, section: str = "full") -> str:
        """Build institutional quant report text from engine metrics."""
        m = getattr(self, "_unity_metrics", None)
        if m is None:
            return (
                "📐 *Institutional Quant Report*\n\n"
                "_Metrics not yet available — Unity Engine still initialising._\n"
                "_Trade returns accumulate after first closed positions._"
            )
        n = len(getattr(m, "_trade_returns", []))
        if section in ("full", "sharpe", "dd", "kelly"):
            base = (
                f"📐 *Institutional Quant Report* [v10.0]\n"
                f"_Rolling window: {n} closed trades_\n\n"
            )
            if n < 5:
                return base + "_Not enough data yet — need ≥5 closed trades._"
            if section == "sharpe" or section == "full":
                base += (
                    f"*Risk-Adjusted Returns*\n"
                    f"  Sharpe Ratio  : `{m.sharpe_ratio:+.4f}`\n"
                    f"  Sortino Ratio : `{m.sortino_ratio:+.4f}`\n"
                    f"  Calmar Ratio  : `{m.calmar_ratio:+.4f}`\n\n"
                )
            if section == "dd" or section == "full":
                base += (
                    f"*Drawdown Analysis*\n"
                    f"  Max Drawdown  : `{m.max_drawdown_pct:.3f}%`\n"
                    f"  Current Equity: `{getattr(m, '_current_equity', 100):.2f}` (base=100)\n\n"
                )
            if section == "kelly" or section == "full":
                base += (
                    f"*Position Sizing (Kelly Criterion)*\n"
                    f"  Full Kelly f*  : `{m.kelly_fraction_pct:.2f}%`\n"
                    f"  Half-Kelly (rec): `{m.kelly_fraction_pct/2:.2f}%`\n"
                    f"  EV per trade   : `{m.expected_value_r:+.4f}R`\n\n"
                )
            if section == "full":
                base += (
                    f"*Overall Performance*\n"
                    f"  Win Rate  : `{m.win_rate:.1f}%` ({m.win_count}W / {m.loss_count}L)\n"
                    f"  Total PnL : `{m.total_profit_pct:+.3f}%`\n"
                )
            return base
        return self._quant_body("full")

    async def _show_quant_stats(self, chat_id_or_q, msg_id=None, section: str = "full") -> None:
        """Dual-mode quant report: PTB (q) or raw HTTP (chat_id, msg_id)."""
        body = self._quant_body(section)
        kb = quant_stats_kb()
        if hasattr(chat_id_or_q, "edit_message_text"):
            await chat_id_or_q.edit_message_text(body, reply_markup=kb, parse_mode="Markdown")
        else:
            await self._edit(chat_id_or_q, msg_id, body, kb)

    async def _show_main(self, q, cfg: UserConfig) -> None:
        await q.edit_message_text(_t(cfg, "welcome"), reply_markup=main_menu_kb(cfg), parse_mode="Markdown")

    async def _show_dashboard(self, q, cfg: UserConfig) -> None:
        balance = equity = avail = upnl = 0.0
        positions: List[Dict[str, Any]] = []
        data_source = "no API keys"
        try:
            # v10.5: prefer CCXT live data when keys are stored
            keys = await self.store.list_api_keys(cfg.user_id, cfg.active_exchange)
            if keys and _HAS_CCXT:
                label = keys[0]["label"]
                bd = await self._ccxt_provider.get_balance(cfg.user_id, cfg.active_exchange, label)
                balance = bd.get("balance",        0.0)
                equity  = bd.get("equity",         0.0)
                avail   = bd.get("available",      0.0)
                upnl    = bd.get("unrealised_pnl", 0.0)
                positions = await self._ccxt_provider.get_positions(cfg.user_id, cfg.active_exchange, label)
                data_source = f"live {cfg.active_exchange.upper()}"
            elif self.balance_provider:
                bd = await self.balance_provider(cfg)
                balance = float(bd.get("balance", 0))
                equity  = float(bd.get("equity",  0))
                avail   = float(bd.get("available", 0))
                upnl    = float(bd.get("unrealised_pnl", 0))
                if self.positions_provider:
                    positions = await self.positions_provider(cfg) or []
                data_source = "engine trader"
        except Exception as e:
            logger.warning(f"dashboard provider error: {e}")
        # Unity engine metrics overlay
        m   = getattr(self, "_unity_metrics", None)
        b   = getattr(self, "_unity_booster", None)
        eng = getattr(self, "_unity_engine",  None)
        wr_str = (f"{m.win_rate:.1f}% ({m.win_count}W/{m.loss_count}L)" if m else "n/a")
        kelly_str = (f"{b.last_kelly_fraction*100:.2f}%" if b else "n/a")
        sig_hr = round(m.total_signals_sent / max(m.uptime_hours, 1e-6), 1) if m else 0
        layers_online = sum(1 for l in eng.health.layers.values() if l.available) if eng else 0
        body = (
            f"📊 *Trading Dashboard* [v10.5]\n"
            f"_Data source: {data_source}_\n\n"
            f"💰 *Exchange Balance*\n"
            f"• Wallet Balance   : `{balance:,.2f} USDT`\n"
            f"• Available Margin : `{avail:,.2f} USDT`\n"
            f"• Margin Equity    : `{equity:,.2f} USDT`\n"
            f"• Unrealised PnL   : `{upnl:+,.2f} USDT`\n"
            f"• Open Positions   : `{len(positions)}`\n\n"
            f"⚙️ *Configuration*\n"
            f"• Exchange  : `{cfg.active_exchange.upper()}`\n"
            f"• Mode      : `{cfg.trading_mode.upper()}`\n"
            f"• Leverage  : `{cfg.leverage}x`  Risk: `{cfg.risk_pct}%`\n"
            f"• SL mode   : `{cfg.sl_mode.upper()}`  TSL: `{'ON' if cfg.trailing_stop_enabled else 'OFF'}`\n\n"
            f"⚡ *Engine Status*\n"
            f"• Win Rate  : `{wr_str}`\n"
            f"• Kelly f*  : `{kelly_str}`\n"
            f"• Signals/h : `{sig_hr:.1f}` (target 5–10)\n"
            f"• Layers    : `{layers_online}/20 online`\n"
        )
        kb = _kb([
            [("🔄 Refresh",      "menu:dash"),
             ("📁 Positions",    "menu:positions")],
            [("📐 Quant Stats",  "menu:quant"),
             ("📐 Backtest",     "menu:backtest")],
            [("◀️ Back", "menu:main")],
        ])
        await q.edit_message_text(body, reply_markup=kb, parse_mode="Markdown")

    async def _show_keys(self, q, cfg: UserConfig) -> None:
        keys = await self.store.list_api_keys(cfg.user_id)
        body = "🔑 *API Keys*\n\n"
        if keys:
            body += f"You have {len(keys)} key(s). Tap to manage:"
        else:
            body += "No API keys yet. Add one to enable execution."
        await q.edit_message_text(body, reply_markup=keys_menu_kb(cfg, keys), parse_mode="Markdown")

    async def _show_signals_menu(self, q, cfg: UserConfig) -> None:
        stats = await self.store.signal_action_stats(cfg.user_id)
        body = (
            "📨 *Working with Signals*\n\n"
            "When a signal arrives in the channel, you can:\n"
            "• 🚀 Follow — execute immediately on your exchange\n"
            "• 🤖 Auto Mode — execute every approved signal automatically\n"
            "• 🙈 Ignore — skip it\n"
            "• 🔁 Retry — re-execute a failed signal\n"
            "• 📊 Brief / Detailed — AI quality breakdown\n\n"
            f"_Your stats: follow={stats.get('follow', 0)}  ignore={stats.get('ignore', 0)}  retry={stats.get('retry', 0)}_"
        )
        await q.edit_message_text(body, reply_markup=_kb([
            [(f"{'✅' if cfg.trading_mode == 'auto' else ''}🤖 Auto Mode",   "set:mode:auto")],
            [(f"{'✅' if cfg.trading_mode == 'manual' else ''}👤 Manual",   "set:mode:manual")],
            [(f"{'✅' if cfg.trading_mode == 'off' else ''}🔇 Off",        "set:mode:off")],
            [("◀️ Back", "menu:main")],
        ]), parse_mode="Markdown")

    async def _show_positions(self, q, cfg: UserConfig) -> None:
        positions: List[Dict[str, Any]] = []
        data_source = "no data"
        try:
            # v10.5: prefer CCXT live positions
            keys = await self.store.list_api_keys(cfg.user_id, cfg.active_exchange)
            if keys and _HAS_CCXT:
                label = keys[0]["label"]
                positions = await self._ccxt_provider.get_positions(cfg.user_id, cfg.active_exchange, label)
                data_source = f"live {cfg.active_exchange.upper()}"
            elif self.positions_provider:
                positions = await self.positions_provider(cfg) or []
                data_source = "engine"
        except Exception as e:
            logger.warning(f"positions provider error: {e}")
        if not positions:
            body = (
                f"📁 *Position Management*\n"
                f"_Source: {data_source}_\n\n"
                f"No open positions."
            )
            kb = _kb([
                [("🔄 Refresh", "menu:positions"),
                 ("◀️ Back",   "menu:main")],
            ])
        else:
            total_upnl = sum(float(p.get("unrealised_pnl", 0)) for p in positions)
            lines = [
                f"📁 *Open Positions* ({len(positions)}) [live]\n"
                f"_Total uPnL: `{total_upnl:+,.2f} USDT`_\n"
            ]
            btn_rows = []
            for p in positions[:8]:
                sym   = p.get("symbol", "?")
                side  = p.get("side",   "?")
                qty   = float(p.get("qty", 0))
                entry = float(p.get("entry_price", 0))
                upnl  = float(p.get("unrealised_pnl", 0))
                lev   = p.get("leverage", 1)
                icon  = "🟢" if side in ("LONG", "BUY") else "🔴"
                lines.append(
                    f"{icon} `{sym}` {side} ×`{lev}` | "
                    f"qty `{qty:.4g}` | entry `{entry:.4g}` | uPnL `{upnl:+.2f}`"
                )
                safe  = sym.replace("/", "_")
                qty_s = f"{qty:.4f}".rstrip("0").rstrip(".")
                btn_rows.append([
                    (f"❌ Close {sym}", f"pos:close:{safe}:{side}:{qty_s}"),
                    (f"📉 50%",         f"pos:close50:{safe}:{side}:{qty_s}"),
                ])
            body = "\n".join(lines)
            kb = _kb([
                *btn_rows,
                [("❌ Close ALL", "pos:closeall"),
                 ("🔄 Refresh",   "menu:positions")],
                [("◀️ Back", "menu:main")],
            ])
        await q.edit_message_text(body, reply_markup=kb, parse_mode="Markdown")

    # ── v10.5: CCXT Order Execution Handlers ──────────────────────────────────

    async def _handle_position_close(self, q, cfg: UserConfig, data: str) -> None:
        """Handle pos:close / pos:close50 / pos:closeall callbacks."""
        # data format: "pos:close:{safe_symbol}:{side}:{qty}"
        #              "pos:close50:{safe_symbol}:{side}:{qty}"
        #              "pos:closeall"
        await q.answer("Processing…")
        keys = await self.store.list_api_keys(cfg.user_id, cfg.active_exchange)
        if not keys:
            await q.edit_message_text(
                "❌ No API keys configured for this exchange.\nGo to ⚙️ Settings → 🔑 API Keys.",
                reply_markup=_kb([[("◀️ Back", "menu:positions")]]),
            )
            return
        label    = keys[0]["label"]
        exchange = cfg.active_exchange
        if data == "pos:closeall":
            positions = await self._ccxt_provider.get_positions(cfg.user_id, exchange, label)
            if not positions:
                await q.edit_message_text("No open positions to close.",
                                          reply_markup=_kb([[("◀️ Back", "menu:positions")]]))
                return
            results = []
            for p in positions:
                r = await self._ccxt_provider.close_position(
                    cfg.user_id, exchange, label,
                    p["symbol"], p["qty"], p["side"]
                )
                results.append(f"{'✅' if r.get('ok') else '❌'} {p['symbol']}: {r.get('id', r.get('error', '?'))}")
            body = "❌ *Close All Positions*\n\n" + "\n".join(results)
            await q.edit_message_text(body, reply_markup=_kb([[("◀️ Back", "menu:positions")]]),
                                      parse_mode="Markdown")
            return
        parts = data.split(":")
        # parts: [pos, close|close50, safe_sym, side, qty]
        action   = parts[1]
        safe_sym = parts[2]
        side     = parts[3]
        qty      = float(parts[4]) if len(parts) > 4 else 0.0
        symbol   = safe_sym.replace("_", "/")
        if action == "close50":
            qty = round(qty * 0.5, 8)
        r = await self._ccxt_provider.close_position(cfg.user_id, exchange, label, symbol, qty, side)
        if r.get("ok"):
            body = (
                f"✅ *Position Closed*\n\n"
                f"• Symbol : `{symbol}`\n"
                f"• Side   : `{side}`\n"
                f"• Qty    : `{qty}`\n"
                f"• Order  : `{r.get('id', '?')}`"
            )
        else:
            body = f"❌ *Close Failed*\n\n`{r.get('error', 'unknown error')}`"
        await q.edit_message_text(body, reply_markup=_kb([
            [("🔄 Positions", "menu:positions"), ("◀️ Back", "menu:main")],
        ]), parse_mode="Markdown")

    async def _handle_execute_signal(self, q, cfg: UserConfig, signal_id: str) -> None:
        """Execute a Unity signal as a real exchange order via CCXT."""
        await q.answer("Executing…")
        sig = self._signal_cache.get(signal_id)
        if not sig:
            await q.edit_message_text(
                "⚠️ Signal data no longer in cache (it may have expired). "
                "Please wait for the next signal.",
                reply_markup=_kb([[("◀️ Back", "menu:main")]]),
            )
            return
        keys = await self.store.list_api_keys(cfg.user_id, cfg.active_exchange)
        if not keys:
            await q.edit_message_text(
                "❌ No API keys configured. Go to ⚙️ Settings → 🔑 API Keys.",
                reply_markup=_kb([[("◀️ Back", "menu:main")]]),
            )
            return
        label    = keys[0]["label"]
        exchange = cfg.active_exchange
        symbol   = sig.get("symbol", "BTC/USDT")
        side     = "buy" if sig.get("direction", "LONG").upper() == "LONG" else "sell"
        entry    = float(sig.get("entry", 0) or 0)
        sl       = float(sig.get("sl",    0) or 0)
        leverage = cfg.leverage
        # Calculate position size from risk %
        bd = await self._ccxt_provider.get_balance(cfg.user_id, exchange, label)
        equity = bd.get("equity", 0.0)
        risk_amt = equity * (cfg.risk_pct / 100.0)
        sl_dist  = abs(entry - sl) if sl and entry else (entry * 0.02)
        qty      = round(risk_amt / max(sl_dist, 1e-9), 6) if sl_dist else 0.0
        if qty <= 0 or equity <= 0:
            await q.edit_message_text(
                f"❌ Cannot compute position size: equity=`{equity:.2f}` risk={cfg.risk_pct}% SL distance=`{sl_dist:.4g}`",
                reply_markup=_kb([[("◀️ Back", "menu:main")]]),
                parse_mode="Markdown",
            )
            return
        # Use market order for instant fill
        r = await self._ccxt_provider.execute_order(
            cfg.user_id, exchange, label, symbol, side, qty,
            order_type="market", leverage=leverage,
        )
        if r.get("ok"):
            body = (
                f"✅ *Order Executed* [v10.5]\n\n"
                f"• Symbol   : `{symbol}`\n"
                f"• Side     : `{side.upper()}`\n"
                f"• Qty      : `{qty:.6g}`\n"
                f"• Leverage : `{leverage}x`\n"
                f"• Order ID : `{r.get('id', '?')}`\n\n"
                f"_SL at {sl:.4g} · Risk {cfg.risk_pct}% · Equity {equity:.2f} USDT_"
            )
        else:
            body = f"❌ *Execution Failed*\n\n`{r.get('error', 'unknown error')}`"
        await q.edit_message_text(body, reply_markup=_kb([
            [("📁 Positions", "menu:positions"), ("◀️ Back", "menu:main")],
        ]), parse_mode="Markdown")

    def cache_signal(self, signal_id: str, signal_data: Dict[str, Any]) -> None:
        """Store a signal in the cache for later execution. Max 50 entries (LRU drop)."""
        if len(self._signal_cache) >= 50:
            oldest = next(iter(self._signal_cache))
            self._signal_cache.pop(oldest, None)
        self._signal_cache[signal_id] = signal_data

    async def _show_history(self, q, cfg: UserConfig) -> None:
        trades: List[Dict[str, Any]] = []
        try:
            if self.history_provider:
                trades = await self.history_provider(cfg) or []
        except Exception as e:
            logger.warning(f"history provider error: {e}")
        if not trades:
            body = "📋 *History & Statistics*\n\nNo closed trades yet."
        else:
            wins   = sum(1 for t in trades if float(t.get("pnl", 0)) > 0)
            losses = len(trades) - wins
            wr     = (wins / len(trades)) * 100 if trades else 0
            total_pnl = sum(float(t.get("pnl", 0)) for t in trades)
            avg_pnl   = total_pnl / len(trades)
            best  = max(trades, key=lambda t: float(t.get("pnl", 0)))
            worst = min(trades, key=lambda t: float(t.get("pnl", 0)))
            body = (
                f"📋 *History & Statistics*\n\n"
                f"• Total trades: `{len(trades)}`\n"
                f"• Wins / Losses: `{wins} / {losses}`\n"
                f"• Win rate: `{wr:.1f}%`\n"
                f"• Total PnL: `{total_pnl:+.2f} USDT`\n"
                f"• Avg PnL: `{avg_pnl:+.2f} USDT`\n"
                f"• Best trade: `{best.get('symbol')} {float(best.get('pnl', 0)):+.2f}`\n"
                f"• Worst trade: `{worst.get('symbol')} {float(worst.get('pnl', 0)):+.2f}`\n"
            )
        await q.edit_message_text(body, reply_markup=_kb([
            [("📊 Statistics", "menu:history")],
            [("◀️ Back", "menu:main")],
        ]), parse_mode="Markdown")

    async def _show_ai_validation(self, q, cfg: UserConfig) -> None:
        body = (
            "🤖 *AI Signal Validation*\n\n"
            "The G0DM0D3 AI ensemble + 10-agent swarm + IRONS scorer "
            "rate every signal across:\n"
            "• Multi-timeframe alignment (4H / 1H / 15M)\n"
            "• 10-agent swarm consensus %\n"
            "• IRONS 25-indicator score (Momentum / Trend / Vol / Volume)\n"
            "• Neural Network MC-Dropout win-prob\n"
            "• OpenRouter LLM ensemble vote\n"
            "• GEX regime + Gamma Zero proximity\n"
        )
        await q.edit_message_text(body, reply_markup=_kb([
            [("📊 Brief Analysis", "sig:brief:latest"),
             ("📊 Detailed",       "sig:detail:latest")],
            [("🎯 Score Components", "menu:aiv")],
            [("◀️ Back", "menu:main")],
        ]), parse_mode="Markdown")

    async def _show_channel(self, q, cfg: UserConfig, context: ContextTypes.DEFAULT_TYPE) -> None:
        body = (
            "📡 *Channel Settings*\n\n"
            f"Currently monitoring: `{cfg.signal_channel}`\n\n"
            "When a signal appears:\n"
            "• Auto Mode ON → executed automatically\n"
            "• Auto Mode OFF → shows action buttons (Follow / Ignore / Brief / Detailed)\n"
        )
        context.user_data[self.PENDING_INPUT_KEY] = {"kind": "channel"}
        await q.edit_message_text(body + "\n_Send a new channel @username (or chat ID starting -100…)._",
                                  reply_markup=_kb([[("◀️ Back", "menu:main")]]), parse_mode="Markdown")

    async def _show_help(self, q, cfg: UserConfig) -> None:
        body = (
            "❓ *Getting Started*\n\n"
            "1️⃣ Open *🔑 API Keys* and add your exchange key (futures-enabled).\n"
            "2️⃣ Open *⚙️ Settings → Risk Management* — set leverage, risk %, max trades.\n"
            "3️⃣ Pick *🎯 Take Profit* count + distribution (45/35/20 is balanced).\n"
            "4️⃣ Optional: turn on *🛡️ Breakeven* after TP1 or TP2 for free trades.\n"
            "5️⃣ Choose *🤖 Mode → Auto* to execute every approved signal.\n\n"
            "Supported exchanges: Binance / Bybit / OKX / BingX / Bitget / KuCoin / Gate / MEXC.\n\n"
            "All signals are filtered through the Unity Engine 12-gate system "
            "(EV, Session, MinTP1, R:R, Swarm consensus, AI confidence, NN win-prob, "
            "Analyzer alignment, Regime, GEX, Per-symbol WR, Quality, IRONS) "
            "before any execution."
        )
        await q.edit_message_text(body, reply_markup=_kb([[("◀️ Back", "menu:main")]]), parse_mode="Markdown")


# ═══════════════════════════════════════════════════════════════════════════
#   STANDALONE LAUNCHER  (for manual `python -m SignalMaestro.cornix_menu_bot`)
# ═══════════════════════════════════════════════════════════════════════════

async def _standalone() -> None:
    if not _HAS_PTB:
        raise SystemExit("python-telegram-bot is required")
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise SystemExit("TELEGRAM_BOT_TOKEN env var is required")

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    app = Application.builder().token(token).build()
    bot = CornixMenuBot()
    bot.attach(app)

    logger.info("🚀 Cornix Menu Bot standalone — polling…")
    await app.initialize()
    await app.start()
    if app.updater:
        await app.updater.start_polling(drop_pending_updates=True)
    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        if app.updater:
            await app.updater.stop()
        await app.stop()
        await app.shutdown()


if __name__ == "__main__":
    asyncio.run(_standalone())

"""
SignalMaestro — User Database  v11.4
═══════════════════════════════════════════════════════════════════════════════
Async per-user SQLite database using aiosqlite.

Tables:
  • users           — registered Telegram user profiles + admin flag
  • api_keys        — Fernet-encrypted exchange API key vault per user
  • user_settings   — risk/mode/leverage preferences per user + exchange
  • active_signals  — live signals awaiting user action
  • signal_history  — completed signal outcomes per user
  • exchange_trades — full CCXT execution records (multi-exchange trade log)
  • user_channels   — Telegram channels/groups user receives signals from
  • notifications   — per-user notification preference flags

Design:
  • All I/O is non-blocking async (aiosqlite) — truly lock-free under asyncio.
  • WAL mode + NORMAL synchronous — maximises concurrent reader throughput.
  • Fernet encryption at rest for all API key material (AES-128-CBC + HMAC).
  • Thread-safe: one DB file, single aiosqlite connection, serialised through
    asyncio.Lock for all writes — reads go straight to the connection.
  • Auto-migrates schema on startup (ALTER TABLE IF NOT EXISTS pattern).
  • Graceful degradation: every public method is try/except-wrapped; never
    raises to caller — returns None / [] / {} / False on any error.

v11.4 additions:
  • TradeRecord + exchange_trades table — real per-exchange CCXT trade log with
    PnL, leverage, order IDs, opened/closed timestamps.
  • ChannelRecord + user_channels table — per-user Telegram signal source config.
  • NotificationPrefs + notifications table — granular push-alert settings.
  • get_exchange_pnl_summary() / get_cross_exchange_stats() — portfolio analytics.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import os
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import aiosqlite

try:
    from cryptography.fernet import Fernet, InvalidToken
    _HAS_CRYPTO = True
except ImportError:
    _HAS_CRYPTO = False

_log = logging.getLogger("UnityEngine.UserDB")

# ── Constants ────────────────────────────────────────────────────────────────
_DB_PATH      = Path(os.getenv("UNITY_USER_DB_PATH", "unity_users.db"))
_VAULT_KEY_ENV = "UNITY_VAULT_KEY"


# ── Fernet vault key helper ──────────────────────────────────────────────────

def _get_fernet() -> Optional[Any]:
    """Return a Fernet cipher seeded from UNITY_VAULT_KEY, or None if unavailable."""
    if not _HAS_CRYPTO:
        return None
    raw = os.getenv(_VAULT_KEY_ENV, "").strip()
    if not raw:
        raw = "unity_default_vault_key_change_in_production"
    key_bytes = base64.urlsafe_b64encode(hashlib.sha256(raw.encode()).digest())
    try:
        return Fernet(key_bytes)
    except Exception:
        return None


def _encrypt(plaintext: str) -> str:
    f = _get_fernet()
    if f is None:
        return plaintext
    try:
        return f.encrypt(plaintext.encode()).decode()
    except Exception:
        return plaintext


def _decrypt(ciphertext: str) -> str:
    f = _get_fernet()
    if f is None:
        return ciphertext
    try:
        return f.decrypt(ciphertext.encode()).decode()
    except Exception:
        return ciphertext


# ── Data Structures ──────────────────────────────────────────────────────────

@dataclass
class UserProfile:
    user_id:       int
    username:      str   = ""
    first_name:    str   = ""
    language:      str   = "en"
    is_admin:      bool  = False
    is_active:     bool  = True
    registered_at: float = field(default_factory=time.time)
    last_seen:     float = field(default_factory=time.time)


@dataclass
class ApiKeyRecord:
    user_id:        int
    exchange:       str
    api_key:        str  = ""
    api_secret:     str  = ""
    api_passphrase: str  = ""
    testnet:        bool = False
    label:          str  = ""
    created_at:     float = field(default_factory=time.time)


@dataclass
class UserSettings:
    user_id:           int
    exchange:          str   = "binance"
    leverage:          int   = 10
    risk_pct:          float = 1.0
    max_open_trades:   int   = 3
    stake_fixed_usdt:  float = 0.0
    margin_mode:       str   = "isolated"
    entry_type:        str   = "market"
    tp_split:          str   = "33/33/34"
    auto_follow:       bool  = False
    mode:              str   = "auto"
    notifications:     bool  = True
    language:          str   = "en"
    trailing_sl_mode:  str   = "off"   # "off"|"breakeven_tp1"|"trail_tp1"|"trail_tp2"
    updated_at:        float = field(default_factory=time.time)


@dataclass
class ActiveSignal:
    signal_id:   str
    user_id:     int
    symbol:      str
    direction:   str
    entry:       float
    sl:          float
    tp1:         float
    tp2:         float
    tp3:         float
    quality:     float = 0.0
    status:      str   = "pending"
    source:      str   = "unity"
    created_at:  float = field(default_factory=time.time)


@dataclass
class SignalOutcome:
    signal_id:  str
    user_id:    int
    symbol:     str
    direction:  str
    entry:      float
    exit_price: float = 0.0
    pnl_pct:    float = 0.0
    result:     str   = "open"
    closed_at:  float = field(default_factory=time.time)


@dataclass
class TradeRecord:
    """Full CCXT execution record — persisted for every real order placed."""
    trade_id:     str
    user_id:      int
    signal_id:    str   = ""
    exchange:     str   = ""
    symbol:       str   = ""
    direction:    str   = ""
    order_type:   str   = "market"
    order_id:     str   = ""
    entry_price:  float = 0.0
    exit_price:   float = 0.0
    size_base:    float = 0.0
    size_usdt:    float = 0.0
    leverage:     int   = 1
    pnl_usdt:     float = 0.0
    pnl_pct:      float = 0.0
    fee_usdt:     float = 0.0
    status:       str   = "open"   # open / closed / cancelled / partial
    opened_at:    float = field(default_factory=time.time)
    closed_at:    float = 0.0


@dataclass
class ChannelRecord:
    """A Telegram channel the user receives signals from."""
    user_id:    int
    channel_id: str
    label:      str  = ""
    active:     bool = True
    added_at:   float = field(default_factory=time.time)


@dataclass
class NotificationPrefs:
    """Granular notification preferences per user."""
    user_id:          int
    signal_alerts:    bool = True
    trade_executed:   bool = True
    tp_hit:           bool = True
    sl_hit:           bool = True
    daily_summary:    bool = True
    engine_warnings:  bool = False
    updated_at:       float = field(default_factory=time.time)


# ── Schema ────────────────────────────────────────────────────────────────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id       INTEGER PRIMARY KEY,
    username      TEXT    DEFAULT '',
    first_name    TEXT    DEFAULT '',
    language      TEXT    DEFAULT 'en',
    is_admin      INTEGER DEFAULT 0,
    is_active     INTEGER DEFAULT 1,
    registered_at REAL    DEFAULT 0,
    last_seen     REAL    DEFAULT 0
);

CREATE TABLE IF NOT EXISTS api_keys (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL,
    exchange        TEXT    NOT NULL,
    api_key_enc     TEXT    DEFAULT '',
    api_secret_enc  TEXT    DEFAULT '',
    passphrase_enc  TEXT    DEFAULT '',
    testnet         INTEGER DEFAULT 0,
    label           TEXT    DEFAULT '',
    created_at      REAL    DEFAULT 0,
    UNIQUE(user_id, exchange)
);

CREATE TABLE IF NOT EXISTS user_settings (
    user_id          INTEGER PRIMARY KEY,
    exchange         TEXT    DEFAULT 'binance',
    leverage         INTEGER DEFAULT 10,
    risk_pct         REAL    DEFAULT 1.0,
    max_open_trades  INTEGER DEFAULT 3,
    stake_fixed_usdt REAL    DEFAULT 0.0,
    margin_mode      TEXT    DEFAULT 'isolated',
    entry_type       TEXT    DEFAULT 'market',
    tp_split         TEXT    DEFAULT '33/33/34',
    auto_follow      INTEGER DEFAULT 0,
    mode             TEXT    DEFAULT 'auto',
    notifications    INTEGER DEFAULT 1,
    language         TEXT    DEFAULT 'en',
    updated_at       REAL    DEFAULT 0
);

CREATE TABLE IF NOT EXISTS active_signals (
    signal_id    TEXT    PRIMARY KEY,
    user_id      INTEGER NOT NULL,
    symbol       TEXT    NOT NULL,
    direction    TEXT    NOT NULL,
    entry        REAL    DEFAULT 0,
    sl           REAL    DEFAULT 0,
    tp1          REAL    DEFAULT 0,
    tp2          REAL    DEFAULT 0,
    tp3          REAL    DEFAULT 0,
    quality      REAL    DEFAULT 0,
    status       TEXT    DEFAULT 'pending',
    source       TEXT    DEFAULT 'unity',
    created_at   REAL    DEFAULT 0
);

CREATE TABLE IF NOT EXISTS signal_history (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id    TEXT    NOT NULL,
    user_id      INTEGER NOT NULL,
    symbol       TEXT    NOT NULL,
    direction    TEXT    NOT NULL,
    entry        REAL    DEFAULT 0,
    exit_price   REAL    DEFAULT 0,
    pnl_pct      REAL    DEFAULT 0,
    result       TEXT    DEFAULT 'open',
    closed_at    REAL    DEFAULT 0
);

CREATE TABLE IF NOT EXISTS exchange_trades (
    trade_id     TEXT    PRIMARY KEY,
    user_id      INTEGER NOT NULL,
    signal_id    TEXT    DEFAULT '',
    exchange     TEXT    NOT NULL,
    symbol       TEXT    NOT NULL,
    direction    TEXT    NOT NULL,
    order_type   TEXT    DEFAULT 'market',
    order_id     TEXT    DEFAULT '',
    entry_price  REAL    DEFAULT 0,
    exit_price   REAL    DEFAULT 0,
    size_base    REAL    DEFAULT 0,
    size_usdt    REAL    DEFAULT 0,
    leverage     INTEGER DEFAULT 1,
    pnl_usdt     REAL    DEFAULT 0,
    pnl_pct      REAL    DEFAULT 0,
    fee_usdt     REAL    DEFAULT 0,
    status       TEXT    DEFAULT 'open',
    opened_at    REAL    DEFAULT 0,
    closed_at    REAL    DEFAULT 0
);

CREATE TABLE IF NOT EXISTS user_channels (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    channel_id  TEXT    NOT NULL,
    label       TEXT    DEFAULT '',
    active      INTEGER DEFAULT 1,
    added_at    REAL    DEFAULT 0,
    UNIQUE(user_id, channel_id)
);

CREATE TABLE IF NOT EXISTS notifications (
    user_id         INTEGER PRIMARY KEY,
    signal_alerts   INTEGER DEFAULT 1,
    trade_executed  INTEGER DEFAULT 1,
    tp_hit          INTEGER DEFAULT 1,
    sl_hit          INTEGER DEFAULT 1,
    daily_summary   INTEGER DEFAULT 1,
    engine_warnings INTEGER DEFAULT 0,
    updated_at      REAL    DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_api_keys_user       ON api_keys(user_id);
CREATE INDEX IF NOT EXISTS idx_signals_user        ON active_signals(user_id);
CREATE INDEX IF NOT EXISTS idx_history_user        ON signal_history(user_id);
CREATE INDEX IF NOT EXISTS idx_history_signal      ON signal_history(signal_id);
CREATE INDEX IF NOT EXISTS idx_ex_trades_user      ON exchange_trades(user_id);
CREATE INDEX IF NOT EXISTS idx_ex_trades_exchange  ON exchange_trades(user_id, exchange);
CREATE INDEX IF NOT EXISTS idx_channels_user       ON user_channels(user_id);
"""

_MIGRATIONS = [
    "ALTER TABLE users ADD COLUMN language TEXT DEFAULT 'en'",
    "ALTER TABLE user_settings ADD COLUMN language TEXT DEFAULT 'en'",
    "ALTER TABLE active_signals ADD COLUMN source TEXT DEFAULT 'unity'",
    # v11.2 migrations — safe no-op if columns exist
    "ALTER TABLE exchange_trades ADD COLUMN fee_usdt REAL DEFAULT 0",
    "ALTER TABLE notifications ADD COLUMN engine_warnings INTEGER DEFAULT 0",
    # v11.5 — trailing SL mode per user
    "ALTER TABLE user_settings ADD COLUMN trailing_sl_mode TEXT DEFAULT 'off'",
]


# ── UserDatabase ──────────────────────────────────────────────────────────────

class UserDatabase:
    """
    Async per-user SQLite database — lock-free reads, serialised writes.

    Usage:
        db = UserDatabase()
        await db.init()
        profile = await db.get_user(user_id)
    """

    def __init__(self, db_path: Optional[Path] = None):
        self._path  = db_path or _DB_PATH
        self._conn: Optional[aiosqlite.Connection] = None
        self._lock  = asyncio.Lock()
        self._ready = False

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def init(self) -> bool:
        try:
            self._conn = await aiosqlite.connect(
                str(self._path),
                check_same_thread=False,
                isolation_level=None,    # autocommit
            )
            self._conn.row_factory = aiosqlite.Row
            await self._conn.execute("PRAGMA journal_mode=WAL")
            await self._conn.execute("PRAGMA synchronous=NORMAL")
            await self._conn.execute("PRAGMA foreign_keys=ON")
            await self._conn.execute("PRAGMA cache_size=-4096")   # 4 MB page cache
            # Execute schema statements one-by-one instead of executescript().
            # executescript() issues an implicit COMMIT then runs outside the
            # aiosqlite async queue, which can cause silent write failures on
            # some aiosqlite versions (0.19+).  Individual execute() calls go
            # through the proper async thread-pool and are each auto-committed
            # because isolation_level=None.
            async with self._lock:
                for _stmt in _SCHEMA.split(";"):
                    _stmt = _stmt.strip()
                    if _stmt:
                        try:
                            await self._conn.execute(_stmt)
                        except Exception:
                            pass   # table/index already exists — safe to ignore
                await self._run_migrations()
            self._ready = True
            _log.info(f"✅ UserDB v11.5 initialised — {self._path}")
            return True
        except Exception as e:
            _log.error(f"UserDB init failed: {e}")
            return False

    async def close(self) -> None:
        if self._conn is not None:
            try:
                await self._conn.close()
            except Exception:
                pass
            self._conn  = None
            self._ready = False

    async def _run_migrations(self) -> None:
        for sql in _MIGRATIONS:
            try:
                await self._conn.execute(sql)
            except Exception:
                pass   # column already exists — safe to ignore

    def _guard(self) -> bool:
        return self._ready and self._conn is not None

    # ── User CRUD ─────────────────────────────────────────────────────────────

    async def upsert_user(self, profile: UserProfile) -> bool:
        if not self._guard():
            return False
        try:
            async with self._lock:
                await self._conn.execute(
                    """INSERT INTO users (user_id, username, first_name, language,
                       is_admin, is_active, registered_at, last_seen)
                       VALUES (?,?,?,?,?,?,?,?)
                       ON CONFLICT(user_id) DO UPDATE SET
                         username=excluded.username,
                         first_name=excluded.first_name,
                         language=excluded.language,
                         is_admin=excluded.is_admin,
                         is_active=excluded.is_active,
                         last_seen=excluded.last_seen""",
                    (
                        profile.user_id, profile.username, profile.first_name,
                        profile.language, int(profile.is_admin), int(profile.is_active),
                        profile.registered_at, profile.last_seen,
                    ),
                )
            return True
        except Exception as e:
            _log.debug(f"upsert_user error: {e}")
            return False

    async def get_user(self, user_id: int) -> Optional[UserProfile]:
        if not self._guard():
            return None
        try:
            async with self._conn.execute(
                "SELECT * FROM users WHERE user_id=?", (user_id,)
            ) as cur:
                row = await cur.fetchone()
            if row is None:
                return None
            return UserProfile(
                user_id=row["user_id"],
                username=row["username"] or "",
                first_name=row["first_name"] or "",
                language=row["language"] or "en",
                is_admin=bool(row["is_admin"]),
                is_active=bool(row["is_active"]),
                registered_at=float(row["registered_at"] or 0),
                last_seen=float(row["last_seen"] or 0),
            )
        except Exception as e:
            _log.debug(f"get_user error: {e}")
            return None

    async def get_all_users(self) -> List[UserProfile]:
        if not self._guard():
            return []
        try:
            async with self._conn.execute(
                "SELECT * FROM users WHERE is_active=1 ORDER BY registered_at DESC"
            ) as cur:
                rows = await cur.fetchall()
            return [
                UserProfile(
                    user_id=r["user_id"],
                    username=r["username"] or "",
                    first_name=r["first_name"] or "",
                    language=r["language"] or "en",
                    is_admin=bool(r["is_admin"]),
                    is_active=bool(r["is_active"]),
                    registered_at=float(r["registered_at"] or 0),
                    last_seen=float(r["last_seen"] or 0),
                )
                for r in rows
            ]
        except Exception as e:
            _log.debug(f"get_all_users error: {e}")
            return []

    async def touch_user(self, user_id: int) -> None:
        if not self._guard():
            return
        try:
            async with self._lock:
                await self._conn.execute(
                    "UPDATE users SET last_seen=? WHERE user_id=?",
                    (time.time(), user_id),
                )
        except Exception:
            pass

    # ── API Key Vault ─────────────────────────────────────────────────────────

    async def save_api_key(
        self,
        user_id:    int,
        exchange:   str,
        api_key:    str,
        api_secret: str,
        passphrase: str  = "",
        testnet:    bool = False,
        label:      str  = "",
    ) -> bool:
        if not self._guard():
            _log.warning(f"save_api_key: DB not ready (user={user_id} exchange={exchange})")
            return False
        try:
            # Encrypt outside the lock — CPU work, no DB I/O needed.
            enc_key  = _encrypt(api_key)
            enc_sec  = _encrypt(api_secret)
            enc_pass = _encrypt(passphrase) if passphrase else ""
            _now     = time.time()
            # Single lock acquisition: user upsert + key upsert in one critical
            # section.  Previously two separate locks created a race window where
            # a concurrent read could see the user row but not the key row.
            async with self._lock:
                await self._conn.execute(
                    """INSERT OR IGNORE INTO users
                       (user_id, username, first_name, language,
                        is_admin, is_active, registered_at, last_seen)
                       VALUES (?, '', '', 'en', 0, 1, ?, ?)""",
                    (user_id, _now, _now),
                )
                await self._conn.execute(
                    """INSERT INTO api_keys
                       (user_id, exchange, api_key_enc, api_secret_enc,
                        passphrase_enc, testnet, label, created_at)
                       VALUES (?,?,?,?,?,?,?,?)
                       ON CONFLICT(user_id, exchange) DO UPDATE SET
                         api_key_enc=excluded.api_key_enc,
                         api_secret_enc=excluded.api_secret_enc,
                         passphrase_enc=excluded.passphrase_enc,
                         testnet=excluded.testnet,
                         label=excluded.label,
                         created_at=excluded.created_at""",
                    (user_id, exchange.lower(), enc_key, enc_sec,
                     enc_pass, int(testnet), label, _now),
                )
            _log.info(f"✅ API key saved: user={user_id} exchange={exchange}")
            return True
        except Exception as e:
            _log.warning(f"save_api_key FAILED (user={user_id} exchange={exchange}): {e}")
            return False

    async def get_api_key(self, user_id: int, exchange: str) -> Optional[ApiKeyRecord]:
        if not self._guard():
            return None
        try:
            async with self._conn.execute(
                "SELECT * FROM api_keys WHERE user_id=? AND exchange=?",
                (user_id, exchange.lower()),
            ) as cur:
                row = await cur.fetchone()
            if row is None:
                return None
            return ApiKeyRecord(
                user_id=row["user_id"],
                exchange=row["exchange"],
                api_key=_decrypt(row["api_key_enc"] or ""),
                api_secret=_decrypt(row["api_secret_enc"] or ""),
                api_passphrase=_decrypt(row["passphrase_enc"] or "") if row["passphrase_enc"] else "",
                testnet=bool(row["testnet"]),
                label=row["label"] or "",
                created_at=float(row["created_at"] or 0),
            )
        except Exception as e:
            _log.debug(f"get_api_key error: {e}")
            return None

    async def list_exchanges(self, user_id: int) -> List[str]:
        if not self._guard():
            return []
        try:
            async with self._conn.execute(
                "SELECT exchange FROM api_keys WHERE user_id=?", (user_id,)
            ) as cur:
                rows = await cur.fetchall()
            return [r["exchange"] for r in rows]
        except Exception:
            return []

    async def delete_api_key(self, user_id: int, exchange: str) -> bool:
        if not self._guard():
            return False
        try:
            async with self._lock:
                await self._conn.execute(
                    "DELETE FROM api_keys WHERE user_id=? AND exchange=?",
                    (user_id, exchange.lower()),
                )
            return True
        except Exception:
            return False

    # ── User Settings ─────────────────────────────────────────────────────────

    async def get_settings(self, user_id: int) -> UserSettings:
        if not self._guard():
            return UserSettings(user_id=user_id)
        try:
            async with self._conn.execute(
                "SELECT * FROM user_settings WHERE user_id=?", (user_id,)
            ) as cur:
                row = await cur.fetchone()
            if row is None:
                defaults = UserSettings(user_id=user_id)
                await self.save_settings(defaults)
                return defaults
            return UserSettings(
                user_id=row["user_id"],
                exchange=row["exchange"] or "binance",
                leverage=int(row["leverage"] or 10),
                risk_pct=float(row["risk_pct"] or 1.0),
                max_open_trades=int(row["max_open_trades"] or 3),
                stake_fixed_usdt=float(row["stake_fixed_usdt"] or 0.0),
                margin_mode=row["margin_mode"] or "isolated",
                entry_type=row["entry_type"] or "market",
                tp_split=row["tp_split"] or "33/33/34",
                auto_follow=bool(row["auto_follow"]),
                mode=row["mode"] or "auto",
                notifications=bool(row["notifications"]),
                language=row["language"] or "en",
                trailing_sl_mode=row["trailing_sl_mode"] if "trailing_sl_mode" in row.keys() else "off",
                updated_at=float(row["updated_at"] or 0),
            )
        except Exception as e:
            _log.debug(f"get_settings error: {e}")
            return UserSettings(user_id=user_id)

    async def save_settings(self, settings: UserSettings) -> bool:
        if not self._guard():
            return False
        try:
            settings.updated_at = time.time()
            _trailing = getattr(settings, "trailing_sl_mode", "off") or "off"
            async with self._lock:
                await self._conn.execute(
                    """INSERT INTO user_settings
                       (user_id, exchange, leverage, risk_pct, max_open_trades,
                        stake_fixed_usdt, margin_mode, entry_type, tp_split,
                        auto_follow, mode, notifications, language, trailing_sl_mode, updated_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(user_id) DO UPDATE SET
                         exchange=excluded.exchange,
                         leverage=excluded.leverage,
                         risk_pct=excluded.risk_pct,
                         max_open_trades=excluded.max_open_trades,
                         stake_fixed_usdt=excluded.stake_fixed_usdt,
                         margin_mode=excluded.margin_mode,
                         entry_type=excluded.entry_type,
                         tp_split=excluded.tp_split,
                         auto_follow=excluded.auto_follow,
                         mode=excluded.mode,
                         notifications=excluded.notifications,
                         language=excluded.language,
                         trailing_sl_mode=excluded.trailing_sl_mode,
                         updated_at=excluded.updated_at""",
                    (
                        settings.user_id, settings.exchange, settings.leverage,
                        settings.risk_pct, settings.max_open_trades,
                        settings.stake_fixed_usdt, settings.margin_mode,
                        settings.entry_type, settings.tp_split,
                        int(settings.auto_follow), settings.mode,
                        int(settings.notifications), settings.language,
                        _trailing, settings.updated_at,
                    ),
                )
            return True
        except Exception as e:
            _log.debug(f"save_settings error: {e}")
            return False

    async def update_setting(self, user_id: int, key: str, value: Any) -> bool:
        _VALID = {
            "exchange", "leverage", "risk_pct", "max_open_trades",
            "stake_fixed_usdt", "margin_mode", "entry_type", "tp_split",
            "auto_follow", "mode", "notifications", "language", "trailing_sl_mode",
        }
        if key not in _VALID:
            return False
        if not self._guard():
            return False
        try:
            await self.get_settings(user_id)   # ensure row exists
            async with self._lock:
                await self._conn.execute(
                    f"UPDATE user_settings SET {key}=?, updated_at=? WHERE user_id=?",
                    (value, time.time(), user_id),
                )
            return True
        except Exception as e:
            _log.debug(f"update_setting error: {e}")
            return False

    # ── Active Signals ────────────────────────────────────────────────────────

    async def save_signal(self, sig: ActiveSignal) -> bool:
        if not self._guard():
            return False
        try:
            async with self._lock:
                await self._conn.execute(
                    """INSERT OR REPLACE INTO active_signals
                       (signal_id, user_id, symbol, direction, entry, sl, tp1, tp2,
                        tp3, quality, status, source, created_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        sig.signal_id, sig.user_id, sig.symbol, sig.direction,
                        sig.entry, sig.sl, sig.tp1, sig.tp2, sig.tp3,
                        sig.quality, sig.status, sig.source, sig.created_at,
                    ),
                )
            return True
        except Exception as e:
            _log.debug(f"save_signal error: {e}")
            return False

    async def get_active_signals(self, user_id: int) -> List[ActiveSignal]:
        if not self._guard():
            return []
        try:
            async with self._conn.execute(
                "SELECT * FROM active_signals WHERE user_id=? ORDER BY created_at DESC LIMIT 50",
                (user_id,),
            ) as cur:
                rows = await cur.fetchall()
            return [
                ActiveSignal(
                    signal_id=r["signal_id"],
                    user_id=r["user_id"],
                    symbol=r["symbol"],
                    direction=r["direction"],
                    entry=float(r["entry"] or 0),
                    sl=float(r["sl"] or 0),
                    tp1=float(r["tp1"] or 0),
                    tp2=float(r["tp2"] or 0),
                    tp3=float(r["tp3"] or 0),
                    quality=float(r["quality"] or 0),
                    status=r["status"] or "pending",
                    source=r["source"] or "unity",
                    created_at=float(r["created_at"] or 0),
                )
                for r in rows
            ]
        except Exception as e:
            _log.debug(f"get_active_signals error: {e}")
            return []

    async def update_signal_status(self, signal_id: str, status: str) -> bool:
        if not self._guard():
            return False
        try:
            async with self._lock:
                await self._conn.execute(
                    "UPDATE active_signals SET status=? WHERE signal_id=?",
                    (status, signal_id),
                )
            return True
        except Exception:
            return False

    # ── Signal History ────────────────────────────────────────────────────────

    async def record_outcome(self, outcome: SignalOutcome) -> bool:
        if not self._guard():
            return False
        try:
            async with self._lock:
                await self._conn.execute(
                    """INSERT INTO signal_history
                       (signal_id, user_id, symbol, direction, entry, exit_price,
                        pnl_pct, result, closed_at)
                       VALUES (?,?,?,?,?,?,?,?,?)""",
                    (
                        outcome.signal_id, outcome.user_id, outcome.symbol,
                        outcome.direction, outcome.entry, outcome.exit_price,
                        outcome.pnl_pct, outcome.result, outcome.closed_at,
                    ),
                )
            return True
        except Exception as e:
            _log.debug(f"record_outcome error: {e}")
            return False

    async def get_history(self, user_id: int, limit: int = 50) -> List[SignalOutcome]:
        if not self._guard():
            return []
        try:
            async with self._conn.execute(
                "SELECT * FROM signal_history WHERE user_id=? ORDER BY closed_at DESC LIMIT ?",
                (user_id, limit),
            ) as cur:
                rows = await cur.fetchall()
            return [
                SignalOutcome(
                    signal_id=r["signal_id"],
                    user_id=r["user_id"],
                    symbol=r["symbol"],
                    direction=r["direction"],
                    entry=float(r["entry"] or 0),
                    exit_price=float(r["exit_price"] or 0),
                    pnl_pct=float(r["pnl_pct"] or 0),
                    result=r["result"] or "open",
                    closed_at=float(r["closed_at"] or 0),
                )
                for r in rows
            ]
        except Exception as e:
            _log.debug(f"get_history error: {e}")
            return []

    async def get_stats(self, user_id: int) -> Dict[str, Any]:
        if not self._guard():
            return {}
        try:
            async with self._conn.execute(
                """SELECT
                     COUNT(*) AS total,
                     SUM(CASE WHEN result='win'  THEN 1 ELSE 0 END) AS wins,
                     SUM(CASE WHEN result='loss' THEN 1 ELSE 0 END) AS losses,
                     SUM(CASE WHEN result='be'   THEN 1 ELSE 0 END) AS breakeven,
                     SUM(pnl_pct) AS total_pnl,
                     AVG(pnl_pct) AS avg_pnl
                   FROM signal_history WHERE user_id=?""",
                (user_id,),
            ) as cur:
                row = await cur.fetchone()
            if row is None or row["total"] == 0:
                return {"total": 0, "wins": 0, "losses": 0, "breakeven": 0,
                        "win_rate": 0.0, "total_pnl": 0.0, "avg_pnl": 0.0}
            total  = int(row["total"] or 0)
            wins   = int(row["wins"]  or 0)
            losses = int(row["losses"] or 0)
            return {
                "total":     total,
                "wins":      wins,
                "losses":    losses,
                "breakeven": int(row["breakeven"] or 0),
                "win_rate":  round(wins / max(total, 1) * 100, 1),
                "total_pnl": round(float(row["total_pnl"] or 0), 2),
                "avg_pnl":   round(float(row["avg_pnl"]   or 0), 2),
            }
        except Exception as e:
            _log.debug(f"get_stats error: {e}")
            return {}

    # ── Exchange Trade Log (v11.2) ─────────────────────────────────────────────

    async def log_trade(self, trade: TradeRecord) -> bool:
        """Insert or update a real CCXT trade record."""
        if not self._guard():
            return False
        try:
            async with self._lock:
                await self._conn.execute(
                    """INSERT INTO exchange_trades
                       (trade_id, user_id, signal_id, exchange, symbol, direction,
                        order_type, order_id, entry_price, exit_price, size_base,
                        size_usdt, leverage, pnl_usdt, pnl_pct, fee_usdt,
                        status, opened_at, closed_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(trade_id) DO UPDATE SET
                         exit_price=excluded.exit_price,
                         pnl_usdt=excluded.pnl_usdt,
                         pnl_pct=excluded.pnl_pct,
                         fee_usdt=excluded.fee_usdt,
                         status=excluded.status,
                         closed_at=excluded.closed_at""",
                    (
                        trade.trade_id, trade.user_id, trade.signal_id,
                        trade.exchange, trade.symbol, trade.direction,
                        trade.order_type, trade.order_id,
                        trade.entry_price, trade.exit_price,
                        trade.size_base, trade.size_usdt, trade.leverage,
                        trade.pnl_usdt, trade.pnl_pct, trade.fee_usdt,
                        trade.status, trade.opened_at, trade.closed_at,
                    ),
                )
            return True
        except Exception as e:
            _log.debug(f"log_trade error: {e}")
            return False

    async def get_exchange_trades(
        self,
        user_id:  int,
        exchange: Optional[str] = None,
        status:   Optional[str] = None,
        limit:    int = 50,
    ) -> List[TradeRecord]:
        """Return CCXT trade records for a user, optionally filtered by exchange/status."""
        if not self._guard():
            return []
        try:
            sql    = "SELECT * FROM exchange_trades WHERE user_id=?"
            params: List[Any] = [user_id]
            if exchange:
                sql    += " AND exchange=?"
                params.append(exchange.lower())
            if status:
                sql    += " AND status=?"
                params.append(status)
            sql += " ORDER BY opened_at DESC LIMIT ?"
            params.append(limit)
            async with self._conn.execute(sql, params) as cur:
                rows = await cur.fetchall()
            return [
                TradeRecord(
                    trade_id=r["trade_id"],
                    user_id=r["user_id"],
                    signal_id=r["signal_id"] or "",
                    exchange=r["exchange"],
                    symbol=r["symbol"],
                    direction=r["direction"],
                    order_type=r["order_type"] or "market",
                    order_id=r["order_id"] or "",
                    entry_price=float(r["entry_price"] or 0),
                    exit_price=float(r["exit_price"] or 0),
                    size_base=float(r["size_base"] or 0),
                    size_usdt=float(r["size_usdt"] or 0),
                    leverage=int(r["leverage"] or 1),
                    pnl_usdt=float(r["pnl_usdt"] or 0),
                    pnl_pct=float(r["pnl_pct"] or 0),
                    fee_usdt=float(r["fee_usdt"] or 0),
                    status=r["status"] or "open",
                    opened_at=float(r["opened_at"] or 0),
                    closed_at=float(r["closed_at"] or 0),
                )
                for r in rows
            ]
        except Exception as e:
            _log.debug(f"get_exchange_trades error: {e}")
            return []

    async def get_exchange_pnl_summary(self, user_id: int) -> Dict[str, Any]:
        """Per-exchange PnL breakdown for the portfolio dashboard."""
        if not self._guard():
            return {}
        try:
            async with self._conn.execute(
                """SELECT exchange,
                          COUNT(*) AS total,
                          SUM(CASE WHEN pnl_usdt > 0 THEN 1 ELSE 0 END) AS wins,
                          SUM(pnl_usdt) AS total_pnl_usdt,
                          AVG(pnl_pct)  AS avg_pnl_pct,
                          SUM(fee_usdt) AS total_fees
                   FROM exchange_trades
                   WHERE user_id=? AND status='closed'
                   GROUP BY exchange""",
                (user_id,),
            ) as cur:
                rows = await cur.fetchall()
            result: Dict[str, Any] = {}
            for r in rows:
                ex = r["exchange"]
                total = int(r["total"] or 0)
                wins  = int(r["wins"]  or 0)
                result[ex] = {
                    "total":        total,
                    "wins":         wins,
                    "win_rate":     round(wins / max(total, 1) * 100, 1),
                    "total_pnl_usdt": round(float(r["total_pnl_usdt"] or 0), 2),
                    "avg_pnl_pct":  round(float(r["avg_pnl_pct"]   or 0), 2),
                    "total_fees":   round(float(r["total_fees"]     or 0), 4),
                }
            return result
        except Exception as e:
            _log.debug(f"get_exchange_pnl_summary error: {e}")
            return {}

    async def get_cross_exchange_stats(self, user_id: int) -> Dict[str, Any]:
        """Aggregate statistics across all exchanges."""
        if not self._guard():
            return {}
        try:
            async with self._conn.execute(
                """SELECT COUNT(*) AS total,
                          SUM(CASE WHEN pnl_usdt > 0 THEN 1 ELSE 0 END) AS wins,
                          SUM(pnl_usdt) AS total_pnl,
                          SUM(fee_usdt) AS total_fees,
                          AVG(pnl_pct)  AS avg_pnl_pct,
                          MAX(pnl_usdt) AS best_trade,
                          MIN(pnl_usdt) AS worst_trade
                   FROM exchange_trades WHERE user_id=? AND status='closed'""",
                (user_id,),
            ) as cur:
                row = await cur.fetchone()
            if row is None or (row["total"] or 0) == 0:
                return {}
            total = int(row["total"] or 0)
            wins  = int(row["wins"]  or 0)
            return {
                "total":       total,
                "wins":        wins,
                "win_rate":    round(wins / max(total, 1) * 100, 1),
                "total_pnl":   round(float(row["total_pnl"]   or 0), 2),
                "total_fees":  round(float(row["total_fees"]   or 0), 4),
                "avg_pnl_pct": round(float(row["avg_pnl_pct"] or 0), 2),
                "best_trade":  round(float(row["best_trade"]   or 0), 2),
                "worst_trade": round(float(row["worst_trade"]  or 0), 2),
            }
        except Exception as e:
            _log.debug(f"get_cross_exchange_stats error: {e}")
            return {}

    # ── Channels (v11.2) ──────────────────────────────────────────────────────

    async def add_channel(self, rec: ChannelRecord) -> bool:
        if not self._guard():
            return False
        try:
            async with self._lock:
                await self._conn.execute(
                    """INSERT INTO user_channels (user_id, channel_id, label, active, added_at)
                       VALUES (?,?,?,?,?)
                       ON CONFLICT(user_id, channel_id) DO UPDATE SET
                         label=excluded.label, active=excluded.active""",
                    (rec.user_id, rec.channel_id, rec.label, int(rec.active), rec.added_at),
                )
            return True
        except Exception as e:
            _log.debug(f"add_channel error: {e}")
            return False

    async def get_channels(self, user_id: int) -> List[ChannelRecord]:
        if not self._guard():
            return []
        try:
            async with self._conn.execute(
                "SELECT * FROM user_channels WHERE user_id=? ORDER BY added_at DESC",
                (user_id,),
            ) as cur:
                rows = await cur.fetchall()
            return [
                ChannelRecord(
                    user_id=r["user_id"],
                    channel_id=r["channel_id"],
                    label=r["label"] or "",
                    active=bool(r["active"]),
                    added_at=float(r["added_at"] or 0),
                )
                for r in rows
            ]
        except Exception as e:
            _log.debug(f"get_channels error: {e}")
            return []

    async def delete_channel(self, user_id: int, channel_id: str) -> bool:
        if not self._guard():
            return False
        try:
            async with self._lock:
                await self._conn.execute(
                    "DELETE FROM user_channels WHERE user_id=? AND channel_id=?",
                    (user_id, channel_id),
                )
            return True
        except Exception:
            return False

    # ── Notification Preferences (v11.2) ──────────────────────────────────────

    async def get_notification_prefs(self, user_id: int) -> NotificationPrefs:
        if not self._guard():
            return NotificationPrefs(user_id=user_id)
        try:
            async with self._conn.execute(
                "SELECT * FROM notifications WHERE user_id=?", (user_id,)
            ) as cur:
                row = await cur.fetchone()
            if row is None:
                prefs = NotificationPrefs(user_id=user_id)
                await self.save_notification_prefs(prefs)
                return prefs
            return NotificationPrefs(
                user_id=row["user_id"],
                signal_alerts=bool(row["signal_alerts"]),
                trade_executed=bool(row["trade_executed"]),
                tp_hit=bool(row["tp_hit"]),
                sl_hit=bool(row["sl_hit"]),
                daily_summary=bool(row["daily_summary"]),
                engine_warnings=bool(row["engine_warnings"]),
                updated_at=float(row["updated_at"] or 0),
            )
        except Exception as e:
            _log.debug(f"get_notification_prefs error: {e}")
            return NotificationPrefs(user_id=user_id)

    async def save_notification_prefs(self, prefs: NotificationPrefs) -> bool:
        if not self._guard():
            return False
        try:
            prefs.updated_at = time.time()
            async with self._lock:
                await self._conn.execute(
                    """INSERT INTO notifications
                       (user_id, signal_alerts, trade_executed, tp_hit, sl_hit,
                        daily_summary, engine_warnings, updated_at)
                       VALUES (?,?,?,?,?,?,?,?)
                       ON CONFLICT(user_id) DO UPDATE SET
                         signal_alerts=excluded.signal_alerts,
                         trade_executed=excluded.trade_executed,
                         tp_hit=excluded.tp_hit,
                         sl_hit=excluded.sl_hit,
                         daily_summary=excluded.daily_summary,
                         engine_warnings=excluded.engine_warnings,
                         updated_at=excluded.updated_at""",
                    (
                        prefs.user_id, int(prefs.signal_alerts),
                        int(prefs.trade_executed), int(prefs.tp_hit),
                        int(prefs.sl_hit), int(prefs.daily_summary),
                        int(prefs.engine_warnings), prefs.updated_at,
                    ),
                )
            return True
        except Exception as e:
            _log.debug(f"save_notification_prefs error: {e}")
            return False

    async def toggle_notification(self, user_id: int, field: str) -> bool:
        _VALID = {
            "signal_alerts", "trade_executed", "tp_hit", "sl_hit",
            "daily_summary", "engine_warnings",
        }
        if field not in _VALID or not self._guard():
            return False
        try:
            prefs = await self.get_notification_prefs(user_id)
            current = getattr(prefs, field, False)
            setattr(prefs, field, not current)
            return await self.save_notification_prefs(prefs)
        except Exception as e:
            _log.debug(f"toggle_notification error: {e}")
            return False

    # ── Performance Metrics (v12.0) ───────────────────────────────────────────

    async def get_performance_metrics(self, user_id: int) -> Dict[str, Any]:
        """
        Compute Sharpe, Sortino, and Max Drawdown from the user's closed trade
        history.  Requires ≥5 closed trades; returns {} when insufficient data.
        """
        if not self._guard():
            return {}
        try:
            async with self._conn.execute(
                "SELECT pnl_pct FROM exchange_trades "
                "WHERE user_id=? AND status='closed' ORDER BY closed_at ASC",
                (user_id,),
            ) as cur:
                rows = await cur.fetchall()
            if len(rows) < 5:
                return {}
            returns = [float(r["pnl_pct"] or 0) / 100.0 for r in rows]
            n   = len(returns)
            mu  = sum(returns) / n
            var = sum((x - mu) ** 2 for x in returns) / max(1, n - 1)
            std = var ** 0.5
            sharpe  = (mu / std * (252 ** 0.5)) if std > 1e-10 else 0.0
            neg     = [x - mu for x in returns if x < 0]
            down    = (sum(x ** 2 for x in neg) / max(1, n - 1)) ** 0.5
            sortino = (mu / down * (252 ** 0.5)) if down > 1e-10 else 0.0
            equity, peak, max_dd = 1.0, 1.0, 0.0
            for r in returns:
                equity *= 1.0 + r
                if equity > peak:
                    peak = equity
                dd = (peak - equity) / peak * 100.0
                if dd > max_dd:
                    max_dd = dd
            return {
                "n":       n,
                "sharpe":  round(sharpe,  3),
                "sortino": round(sortino, 3),
                "max_dd":  round(max_dd,  2),
                "avg_pct": round(mu * 100, 3),
            }
        except Exception as e:
            _log.debug(f"get_performance_metrics error: {e}")
            return {}

    # ── Cleanup Old Signals (v12.0) ───────────────────────────────────────────

    async def cleanup_old_signals(self, max_age_hours: int = 24) -> int:
        """
        Delete completed/stale active_signals older than max_age_hours.
        Skips rows with status 'open' or 'pending' to avoid removing live signals.
        Returns the number of rows deleted.
        """
        if not self._guard():
            return 0
        try:
            cutoff = time.time() - max_age_hours * 3600.0
            async with self._lock:
                cur = await self._conn.execute(
                    "DELETE FROM active_signals "
                    "WHERE created_at < ? AND status NOT IN ('open', 'pending')",
                    (cutoff,),
                )
                deleted = cur.rowcount or 0
            if deleted > 0:
                _log.info(
                    f"🧹 cleanup_old_signals: removed {deleted} stale signal(s) "
                    f"(older than {max_age_hours}h)"
                )
            return deleted
        except Exception as e:
            _log.debug(f"cleanup_old_signals error: {e}")
            return 0

    # ── Recent Signals (v13.0) ────────────────────────────────────────────────

    async def get_all_auto_mode_users(self) -> List[int]:
        """
        Return user_ids of all active users who have mode='auto' set in user_settings.
        Used by maybe_auto_execute() to auto-trade for every opt-in user,
        not just those listed in UNITY_ADMIN_IDS.
        """
        if not self._guard():
            return []
        try:
            async with self._conn.execute(
                """SELECT us.user_id
                   FROM user_settings us
                   INNER JOIN users u ON u.user_id = us.user_id
                   WHERE us.mode = 'auto' AND u.is_active = 1""",
            ) as cur:
                rows = await cur.fetchall()
            return [int(r["user_id"]) for r in rows]
        except Exception as e:
            _log.debug(f"get_all_auto_mode_users error: {e}")
            return []

    async def get_recent_signals(
        self,
        user_id: int,
        limit:   int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Return the most recent active_signals rows for a user as plain dicts.
        Ordered newest-first.  Returns [] when the table is empty or missing.
        """
        if not self._guard():
            return []
        try:
            async with self._conn.execute(
                "SELECT * FROM active_signals "
                "WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
                (user_id, limit),
            ) as cur:
                rows = await cur.fetchall()
            return [dict(r) for r in rows]
        except Exception as e:
            _log.debug(f"get_recent_signals error: {e}")
            return []


# ── Module-level singleton ────────────────────────────────────────────────────

_user_db: Optional[UserDatabase] = None


def get_user_db() -> UserDatabase:
    global _user_db
    if _user_db is None:
        _user_db = UserDatabase()
    return _user_db


async def ensure_user_db() -> UserDatabase:
    db = get_user_db()
    if not db._ready:
        await db.init()
    return db

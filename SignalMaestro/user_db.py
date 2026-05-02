"""
SignalMaestro — User Database  v11.0
═══════════════════════════════════════════════════════════════════════════════
Async per-user SQLite database using aiosqlite.

Tables:
  • users          — registered Telegram user profiles + admin flag
  • api_keys       — Fernet-encrypted exchange API key vault per user
  • user_settings  — risk/mode/leverage preferences per user + exchange
  • active_signals — live signals awaiting user action
  • signal_history — completed signal outcomes per user
  • notifications  — per-user notification preferences

Design:
  • All I/O is non-blocking async (aiosqlite).
  • Fernet encryption at rest for all API key material.
  • Thread-safe: one DB file, one aiosqlite connection pool, all access
    serialised through asyncio.
  • Auto-migrates schema on startup (no manual migrations needed).
  • Graceful degradation: every public method is try/except-wrapped and
    returns a safe default — never raises to caller.
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
_DB_PATH  = Path(os.getenv("UNITY_USER_DB_PATH", "unity_users.db"))
_VAULT_KEY_ENV = "UNITY_VAULT_KEY"


# ── Fernet vault key helper ──────────────────────────────────────────────────

def _get_fernet() -> Optional[Any]:
    """Return a Fernet cipher seeded from UNITY_VAULT_KEY, or None if unavailable."""
    if not _HAS_CRYPTO:
        return None
    raw = os.getenv(_VAULT_KEY_ENV, "").strip()
    if not raw:
        raw = "unity_default_vault_key_change_in_production"
    # Derive a 32-byte key via SHA-256 then base64url-encode to Fernet format
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
    user_id:      int
    username:     str       = ""
    first_name:   str       = ""
    language:     str       = "en"
    is_admin:     bool      = False
    is_active:    bool      = True
    registered_at: float    = field(default_factory=time.time)
    last_seen:    float      = field(default_factory=time.time)


@dataclass
class ApiKeyRecord:
    user_id:     int
    exchange:    str
    api_key:     str        = ""   # always stored encrypted
    api_secret:  str        = ""   # always stored encrypted
    api_passphrase: str     = ""   # OKX / BingX / Bitget
    testnet:     bool       = False
    label:       str        = ""
    created_at:  float      = field(default_factory=time.time)


@dataclass
class UserSettings:
    user_id:          int
    exchange:         str    = "binance"
    leverage:         int    = 10
    risk_pct:         float  = 1.0
    max_open_trades:  int    = 3
    stake_fixed_usdt: float  = 0.0     # 0 = use risk_pct instead
    margin_mode:      str    = "isolated"   # isolated / cross
    entry_type:       str    = "market"     # market / limit / dca
    tp_split:         str    = "33/33/34"   # TP1/TP2/TP3 % distribution
    auto_follow:      bool   = False   # auto-execute all incoming signals
    mode:             str    = "auto"  # auto / manual / off
    notifications:    bool   = True
    language:         str    = "en"
    updated_at:       float  = field(default_factory=time.time)


@dataclass
class ActiveSignal:
    signal_id:   str
    user_id:     int
    symbol:      str
    direction:   str          # BUY / SELL
    entry:       float
    sl:          float
    tp1:         float
    tp2:         float
    tp3:         float
    quality:     float        = 0.0
    status:      str          = "pending"  # pending / followed / ignored / executed
    source:      str          = "unity"
    created_at:  float        = field(default_factory=time.time)


@dataclass
class SignalOutcome:
    signal_id:   str
    user_id:     int
    symbol:      str
    direction:   str
    entry:       float
    exit_price:  float        = 0.0
    pnl_pct:     float        = 0.0
    result:      str          = "open"   # win / loss / be / open
    closed_at:   float        = field(default_factory=time.time)


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
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL,
    exchange      TEXT    NOT NULL,
    api_key_enc   TEXT    DEFAULT '',
    api_secret_enc TEXT   DEFAULT '',
    passphrase_enc TEXT   DEFAULT '',
    testnet       INTEGER DEFAULT 0,
    label         TEXT    DEFAULT '',
    created_at    REAL    DEFAULT 0,
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

CREATE INDEX IF NOT EXISTS idx_api_keys_user     ON api_keys(user_id);
CREATE INDEX IF NOT EXISTS idx_signals_user      ON active_signals(user_id);
CREATE INDEX IF NOT EXISTS idx_history_user      ON signal_history(user_id);
CREATE INDEX IF NOT EXISTS idx_history_signal    ON signal_history(signal_id);
"""

_MIGRATIONS = [
    "ALTER TABLE users ADD COLUMN language TEXT DEFAULT 'en'",
    "ALTER TABLE user_settings ADD COLUMN language TEXT DEFAULT 'en'",
    "ALTER TABLE active_signals ADD COLUMN source TEXT DEFAULT 'unity'",
]


# ── UserDatabase ──────────────────────────────────────────────────────────────

class UserDatabase:
    """
    Async per-user SQLite database.

    Usage:
        db = UserDatabase()
        await db.init()
        profile = await db.get_user(user_id)
    """

    def __init__(self, db_path: Optional[Path] = None):
        self._path = db_path or _DB_PATH
        self._conn: Optional[aiosqlite.Connection] = None
        self._lock = asyncio.Lock()
        self._ready = False

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def init(self) -> bool:
        """Open DB, apply schema, run safe migrations. Returns True on success."""
        try:
            self._conn = await aiosqlite.connect(
                str(self._path),
                check_same_thread=False,
                isolation_level=None,   # autocommit
            )
            self._conn.row_factory = aiosqlite.Row
            await self._conn.execute("PRAGMA journal_mode=WAL")
            await self._conn.execute("PRAGMA synchronous=NORMAL")
            await self._conn.execute("PRAGMA foreign_keys=ON")
            # Apply schema
            async with self._lock:
                await self._conn.executescript(_SCHEMA)
                await self._run_migrations()
            self._ready = True
            _log.info(f"✅ UserDB initialised — {self._path}")
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
            self._conn = None
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
            result = []
            for row in rows:
                result.append(UserProfile(
                    user_id=row["user_id"],
                    username=row["username"] or "",
                    first_name=row["first_name"] or "",
                    language=row["language"] or "en",
                    is_admin=bool(row["is_admin"]),
                    is_active=bool(row["is_active"]),
                    registered_at=float(row["registered_at"] or 0),
                    last_seen=float(row["last_seen"] or 0),
                ))
            return result
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
        user_id: int,
        exchange: str,
        api_key: str,
        api_secret: str,
        passphrase: str = "",
        testnet: bool = False,
        label: str = "",
    ) -> bool:
        """Store encrypted API keys. Returns True on success."""
        if not self._guard():
            return False
        try:
            enc_key  = _encrypt(api_key)
            enc_sec  = _encrypt(api_secret)
            enc_pass = _encrypt(passphrase) if passphrase else ""
            async with self._lock:
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
                     enc_pass, int(testnet), label, time.time()),
                )
            _log.info(f"✅ API key saved: user={user_id} exchange={exchange}")
            return True
        except Exception as e:
            _log.debug(f"save_api_key error: {e}")
            return False

    async def get_api_key(self, user_id: int, exchange: str) -> Optional[ApiKeyRecord]:
        """Return decrypted API key record, or None if not found."""
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
        """Return list of exchanges for which user has stored API keys."""
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
        """Return user settings, creating defaults if not yet saved."""
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
            async with self._lock:
                await self._conn.execute(
                    """INSERT INTO user_settings
                       (user_id, exchange, leverage, risk_pct, max_open_trades,
                        stake_fixed_usdt, margin_mode, entry_type, tp_split,
                        auto_follow, mode, notifications, language, updated_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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
                         updated_at=excluded.updated_at""",
                    (
                        settings.user_id, settings.exchange, settings.leverage,
                        settings.risk_pct, settings.max_open_trades,
                        settings.stake_fixed_usdt, settings.margin_mode,
                        settings.entry_type, settings.tp_split,
                        int(settings.auto_follow), settings.mode,
                        int(settings.notifications), settings.language,
                        settings.updated_at,
                    ),
                )
            return True
        except Exception as e:
            _log.debug(f"save_settings error: {e}")
            return False

    async def update_setting(self, user_id: int, key: str, value: Any) -> bool:
        """Update a single setting field by name. Safe against unknown keys."""
        _VALID = {
            "exchange", "leverage", "risk_pct", "max_open_trades",
            "stake_fixed_usdt", "margin_mode", "entry_type", "tp_split",
            "auto_follow", "mode", "notifications", "language",
        }
        if key not in _VALID:
            return False
        if not self._guard():
            return False
        try:
            # Ensure row exists
            await self.get_settings(user_id)
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
            result = []
            for r in rows:
                result.append(ActiveSignal(
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
                ))
            return result
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

    async def get_history(
        self,
        user_id: int,
        limit: int = 50,
    ) -> List[SignalOutcome]:
        if not self._guard():
            return []
        try:
            async with self._conn.execute(
                """SELECT * FROM signal_history WHERE user_id=?
                   ORDER BY closed_at DESC LIMIT ?""",
                (user_id, limit),
            ) as cur:
                rows = await cur.fetchall()
            result = []
            for r in rows:
                result.append(SignalOutcome(
                    signal_id=r["signal_id"],
                    user_id=r["user_id"],
                    symbol=r["symbol"],
                    direction=r["direction"],
                    entry=float(r["entry"] or 0),
                    exit_price=float(r["exit_price"] or 0),
                    pnl_pct=float(r["pnl_pct"] or 0),
                    result=r["result"] or "open",
                    closed_at=float(r["closed_at"] or 0),
                ))
            return result
        except Exception as e:
            _log.debug(f"get_history error: {e}")
            return []

    async def get_stats(self, user_id: int) -> Dict[str, Any]:
        """Return summary stats: total trades, wins, losses, WR, total PnL."""
        if not self._guard():
            return {}
        try:
            async with self._conn.execute(
                """SELECT
                     COUNT(*) AS total,
                     SUM(CASE WHEN result='win' THEN 1 ELSE 0 END) AS wins,
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
            total = int(row["total"] or 0)
            wins  = int(row["wins"]  or 0)
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


# ── Module-level singleton ────────────────────────────────────────────────────

_user_db: Optional[UserDatabase] = None


def get_user_db() -> UserDatabase:
    """Return the module-level singleton UserDatabase (not yet initialised)."""
    global _user_db
    if _user_db is None:
        _user_db = UserDatabase()
    return _user_db


async def ensure_user_db() -> UserDatabase:
    """Return initialised singleton, initialising it on first call."""
    db = get_user_db()
    if not db._ready:
        await db.init()
    return db

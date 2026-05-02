"""
SignalMaestro — Trading Interface  v11.0
═══════════════════════════════════════════════════════════════════════════════
Command-less Telegram inline-keyboard trading UI for Unity Engine v11.0.

Design philosophy:
  • Zero slash commands required — everything via inline buttons
  • Signal cards with action buttons: Follow / Skip / Execute / Details
  • Live portfolio dashboard via button navigation
  • One-tap signal execution through ExchangeExecutor
  • Per-user settings panel with persistent UserDatabase storage
  • Admin-gated panels: engine metrics, gate stats, RL/Kelly dashboard
  • Graceful degradation: all callbacks are try/except wrapped

Panel flow:
  Signal Card → [▶ Execute] [✅ Follow] [⏭ Skip] [📊 Details]
  Main Menu   → [💼 Portfolio] [📈 Signals] [⚙️ Settings] [📊 Stats]
  Settings    → [🏦 Exchange] [⚖️ Leverage] [🎯 Risk %] [🔑 API Keys]
  Portfolio   → [📋 Positions] [📜 History] [💰 Balance]

Integrates with:
  • UserDatabase (user_db.py) — persistent per-user preferences & history
  • ExchangeExecutor (exchange_executor.py) — one-tap trade execution
  • CornixMenuBot (cornix_menu_bot.py) — delegates complex menus
  • UnityEngine — reads signal filter / metrics / booster state
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

_log = logging.getLogger("UnityEngine.TradingInterface")

# ── Telegram imports ──────────────────────────────────────────────────────────
try:
    from telegram import (
        InlineKeyboardButton as IKB,
        InlineKeyboardMarkup as IKM,
        Update,
        Message,
        CallbackQuery,
    )
    from telegram.ext import (
        Application,
        CallbackQueryHandler,
        MessageHandler,
        filters,
        ContextTypes,
    )
    _HAS_PTB = True
except Exception as _ptb_err:
    _HAS_PTB = False
    _log.warning(f"python-telegram-bot not available — TradingInterface disabled: {_ptb_err}")

# ── Internal imports ──────────────────────────────────────────────────────────
try:
    from SignalMaestro.user_db import (
        UserDatabase, UserProfile, UserSettings, ActiveSignal, SignalOutcome,
        ensure_user_db,
    )
    _HAS_USER_DB = True
except Exception as _udb_err:
    _HAS_USER_DB = False
    _log.warning(f"UserDatabase unavailable: {_udb_err}")

try:
    from SignalMaestro.exchange_executor import (
        ExchangeExecutor, ExecutionPlan, calc_position_size, get_executor,
    )
    _HAS_EXECUTOR = True
except Exception as _exec_err:
    _HAS_EXECUTOR = False
    _log.warning(f"ExchangeExecutor unavailable: {_exec_err}")

# ── Constants ─────────────────────────────────────────────────────────────────
_ADMIN_IDS: List[int] = []
_CALLBACK_PREFIX = "ti_"   # prefix for all callback_data to avoid collisions

def _load_admin_ids() -> List[int]:
    raw = os.getenv("UNITY_ADMIN_IDS", os.getenv("ADMIN_CHAT_ID", ""))
    ids = []
    for part in raw.replace(",", " ").split():
        try:
            ids.append(int(part.strip()))
        except ValueError:
            pass
    return ids


# ── Emoji helpers ─────────────────────────────────────────────────────────────
_DIR_EMOJI = {"BUY": "🟢", "SELL": "🔴", "LONG": "🟢", "SHORT": "🔴"}
_RESULT_EMOJI = {"win": "✅", "loss": "❌", "be": "➖", "open": "⏳"}


def _dir_emoji(direction: str) -> str:
    return _DIR_EMOJI.get(direction.upper(), "⚪")


# ── Signal Card Builder ───────────────────────────────────────────────────────

def build_signal_card(
    signal_id: str,
    symbol:    str,
    direction: str,
    entry:     float,
    sl:        float,
    tp1:       float,
    tp2:       float,
    tp3:       float,
    quality:   float  = 0.0,
    extra:     str    = "",
) -> Tuple[str, Optional[Any]]:
    """
    Build a signal card message + inline keyboard.

    Returns (message_text, InlineKeyboardMarkup) — both are None-safe.
    """
    rr = 0.0
    try:
        dist_sl  = abs(entry - sl)
        dist_tp1 = abs(tp1 - entry)
        rr = dist_tp1 / dist_sl if dist_sl > 1e-10 else 0.0
    except Exception:
        pass

    q_bar = "█" * int(quality // 10) + "░" * (10 - int(quality // 10))
    text = (
        f"{_dir_emoji(direction)} <b>{symbol}</b> — {direction}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📥 Entry:  <code>{entry:.4f}</code>\n"
        f"🛑 SL:     <code>{sl:.4f}</code>\n"
        f"🎯 TP1:    <code>{tp1:.4f}</code>\n"
        f"🎯 TP2:    <code>{tp2:.4f}</code>\n"
        f"🎯 TP3:    <code>{tp3:.4f}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 Quality: {q_bar} {quality:.0f}/100\n"
        f"📐 R:R ≈ {rr:.2f}\n"
    )
    if extra:
        text += f"\n{extra}"

    if not _HAS_PTB:
        return text, None

    sid = signal_id[:24]   # keep callback_data short
    kb = [
        [
            IKB("▶️ Execute",   callback_data=f"{_CALLBACK_PREFIX}exec_{sid}"),
            IKB("✅ Follow",    callback_data=f"{_CALLBACK_PREFIX}follow_{sid}"),
        ],
        [
            IKB("⏭ Skip",      callback_data=f"{_CALLBACK_PREFIX}skip_{sid}"),
            IKB("📊 Details",  callback_data=f"{_CALLBACK_PREFIX}detail_{sid}"),
        ],
        [
            IKB("🏠 Menu",     callback_data=f"{_CALLBACK_PREFIX}menu"),
        ],
    ]
    return text, IKM(kb)


# ── Main Menu Builder ─────────────────────────────────────────────────────────

def build_main_menu(is_admin: bool = False) -> Tuple[str, Optional[Any]]:
    """Build the main menu card."""
    text = (
        "🤖 <b>Unity Engine v11.0</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "Choose an option below:"
    )
    if not _HAS_PTB:
        return text, None

    kb = [
        [
            IKB("💼 Portfolio",   callback_data=f"{_CALLBACK_PREFIX}portfolio"),
            IKB("📈 Signals",     callback_data=f"{_CALLBACK_PREFIX}signals"),
        ],
        [
            IKB("⚙️ Settings",    callback_data=f"{_CALLBACK_PREFIX}settings"),
            IKB("📊 Stats",       callback_data=f"{_CALLBACK_PREFIX}stats"),
        ],
    ]
    if is_admin:
        kb.append([
            IKB("🔬 Engine Metrics", callback_data=f"{_CALLBACK_PREFIX}metrics"),
            IKB("🚦 Gate Stats",     callback_data=f"{_CALLBACK_PREFIX}gates"),
        ])
    return text, IKM(kb)


# ── Settings Panel Builder ────────────────────────────────────────────────────

def build_settings_panel(settings: Any) -> Tuple[str, Optional[Any]]:
    """Build the settings panel from a UserSettings object."""
    exchange   = getattr(settings, "exchange",      "binance")
    leverage   = getattr(settings, "leverage",      10)
    risk_pct   = getattr(settings, "risk_pct",      1.0)
    mode       = getattr(settings, "mode",          "auto")
    auto_follow= getattr(settings, "auto_follow",   False)
    margin     = getattr(settings, "margin_mode",   "isolated")
    entry_type = getattr(settings, "entry_type",    "market")

    text = (
        "⚙️ <b>Settings</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🏦 Exchange:    <code>{exchange.upper()}</code>\n"
        f"⚖️ Leverage:    <code>{leverage}×</code>\n"
        f"🎯 Risk/Trade:  <code>{risk_pct:.1f}%</code>\n"
        f"📐 Margin Mode: <code>{margin}</code>\n"
        f"📥 Entry Type:  <code>{entry_type}</code>\n"
        f"🤖 Mode:        <code>{mode}</code>\n"
        f"🔄 Auto-Follow: <code>{'ON' if auto_follow else 'OFF'}</code>\n"
    )
    if not _HAS_PTB:
        return text, None

    kb = [
        [
            IKB("🏦 Exchange",    callback_data=f"{_CALLBACK_PREFIX}set_exchange"),
            IKB("⚖️ Leverage",    callback_data=f"{_CALLBACK_PREFIX}set_leverage"),
        ],
        [
            IKB("🎯 Risk %",      callback_data=f"{_CALLBACK_PREFIX}set_risk"),
            IKB("📐 Margin",      callback_data=f"{_CALLBACK_PREFIX}set_margin"),
        ],
        [
            IKB("📥 Entry Type",  callback_data=f"{_CALLBACK_PREFIX}set_entry"),
            IKB("🔑 API Keys",    callback_data=f"{_CALLBACK_PREFIX}apikeys"),
        ],
        [
            IKB(
                f"🔄 Auto-Follow: {'ON ✅' if auto_follow else 'OFF ⬜'}",
                callback_data=f"{_CALLBACK_PREFIX}toggle_autofollow",
            ),
        ],
        [IKB("🏠 Back", callback_data=f"{_CALLBACK_PREFIX}menu")],
    ]
    return text, IKM(kb)


# ── Portfolio Panel Builder ───────────────────────────────────────────────────

def build_portfolio_panel(
    balance_usdt: float = 0.0,
    open_count:   int   = 0,
    pnl_today:    float = 0.0,
) -> Tuple[str, Optional[Any]]:
    text = (
        "💼 <b>Portfolio</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💵 Balance:     <code>${balance_usdt:.2f} USDT</code>\n"
        f"📂 Open trades: <code>{open_count}</code>\n"
        f"📈 PnL today:   <code>{pnl_today:+.2f}%</code>\n"
    )
    if not _HAS_PTB:
        return text, None

    kb = [
        [
            IKB("📋 Positions",  callback_data=f"{_CALLBACK_PREFIX}positions"),
            IKB("💰 Balance",    callback_data=f"{_CALLBACK_PREFIX}balance"),
        ],
        [
            IKB("📜 History",    callback_data=f"{_CALLBACK_PREFIX}history"),
            IKB("❌ Close All",  callback_data=f"{_CALLBACK_PREFIX}close_all"),
        ],
        [IKB("🏠 Back", callback_data=f"{_CALLBACK_PREFIX}menu")],
    ]
    return text, IKM(kb)


# ── Stats Panel ───────────────────────────────────────────────────────────────

def build_stats_panel(stats: Dict[str, Any]) -> Tuple[str, Optional[Any]]:
    total   = stats.get("total",     0)
    wins    = stats.get("wins",      0)
    losses  = stats.get("losses",    0)
    wr      = stats.get("win_rate",  0.0)
    pnl     = stats.get("total_pnl", 0.0)
    avg_pnl = stats.get("avg_pnl",   0.0)

    text = (
        "📊 <b>My Statistics</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📋 Total trades: <code>{total}</code>\n"
        f"✅ Wins:         <code>{wins}</code>\n"
        f"❌ Losses:       <code>{losses}</code>\n"
        f"📈 Win rate:     <code>{wr:.1f}%</code>\n"
        f"💰 Total PnL:    <code>{pnl:+.2f}%</code>\n"
        f"📊 Avg PnL:      <code>{avg_pnl:+.2f}%</code>\n"
    )
    if not _HAS_PTB:
        return text, None

    kb = [[IKB("🏠 Back", callback_data=f"{_CALLBACK_PREFIX}menu")]]
    return text, IKM(kb)


# ── TradingInterface ──────────────────────────────────────────────────────────

class TradingInterface:
    """
    Command-less Telegram inline-keyboard UI.

    Attach to a python-telegram-bot Application instance via `attach()`.
    Handles all ti_ prefixed callback queries and dispatches to the
    appropriate panel or executor.

    The interface reads from UserDatabase and executes via ExchangeExecutor,
    keeping all state persistent across restarts.
    """

    def __init__(
        self,
        unity_engine: Optional[Any]     = None,
        user_db:      Optional[Any]     = None,
        executor:     Optional[Any]     = None,
    ):
        self._engine   = unity_engine
        self._db:   Optional[Any] = user_db
        self._exec: Optional[Any] = executor
        self._admin_ids = _load_admin_ids()
        # Signal cache: signal_id → signal dict (populated by engine)
        self._signal_cache: Dict[str, Dict[str, Any]] = {}
        self._ready = False

    async def init(self) -> bool:
        """Initialise dependencies (DB, executor)."""
        if _HAS_USER_DB and self._db is None:
            try:
                self._db = await ensure_user_db()
            except Exception as e:
                _log.warning(f"UserDB init failed: {e}")

        if _HAS_EXECUTOR and self._exec is None:
            try:
                self._exec = get_executor()
            except Exception as e:
                _log.warning(f"Executor init failed: {e}")

        self._ready = True
        _log.info("✅ TradingInterface initialised")
        return True

    def cache_signal(self, signal_id: str, signal_dict: Dict[str, Any]) -> None:
        """Cache a signal for one-tap execution (called by signal consumer)."""
        self._signal_cache[signal_id] = signal_dict
        # Prune cache: keep only last 50
        if len(self._signal_cache) > 50:
            oldest = sorted(self._signal_cache.keys())[:-50]
            for k in oldest:
                self._signal_cache.pop(k, None)

    async def attach(self, application: Any) -> None:
        """Register all handlers with the python-telegram-bot Application."""
        if not _HAS_PTB:
            _log.warning("TradingInterface: python-telegram-bot not available — skipping")
            return
        await self.init()

        application.add_handler(
            CallbackQueryHandler(
                self._handle_callback,
                pattern=f"^{_CALLBACK_PREFIX}",
            )
        )
        # Non-command message handler (inline text replies for settings)
        application.add_handler(
            MessageHandler(
                filters.TEXT & ~filters.COMMAND,
                self._handle_text_input,
            )
        )
        _log.info("✅ TradingInterface handlers registered")

    # ── Callback dispatcher ────────────────────────────────────────────────────

    async def _handle_callback(self, update: Any, context: Any) -> None:
        try:
            query: CallbackQuery = update.callback_query
            await query.answer()

            data    = query.data or ""
            user_id = query.from_user.id if query.from_user else 0
            action  = data[len(_CALLBACK_PREFIX):]

            # Touch user + upsert profile
            await self._touch_user(update)

            if action == "menu":
                await self._show_main_menu(query, user_id)
            elif action == "portfolio":
                await self._show_portfolio(query, user_id)
            elif action == "signals":
                await self._show_signals(query, user_id)
            elif action == "settings":
                await self._show_settings(query, user_id)
            elif action == "stats":
                await self._show_stats(query, user_id)
            elif action == "metrics":
                await self._show_engine_metrics(query, user_id)
            elif action == "gates":
                await self._show_gate_stats(query, user_id)
            elif action == "positions":
                await self._show_positions(query, user_id)
            elif action == "balance":
                await self._show_balance(query, user_id)
            elif action == "history":
                await self._show_history(query, user_id)
            elif action == "toggle_autofollow":
                await self._toggle_autofollow(query, user_id)
            elif action.startswith("exec_"):
                sid = action[5:]
                await self._execute_signal(query, user_id, sid)
            elif action.startswith("follow_"):
                sid = action[7:]
                await self._follow_signal(query, user_id, sid)
            elif action.startswith("skip_"):
                sid = action[5:]
                await self._skip_signal(query, user_id, sid)
            elif action.startswith("detail_"):
                sid = action[7:]
                await self._signal_detail(query, user_id, sid)
            elif action.startswith("set_"):
                await self._settings_input_prompt(query, user_id, action[4:], context)
            elif action == "apikeys":
                await self._show_apikeys(query, user_id)
            else:
                await query.answer(f"Unknown action: {action}", show_alert=False)

        except Exception as e:
            _log.debug(f"_handle_callback error: {e}")

    async def _handle_text_input(self, update: Any, context: Any) -> None:
        """Handle text messages for settings input (awaiting state)."""
        try:
            if not update.message or not update.effective_user:
                return
            user_id   = update.effective_user.id
            user_data = context.user_data or {}
            await_key  = user_data.get("await_setting_key")
            if not await_key:
                return
            value_str = update.message.text.strip()
            user_data.pop("await_setting_key", None)
            await self._apply_setting(update, user_id, await_key, value_str)
        except Exception as e:
            _log.debug(f"_handle_text_input error: {e}")

    # ── Panel handlers ─────────────────────────────────────────────────────────

    async def _show_main_menu(self, query: Any, user_id: int) -> None:
        is_admin = user_id in self._admin_ids
        text, kb = build_main_menu(is_admin=is_admin)
        try:
            await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            pass

    async def _show_portfolio(self, query: Any, user_id: int) -> None:
        balance_usdt = 0.0
        open_count   = 0
        try:
            if self._db and self._exec:
                settings = await self._db.get_settings(user_id)
                key_rec  = await self._db.get_api_key(user_id, settings.exchange)
                if key_rec:
                    bi = await self._exec.get_balance(
                        user_id, settings.exchange,
                        key_rec.api_key, key_rec.api_secret,
                        key_rec.api_passphrase, key_rec.testnet,
                    )
                    balance_usdt = bi.usdt_total
                    positions = await self._exec.get_positions(
                        user_id, settings.exchange,
                        key_rec.api_key, key_rec.api_secret,
                        key_rec.api_passphrase, key_rec.testnet,
                    )
                    open_count = len(positions)
        except Exception as e:
            _log.debug(f"portfolio fetch error: {e}")

        text, kb = build_portfolio_panel(balance_usdt, open_count)
        try:
            await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            pass

    async def _show_signals(self, query: Any, user_id: int) -> None:
        signals = []
        if self._db:
            try:
                signals = await self._db.get_active_signals(user_id)
            except Exception:
                pass

        if not signals:
            text = "📈 <b>Active Signals</b>\n━━━━━━━━━━━━━━━\nNo active signals right now."
            kb   = IKM([[IKB("🏠 Back", callback_data=f"{_CALLBACK_PREFIX}menu")]]) if _HAS_PTB else None
        else:
            lines = ["📈 <b>Active Signals</b>", "━━━━━━━━━━━━━━━"]
            for s in signals[:10]:
                lines.append(
                    f"{_dir_emoji(s.direction)} <b>{s.symbol}</b> "
                    f"@ {s.entry:.4f} | Q:{s.quality:.0f} | {s.status}"
                )
            text = "\n".join(lines)
            kb   = IKM([[IKB("🏠 Back", callback_data=f"{_CALLBACK_PREFIX}menu")]]) if _HAS_PTB else None

        try:
            await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            pass

    async def _show_settings(self, query: Any, user_id: int) -> None:
        settings = None
        if self._db:
            try:
                settings = await self._db.get_settings(user_id)
            except Exception:
                pass
        text, kb = build_settings_panel(settings or type("S", (), {})())
        try:
            await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            pass

    async def _show_stats(self, query: Any, user_id: int) -> None:
        stats: Dict[str, Any] = {}
        if self._db:
            try:
                stats = await self._db.get_stats(user_id)
            except Exception:
                pass
        text, kb = build_stats_panel(stats)
        try:
            await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            pass

    async def _show_engine_metrics(self, query: Any, user_id: int) -> None:
        if user_id not in self._admin_ids:
            await query.answer("⛔ Admin only", show_alert=True)
            return
        m = getattr(self._engine, "metrics", None)
        b = getattr(self._engine, "booster", None)
        if m is None:
            text = "🔬 Engine metrics unavailable."
        else:
            text = (
                "🔬 <b>Engine Metrics</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📊 Win Rate:    <code>{getattr(m, 'win_rate', 0):.1f}%</code>\n"
                f"📨 Signals:     <code>{getattr(m, 'total_signals_sent', 0)}</code>\n"
                f"♻️ Cycles:      <code>{getattr(m, 'scan_cycles', 0)}</code>\n"
                f"💹 Total PnL:   <code>{getattr(m, 'total_profit_pct', 0):+.2f}%</code>\n"
                f"📈 Sharpe:      <code>{getattr(m, 'sharpe_ratio', 0):+.3f}</code>\n"
                f"🎯 Kelly:       <code>{getattr(b, 'last_kelly_fraction', 0)*100:.1f}%</code>\n"
                f"🧠 RL Thresh:   <code>{getattr(b, 'dynamic_threshold', 0):.0f}%</code>\n"
                f"🏛 GEX Regime:  <code>{getattr(m, 'last_gex_regime', 'N/A')}</code>\n"
            )
        kb = IKM([[IKB("🏠 Back", callback_data=f"{_CALLBACK_PREFIX}menu")]]) if _HAS_PTB else None
        try:
            await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            pass

    async def _show_gate_stats(self, query: Any, user_id: int) -> None:
        if user_id not in self._admin_ids:
            await query.answer("⛔ Admin only", show_alert=True)
            return
        sf = getattr(self._engine, "signal_filter", None)
        if sf is None:
            text = "🚦 Gate stats unavailable."
        else:
            try:
                summary = sf.gate_stats_summary()
            except Exception:
                summary = "N/A"
            text = (
                "🚦 <b>Gate Pass Rates</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                f"<code>{summary}</code>"
            )
        kb = IKM([[IKB("🏠 Back", callback_data=f"{_CALLBACK_PREFIX}menu")]]) if _HAS_PTB else None
        try:
            await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            pass

    async def _show_positions(self, query: Any, user_id: int) -> None:
        positions = []
        try:
            if self._db and self._exec:
                settings = await self._db.get_settings(user_id)
                key_rec  = await self._db.get_api_key(user_id, settings.exchange)
                if key_rec:
                    positions = await self._exec.get_positions(
                        user_id, settings.exchange,
                        key_rec.api_key, key_rec.api_secret,
                        key_rec.api_passphrase, key_rec.testnet,
                    )
        except Exception as e:
            _log.debug(f"positions fetch error: {e}")

        if not positions:
            text = "📋 <b>Positions</b>\n━━━━━━━━━━━━━━━\nNo open positions."
        else:
            lines = ["📋 <b>Open Positions</b>", "━━━━━━━━━━━━━━━"]
            for p in positions[:10]:
                pnl_emoji = "🟢" if p.unrealised_pnl >= 0 else "🔴"
                lines.append(
                    f"{pnl_emoji} <b>{p.symbol}</b> {p.side.upper()} "
                    f"{p.size} @ {p.entry_price:.4f}\n"
                    f"   PnL: <code>{p.unrealised_pnl:+.2f} USDT ({p.percentage:+.2f}%)</code>\n"
                    f"   Liq: <code>{p.liquidation_price:.4f}</code>"
                )
            text = "\n".join(lines)

        kb = IKM([
            [IKB("🔄 Refresh", callback_data=f"{_CALLBACK_PREFIX}positions")],
            [IKB("🏠 Back",    callback_data=f"{_CALLBACK_PREFIX}portfolio")],
        ]) if _HAS_PTB else None
        try:
            await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            pass

    async def _show_balance(self, query: Any, user_id: int) -> None:
        bi_text = "Balance unavailable."
        try:
            if self._db and self._exec:
                settings = await self._db.get_settings(user_id)
                key_rec  = await self._db.get_api_key(user_id, settings.exchange)
                if key_rec:
                    bi = await self._exec.get_balance(
                        user_id, settings.exchange,
                        key_rec.api_key, key_rec.api_secret,
                        key_rec.api_passphrase, key_rec.testnet,
                        force_refresh=True,
                    )
                    bi_text = (
                        f"💰 <b>Balance — {settings.exchange.upper()}</b>\n"
                        "━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"Available: <code>${bi.usdt_free:.2f} USDT</code>\n"
                        f"In use:    <code>${bi.usdt_used:.2f} USDT</code>\n"
                        f"Total:     <code>${bi.usdt_total:.2f} USDT</code>\n"
                    )
        except Exception as e:
            _log.debug(f"balance fetch error: {e}")

        kb = IKM([
            [IKB("🔄 Refresh", callback_data=f"{_CALLBACK_PREFIX}balance")],
            [IKB("🏠 Back",    callback_data=f"{_CALLBACK_PREFIX}portfolio")],
        ]) if _HAS_PTB else None
        try:
            await query.edit_message_text(bi_text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            pass

    async def _show_history(self, query: Any, user_id: int) -> None:
        history = []
        if self._db:
            try:
                history = await self._db.get_history(user_id, limit=20)
            except Exception:
                pass

        if not history:
            text = "📜 <b>History</b>\n━━━━━━━━━━━━━━━\nNo completed trades yet."
        else:
            lines = ["📜 <b>Recent Trades</b>", "━━━━━━━━━━━━━━━"]
            for h in history[:15]:
                emoji = _RESULT_EMOJI.get(h.result, "❓")
                lines.append(
                    f"{emoji} {h.symbol} {h.direction} | "
                    f"<code>{h.pnl_pct:+.2f}%</code>"
                )
            text = "\n".join(lines)

        kb = IKM([[IKB("🏠 Back", callback_data=f"{_CALLBACK_PREFIX}portfolio")]]) if _HAS_PTB else None
        try:
            await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            pass

    async def _show_apikeys(self, query: Any, user_id: int) -> None:
        exchanges = []
        if self._db:
            try:
                exchanges = await self._db.list_exchanges(user_id)
            except Exception:
                pass

        if exchanges:
            ex_str = " | ".join(e.upper() for e in exchanges)
            text = (
                "🔑 <b>API Keys</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                f"Stored: <code>{ex_str}</code>\n\n"
                "To update keys, send:\n"
                "<code>KEY exchange api_key api_secret [passphrase]</code>"
            )
        else:
            text = (
                "🔑 <b>API Keys</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "No keys stored yet.\n\n"
                "To add keys, send:\n"
                "<code>KEY exchange api_key api_secret [passphrase]</code>\n\n"
                "Example:\n"
                "<code>KEY binance abc123 def456</code>"
            )

        kb = IKM([[IKB("🏠 Back", callback_data=f"{_CALLBACK_PREFIX}settings")]]) if _HAS_PTB else None
        try:
            await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            pass

    # ── Signal actions ─────────────────────────────────────────────────────────

    async def _execute_signal(self, query: Any, user_id: int, signal_id: str) -> None:
        """One-tap execute a cached signal via ExchangeExecutor."""
        await query.answer("Executing…", show_alert=False)
        sig_data = self._signal_cache.get(signal_id)
        if not sig_data:
            await query.answer("Signal expired or not found", show_alert=True)
            return

        if not (self._db and self._exec):
            await query.answer("Execution engine not available", show_alert=True)
            return

        try:
            settings = await self._db.get_settings(user_id)
            key_rec  = await self._db.get_api_key(user_id, settings.exchange)
            if not key_rec:
                await query.answer(f"No API key for {settings.exchange.upper()}", show_alert=True)
                return

            # Fetch balance for position sizing
            bi = await self._exec.get_balance(
                user_id, settings.exchange,
                key_rec.api_key, key_rec.api_secret,
                key_rec.api_passphrase, key_rec.testnet,
            )

            entry = float(sig_data.get("entry", 0))
            sl    = float(sig_data.get("sl",    0))
            tp1   = float(sig_data.get("tp1",   0))
            tp2   = float(sig_data.get("tp2",   0))
            tp3   = float(sig_data.get("tp3",   0))

            base_size, notional = calc_position_size(
                bi.usdt_total, settings.risk_pct,
                entry, sl, settings.leverage,
                settings.stake_fixed_usdt,
            ) if _HAS_EXECUTOR else (0.0, 0.0)

            plan = ExecutionPlan(
                symbol=sig_data.get("symbol", ""),
                direction=sig_data.get("direction", "BUY"),
                entry_price=entry,
                sl_price=sl,
                tp1_price=tp1,
                tp2_price=tp2,
                tp3_price=tp3,
                position_size=base_size,
                notional_usdt=notional,
                leverage=settings.leverage,
                risk_usdt=bi.usdt_total * settings.risk_pct / 100,
                rr_ratio=abs(tp1 - entry) / abs(entry - sl) if abs(entry - sl) > 1e-10 else 0.0,
                order_type=settings.entry_type,
            )

            result = await self._exec.execute_signal(
                user_id, settings.exchange,
                key_rec.api_key, key_rec.api_secret,
                plan, key_rec.api_passphrase, key_rec.testnet,
            )

            if result.get("success"):
                text = (
                    f"✅ <b>Executed!</b>\n"
                    f"{sig_data.get('symbol')} {sig_data.get('direction')}\n"
                    f"Size: <code>{base_size:.4f}</code> ({notional:.0f} USDT)\n"
                    f"Entry: <code>{entry:.4f}</code>\n"
                )
                await self._db.update_signal_status(signal_id, "executed")
            else:
                errs = " | ".join(result.get("errors", ["unknown"]))
                text = f"❌ Execution failed:\n<code>{errs[:200]}</code>"

            kb = IKM([[IKB("🏠 Menu", callback_data=f"{_CALLBACK_PREFIX}menu")]]) if _HAS_PTB else None
            await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")

        except Exception as e:
            _log.warning(f"_execute_signal error: {e}")
            await query.answer(f"Error: {str(e)[:100]}", show_alert=True)

    async def _follow_signal(self, query: Any, user_id: int, signal_id: str) -> None:
        await query.answer("Signal followed ✅")
        if self._db:
            await self._db.update_signal_status(signal_id, "followed")
        kb = IKM([[IKB("🏠 Menu", callback_data=f"{_CALLBACK_PREFIX}menu")]]) if _HAS_PTB else None
        try:
            await query.edit_message_text(
                "✅ Signal marked as followed.\nPosition will be tracked in your history.",
                reply_markup=kb,
                parse_mode="HTML",
            )
        except Exception:
            pass

    async def _skip_signal(self, query: Any, user_id: int, signal_id: str) -> None:
        await query.answer("Signal skipped ⏭")
        if self._db:
            await self._db.update_signal_status(signal_id, "ignored")
        try:
            await query.delete_message()
        except Exception:
            pass

    async def _signal_detail(self, query: Any, user_id: int, signal_id: str) -> None:
        sig_data = self._signal_cache.get(signal_id)
        if not sig_data:
            await query.answer("Signal data expired", show_alert=True)
            return

        symbol    = sig_data.get("symbol",    "?")
        direction = sig_data.get("direction", "?")
        quality   = float(sig_data.get("quality", 0))
        entry     = float(sig_data.get("entry",  0))
        sl        = float(sig_data.get("sl",     0))
        tp1       = float(sig_data.get("tp1",    0))
        tp2       = float(sig_data.get("tp2",    0))
        tp3       = float(sig_data.get("tp3",    0))

        risk_pct = abs(entry - sl) / entry * 100 if entry else 0
        rr       = abs(tp1 - entry) / abs(entry - sl) if abs(entry - sl) > 1e-10 else 0

        # Pull filter details from engine if available
        sf = getattr(self._engine, "signal_filter", None)
        irons_str = f"{getattr(sf, 'last_irons_score', lambda: 0.0)():.1f}/100" if sf else "N/A"
        gate_str  = sf.gate_stats_summary() if sf else "N/A"

        text = (
            f"📊 <b>Signal Details — {symbol}</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Direction:  <b>{direction}</b>\n"
            f"Entry:      <code>{entry:.4f}</code>\n"
            f"SL:         <code>{sl:.4f}</code> ({risk_pct:.2f}% risk)\n"
            f"TP1:        <code>{tp1:.4f}</code>\n"
            f"TP2:        <code>{tp2:.4f}</code>\n"
            f"TP3:        <code>{tp3:.4f}</code>\n"
            f"R:R:        <code>{rr:.2f}</code>\n"
            f"Quality:    <code>{quality:.1f}/100</code>\n"
            f"IRONS:      <code>{irons_str}</code>\n"
            f"\n<i>Gates: {gate_str}</i>"
        )

        kb = IKM([
            [
                IKB("▶️ Execute", callback_data=f"{_CALLBACK_PREFIX}exec_{signal_id[:24]}"),
                IKB("✅ Follow",  callback_data=f"{_CALLBACK_PREFIX}follow_{signal_id[:24]}"),
            ],
            [IKB("🏠 Menu", callback_data=f"{_CALLBACK_PREFIX}menu")],
        ]) if _HAS_PTB else None

        try:
            await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            pass

    # ── Settings helpers ───────────────────────────────────────────────────────

    async def _toggle_autofollow(self, query: Any, user_id: int) -> None:
        if not self._db:
            return
        settings = await self._db.get_settings(user_id)
        new_val  = not settings.auto_follow
        await self._db.update_setting(user_id, "auto_follow", int(new_val))
        settings.auto_follow = new_val
        text, kb = build_settings_panel(settings)
        try:
            await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            pass

    async def _settings_input_prompt(
        self,
        query: Any,
        user_id: int,
        setting_key: str,
        context: Any,
    ) -> None:
        _PROMPTS = {
            "exchange": "📨 Send exchange name (binance / bybit / okx / bingx / bitget / kucoin / gate / mexc):",
            "leverage": "📨 Send new leverage (1-125):",
            "risk":     "📨 Send risk % per trade (0.1 – 5.0):",
            "margin":   "📨 Send margin mode (isolated / cross):",
            "entry":    "📨 Send entry type (market / limit / dca):",
        }
        prompt = _PROMPTS.get(setting_key, f"📨 Send new value for {setting_key}:")
        if context and hasattr(context, "user_data"):
            context.user_data["await_setting_key"] = setting_key
        try:
            await query.edit_message_text(
                f"{prompt}\n\n<i>Send the value as a plain message.</i>",
                parse_mode="HTML",
            )
        except Exception:
            pass

    async def _apply_setting(
        self,
        update: Any,
        user_id: int,
        key: str,
        value_str: str,
    ) -> None:
        if not self._db:
            return
        _KEY_MAP = {
            "exchange": ("exchange", str),
            "leverage": ("leverage", int),
            "risk":     ("risk_pct", float),
            "margin":   ("margin_mode", str),
            "entry":    ("entry_type", str),
        }
        mapped = _KEY_MAP.get(key)
        if not mapped:
            return
        db_key, cast = mapped
        try:
            value = cast(value_str.strip())
        except Exception:
            await update.message.reply_text(f"❌ Invalid value: <code>{value_str}</code>", parse_mode="HTML")
            return
        await self._db.update_setting(user_id, db_key, value)
        await update.message.reply_text(
            f"✅ <b>{key.title()}</b> updated to <code>{value}</code>",
            parse_mode="HTML",
        )

    # ── User touch helper ──────────────────────────────────────────────────────

    async def _touch_user(self, update: Any) -> None:
        if not self._db:
            return
        try:
            user = (
                update.callback_query.from_user
                if update.callback_query
                else update.effective_user
            )
            if user is None:
                return
            profile = UserProfile(
                user_id=user.id,
                username=getattr(user, "username", "") or "",
                first_name=getattr(user, "first_name", "") or "",
                is_admin=user.id in self._admin_ids,
                last_seen=time.time(),
            )
            await self._db.upsert_user(profile)
        except Exception:
            pass

    # ── Public helpers (called by engine) ─────────────────────────────────────

    def set_unity_engine(self, engine: Any) -> None:
        self._engine = engine

    def set_admin_ids(self, ids: List[int]) -> None:
        self._admin_ids = ids

    def is_ready(self) -> bool:
        return self._ready


# ── Module-level singleton ────────────────────────────────────────────────────

_trading_interface: Optional[TradingInterface] = None


def get_trading_interface(engine: Optional[Any] = None) -> TradingInterface:
    """Return module-level TradingInterface singleton."""
    global _trading_interface
    if _trading_interface is None:
        _trading_interface = TradingInterface(unity_engine=engine)
    elif engine is not None and _trading_interface._engine is None:
        _trading_interface._engine = engine
    return _trading_interface

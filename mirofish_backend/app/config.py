"""
MiroFish Backend — Configuration
Loads from project-root .env (if present) then falls back to environment variables.
Key intelligence: OPENAI_API_KEY is transparently bridged to LLM_API_KEY when the
latter is absent, so existing Replit secrets work without extra setup.
"""

from __future__ import annotations

import os
import secrets
from dotenv import load_dotenv

# ── Load .env from project root (../.. relative to backend/app/config.py) ──
_project_root_env = os.path.join(os.path.dirname(__file__), "../../.env")
if os.path.exists(_project_root_env):
    load_dotenv(_project_root_env, override=True)
else:
    load_dotenv(override=True)

# ── Invisible Unicode character sanitizer (fixes U+200E / U+200F etc.) ──
import unicodedata as _ud

def _sanitize_key(val: str) -> str:
    """Strip invisible formatting characters that break HTTP auth headers."""
    return "".join(
        ch for ch in val
        if _ud.category(ch) not in ("Cf", "Cc", "Cs", "Co", "Cn")
        and ch.isprintable()
    ).strip()


def _clean_env_key(name: str) -> None:
    raw = os.environ.get(name, "")
    if raw:
        clean = _sanitize_key(raw)
        if clean != raw:
            os.environ[name] = clean


# Sanitize all relevant keys in-place before bridging
for _k in ("OPENAI_API_KEY", "LLM_API_KEY", "ZEP_API_KEY", "ANTHROPIC_API_KEY"):
    _clean_env_key(_k)

# ── API key bridge: OPENAI_API_KEY → LLM_API_KEY ──
# Do this at module import time so Config attributes see the bridged value.
if not os.environ.get("LLM_API_KEY"):
    _oai = os.environ.get("OPENAI_API_KEY", "").strip()
    if _oai:
        os.environ["LLM_API_KEY"] = _oai


class Config:
    """Flask configuration — production-safe defaults."""

    # ── Flask ──
    SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
    # Production default: debug off (Werkzeug reloader causes double-threads)
    DEBUG = os.environ.get("FLASK_DEBUG", "False").lower() == "true"

    # ── JSON ──
    JSON_AS_ASCII = False           # Emit CJK chars directly (no \uXXXX escaping)
    JSONIFY_PRETTYPRINT_REGULAR = False

    # ── LLM (OpenAI-compatible) ──
    LLM_API_KEY    = os.environ.get("LLM_API_KEY")       # bridged above if needed
    LLM_BASE_URL   = os.environ.get("LLM_BASE_URL",    "https://api.openai.com/v1")
    LLM_MODEL_NAME = os.environ.get("LLM_MODEL_NAME",  "gpt-4o-mini")

    # ── Zep Cloud (optional — disables graph-memory when absent) ──
    ZEP_API_KEY = os.environ.get("ZEP_API_KEY")

    # ── File upload ──
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024        # 50 MB
    UPLOAD_FOLDER      = os.path.join(os.path.dirname(__file__), "../uploads")
    ALLOWED_EXTENSIONS = {"pdf", "md", "txt", "markdown"}

    # ── Text processing ──
    DEFAULT_CHUNK_SIZE    = int(os.environ.get("CHUNK_SIZE",    "500"))
    DEFAULT_CHUNK_OVERLAP = int(os.environ.get("CHUNK_OVERLAP",  "50"))

    # ── OASIS simulation ──
    OASIS_DEFAULT_MAX_ROUNDS   = int(os.environ.get("OASIS_DEFAULT_MAX_ROUNDS", "10"))
    OASIS_SIMULATION_DATA_DIR  = os.path.join(
        os.path.dirname(__file__), "../uploads/simulations"
    )

    OASIS_TWITTER_ACTIONS = [
        "CREATE_POST", "LIKE_POST", "REPOST", "FOLLOW", "DO_NOTHING", "QUOTE_POST",
    ]
    OASIS_REDDIT_ACTIONS = [
        "LIKE_POST", "DISLIKE_POST", "CREATE_POST", "CREATE_COMMENT",
        "LIKE_COMMENT", "DISLIKE_COMMENT", "SEARCH_POSTS", "SEARCH_USER",
        "TREND", "REFRESH", "DO_NOTHING", "FOLLOW", "MUTE",
    ]

    # ── Report agent ──
    REPORT_AGENT_MAX_TOOL_CALLS       = int(os.environ.get("REPORT_AGENT_MAX_TOOL_CALLS",       "5"))
    REPORT_AGENT_MAX_REFLECTION_ROUNDS = int(os.environ.get("REPORT_AGENT_MAX_REFLECTION_ROUNDS","2"))
    REPORT_AGENT_TEMPERATURE          = float(os.environ.get("REPORT_AGENT_TEMPERATURE",        "0.5"))

    # ── Rate limiting ──
    RATELIMIT_DEFAULT        = os.environ.get("RATELIMIT_DEFAULT",     "200 per hour")
    RATELIMIT_STORAGE_URL    = os.environ.get("RATELIMIT_STORAGE_URL", "memory://")

    @classmethod
    def validate(cls) -> list[str]:
        """Return list of non-fatal configuration warnings."""
        warnings: list[str] = []
        if not cls.LLM_API_KEY:
            warnings.append("LLM_API_KEY 未配置")
        if not cls.ZEP_API_KEY:
            warnings.append("ZEP_API_KEY 未配置")
        return warnings

    @classmethod
    def is_production_ready(cls) -> bool:
        """True when all critical keys are set."""
        return bool(cls.LLM_API_KEY)

    @classmethod
    def dump_safe(cls) -> dict:
        """Return a safe (no secrets) config snapshot for diagnostics."""
        return {
            "DEBUG":            cls.DEBUG,
            "LLM_BASE_URL":     cls.LLM_BASE_URL,
            "LLM_MODEL_NAME":   cls.LLM_MODEL_NAME,
            "LLM_API_KEY":      "✅ set" if cls.LLM_API_KEY else "❌ missing",
            "ZEP_API_KEY":      "✅ set" if cls.ZEP_API_KEY else "⚠️  missing",
            "MAX_CONTENT_LENGTH": cls.MAX_CONTENT_LENGTH,
            "OASIS_MAX_ROUNDS": cls.OASIS_DEFAULT_MAX_ROUNDS,
        }

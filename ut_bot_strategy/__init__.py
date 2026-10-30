"""ut_bot_strategy — UT Bot Alerts + STC signal engine (Unity Engine L2.7)."""

from .engine.signal_engine import SignalEngine, compute_utbot_direction  # noqa: F401

__all__ = ["SignalEngine", "compute_utbot_direction"]

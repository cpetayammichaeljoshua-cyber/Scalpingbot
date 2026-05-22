#!/usr/bin/env python3
"""
Async Circuit Breaker  —  v18.4  (SignalMaestro/async_circuit_breaker.py)
=========================================================================
Standalone 3-state Fowler / Netflix-Hystrix circuit breaker for async coroutines.

Design
------
State machine: CLOSED → OPEN → HALF_OPEN → CLOSED (recovery)

  CLOSED    : calls pass through normally; consecutive failures counted
  OPEN      : calls fast-fail immediately with CircuitOpenError; cooldown runs
  HALF_OPEN : one probe call allowed; success → CLOSED, failure → OPEN (backoff ×2)

Integration
-----------
Use as a standalone decorator on any async function::

    from SignalMaestro.async_circuit_breaker import async_circuit_breaker

    @async_circuit_breaker("deribit_ws", threshold=5, cooldown=60.0)
    async def fetch_deribit_data():
        ...

Or instantiate directly for shared state across multiple callers::

    _cb = AsyncCircuitBreaker("okx_gex", threshold=3, cooldown=30.0)

    async def handler():
        async with _cb:
            ...

The decorator form wraps the decorated coroutine and re-raises the original
exception on failure (never swallows errors — callers see the real cause).
``CircuitOpenError`` is raised when the breaker is OPEN, allowing callers to
fast-path to a fallback without waiting for a network timeout.

Thread / async safety
---------------------
All state mutations are protected by ``asyncio.Lock`` — safe for concurrent
async tasks within a single event loop.  Cross-thread usage is NOT supported
(use threading.Lock separately if needed).

Environment overrides
---------------------
  UNITY_CB_THRESHOLD   — default failure threshold (default: 5)
  UNITY_CB_COOLDOWN    — default cooldown seconds (default: 60.0)
  UNITY_CB_MAX_COOLDOWN— max backoff cap (default: 300.0)
"""

from __future__ import annotations

import asyncio
import enum
import functools
import logging
import os
import time
from typing import Any, Callable, Coroutine, Optional

__all__ = [
    "CircuitBreakerState",
    "CircuitOpenError",
    "AsyncCircuitBreaker",
    "async_circuit_breaker",
]

_LOG = logging.getLogger("UnityEngine.AsyncCB")

_DEFAULT_THRESHOLD  = int(float(os.getenv("UNITY_CB_THRESHOLD",   "5")))
_DEFAULT_COOLDOWN   = float(os.getenv("UNITY_CB_COOLDOWN",         "60.0"))
_DEFAULT_MAX_COOL   = float(os.getenv("UNITY_CB_MAX_COOLDOWN",     "300.0"))


class CircuitBreakerState(enum.Enum):
    """Three-state circuit breaker (Fowler pattern)."""
    CLOSED    = "CLOSED"
    OPEN      = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitOpenError(RuntimeError):
    """Raised when a call is made while the circuit breaker is OPEN."""
    def __init__(self, name: str, retry_after: float):
        self.name        = name
        self.retry_after = retry_after
        super().__init__(
            f"Circuit breaker [{name}] is OPEN — retry after {retry_after:.1f}s"
        )


class AsyncCircuitBreaker:
    """
    Async-native 3-state circuit breaker.

    Parameters
    ----------
    name        : Human-readable label (used in logs and CircuitOpenError).
    threshold   : Consecutive failures before CLOSED → OPEN transition.
    cooldown    : Initial cooldown seconds in OPEN state before HALF_OPEN probe.
    max_cooldown: Upper bound for exponential backoff during repeated failures.
    """

    def __init__(
        self,
        name: str,
        threshold:    int   = _DEFAULT_THRESHOLD,
        cooldown:     float = _DEFAULT_COOLDOWN,
        max_cooldown: float = _DEFAULT_MAX_COOL,
    ) -> None:
        self.name         = name
        self._threshold   = max(1, threshold)
        self._base_cool   = max(1.0, cooldown)
        self._max_cool    = max(self._base_cool, max_cooldown)

        self._state:        CircuitBreakerState = CircuitBreakerState.CLOSED
        self._failures:     int   = 0
        self._cooldown:     float = self._base_cool
        self._open_until:   float = 0.0
        self._probe_active: bool  = False
        self._lock:         asyncio.Lock = asyncio.Lock()

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def state(self) -> CircuitBreakerState:
        return self._state

    @property
    def is_closed(self) -> bool:
        return self._state == CircuitBreakerState.CLOSED

    # ── Context manager (async with _cb) ──────────────────────────────────────

    async def __aenter__(self) -> "AsyncCircuitBreaker":
        await self._check_and_maybe_probe()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> bool:
        if exc_type is None:
            await self._on_success()
        else:
            await self._on_failure()
        return False   # never suppress the exception

    # ── Call wrapper ──────────────────────────────────────────────────────────

    async def call(self, coro: Coroutine) -> Any:
        """Wrap an awaitable with circuit-breaker protection."""
        await self._check_and_maybe_probe()
        try:
            result = await coro
        except Exception:
            await self._on_failure()
            raise
        await self._on_success()
        return result

    # ── Internal state machine ─────────────────────────────────────────────────

    async def _check_and_maybe_probe(self) -> None:
        async with self._lock:
            if self._state == CircuitBreakerState.CLOSED:
                return
            if self._state == CircuitBreakerState.OPEN:
                now = time.monotonic()
                if now < self._open_until:
                    raise CircuitOpenError(self.name, self._open_until - now)
                # Cooldown expired → allow one probe
                self._state = CircuitBreakerState.HALF_OPEN
                self._probe_active = True
                _LOG.info(f"🔶 Circuit breaker HALF_OPEN [{self.name}] — probe starting")
            # HALF_OPEN: allow the one probe through (no blocking)

    async def _on_success(self) -> None:
        async with self._lock:
            if self._state == CircuitBreakerState.HALF_OPEN:
                self._state        = CircuitBreakerState.CLOSED
                self._failures     = 0
                self._cooldown     = self._base_cool
                self._probe_active = False
                _LOG.info(f"✅ Circuit breaker CLOSED [{self.name}] — probe succeeded")
            else:
                self._failures = 0   # reset consecutive-failure window on success

    async def _on_failure(self) -> None:
        async with self._lock:
            self._probe_active = False
            if self._state == CircuitBreakerState.HALF_OPEN:
                # Probe failed → reopen with doubled cooldown
                self._cooldown = min(self._max_cool, self._cooldown * 2)
                self._trip()
                _LOG.warning(
                    f"🔴 Circuit breaker OPEN [{self.name}] — probe failed, "
                    f"backoff {self._cooldown:.0f}s"
                )
            else:
                self._failures += 1
                if self._failures >= self._threshold:
                    self._trip()
                    _LOG.warning(
                        f"🔴 Circuit breaker OPEN [{self.name}] — "
                        f"{self._failures} consecutive failures, "
                        f"cooldown {self._cooldown:.0f}s"
                    )

    def _trip(self) -> None:
        self._state      = CircuitBreakerState.OPEN
        self._open_until = time.monotonic() + self._cooldown

    # ── Representation ────────────────────────────────────────────────────────

    def __repr__(self) -> str:
        return (
            f"AsyncCircuitBreaker(name={self.name!r}, "
            f"state={self._state.value}, "
            f"failures={self._failures}/{self._threshold})"
        )


# ── Decorator ─────────────────────────────────────────────────────────────────

def async_circuit_breaker(
    name:         str,
    threshold:    int   = _DEFAULT_THRESHOLD,
    cooldown:     float = _DEFAULT_COOLDOWN,
    max_cooldown: float = _DEFAULT_MAX_COOL,
) -> Callable:
    """
    Decorator that wraps an async function with circuit-breaker protection.

    Usage::

        @async_circuit_breaker("binance_rest", threshold=5, cooldown=30.0)
        async def fetch_klines(symbol: str):
            ...

    The same ``AsyncCircuitBreaker`` instance is reused across all calls to the
    decorated function (one breaker per decorated function definition).
    ``CircuitOpenError`` is raised (not swallowed) when the breaker is OPEN, so
    callers can catch it and fall back gracefully.
    """
    _cb = AsyncCircuitBreaker(name, threshold=threshold, cooldown=cooldown, max_cooldown=max_cooldown)

    def decorator(fn: Callable[..., Coroutine]) -> Callable:
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs) -> Any:
            return await _cb.call(fn(*args, **kwargs))
        wrapper._circuit_breaker = _cb   # expose for inspection / testing
        return wrapper

    return decorator

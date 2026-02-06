"""Circuit breaker for site-wide outages: stops dequeuing and probes until recovery."""

from __future__ import annotations

import asyncio
from typing import Literal

from page_fetcher.metrics import (
    circuit_breaker_closed_total,
    circuit_breaker_consecutive_failures_gauge,
    circuit_breaker_current_backoff_seconds,
    circuit_breaker_opened_total,
    circuit_breaker_state_gauge,
)

CircuitState = Literal["closed", "open", "half_open"]


class CircuitBreaker:
    """
    Trips after N consecutive site-wide failures.
    Open: sleep with exponential backoff, then transition to half_open.
    Half-open: one probe request; success -> closed, failure -> open (longer backoff).
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        initial_backoff_seconds: float = 30.0,
        max_backoff_seconds: float = 300.0,
        backoff_multiplier: float = 2.0,
    ) -> None:
        self._failure_threshold = failure_threshold
        self._initial_backoff = initial_backoff_seconds
        self._max_backoff = max_backoff_seconds
        self._backoff_multiplier = backoff_multiplier
        self._consecutive_failures = 0
        self._state: CircuitState = "closed"
        self._current_backoff = initial_backoff_seconds
        self._backoff_tier = 0

    @property
    def state(self) -> CircuitState:
        return self._state

    def record_success(self) -> None:
        """Reset failure counter. If half_open, transition to closed."""
        self._consecutive_failures = 0
        if self._state == "half_open":
            self._state = "closed"
            self._current_backoff = self._initial_backoff
            self._backoff_tier = 0
            circuit_breaker_closed_total.inc()
        circuit_breaker_state_gauge.set(_state_to_number(self._state))
        circuit_breaker_consecutive_failures_gauge.set(0)
        circuit_breaker_current_backoff_seconds.set(0)

    def record_site_wide_failure(self) -> None:
        """Increment failure counter. If closed and threshold reached, transition to open."""
        self._consecutive_failures += 1
        circuit_breaker_consecutive_failures_gauge.set(self._consecutive_failures)
        if (
            self._state == "closed"
            and self._consecutive_failures >= self._failure_threshold
        ):
            self._state = "open"
            circuit_breaker_opened_total.inc()
            circuit_breaker_state_gauge.set(_state_to_number(self._state))

    async def wait_if_open(self) -> None:
        """
        If state is open, sleep until current backoff expires, then transition to half_open.
        If already half_open or closed, return immediately.
        """
        if self._state != "open":
            return
        circuit_breaker_current_backoff_seconds.set(self._current_backoff)
        await asyncio.sleep(self._current_backoff)
        self._state = "half_open"
        circuit_breaker_state_gauge.set(_state_to_number(self._state))
        # Next failure will use longer backoff
        self._backoff_tier += 1
        self._current_backoff = min(
            self._initial_backoff * (self._backoff_multiplier**self._backoff_tier),
            self._max_backoff,
        )

    @property
    def should_probe(self) -> bool:
        """True when in half_open state (main loop should try one request)."""
        return self._state == "half_open"

    def record_probe_failure(self) -> None:
        """Called when probe in half_open fails; transition back to open."""
        self._state = "open"
        circuit_breaker_state_gauge.set(_state_to_number(self._state))


def _state_to_number(state: CircuitState) -> int:
    match state:
        case "closed":
            return 0
        case "open":
            return 1
        case "half_open":
            return 2

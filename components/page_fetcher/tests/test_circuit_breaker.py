"""Tests for circuit breaker state machine."""

from __future__ import annotations

import pytest
from page_fetcher.circuit_breaker import CircuitBreaker


@pytest.mark.asyncio
async def test_initial_state_closed() -> None:
    cb = CircuitBreaker(failure_threshold=3)
    assert cb.state == "closed"


@pytest.mark.asyncio
async def test_success_resets_failures() -> None:
    cb = CircuitBreaker(failure_threshold=3)
    cb.record_site_wide_failure()
    cb.record_site_wide_failure()
    cb.record_success()
    assert cb.state == "closed"
    # Consecutive count should be reset (internal)


@pytest.mark.asyncio
async def test_threshold_opens_circuit() -> None:
    cb = CircuitBreaker(failure_threshold=3)
    cb.record_site_wide_failure()
    cb.record_site_wide_failure()
    assert cb.state == "closed"
    cb.record_site_wide_failure()
    assert cb.state == "open"


@pytest.mark.asyncio
async def test_wait_if_open_transitions_to_half_open() -> None:
    cb = CircuitBreaker(
        failure_threshold=1,
        initial_backoff_seconds=0.05,
        max_backoff_seconds=1.0,
    )
    cb.record_site_wide_failure()
    cb.record_site_wide_failure()  # open
    assert cb.state == "open"
    await cb.wait_if_open()
    assert cb.state == "half_open"


@pytest.mark.asyncio
async def test_half_open_success_closes() -> None:
    cb = CircuitBreaker(failure_threshold=2, initial_backoff_seconds=0.01)
    cb.record_site_wide_failure()
    cb.record_site_wide_failure()
    await cb.wait_if_open()
    assert cb.state == "half_open"
    cb.record_success()
    assert cb.state == "closed"


@pytest.mark.asyncio
async def test_should_probe_only_in_half_open() -> None:
    cb = CircuitBreaker(failure_threshold=2, initial_backoff_seconds=0.01)
    assert cb.should_probe == False
    cb.record_site_wide_failure()
    cb.record_site_wide_failure()
    assert cb.should_probe == False
    await cb.wait_if_open()
    assert cb.should_probe == True
    cb.record_success()
    assert cb.should_probe == False

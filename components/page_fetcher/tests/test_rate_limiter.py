"""Tests for Redis-based rate limiter."""

from __future__ import annotations

import time

import pytest
from page_fetcher.rate_limiter import RateLimiter


@pytest.mark.asyncio
async def test_acquire_allows_first_request_immediately(
    redis_url: str,
) -> None:
    limiter = RateLimiter(redis_url, requests_per_second=10.0)
    start = time.monotonic()
    await limiter.acquire("testdomain.com")
    elapsed = time.monotonic() - start
    assert elapsed < 0.5


@pytest.mark.asyncio
async def test_acquire_blocks_second_request_within_interval(
    redis_url: str,
) -> None:
    limiter = RateLimiter(
        redis_url,
        requests_per_second=2.0,  # 1 req per 0.5s
        poll_interval_seconds=0.05,
    )
    await limiter.acquire("blockingtest.com")
    start = time.monotonic()
    await limiter.acquire("blockingtest.com")
    elapsed = time.monotonic() - start
    assert elapsed >= 0.4  # Should have waited ~0.5s

"""Tests for robots.txt checker."""

from __future__ import annotations

import pytest
from core.cache import RedisCache
from page_fetcher.robots import RobotsChecker


@pytest.mark.asyncio
async def test_is_allowed_without_fetcher_defaults_allow(redis_url: str) -> None:
    cache = RedisCache(redis_url)
    checker = RobotsChecker(cache)
    assert await checker.is_allowed("https://example.com/page") is True


@pytest.mark.asyncio
async def test_is_allowed_with_disallow_rule(redis_url: str) -> None:
    cache = RedisCache(redis_url)
    checker = RobotsChecker(cache, user_agent="OttoBot/1.0")
    body = "User-agent: *\nDisallow: /private/"

    async def fetcher(domain: str) -> str | None:
        return body

    checker.set_fetcher(fetcher)
    assert await checker.is_allowed("https://example.com/private/secret") is False
    assert await checker.is_allowed("https://example.com/public/page") is True


@pytest.mark.asyncio
async def test_robots_cached(redis_url: str) -> None:
    cache = RedisCache(redis_url)
    checker = RobotsChecker(cache)
    call_count = 0

    async def fetcher(domain: str) -> str | None:
        nonlocal call_count
        call_count += 1
        return "User-agent: *\nDisallow: "

    checker.set_fetcher(fetcher)
    # Use a unique domain so cache is definitely empty
    await checker.is_allowed("https://cachedtest.example.com/first")
    first_calls = call_count
    await checker.is_allowed("https://cachedtest.example.com/second")
    assert first_calls == 1, "First call should have triggered one fetch"
    assert call_count == 1, "Second call should have used cache (no extra fetch)"

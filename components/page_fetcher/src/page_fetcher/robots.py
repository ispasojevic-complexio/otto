"""robots.txt fetching, parsing, and caching (Redis)."""

from __future__ import annotations

import urllib.robotparser
from typing import Any
from urllib.parse import urlparse

from core.cache import Cache


class RobotsChecker:
    """
    Fetches robots.txt per domain, caches parsed rules in Redis, answers is_allowed(url).
    On fetch failure, defaults to allow (permissive).
    """

    def __init__(
        self,
        cache: Cache,
        cache_ttl_seconds: int = 86400,
        user_agent: str = "OttoBot/1.0",
    ) -> None:
        self._cache = cache
        self._cache_ttl = cache_ttl_seconds
        self._user_agent = user_agent
        self._fetcher: Any = None  # Injected httpx client or fetch callable

    def set_fetcher(self, fetch_robots_txt: Any) -> None:
        """Set async callable(domain: str) -> str | None for fetching robots.txt body."""
        self._fetcher = fetch_robots_txt

    async def is_allowed(self, url: str) -> bool:
        """Return True if robots.txt allows fetching the given URL."""
        parsed = urlparse(url)
        domain = parsed.netloc or parsed.hostname or ""
        if not domain:
            return True
        cache_key = f"robots:{domain}"
        raw = await self._cache.get(cache_key)
        if raw is not None:
            rp = urllib.robotparser.RobotFileParser()
            rp.parse(raw.splitlines())
            return rp.can_fetch(self._user_agent, url)
        # Fetch and cache
        if self._fetcher is None:
            return True
        body = await self._fetcher(domain)
        if body is None:
            return True  # Permissive on failure
        await self._cache.set(cache_key, body, ttl_seconds=self._cache_ttl)
        rp = urllib.robotparser.RobotFileParser()
        rp.parse(body.splitlines())
        return rp.can_fetch(self._user_agent, url)

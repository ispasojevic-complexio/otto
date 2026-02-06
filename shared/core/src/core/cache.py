"""Cache abstraction: key-value store with optional TTL (async)."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Cache(Protocol):
    """Key-value cache. Implementation-agnostic (async)."""

    async def get(self, key: str) -> str | None:
        """Return the value for key, or None if missing."""
        ...

    async def set(
        self,
        key: str,
        value: str,
        ttl_seconds: int | None = None,
    ) -> None:
        """Store value for key. If ttl_seconds is set, the entry expires after that many seconds."""
        ...


class RedisCache:
    """Redis-backed cache with optional TTL."""

    def __init__(self, redis_url: str) -> None:
        from redis.asyncio import Redis

        self._client: Any = Redis.from_url(redis_url, decode_responses=True)

    async def get(self, key: str) -> str | None:
        return await self._client.get(key)

    async def set(
        self,
        key: str,
        value: str,
        ttl_seconds: int | None = None,
    ) -> None:
        if ttl_seconds is not None:
            await self._client.setex(key, ttl_seconds, value)
        else:
            await self._client.set(key, value)

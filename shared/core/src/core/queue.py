"""Queue abstraction: FIFO with optional blocking dequeue (async)."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Queue(Protocol):
    """FIFO queue of string items. Implementation-agnostic (async)."""

    async def enqueue(self, item: str) -> None:
        """Add an item to the tail of the queue."""
        ...

    async def dequeue(self, timeout_seconds: float | None = None) -> str | None:
        """
        Remove and return the item at the head of the queue.

        - If timeout_seconds is None or 0: non-blocking, return None if empty.
        - If timeout_seconds > 0: block up to that many seconds; return None on timeout.
        """
        ...

    async def size(self) -> int:
        """Return the current number of items in the queue."""
        ...


class RedisQueue:
    """Queue implementation backed by a Redis list (FIFO: enqueue at tail, dequeue from head)."""

    def __init__(self, redis_url: str, name: str) -> None:
        from redis.asyncio import Redis

        self._client: Any = Redis.from_url(redis_url, decode_responses=True)
        self._name = name

    async def enqueue(self, item: str) -> None:
        await self._client.rpush(self._name, item)

    async def dequeue(self, timeout_seconds: float | None = None) -> str | None:
        if timeout_seconds is None or timeout_seconds <= 0:
            result = await self._client.lpop(self._name)
            return result
        result = await self._client.blpop(self._name, timeout=timeout_seconds)
        if result is None:
            return None
        _key, value = result
        return value

    async def size(self) -> int:
        return await self._client.llen(self._name)

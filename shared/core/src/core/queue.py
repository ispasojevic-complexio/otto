"""Queue abstraction: FIFO with optional blocking dequeue."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Queue(Protocol):
    """FIFO queue of string items. Implementation-agnostic."""

    def enqueue(self, item: str) -> None:
        """Add an item to the tail of the queue."""
        ...

    def dequeue(self, timeout_seconds: float | None = None) -> str | None:
        """
        Remove and return the item at the head of the queue.

        - If timeout_seconds is None or 0: non-blocking, return None if empty.
        - If timeout_seconds > 0: block up to that many seconds; return None on timeout.
        """
        ...

    def size(self) -> int:
        """Return the current number of items in the queue."""
        ...


class RedisQueue:
    """Queue implementation backed by a Redis list (FIFO: enqueue at tail, dequeue from head)."""

    def __init__(self, redis_url: str, name: str) -> None:
        import redis

        # Treat the Redis client as dynamically typed to avoid tight coupling
        # to redis-py's stubs, which can vary across versions.
        self._client: Any = redis.from_url(redis_url, decode_responses=True)
        self._name = name

    def enqueue(self, item: str) -> None:
        self._client.rpush(self._name, item)

    def dequeue(self, timeout_seconds: float | None = None) -> str | None:
        if timeout_seconds is None or timeout_seconds <= 0:
            result = self._client.lpop(self._name)
            return result
        result = self._client.blpop(self._name, timeout=timeout_seconds)
        if result is None:
            return None
        _key, value = result
        return value

    def size(self) -> int:
        return self._client.llen(self._name)


"""Tests for RedisQueue (near 100% coverage)."""

from __future__ import annotations

import asyncio
import uuid

import pytest
from core.queue import Queue, RedisQueue


@pytest.fixture
def queue(redis_url: str) -> RedisQueue:
    """RedisQueue using the fixture Redis; unique key per test so tests are isolated."""
    return RedisQueue(redis_url, f"core_test_queue_{uuid.uuid4().hex}")


@pytest.mark.asyncio
async def test_redis_queue_implements_queue_protocol(queue: RedisQueue) -> None:
    assert isinstance(queue, Queue)


@pytest.mark.asyncio
async def test_size_empty(queue: RedisQueue) -> None:
    assert await queue.size() == 0


@pytest.mark.asyncio
async def test_dequeue_empty_nonblocking_none(queue: RedisQueue) -> None:
    assert await queue.dequeue() is None
    assert await queue.dequeue(timeout_seconds=0) is None


@pytest.mark.asyncio
async def test_dequeue_empty_blocking_returns_none_after_timeout(
    queue: RedisQueue,
) -> None:
    assert await queue.dequeue(timeout_seconds=0.05) is None


@pytest.mark.asyncio
async def test_enqueue_increases_size(queue: RedisQueue) -> None:
    await queue.enqueue("a")
    assert await queue.size() == 1
    await queue.enqueue("b")
    assert await queue.size() == 2


@pytest.mark.asyncio
async def test_dequeue_returns_item_and_decreases_size(queue: RedisQueue) -> None:
    await queue.enqueue("x")
    assert await queue.size() == 1
    assert await queue.dequeue() == "x"
    assert await queue.size() == 0


@pytest.mark.asyncio
async def test_fifo_order(queue: RedisQueue) -> None:
    await queue.enqueue("first")
    await queue.enqueue("second")
    await queue.enqueue("third")
    assert await queue.dequeue() == "first"
    assert await queue.dequeue() == "second"
    assert await queue.dequeue() == "third"
    assert await queue.dequeue() is None


@pytest.mark.asyncio
async def test_dequeue_blocking_returns_item_when_available(
    queue: RedisQueue,
    redis_url: str,
) -> None:
    result: list[str | None] = []

    async def consumer() -> None:
        r = await queue.dequeue(timeout_seconds=2.0)
        result.append(r)

    task = asyncio.create_task(consumer())
    await asyncio.sleep(0.05)
    await queue.enqueue("from_blocking")
    await task
    assert result == ["from_blocking"]


@pytest.mark.asyncio
async def test_dequeue_blocking_returns_none_on_timeout(
    queue: RedisQueue,
) -> None:
    assert await queue.dequeue(timeout_seconds=0.02) is None


@pytest.mark.asyncio
async def test_isolated_by_name(redis_url: str) -> None:
    q1 = RedisQueue(redis_url, "queue_one")
    q2 = RedisQueue(redis_url, "queue_two")
    await q1.enqueue("in_one")
    await q2.enqueue("in_two")
    assert await q1.size() == 1
    assert await q2.size() == 1
    assert await q1.dequeue() == "in_one"
    assert await q2.dequeue() == "in_two"
    assert await q1.size() == 0
    assert await q2.size() == 0


@pytest.mark.asyncio
async def test_enqueue_dequeue_roundtrip(queue: RedisQueue) -> None:
    await queue.enqueue("item")
    assert await queue.dequeue(timeout_seconds=None) == "item"
    assert await queue.dequeue() is None

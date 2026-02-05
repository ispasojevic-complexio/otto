"""Tests for RedisQueue (near 100% coverage)."""

from __future__ import annotations

import uuid

import pytest
from core.queue import Queue, RedisQueue


@pytest.fixture
def queue(redis_url: str) -> RedisQueue:
    """RedisQueue using the fixture Redis; unique key per test so tests are isolated."""
    return RedisQueue(redis_url, f"core_test_queue_{uuid.uuid4().hex}")


def test_redis_queue_implements_queue_protocol(queue: RedisQueue) -> None:
    assert isinstance(queue, Queue)


def test_size_empty(queue: RedisQueue) -> None:
    assert queue.size() == 0


def test_dequeue_empty_nonblocking_none(queue: RedisQueue) -> None:
    assert queue.dequeue() is None
    assert queue.dequeue(timeout_seconds=0) is None


def test_dequeue_empty_blocking_returns_none_after_timeout(
    queue: RedisQueue,
    redis_client: object,
) -> None:
    assert queue.dequeue(timeout_seconds=0.05) is None


def test_enqueue_increases_size(queue: RedisQueue) -> None:
    queue.enqueue("a")
    assert queue.size() == 1
    queue.enqueue("b")
    assert queue.size() == 2


def test_dequeue_returns_item_and_decreases_size(queue: RedisQueue) -> None:
    queue.enqueue("x")
    assert queue.size() == 1
    assert queue.dequeue() == "x"
    assert queue.size() == 0


def test_fifo_order(queue: RedisQueue) -> None:
    queue.enqueue("first")
    queue.enqueue("second")
    queue.enqueue("third")
    assert queue.dequeue() == "first"
    assert queue.dequeue() == "second"
    assert queue.dequeue() == "third"
    assert queue.dequeue() is None


def test_dequeue_blocking_returns_item_when_available(
    queue: RedisQueue,
    redis_url: str,
) -> None:
    import threading

    result: list[str | None] = []

    def consumer() -> None:
        result.append(queue.dequeue(timeout_seconds=2.0))

    t = threading.Thread(target=consumer)
    t.start()
    queue.enqueue("from_blocking")
    t.join(timeout=3)
    assert result == ["from_blocking"]


def test_dequeue_blocking_returns_none_on_timeout(
    queue: RedisQueue,
) -> None:
    assert queue.dequeue(timeout_seconds=0.02) is None


def test_isolated_by_name(redis_url: str) -> None:
    q1 = RedisQueue(redis_url, "queue_one")
    q2 = RedisQueue(redis_url, "queue_two")
    q1.enqueue("in_one")
    q2.enqueue("in_two")
    assert q1.size() == 1
    assert q2.size() == 1
    assert q1.dequeue() == "in_one"
    assert q2.dequeue() == "in_two"
    assert q1.size() == 0
    assert q2.size() == 0


def test_enqueue_dequeue_roundtrip(queue: RedisQueue) -> None:
    queue.enqueue("item")
    assert queue.dequeue(timeout_seconds=None) == "item"
    assert queue.dequeue() is None

"""Integration tests for scheduler queue operations (Redis / core queue)."""

import pytest
import redis

from config import SchedulerConfig
from core.queue import RedisQueue
from seeds import enqueue_seeds, load_seeds


@pytest.fixture
def config() -> SchedulerConfig:
    return SchedulerConfig(
        redis_url="redis://localhost:6379",  # overridden by redis_url fixture where needed
        input_queue="url_filter_output",
        output_queue="crawler_queue",
        max_queue_size=5,
    )


def test_enqueue_seeds_respects_backpressure(
    redis_client: redis.Redis,
    redis_url: str,
    config: SchedulerConfig,
) -> None:
    # Fill output queue to max_queue_size using raw client
    for _ in range(config.max_queue_size):
        redis_client.rpush(config.output_queue, "https://filled.com/x")
    output_queue = RedisQueue(redis_url, config.output_queue)
    seeds = ["https://a.com", "https://b.com", "https://c.com"]
    n = enqueue_seeds(output_queue, config.max_queue_size, seeds, log_fn=None)
    assert n == 0
    assert redis_client.llen(config.output_queue) == config.max_queue_size


def test_enqueue_seeds_enqueues_until_full(
    redis_client: redis.Redis,
    redis_url: str,
    config: SchedulerConfig,
) -> None:
    output_queue = RedisQueue(redis_url, config.output_queue)
    seeds = ["https://a.com", "https://b.com", "https://c.com", "https://d.com", "https://e.com", "https://f.com"]
    n = enqueue_seeds(output_queue, config.max_queue_size, seeds, log_fn=None)
    assert n == config.max_queue_size
    assert redis_client.llen(config.output_queue) == config.max_queue_size
    for i in range(5):
        assert redis_client.lindex(config.output_queue, i) == seeds[i]


def test_brpop_rpush_ordering(
    redis_client: redis.Redis,
    redis_url: str,
    config: SchedulerConfig,
) -> None:
    input_queue = RedisQueue(redis_url, config.input_queue)
    output_queue = RedisQueue(redis_url, config.output_queue)
    input_queue.enqueue("https://first.com")
    input_queue.enqueue("https://second.com")
    # FIFO: dequeue returns oldest first
    url = input_queue.dequeue(timeout_seconds=1)
    assert url is not None
    assert "first.com" in url
    output_queue.enqueue(url)
    assert output_queue.size() == 1
    assert input_queue.size() == 1

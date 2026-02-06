"""Integration tests for scheduler queue operations (Redis / core queue)."""

import pytest
from core.queue import RedisQueue
from crawler_scheduler.config import SchedulerConfig
from crawler_scheduler.seeds import enqueue_seeds, load_seeds
from redis.asyncio import Redis  # type: ignore[attr-defined]


@pytest.fixture
def config() -> SchedulerConfig:
    return SchedulerConfig(
        redis_url="redis://localhost:6379",  # overridden by redis_url fixture where needed
        input_queue="url_filter_output",
        output_queue="crawler_queue",
        max_queue_size=5,
    )


@pytest.mark.asyncio
async def test_enqueue_seeds_respects_backpressure(
    redis_client: Redis,
    redis_url: str,
    config: SchedulerConfig,
) -> None:
    # Fill output queue to max_queue_size using raw client
    for _ in range(config.max_queue_size):
        await redis_client.rpush(config.output_queue, "https://filled.com/x")  # type: ignore[union-attr]
    output_queue = RedisQueue(redis_url, config.output_queue)
    seeds = ["https://a.com", "https://b.com", "https://c.com"]
    n = await enqueue_seeds(output_queue, config.max_queue_size, seeds, log_fn=None)
    assert n == 0
    assert await redis_client.llen(config.output_queue) == config.max_queue_size  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_enqueue_seeds_enqueues_until_full(
    redis_client: Redis,
    redis_url: str,
    config: SchedulerConfig,
) -> None:
    output_queue = RedisQueue(redis_url, config.output_queue)
    seeds = [
        "https://a.com",
        "https://b.com",
        "https://c.com",
        "https://d.com",
        "https://e.com",
        "https://f.com",
    ]
    n = await enqueue_seeds(output_queue, config.max_queue_size, seeds, log_fn=None)
    assert n == config.max_queue_size
    assert await redis_client.llen(config.output_queue) == config.max_queue_size  # type: ignore[union-attr]
    for i in range(5):
        assert await redis_client.lindex(config.output_queue, i) == seeds[i]  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_brpop_rpush_ordering(
    redis_url: str,
    config: SchedulerConfig,
) -> None:
    input_queue = RedisQueue(redis_url, config.input_queue)
    output_queue = RedisQueue(redis_url, config.output_queue)
    await input_queue.enqueue("https://first.com")
    await input_queue.enqueue("https://second.com")
    # FIFO: dequeue returns oldest first
    url = await input_queue.dequeue(timeout_seconds=1)
    assert url is not None
    assert "first.com" in url
    await output_queue.enqueue(url)
    assert await output_queue.size() == 1
    assert await input_queue.size() == 1

"""Integration tests for scheduler queue operations (Redis)."""

import pytest
import redis
from testcontainers.redis import RedisContainer

from config import SchedulerConfig
from seeds import enqueue_seeds, load_seeds

@pytest.fixture(scope="module")
def redis_container() -> RedisContainer:
    try:
        container = RedisContainer("redis:7-alpine")
        with container:
            yield container
    except Exception as e:
        pytest.skip(f"Docker not available: {e}")


@pytest.fixture
def redis_client(redis_container: RedisContainer):
    # Use decode_responses=True to match production (main.py uses it)
    url = getattr(redis_container, "get_connection_url", None)
    if url:
        url = url()
    else:
        host = redis_container.get_container_host_ip()
        port = redis_container.get_exposed_port(6379)
        url = f"redis://{host}:{port}"
    client = redis.from_url(url, decode_responses=True)
    yield client
    client.flushdb()


@pytest.fixture
def config() -> SchedulerConfig:
    return SchedulerConfig(
        redis_url="redis://localhost:6379",  # overridden by fixture URL
        input_queue="url_filter_output",
        output_queue="crawler_queue",
        max_queue_size=5,
    )


def test_enqueue_seeds_respects_backpressure(
    redis_client: redis.Redis,
    config: SchedulerConfig,
) -> None:
    # Fill output queue to max_queue_size
    for _ in range(config.max_queue_size):
        redis_client.rpush(config.output_queue, "https://filled.com/x")
    seeds = ["https://a.com", "https://b.com", "https://c.com"]
    n = enqueue_seeds(redis_client, config, seeds, log_fn=None)
    assert n == 0
    assert redis_client.llen(config.output_queue) == config.max_queue_size


def test_enqueue_seeds_enqueues_until_full(
    redis_client: redis.Redis,
    config: SchedulerConfig,
) -> None:
    seeds = ["https://a.com", "https://b.com", "https://c.com", "https://d.com", "https://e.com", "https://f.com"]
    n = enqueue_seeds(redis_client, config, seeds, log_fn=None)
    assert n == config.max_queue_size
    assert redis_client.llen(config.output_queue) == config.max_queue_size
    # First 5 should be in queue in order
    for i in range(5):
        assert redis_client.lindex(config.output_queue, i) == seeds[i]


def test_brpop_rpush_ordering(
    redis_client: redis.Redis,
    config: SchedulerConfig,
) -> None:
    redis_client.rpush(config.input_queue, "https://first.com", "https://second.com")
    # BRPOP returns rightmost (last pushed); one iteration: pop then push to output
    result = redis_client.brpop(config.input_queue, timeout=1)
    assert result is not None
    _q, url = result
    assert "second.com" in url
    redis_client.rpush(config.output_queue, url)
    assert redis_client.llen(config.output_queue) == 1
    assert redis_client.llen(config.input_queue) == 1

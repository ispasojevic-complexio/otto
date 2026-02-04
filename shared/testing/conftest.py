"""Shared pytest fixtures (Redis container, client, etc.)."""

from __future__ import annotations

import pytest
import redis
from testcontainers.redis import RedisContainer


@pytest.fixture(scope="session")
def redis_container() -> RedisContainer:
    """Start a Redis container for the test session. Skips if Docker is unavailable."""
    try:
        container = RedisContainer("redis:7-alpine")
        with container:
            yield container
    except Exception as e:
        pytest.skip(f"Docker not available: {e}")


@pytest.fixture
def redis_client(redis_container: RedisContainer) -> redis.Redis[str]:
    """Return a Redis client connected to the session Redis container (decode_responses=True). Flushes DB after each test."""
    url = getattr(redis_container, "get_connection_url", None)
    if callable(url):
        url = url()
    else:
        host = redis_container.get_container_host_ip()
        port = redis_container.get_exposed_port(6379)
        url = f"redis://{host}:{port}"
    client: redis.Redis[str] = redis.from_url(url, decode_responses=True)
    yield client
    client.flushdb()

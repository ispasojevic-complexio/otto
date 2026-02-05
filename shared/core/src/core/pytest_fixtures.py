"""Shared pytest fixtures (Redis container, client, URL, etc.)."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

import pytest
import redis
from testcontainers.redis import RedisContainer


def _redis_url_from_container(redis_container: RedisContainer) -> str:
    url_attr = getattr(redis_container, "get_connection_url", None)
    if callable(url_attr):
        # testcontainers types are not precise; we know this is a string URL.
        return str(url_attr())
    host = redis_container.get_container_host_ip()
    port = redis_container.get_exposed_port(6379)
    return f"redis://{host}:{port}"


@pytest.fixture(scope="session")
def redis_container() -> Generator[RedisContainer, None, None]:
    """Start a Redis container for the test session. Skips if Docker is unavailable."""
    try:
        container = RedisContainer("redis:7-alpine")
        with container:
            yield container
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"Docker not available: {e}")


@pytest.fixture
def redis_url(redis_container: RedisContainer) -> str:
    """Connection URL for the session Redis container (for core.RedisQueue, etc.)."""
    return _redis_url_from_container(redis_container)


@pytest.fixture
def redis_client(redis_container: RedisContainer) -> Generator[redis.Redis, None, None]:
    """Return a Redis client connected to the session Redis container (decode_responses=True). Flushes DB after each test."""
    url = _redis_url_from_container(redis_container)
    client: redis.Redis = redis.from_url(url, decode_responses=True)
    yield client
    # Be liberal about the client type; this is test-only code.
    getattr(client, "flushdb", lambda: None)()

"""Shared pytest fixtures (Redis container, async client, URL, etc.)."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Generator
from typing import Any

import pytest
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
async def redis_client(
    redis_container: RedisContainer,
) -> AsyncGenerator[Any, None]:
    """Async Redis client (decode_responses=True). Flushes DB after each test."""
    from redis.asyncio import Redis

    url = _redis_url_from_container(redis_container)
    client = Redis.from_url(url, decode_responses=True)
    yield client
    await client.flushdb()
    await client.aclose()

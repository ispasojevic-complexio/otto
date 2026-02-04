# Otto

Car sales analytics platform: crawls [polovniautomobili.com](https://www.polovniautomobili.com), processes ad data through an event-driven pipeline, and provides insights via an AI chatbot.

See [spec.md](spec.md) for the high-level architecture and [implementation_plan.md](implementation_plan.md) for the full implementation specification.

## Core package

The **core** package ([shared/core/](shared/core/)) provides common interfaces and implementations used across components. Components depend on **otto-core** instead of specific backends.

- **Queue**: FIFO string queue with `enqueue`, `dequeue` (optional blocking), and `size`. Implementation-agnostic; the only implementation today is **Redis** ([shared/core/core/queue.py](shared/core/core/queue.py)).
- **Redis** is a production dependency of **core** only; no other package declares it. Use the queue abstraction in components; use `RedisQueue(redis_url, queue_name)` when configuring.

Shared testing ([shared/testing](shared/testing)) stays separate from core: it provides pytest fixtures (e.g. Redis container, client, `redis_url`) for integration tests. Tests can use the same queue abstraction via `RedisQueue(redis_url, name)` against the fixture Redis.

## Development setup

- **Python**: 3.12+
- **Package manager**: [uv](https://docs.astral.sh/uv/)

```bash
uv sync
```

## Testing

Tests are run from the **repository root**. Pytest and testcontainers are provided at the monorepo level (see root [pyproject.toml](pyproject.toml)); components do not declare them.

### Running tests

Run tests from the repo root. Use `--project` so the component’s dependencies are available:

```bash
# All tests (run each component’s tests with its project)
uv run pytest
# Or for a single component:
uv run --project components/crawler_scheduler pytest components/crawler_scheduler/tests/ -v

# A single file or test
uv run --project components/crawler_scheduler pytest components/crawler_scheduler/tests/test_seeds.py -v
```

Pytest and testcontainers are installed at the monorepo level only; components do not declare them.

### Shared testing framework

The monorepo provides shared pytest fixtures so components can reuse the same test infrastructure without duplicating dependencies.

- **Where**: [conftest.py](conftest.py) at the root loads the shared plugin from **`shared/testing`**.
- **Fixtures** (defined in [shared/testing/conftest.py](shared/testing/conftest.py)):
  - **`redis_container`** (session-scoped): Starts a Redis 7 Alpine container via testcontainers. Skips the test session if Docker is unavailable.
  - **`redis_url`**: Connection URL for that container (e.g. for `RedisQueue(redis_url, name)`).
  - **`redis_client`**: A Redis client connected to that container with `decode_responses=True`. The DB is flushed after each test.

Any component test can request `redis_client` (or `redis_container`) in its signature; no extra setup is required. Add component-specific fixtures in the component’s own `tests/conftest.py`.

Integration tests that need Docker will be skipped when Docker is not available (e.g. in CI without Docker).

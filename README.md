# Otto

Car sales analytics platform: crawls [polovniautomobili.com](https://www.polovniautomobili.com), processes ad data through an event-driven pipeline, and provides insights via an AI chatbot.

See [spec.md](spec.md) for the high-level architecture and [implementation_plan.md](implementation_plan.md) for the full implementation specification.

## Core package (shared/core)

The **core** package ([shared/core/](shared/core/)) is the single shared package for the monorepo. It provides:

- **Production**: Common interfaces and implementations used by components.
  - **Queue**: FIFO string queue with `enqueue`, `dequeue` (optional blocking), and `size`. Implementation-agnostic; the only implementation is **Redis** ([shared/core/src/core/queue.py](shared/core/src/core/queue.py)).
  - **Redis** is a production dependency of **core** only; no other package declares it. Use the queue abstraction in components; use `RedisQueue(redis_url, queue_name)` when configuring.
- **Testing**: Shared pytest fixtures so component and core tests share the same test infrastructure (no duplicate pytest/testcontainers/redis).
  - Fixtures live in [shared/core/pytest_fixtures.py](shared/core/pytest_fixtures.py): **`redis_container`** (session), **`redis_url`**, **`redis_client`** (flushes DB after each test).
  - The root [conftest.py](conftest.py) loads them via `pytest_plugins = ["core.pytest_fixtures"]`. Any component test can request `redis_url` or `redis_client`; use `RedisQueue(redis_url, name)` for queue tests.

## Development setup

- **Python**: 3.12+
- **Package manager**: [uv](https://docs.astral.sh/uv/)

```bash
uv sync
```

### Pre-commit

Pre-commit hooks run on every commit (install once with `uv run pre-commit install`):

1. **pyrefly** – typecheck the whole project
2. **ruff** – format code (default settings) and sort imports (isort)

Run manually: `uv run pre-commit run --all-files`. Ruff config is in root [pyproject.toml](pyproject.toml) under `[tool.ruff]`.

## Testing

Tests are run from the **repository root**. Pytest and testcontainers are provided at the monorepo level (see root [pyproject.toml](pyproject.toml)); components do not declare them. The **core** package declares them as dev dependencies for its own tests and for the shared fixtures.

### Running tests

Run tests from the repo root. Use `--project` so the component’s (or core’s) dependencies are available:

```bash
# Core (queue + fixtures)
uv run --project shared/core pytest shared/core/tests/ -v

# A component
uv run --project components/crawler_scheduler pytest components/crawler_scheduler/tests/ -v

# With coverage (core)
uv run --project shared/core pytest shared/core/tests/ --cov=core.queue --cov-report=term-missing
```

### Shared fixtures

- **Where**: [conftest.py](conftest.py) at the root loads **`core.pytest_fixtures`**.
- **Fixtures** (in [shared/core/src/core/pytest_fixtures.py](shared/core/src/core/pytest_fixtures.py)):
  - **`redis_container`** (session-scoped): Redis 7 Alpine via testcontainers. Skips if Docker is unavailable.
  - **`redis_url`**: Connection URL for that container (e.g. for `RedisQueue(redis_url, name)`).
  - **`redis_client`**: Redis client with `decode_responses=True`. DB is flushed after each test.

Add component-specific fixtures in the component’s own `tests/conftest.py`. Integration tests that need Docker are skipped when Docker is not available.

# Crawler Scheduler Implementation Plan

## Scope and decisions

- FIFO only; no priority levels or dedupe in scheduler (URL Filter remains the dedupe gate).
- Redis is the only persistence/checkpointing mechanism; queue state lives in Redis.
- Initial seed URLs come from a static config file in repo.

## Key files

- Service code: `main.py`
- Config: `config.py`
- Seed loader: `seeds.py`
- Metrics: `metrics.py`
- Component README/spec: `README.md`
- Seed config: `seeds.yaml`
- Tests: `tests/`
- Dependencies: `pyproject.toml`

## Design

- **Input queue**: `url_filter_output` (Redis list) using BRPOP for blocking consumption.
- **Output queue**: `crawler_queue` (Redis list) using RPUSH.
- **Seed ingestion**: read `seeds.yaml` on startup and enqueue once (no dedupe).
- **Backpressure**: enforce `MAX_QUEUE_SIZE`; re-queue to input when output is full.
- **Observability**: structured JSON logs, Prometheus metrics.

## Implementation steps (done)

1. Configuration model and defaults (`config.py`, Pydantic settings).
2. Seed loader and startup enqueue (`seeds.py`, `seeds.yaml`, called from `main.py`).
3. Scheduler loop with backpressure and graceful shutdown (`main.py`).
4. Structured logging and Prometheus metrics (`main.py`, `metrics.py`).
5. README with configuration, queues, and operational behavior.
6. Unit and integration tests (`tests/`).
7. Dependencies in `pyproject.toml`: redis, pydantic, pydantic-settings, pyyaml, prometheus-client.

## Success criteria

- Scheduler consumes from `url_filter_output` and enqueues to `crawler_queue` with FIFO ordering.
- Seeds are loaded once on startup from `seeds.yaml` and enqueued successfully.
- Queue size backpressure prevents runaway growth.
- Tests cover core behaviors and pass.

## Risks

- Without dedupe in scheduler, duplicates may enter `crawler_queue`; URL Filter must remain authoritative.
- Redis outages will stall the scheduler; reconnection handling is implemented with retry/backoff.

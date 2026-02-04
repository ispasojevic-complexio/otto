# Crawler Scheduler

Manages the URL crawl queue: consumes URLs from the URL Filter output queue and enqueues them to the crawler queue for the Page Fetcher. Optionally loads initial seed URLs from a static YAML file on startup.

## Configuration

All settings are environment-driven via `CRAWLER_SCHEDULER_*` and optional `.env` in the working directory.

| Variable | Default | Description |
|----------|---------|-------------|
| `CRAWLER_SCHEDULER_REDIS_URL` | `redis://localhost:6379` | Redis connection URL |
| `CRAWLER_SCHEDULER_INPUT_QUEUE` | `url_filter_output` | Redis list to consume URLs from (BRPOP) |
| `CRAWLER_SCHEDULER_OUTPUT_QUEUE` | `crawler_queue` | Redis list to enqueue URLs to (RPUSH) |
| `CRAWLER_SCHEDULER_MAX_QUEUE_SIZE` | `100000` | Max length of output queue before backpressure |
| `CRAWLER_SCHEDULER_SEED_FILE_PATH` | `seeds.yaml` (next to code) | Path to YAML file with seed URLs |
| `CRAWLER_SCHEDULER_POLL_TIMEOUT_SECONDS` | `5.0` | BRPOP timeout in seconds |

## Queues

- **Input**: `url_filter_output` — URLs produced by the URL Filter. Scheduler blocks on BRPOP.
- **Output**: `crawler_queue` — URLs to be fetched. Page Fetcher consumes from this queue.

Ordering is FIFO. No deduplication is done in the scheduler; URL Filter is the deduplication gate.

## Operational behavior

- **Startup**: Loads `seeds.yaml` (schema: `seeds: [url, ...]`) and enqueues all seeds to `crawler_queue` once, respecting `MAX_QUEUE_SIZE`.
- **Loop**: Repeatedly BRPOP from `url_filter_output`, then RPUSH to `crawler_queue` if queue size is below `MAX_QUEUE_SIZE`. If at capacity, the URL is re-queued to the input queue (backpressure).
- **Shutdown**: SIGINT/SIGTERM triggers graceful exit after the current iteration.
- **Resilience**: On Redis connection/errors, the process logs and retries with backoff; no checkpoint file (state is in Redis only).

## Running

From the component directory:

```bash
uv run python main.py
```

Ensure Redis is reachable at `REDIS_URL` and that `seeds.yaml` exists if you use seed URLs.

## Observability

- **Logs**: JSON lines to stdout (`component`, `message`, and context fields).
- **Metrics** (Prometheus): `crawler_scheduler_urls_enqueued_total`, `crawler_scheduler_seed_urls_enqueued_total`, `crawler_scheduler_crawler_queue_size`, `crawler_scheduler_loop_lag_seconds`.

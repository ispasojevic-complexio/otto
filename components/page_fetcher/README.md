# Page Fetcher

Consumes URLs from the crawler queue (`crawler_queue`), downloads pages via HTTP, caches full HTML in Redis, and publishes lightweight metadata events to the Kafka `webpage_log` topic. Downstream components (URL Extractor, Ad Parser) read from Kafka and fetch full content from Redis using the cache key.

## Features

- **Async**: httpx, Redis, and Kafka are used asynchronously.
- **Rate limiting**: Redis-based token bucket, 1 req/sec per domain (configurable).
- **Circuit breaker**: On consecutive site-wide failures (e.g. target site down), stops dequeuing and probes with exponential backoff until recovery.
- **robots.txt**: Fetched per domain, cached in Redis; disallowed URLs are skipped.
- **Dead letter queue**: URL-specific permanent failures (after retries) are sent to `page_fetcher_dlq`.

## Configuration

Environment variables (prefix `PAGE_FETCHER_`):

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_URL` | `redis://localhost:6379` | Redis connection URL |
| `KAFKA_BOOTSTRAP_SERVERS` | `localhost:9092` | Kafka broker list |
| `INPUT_QUEUE` | `crawler_queue` | Redis queue to consume URLs from |
| `DLQ_QUEUE` | `page_fetcher_dlq` | Redis queue for failed URLs |
| `WEBPAGE_LOG_TOPIC` | `webpage_log` | Kafka topic for fetch events |
| `CACHE_TTL_SECONDS` | `3600` | Redis cache TTL for page content |
| `RATE_LIMIT_PER_SECOND` | `1.0` | Max requests per second per domain |
| `CIRCUIT_BREAKER_FAILURE_THRESHOLD` | `5` | Consecutive failures before opening circuit |
| `CRAWL_DOMAIN` | `polovniautomobili.com` | Domain used for circuit breaker probe |

## Queues and Kafka

- **Input**: Redis list `crawler_queue` (same as Crawler Scheduler output).
- **Output**: Kafka topic `webpage_log` (metadata only); full HTML in Redis under keys `webpage:{sha256(url)}`.
- **DLQ**: Redis list `page_fetcher_dlq` for URLs that failed permanently after retries.

## Running

```bash
# From repo root
uv run page-fetcher

# Or with env
PAGE_FETCHER_REDIS_URL=redis://localhost:6379 PAGE_FETCHER_KAFKA_BOOTSTRAP_SERVERS=localhost:9092 uv run page-fetcher
```

## Metrics

Prometheus metrics are exposed (if a metrics server is configured). See `metrics.py` for counters, gauges, and histograms (fetch duration, content size, circuit breaker state, etc.).

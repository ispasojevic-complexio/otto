# Page Fetcher Implementation Plan

## Summary

Page Fetcher is the component that downloads web pages from URLs queued by Crawler
Scheduler, caches the full HTML content in Redis, and publishes lightweight metadata
events to the Kafka `webpage_log` topic. Downstream consumers (URL Extractor, Ad Parser)
read the metadata from Kafka and fetch full content from the Redis cache.

## Scope and decisions

- **Async throughout**: Page Fetcher uses `asyncio` with async httpx, async Redis, and
  async Kafka producer. This also requires migrating the shared `RedisQueue` to async
  and updating Crawler Scheduler accordingly.
- **Metadata in Kafka, content in Redis cache**: Kafka `webpage_log` messages contain
  only metadata (URL, status code, cache key, content hash, etc.). Full HTML is stored
  in Redis with a configurable TTL. Consumers retrieve content via the cache key.
- **Redis-based distributed rate limiter**: Uses a Redis token bucket to enforce
  per-domain request rate (1 req/sec default). Future-proofed for multiple instances.
- **Circuit breaker for site-wide failures**: Distinguishes site-wide failures
  (connection refused, DNS errors, 502/503/504) from URL-specific failures (404, 403).
  Site-wide failures trigger a circuit breaker that stops dequeuing and enters a
  low-resource probe mode with exponential backoff. URLs are re-enqueued, not lost.
  Automatic recovery when the site comes back.
- **Dead Letter Queue**: Only URL-specific permanent failures (after retries) go to
  DLQ. Site-wide failures never enter DLQ -- they are re-enqueued and the circuit
  breaker handles backoff.
- **robots.txt enforcement**: Page Fetcher checks robots.txt before each fetch.
  robots.txt is fetched per domain, cached in Redis with a 24h TTL, and checked using
  Python's `urllib.robotparser`. Disallowed URLs are skipped (logged + metric), not
  sent to DLQ.
- **No content compression**: Raw HTML is stored in Redis cache for simplicity.
  Compression can be added later if memory pressure warrants it.
- **Common dependencies in core**: pydantic, pydantic-settings, aiokafka, and
  prometheus-client live in `otto-core`. Page Fetcher only adds `httpx`.

## Architecture context

```
                    ┌─────────────────┐
                    │ Crawler         │
                    │ Scheduler       │
                    └────────┬────────┘
                             │ Redis queue: crawler_queue
                             ▼
                    ┌─────────────────┐
                    │  Page Fetcher   │──── robots.txt check (Redis-cached)
                    │                 │──── Rate limiter (Redis token bucket)
                    │                 │──── Circuit breaker (site-wide outages)
                    │                 │──── Retry w/ exponential backoff
                    └───┬─────────┬───┘
                        │         │
          Redis cache   │         │  Kafka: webpage_log
          webpage:{hash}│         │  (metadata + cache_key)
                        ▼         ▼
                   ┌────────┐  ┌────────────────┐
                   │ Redis  │  │ URL Extractor   │
                   │ Cache  │  │ Ad Parser       │
                   └────────┘  └────────────────┘
                        │
                 (consumers fetch full
                  content via cache_key)

    URL-specific failures ──► Redis queue: page_fetcher_dlq
    Site-wide failures    ──► re-enqueue to crawler_queue + circuit breaker
```

## Prerequisites (shared/core changes)

### 1. Async RedisQueue migration

Migrate `core.queue.Queue` protocol and `core.queue.RedisQueue` to async:

```python
class Queue(Protocol):
    async def enqueue(self, item: str) -> None: ...
    async def dequeue(self, timeout_seconds: float | None = None) -> str | None: ...
    async def size(self) -> int: ...
```

`RedisQueue` switches from `redis.Redis` to `redis.asyncio.Redis`, using the same
underlying Redis list operations (RPUSH, BLPOP/LPOP, LLEN).

**Impact**: Crawler Scheduler must be updated to run its main loop under `asyncio.run()`.
The loop logic is unchanged; only the await points are added.

**Test impact**: Existing `test_redis_queue.py` tests become async (pytest-asyncio).
`pytest_fixtures.py` Redis fixtures updated to yield async clients.

### 2. Kafka producer abstraction in shared/core

Add `core.kafka` module with:

```python
class KafkaProducer(Protocol):
    async def send(self, topic: str, value: bytes, key: bytes | None = None) -> None: ...
    async def close(self) -> None: ...

class AIOKafkaProducer:
    """Thin wrapper around aiokafka.AIOKafkaProducer."""
    def __init__(self, bootstrap_servers: str) -> None: ...
    async def start(self) -> None: ...
    async def send(self, topic: str, value: bytes, key: bytes | None = None) -> None: ...
    async def close(self) -> None: ...
```

The protocol allows testing without a real Kafka broker where needed.

### 3. Redis cache abstraction in shared/core

Add `core.cache` module with:

```python
class Cache(Protocol):
    async def get(self, key: str) -> str | None: ...
    async def set(self, key: str, value: str, ttl_seconds: int | None = None) -> None: ...

class RedisCache:
    """Redis-backed cache with optional TTL."""
    def __init__(self, redis_url: str) -> None: ...
    async def get(self, key: str) -> str | None: ...
    async def set(self, key: str, value: str, ttl_seconds: int | None = None) -> None: ...
```

### 4. Dependency consolidation in otto-core

Move common dependencies into `otto-core` so downstream components inherit them:

```toml
# shared/core/pyproject.toml
dependencies = [
    "redis>=7.1",
    "pydantic>=2.12",
    "pydantic-settings>=2.12",
    "aiokafka>=0.13",
    "prometheus-client>=0.24",
]
```

Crawler Scheduler's `pyproject.toml` drops its direct deps on pydantic,
pydantic-settings, and prometheus-client (now transitive via `otto-core`).

## Data models

### WebpageEvent (Kafka message to `webpage_log`)

```python
from pydantic import BaseModel
from datetime import datetime
from typing import Literal

class WebpageEvent(BaseModel):
    type: Literal["webpage_fetched"] = "webpage_fetched"
    url: str
    cache_key: str           # Redis key where full HTML is stored
    status_code: int
    content_type: str | None
    content_length: int      # bytes
    content_hash: str        # sha256 hex digest of content
    fetched_at: datetime
```

Serialized as JSON to Kafka. Key is `sha256(url)` bytes for partitioning.

### FetchFailure (tagged union for error classification)

```python
from typing import Literal

class SiteWideFailure(BaseModel):
    """Connection refused, DNS error, connect timeout, HTTP 502/503/504."""
    type: Literal["site_wide"] = "site_wide"
    reason: str

class UrlSpecificFailure(BaseModel):
    """HTTP 404/403/410, other 4xx, content errors."""
    type: Literal["url_specific"] = "url_specific"
    status_code: int | None
    reason: str

type FetchFailure = SiteWideFailure | UrlSpecificFailure
```

## Key files

```
components/page_fetcher/
├── src/page_fetcher/
│   ├── __init__.py
│   ├── main.py              # Entry point, main loop, signal handling
│   ├── config.py            # Pydantic settings
│   ├── fetcher.py           # HTTP fetching, retry, caching, Kafka publishing
│   ├── circuit_breaker.py   # Circuit breaker for site-wide outages
│   ├── rate_limiter.py      # Redis-based distributed token bucket
│   ├── robots.py            # robots.txt fetching, caching, checking
│   ├── metrics.py           # Prometheus counters/gauges/histograms
│   └── models.py            # WebpageEvent, FetchFailure, and related models
├── tests/
│   ├── conftest.py
│   ├── test_fetcher.py          # Integration tests (Redis + HTTP)
│   ├── test_circuit_breaker.py  # Circuit breaker state machine tests
│   ├── test_rate_limiter.py     # Rate limiter tests (Redis)
│   └── test_robots.py           # robots.txt tests
├── pyproject.toml
├── deploy/
│   └── Dockerfile
├── implementation_plan.md
└── README.md
```

## Design details

### Circuit breaker (`circuit_breaker.py`)

The circuit breaker prevents resource exhaustion during site-wide outages and enables
automatic recovery without human intervention.

**Error classification:**

| Error type | Classification | Examples |
|---|---|---|
| Site-wide | `SiteWideFailure` | Connection refused, DNS error, connect timeout, HTTP 502, 503, 504 |
| URL-specific | `UrlSpecificFailure` | HTTP 404, 403, 410, other 4xx, content parse errors |
| Rate limit | Neither (special handling) | HTTP 429 -- respect Retry-After, don't count toward circuit breaker |
| Ambiguous | Counted toward circuit breaker | HTTP 500 -- single occurrence retried normally; consecutive 500s trip the breaker |

**States:**

```
    CLOSED (normal operation)
        │
        │  N consecutive site-wide failures (default: 5)
        ▼
    OPEN (outage detected -- stop dequeuing)
        │
        │  backoff timer expires (30s → 1m → 2m → 5m cap)
        ▼
    HALF-OPEN (probing)
        │
       ╱ ╲
  success  failure
     │       │
     ▼       ▼
  CLOSED   OPEN (longer backoff)
```

**Closed** (normal operation):
- Process URLs normally from `crawler_queue`
- Track consecutive site-wide failures
- Any successful fetch resets the failure counter to zero
- After `failure_threshold` (default 5) consecutive site-wide failures, transition to
  Open

**Open** (outage detected):
- **Stop dequeuing** from `crawler_queue` -- URLs remain safely in Redis
- Sleep with exponential backoff: 30s → 1m → 2m → 5m (capped at
  `max_backoff_seconds`)
- After the current backoff expires, transition to Half-Open
- Log: "Circuit open: {domain} appears down. Next probe in {backoff}s."

**Half-Open** (probing):
- Make a single lightweight HEAD request to the domain root
- On success: reset failure counter, transition to Closed, log recovery, resume
  normal dequeuing
- On failure: transition back to Open with the next backoff tier

**URL handling during state transitions:**
- URLs that fail with `SiteWideFailure` are **re-enqueued** to `crawler_queue` (back
  of queue), never sent to DLQ
- The ~5 URLs that fail before the circuit opens are not lost -- they're back in the
  queue
- When the circuit closes, they'll be fetched normally

**Interface:**

```python
class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: int = 5,
        initial_backoff_seconds: float = 30.0,
        max_backoff_seconds: float = 300.0,
        backoff_multiplier: float = 2.0,
    ) -> None: ...

    @property
    def state(self) -> Literal["closed", "open", "half_open"]: ...

    def record_success(self) -> None:
        """Reset failure counter. Transition half_open → closed."""

    def record_site_wide_failure(self) -> None:
        """Increment failure counter. Transition closed → open if threshold reached."""

    async def wait_if_open(self) -> None:
        """If open, sleep until backoff expires, then transition to half_open."""

    @property
    def should_probe(self) -> bool:
        """True when in half_open state (main loop should try one request)."""
```

**2-hour outage scenario walkthrough:**

1. Site goes down at T+0
2. URLs #1-#5 fail with connection errors → each re-enqueued to `crawler_queue`
3. Circuit opens. Fetcher stops dequeuing, sleeps 30s
4. T+30s: probe HEAD request fails → back to Open, sleep 1m
5. T+1m30s: probe fails → Open, sleep 2m
6. ... continues probing every 5m (capped)
7. `crawler_queue` intact, DLQ empty, CPU/threads idle
8. T+2h: site comes back. Next probe succeeds → circuit closes
9. Fetcher resumes dequeuing. All URLs processed. Zero human intervention.

### Main loop (`main.py`)

```
async main():
    setup signal handlers (SIGINT, SIGTERM)
    create RedisQueue(input=crawler_queue)
    create RedisQueue(dlq=page_fetcher_dlq)
    create RedisCache(...)
    create AIOKafkaProducer(...)
    create RateLimiter(...)
    create RobotsChecker(...)
    create CircuitBreaker(...)
    create Fetcher(...)

    while not shutdown:
        # If circuit is open, sleep until backoff expires
        await circuit_breaker.wait_if_open()

        # In half-open state, probe with HEAD request
        if circuit_breaker.should_probe:
            success = await fetcher.probe_domain(domain)
            if success:
                circuit_breaker.record_success()
            else:
                circuit_breaker.record_site_wide_failure()
            continue

        # Normal operation (circuit closed)
        url = await input_queue.dequeue(timeout_seconds=poll_timeout)
        if url is None:
            continue

        result = await fetcher.process(url)
        match result:
            case Ok():
                circuit_breaker.record_success()
            case Err(SiteWideFailure()):
                await input_queue.enqueue(url)  # re-enqueue
                circuit_breaker.record_site_wide_failure()
            case Err(UrlSpecificFailure()):
                await dlq_queue.enqueue(url)
```

### Fetcher (`fetcher.py`)

The `Fetcher` class orchestrates the full pipeline for a single URL:

1. **robots.txt check** -- if disallowed, log + metric, skip (return Ok, not a failure)
2. **Rate limit** -- await until token is available
3. **HTTP GET** with httpx async client
   - Timeout: configurable (default 30s)
   - Follow redirects: yes (max 5)
   - User-Agent: `OttoBot/1.0`
4. **Classify failure** if request fails:
   - Connection/DNS/timeout errors → `SiteWideFailure`
   - HTTP 502/503/504 → `SiteWideFailure`
   - HTTP 404/403/410/other 4xx → `UrlSpecificFailure`
   - HTTP 429 → sleep for Retry-After, retry (don't count toward circuit breaker)
   - HTTP 500 → `UrlSpecificFailure` (but consecutive 500s trip circuit breaker
     naturally since they're retried and fail)
5. **Retry on URL-specific retriable errors** -- exponential backoff (base 2s, max 3
   attempts). Only URL-specific failures are retried per-URL. Site-wide failures
   short-circuit immediately to the circuit breaker.
6. **Cache content** -- store HTML in Redis: key `webpage:{sha256(url)}`, with TTL
7. **Publish event** -- send `WebpageEvent` to Kafka `webpage_log`

Returns `Ok(WebpageEvent)` on success or `Err(FetchFailure)` on failure.

### Rate limiter (`rate_limiter.py`)

Redis-based sliding window / token bucket:

- Key: `rate_limit:{domain}`
- Uses a Lua script for atomic check-and-decrement
- Configurable rate (default: 1 req/sec per domain)
- `await rate_limiter.acquire(domain)` blocks until a token is available

### robots.txt checker (`robots.py`)

- Fetches `https://{domain}/robots.txt` via httpx
- Parses with `urllib.robotparser.RobotFileParser`
- Caches the parsed result in Redis (key: `robots:{domain}`, TTL: 24h)
- `await robots_checker.is_allowed(url) -> bool`
- On fetch failure: defaults to allow (permissive, logged as warning)

### Configuration (`config.py`)

```python
class PageFetcherConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PAGE_FETCHER_")

    redis_url: str = "redis://localhost:6379"
    kafka_bootstrap_servers: str = "localhost:9092"

    # Queues
    input_queue: str = "crawler_queue"
    dlq_queue: str = "page_fetcher_dlq"

    # Kafka
    webpage_log_topic: str = "webpage_log"

    # HTTP
    request_timeout_seconds: float = 30.0
    max_retries: int = 3
    retry_backoff_base_seconds: float = 2.0
    user_agent: str = "OttoBot/1.0"
    max_redirects: int = 5

    # Cache
    cache_ttl_seconds: int = 3600  # 1 hour

    # Rate limiting
    rate_limit_per_second: float = 1.0

    # Circuit breaker
    circuit_breaker_failure_threshold: int = 5
    circuit_breaker_initial_backoff_seconds: float = 30.0
    circuit_breaker_max_backoff_seconds: float = 300.0
    circuit_breaker_backoff_multiplier: float = 2.0

    # robots.txt
    robots_txt_cache_ttl_seconds: int = 86400  # 24 hours

    # Main loop
    poll_timeout_seconds: float = 5.0
```

## Implementation steps

Implementation follows TDD: tests are written before or alongside production code.

### Phase 0: Shared library changes

| # | Step | Tests |
|---|------|-------|
| 0.1 | Consolidate deps into `otto-core`: add pydantic, pydantic-settings, aiokafka, prometheus-client with latest versions. Bump redis to `>=7.1`. Remove duplicates from crawler_scheduler. | Verify crawler_scheduler tests still pass |
| 0.2 | Migrate `Queue` protocol and `RedisQueue` to async in `shared/core` | Update `test_redis_queue.py` to async |
| 0.3 | Update `pytest_fixtures.py` to provide async Redis client | Verify fixtures work |
| 0.4 | Update Crawler Scheduler to use async `RedisQueue` (wrap `main()` in `asyncio.run()`) | Verify existing scheduler tests pass |
| 0.5 | Add `core.cache` module (`Cache` protocol + `RedisCache`) | `test_redis_cache.py` |
| 0.6 | Add `core.kafka` module (`KafkaProducer` protocol + `AIOKafkaProducer`) | `test_kafka_producer.py` (integration with testcontainers) |

### Phase 1: Page Fetcher foundation

| # | Step | Tests |
|---|------|-------|
| 1.1 | Scaffold component: `pyproject.toml`, directory structure, `config.py` | Config loading tests |
| 1.2 | `models.py` -- `WebpageEvent`, `FetchFailure` union types | Serialization round-trip tests |
| 1.3 | `circuit_breaker.py` -- state machine (closed/open/half-open), backoff logic | State transition tests: closed→open on threshold, open→half-open on backoff expiry, half-open→closed on success, half-open→open on failure. Backoff escalation and cap. Success resets counter. |
| 1.4 | `rate_limiter.py` -- Redis token bucket | Rate enforcement tests (Redis) |
| 1.5 | `robots.py` -- robots.txt fetcher, parser, cache | Parse + allow/disallow tests, cache TTL tests |

### Phase 2: Core fetching logic

| # | Step | Tests |
|---|------|-------|
| 2.1 | `fetcher.py` -- HTTP fetch + error classification | Test with local HTTP server: success, 5xx→SiteWideFailure, 4xx→UrlSpecificFailure, timeout→SiteWideFailure, 429→retry with Retry-After |
| 2.2 | `fetcher.py` -- retry logic for URL-specific failures | Verify retry count, backoff timing, max retries exhausted |
| 2.3 | `fetcher.py` -- Redis caching of content | Verify cache key pattern, TTL, content retrieval |
| 2.4 | `fetcher.py` -- Kafka event publishing | Verify `WebpageEvent` published with correct fields |
| 2.5 | `fetcher.py` -- robots.txt + rate limiter integration | End-to-end: disallowed URL skipped, rate respected |

### Phase 3: Main loop and deployment

| # | Step | Tests |
|---|------|-------|
| 3.1 | `main.py` -- main loop with circuit breaker integration: re-enqueue on site-wide failure, DLQ on URL-specific failure, probe in half-open state | Integration: site-wide failure re-enqueues URL; circuit opens after threshold; probe success resumes processing |
| 3.2 | `main.py` -- signal handling, graceful shutdown | Integration test: enqueue URL, verify Kafka event + cache |
| 3.3 | `metrics.py` -- Prometheus metrics (including circuit breaker) | Verify counters increment |
| 3.4 | `deploy/Dockerfile` | Build test |
| 3.5 | Update `docker-compose.local.yml` with page_fetcher + Kafka services | Docker compose up smoke test |
| 3.6 | `README.md` -- configuration, queues, operational behavior | -- |

## Metrics

```python
# Counters
page_fetcher_pages_fetched_total          # Successful fetches
page_fetcher_pages_failed_total           # URL-specific permanent failures (after retries)
page_fetcher_pages_skipped_robots_total   # Skipped due to robots.txt
page_fetcher_pages_requeued_total         # Re-enqueued due to site-wide failure
page_fetcher_retries_total                # Total retry attempts
page_fetcher_dlq_enqueued_total           # URLs sent to DLQ

# Circuit breaker counters
page_fetcher_circuit_breaker_opened_total   # Times circuit transitioned to open
page_fetcher_circuit_breaker_closed_total   # Times circuit transitioned to closed
page_fetcher_circuit_breaker_probes_total   # Probe attempts (labels: result=success|failure)

# Gauges
page_fetcher_input_queue_size                    # Current crawler_queue size
page_fetcher_dlq_size                            # Current DLQ size
page_fetcher_circuit_breaker_state               # 0=closed, 1=open, 2=half_open
page_fetcher_circuit_breaker_consecutive_failures # Current consecutive failure count
page_fetcher_circuit_breaker_current_backoff_seconds # Current backoff duration

# Histograms
page_fetcher_fetch_duration_seconds       # HTTP request duration
page_fetcher_content_size_bytes           # Downloaded page size
```

## Dependencies

### `otto-core` (`shared/core/pyproject.toml`)

```toml
dependencies = [
    "redis>=7.1",
    "pydantic>=2.12",
    "pydantic-settings>=2.12",
    "aiokafka>=0.13",
    "prometheus-client>=0.24",
]
```

### `page_fetcher` (`components/page_fetcher/pyproject.toml`)

```toml
dependencies = [
    "otto-core",
    "httpx>=0.28",
]
```

### `crawler_scheduler` (simplified after consolidation)

```toml
dependencies = [
    "otto-core",
    "pyyaml>=6.0",
]
```

## Success criteria

- Page Fetcher consumes URLs from `crawler_queue`, fetches pages, caches content in
  Redis, and publishes `WebpageEvent` to Kafka `webpage_log`.
- Rate limiting enforces 1 req/sec per domain via Redis.
- robots.txt is respected; disallowed URLs are skipped with appropriate logging.
- Circuit breaker trips after 5 consecutive site-wide failures, stops dequeuing,
  probes with exponential backoff, and automatically resumes when the site recovers.
- URLs affected by site-wide failures are re-enqueued, not sent to DLQ.
- Only URL-specific permanent failures land in `page_fetcher_dlq`.
- All shared/core changes are backward-compatible; Crawler Scheduler tests pass after
  async migration and dependency consolidation.
- Integration tests cover: successful fetch, retry on URL-specific failure, DLQ on
  permanent failure, site-wide failure re-enqueue, circuit breaker state transitions,
  robots.txt enforcement, rate limiting.

## Risks

- **Async migration scope**: Changing `RedisQueue` to async affects Crawler Scheduler.
  Mitigation: phase 0 is isolated and validated before Page Fetcher work begins.
- **Kafka testcontainer complexity**: Kafka containers are heavier than Redis.
  Mitigation: use `confluentinc/cp-kafka` image with KRaft mode (no Zookeeper).
- **Redis cache eviction**: Under memory pressure, Redis may evict cached pages before
  consumers read them. Mitigation: configure `maxmemory-policy` appropriately; consider
  `volatile-ttl` so only TTL keys are evicted. Monitor cache hit rate.
- **robots.txt fetch failures**: If robots.txt can't be fetched, we default to allow.
  This is standard practice but should be monitored.
- **Circuit breaker false positives**: Transient network blips could trip the breaker
  prematurely. Mitigation: threshold of 5 consecutive failures provides reasonable
  tolerance. Backoff starts short (30s) so recovery is fast if it was a blip.

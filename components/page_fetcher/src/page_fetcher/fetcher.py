"""HTTP fetch, retry, cache, and Kafka publish for a single URL."""

from __future__ import annotations

import asyncio
import hashlib
import time
from datetime import datetime
from typing import TYPE_CHECKING
from urllib.parse import urlparse

import httpx
from core.cache import Cache
from core.kafka import KafkaProducer

from page_fetcher.metrics import (
    circuit_breaker_probes_total,
    content_size_bytes,
    dlq_enqueued_total,
    fetch_duration_seconds,
    pages_failed_total,
    pages_fetched_total,
    pages_skipped_robots_total,
    retries_total,
)
from page_fetcher.models import (
    ProcessResult,
    SiteWideFailure,
    SkippedRobots,
    UrlSpecificFailure,
    WebpageEvent,
)

if TYPE_CHECKING:
    from page_fetcher.rate_limiter import RateLimiter
    from page_fetcher.robots import RobotsChecker


def _cache_key(url: str) -> str:
    h = hashlib.sha256(url.encode("utf-8")).hexdigest()
    return f"webpage:{h}"


def _domain(url: str) -> str:
    parsed = urlparse(url)
    return parsed.netloc or parsed.hostname or ""


def _classify_exception(exc: BaseException) -> SiteWideFailure:
    return SiteWideFailure(reason=f"{type(exc).__name__}: {exc}")


def _classify_response(
    status_code: int, reason: str
) -> SiteWideFailure | UrlSpecificFailure:
    if status_code >= 500 or status_code in (502, 503, 504):
        return SiteWideFailure(reason=f"HTTP {status_code} {reason}")
    return UrlSpecificFailure(
        status_code=status_code, reason=f"HTTP {status_code} {reason}"
    )


class Fetcher:
    """Orchestrates fetch for one URL: robots, rate limit, HTTP, cache, Kafka."""

    def __init__(
        self,
        cache: Cache,
        producer: KafkaProducer,
        rate_limiter: RateLimiter,
        robots_checker: RobotsChecker,
        topic: str,
        cache_ttl_seconds: int,
        request_timeout_seconds: float,
        max_retries: int,
        retry_backoff_base: float,
        user_agent: str,
        max_redirects: int,
    ) -> None:
        self._cache = cache
        self._producer = producer
        self._rate_limiter = rate_limiter
        self._robots = robots_checker
        self._topic = topic
        self._cache_ttl = cache_ttl_seconds
        self._timeout = request_timeout_seconds
        self._max_retries = max_retries
        self._retry_backoff_base = retry_backoff_base
        self._user_agent = user_agent
        self._max_redirects = max_redirects

    async def is_allowed_by_robots(self, url: str) -> bool:
        return await self._robots.is_allowed(url)

    async def process(self, url: str) -> ProcessResult:
        """Fetch URL, cache content, publish event. Returns result or failure."""
        if not await self._robots.is_allowed(url):
            pages_skipped_robots_total.inc()
            return SkippedRobots(url=url)
        domain = _domain(url)
        await self._rate_limiter.acquire(domain)
        last_error: SiteWideFailure | UrlSpecificFailure | None = None
        for attempt in range(self._max_retries + 1):
            if attempt > 0:
                retries_total.inc()
                backoff = self._retry_backoff_base**attempt
                await asyncio.sleep(backoff)
            result = await self._do_fetch(url, domain)
            match result:
                case WebpageEvent():
                    pages_fetched_total.inc()
                    return result
                case SkippedRobots():
                    return result
                case SiteWideFailure():
                    last_error = result
                    # Don't retry site-wide; main loop re-enqueues and circuit breaker handles it
                    return result
                case UrlSpecificFailure():
                    last_error = result
                    # Retry only for 5xx or timeout-like; 4xx we don't retry
                    if result.status_code and result.status_code >= 500:
                        continue
                    break
        # Exhausted retries or got non-retriable 4xx
        pages_failed_total.inc()
        dlq_enqueued_total.inc()
        assert last_error is not None
        return last_error

    async def _do_fetch(self, url: str, domain: str) -> ProcessResult:
        """Single attempt: GET, cache, publish. Returns event or failure."""
        start = time.perf_counter()
        try:
            async with httpx.AsyncClient(
                follow_redirects=True,
                max_redirects=self._max_redirects,
                timeout=self._timeout,
                headers={"User-Agent": self._user_agent},
            ) as client:
                resp = await client.get(url)
        except httpx.TimeoutException as e:
            fetch_duration_seconds.observe(time.perf_counter() - start)
            return _classify_exception(e)
        except (httpx.ConnectError, httpx.RemoteProtocolError, OSError) as e:
            fetch_duration_seconds.observe(time.perf_counter() - start)
            return _classify_exception(e)
        except Exception as e:  # noqa: BLE001
            fetch_duration_seconds.observe(time.perf_counter() - start)
            return _classify_exception(e)

        fetch_duration_seconds.observe(time.perf_counter() - start)
        if resp.status_code >= 400:
            return _classify_response(resp.status_code, resp.reason_phrase or "")

        # 2xx (and we treat 3xx as followed to 2xx by httpx)
        body = resp.text
        content_size_bytes.observe(len(body.encode("utf-8")))
        cache_key = _cache_key(url)
        await self._cache.set(cache_key, body, ttl_seconds=self._cache_ttl)
        content_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
        event = WebpageEvent(
            url=url,
            cache_key=cache_key,
            status_code=resp.status_code,
            content_type=resp.headers.get("content-type"),
            content_length=len(body.encode("utf-8")),
            content_hash=content_hash,
            fetched_at=datetime.now(),
        )
        payload = event.model_dump_json().encode("utf-8")
        key = hashlib.sha256(url.encode("utf-8")).digest()
        await self._producer.send(self._topic, payload, key=key)
        return event

    async def probe_domain(self, domain: str) -> bool:
        """HEAD request to domain root. Used when circuit is half_open."""
        url = f"https://{domain}/"
        start = time.perf_counter()
        try:
            async with httpx.AsyncClient(
                follow_redirects=True,
                max_redirects=3,
                timeout=10.0,
                headers={"User-Agent": self._user_agent},
            ) as client:
                resp = await client.head(url)
        except Exception:  # noqa: BLE001
            fetch_duration_seconds.observe(time.perf_counter() - start)
            circuit_breaker_probes_total.labels(result="failure").inc()
            return False
        fetch_duration_seconds.observe(time.perf_counter() - start)
        ok = 200 <= resp.status_code < 400
        circuit_breaker_probes_total.labels(result="success" if ok else "failure").inc()
        return ok

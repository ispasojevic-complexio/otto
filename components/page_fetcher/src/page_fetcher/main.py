"""Page Fetcher: consume URLs from crawler queue, fetch, cache, publish to Kafka."""

from __future__ import annotations

import asyncio
import signal
from typing import Any

import httpx
from core import get_logger
from core.cache import RedisCache
from core.kafka import AIOKafkaProducer
from core.queue import RedisQueue

from page_fetcher.circuit_breaker import CircuitBreaker
from page_fetcher.config import PageFetcherConfig
from page_fetcher.fetcher import Fetcher
from page_fetcher.metrics import dlq_size, input_queue_size, pages_requeued_total
from page_fetcher.models import (
    SiteWideFailure,
    SkippedRobots,
    UrlSpecificFailure,
    WebpageEvent,
)
from page_fetcher.rate_limiter import RateLimiter
from page_fetcher.robots import RobotsChecker

COMPONENT = "page_fetcher"
_shutdown_requested = False
_logger = get_logger(COMPONENT)


def _request_shutdown(*args: object) -> None:
    global _shutdown_requested
    _shutdown_requested = True


async def _fetch_robots_txt(domain: str, user_agent: str) -> str | None:
    """Fetch robots.txt body for domain. Returns None on failure."""
    url = f"https://{domain}/robots.txt"
    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=10.0,
            headers={"User-Agent": user_agent},
        ) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return None
            return resp.text
    except Exception:  # noqa: BLE001
        return None


async def _run(config: PageFetcherConfig) -> None:
    cache = RedisCache(config.redis_url)
    producer = AIOKafkaProducer(config.kafka_bootstrap_servers)
    await producer.start()
    input_queue = RedisQueue(config.redis_url, config.input_queue)
    dlq = RedisQueue(config.redis_url, config.dlq_queue)
    rate_limiter = RateLimiter(
        config.redis_url,
        requests_per_second=config.rate_limit_per_second,
    )
    robots_checker = RobotsChecker(
        cache,
        cache_ttl_seconds=config.robots_txt_cache_ttl_seconds,
        user_agent=config.user_agent,
    )
    robots_checker.set_fetcher(
        lambda d: _fetch_robots_txt(d, config.user_agent),
    )
    circuit_breaker = CircuitBreaker(
        failure_threshold=config.circuit_breaker_failure_threshold,
        initial_backoff_seconds=config.circuit_breaker_initial_backoff_seconds,
        max_backoff_seconds=config.circuit_breaker_max_backoff_seconds,
        backoff_multiplier=config.circuit_breaker_backoff_multiplier,
    )
    fetcher = Fetcher(
        cache=cache,
        producer=producer,
        rate_limiter=rate_limiter,
        robots_checker=robots_checker,
        topic=config.webpage_log_topic,
        cache_ttl_seconds=config.cache_ttl_seconds,
        request_timeout_seconds=config.request_timeout_seconds,
        max_retries=config.max_retries,
        retry_backoff_base=config.retry_backoff_base_seconds,
        user_agent=config.user_agent,
        max_redirects=config.max_redirects,
    )

    domain = config.crawl_domain
    _logger.info(
        "Page fetcher starting",
        extra={
            "redis_url": config.redis_url,
            "input_queue": config.input_queue,
            "dlq_queue": config.dlq_queue,
            "crawl_domain": domain,
        },
    )

    while not _shutdown_requested:
        await circuit_breaker.wait_if_open()

        if circuit_breaker.should_probe:
            success = await fetcher.probe_domain(domain)
            if success:
                circuit_breaker.record_success()
                _logger.info(
                    "Circuit closed after successful probe", extra={"domain": domain}
                )
            else:
                circuit_breaker.record_probe_failure()
                circuit_breaker.record_site_wide_failure()
            continue

        url: str | None = await input_queue.dequeue(
            timeout_seconds=config.poll_timeout_seconds,
        )
        if url is None:
            input_queue_size.set(await input_queue.size())
            dlq_size.set(await dlq.size())
            continue

        input_queue_size.set(await input_queue.size())
        dlq_size.set(await dlq.size())

        result = await fetcher.process(url)
        match result:
            case WebpageEvent():
                circuit_breaker.record_success()
                _logger.info(
                    "Page fetched",
                    extra={"url": url, "status_code": result.status_code},
                )
            case SkippedRobots():
                _logger.debug("URL skipped by robots.txt", extra={"url": url})
            case SiteWideFailure():
                await input_queue.enqueue(url)
                pages_requeued_total.inc()
                circuit_breaker.record_site_wide_failure()
                _logger.warning(
                    "Site-wide failure, re-enqueued",
                    extra={"url": url, "reason": result.reason},
                )
            case UrlSpecificFailure():
                await dlq.enqueue(url)
                _logger.warning(
                    "URL failed, sent to DLQ",
                    extra={"url": url, "reason": result.reason},
                )

    await producer.close()
    _logger.info("Shutting down")


def main() -> None:
    config = PageFetcherConfig()
    signal.signal(signal.SIGINT, _request_shutdown)
    signal.signal(signal.SIGTERM, _request_shutdown)
    asyncio.run(_run(config))


if __name__ == "__main__":
    main()

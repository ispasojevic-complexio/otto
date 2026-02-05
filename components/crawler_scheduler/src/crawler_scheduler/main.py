"""Crawler scheduler: consumes from URL Filter queue, enqueues to crawler queue."""

from __future__ import annotations

import signal
import time

from core import get_logger
from core.queue import RedisQueue

from crawler_scheduler.config import SchedulerConfig
from crawler_scheduler.metrics import (
    crawler_queue_size,
    scheduler_loop_lag_seconds,
    seed_urls_enqueued_total,
    urls_enqueued_total,
)
from crawler_scheduler.seeds import enqueue_seeds, load_seeds

COMPONENT = "crawler_scheduler"
_shutdown_requested = False
_logger = get_logger(COMPONENT)


def _request_shutdown(*args: object) -> None:
    global _shutdown_requested
    _shutdown_requested = True


def main() -> None:
    config = SchedulerConfig()

    _logger.info(
        "Scheduler starting",
        extra={
            "redis_url": config.redis_url,
            "input_queue": config.input_queue,
            "output_queue": config.output_queue,
            "max_queue_size": config.max_queue_size,
            "seed_file": str(config.seed_file_path),
            "poll_timeout_seconds": config.poll_timeout_seconds,
        },
    )

    signal.signal(signal.SIGINT, _request_shutdown)
    signal.signal(signal.SIGTERM, _request_shutdown)

    input_queue = RedisQueue(config.redis_url, config.input_queue)
    output_queue = RedisQueue(config.redis_url, config.output_queue)

    _logger.info(
        "Redis queues initialised",
        extra={
            "redis_url": config.redis_url,
            "input_queue": config.input_queue,
            "output_queue": config.output_queue,
        },
    )

    # Seed ingestion (once on startup)
    seeds = load_seeds(config.seed_file_path)
    if seeds:
        n = enqueue_seeds(
            output_queue,
            config.max_queue_size,
            seeds,
            log_fn=lambda msg, extra: _logger.info(
                msg,
                extra=extra if isinstance(extra, dict) else {"extra": extra},
            ),
        )
        seed_urls_enqueued_total.inc(n)
        _logger.info(
            "Seeds enqueued",
            extra={"seed_count": len(seeds), "enqueued": n},
        )
    else:
        _logger.info(
            "No seeds to enqueue",
            extra={"seed_file": str(config.seed_file_path)},
        )

    # Scheduler loop: dequeue from input -> enqueue to output with backpressure
    last_success_at = time.monotonic()
    while not _shutdown_requested:
        try:
            url = input_queue.dequeue(timeout_seconds=config.poll_timeout_seconds)
            if url is None:
                scheduler_loop_lag_seconds.set(time.monotonic() - last_success_at)
                continue
            current_size = output_queue.size()
            crawler_queue_size.set(current_size)
            if current_size >= config.max_queue_size:
                _logger.warning(
                    "Backpressure: output queue at max size, re-queuing to input",
                    extra={"url": url, "current": current_size},
                )
                input_queue.enqueue(url)
                continue
            output_queue.enqueue(url)
            _logger.info(
                "URL moved to crawler queue",
                extra={"url": url, "output_queue_size": current_size + 1},
            )
            urls_enqueued_total.inc(1)
            last_success_at = time.monotonic()
            scheduler_loop_lag_seconds.set(0)
        except Exception as e:  # noqa: BLE001
            _logger.exception("Queue error")
            time.sleep(1)

    _logger.info("Shutting down")


if __name__ == "__main__":
    main()

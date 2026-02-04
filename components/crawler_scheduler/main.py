"""Crawler scheduler: consumes from URL Filter queue, enqueues to crawler queue."""

from __future__ import annotations

import json
import logging
import signal
import sys
import time
import redis

from config import SchedulerConfig
from metrics import (
    crawler_queue_size,
    scheduler_loop_lag_seconds,
    seed_urls_enqueued_total,
    urls_enqueued_total,
)
from seeds import enqueue_seeds, load_seeds

COMPONENT = "crawler_scheduler"
_shutdown_requested = False


def _log(message: str, **kwargs: object) -> None:
    record = {
        "component": COMPONENT,
        "message": message,
        **{k: v for k, v in kwargs.items()},
    }
    print(json.dumps(record), flush=True)


def _request_shutdown(*args: object) -> None:
    global _shutdown_requested
    _shutdown_requested = True


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    config = SchedulerConfig()

    signal.signal(signal.SIGINT, _request_shutdown)
    signal.signal(signal.SIGTERM, _request_shutdown)

    client = redis.from_url(config.redis_url, decode_responses=True)

    # Seed ingestion (once on startup)
    seeds = load_seeds(config.seed_file_path)
    if seeds:
        n = enqueue_seeds(
            client,
            config,
            seeds,
            log_fn=lambda msg, extra: _log(msg, **(extra if isinstance(extra, dict) else {"extra": extra})),
        )
        seed_urls_enqueued_total.inc(n)
        _log("Seeds enqueued", seed_count=len(seeds), enqueued=n)
    else:
        _log("No seeds to enqueue", seed_file=str(config.seed_file_path))

    # Scheduler loop: BRPOP from input_queue -> RPUSH to output_queue with backpressure
    last_success_at = time.monotonic()
    while not _shutdown_requested:
        try:
            result = client.brpop(config.input_queue, timeout=config.poll_timeout_seconds)
            if result is None:
                # Timeout: update lag gauge and continue
                scheduler_loop_lag_seconds.set(time.monotonic() - last_success_at)
                continue
            _queue_name, url = result
            current_size = client.llen(config.output_queue)
            crawler_queue_size.set(current_size)
            if current_size >= config.max_queue_size:
                _log("Backpressure: output queue at max size, re-queuing to input", url=url, current=current_size)
                client.lpush(config.input_queue, url)
                continue
            client.rpush(config.output_queue, url)
            urls_enqueued_total.inc(1)
            last_success_at = time.monotonic()
            scheduler_loop_lag_seconds.set(0)
        except redis.ConnectionError as e:
            _log("Redis connection error, will retry", error=str(e))
            time.sleep(2)
            try:
                client.ping()
            except redis.RedisError:
                pass
        except redis.RedisError as e:
            _log("Redis error", error=str(e))
            time.sleep(1)

    _log("Shutting down")


if __name__ == "__main__":
    main()

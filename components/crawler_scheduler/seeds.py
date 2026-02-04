"""Load seed URLs from YAML and enqueue to Redis."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Callable

import yaml

from config import SchedulerConfig

if TYPE_CHECKING:
    import redis


def load_seeds(path: Path) -> list[str]:
    """Parse seeds.yaml and return list of URL strings."""
    if not path.exists():
        return []
    try:
        raw = path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw) or {}
    except yaml.YAMLError:
        return []
    seeds = data.get("seeds")
    if not isinstance(seeds, list):
        return []
    return [str(s).strip() for s in seeds if s and isinstance(s, str)]


def enqueue_seeds(
    redis_client: redis.Redis[bytes],
    config: SchedulerConfig,
    seeds: list[str],
    *,
    log_fn: Callable[[str, object], None] | None = None,
) -> int:
    """
    Push seed URLs to output queue, respecting max_queue_size.
    Returns number of URLs actually enqueued.
    """
    enqueued = 0
    for url in seeds:
        current = redis_client.llen(config.output_queue)
        if current >= config.max_queue_size:
            if log_fn:
                log_fn("Backpressure: output queue at max size, skipping remaining seeds", {"current": current})
            break
        redis_client.rpush(config.output_queue, url)
        enqueued += 1
        if log_fn and enqueued <= 5:
            log_fn("Seed enqueued", {"url": url, "enqueued_so_far": enqueued})
    return enqueued

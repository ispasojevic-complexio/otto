"""Load seed URLs from YAML and enqueue to the output queue."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import yaml

from core.queue import Queue


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
    output_queue: Queue,
    max_size: int,
    seeds: list[str],
    *,
    log_fn: Callable[[str, object], None] | None = None,
) -> int:
    """
    Push seed URLs to the output queue, respecting max_size (backpressure).
    Returns number of URLs actually enqueued.
    """
    enqueued = 0
    for url in seeds:
        if output_queue.size() >= max_size:
            if log_fn:
                log_fn("Backpressure: output queue at max size, skipping remaining seeds", {"current": output_queue.size()})
            break
        output_queue.enqueue(url)
        enqueued += 1
        if log_fn and enqueued <= 5:
            log_fn("Seed enqueued", {"url": url, "enqueued_so_far": enqueued})
    return enqueued

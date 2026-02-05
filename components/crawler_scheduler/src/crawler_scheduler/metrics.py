"""Prometheus metrics for crawler scheduler."""

from prometheus_client import Counter, Gauge

urls_enqueued_total = Counter(
    "crawler_scheduler_urls_enqueued_total",
    "Total URLs enqueued to crawler_queue (from URL filter)",
)
seed_urls_enqueued_total = Counter(
    "crawler_scheduler_seed_urls_enqueued_total",
    "Total seed URLs enqueued on startup",
)
crawler_queue_size = Gauge(
    "crawler_scheduler_crawler_queue_size",
    "Current length of crawler_queue",
)
scheduler_loop_lag_seconds = Gauge(
    "crawler_scheduler_loop_lag_seconds",
    "Seconds since last successful dequeue from url_filter_output",
)


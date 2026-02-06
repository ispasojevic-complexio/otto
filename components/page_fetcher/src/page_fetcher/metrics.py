"""Prometheus metrics for Page Fetcher."""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

# Counters
pages_fetched_total = Counter(
    "page_fetcher_pages_fetched_total",
    "Successful page fetches",
)
pages_failed_total = Counter(
    "page_fetcher_pages_failed_total",
    "URL-specific permanent failures (after retries)",
)
pages_skipped_robots_total = Counter(
    "page_fetcher_pages_skipped_robots_total",
    "Skipped due to robots.txt",
)
pages_requeued_total = Counter(
    "page_fetcher_pages_requeued_total",
    "Re-enqueued due to site-wide failure",
)
retries_total = Counter(
    "page_fetcher_retries_total",
    "Total retry attempts",
)
dlq_enqueued_total = Counter(
    "page_fetcher_dlq_enqueued_total",
    "URLs sent to DLQ",
)

# Circuit breaker counters
circuit_breaker_opened_total = Counter(
    "page_fetcher_circuit_breaker_opened_total",
    "Times circuit transitioned to open",
)
circuit_breaker_closed_total = Counter(
    "page_fetcher_circuit_breaker_closed_total",
    "Times circuit transitioned to closed",
)
circuit_breaker_probes_total = Counter(
    "page_fetcher_circuit_breaker_probes_total",
    "Probe attempts",
    ["result"],  # success | failure
)

# Gauges
input_queue_size = Gauge(
    "page_fetcher_input_queue_size",
    "Current crawler_queue size",
)
dlq_size = Gauge(
    "page_fetcher_dlq_size",
    "Current DLQ size",
)
circuit_breaker_state_gauge = Gauge(
    "page_fetcher_circuit_breaker_state",
    "Circuit state: 0=closed, 1=open, 2=half_open",
)
circuit_breaker_consecutive_failures_gauge = Gauge(
    "page_fetcher_circuit_breaker_consecutive_failures",
    "Current consecutive site-wide failure count",
)
circuit_breaker_current_backoff_seconds = Gauge(
    "page_fetcher_circuit_breaker_current_backoff_seconds",
    "Current backoff duration in seconds",
)

# Histograms
fetch_duration_seconds = Histogram(
    "page_fetcher_fetch_duration_seconds",
    "HTTP request duration in seconds",
    buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)
content_size_bytes = Histogram(
    "page_fetcher_content_size_bytes",
    "Downloaded page size in bytes",
    buckets=(1024, 10_000, 50_000, 100_000, 500_000, 1_000_000),
)

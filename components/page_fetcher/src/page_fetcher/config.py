"""Page Fetcher configuration (Pydantic Settings)."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class PageFetcherConfig(BaseSettings):
    model_config = SettingsConfigDict(  # pyrefly: ignore[missing-override-decorator]
        env_prefix="PAGE_FETCHER_"
    )

    redis_url: str = Field(default="redis://localhost:6379")
    kafka_bootstrap_servers: str = Field(default="localhost:9092")

    # Queues
    input_queue: str = Field(default="crawler_queue")
    dlq_queue: str = Field(default="page_fetcher_dlq")

    # Kafka
    webpage_log_topic: str = Field(default="webpage_log")

    # HTTP
    request_timeout_seconds: float = Field(default=30.0)
    max_retries: int = Field(default=3)
    retry_backoff_base_seconds: float = Field(default=2.0)
    user_agent: str = Field(default="OttoBot/1.0")
    max_redirects: int = Field(default=5)

    # Cache
    cache_ttl_seconds: int = Field(default=3600)

    # Rate limiting
    rate_limit_per_second: float = Field(default=1.0)

    # Circuit breaker
    circuit_breaker_failure_threshold: int = Field(default=5)
    circuit_breaker_initial_backoff_seconds: float = Field(default=30.0)
    circuit_breaker_max_backoff_seconds: float = Field(default=300.0)
    circuit_breaker_backoff_multiplier: float = Field(default=2.0)

    # robots.txt
    robots_txt_cache_ttl_seconds: int = Field(default=86400)

    # Main loop
    poll_timeout_seconds: float = Field(default=5.0)

    # Domain to probe when circuit is half-open (e.g. polovniautomobili.com)
    crawl_domain: str = Field(default="polovniautomobili.com")

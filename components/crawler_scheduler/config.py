"""Configuration for crawler scheduler (environment-driven)."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class SchedulerConfig(BaseSettings):
    """Environment-driven scheduler settings."""

    model_config = SettingsConfigDict(
        env_prefix="CRAWLER_SCHEDULER_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    redis_url: str = Field(default="redis://localhost:6379", description="Redis connection URL")
    input_queue: str = Field(default="url_filter_output", description="Redis list to consume URLs from")
    output_queue: str = Field(default="crawler_queue", description="Redis list to enqueue URLs to")
    max_queue_size: int = Field(default=100_000, ge=1, description="Max length of output queue before backpressure")
    seed_file_path: Path = Field(
        default_factory=lambda: Path(__file__).parent / "seeds.yaml",
        description="Path to YAML file with seed URLs",
    )
    poll_timeout_seconds: float = Field(default=5.0, gt=0, description="BRPOP timeout in seconds")

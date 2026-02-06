"""Data models for webpage events and fetch failures."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class WebpageEvent(BaseModel):
    """Event published to Kafka webpage_log when a page is successfully fetched."""

    type: Literal["webpage_fetched"] = Field(default="webpage_fetched")
    url: str = Field(description="Fetched URL")
    cache_key: str = Field(description="Redis key where full HTML is stored")
    status_code: int = Field(description="HTTP status code")
    content_type: str | None = Field(default=None)
    content_length: int = Field(description="Response body length in bytes")
    content_hash: str = Field(description="SHA256 hex digest of content")
    fetched_at: datetime = Field(default_factory=datetime.now)


class SiteWideFailure(BaseModel):
    """Connection refused, DNS error, timeout, HTTP 502/503/504."""

    type: Literal["site_wide"] = Field(default="site_wide")
    reason: str = Field(description="Human-readable failure reason")


class UrlSpecificFailure(BaseModel):
    """HTTP 404/403/410, other 4xx, content errors."""

    type: Literal["url_specific"] = Field(default="url_specific")
    status_code: int | None = Field(default=None)
    reason: str = Field(description="Human-readable failure reason")


# Tagged union for fetch failure classification
FetchFailure = SiteWideFailure | UrlSpecificFailure


# Result of process(url): success yields WebpageEvent, failure yields FetchFailure
# Skipped (e.g. robots.txt) is represented as a sentinel or we use None for skip.
class SkippedRobots(BaseModel):
    """URL was skipped because robots.txt disallows it."""

    type: Literal["skipped_robots"] = Field(default="skipped_robots")
    url: str = Field()


ProcessResult = WebpageEvent | SkippedRobots | SiteWideFailure | UrlSpecificFailure

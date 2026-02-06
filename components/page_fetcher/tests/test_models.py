"""Tests for WebpageEvent and FetchFailure models."""

from __future__ import annotations

from datetime import datetime

import pytest
from page_fetcher.models import (
    SiteWideFailure,
    UrlSpecificFailure,
    WebpageEvent,
)


def test_webpage_event_serialization_roundtrip() -> None:
    event = WebpageEvent(
        url="https://example.com/page",
        cache_key="webpage:abc123",
        status_code=200,
        content_type="text/html",
        content_length=1024,
        content_hash="deadbeef",
        fetched_at=datetime(2025, 1, 15, 12, 0, 0),
    )
    json_str = event.model_dump_json()
    loaded = WebpageEvent.model_validate_json(json_str)
    assert loaded.url == event.url
    assert loaded.cache_key == event.cache_key
    assert loaded.status_code == 200
    assert loaded.fetched_at == event.fetched_at


def test_site_wide_failure_serialization() -> None:
    f = SiteWideFailure(reason="Connection refused")
    assert f.type == "site_wide"
    assert f.reason == "Connection refused"
    d = f.model_dump()
    assert d["type"] == "site_wide"


def test_url_specific_failure_serialization() -> None:
    f = UrlSpecificFailure(status_code=404, reason="Not Found")
    assert f.type == "url_specific"
    assert f.status_code == 404
    assert f.reason == "Not Found"

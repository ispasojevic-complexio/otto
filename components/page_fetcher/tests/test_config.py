"""Tests for Page Fetcher config."""

from __future__ import annotations

import os

import pytest
from page_fetcher.config import PageFetcherConfig


def test_config_defaults() -> None:
    config = PageFetcherConfig()
    assert config.redis_url == "redis://localhost:6379"
    assert config.input_queue == "crawler_queue"
    assert config.dlq_queue == "page_fetcher_dlq"
    assert config.webpage_log_topic == "webpage_log"
    assert config.cache_ttl_seconds == 3600
    assert config.circuit_breaker_failure_threshold == 5
    assert config.crawl_domain == "polovniautomobili.com"


def test_config_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PAGE_FETCHER_REDIS_URL", "redis://other:6380")
    monkeypatch.setenv("PAGE_FETCHER_INPUT_QUEUE", "my_queue")
    config = PageFetcherConfig()
    assert config.redis_url == "redis://other:6380"
    assert config.input_queue == "my_queue"

"""Core package: common interfaces and implementations (queue, logging, etc.)."""

from core.logging import (
    LogSink,
    PrintSink,
    configure_logging,
    get_default_logger,
    get_logger,
)
from core.queue import Queue, RedisQueue

__all__ = [
    "Queue",
    "RedisQueue",
    "LogSink",
    "PrintSink",
    "configure_logging",
    "get_default_logger",
    "get_logger",
]

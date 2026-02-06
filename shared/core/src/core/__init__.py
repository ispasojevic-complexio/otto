"""Core package: common interfaces and implementations (queue, cache, kafka, logging, etc.)."""

from core.cache import Cache, RedisCache
from core.kafka import AIOKafkaProducer, KafkaProducer
from core.logging import (
    LogSink,
    PrintSink,
    configure_logging,
    get_default_logger,
    get_logger,
)
from core.queue import Queue, RedisQueue

__all__ = [
    "Cache",
    "RedisCache",
    "KafkaProducer",
    "AIOKafkaProducer",
    "Queue",
    "RedisQueue",
    "LogSink",
    "PrintSink",
    "configure_logging",
    "get_default_logger",
    "get_logger",
]

"""Core package: common interfaces and implementations (queue, etc.)."""

from core.queue import Queue, RedisQueue

__all__ = ["Queue", "RedisQueue"]


"""Lightweight, pluggable logging abstraction shared across components.

Current implementation writes JSON lines to stdout via :func:`print`, but the
interface is designed so we can later swap the sink (e.g. to files or a
structured logging backend) without touching call sites.
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass
from typing import Protocol, TextIO


class LogSink(Protocol):
    """Abstract destination for log records."""

    def write(self, message: str) -> None:  # pragma: no cover - simple protocol
        ...


@dataclass
class PrintSink:
    """Log sink that writes each record as a line via :func:`print`."""

    stream: TextIO = sys.stdout

    def write(self, message: str) -> None:
        print(message, file=self.stream, flush=True)


@dataclass
class JsonLogger:
    """JSON-structured logger with pluggable sink."""

    component: str
    sink: LogSink

    def log(self, message: str, **kwargs: object) -> None:
        record: dict[str, object] = {
            "ts": time.time(),
            "component": self.component,
            "message": message,
            **kwargs,
        }
        self.sink.write(json.dumps(record))


def get_default_logger(component: str) -> JsonLogger:
    """Return a logger that prints JSON lines to stdout.

    In the future we can change this factory to route logs elsewhere without
    touching call sites – only this factory.
    """

    return JsonLogger(component=component, sink=PrintSink())

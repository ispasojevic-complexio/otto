"""Pluggable logging using the standard library ``logging`` interface.

Components use :func:`get_logger` to get a standard :class:`logging.Logger`.
Output is formatted as JSON lines (to stdout by default); the sink can be
swapped (e.g. to files or a logging backend) by configuring a different
handler when setting up logging.
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Any, Protocol, TextIO, override

# Attributes that exist on every logging.LogRecord; we don't duplicate them as "extra".
_STANDARD_RECORD_ATTRS = frozenset(
    {
        "name",
        "msg",
        "args",
        "created",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "exc_info",
        "exc_text",
        "message",
        "taskName",
        "getMessage",
    }
)


class LogSink(Protocol):
    """Abstract destination for log records (e.g. stdout, file, backend)."""

    def write(self, message: str) -> None:  # pragma: no cover
        ...


class PrintSink:
    """Log sink that writes each record as a line via :func:`print`."""

    _stream: TextIO

    def __init__(self, stream: TextIO | None = None) -> None:
        self._stream = stream if stream is not None else sys.stdout

    def write(self, message: str) -> None:
        print(message, file=self._stream, flush=True)


class JsonFormatter(logging.Formatter):
    """Format log records as a single JSON object per line."""

    @override
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": record.created,
            "level": record.levelname,
            "component": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _STANDARD_RECORD_ATTRS and value is not None:
                payload[key] = value
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload)


class SinkHandler(logging.Handler):
    """Handler that writes formatted records to a :class:`LogSink`."""

    _sink: LogSink

    def __init__(self, sink: LogSink) -> None:
        super().__init__()
        self._sink = sink

    @override
    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._sink.write(self.format(record))
        except Exception:  # noqa: BLE001
            self.handleError(record)


_default_sink: LogSink | None = None


def configure_logging(
    level: int = logging.INFO,
    sink: LogSink | None = None,
) -> None:
    """Configure root logging to emit JSON lines to the given sink.

    If ``sink`` is omitted, uses :class:`PrintSink` (stdout). Call once at
    startup if you need to override the default; otherwise :func:`get_logger`
    will use stdout on first use.
    """
    global _default_sink
    _default_sink = sink if sink is not None else PrintSink()
    root = logging.getLogger()
    root.setLevel(level)
    handler = SinkHandler(_default_sink)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """Return a standard :class:`logging.Logger` for the given component/name.

    On first call, configures root logging to emit JSON lines to stdout (or
    the sink set by :func:`configure_logging`). Use the standard interface::

        logger = get_logger(__name__)
        logger.info("Starting", extra={"redis_url": url})
    """
    if _default_sink is None:
        configure_logging(sink=PrintSink())
    return logging.getLogger(name)


def get_default_logger(name: str) -> logging.Logger:
    """Alias for :func:`get_logger` for backward compatibility."""
    return get_logger(name)

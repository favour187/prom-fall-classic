"""Structured logging setup (JSON in production, readable in development)."""

from __future__ import annotations

import logging
import sys
from typing import Any

_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
_FIELD_ORDER = ("ts", "level", "logger", "message")


class JsonFormatter(logging.Formatter):
    """Minimal JSON log formatter (stdlib only, no extra dependency)."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        extra = record.__dict__.get("extra_fields")
        if isinstance(extra, dict):
            payload.update({k: v for k, v in extra.items() if k not in payload})
        return _json_dumps(payload)


def _json_dumps(payload: dict[str, Any]) -> str:
    import json

    return json.dumps(payload, default=str)


def setup_logging(*, debug: bool = False, json_logs: bool = False) -> None:
    """Configure the root logger once. Safe to call repeatedly."""
    root = logging.getLogger()
    if getattr(root, "_hackathon_configured", False):
        root.setLevel(logging.DEBUG if debug else logging.INFO)
        return

    handler = logging.StreamHandler(sys.stdout)
    if json_logs:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter(_FORMAT))
    root.handlers = [handler]
    root.setLevel(logging.DEBUG if debug else logging.INFO)
    # Keep noisy third-party loggers down.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    setattr(root, "_hackathon_configured", True)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)

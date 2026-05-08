"""Structured logging via ``structlog``.

API keys and obvious secrets are scrubbed before they hit any handler.
"""

from __future__ import annotations

import logging
import re
import sys
from typing import Any

import structlog

_SECRET_RE = re.compile(r"(api[_-]?key|authorization|secret|token)", re.IGNORECASE)


def _redact_secrets(_logger: Any, _name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    for k in list(event_dict.keys()):
        if _SECRET_RE.search(k):
            event_dict[k] = "***"
    return event_dict


_CONFIGURED = False


def configure_logging(level: str = "INFO") -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stderr,
        level=getattr(logging, level.upper(), logging.INFO),
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            _redact_secrets,
            structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty()),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        cache_logger_on_first_use=True,
    )
    _CONFIGURED = True


def get_logger(name: str | None = None) -> structlog.BoundLogger:
    if not _CONFIGURED:
        configure_logging()
    return structlog.get_logger(name) if name else structlog.get_logger()


__all__ = ["configure_logging", "get_logger"]

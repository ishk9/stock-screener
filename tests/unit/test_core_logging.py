"""Unit tests for ``stock_screener.core.logging``."""

from __future__ import annotations

import logging as _stdlib_logging
from typing import Any

import pytest
import structlog

from stock_screener.core import logging as logging_mod
from stock_screener.core.logging import (
    _redact_secrets,
    configure_logging,
    get_logger,
)


@pytest.fixture
def reset_logging(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset the configured-once flag and clear root handlers."""
    monkeypatch.setattr(logging_mod, "_CONFIGURED", False)
    root = _stdlib_logging.getLogger()
    original_handlers = list(root.handlers)
    for h in list(root.handlers):
        root.removeHandler(h)
    structlog.reset_defaults()
    yield
    for h in list(root.handlers):
        root.removeHandler(h)
    for h in original_handlers:
        root.addHandler(h)
    structlog.reset_defaults()


def test_redact_secrets_masks_known_keys() -> None:
    event_dict: dict[str, Any] = {
        "api_key": "sk-leak",
        "API_KEY": "sk-leak2",
        "apikey": "sk-leak3",
        "Authorization": "Bearer token",
        "secret": "shh",
        "auth_token": "abc",
    }
    out = _redact_secrets(None, "name", dict(event_dict))
    for k in event_dict:
        assert out[k] == "***", f"expected {k!r} to be masked"


def test_redact_secrets_passes_other_keys_unchanged() -> None:
    event_dict: dict[str, Any] = {
        "user": "alice",
        "count": 7,
        "event": "login",
    }
    out = _redact_secrets(None, "name", dict(event_dict))
    assert out == event_dict


def test_configure_logging_is_idempotent(reset_logging: None) -> None:
    configure_logging()
    configure_logging()
    configure_logging(level="DEBUG")
    assert logging_mod._CONFIGURED is True


def test_get_logger_returns_object_with_info(reset_logging: None) -> None:
    log = get_logger("foo")
    assert hasattr(log, "info")
    assert callable(log.info)


def test_logged_secrets_are_masked_in_stderr(
    reset_logging: None, capsys: pytest.CaptureFixture[str]
) -> None:
    configure_logging()
    log = get_logger("redaction-test")
    log.info("auth", api_key="sk-VERYSECRET-XXXX", token="t-1234567890")

    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "sk-VERYSECRET-XXXX" not in combined
    assert "t-1234567890" not in combined
    assert "***" in combined

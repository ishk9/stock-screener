"""Unit tests for ``stock_screener.core.errors``."""

from __future__ import annotations

import pytest

from stock_screener.core import errors as errors_mod
from stock_screener.core.errors import (
    AuthError,
    CacheError,
    ConfigError,
    DataQualityError,
    LLMError,
    LLMRateLimitError,
    LLMRefusalError,
    LLMSchemaError,
    ProviderError,
    RateLimitError,
    RenderError,
    SSError,
    UnavailableError,
)


@pytest.mark.parametrize(
    "cls",
    [
        ConfigError,
        ProviderError,
        RateLimitError,
        AuthError,
        DataQualityError,
        UnavailableError,
        LLMError,
        LLMRateLimitError,
        LLMSchemaError,
        LLMRefusalError,
        CacheError,
        RenderError,
    ],
)
def test_all_errors_derive_from_ss_error(cls: type[Exception]) -> None:
    assert issubclass(cls, SSError)
    assert issubclass(cls, Exception)


def test_provider_error_hierarchy() -> None:
    assert issubclass(RateLimitError, ProviderError)
    assert issubclass(AuthError, ProviderError)
    assert issubclass(DataQualityError, ProviderError)
    assert issubclass(UnavailableError, ProviderError)


def test_llm_error_hierarchy() -> None:
    assert issubclass(LLMRateLimitError, LLMError)
    assert issubclass(LLMSchemaError, LLMError)
    assert issubclass(LLMRefusalError, LLMError)
    assert not issubclass(LLMError, ProviderError)


def test_errors_carry_their_message() -> None:
    assert str(ProviderError("x")) == "x"
    assert str(RateLimitError("slow down")) == "slow down"
    assert str(LLMRateLimitError("rate")) == "rate"
    assert str(ConfigError("nope")) == "nope"


def test_all_export_contains_expected_names() -> None:
    expected = {
        "SSError",
        "ConfigError",
        "ProviderError",
        "RateLimitError",
        "AuthError",
        "DataQualityError",
        "UnavailableError",
        "LLMError",
        "LLMRateLimitError",
        "LLMSchemaError",
        "LLMRefusalError",
        "CacheError",
        "RenderError",
    }
    assert expected == set(errors_mod.__all__)


def test_catching_parent_catches_child() -> None:
    with pytest.raises(ProviderError):
        raise RateLimitError("rl")
    with pytest.raises(SSError):
        raise UnavailableError("u")
    with pytest.raises(LLMError):
        raise LLMSchemaError("schema")
    with pytest.raises(SSError):
        raise CacheError("c")

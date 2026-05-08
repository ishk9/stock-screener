"""Typed error taxonomy for the Stock Screener.

Every adapter must map vendor-specific exceptions to one of these at the
boundary. The domain only ever sees ``SSError`` subclasses.
"""

from __future__ import annotations


class SSError(Exception):
    """Root of the Stock Screener error hierarchy."""


# --------------------------------------------------------------------------- #
# Configuration / startup
# --------------------------------------------------------------------------- #
class ConfigError(SSError):
    """Invalid, missing or conflicting configuration."""


# --------------------------------------------------------------------------- #
# Data providers
# --------------------------------------------------------------------------- #
class ProviderError(SSError):
    """Base class for any market-data provider failure."""


class RateLimitError(ProviderError):
    """The remote provider rate-limited us."""


class AuthError(ProviderError):
    """Authentication/authorization with the provider failed."""


class DataQualityError(ProviderError):
    """Provider returned malformed or implausible data."""


class UnavailableError(ProviderError):
    """Provider is temporarily unavailable (5xx, timeout, network)."""


# --------------------------------------------------------------------------- #
# LLM
# --------------------------------------------------------------------------- #
class LLMError(SSError):
    """Base class for any LLM-vendor failure."""


class LLMRateLimitError(LLMError):
    """LLM vendor rate-limited us."""


class LLMSchemaError(LLMError):
    """LLM returned content that does not match the requested schema."""


class LLMRefusalError(LLMError):
    """LLM refused to answer (safety / policy)."""


# --------------------------------------------------------------------------- #
# Cache / persistence
# --------------------------------------------------------------------------- #
class CacheError(SSError):
    """Local cache or persistence layer failure."""


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #
class RenderError(SSError):
    """Output rendering failed."""


__all__ = [
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
]

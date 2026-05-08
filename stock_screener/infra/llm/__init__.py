"""LLM adapter package — Template-Method base + vendor implementations."""

from .base import BaseLLMClient
from .factory import LLMClientFactory
from .stub_client import StubLLMClient

__all__ = ["BaseLLMClient", "LLMClientFactory", "StubLLMClient"]

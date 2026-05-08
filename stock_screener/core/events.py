"""Tiny in-process pub/sub used for progress + telemetry.

Decouples long-running pipelines from the renderer. A subscriber is just
``Callable[[Event], None]``; events are immutable dataclasses.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable

# --------------------------------------------------------------------------- #
# Events
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class Event:
    """Marker base class — every event subclasses this."""


@dataclass(frozen=True, slots=True)
class UseCaseStarted(Event):
    name: str
    payload: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class UseCaseCompleted(Event):
    name: str
    duration_ms: float


@dataclass(frozen=True, slots=True)
class UseCaseFailed(Event):
    name: str
    error: str


@dataclass(frozen=True, slots=True)
class UniverseRefreshed(Event):
    count: int


@dataclass(frozen=True, slots=True)
class ProviderCallStarted(Event):
    provider: str
    operation: str


@dataclass(frozen=True, slots=True)
class ProviderCallCompleted(Event):
    provider: str
    operation: str
    duration_ms: float
    cache_hit: bool = False


@dataclass(frozen=True, slots=True)
class ProviderFailed(Event):
    provider: str
    operation: str
    error: str


@dataclass(frozen=True, slots=True)
class LLMCallCompleted(Event):
    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    duration_ms: float


@dataclass(frozen=True, slots=True)
class RecommendationProduced(Event):
    symbol: str
    score: float
    risk_pct: float


# --------------------------------------------------------------------------- #
# Bus
# --------------------------------------------------------------------------- #
Subscriber = Callable[[Event], None]


class EventBus:
    """Synchronous, type-keyed pub/sub. Thread-unsafe by design (single CLI run)."""

    def __init__(self) -> None:
        self._subs: dict[type[Event], list[Subscriber]] = defaultdict(list)
        self._all: list[Subscriber] = []

    def subscribe(self, event_type: type[Event], handler: Subscriber) -> None:
        self._subs[event_type].append(handler)

    def subscribe_all(self, handler: Subscriber) -> None:
        self._all.append(handler)

    def publish(self, event: Event) -> None:
        for h in self._subs.get(type(event), []):
            try:
                h(event)
            except Exception:  # noqa: BLE001 — subscribers must never break the pipeline
                pass
        for h in self._all:
            try:
                h(event)
            except Exception:  # noqa: BLE001
                pass


__all__ = [
    "Event",
    "UseCaseStarted",
    "UseCaseCompleted",
    "UseCaseFailed",
    "UniverseRefreshed",
    "ProviderCallStarted",
    "ProviderCallCompleted",
    "ProviderFailed",
    "LLMCallCompleted",
    "RecommendationProduced",
    "EventBus",
]

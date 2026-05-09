"""Unit tests for ``stock_screener.core.events``."""

from __future__ import annotations

import pytest

from stock_screener.core.events import (
    Event,
    EventBus,
    LLMCallCompleted,
    UseCaseCompleted,
    UseCaseFailed,
    UseCaseStarted,
)


def test_subscribe_receives_published_event() -> None:
    bus = EventBus()
    received: list[Event] = []
    bus.subscribe(UseCaseStarted, received.append)

    evt = UseCaseStarted(name="run", payload={"x": 1})
    bus.publish(evt)

    assert received == [evt]


def test_subscriber_does_not_receive_other_event_types() -> None:
    bus = EventBus()
    received: list[Event] = []
    bus.subscribe(UseCaseStarted, received.append)

    bus.publish(UseCaseCompleted(name="run", duration_ms=1.0))

    assert received == []


def test_subscribe_all_receives_every_event() -> None:
    bus = EventBus()
    seen: list[Event] = []
    bus.subscribe_all(seen.append)

    a = UseCaseStarted(name="a")
    b = UseCaseCompleted(name="a", duration_ms=2.5)
    c = UseCaseFailed(name="a", error="bad")
    bus.publish(a)
    bus.publish(b)
    bus.publish(c)

    assert seen == [a, b, c]


def test_multiple_subscribers_receive_in_registration_order() -> None:
    bus = EventBus()
    order: list[str] = []
    bus.subscribe(UseCaseStarted, lambda _e: order.append("first"))
    bus.subscribe(UseCaseStarted, lambda _e: order.append("second"))
    bus.subscribe(UseCaseStarted, lambda _e: order.append("third"))

    bus.publish(UseCaseStarted(name="x"))

    assert order == ["first", "second", "third"]


def test_raising_subscriber_does_not_break_others() -> None:
    bus = EventBus()
    captured: list[Event] = []

    def boom(_e: Event) -> None:
        raise RuntimeError("subscriber crashed")

    bus.subscribe(UseCaseStarted, boom)
    bus.subscribe(UseCaseStarted, captured.append)

    evt = UseCaseStarted(name="ok")
    bus.publish(evt)

    assert captured == [evt]


def test_use_case_event_payloads() -> None:
    bus = EventBus()
    seen: list[Event] = []
    bus.subscribe_all(seen.append)

    started = UseCaseStarted(name="screen", payload={"profile": "value"})
    completed = UseCaseCompleted(name="screen", duration_ms=42.0)
    failed = UseCaseFailed(name="screen", error="boom")
    bus.publish(started)
    bus.publish(completed)
    bus.publish(failed)

    assert isinstance(seen[0], UseCaseStarted)
    assert seen[0].name == "screen"
    assert seen[0].payload == {"profile": "value"}
    assert isinstance(seen[1], UseCaseCompleted)
    assert seen[1].duration_ms == 42.0
    assert isinstance(seen[2], UseCaseFailed)
    assert seen[2].error == "boom"


def test_llm_call_completed_event_fields() -> None:
    bus = EventBus()
    seen: list[LLMCallCompleted] = []
    bus.subscribe(LLMCallCompleted, lambda e: seen.append(e))  # type: ignore[arg-type]

    evt = LLMCallCompleted(
        provider="openai",
        model="gpt-4o-mini",
        prompt_tokens=125,
        completion_tokens=64,
        duration_ms=300.5,
    )
    bus.publish(evt)

    assert len(seen) == 1
    assert seen[0].prompt_tokens == 125
    assert seen[0].completion_tokens == 64
    assert seen[0].provider == "openai"
    assert seen[0].model == "gpt-4o-mini"


def test_events_are_frozen() -> None:
    evt = UseCaseStarted(name="x")
    with pytest.raises(Exception):
        evt.name = "mutated"  # type: ignore[misc]

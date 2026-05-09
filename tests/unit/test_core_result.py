"""Unit tests for ``stock_screener.core.result``."""

from __future__ import annotations

import pytest

from stock_screener.core.result import Err, Ok


def test_ok_is_ok_and_not_err() -> None:
    r = Ok(5)
    assert r.is_ok() is True
    assert r.is_err() is False


def test_err_is_err_and_not_ok() -> None:
    r = Err("oops")
    assert r.is_err() is True
    assert r.is_ok() is False


def test_ok_unwrap_returns_value() -> None:
    assert Ok(5).unwrap() == 5
    assert Ok("hello").unwrap() == "hello"


def test_err_unwrap_raises_wrapped_exception() -> None:
    err = Err(ValueError("boom"))
    with pytest.raises(ValueError, match="boom"):
        err.unwrap()


def test_err_unwrap_string_raises_runtime_error() -> None:
    with pytest.raises(RuntimeError, match=r"Err: 'just a string'"):
        Err("just a string").unwrap()


def test_unwrap_or_returns_value_for_ok_and_default_for_err() -> None:
    assert Ok(5).unwrap_or(99) == 5
    assert Err("x").unwrap_or(99) == 99


def test_ok_map_applies_function() -> None:
    assert Ok(5).map(lambda v: v * 2) == Ok(10)


def test_err_map_is_unchanged() -> None:
    e = Err("x")
    mapped = e.map(lambda v: v * 2)  # type: ignore[arg-type]
    assert mapped is e
    assert mapped == Err("x")


def test_ok_map_err_is_unchanged() -> None:
    o = Ok(5)
    mapped = o.map_err(lambda e: f"!{e}")
    assert mapped is o
    assert mapped == Ok(5)


def test_err_map_err_transforms_error() -> None:
    assert Err("x").map_err(lambda e: f"!{e}") == Err("!x")


def test_ok_is_frozen() -> None:
    o = Ok(5)
    with pytest.raises(Exception):
        o.value = 6  # type: ignore[misc]


def test_equality_and_distinct_types() -> None:
    assert Ok(5) == Ok(5)
    assert Err("x") == Err("x")
    assert Ok(5) != Err(5)
    assert Ok(5) != Ok(6)


def test_pattern_match_discrimination() -> None:
    def describe(r: Ok[int] | Err[str]) -> str:
        match r:
            case Ok(value=v):
                return f"ok:{v}"
            case Err(error=e):
                return f"err:{e}"

    assert describe(Ok(5)) == "ok:5"
    assert describe(Err("nope")) == "err:nope"

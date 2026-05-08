"""A minimal ``Result[T, E]`` type used at adapter boundaries.

Adapters return ``Ok(value)`` or ``Err(error)`` for *expected* failures so
callers can pattern-match outcomes instead of wrapping every call in
``try/except``. Truly exceptional bugs still raise.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Generic, NoReturn, TypeVar

T = TypeVar("T")
U = TypeVar("U")
E = TypeVar("E")
F = TypeVar("F")


@dataclass(frozen=True, slots=True)
class Ok(Generic[T]):
    value: T

    def is_ok(self) -> bool:
        return True

    def is_err(self) -> bool:
        return False

    def unwrap(self) -> T:
        return self.value

    def unwrap_or(self, _default: T) -> T:
        return self.value

    def map(self, fn: Callable[[T], U]) -> "Ok[U]":
        return Ok(fn(self.value))

    def map_err(self, _fn: Callable[[E], F]) -> "Ok[T]":  # noqa: ARG002
        return self


@dataclass(frozen=True, slots=True)
class Err(Generic[E]):
    error: E

    def is_ok(self) -> bool:
        return False

    def is_err(self) -> bool:
        return True

    def unwrap(self) -> NoReturn:
        if isinstance(self.error, Exception):
            raise self.error
        raise RuntimeError(f"called unwrap() on Err: {self.error!r}")

    def unwrap_or(self, default: T) -> T:
        return default

    def map(self, _fn: Callable[[T], U]) -> "Err[E]":  # noqa: ARG002
        return self

    def map_err(self, fn: Callable[[E], F]) -> "Err[F]":
        return Err(fn(self.error))


Result = Ok[T] | Err[E]


__all__ = ["Ok", "Err", "Result"]

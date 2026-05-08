"""Money value object — currency-tagged amount."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Union

Numeric = Union[int, float, Decimal, str]


@dataclass(frozen=True, slots=True)
class Money:
    amount: Decimal
    currency: str = "INR"

    def __init__(self, amount: Numeric, currency: str = "INR") -> None:
        if isinstance(amount, float):
            amount = Decimal(str(amount))
        else:
            amount = Decimal(amount)
        object.__setattr__(self, "amount", amount)
        object.__setattr__(self, "currency", currency.upper())

    def __add__(self, other: "Money") -> "Money":
        self._same_ccy(other)
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: "Money") -> "Money":
        self._same_ccy(other)
        return Money(self.amount - other.amount, self.currency)

    def _same_ccy(self, other: "Money") -> None:
        if self.currency != other.currency:
            raise ValueError(
                f"currency mismatch: {self.currency!r} vs {other.currency!r}"
            )

    def __str__(self) -> str:
        sign = "₹" if self.currency == "INR" else f"{self.currency} "
        return f"{sign}{self.amount:,.2f}"


__all__ = ["Money"]

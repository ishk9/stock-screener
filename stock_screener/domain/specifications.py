"""Specification pattern for user-supplied screening constraints.

A ``Specification[T]`` answers "does this candidate satisfy my rule?".
Specifications combine with ``&``, ``|`` and ``~``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Generic, Iterable, TypeVar

from .entities.recommendation import Recommendation
from .entities.snapshot import CompanySnapshot
from .value_objects.market_cap import MarketCapBucket
from .value_objects.pct import Pct

T = TypeVar("T")


class Specification(ABC, Generic[T]):
    @abstractmethod
    def is_satisfied_by(self, candidate: T) -> bool: ...

    def __and__(self, other: "Specification[T]") -> "Specification[T]":
        return _And(self, other)

    def __or__(self, other: "Specification[T]") -> "Specification[T]":
        return _Or(self, other)

    def __invert__(self) -> "Specification[T]":
        return _Not(self)


@dataclass(frozen=True, slots=True)
class _And(Specification[T]):
    a: Specification[T]
    b: Specification[T]

    def is_satisfied_by(self, candidate: T) -> bool:
        return self.a.is_satisfied_by(candidate) and self.b.is_satisfied_by(candidate)


@dataclass(frozen=True, slots=True)
class _Or(Specification[T]):
    a: Specification[T]
    b: Specification[T]

    def is_satisfied_by(self, candidate: T) -> bool:
        return self.a.is_satisfied_by(candidate) or self.b.is_satisfied_by(candidate)


@dataclass(frozen=True, slots=True)
class _Not(Specification[T]):
    inner: Specification[T]

    def is_satisfied_by(self, candidate: T) -> bool:
        return not self.inner.is_satisfied_by(candidate)


# --------------------------------------------------------------------------- #
# Concrete specs over CompanySnapshot
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class MarketCapSpec(Specification[CompanySnapshot]):
    bucket: MarketCapBucket

    def is_satisfied_by(self, candidate: CompanySnapshot) -> bool:
        return candidate.company.market_cap_bucket == self.bucket


@dataclass(frozen=True, slots=True)
class SectorWhitelistSpec(Specification[CompanySnapshot]):
    sectors: frozenset[str]

    @classmethod
    def of(cls, sectors: Iterable[str]) -> "SectorWhitelistSpec":
        return cls(frozenset(s.strip().lower() for s in sectors if s.strip()))

    def is_satisfied_by(self, candidate: CompanySnapshot) -> bool:
        if not self.sectors:
            return True
        sector = (candidate.company.sector or "").strip().lower()
        return sector in self.sectors


@dataclass(frozen=True, slots=True)
class SectorBlacklistSpec(Specification[CompanySnapshot]):
    sectors: frozenset[str]

    @classmethod
    def of(cls, sectors: Iterable[str]) -> "SectorBlacklistSpec":
        return cls(frozenset(s.strip().lower() for s in sectors if s.strip()))

    def is_satisfied_by(self, candidate: CompanySnapshot) -> bool:
        if not self.sectors:
            return True
        sector = (candidate.company.sector or "").strip().lower()
        return sector not in self.sectors


@dataclass(frozen=True, slots=True)
class HasMinimumDataSpec(Specification[CompanySnapshot]):
    def is_satisfied_by(self, candidate: CompanySnapshot) -> bool:
        return candidate.has_minimum_data


# --------------------------------------------------------------------------- #
# Specs over Recommendation
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class MaxRiskSpec(Specification[Recommendation]):
    max_risk: Pct

    def is_satisfied_by(self, candidate: Recommendation) -> bool:
        return candidate.risk_pct.value <= self.max_risk.value


@dataclass(frozen=True, slots=True)
class MinRiskSpec(Specification[Recommendation]):
    min_risk: Pct

    def is_satisfied_by(self, candidate: Recommendation) -> bool:
        return candidate.risk_pct.value >= self.min_risk.value


@dataclass(frozen=True, slots=True)
class MinScoreSpec(Specification[Recommendation]):
    min_score: float

    def is_satisfied_by(self, candidate: Recommendation) -> bool:
        return candidate.score.value >= self.min_score


@dataclass(frozen=True, slots=True)
class MaxScoreSpec(Specification[Recommendation]):
    max_score: float

    def is_satisfied_by(self, candidate: Recommendation) -> bool:
        return candidate.score.value <= self.max_score


__all__ = [
    "Specification",
    "MarketCapSpec",
    "SectorWhitelistSpec",
    "SectorBlacklistSpec",
    "HasMinimumDataSpec",
    "MaxRiskSpec",
    "MinRiskSpec",
    "MaxScoreSpec",
    "MinScoreSpec",
]

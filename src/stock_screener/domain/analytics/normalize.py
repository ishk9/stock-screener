"""Normalisation helpers — pure, None-safe."""

from __future__ import annotations

from typing import Sequence


def _present(values: Sequence[float | None]) -> list[float]:
    return [float(v) for v in values if v is not None]


def min_max(values: Sequence[float | None]) -> list[float | None]:
    """Min-max scale to ``[0, 1]``; ``None`` values pass through.

    When all present values are equal (or only one is present) the output
    is ``0.5`` — the neutral midpoint — for those slots.
    """
    present = _present(values)
    if not present:
        return [None for _ in values]
    lo = min(present)
    hi = max(present)
    if hi == lo:
        return [None if v is None else 0.5 for v in values]
    span = hi - lo
    out: list[float | None] = []
    for v in values:
        if v is None:
            out.append(None)
        else:
            out.append((float(v) - lo) / span)
    return out


def winsorize(
    values: Sequence[float | None],
    lower: float = 0.05,
    upper: float = 0.95,
) -> list[float | None]:
    """Clip extreme values to the [lower, upper] quantile range.

    ``None`` values are preserved. Quantiles are computed on the present
    subset only. If fewer than 2 present values are supplied, the input
    is returned unchanged.
    """
    if not (0.0 <= lower < upper <= 1.0):
        raise ValueError(f"invalid winsorize bounds: lower={lower}, upper={upper}")
    present = sorted(_present(values))
    if len(present) < 2:
        return [None if v is None else float(v) for v in values]
    lo = _quantile(present, lower)
    hi = _quantile(present, upper)
    out: list[float | None] = []
    for v in values:
        if v is None:
            out.append(None)
            continue
        x = float(v)
        if x < lo:
            x = lo
        elif x > hi:
            x = hi
        out.append(x)
    return out


def _quantile(sorted_values: Sequence[float], q: float) -> float:
    n = len(sorted_values)
    if n == 1:
        return float(sorted_values[0])
    pos = q * (n - 1)
    lo_idx = int(pos)
    hi_idx = min(lo_idx + 1, n - 1)
    frac = pos - lo_idx
    return float(sorted_values[lo_idx]) * (1.0 - frac) + float(sorted_values[hi_idx]) * frac


def rank_pct(
    values: Sequence[float | None],
    higher_is_better: bool = True,
) -> list[float | None]:
    """Percentile-rank values to ``[0, 1]``.

    Ties share the average of the ranks they span. ``None`` values pass
    through. With one present value the output is ``0.5``.
    """
    present = [(i, float(v)) for i, v in enumerate(values) if v is not None]
    if not present:
        return [None for _ in values]
    if len(present) == 1:
        return [None if v is None else 0.5 for v in values]

    indexed = sorted(present, key=lambda iv: iv[1])
    ranks: dict[int, float] = {}
    n = len(indexed)
    i = 0
    while i < n:
        j = i
        while j + 1 < n and indexed[j + 1][1] == indexed[i][1]:
            j += 1
        avg_rank = (i + j) / 2.0
        for k in range(i, j + 1):
            idx = indexed[k][0]
            ranks[idx] = avg_rank / (n - 1)
        i = j + 1

    out: list[float | None] = []
    for original_idx, v in enumerate(values):
        if v is None:
            out.append(None)
        else:
            r = ranks[original_idx]
            out.append(r if higher_is_better else 1.0 - r)
    return out


__all__ = ["min_max", "winsorize", "rank_pct"]

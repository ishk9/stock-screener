"""Action value objects.

Two distinct enums by use-case:

* :class:`Action` — for **new** positions (a ``ss screen`` recommendation).
  Answers: "should I open a position right now?".

* :class:`PortfolioAction` — for **held** positions (a ``ss portfolio review``).
  Answers: "what should I do with the position I already have?".

The intentional split prevents the screener's "BUY" being conflated with the
portfolio's "ADD" (which means "add to an existing position you already own").
"""

from __future__ import annotations

from enum import Enum


class Action(str, Enum):
    """Recommended action for opening a *new* position."""

    BUY = "BUY"        # high score + acceptable risk → enter now
    WAIT = "WAIT"      # decent setup but not actionable yet
    AVOID = "AVOID"    # do not initiate

    @classmethod
    def from_signal(
        cls, *, score: float, risk_pct: float, conviction_high: bool
    ) -> "Action":
        """Deterministic mapping from quant signal to action.

        - BUY:    score >= 65 AND risk <= 50 (and stronger if HIGH conviction)
        - AVOID:  score < 40 OR risk >= 75
        - WAIT:   anything else
        """
        if score < 40 or risk_pct >= 75:
            return cls.AVOID
        if score >= 65 and risk_pct <= 50:
            return cls.BUY
        if conviction_high and score >= 60 and risk_pct <= 55:
            return cls.BUY
        return cls.WAIT


class PortfolioAction(str, Enum):
    """Recommended action for an *already-held* position."""

    ADD = "ADD"        # average down or up; thesis intact, valuation favourable
    HOLD = "HOLD"      # no urgent action
    TRIM = "TRIM"      # take partial profit / reduce concentration
    EXIT = "EXIT"      # thesis broken; cut the position

    @classmethod
    def from_signal(
        cls,
        *,
        score: float,
        risk_pct: float,
        unrealised_pnl_pct: float,
        stop_loss_breached: bool,
    ) -> "PortfolioAction":
        """Decide based on quant view + P&L.

        Order of evaluation matters; the first matching rule wins.
        - EXIT  : score < 35, or stop-loss breached, or risk >= 80 with negative P&L
        - TRIM  : unrealised P&L >= +50% AND (score < 60 OR risk >= 65)
        - ADD   : score >= 65 AND risk <= 55 (regardless of P&L)
        - HOLD  : everything else
        """
        if score < 35 or stop_loss_breached or (risk_pct >= 80 and unrealised_pnl_pct < 0):
            return cls.EXIT
        if unrealised_pnl_pct >= 50.0 and (score < 60 or risk_pct >= 65):
            return cls.TRIM
        if score >= 65 and risk_pct <= 55:
            return cls.ADD
        return cls.HOLD


__all__ = ["Action", "PortfolioAction"]

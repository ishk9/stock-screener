"""PortfolioActionPolicy — decides ADD / HOLD / TRIM / EXIT for held positions.

Pure domain logic, no I/O. Encapsulates the heuristics and renders a short
human-readable rationale for the chosen action.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..entities.position import Position
from ..entities.recommendation import Recommendation
from ..value_objects.action import PortfolioAction


# Stop-loss breach is "current price below avg_buy by this %", e.g. 25 = -25%.
DEFAULT_STOP_LOSS_PCT = 25.0


@dataclass(frozen=True, slots=True)
class PortfolioActionPolicy:
    stop_loss_pct: float = DEFAULT_STOP_LOSS_PCT

    def decide(
        self,
        *,
        position: Position,
        current_price: float | None,
        recommendation: Recommendation | None,
    ) -> tuple[PortfolioAction, str]:
        """Return ``(action, rationale)``.

        Falls back gracefully when price or recommendation is missing.
        """
        if current_price is None or current_price <= 0:
            return (
                PortfolioAction.HOLD,
                "Live price unavailable — defer action until data refreshes.",
            )

        _, pnl_pct = position.unrealised_pnl(current_price)
        stop_breached = pnl_pct <= -self.stop_loss_pct

        if recommendation is None:
            if stop_breached:
                return (
                    PortfolioAction.EXIT,
                    f"Position is {pnl_pct:+.1f}% (below the {self.stop_loss_pct}% stop) "
                    f"and we have no fresh research to override. Cut and reassess.",
                )
            if pnl_pct >= 50.0:
                return (
                    PortfolioAction.TRIM,
                    f"Up {pnl_pct:+.1f}% with no fresh thesis — "
                    "consider booking partial profit.",
                )
            return (PortfolioAction.HOLD, "No fresh research; defer to next review.")

        score = recommendation.score.value
        risk = recommendation.risk_pct.value
        action = PortfolioAction.from_signal(
            score=score,
            risk_pct=risk,
            unrealised_pnl_pct=pnl_pct,
            stop_loss_breached=stop_breached,
        )
        return action, self._rationale(action, score, risk, pnl_pct, stop_breached)

    def _rationale(
        self,
        action: PortfolioAction,
        score: float,
        risk: float,
        pnl_pct: float,
        stop_breached: bool,
    ) -> str:
        base = f"Score {score:.0f}/100, risk {risk:.0f}%, P&L {pnl_pct:+.1f}%."
        if action is PortfolioAction.EXIT:
            why = (
                "Stop-loss breached." if stop_breached else
                "Quant view has deteriorated; thesis no longer supports holding."
            )
            return f"{base} {why} Recommend exiting and redeploying capital."
        if action is PortfolioAction.TRIM:
            return (
                f"{base} Sizeable gain with weakening signal — book partial profit "
                "to lock in returns and reduce concentration."
            )
        if action is PortfolioAction.ADD:
            return (
                f"{base} Strong score with manageable risk — averaging up/down "
                "is consistent with the active thesis."
            )
        return f"{base} No urgent action; thesis intact, hold through the next review."


__all__ = ["PortfolioActionPolicy", "DEFAULT_STOP_LOSS_PCT"]

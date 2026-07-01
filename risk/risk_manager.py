"""Risk controls: position sizing and pre-trade limit checks.

Every order the engine wants to send is first sized here and then validated
against the configured limits. Shared by both paper trading and the backtester
so the two behave consistently.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Tuple


@dataclass
class RiskLimits:
    max_position_pct: float = 0.15
    max_gross_exposure: float = 1.0
    max_positions: int = 10
    stop_loss_pct: float = 0.05
    take_profit_pct: float = 0.10

    @classmethod
    def from_config(cls, cfg: Dict[str, Any]) -> "RiskLimits":
        r = cfg.get("risk", {})
        return cls(
            max_position_pct=r.get("max_position_pct", 0.15),
            max_gross_exposure=r.get("max_gross_exposure", 1.0),
            max_positions=r.get("max_positions", 10),
            stop_loss_pct=r.get("stop_loss_pct", 0.05),
            take_profit_pct=r.get("take_profit_pct", 0.10),
        )


class RiskManager:
    def __init__(self, limits: RiskLimits):
        self.limits = limits

    # ------------------------------------------------------------------- sizing
    def target_qty(self, equity: float, price: float) -> int:
        """Whole-share quantity for a single position at the per-asset cap."""
        if price <= 0 or equity <= 0:
            return 0
        dollar_cap = equity * self.limits.max_position_pct
        return int(dollar_cap // price)

    # -------------------------------------------------------------- pre-trade check
    def check_order(
        self,
        symbol: str,
        qty: float,
        price: float,
        equity: float,
        current_positions: Dict[str, float],
        current_gross: float,
    ) -> Tuple[bool, str]:
        """Return (approved, reason). Reason explains a rejection."""
        if qty <= 0:
            return False, "non-positive quantity"
        if price <= 0:
            return False, "invalid price"

        notional = qty * price

        # Per-asset cap.
        if notional > equity * self.limits.max_position_pct + 1e-6:
            return False, (
                f"exceeds per-asset cap "
                f"({notional:.0f} > {equity * self.limits.max_position_pct:.0f})"
            )

        # Max number of simultaneous positions (only if this opens a new one).
        opening_new = symbol not in current_positions or current_positions[symbol] == 0
        if opening_new and len([p for p in current_positions.values() if p != 0]) >= self.limits.max_positions:
            return False, f"max positions reached ({self.limits.max_positions})"

        # Gross exposure cap.
        projected_gross = current_gross + notional
        if projected_gross > equity * self.limits.max_gross_exposure + 1e-6:
            return False, (
                f"exceeds gross exposure cap "
                f"({projected_gross:.0f} > {equity * self.limits.max_gross_exposure:.0f})"
            )

        return True, "ok"

    # ----------------------------------------------------------- stop / take-profit
    def should_exit(self, entry_price: float, current_price: float, side: int) -> Tuple[bool, str]:
        """Check stop-loss / take-profit for an open position.

        side: +1 for long, -1 for short.
        """
        if entry_price <= 0:
            return False, ""
        ret = (current_price - entry_price) / entry_price * side
        if ret <= -self.limits.stop_loss_pct:
            return True, "stop_loss"
        if ret >= self.limits.take_profit_pct:
            return True, "take_profit"
        return False, ""

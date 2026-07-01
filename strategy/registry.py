"""Strategy factory: build the active strategy from config (switchable)."""
from __future__ import annotations

from typing import Any, Dict

from strategy.base import Strategy
from strategy.mean_reversion import MeanReversion
from strategy.trend_ma import TrendMACrossover

AVAILABLE = ("trend", "mean_reversion")


def build_strategy(cfg: Dict[str, Any]) -> Strategy:
    """Instantiate the strategy named by cfg['strategy']['active']."""
    s = cfg["strategy"]
    active = s.get("active", "trend")

    if active == "trend":
        p = s.get("trend", {})
        return TrendMACrossover(
            fast_window=p.get("fast_window", 20),
            slow_window=p.get("slow_window", 50),
        )
    if active == "mean_reversion":
        p = s.get("mean_reversion", {})
        return MeanReversion(
            lookback=p.get("lookback", 20),
            entry_z=p.get("entry_z", 2.0),
            exit_z=p.get("exit_z", 0.5),
        )
    raise ValueError(f"Unknown strategy '{active}'. Choose from {AVAILABLE}")

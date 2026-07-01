"""Performance metrics for the backtester and reporting."""
from __future__ import annotations

from typing import Any, Dict, List

import numpy as np
import pandas as pd


def max_drawdown(equity: pd.Series) -> float:
    """Largest peak-to-trough decline as a positive fraction (e.g. 0.20 = 20%)."""
    if equity.empty:
        return 0.0
    running_max = equity.cummax()
    drawdown = (equity - running_max) / running_max
    return float(-drawdown.min())


def sharpe_ratio(returns: pd.Series, periods_per_year: int = 252) -> float:
    """Annualised Sharpe of a per-period return series (risk-free = 0)."""
    if returns.std(ddof=0) == 0 or returns.empty:
        return 0.0
    return float(np.sqrt(periods_per_year) * returns.mean() / returns.std(ddof=0))


def compute_metrics(
    equity_curve: pd.Series,
    trades: List[Dict[str, Any]],
    periods_per_year: int = 252,
) -> Dict[str, Any]:
    """Summarise an equity curve + list of closed trades.

    Each trade dict is expected to carry a realised 'pnl' value.
    """
    equity_curve = equity_curve.dropna()
    if equity_curve.empty:
        return {}

    returns = equity_curve.pct_change().dropna()
    start_val = float(equity_curve.iloc[0])
    end_val = float(equity_curve.iloc[-1])

    wins = [t for t in trades if t.get("pnl", 0) > 0]
    losses = [t for t in trades if t.get("pnl", 0) < 0]
    n_closed = len(wins) + len(losses)

    return {
        "start_equity": round(start_val, 2),
        "end_equity": round(end_val, 2),
        "total_return_pct": round((end_val / start_val - 1) * 100, 2),
        "cumulative_pnl": round(end_val - start_val, 2),
        "max_drawdown_pct": round(max_drawdown(equity_curve) * 100, 2),
        "sharpe": round(sharpe_ratio(returns, periods_per_year), 2),
        "num_trades": len(trades),
        "num_closed_trades": n_closed,
        "hit_rate_pct": round(100 * len(wins) / n_closed, 2) if n_closed else 0.0,
        "avg_win": round(np.mean([t["pnl"] for t in wins]), 2) if wins else 0.0,
        "avg_loss": round(np.mean([t["pnl"] for t in losses]), 2) if losses else 0.0,
    }

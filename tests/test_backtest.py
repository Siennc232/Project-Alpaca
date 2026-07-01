"""Unit tests for the backtester and metrics (synthetic data, no network)."""
import numpy as np
import pandas as pd

from backtest.backtester import Backtester
from backtest.metrics import compute_metrics, max_drawdown
from strategy.trend_ma import TrendMACrossover


def _cfg():
    return {
        "strategy": {"active": "trend", "allow_short": False,
                     "trend": {"fast_window": 10, "slow_window": 30}},
        "risk": {"max_position_pct": 0.2, "max_gross_exposure": 1.0,
                 "max_positions": 10, "stop_loss_pct": 0.05, "take_profit_pct": 0.1},
        "backtest": {"initial_cash": 100_000},
    }


def _ohlcv(close):
    idx = pd.date_range("2023-01-01", periods=len(close), freq="D")
    return pd.DataFrame({"open": close, "high": close, "low": close,
                         "close": close, "volume": 1000}, index=idx)


def test_backtester_produces_equity_curve():
    # Two trending series so the trend strategy takes positions.
    data = {
        "AAA": _ohlcv(np.linspace(100, 180, 150)),
        "BBB": _ohlcv(np.linspace(50, 90, 150)),
    }
    result = Backtester(_cfg(), TrendMACrossover(10, 30)).run(data)
    eq = result["equity_curve"]
    assert len(eq) == 150
    assert result["metrics"]["num_trades"] >= 0
    assert "total_return_pct" in result["metrics"]


def test_backtester_makes_money_in_clean_uptrend():
    data = {"AAA": _ohlcv(np.linspace(100, 300, 200))}
    result = Backtester(_cfg(), TrendMACrossover(10, 30)).run(data)
    # A monotic uptrend that the crossover rides should not lose money.
    assert result["metrics"]["end_equity"] >= result["metrics"]["start_equity"]


def test_max_drawdown_simple():
    eq = pd.Series([100, 120, 90, 110])  # peak 120 -> trough 90 = 25%
    assert abs(max_drawdown(eq) - 0.25) < 1e-9


def test_compute_metrics_hit_rate():
    eq = pd.Series([100, 101, 102, 103],
                   index=pd.date_range("2023-01-01", periods=4))
    trades = [{"pnl": 10}, {"pnl": -5}, {"pnl": 20}]
    m = compute_metrics(eq, trades)
    assert m["num_trades"] == 3
    assert abs(m["hit_rate_pct"] - 66.67) < 0.1

"""Unit tests for the trading strategies (no network required)."""
import numpy as np
import pandas as pd

from strategy.mean_reversion import MeanReversion
from strategy.trend_ma import TrendMACrossover


def _ohlcv(close: np.ndarray) -> pd.DataFrame:
    idx = pd.date_range("2023-01-01", periods=len(close), freq="D")
    return pd.DataFrame(
        {"open": close, "high": close, "low": close, "close": close,
         "volume": np.full(len(close), 1000)},
        index=idx,
    )


def test_trend_goes_long_in_uptrend():
    close = np.linspace(100, 200, 120)  # steady uptrend
    df = _ohlcv(close)
    strat = TrendMACrossover(fast_window=10, slow_window=30)
    assert strat.latest_signal(df) == 1


def test_trend_goes_short_in_downtrend():
    close = np.linspace(200, 100, 120)  # steady downtrend
    df = _ohlcv(close)
    strat = TrendMACrossover(fast_window=10, slow_window=30)
    assert strat.latest_signal(df) == -1


def test_trend_rejects_bad_windows():
    try:
        TrendMACrossover(fast_window=50, slow_window=20)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_mean_reversion_buys_the_dip():
    close = np.full(60, 100.0)
    close[-1] = 80.0  # sharp drop -> strongly negative z-score -> buy
    df = _ohlcv(close)
    strat = MeanReversion(lookback=20, entry_z=2.0, exit_z=0.5)
    assert strat.latest_signal(df) == 1


def test_mean_reversion_sells_the_spike():
    close = np.full(60, 100.0)
    close[-1] = 120.0  # sharp spike -> strongly positive z-score -> sell/short
    df = _ohlcv(close)
    strat = MeanReversion(lookback=20, entry_z=2.0, exit_z=0.5)
    assert strat.latest_signal(df) == -1


def test_signal_series_aligned_to_index():
    df = _ohlcv(np.linspace(100, 150, 80))
    sig = TrendMACrossover(10, 30).generate_signals(df)
    assert len(sig) == len(df)
    assert set(sig.unique()).issubset({-1, 0, 1})

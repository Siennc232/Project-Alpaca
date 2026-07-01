"""Trend-following strategy: dual moving-average crossover.

Intuition: prices trend, and momentum persists over intermediate horizons.
When a fast moving average rises above a slow one the recent trend is up, so we
go long; when it falls below, the trend is down, so we exit (or short).
"""
from __future__ import annotations

import pandas as pd

from strategy.base import Strategy


class TrendMACrossover(Strategy):
    name = "trend"

    def __init__(self, fast_window: int = 20, slow_window: int = 50):
        if fast_window >= slow_window:
            raise ValueError("fast_window must be < slow_window")
        self.fast_window = fast_window
        self.slow_window = slow_window

    def generate_signals(self, prices: pd.DataFrame) -> pd.Series:
        close = prices["close"]
        fast = close.rolling(self.fast_window).mean()
        slow = close.rolling(self.slow_window).mean()

        signal = pd.Series(0, index=prices.index, dtype=int)
        signal[fast > slow] = 1
        signal[fast < slow] = -1
        # Before the slow MA has enough data the signal is undefined -> flat.
        signal[slow.isna()] = 0
        return signal

    def describe(self) -> str:
        return f"Trend MA crossover ({self.fast_window}/{self.slow_window})"

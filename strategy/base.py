"""Strategy interface shared by all systematic strategies.

Signal convention (per bar, per symbol):
    +1  -> desired LONG
     0  -> desired FLAT
    -1  -> desired SHORT

A strategy consumes a single-symbol OHLCV DataFrame and returns a signal Series
aligned to its index. The same method serves both live trading (take the last
value) and backtesting (use the whole series), which keeps the two modes in sync.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd


class Strategy(ABC):
    name: str = "base"

    @abstractmethod
    def generate_signals(self, prices: pd.DataFrame) -> pd.Series:
        """Return an int signal Series (-1/0/+1) indexed like `prices`."""
        raise NotImplementedError

    def latest_signal(self, prices: pd.DataFrame) -> int:
        """Convenience: the most recent signal for live trading."""
        sig = self.generate_signals(prices)
        if sig.empty:
            return 0
        return int(sig.iloc[-1])

    def describe(self) -> str:
        return self.name

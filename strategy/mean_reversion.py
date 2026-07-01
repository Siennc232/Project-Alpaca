"""Mean-reversion strategy: z-score of price vs its rolling mean.

Intuition: over short horizons prices over-react and then revert to a local
average. We measure how many standard deviations price sits from its rolling
mean (the z-score). When price is unusually cheap (z <= -entry) we buy; when
unusually rich (z >= +entry) we sell/short; we flatten once |z| falls back
inside the exit band. Positions are held between entry and exit via forward-fill.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from strategy.base import Strategy


class MeanReversion(Strategy):
    name = "mean_reversion"

    def __init__(self, lookback: int = 20, entry_z: float = 2.0, exit_z: float = 0.5):
        if entry_z <= exit_z:
            raise ValueError("entry_z must be greater than exit_z")
        self.lookback = lookback
        self.entry_z = entry_z
        self.exit_z = exit_z

    def zscore(self, prices: pd.DataFrame) -> pd.Series:
        close = prices["close"]
        mean = close.rolling(self.lookback).mean()
        std = close.rolling(self.lookback).std()
        return (close - mean) / std.replace(0, np.nan)

    def generate_signals(self, prices: pd.DataFrame) -> pd.Series:
        z = self.zscore(prices)

        # Raw markers: enter long/short at the entry band, flatten inside exit.
        raw = pd.Series(np.nan, index=prices.index, dtype="float64")
        raw[z <= -self.entry_z] = 1.0     # too cheap -> buy
        raw[z >= self.entry_z] = -1.0     # too rich  -> sell/short
        raw[z.abs() <= self.exit_z] = 0.0  # reverted  -> flat

        # Hold the last decision between an entry and its exit.
        signal = raw.ffill().fillna(0.0).astype(int)
        return signal

    def describe(self) -> str:
        return (
            f"Mean reversion (lookback={self.lookback}, "
            f"entry={self.entry_z}sigma, exit={self.exit_z}sigma)"
        )

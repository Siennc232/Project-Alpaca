"""Market-data fetching: turn Alpaca responses into tidy per-symbol DataFrames."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, List

import pandas as pd

from data.alpaca_client import AlpacaClient


def _split_by_symbol(df: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    """Split alpaca's multi-index (symbol, timestamp) bars frame into a dict."""
    out: Dict[str, pd.DataFrame] = {}
    if df is None or df.empty:
        return out
    # alpaca-py returns a MultiIndex [symbol, timestamp]; normalise it.
    if isinstance(df.index, pd.MultiIndex):
        for symbol in df.index.get_level_values(0).unique():
            sub = df.xs(symbol, level=0).copy()
            sub.index = pd.to_datetime(sub.index)
            out[str(symbol)] = sub.sort_index()
    else:
        out["_"] = df.sort_index()
    return out


def fetch_history(
    client: AlpacaClient,
    symbols: List[str],
    timeframe: str,
    lookback_days: int,
) -> Dict[str, pd.DataFrame]:
    """Fetch the last `lookback_days` of bars for each symbol."""
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=lookback_days)
    df = client.get_bars(symbols, timeframe, start=start, end=end)
    return _split_by_symbol(df)


def fetch_range(
    client: AlpacaClient,
    symbols: List[str],
    timeframe: str,
    start: str,
    end: str,
) -> Dict[str, pd.DataFrame]:
    """Fetch bars between two ISO date strings (used for backtesting)."""
    s = pd.Timestamp(start, tz="UTC")
    e = pd.Timestamp(end, tz="UTC")
    df = client.get_bars(symbols, timeframe, start=s, end=e)
    return _split_by_symbol(df)


def fetch_latest_prices(client: AlpacaClient, symbols: List[str]) -> Dict[str, float]:
    """Return {symbol: mid-price} from the latest quotes."""
    quotes = client.get_latest_quotes(symbols)
    prices: Dict[str, float] = {}
    for symbol, q in quotes.items():
        bid = float(getattr(q, "bid_price", 0) or 0)
        ask = float(getattr(q, "ask_price", 0) or 0)
        if bid and ask:
            prices[symbol] = (bid + ask) / 2.0
        elif ask:
            prices[symbol] = ask
        elif bid:
            prices[symbol] = bid
    return prices

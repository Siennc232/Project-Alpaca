"""Thin wrapper around the alpaca-py trading and market-data clients.

Centralises client construction and exposes the handful of account / order /
market-data helpers the rest of the system needs, so no other module talks to
alpaca-py directly.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from alpaca.data.enums import DataFeed
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest, StockLatestQuoteRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, OrderType, TimeInForce
from alpaca.trading.requests import (
    GetOrdersRequest,
    LimitOrderRequest,
    MarketOrderRequest,
)


# Map human-friendly timeframe strings from config to alpaca TimeFrame objects.
_TIMEFRAME_MAP = {
    "1Min": TimeFrame(1, TimeFrameUnit.Minute),
    "5Min": TimeFrame(5, TimeFrameUnit.Minute),
    "15Min": TimeFrame(15, TimeFrameUnit.Minute),
    "1Hour": TimeFrame(1, TimeFrameUnit.Hour),
    "1Day": TimeFrame(1, TimeFrameUnit.Day),
}


def parse_timeframe(name: str) -> TimeFrame:
    if name not in _TIMEFRAME_MAP:
        raise ValueError(f"Unsupported timeframe '{name}'. Choose one of {list(_TIMEFRAME_MAP)}")
    return _TIMEFRAME_MAP[name]


_FEED_MAP = {"iex": DataFeed.IEX, "sip": DataFeed.SIP, "otc": DataFeed.OTC}


class AlpacaClient:
    """Holds the trading + historical-data clients and account helpers.

    `feed` selects the market-data source. Free Alpaca accounts must use "iex"
    (the default); "sip" requires a paid data subscription.
    """

    def __init__(self, api_key: str, secret_key: str, paper: bool = True, feed: str = "iex"):
        if not api_key or not secret_key:
            raise ValueError(
                "Missing Alpaca credentials. Set ALPACA_API_KEY / ALPACA_SECRET_KEY in .env"
            )
        self.trading = TradingClient(api_key, secret_key, paper=paper)
        self.data = StockHistoricalDataClient(api_key, secret_key)
        self.feed = _FEED_MAP.get(feed.lower(), DataFeed.IEX)

    # ------------------------------------------------------------------ account
    def get_account(self) -> Any:
        return self.trading.get_account()

    def get_equity(self) -> float:
        return float(self.get_account().equity)

    def get_buying_power(self) -> float:
        return float(self.get_account().buying_power)

    def get_positions(self) -> List[Any]:
        return self.trading.get_all_positions()

    def get_position_map(self) -> Dict[str, float]:
        """Return {symbol: signed qty} for current positions."""
        out: Dict[str, float] = {}
        for p in self.get_positions():
            out[p.symbol] = float(p.qty)
        return out

    # ------------------------------------------------------------------- orders
    def submit_market_order(
        self, symbol: str, qty: float, side: OrderSide, tif: TimeInForce
    ) -> Any:
        req = MarketOrderRequest(symbol=symbol, qty=qty, side=side, time_in_force=tif)
        return self.trading.submit_order(order_data=req)

    def submit_limit_order(
        self, symbol: str, qty: float, side: OrderSide, tif: TimeInForce, limit_price: float
    ) -> Any:
        req = LimitOrderRequest(
            symbol=symbol,
            qty=qty,
            side=side,
            time_in_force=tif,
            limit_price=round(limit_price, 2),
        )
        return self.trading.submit_order(order_data=req)

    def get_orders(self, status: str = "all", limit: int = 50) -> List[Any]:
        req = GetOrdersRequest(status=status, limit=limit)
        return self.trading.get_orders(filter=req)

    def cancel_all_orders(self) -> Any:
        return self.trading.cancel_orders()

    # ---------------------------------------------------------------- marketdata
    def get_bars(self, symbols: List[str], timeframe: str, start, end=None):
        """Return a (possibly multi-index) DataFrame of OHLCV bars."""
        req = StockBarsRequest(
            symbol_or_symbols=symbols,
            timeframe=parse_timeframe(timeframe),
            start=start,
            end=end,
            feed=self.feed,
        )
        return self.data.get_stock_bars(req).df

    def get_latest_quotes(self, symbols: List[str]) -> Dict[str, Any]:
        req = StockLatestQuoteRequest(symbol_or_symbols=symbols, feed=self.feed)
        return self.data.get_stock_latest_quote(req)


# Re-export enums so callers need only import from this module.
__all__ = [
    "AlpacaClient",
    "OrderSide",
    "OrderType",
    "TimeInForce",
    "parse_timeframe",
]

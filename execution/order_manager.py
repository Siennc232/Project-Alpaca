"""Order submission + state tracking against the Alpaca paper account.

Wraps AlpacaClient order calls with error handling and records every order to
storage so the UI can display order state (submitted / filled / canceled / etc).
"""
from __future__ import annotations

from typing import Any, Optional

from alpaca.common.exceptions import APIError

from data.alpaca_client import AlpacaClient, OrderSide, TimeInForce
from data.storage import Storage


_TIF_MAP = {
    "day": TimeInForce.DAY,
    "gtc": TimeInForce.GTC,
    "ioc": TimeInForce.IOC,
    "fok": TimeInForce.FOK,
}


class OrderManager:
    def __init__(self, client: AlpacaClient, storage: Storage, logger=None):
        self.client = client
        self.storage = storage
        self.logger = logger

    def _log(self, level: str, msg: str) -> None:
        if self.logger:
            getattr(self.logger, level, self.logger.info)(msg)
        self.storage.log_event(level.upper(), msg)

    def submit(
        self,
        symbol: str,
        qty: int,
        side: str,          # "buy" or "sell"
        order_type: str = "market",
        tif: str = "day",
        price: Optional[float] = None,
    ) -> Optional[Any]:
        """Submit an order, handling API/network errors gracefully."""
        if qty <= 0:
            self._log("warning", f"Skipped {side} {symbol}: qty={qty}")
            return None

        order_side = OrderSide.BUY if side == "buy" else OrderSide.SELL
        time_in_force = _TIF_MAP.get(tif, TimeInForce.DAY)

        try:
            if order_type == "limit" and price:
                order = self.client.submit_limit_order(
                    symbol, qty, order_side, time_in_force, price
                )
            else:
                order = self.client.submit_market_order(
                    symbol, qty, order_side, time_in_force
                )
        except APIError as exc:
            self._log("error", f"Order rejected {side} {qty} {symbol}: {exc}")
            self.storage.save_order("REJECTED", symbol, side, qty, order_type, "rejected", price)
            return None
        except Exception as exc:  # network / unexpected
            self._log("error", f"Order error {side} {qty} {symbol}: {exc}")
            self.storage.save_order("ERROR", symbol, side, qty, order_type, "error", price)
            return None

        self.storage.save_order(
            str(order.id), symbol, side, qty, order_type, str(order.status), price
        )
        self._log("info", f"Submitted {side} {qty} {symbol} ({order.status})")
        return order

    def reconcile(self, limit: int = 50) -> None:
        """Refresh recent order statuses from Alpaca into storage."""
        try:
            orders = self.client.get_orders(status="all", limit=limit)
        except Exception as exc:
            self._log("error", f"Could not fetch orders: {exc}")
            return
        for o in orders:
            filled_price = getattr(o, "filled_avg_price", None)
            price = float(filled_price) if filled_price else None
            self.storage.save_order(
                str(o.id), o.symbol, str(o.side.value if hasattr(o.side, "value") else o.side),
                float(o.qty), str(o.order_type.value if hasattr(o.order_type, "value") else o.order_type),
                str(o.status.value if hasattr(o.status, "value") else o.status), price,
            )

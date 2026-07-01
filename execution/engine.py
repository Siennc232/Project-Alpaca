"""Trading engine: the live paper-trading loop.

One `step()` does the full cycle:
    1. pull recent history for the universe
    2. compute the strategy signal for each symbol
    3. apply stop-loss / take-profit to open positions
    4. turn target positions into buy/sell orders (risk-checked)
    5. persist signals, orders, equity for the UI

Designed so the UI can drive it one step at a time (Start/Stop) or the CLI can
loop it on an interval.
"""
from __future__ import annotations

import time
from typing import Any, Dict, Optional

from data.alpaca_client import AlpacaClient
from data.fetcher import fetch_history
from data.storage import Storage
from execution.order_manager import OrderManager
from risk.risk_manager import RiskLimits, RiskManager
from strategy.base import Strategy


class TradingEngine:
    def __init__(self, cfg: Dict[str, Any], strategy: Strategy, logger=None):
        self.cfg = cfg
        self.strategy = strategy
        self.logger = logger

        self.client = AlpacaClient(
            cfg["alpaca"]["api_key"],
            cfg["alpaca"]["secret_key"],
            paper=cfg["alpaca"].get("paper", True),
            feed=cfg["data"].get("feed", "iex"),
        )
        self.storage = Storage(cfg["data"]["db_path"])
        self.orders = OrderManager(self.client, self.storage, logger)
        self.risk = RiskManager(RiskLimits.from_config(cfg))

        self.universe = cfg["universe"]
        self.allow_short = cfg["strategy"].get("allow_short", False)
        self.order_type = cfg["execution"].get("order_type", "market")
        self.tif = cfg["execution"].get("time_in_force", "day")
        self.last_step_summary: Dict[str, Any] = {}

    def _log(self, level: str, msg: str) -> None:
        if self.logger:
            getattr(self.logger, level, self.logger.info)(msg)

    # --------------------------------------------------------------------- step
    def step(self) -> Dict[str, Any]:
        """Run one full data -> signal -> risk -> order cycle."""
        summary: Dict[str, Any] = {"signals": {}, "orders": [], "exits": []}

        equity = self.client.get_equity()
        history = fetch_history(
            self.client, self.universe,
            self.cfg["data"]["timeframe"], self.cfg["data"]["lookback_days"],
        )
        positions = self._position_details()
        pos_qty = {s: d["qty"] for s, d in positions.items()}
        gross = sum(abs(d["qty"]) * d["price"] for d in positions.values())

        # Symbols with a live order: skip them so we never stack duplicate
        # orders (Alpaca rejects those as "potential wash trade").
        try:
            open_order_symbols = self.client.get_open_order_symbols()
        except Exception:
            open_order_symbols = set()
        summary["market_open"] = self.client.is_market_open()

        for symbol in self.universe:
            df = history.get(symbol)
            if df is None or df.empty:
                continue

            # Persist the latest bar for the record.
            self.storage.save_bars(symbol, df.tail(1))
            last_price = float(df["close"].iloc[-1])

            # Skip anything that already has a pending order this bar.
            if symbol in open_order_symbols:
                summary.setdefault("skipped", []).append(symbol)
                continue

            # 1) stop-loss / take-profit on any open position
            if symbol in positions and positions[symbol]["qty"] != 0:
                d = positions[symbol]
                side = 1 if d["qty"] > 0 else -1
                exit_now, reason = self.risk.should_exit(d["entry"], last_price, side)
                if exit_now:
                    close_side = "sell" if d["qty"] > 0 else "buy"
                    self.orders.submit(symbol, int(abs(d["qty"])), close_side,
                                       self.order_type, self.tif, last_price)
                    summary["exits"].append({"symbol": symbol, "reason": reason})
                    continue  # don't also act on signal this bar

            # 2) strategy signal
            raw_signal = self.strategy.latest_signal(df)
            signal = raw_signal if (self.allow_short or raw_signal >= 0) else 0
            self.storage.save_signal(symbol, signal, self.strategy.name, last_price)
            summary["signals"][symbol] = signal

            # 3) target position -> order to close the gap
            self._rebalance_symbol(symbol, signal, last_price, equity,
                                  pos_qty, gross, summary)

        # Record equity snapshot for the P&L curve.
        try:
            acct = self.client.get_account()
            self.storage.save_equity(float(acct.equity), float(acct.cash))
        except Exception:
            pass

        self.last_step_summary = summary
        self._log("info", f"Step done: {len(summary['orders'])} orders, "
                          f"{len(summary['exits'])} exits")
        return summary

    def _rebalance_symbol(self, symbol, signal, price, equity, pos_qty, gross, summary):
        current = pos_qty.get(symbol, 0)
        target = 0
        if signal != 0:
            target = self.risk.target_qty(equity, price) * signal

        delta = target - current
        if delta == 0:
            return

        side = "buy" if delta > 0 else "sell"
        qty = int(abs(delta))

        # Only risk-check orders that increase exposure (opening/adding).
        increases = abs(target) > abs(current)
        if increases:
            ok, reason = self.risk.check_order(
                symbol, qty, price, equity, pos_qty, gross
            )
            if not ok:
                self.storage.log_event("WARNING", f"Risk blocked {side} {qty} {symbol}: {reason}")
                self._log("warning", f"Risk blocked {side} {qty} {symbol}: {reason}")
                return

        order = self.orders.submit(symbol, qty, side, self.order_type, self.tif, price)
        if order is not None:
            pos_qty[symbol] = target
            summary["orders"].append({"symbol": symbol, "side": side, "qty": qty})

    def _position_details(self) -> Dict[str, Dict[str, float]]:
        out: Dict[str, Dict[str, float]] = {}
        try:
            for p in self.client.get_positions():
                out[p.symbol] = {
                    "qty": float(p.qty),
                    "entry": float(p.avg_entry_price),
                    "price": float(p.current_price or p.avg_entry_price),
                }
        except Exception as exc:
            self._log("error", f"Could not read positions: {exc}")
        return out

    # --------------------------------------------------------------------- loop
    def run_forever(self, interval: int = 60, max_iterations: Optional[int] = None,
                    should_continue=None) -> None:
        """CLI loop. `should_continue` is an optional callable returning bool."""
        i = 0
        while True:
            if should_continue is not None and not should_continue():
                break
            if max_iterations is not None and i >= max_iterations:
                break
            try:
                self.step()
            except Exception as exc:
                self._log("error", f"Step failed: {exc}")
            i += 1
            if max_iterations is not None and i >= max_iterations:
                break
            time.sleep(interval)

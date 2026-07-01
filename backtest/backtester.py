"""Event-driven portfolio backtester.

Runs the same strategy + risk sizing used live over historical bars, so results
are comparable to paper trading. Signals are shifted by one bar (act on the next
bar's close) to avoid look-ahead bias. Fills are at the close with no slippage
or commissions — a simplification noted in the README limitations.
"""
from __future__ import annotations

from typing import Any, Dict, List

import numpy as np
import pandas as pd

from backtest.metrics import compute_metrics
from risk.risk_manager import RiskLimits, RiskManager
from strategy.base import Strategy


class Backtester:
    def __init__(self, cfg: Dict[str, Any], strategy: Strategy):
        self.cfg = cfg
        self.strategy = strategy
        self.risk = RiskManager(RiskLimits.from_config(cfg))
        self.allow_short = cfg["strategy"].get("allow_short", False)
        self.initial_cash = cfg["backtest"].get("initial_cash", 100_000)
        self.max_gross = cfg["risk"].get("max_gross_exposure", 1.0)

    def run(self, price_data: Dict[str, pd.DataFrame]) -> Dict[str, Any]:
        """Simulate the portfolio over the supplied per-symbol OHLCV frames."""
        symbols = [s for s, df in price_data.items() if df is not None and not df.empty]
        if not symbols:
            return {"equity_curve": pd.Series(dtype=float), "trades": [], "metrics": {}}

        # Align every symbol onto a shared calendar of closes and signals.
        closes = pd.DataFrame(
            {s: price_data[s]["close"] for s in symbols}
        ).sort_index().ffill()

        signals = {}
        for s in symbols:
            sig = self.strategy.generate_signals(price_data[s])
            sig = sig.reindex(closes.index).ffill().fillna(0)
            if not self.allow_short:
                sig = sig.clip(lower=0)
            signals[s] = sig.shift(1).fillna(0)  # act on next bar -> no look-ahead
        signal_df = pd.DataFrame(signals)

        cash = float(self.initial_cash)
        holdings: Dict[str, float] = {s: 0.0 for s in symbols}
        entry: Dict[str, float] = {s: 0.0 for s in symbols}
        trades: List[Dict[str, Any]] = []
        equity_records: Dict[Any, float] = {}

        for ts in closes.index:
            prices = closes.loc[ts]
            equity = cash + sum(holdings[s] * prices[s] for s in symbols if not np.isnan(prices[s]))
            if equity <= 0:
                equity_records[ts] = equity
                continue

            # Desired quantity per symbol from signal + per-asset sizing.
            targets: Dict[str, int] = {}
            for s in symbols:
                px = prices[s]
                if np.isnan(px) or px <= 0:
                    targets[s] = int(holdings[s])
                    continue
                sig = int(signal_df.loc[ts, s])
                targets[s] = self.risk.target_qty(equity, px) * sig

            # Enforce gross-exposure cap by scaling all targets down together.
            gross = sum(abs(targets[s]) * prices[s] for s in symbols if not np.isnan(prices[s]))
            cap = equity * self.max_gross
            if gross > cap and gross > 0:
                scale = cap / gross
                targets = {s: int(q * scale) for s, q in targets.items()}

            # Execute the moves for this bar.
            for s in symbols:
                px = prices[s]
                if np.isnan(px) or px <= 0:
                    continue
                cash = self._apply_target(s, targets[s], px, holdings, entry, trades, cash)

            equity_records[ts] = cash + sum(
                holdings[s] * prices[s] for s in symbols if not np.isnan(prices[s])
            )

        equity_curve = pd.Series(equity_records).sort_index()
        metrics = compute_metrics(equity_curve, trades)
        return {"equity_curve": equity_curve, "trades": trades, "metrics": metrics}

    @staticmethod
    def _apply_target(symbol, target, price, holdings, entry, trades, cash) -> float:
        """Move a single position toward `target`, booking realised PnL, update cash."""
        q0 = holdings[symbol]
        if target == q0:
            return cash
        e0 = entry[symbol]
        delta = target - q0
        cash -= delta * price  # buy (delta>0) uses cash; sell/short returns cash

        closing = (q0 != 0) and (abs(target) < abs(q0) or np.sign(target) != np.sign(q0))
        if closing:
            closed_qty = q0 - (target if np.sign(target) == np.sign(q0) else 0)
            pnl = (price - e0) * closed_qty
            trades.append({"symbol": symbol, "pnl": float(pnl), "price": float(price)})
            if np.sign(target) != np.sign(q0) and target != 0:
                entry[symbol] = price  # flipped into a fresh position
        elif q0 == 0 and target != 0:
            entry[symbol] = price      # opened new
        elif np.sign(target) == np.sign(q0) and abs(target) > abs(q0):
            # Added to an existing position -> weighted-average entry.
            entry[symbol] = (e0 * abs(q0) + price * abs(delta)) / abs(target)

        holdings[symbol] = target
        return cash

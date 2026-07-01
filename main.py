"""Command-line entrypoint for the Alpaca systematic trading system.

Examples
--------
  # One paper-trading cycle (safe way to test the pipeline):
  python main.py --mode paper --once

  # Continuous paper trading, one cycle every 60s:
  python main.py --mode paper --interval 60

  # Backtest the configured strategy over the config date range:
  python main.py --mode backtest

  # Override the active strategy from the CLI:
  python main.py --mode backtest --strategy mean_reversion
"""
from __future__ import annotations

import argparse
import sys

from config.loader import has_credentials, load_config
from utils.logging_config import setup_logger


def run_backtest(cfg, logger) -> None:
    from backtest.backtester import Backtester
    from data.alpaca_client import AlpacaClient
    from data.fetcher import fetch_range
    from strategy.registry import build_strategy

    strategy = build_strategy(cfg)
    logger.info(f"Backtesting: {strategy.describe()}")

    client = AlpacaClient(cfg["alpaca"]["api_key"], cfg["alpaca"]["secret_key"],
                          paper=cfg["alpaca"].get("paper", True),
                          feed=cfg["data"].get("feed", "iex"))
    bt = cfg["backtest"]
    price_data = fetch_range(client, cfg["universe"], cfg["data"]["timeframe"],
                             bt["start"], bt["end"])
    logger.info(f"Fetched history for {len(price_data)} symbols "
                f"({bt['start']} -> {bt['end']})")

    result = Backtester(cfg, strategy).run(price_data)
    metrics = result["metrics"]
    print("\n===== Backtest results =====")
    for k, v in metrics.items():
        print(f"  {k:22s}: {v}")
    print("============================\n")


def run_paper(cfg, logger, once: bool, interval: int) -> None:
    from execution.engine import TradingEngine
    from strategy.registry import build_strategy

    strategy = build_strategy(cfg)
    logger.info(f"Paper trading: {strategy.describe()}")
    engine = TradingEngine(cfg, strategy, logger)

    if once:
        summary = engine.step()
        print("\n===== Step summary =====")
        print(f"  signals: {summary['signals']}")
        print(f"  orders : {summary['orders']}")
        print(f"  exits  : {summary['exits']}")
        print("========================\n")
    else:
        logger.info(f"Looping every {interval}s. Ctrl-C to stop.")
        try:
            engine.run_forever(interval=interval)
        except KeyboardInterrupt:
            logger.info("Stopped by user.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Alpaca systematic trading system")
    parser.add_argument("--mode", choices=["paper", "backtest"], default=None,
                        help="override config mode")
    parser.add_argument("--strategy", choices=["trend", "mean_reversion"], default=None,
                        help="override active strategy")
    parser.add_argument("--once", action="store_true", help="run a single paper cycle")
    parser.add_argument("--interval", type=int, default=60,
                        help="seconds between paper cycles (loop mode)")
    args = parser.parse_args()

    logger = setup_logger()
    cfg = load_config()
    if args.mode:
        cfg["mode"] = args.mode
    if args.strategy:
        cfg["strategy"]["active"] = args.strategy

    if not has_credentials(cfg):
        logger.error("Missing Alpaca credentials. Copy .env.example to .env and fill it in.")
        return 1

    if cfg["mode"] == "backtest":
        run_backtest(cfg, logger)
    else:
        run_paper(cfg, logger, once=args.once, interval=args.interval)
    return 0


if __name__ == "__main__":
    sys.exit(main())

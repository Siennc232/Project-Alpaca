"""Streamlit dashboard: monitor and control the trading system.

Run with:  streamlit run ui/app.py
Shows account status, positions/P&L, recent signals and orders, an equity curve,
and a backtest tab. Start/Stop drives the engine one step at a time from the UI.
"""
from __future__ import annotations

import pathlib
import sys
import time

# Make the repo root importable when Streamlit runs this file directly.
ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st

from config.loader import has_credentials, load_config
from strategy.registry import build_strategy

st.set_page_config(page_title="Alpaca Trading System", layout="wide")


# --------------------------------------------------------------------- helpers
@st.cache_resource
def get_config():
    return load_config()


def get_engine(cfg):
    """Build (once) and cache the TradingEngine in session state."""
    from execution.engine import TradingEngine
    strat_name = cfg["strategy"]["active"]
    key = f"engine_{strat_name}"
    if key not in st.session_state:
        st.session_state[key] = TradingEngine(cfg, build_strategy(cfg))
    return st.session_state[key]


cfg = get_config()

# ------------------------------------------------------------------- sidebar
st.sidebar.title("Control panel")

if not has_credentials(cfg):
    st.sidebar.error("No Alpaca credentials found. Copy .env.example -> .env.")

mode = st.sidebar.radio("Mode", ["paper", "backtest"],
                        index=0 if cfg["mode"] == "paper" else 1)
cfg["mode"] = mode

strategy_name = st.sidebar.selectbox(
    "Strategy", ["trend", "mean_reversion"],
    index=0 if cfg["strategy"]["active"] == "trend" else 1,
)
cfg["strategy"]["active"] = strategy_name

st.sidebar.subheader("Strategy parameters")
if strategy_name == "trend":
    cfg["strategy"]["trend"]["fast_window"] = st.sidebar.number_input(
        "Fast MA", 2, 200, cfg["strategy"]["trend"]["fast_window"])
    cfg["strategy"]["trend"]["slow_window"] = st.sidebar.number_input(
        "Slow MA", 3, 400, cfg["strategy"]["trend"]["slow_window"])
else:
    cfg["strategy"]["mean_reversion"]["lookback"] = st.sidebar.number_input(
        "Lookback", 2, 200, cfg["strategy"]["mean_reversion"]["lookback"])
    cfg["strategy"]["mean_reversion"]["entry_z"] = st.sidebar.number_input(
        "Entry z", 0.5, 5.0, float(cfg["strategy"]["mean_reversion"]["entry_z"]), 0.1)
    cfg["strategy"]["mean_reversion"]["exit_z"] = st.sidebar.number_input(
        "Exit z", 0.0, 3.0, float(cfg["strategy"]["mean_reversion"]["exit_z"]), 0.1)

st.sidebar.subheader("Risk limits")
cfg["risk"]["max_position_pct"] = st.sidebar.slider(
    "Max position (% equity)", 0.01, 1.0, float(cfg["risk"]["max_position_pct"]), 0.01)
cfg["risk"]["max_gross_exposure"] = st.sidebar.slider(
    "Max gross exposure", 0.1, 2.0, float(cfg["risk"]["max_gross_exposure"]), 0.1)
cfg["risk"]["stop_loss_pct"] = st.sidebar.slider(
    "Stop loss (%)", 0.0, 0.5, float(cfg["risk"]["stop_loss_pct"]), 0.01)

st.session_state.setdefault("running", False)

# ==================================================================== main body
st.title("📈 Alpaca Systematic Trading System")

tab_live, tab_backtest = st.tabs(["Live / Paper", "Backtest"])

# ------------------------------------------------------------------- live tab
with tab_live:
    if mode != "paper":
        st.info("Switch Mode to **paper** in the sidebar to use the live dashboard.")
    elif not has_credentials(cfg):
        st.warning("Add Alpaca credentials to .env to connect.")
    else:
        engine = get_engine(cfg)
        # Reflect any live sidebar edits onto the running engine.
        engine.risk.limits.max_position_pct = cfg["risk"]["max_position_pct"]
        engine.risk.limits.max_gross_exposure = cfg["risk"]["max_gross_exposure"]
        engine.risk.limits.stop_loss_pct = cfg["risk"]["stop_loss_pct"]

        c1, c2, c3, c4 = st.columns(4)
        try:
            acct = engine.client.get_account()
            connected = True
            c1.metric("Status", "🟢 Connected")
            c2.metric("Equity", f"${float(acct.equity):,.0f}")
            c3.metric("Buying power", f"${float(acct.buying_power):,.0f}")
            c4.metric("Cash", f"${float(acct.cash):,.0f}")
        except Exception as exc:
            connected = False
            c1.metric("Status", "🔴 Disconnected")
            st.error(f"Could not reach Alpaca: {exc}")

        # ---- controls
        b1, b2, b3, _ = st.columns([1, 1, 1, 3])
        if b1.button("▶ Start", use_container_width=True):
            st.session_state.running = True
        if b2.button("⏹ Stop", use_container_width=True):
            st.session_state.running = False
        step_now = b3.button("⏭ Run one step", use_container_width=True)

        st.caption(f"Engine state: {'🟢 RUNNING' if st.session_state.running else '⚪ stopped'} "
                   f"· strategy: {engine.strategy.describe()}")

        if connected and (step_now or st.session_state.running):
            with st.spinner("Running a trading cycle..."):
                try:
                    summary = engine.step()
                    st.success(f"Cycle complete — {len(summary['orders'])} orders, "
                               f"{len(summary['exits'])} risk exits.")
                except Exception as exc:
                    st.error(f"Cycle failed: {exc}")

        # ---- positions
        st.subheader("Positions")
        try:
            positions = engine.client.get_positions()
            if positions:
                pos_df = pd.DataFrame([{
                    "symbol": p.symbol,
                    "qty": float(p.qty),
                    "avg_entry": float(p.avg_entry_price),
                    "current": float(p.current_price or 0),
                    "market_value": float(p.market_value or 0),
                    "unrealized_pl": float(p.unrealized_pl or 0),
                    "unrealized_pct": round(float(p.unrealized_plpc or 0) * 100, 2),
                } for p in positions])
                st.dataframe(pos_df, use_container_width=True, hide_index=True)
            else:
                st.info("No open positions.")
        except Exception as exc:
            st.warning(f"Positions unavailable: {exc}")

        # ---- signals, orders, equity from storage
        col_a, col_b = st.columns(2)
        with col_a:
            st.subheader("Recent signals")
            sig = engine.storage.recent_signals(30)
            st.dataframe(sig, use_container_width=True, hide_index=True) if not sig.empty \
                else st.caption("No signals recorded yet.")
        with col_b:
            st.subheader("Recent orders")
            orders = engine.storage.recent_orders(30)
            st.dataframe(orders, use_container_width=True, hide_index=True) if not orders.empty \
                else st.caption("No orders recorded yet.")

        st.subheader("Equity curve")
        eq = engine.storage.equity_curve()
        if not eq.empty:
            eq = eq.copy()
            eq["ts"] = pd.to_datetime(eq["ts"])
            st.line_chart(eq.set_index("ts")["equity"])
        else:
            st.caption("Equity history builds up as the engine runs.")

        # Auto-advance the loop while 'running'.
        if st.session_state.running and connected:
            time.sleep(5)
            st.rerun()

# --------------------------------------------------------------- backtest tab
with tab_backtest:
    st.subheader("Backtest")
    bcol1, bcol2 = st.columns(2)
    start = bcol1.text_input("Start date", cfg["backtest"]["start"])
    end = bcol2.text_input("End date", cfg["backtest"]["end"])

    if st.button("Run backtest", type="primary"):
        if not has_credentials(cfg):
            st.error("Alpaca credentials required to download historical bars.")
        else:
            with st.spinner("Downloading history and simulating..."):
                from backtest.backtester import Backtester
                from data.alpaca_client import AlpacaClient
                from data.fetcher import fetch_range
                try:
                    client = AlpacaClient(cfg["alpaca"]["api_key"],
                                          cfg["alpaca"]["secret_key"],
                                          paper=cfg["alpaca"].get("paper", True),
                                          feed=cfg["data"].get("feed", "iex"))
                    data = fetch_range(client, cfg["universe"],
                                       cfg["data"]["timeframe"], start, end)
                    result = Backtester(cfg, build_strategy(cfg)).run(data)
                except Exception as exc:
                    st.error(f"Backtest failed: {exc}")
                    result = None

            if result:
                m = result["metrics"]
                if m:
                    k1, k2, k3, k4 = st.columns(4)
                    k1.metric("Total return", f"{m['total_return_pct']}%")
                    k2.metric("Max drawdown", f"{m['max_drawdown_pct']}%")
                    k3.metric("Sharpe", m["sharpe"])
                    k4.metric("Hit rate", f"{m['hit_rate_pct']}%")
                    st.line_chart(result["equity_curve"])
                    st.json(m)
                else:
                    st.warning("No data returned for that range/universe.")

# Alpaca Systematic Trading System

An end-to-end, modular systematic trading system built on **Alpaca paper trading**.
It collects market data, generates rule-based signals from two switchable
strategies, routes orders through a risk layer, and exposes a Streamlit dashboard
to monitor and control everything. It runs in two modes: **backtest** (historical
bars) and **paper** (live Alpaca paper account).

> ⚠️ **Paper trading only.** This project never uses real money and requires no
> credit card. All orders are routed to Alpaca's paper environment
> (`https://paper-api.alpaca.markets`).

---

## 1. Goals

- Demonstrate a realistic, modular trading-system architecture (data → strategy →
  risk → execution → UI).
- Exploit two well-understood market behaviours with **switchable strategies**:
  - **Trend-following** — momentum persists, so ride established trends.
  - **Mean-reversion** — short-term over-reactions revert to a local average.
- Enforce **basic but meaningful risk controls** (position caps, gross-exposure
  cap, max positions, stop-loss / take-profit).
- Provide a monitoring/control **UI** and a reproducible **backtest**.

---

## 2. Architecture

```
                         ┌────────────────────────┐
                         │      config/            │
                         │  config.yaml + .env     │  (params + secrets)
                         └───────────┬────────────┘
                                     │ load_config()
        ┌────────────────────────────┼────────────────────────────┐
        │                            │                             │
        ▼                            ▼                             ▼
 ┌─────────────┐            ┌─────────────────┐          ┌──────────────────┐
 │   data/     │            │   strategy/     │          │     risk/        │
 │ alpaca_     │  bars      │  base           │  signal  │  risk_manager    │
 │  client     │──────────► │  trend_ma       │────────► │  - sizing        │
 │ fetcher     │  (OHLCV)   │  mean_reversion │  -1/0/+1 │  - limit checks  │
 │ storage     │            │  registry       │          │  - stop/take     │
 └──────┬──────┘            └─────────────────┘          └────────┬─────────┘
        │ SQLite                                                  │ approved qty
        │ (bars, signals,          ┌──────────────────────────────▼─────────┐
        │  orders, equity,         │            execution/                   │
        │  events)                 │   engine  (data→signal→risk→order loop) │
        │                          │   order_manager (submit + state track)  │
        │                          └───────────────────┬─────────────────────┘
        │                                               │ submit_order (paper)
        │                                               ▼
        │                                     ┌───────────────────┐
        └────────────► ui/app.py ◄────────────│   Alpaca Paper    │
             (Streamlit dashboard:            │   Trading API     │
              status, positions, P&L,         └───────────────────┘
              signals, orders, controls,
              backtest tab)

   backtest/ (backtester + metrics) reuses strategy/ and risk/ on historical bars.
```

**Data flow:** `data/` fetches OHLCV bars from Alpaca and persists them to SQLite.
`strategy/` turns bars into `-1/0/+1` signals. `risk/` sizes positions and vetoes
orders that breach limits. `execution/` reconciles current vs. target positions and
submits paper orders, tracking their state. `ui/` reads live account state + the
SQLite log to display everything and drive the engine. `backtest/` reuses the same
strategy and risk logic on historical data so results are comparable.

---

## 3. Folder structure

```
Project-Alpaca/
├── config/          config.yaml (params) + loader.py (+ .env for secrets)
├── data/            alpaca_client.py, fetcher.py, storage.py
├── strategy/        base.py, trend_ma.py, mean_reversion.py, registry.py
├── execution/       order_manager.py, engine.py
├── risk/            risk_manager.py
├── backtest/        backtester.py, metrics.py
├── ui/              app.py  (Streamlit dashboard)
├── utils/           logging_config.py
├── tests/           test_strategies.py, test_risk.py, test_backtest.py
├── logs/            SQLite db + system.log (gitignored)
├── main.py          CLI entrypoint (backtest / paper)
├── requirements.txt
└── .env.example     copy to .env and fill in your paper keys
```

---

## 4. Setup

### Prerequisites
- Python 3.10+
- A free **Alpaca paper trading** account: https://app.alpaca.markets/

### Install
```bash
git clone https://github.com/Siennc232/Project-Alpaca.git
cd Project-Alpaca
python -m venv .venv && source .venv/bin/activate    # optional
pip install -r requirements.txt
```

### Configure credentials
```bash
cp .env.example .env
# edit .env and paste your PAPER API key + secret
```
`.env` is gitignored — **never commit real keys**. `config/config.yaml` holds all
non-secret parameters (universe, strategy params, risk limits, mode, data feed).

> **Data feed:** free Alpaca accounts must use `data.feed: iex` in
> `config.yaml` (already the default). `sip` requires a paid data subscription.

---

## 5. Usage

### Run the tests
```bash
pytest -q
```

### Backtest
```bash
python main.py --mode backtest                       # uses config strategy + dates
python main.py --mode backtest --strategy mean_reversion
```
Prints total return, cumulative P&L, max drawdown, Sharpe, number of trades and
hit rate.

### Paper trading (CLI)
```bash
python main.py --mode paper --once                   # a single safe cycle
python main.py --mode paper --interval 60            # loop every 60s (Ctrl-C to stop)
```

### UI dashboard
```bash
streamlit run ui/app.py
```
Then in the browser you can:
- see **system status** (connected/disconnected, mode), account **equity / buying
  power / cash**;
- view **positions with unrealized P&L**, **recent signals**, **recent orders**,
  and an **equity curve**;
- **Start / Stop** the engine or **Run one step**;
- switch **strategy** and adjust **risk limits / strategy parameters** live;
- run a **backtest** from the Backtest tab.

---

## 6. Strategy & risk controls

### Trend-following (`strategy/trend_ma.py`)
Dual moving-average crossover. Long when the fast MA (default 20) is above the slow
MA (default 50), short/flat when below. **Intuition:** trends and momentum persist
over intermediate horizons.

### Mean-reversion (`strategy/mean_reversion.py`)
Rolling z-score of price vs. its mean (default lookback 20). Buy when
`z ≤ -entry_z` (unusually cheap), sell/short when `z ≥ +entry_z` (unusually rich),
flatten when `|z| ≤ exit_z`. **Intuition:** short-term over-reactions revert.

### Risk controls (`risk/risk_manager.py`) — applied in both modes
| Control | Config key | Default |
|---|---|---|
| Max position per asset (% equity) | `risk.max_position_pct` | 15% |
| Max gross exposure (notional / equity) | `risk.max_gross_exposure` | 1.0 (no leverage) |
| Max simultaneous positions | `risk.max_positions` | 10 |
| Stop-loss per position | `risk.stop_loss_pct` | 5% |
| Take-profit per position | `risk.take_profit_pct` | 10% |
| Long-only toggle | `strategy.allow_short` | `false` |

Every order is sized to the per-asset cap and then validated against the per-asset,
gross-exposure and max-positions limits before submission. Open positions are
checked each cycle for stop-loss / take-profit.

---

## 7. Example results

Backtest of the trend strategy on the default 8-symbol universe (2023-01-01 →
2024-12-31, daily bars, IEX feed):

| Metric | Value |
|---|---|
| Total return | ~70% |
| Max drawdown | ~15% |
| Sharpe | ~1.4 |
| Trades | ~750 |

*(Exact numbers depend on the data feed and date range. Reproduce with
`python main.py --mode backtest`.)*

---

## 8. Limitations & possible improvements

**Limitations**
- Backtest fills at the close with **no slippage or commissions**; signals are
  shifted one bar to avoid look-ahead, but real fills will differ.
- Free **IEX** feed covers a fraction of consolidated volume, so live prices can
  differ slightly from SIP.
- Position sizing is a simple fixed fraction of equity; no volatility targeting.
- The UI drives the engine one step per refresh (simple and demo-friendly) rather
  than a separate always-on process.

**Improvements**
- Volatility-scaled sizing / portfolio-level risk parity.
- Transaction-cost and slippage modelling in the backtester.
- Streaming quotes (websocket) instead of polling.
- Walk-forward parameter validation; more strategies (factor, ML).
- Persist a separate always-on engine process with the UI as a pure monitor.

---

## 9. Disclaimer

Educational project for FINM 25000. **Paper trading only** — not investment advice,
no real-money trading. Rotate any API key that has been shared.

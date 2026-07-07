# Video Narration Script · Alpaca Systematic Trading System

> Target length ~12 minutes. Four presenters (A/B/C/D). Text in `[brackets]` is a
> stage/screen direction; everything else is spoken lines you can read aloud.
> Record the live demo during US market hours. Before recording, run
> `rm logs/market_data.db` so the tables start clean.

---

## 0:00–1:00 · Intro (A)

[Screen: top of the README / a title slide]

Hi everyone. Our project is the **Alpaca Systematic Trading System**, our group project for FINM 25000. In short, we built a complete, **end-to-end trading system that actually runs**: it pulls live market data from Alpaca, generates trading signals from a set of rules, passes them through a risk layer, and automatically places orders — and there's a web dashboard to monitor and control the whole thing in real time.

One thing up front that matters most: **everything runs on Alpaca's paper-trading environment. No real money is involved, and we never entered any card details.** Every order goes to Alpaca's simulated account.

The stack is simple: Python for the core logic, Alpaca's official `alpaca-py` library for data and orders, SQLite for storage, and Streamlit for the UI. One thing we're a bit proud of: the system ships with **two strategies you can switch between on the fly** — we'll demo that later. I'll walk through the architecture first, then my teammates cover data, strategy, and execution/risk, and finally we'll run it live.

---

## 1:00–3:00 · Architecture (A)

[Screen: the architecture diagram in the README, then the folder tree in the editor]

Here's the architecture. It's fully **modular** — each piece does one job. At the top is **config**: every parameter — which tickers we trade, strategy settings, risk limits — lives in one `config.yaml`. Secrets like API keys live separately in a `.env` file that's git-ignored, so they are **never committed to the repo**.

Then the data flows down. The **data** module pulls bars from Alpaca and stores them in SQLite. The **strategy** module turns prices into signals — and we use one simple convention: **+1 means go long, 0 means flat, -1 means short**. Signals don't go straight to orders; they first pass through the **risk** module, which sizes the position and checks it against our limits. If it passes, **execution** actually sends the order to Alpaca and tracks its state. And finally the **ui** — the Streamlit dashboard — reads live account state and the SQLite logs to display everything, and it can drive the engine too.

[Screen: point at the folder tree]

One design choice we like: the system runs in two modes — **backtest** and **live paper trading** — and both **share the exact same strategy and risk code**. So the logic you see in the backtest is identical to what runs live; there's no "one version for backtest, another for live." The **backtest** module just replays that same logic over historical data. Over to B for the data pipeline and strategies.

---

## 3:00–5:00 · Data Pipeline + Strategies (B)

[Screen: open data/alpaca_client.py and fetcher.py, scroll quickly]

I'll start with data. We trade a basket of very liquid names: Apple, Microsoft, Google, Amazon, Nvidia, Meta, Tesla, plus the S&P 500 ETF — eight tickers in total. `alpaca_client.py` is a thin wrapper around Alpaca's SDK that keeps account, order, and market-data calls in one place, so nothing else touches the SDK directly. `fetcher.py` turns Alpaca's multi-index response into one clean OHLCV table per symbol and stores it in SQLite.

[Screen: config.yaml, point at the `feed: iex` line]

Here's a gotcha we hit: a free Alpaca account can only use the **IEX** data feed. If you use the default SIP feed for recent data, it errors out with "subscription does not permit." So we explicitly set `feed: iex` — that one cost us a bit of time.

[Screen: strategy/trend_ma.py]

On to strategies. The first is **trend-following**, a **moving-average crossover**: a fast average — 20 days by default — and a slow one at 50. When the fast crosses above the slow, we go long; when it crosses below, we exit or short. **The intuition:** prices trend, and momentum tends to persist over the medium term, so we ride the established trend.

[Screen: strategy/mean_reversion.py]

The second is **mean-reversion**, based on the **z-score** of price against its rolling mean. When price is unusually cheap — z below minus two standard deviations — we buy; unusually rich — z above plus two — we sell; and we flatten once it comes back near the mean. **The intuition is the opposite:** in the short term markets often over-react and then revert. Both strategies output the same +1/0/-1 signal with an identical interface, which is why we can swap them any time. Over to C for how we size and route orders.

---

## 5:00–7:00 · Execution + Risk (C)

[Screen: risk/risk_manager.py]

We have signals, but we don't just fire orders blindly — they go through risk first. We enforce a few layers: **no single stock is more than 15% of equity**; **total exposure stays under one times equity**, so no leverage by default; at most ten positions open at once; and every position has a **5% stop-loss and 10% take-profit**. In `risk_manager.py`, each order we want to place is first sized here, then checked against those limits one by one — anything that breaches a limit gets blocked.

[Screen: execution/engine.py, the step() method]

The main loop lives in `step()` in `engine.py`, and one cycle does five things: **pull the latest data, compute a signal per symbol, check open positions for stop-loss or take-profit, turn the gap between target and current positions into buy/sell orders, and log everything.**

[Screen: point at the open-orders guard / order_manager.py]

I want to highlight one real bug we hit and fixed — this is where we learned the most about real trading systems. On our first run, every order got rejected with **"potential wash trade detected."** It turned out to be two things stacked together: one, **the market was closed** at the time, so market orders just queue instead of filling; and two, our engine re-submitted an order for the same stock every cycle, while the previous one was still sitting open — so Alpaca flagged it as a duplicate, self-crossing trade and rejected it. Our fix: **before placing an order, check whether that symbol already has a pending order, and skip it if so.** We also added a market open/closed banner and a one-click "cancel orders" button. This really drove home that in real trading you have to handle market hours, order states, and exchange compliance checks — it's not just writing a submit function. Over to D to run it live.

---

## 7:00–10:30 · Live Demo (D)

[Screen: the Streamlit dashboard in the browser]

Okay, this is our dashboard. Let me go through it. [point at the top, pause ~5s] Up top is the **system status**: it shows green, Connected, so we're linked to my Alpaca paper account. To the right is account equity, buying power, and cash. This green banner shows **Market is OPEN**, which means orders placed now can actually fill.

[interact with the sidebar, pause ~10s] On the left is the control panel. I can **switch the strategy live** — say, from trend to mean-reversion — and drag these sliders to adjust the risk limits, for example the per-stock cap. **No code changes, no restart** — it takes effect immediately.

[click "Run one step", then watch the screen silently, wait ~8s] Let me click **Run one step** to run one full cycle... You can see it pulled data for all eight symbols and computed signals. The message up here tells us how many orders it placed this cycle, how many stop/take-profit exits, and how many it skipped because they had pending orders.

[click "Start", let it auto-run ~20s, point at each in turn] Now I'll click **Start** so it loops on its own. Watch: **Recent signals** is refreshing live — the S&P is at +1 right now; **Recent orders** shows new orders, and notice these have real order IDs and are **filled**, not the rejected ones from before; **Positions** shows what we're holding and the unrealized P&L; and at the bottom the **Equity curve** starts to move.

[click "Stop", pause ~3s] I can hit **Stop** to halt it any time. Starting, stopping, and every parameter — it's all in this one interface.

[switch to the "Backtest" tab, fill dates, click "Run backtest", wait ~20s] Now the **Backtest** tab. I'll set it from the start of 2023 to the end of 2024 and click **Run backtest**... It downloads the history and replays it using the **exact same strategy and risk code** as live trading. [when results appear, point at the metric cards] Here are the results: over that window the trend strategy returned about **70%, with a max drawdown around 15% and a Sharpe of roughly 1.4**. One thing to stress: to avoid look-ahead, signals are **shifted one bar** before they execute; but fills are at the close with no commissions or slippage, which is the optimistic part — we'll come back to that.

---

## 10:30–12:00 · Reflection & Wrap-up (A / all)

[Screen: the Limitations section of the README, or a summary slide]

Let me close with limitations and improvements.

**Limitations:**
- The backtest is idealized — fills at the close, with **no commissions or slippage** — so real fills will differ.
- We use the free IEX feed, which only covers part of total volume, so prices differ slightly from the full market.
- Position sizing is simple — a fixed fraction of equity — with no volatility-based adjustment.
- The UI drives the engine one step per refresh, which is great for a demo but isn't a 24/7 always-on process.

**If we kept going, we'd:**
- add **volatility-scaled sizing** and portfolio-level risk parity;
- model **transaction costs and slippage** in the backtester;
- use a **websocket live data stream** instead of polling;
- do walk-forward parameter validation, and add more strategies like factor or machine-learning models.

**And what we learned.** We assumed the strategy would be the hard part. What we actually found is that getting a trading system to **run reliably** is where the real work is: handling market open and close, all the order states, exchange rejections, managing secrets safely, and sharing one codebase between backtest and live. That engineering side is the biggest difference between a real trading system and a classroom exercise. Our code, README, and this video are all on GitHub. Thanks for watching!

---

### Recording tips
- After clicking a button, **pause before speaking** — let the result appear so viewers see cause and effect.
- After **Start**, let it auto-run for 15–20 seconds; it's the most convincing shot.
- The backtest download can take 10–30 seconds; do a warm-up run beforehand.
- Keep repeating that it's **paper trading — no real money**.

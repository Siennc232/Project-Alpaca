"""SQLite persistence for bars, quotes, signals, orders and event logs.

A single database file (config: data.db_path) keeps a structured record of
everything the system does, which the UI reads back for monitoring.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

_SCHEMA = {
    "bars": """
        CREATE TABLE IF NOT EXISTS bars (
            symbol TEXT, ts TEXT, open REAL, high REAL, low REAL,
            close REAL, volume REAL,
            PRIMARY KEY (symbol, ts)
        )""",
    "quotes": """
        CREATE TABLE IF NOT EXISTS quotes (
            ts TEXT, symbol TEXT, price REAL
        )""",
    "signals": """
        CREATE TABLE IF NOT EXISTS signals (
            ts TEXT, symbol TEXT, signal INTEGER, strategy TEXT, price REAL
        )""",
    "orders": """
        CREATE TABLE IF NOT EXISTS orders (
            ts TEXT, order_id TEXT, symbol TEXT, side TEXT, qty REAL,
            order_type TEXT, status TEXT, price REAL
        )""",
    "events": """
        CREATE TABLE IF NOT EXISTS events (
            ts TEXT, level TEXT, message TEXT
        )""",
    "equity": """
        CREATE TABLE IF NOT EXISTS equity (
            ts TEXT, equity REAL, cash REAL
        )""",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Storage:
    def __init__(self, db_path: str):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False so Streamlit's threads can share the handle.
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self._init_schema()

    def _init_schema(self) -> None:
        cur = self.conn.cursor()
        for ddl in _SCHEMA.values():
            cur.execute(ddl)
        self.conn.commit()

    # ------------------------------------------------------------------- writes
    def save_bars(self, symbol: str, df: pd.DataFrame) -> None:
        rows = [
            (symbol, str(idx), r.get("open"), r.get("high"), r.get("low"),
             r.get("close"), r.get("volume"))
            for idx, r in df.iterrows()
        ]
        self.conn.executemany(
            "INSERT OR REPLACE INTO bars VALUES (?,?,?,?,?,?,?)", rows
        )
        self.conn.commit()

    def save_quote(self, symbol: str, price: float) -> None:
        self.conn.execute(
            "INSERT INTO quotes VALUES (?,?,?)", (_now(), symbol, price)
        )
        self.conn.commit()

    def save_signal(self, symbol: str, signal: int, strategy: str, price: float) -> None:
        self.conn.execute(
            "INSERT INTO signals VALUES (?,?,?,?,?)",
            (_now(), symbol, int(signal), strategy, price),
        )
        self.conn.commit()

    def save_order(
        self, order_id: str, symbol: str, side: str, qty: float,
        order_type: str, status: str, price: Optional[float] = None,
    ) -> None:
        self.conn.execute(
            "INSERT INTO orders VALUES (?,?,?,?,?,?,?,?)",
            (_now(), order_id, symbol, side, qty, order_type, status, price),
        )
        self.conn.commit()

    def save_equity(self, equity: float, cash: float) -> None:
        self.conn.execute(
            "INSERT INTO equity VALUES (?,?,?)", (_now(), equity, cash)
        )
        self.conn.commit()

    def log_event(self, level: str, message: str) -> None:
        self.conn.execute(
            "INSERT INTO events VALUES (?,?,?)", (_now(), level, message)
        )
        self.conn.commit()

    # -------------------------------------------------------------------- reads
    def _read(self, table: str, limit: int, order: str = "ts DESC") -> pd.DataFrame:
        try:
            return pd.read_sql_query(
                f"SELECT * FROM {table} ORDER BY {order} LIMIT {limit}", self.conn
            )
        except Exception:
            return pd.DataFrame()

    def recent_signals(self, limit: int = 50) -> pd.DataFrame:
        return self._read("signals", limit)

    def recent_orders(self, limit: int = 50) -> pd.DataFrame:
        return self._read("orders", limit)

    def recent_events(self, limit: int = 100) -> pd.DataFrame:
        return self._read("events", limit)

    def equity_curve(self, limit: int = 1000) -> pd.DataFrame:
        df = self._read("equity", limit, order="ts ASC")
        return df

    def close(self) -> None:
        self.conn.close()

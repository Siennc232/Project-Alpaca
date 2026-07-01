"""Configuration + credential loading.

Loads `config/config.yaml` for parameters and `.env` for secrets, then merges
the Alpaca credentials into the returned config dict. Uses a tiny built-in
`.env` parser so no third-party dependency (python-dotenv) is required.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

import yaml

# Repository root = parent of the `config/` directory.
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV = ROOT / ".env"
DEFAULT_CONFIG = ROOT / "config" / "config.yaml"


def load_env(env_path: Path | None = None) -> None:
    """Load KEY=VALUE pairs from a .env file into os.environ (if present)."""
    env_path = env_path or DEFAULT_ENV
    if not env_path.exists():
        return
    for raw in env_path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        val = val.strip().strip('"').strip("'")
        # Do not overwrite variables already set in the real environment.
        os.environ.setdefault(key.strip(), val)


def load_config(path: Path | None = None) -> Dict[str, Any]:
    """Return the merged configuration dict (yaml params + env credentials)."""
    load_env()
    path = path or DEFAULT_CONFIG
    with open(path, "r") as fh:
        cfg: Dict[str, Any] = yaml.safe_load(fh)

    cfg.setdefault("alpaca", {})
    cfg["alpaca"]["api_key"] = os.environ.get("ALPACA_API_KEY", "")
    cfg["alpaca"]["secret_key"] = os.environ.get("ALPACA_SECRET_KEY", "")
    cfg["alpaca"]["base_url"] = os.environ.get(
        "ALPACA_BASE_URL", "https://paper-api.alpaca.markets"
    )
    # Resolve db_path relative to the repo root for consistent behaviour.
    db_path = cfg.get("data", {}).get("db_path", "logs/market_data.db")
    if not os.path.isabs(db_path):
        cfg["data"]["db_path"] = str(ROOT / db_path)
    return cfg


def has_credentials(cfg: Dict[str, Any]) -> bool:
    """True if both API key and secret are present."""
    a = cfg.get("alpaca", {})
    return bool(a.get("api_key")) and bool(a.get("secret_key"))

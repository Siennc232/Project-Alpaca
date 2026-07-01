"""Central logging setup: logs to both console and logs/system.log."""
from __future__ import annotations

import logging
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / "logs"


def setup_logger(name: str = "trading", level: int = logging.INFO) -> logging.Logger:
    """Return a configured logger that writes to console and logs/system.log."""
    LOG_DIR.mkdir(exist_ok=True)
    logger = logging.getLogger(name)
    if logger.handlers:  # already configured
        return logger
    logger.setLevel(level)

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    logger.addHandler(console)

    file_handler = logging.FileHandler(LOG_DIR / "system.log")
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    logger.propagate = False
    return logger

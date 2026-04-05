from __future__ import annotations

import logging
import sys
import traceback
from datetime import datetime
from pathlib import Path

from opencode_telegram_bot.core.config import DEFAULT_CONFIG_DIR

LOG_DIR = DEFAULT_CONFIG_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / f"tp-opencode-{datetime.now().strftime('%Y-%m-%d')}.log"


def setup_logging(level: str = "DEBUG") -> logging.Logger:
    root = logging.getLogger("tp-opencode")
    root.setLevel(getattr(logging, level.upper(), logging.DEBUG))

    if root.handlers:
        return root

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s (%(filename)s:%(lineno)d): %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    root.addHandler(fh)

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    root.addHandler(ch)

    return root


def log_exception(exc: Exception, context: str = "") -> None:
    root = logging.getLogger("tp-opencode")
    tb = traceback.format_exc()
    root.error("=== EXCEPTION ===")
    if context:
        root.error("Context: %s", context)
    root.error("Type: %s", type(exc).__name__)
    root.error("Message: %s", str(exc))
    root.error("Traceback:\n%s", tb)
    root.error("=== END EXCEPTION ===")


def get_log_contents(max_lines: int = 500) -> str:
    if not LOG_FILE.exists():
        return "No log file found."
    lines = LOG_FILE.read_text(encoding="utf-8").splitlines()
    return "\n".join(lines[-max_lines:])

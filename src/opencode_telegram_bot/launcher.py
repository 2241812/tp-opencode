from __future__ import annotations

import logging
import shutil
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from opencode_telegram_bot.api import OpenCodeServer
from opencode_telegram_bot.core.config import DEFAULT_CONFIG_DIR

logger = logging.getLogger("tp-opencode-launcher")


def _find_opencode() -> str:
    if cmd := shutil.which("opencode"):
        return cmd
    candidates = [
        Path.home() / ".local" / "bin" / "opencode",
        Path.home() / ".config" / "opencode" / "bin" / "opencode",
        Path.home() / "AppData" / "Local" / "Programs" / "opencode" / "opencode.exe",
        Path.home() / "scoop" / "apps" / "opencode" / "current" / "opencode.exe",
        Path("C:/Program Files/opencode/opencode.exe"),
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    return "opencode"


def launch() -> None:
    env_file = DEFAULT_CONFIG_DIR / ".env"
    if env_file.exists():
        load_dotenv(env_file, override=True)

    from opencode_telegram_bot.core.config import Settings

    settings = Settings()
    opencode_cmd = settings.opencode_command or _find_opencode()

    server = OpenCodeServer(
        command=opencode_cmd,
        work_dir=settings.opencode_work_dir or None,
    )

    if settings.opencode_auto_start and not server.is_running:
        try:
            logger.info("Starting OpenCode server...")
            server.start()
            time.sleep(3)
            logger.info("OpenCode server started.")
        except FileNotFoundError:
            logger.warning("opencode command not found. GUI will still open.")

    from opencode_telegram_bot.gui import main as gui_main
    gui_main()


if __name__ == "__main__":
    launch()

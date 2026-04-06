from __future__ import annotations

import shutil
import sys
import time
import traceback
from pathlib import Path

from dotenv import load_dotenv

from opencode_telegram_bot.api import OpenCodeServer
from opencode_telegram_bot.core.config import DEFAULT_CONFIG_DIR
from opencode_telegram_bot.utils.logger import (
    log_exception,
    setup_logging,
)


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
    logger = setup_logging()
    logger.info("=" * 60)
    logger.info("tp-opencode starting")
    logger.info("Python: %s", sys.version)
    logger.info("Platform: %s", sys.platform)
    logger.info("Config dir: %s", DEFAULT_CONFIG_DIR)

    env_file = DEFAULT_CONFIG_DIR / ".env"
    if env_file.exists():
        load_dotenv(env_file, override=True)
        logger.info("Loaded config from %s", env_file)
    else:
        logger.warning("No .env file found at %s", env_file)

    try:
        from opencode_telegram_bot.core.config import Settings

        settings = Settings()
        logger.info("Settings loaded. API URL: %s", settings.opencode_api_url)
        logger.info("Auto-start: %s", settings.opencode_auto_start)

        opencode_cmd = settings.opencode_command or _find_opencode()
        logger.info("OpenCode command: %s", opencode_cmd)

        server = OpenCodeServer(
            command=opencode_cmd,
            work_dir=settings.opencode_work_dir or None,
        )

        if settings.opencode_auto_start and not server.is_running:
            try:
                logger.info("Starting OpenCode server...")
                server.start()
                time.sleep(3)
                logger.info("OpenCode server started (PID: %s)", server.get_pid())
            except FileNotFoundError:
                logger.warning("opencode command not found at '%s'. GUI will still open.", opencode_cmd)
            except Exception as e:
                log_exception(e, "Starting OpenCode server")
                logger.warning("Failed to start OpenCode server. GUI will still open.")

        logger.info("Launching GUI...")
        from opencode_telegram_bot.gui import main as gui_main
        gui_main()

    except Exception as e:
        log_exception(e, "Launcher")
        print(f"\nFatal error: {e}")
        traceback.print_exc()
        input("Press Enter to exit...")
        raise


if __name__ == "__main__":
    launch()

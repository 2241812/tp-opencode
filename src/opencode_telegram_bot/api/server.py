from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


class OpenCodeServer:
    """Manage the OpenCode server process (start/stop/status)."""

    def __init__(
        self,
        command: str = "opencode",
        work_dir: str | None = None,
    ) -> None:
        self.command = command
        self.work_dir = Path(work_dir) if work_dir else Path.cwd()
        self._process: subprocess.Popen | None = None

    @property
    def is_running(self) -> bool:
        if self._process is None:
            return False
        return self._process.poll() is None

    def start(self, port: int = 4096) -> None:
        if self.is_running:
            logger.info("OpenCode server is already running")
            return

        logger.info("Starting OpenCode server on port %d in %s", port, self.work_dir)
        self._process = subprocess.Popen(
            [self.command, "serve", "--port", str(port)],
            cwd=self.work_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
            text=True,
        )
        logger.info("OpenCode server started with PID %d", self._process.pid)

    def stop(self) -> None:
        if not self.is_running:
            logger.info("OpenCode server is not running")
            return

        logger.info("Stopping OpenCode server (PID %d)", self._process.pid)
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/PID", str(self._process.pid)], check=False)
        else:
            self._process.terminate()
            try:
                self._process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._process.kill()
        self._process = None
        logger.info("OpenCode server stopped")

    def get_pid(self) -> int | None:
        return self._process.pid if self._process and self.is_running else None

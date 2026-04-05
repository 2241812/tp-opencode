from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class SessionManager:
    """Manage session state and persistence."""

    def __init__(self, data_dir: Path | None = None) -> None:
        self.data_dir = data_dir or Path.home() / ".config" / "tp-opencode"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._file = self.data_dir / "sessions.json"
        self._sessions: dict[str, dict[str, Any]] = self._load()

    def _load(self) -> dict[str, dict[str, Any]]:
        if self._file.exists():
            try:
                return json.loads(self._file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def _save(self) -> None:
        self._file.write_text(json.dumps(self._sessions, indent=2), encoding="utf-8")

    def add(self, session_id: str, metadata: dict[str, Any]) -> None:
        self._sessions[session_id] = {
            **metadata,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }
        self._save()

    def update(self, session_id: str, metadata: dict[str, Any]) -> None:
        if session_id in self._sessions:
            self._sessions[session_id].update(metadata)
            self._sessions[session_id]["updated_at"] = datetime.utcnow().isoformat()
            self._save()

    def remove(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)
        self._save()

    def get(self, session_id: str) -> dict[str, Any] | None:
        return self._sessions.get(session_id)

    def list_all(self) -> dict[str, dict[str, Any]]:
        return dict(self._sessions)

    def clear(self) -> None:
        self._sessions.clear()
        self._save()

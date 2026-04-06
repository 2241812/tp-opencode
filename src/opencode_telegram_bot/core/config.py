from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_DIR = Path.home() / ".config" / "tp-opencode"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Telegram
    telegram_bot_token: str = ""
    telegram_allowed_user_id: str = ""
    telegram_proxy_url: str = ""

    # OpenCode Server
    opencode_api_url: str = "http://localhost:4096"
    opencode_server_username: str = "opencode"
    opencode_server_password: str = ""

    # Model
    opencode_model_provider: str = "opencode"
    opencode_model_id: str = "big-pickle"

    # Bot
    bot_locale: str = "en"
    sessions_list_limit: int = 10
    projects_list_limit: int = 10
    commands_list_limit: int = 10
    task_limit: int = 10
    bash_tool_display_max_length: int = 128
    service_messages_interval_sec: int = 5
    hide_thinking_messages: bool = False
    hide_tool_call_messages: bool = False
    response_streaming: bool = True
    message_format_mode: str = "markdown"
    code_file_max_size_kb: int = 100

    # Voice (STT)
    stt_api_url: str = ""
    stt_api_key: str = ""
    stt_model: str = "whisper-large-v3-turbo"
    stt_language: str = ""

    # TTS
    tts_api_url: str = ""
    tts_api_key: str = ""
    tts_model: str = "gpt-4o-mini-tts"
    tts_voice: str = "alloy"

    # Web GUI
    web_gui_enabled: bool = True
    web_gui_host: str = "127.0.0.1"
    web_gui_port: int = 8765

    # Logging
    log_level: str = "info"

    # OpenCode Server Management
    opencode_command: str = "opencode"
    opencode_work_dir: str = ""
    opencode_auto_start: bool = False


class BotSettings:
    """Persistent bot-specific settings stored in JSON."""

    def __init__(self, data_dir: Path | None = None) -> None:
        self.data_dir = data_dir or DEFAULT_CONFIG_DIR
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._file = self.data_dir / "settings.json"
        self._data: dict[str, Any] = self._load()

    def _load(self) -> dict[str, Any]:
        if self._file.exists():
            try:
                return json.loads(self._file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def _save(self) -> None:
        self._file.write_text(json.dumps(self._data, indent=2), encoding="utf-8")

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value
        self._save()

    @property
    def tts_enabled(self) -> bool:
        return self._data.get("tts_enabled", False)

    @tts_enabled.setter
    def tts_enabled(self, value: bool) -> None:
        self.set("tts_enabled", value)

    @property
    def current_session_id(self) -> str | None:
        return self._data.get("current_session_id")

    @current_session_id.setter
    def current_session_id(self, value: str | None) -> None:
        self.set("current_session_id", value)

    @property
    def current_project_id(self) -> str | None:
        return self._data.get("current_project_id")

    @current_project_id.setter
    def current_project_id(self, value: str | None) -> None:
        self.set("current_project_id", value)

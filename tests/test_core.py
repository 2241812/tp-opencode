import json
import tempfile
from pathlib import Path

from opencode_telegram_bot.core.config import BotSettings
from opencode_telegram_bot.core.session import SessionManager


def test_bot_settings_tts():
    with tempfile.TemporaryDirectory() as tmpdir:
        settings = BotSettings(data_dir=Path(tmpdir))
        assert settings.tts_enabled is False
        settings.tts_enabled = True
        assert settings.tts_enabled is True

        settings2 = BotSettings(data_dir=Path(tmpdir))
        assert settings2.tts_enabled is True


def test_bot_settings_session_id():
    with tempfile.TemporaryDirectory() as tmpdir:
        settings = BotSettings(data_dir=Path(tmpdir))
        settings.current_session_id = "sess_123"
        assert settings.current_session_id == "sess_123"


def test_session_manager():
    with tempfile.TemporaryDirectory() as tmpdir:
        sm = SessionManager(data_dir=Path(tmpdir))
        sm.add("sess_1", {"title": "Test Session"})
        assert sm.get("sess_1") is not None
        assert sm.get("sess_1")["title"] == "Test Session"


def test_session_manager_update():
    with tempfile.TemporaryDirectory() as tmpdir:
        sm = SessionManager(data_dir=Path(tmpdir))
        sm.add("sess_1", {"title": "Old"})
        sm.update("sess_1", {"title": "New"})
        assert sm.get("sess_1")["title"] == "New"


def test_session_manager_remove():
    with tempfile.TemporaryDirectory() as tmpdir:
        sm = SessionManager(data_dir=Path(tmpdir))
        sm.add("sess_1", {"title": "Test"})
        sm.remove("sess_1")
        assert sm.get("sess_1") is None


def test_session_persistence():
    with tempfile.TemporaryDirectory() as tmpdir:
        sm = SessionManager(data_dir=Path(tmpdir))
        sm.add("sess_1", {"title": "Persisted"})

        sm2 = SessionManager(data_dir=Path(tmpdir))
        assert sm2.get("sess_1")["title"] == "Persisted"

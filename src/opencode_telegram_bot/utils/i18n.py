from __future__ import annotations

import contextlib
import json
from pathlib import Path
from typing import Any

_DEFAULTS: dict[str, dict[str, str]] = {}

_loaded: dict[str, dict[str, str]] = {}


def _load_locale(code: str) -> dict[str, str]:
    if code in _loaded:
        return _loaded[code]

    locale_file = Path(__file__).parent.parent / "locales" / code / "messages.json"
    if locale_file.exists():
        try:
            data = json.loads(locale_file.read_text(encoding="utf-8"))
            _loaded[code] = data
            return data
        except (json.JSONDecodeError, OSError):
            pass

    default_file = Path(__file__).parent.parent / "locales" / "en" / "messages.json"
    if default_file.exists():
        try:
            data = json.loads(default_file.read_text(encoding="utf-8"))
            _loaded[code] = data
            return data
        except (json.JSONDecodeError, OSError):
            pass

    _loaded[code] = {}
    return _loaded[code]


def t(key: str, locale: str = "en", **kwargs: Any) -> str:
    strings = _load_locale(locale)
    text = strings.get(key, key)
    if kwargs:
        with contextlib.suppress(KeyError, ValueError):
            text = text.format(**kwargs)
    return text


def get_available_locales() -> list[str]:
    locales_dir = Path(__file__).parent.parent / "locales"
    if not locales_dir.exists():
        return ["en"]
    return [
        d.name for d in locales_dir.iterdir()
        if d.is_dir() and (d / "messages.json").exists()
    ]

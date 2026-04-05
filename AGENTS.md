# AGENTS.md

This is an OpenCode Telegram Bot project — a Python-based Telegram client for [OpenCode](https://github.com/anomalyco/opencode) CLI.

## Architecture

- **src/opencode_telegram_bot/api/** — OpenCode HTTP API client and server process manager
- **src/opencode_telegram_bot/bot/** — Telegram bot command handlers and message routing
- **src/opencode_telegram_bot/core/** — Configuration, settings, and session state management
- **src/opencode_telegram_bot/utils/** — i18n, voice transcription (STT/TTS), task scheduler
- **src/opencode_telegram_bot/web/** — Flask-based monitoring web GUI
- **src/opencode_telegram_bot/locales/** — Translation files for multiple languages

## Key Dependencies

- `python-telegram-bot` — Telegram Bot API
- `httpx` — Async HTTP client for OpenCode API
- `pydantic-settings` — Environment-based configuration
- `apscheduler` — Scheduled task management
- `flask` — Web monitoring GUI
- `openai` — Whisper-compatible STT/TTS client

## Commands

```bash
# Start the bot
opencode-telegram

# Run configuration wizard
opencode-telegram config

# Development
pip install -e ".[dev]"
ruff check src/
mypy src/
pytest tests/ -v

# Docker
docker compose up -d
```

## OpenCode API Integration

The bot communicates with OpenCode's HTTP API at `http://localhost:4096` by default. Key endpoints:
- `GET /health` — Server health check
- `GET/POST /api/projects` — Project management
- `GET/POST /api/sessions` — Session CRUD
- `GET/POST /api/models` — Model management
- `POST /api/sessions/{id}/message` — Send prompts
- `GET /api/sessions/{id}/events` — SSE event stream for live responses

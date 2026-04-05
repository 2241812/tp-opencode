# OpenCode Telegram Bot

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![OpenCode](https://img.shields.io/badge/OpenCode-Compatible-brightgreen)](https://opencode.ai)

**OpenCode mobile client via Telegram** — run and monitor AI coding tasks from your phone while everything runs locally on your machine. A lightweight [OpenClaw](https://github.com/openclaw/openclaw) alternative built for [OpenCode](https://github.com/anomalyco/opencode).

[![OpenCode Telegram Bot](assets/banner.png)](https://opencode.ai)

## Features

- **Remote coding** — send prompts to OpenCode from anywhere, receive complete results with code sent as files
- **Session management** — create, switch, rename, compact, and abort sessions from Telegram
- **Live status** — pinned message with current project, model, context usage, updated in real time
- **Model switching** — pick models directly in the chat via inline keyboard
- **Agent modes** — switch between Plan and Build modes on the fly with `/mode`
- **Interactive Q&A** — answer agent questions and approve permissions via inline buttons
- **Voice prompts** — send voice messages, transcribe them via Whisper-compatible API
- **File attachments** — send images, documents, and text-based files to OpenCode
- **Scheduled tasks** — schedule prompts to run later or on a recurring interval
- **Server control** — start/stop the OpenCode server remotely via `/opencode_start` and `/opencode_stop`
- **Web GUI** — built-in monitoring dashboard at `http://localhost:8765`
- **Security** — strict user ID whitelist; no external attack surface
- **Localization** — English, Deutsch, Español, Français, Русский, 简体中文
- **Docker support** — one-command deployment with docker-compose

## Architecture

```
Telegram (your phone)
        │
        ▼
┌───────────────────────────────┐
│   OpenCode Telegram Bot       │
│   (Python · python-telegram)  │
│                               │
│  ┌─ Bot Handler               │
│  ├─ OpenCode API Client       │
│  ├─ Session Manager           │
│  ├─ Task Scheduler            │
│  ├─ Voice Transcriber (STT)   │
│  ├─ Text-to-Speech (TTS)      │
│  └─ Web GUI (Flask)           │
└──────────┬────────────────────┘
           │ HTTP / SSE
           ▼
┌───────────────────────────────┐
│   OpenCode Server             │
│   (localhost:4096)            │
│   opencode serve              │
└───────────────────────────────┘
```

## Quick Start

### 1. Create a Telegram Bot

1. Open [@BotFather](https://t.me/BotFather) in Telegram and send `/newbot`
2. Follow the prompts to choose a name and username
3. Copy the **bot token** you receive

Get your **Telegram User ID** by messaging [@userinfobot](https://t.me/userinfobot).

### 2. Install OpenCode

```bash
# Install OpenCode CLI
curl -fsSL https://opencode.ai/install | bash

# Start the server in your project directory
cd /path/to/project
opencode serve
```

### 3. Install & Run the Bot

#### Option A: pip install (recommended)

```bash
pip install opencode-telegram-bot
opencode-telegram config    # Interactive setup wizard
opencode-telegram start     # Launch the bot
```

#### Option B: From source

```bash
git clone https://github.com/2241812/opencode-telegram-bot.git
cd opencode-telegram-bot
pip install -r requirements.txt
opencode-telegram config    # Interactive setup wizard
opencode-telegram start     # Launch the bot
```

#### Option C: Docker

```bash
git clone https://github.com/2241812/opencode-telegram-bot.git
cd opencode-telegram-bot
cp .env.example .env
# Edit .env with your bot token and user ID
docker compose up -d
```

## Bot Commands

| Command | Description |
|---------|-------------|
| `/status` | Server health, current project, session, and model info |
| `/new` | Create a new session |
| `/abort` | Abort the current task |
| `/sessions` | Browse and switch between recent sessions |
| `/projects` | Switch between OpenCode projects |
| `/mode` | Toggle between Plan and Build agent modes |
| `/models` | Pick a model from available options |
| `/compact` | Compact session context |
| `/rename <title>` | Rename the current session |
| `/commands` | Browse and run custom commands |
| `/task <min> <prompt>` | Create a scheduled task |
| `/tasklist` | Browse and delete scheduled tasks |
| `/tts` | Toggle text-to-speech audio replies |
| `/opencode_start` | Start the OpenCode server remotely |
| `/opencode_stop` | Stop the OpenCode server remotely |
| `/help` | Show available commands |

Any regular text message is sent as a prompt to the coding agent.

## Configuration

### Environment Variables

| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| `TELEGRAM_BOT_TOKEN` | Bot token from @BotFather | Yes | — |
| `TELEGRAM_ALLOWED_USER_ID` | Your numeric Telegram user ID | Yes | — |
| `TELEGRAM_PROXY_URL` | Proxy URL for Telegram API (SOCKS5/HTTP) | No | — |
| `OPENCODE_API_URL` | OpenCode server URL | No | `http://localhost:4096` |
| `OPENCODE_SERVER_USERNAME` | Server auth username | No | `opencode` |
| `OPENCODE_SERVER_PASSWORD` | Server auth password | No | — |
| `OPENCODE_MODEL_PROVIDER` | Default model provider | No | `opencode` |
| `OPENCODE_MODEL_ID` | Default model ID | No | `big-pickle` |
| `BOT_LOCALE` | Bot UI language (`en`, `de`, `es`, `fr`, `ru`, `zh`) | No | `en` |
| `RESPONSE_STREAMING` | Stream assistant replies | No | `true` |
| `MESSAGE_FORMAT_MODE` | Reply formatting: `markdown` or `raw` | No | `markdown` |
| `STT_API_URL` | Whisper-compatible API base URL (enables voice) | No | — |
| `STT_API_KEY` | API key for STT provider | No | — |
| `TTS_API_URL` | TTS API base URL | No | — |
| `TTS_API_KEY` | TTS API key | No | — |
| `WEB_GUI_ENABLED` | Enable monitoring web GUI | No | `true` |
| `WEB_GUI_PORT` | Web GUI port | No | `8765` |
| `OPENCODE_AUTO_START` | Auto-start OpenCode server with bot | No | `false` |
| `LOG_LEVEL` | Log level (`debug`, `info`, `warn`, `error`) | No | `info` |

### Voice Transcription

Set `STT_API_URL` and `STT_API_KEY` to enable voice message transcription:

```bash
# OpenAI Whisper
STT_API_URL=https://api.openai.com/v1
STT_API_KEY=your-key
STT_MODEL=whisper-1

# Groq
STT_API_URL=https://api.groq.com/openai/v1
STT_API_KEY=your-key
STT_MODEL=whisper-large-v3-turbo
```

### Text-to-Speech

Set `TTS_API_URL` and `TTS_API_KEY` to enable spoken replies:

```bash
TTS_API_URL=https://api.openai.com/v1
TTS_API_KEY=your-key
TTS_MODEL=gpt-4o-mini-tts
TTS_VOICE=alloy
```

Toggle with `/tts` in the bot chat.

## Web GUI

The built-in monitoring dashboard is available at `http://localhost:8765` (configurable via `WEB_GUI_PORT`). It shows:

- OpenCode server status
- Current model and session info
- Active sessions list
- Scheduled tasks overview
- JSON API at `/api/status`

## Security

The bot enforces a **strict user ID whitelist**. Only the Telegram user whose numeric ID matches `TELEGRAM_ALLOWED_USER_ID` can interact with the bot. Messages from any other user are silently ignored.

Since the bot runs locally on your machine and connects to your local OpenCode server, there is no external attack surface beyond the Telegram Bot API itself.

## Comparison with Alternatives

| Feature | This Bot | [grinev/opencode-telegram-bot](https://github.com/grinev/opencode-telegram-bot) | [OpenClaw](https://github.com/openclaw/openclaw) |
|---------|----------|----------|----------|
| Language | **Python** | TypeScript | TypeScript |
| Setup | `pip install` + wizard | `npx` + wizard | Complex npm setup |
| Telegram | ✅ | ✅ | ✅ (one of 20+ channels) |
| Web GUI | ✅ (built-in) | ❌ | ✅ |
| Voice STT/TTS | ✅ | ✅ | ✅ |
| Scheduled Tasks | ✅ | ✅ | ✅ (cron) |
| Server Control | ✅ | ✅ | ❌ |
| Docker | ✅ | ❌ | ✅ |
| Scope | Telegram-only, focused | Telegram-only, focused | Full platform, 20+ channels |

## Development

```bash
git clone https://github.com/2241812/opencode-telegram-bot.git
cd opencode-telegram-bot
pip install -e ".[dev]"

# Run with auto-reload
python -m opencode_telegram_bot.main

# Lint
ruff check src/

# Type check
mypy src/

# Tests
pytest tests/ -v
```

## Project Structure

```
opencode-telegram-bot/
├── src/opencode_telegram_bot/
│   ├── api/
│   │   ├── client.py          # OpenCode HTTP API client
│   │   └── server.py          # OpenCode server process manager
│   ├── bot/
│   │   └── handler.py         # Telegram bot command handlers
│   ├── core/
│   │   ├── config.py          # Settings and configuration
│   │   └── session.py         # Session state management
│   ├── utils/
│   │   ├── i18n.py            # Localization system
│   │   ├── voice.py           # STT/TTS voice processing
│   │   └── scheduler.py       # Scheduled task manager
│   ├── web/
│   │   └── gui.py             # Flask monitoring dashboard
│   ├── locales/               # Translation files (en, ru, zh, de, es, fr)
│   └── main.py                # Entry point and CLI
├── tests/
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── pyproject.toml
└── README.md
```

## Related Projects

- [OpenCode](https://github.com/anomalyco/opencode) — The open source AI coding agent
- [OpenCode Docs](https://opencode.ai/docs) — Official OpenCode documentation
- [OpenClaw](https://github.com/openclaw/openclaw) — Personal AI assistant (multi-channel)
- [LightClaw](https://github.com/OthmaneBlial/lightclaw) — Lightweight Python OpenClaw alternative
- [grinev/opencode-telegram-bot](https://github.com/grinev/opencode-telegram-bot) — TypeScript Telegram bot for OpenCode

## License

[MIT](LICENSE) © 2241812

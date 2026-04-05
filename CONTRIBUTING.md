# Contributing to OpenCode Telegram Bot

Thank you for your interest in contributing! This project is inspired by the work done in [grinev/opencode-telegram-bot](https://github.com/grinev/opencode-telegram-bot) and aims to provide a Python-based alternative for easier setup and customization.

## Development Setup

```bash
git clone https://github.com/2241812/tp-opencode.git
cd tp-opencode
pip install -e ".[dev]"
```

## Code Style

This project uses:
- **ruff** for linting and formatting
- **mypy** for type checking

```bash
ruff check src/ tests/
ruff format src/ tests/
mypy src/
```

## Running Tests

```bash
pytest tests/ -v
pytest tests/ -v --cov=opencode_telegram_bot
```

## Adding a New Locale

1. Create a new directory under `src/opencode_telegram_bot/locales/<code>/`
2. Copy `locales/en/messages.json` as a template
3. Translate all string values
4. The locale will be auto-detected by the setup wizard

## Pull Request Guidelines

- Follow the existing code style (ruff + mypy clean)
- Add tests for new features
- Update documentation if changing user-facing behavior
- Keep commits focused and atomic
- Reference related issues in commit messages

## Commit Convention

Use conventional commits:
- `feat:` new feature
- `fix:` bug fix
- `docs:` documentation changes
- `refactor:` code refactoring
- `test:` adding or updating tests
- `chore:` maintenance tasks

## Related

- [OpenCode](https://github.com/anomalyco/opencode) — The open source AI coding agent
- [OpenCode Telegram Bot (TypeScript)](https://github.com/grinev/opencode-telegram-bot) — Original Telegram bot implementation

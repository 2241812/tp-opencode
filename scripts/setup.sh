#!/usr/bin/env bash
set -euo pipefail

echo "OpenCode Telegram Bot — Setup Script"
echo "======================================"

if ! command -v python3 &>/dev/null; then
    echo "Error: python3 is required but not installed."
    exit 1
fi

PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
REQUIRED="3.10"

if [[ "$(printf '%s\n' "$REQUIRED" "$PYTHON_VERSION" | sort -V | head -n1)" != "$REQUIRED" ]]; then
    echo "Error: Python $REQUIRED or higher is required (found $PYTHON_VERSION)"
    exit 1
fi

echo "Installing dependencies..."
pip install -r requirements.txt

echo ""
echo "Running configuration wizard..."
python -m opencode_telegram_bot.main config

echo ""
echo "Setup complete! Start the bot with:"
echo "  python -m opencode_telegram_bot.main"
echo "  # or: opencode-telegram (if installed with pip install -e .)"

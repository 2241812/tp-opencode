@echo off
echo ========================================
echo  tp-opencode — OpenCode Telegram Bot
echo ========================================
echo.

cd /d "%~dp0"

echo Starting tp-opencode...
python -m opencode_telegram_bot.launcher

pause

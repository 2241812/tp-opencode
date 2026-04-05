from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from prompt_toolkit import prompt
from prompt_toolkit.completion import WordCompleter
from rich.console import Console
from rich.panel import Panel

from opencode_telegram_bot.core.config import Settings, BotSettings, DEFAULT_CONFIG_DIR
from opencode_telegram_bot.core.session import SessionManager
from opencode_telegram_bot.utils.scheduler import TaskScheduler
from opencode_telegram_bot.utils.i18n import get_available_locales

console = Console()


def run_wizard() -> None:
    """Interactive configuration wizard."""
    console.print(Panel("OpenCode Telegram Bot — Setup Wizard", style="bold blue"))

    config_dir = DEFAULT_CONFIG_DIR
    config_dir.mkdir(parents=True, exist_ok=True)
    env_file = config_dir / ".env"

    if env_file.exists():
        console.print(f"[yellow]Existing config found at {env_file}[/yellow]")
        choice = prompt("Overwrite? (y/N): ").strip().lower()
        if choice not in ("y", "yes"):
            console.print("[green]Keeping existing configuration.[/green]")
            return

    locales = get_available_locales()
    console.print("\nAvailable languages:")
    for i, loc in enumerate(locales):
        console.print(f"  {i + 1}. {loc}")
    locale_idx = prompt("Select language [1]: ").strip()
    locale = locales[int(locale_idx) - 1] if locale_idx.isdigit() and 0 < int(locale_idx) <= len(locales) else "en"

    token = prompt("Telegram Bot Token (from @BotFather): ").strip()
    user_id = prompt("Telegram User ID (from @userinfobot): ").strip()
    api_url = prompt("OpenCode API URL [http://localhost:4096]: ").strip() or "http://localhost:4096"
    password = prompt("OpenCode server password (leave empty if none): ", is_password=True).strip()

    lines = [
        f"BOT_LOCALE={locale}",
        f"TELEGRAM_BOT_TOKEN={token}",
        f"TELEGRAM_ALLOWED_USER_ID={user_id}",
        f"OPENCODE_API_URL={api_url}",
    ]
    if password:
        lines.append(f"OPENCODE_SERVER_PASSWORD={password}")

    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    console.print(f"\n[green]Configuration saved to {env_file}[/green]")
    console.print("[bold green]Run 'opencode-telegram start' to launch the bot.[/bold green]")


def setup_logging(level: str = "info") -> None:
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


async def run_bot() -> None:
    """Main bot entry point."""
    env_paths = [
        Path(".env"),
        DEFAULT_CONFIG_DIR / ".env",
        Path.home() / ".env",
    ]
    for p in env_paths:
        if p.exists():
            load_dotenv(p, override=True)
            break

    settings = Settings()
    if not settings.telegram_bot_token:
        console.print("[red]No TELEGRAM_BOT_TOKEN configured.[/red]")
        console.print("Run [bold]opencode-telegram config[/bold] to set up, or create a .env file.")
        sys.exit(1)

    setup_logging(settings.log_level)

    bot_settings = BotSettings()
    session_manager = SessionManager()
    scheduler = TaskScheduler(max_tasks=settings.task_limit)

    from opencode_telegram_bot.bot import BotHandler

    handler = BotHandler(settings, bot_settings, session_manager, scheduler)

    if settings.opencode_auto_start and not handler.server.is_running:
        handler.server.start()
        await asyncio.sleep(3)

    from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters

    app = (
        ApplicationBuilder()
        .token(settings.telegram_bot_token)
        .build()
    )

    if settings.telegram_proxy_url:
        app = (
            ApplicationBuilder()
            .token(settings.telegram_bot_token)
            .proxy_url(settings.telegram_proxy_url)
            .get_updates_proxy_url(settings.telegram_proxy_url)
            .build()
        )

    app.add_handler(CommandHandler("start", handler.cmd_start))
    app.add_handler(CommandHandler("help", handler.cmd_help))
    app.add_handler(CommandHandler("status", handler.cmd_status))
    app.add_handler(CommandHandler("new", handler.cmd_new))
    app.add_handler(CommandHandler("abort", handler.cmd_abort))
    app.add_handler(CommandHandler("sessions", handler.cmd_sessions))
    app.add_handler(CommandHandler("projects", handler.cmd_projects))
    app.add_handler(CommandHandler("tts", handler.cmd_tts))
    app.add_handler(CommandHandler("rename", handler.cmd_rename))
    app.add_handler(CommandHandler("compact", handler.cmd_compact))
    app.add_handler(CommandHandler("mode", handler.cmd_mode))
    app.add_handler(CommandHandler("models", handler.cmd_models))
    app.add_handler(CommandHandler("commands", handler.cmd_commands))
    app.add_handler(CommandHandler("task", handler.cmd_task))
    app.add_handler(CommandHandler("tasklist", handler.cmd_tasklist))
    app.add_handler(CommandHandler("opencode_start", handler.cmd_opencode_start))
    app.add_handler(CommandHandler("opencode_stop", handler.cmd_opencode_stop))
    app.add_handler(CallbackQueryHandler(handler.callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handler.handle_message))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO | filters.Document.ALL, handler.handle_message))

    scheduler.start()

    gui = None
    if settings.web_gui_enabled:
        from opencode_telegram_bot.web import WebGUI
        gui = WebGUI(host=settings.web_gui_host, port=settings.web_gui_port, bot_handler=handler)
        gui.start()

    console.print(Panel(
        f"[bold green]Bot is running![/bold green]\n"
        f"Locale: {settings.bot_locale}\n"
        f"API: {settings.opencode_api_url}\n"
        f"Model: {settings.opencode_model_provider}/{settings.opencode_model_id}\n"
        f"GUI: http://{settings.web_gui_host}:{settings.web_gui_port}" if settings.web_gui_enabled else "",
        title="OpenCode Telegram Bot",
        style="green",
    ))

    try:
        await app.initialize()
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        console.print("[green]Polling started. Send messages to your bot![/green]")

        try:
            while True:
                await asyncio.sleep(1)
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
    finally:
        console.print("\n[yellow]Shutting down...[/yellow]")
        await app.updater.stop()
        await app.stop()
        await app.shutdown()
        await handler.cleanup()
        scheduler.stop()
        if gui:
            gui.stop()


def main() -> None:
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd in ("config", "onboard", "setup"):
            run_wizard()
            return
        if cmd in ("reset", "clear"):
            env_file = DEFAULT_CONFIG_DIR / ".env"
            if env_file.exists():
                env_file.unlink()
                console.print("[green]Configuration reset.[/green]")
            else:
                console.print("[yellow]No configuration found.[/yellow]")
            return
    asyncio.run(run_bot())


if __name__ == "__main__":
    main()

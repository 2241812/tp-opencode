from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import sys
import threading
from pathlib import Path
from typing import Any, Callable

import customtkinter as ctk

from opencode_telegram_bot.api import OpenCodeClient, OpenCodeServer
from opencode_telegram_bot.core import BotSettings, SessionManager
from opencode_telegram_bot.core.config import Settings, DEFAULT_CONFIG_DIR
from opencode_telegram_bot.utils.scheduler import TaskScheduler
from opencode_telegram_bot.utils.i18n import get_available_locales

logger = logging.getLogger(__name__)

COLORS = {
    "bg": "#FFFFFF",
    "bg_secondary": "#F5F5F7",
    "card": "#FFFFFF",
    "border": "#E5E5E7",
    "text_primary": "#1D1D1F",
    "text_secondary": "#86868B",
    "accent": "#0071E3",
    "accent_hover": "#0077ED",
    "success": "#34C759",
    "warning": "#FF9F0A",
    "error": "#FF3B30",
    "button_secondary": "#F5F5F7",
    "button_secondary_border": "#D2D2D7",
}


class LogHandler(logging.Handler):
    def __init__(self, callback: Callable[[str], None]) -> None:
        super().__init__()
        self.callback = callback
        self.setLevel(logging.DEBUG)

    def emit(self, record: logging.LogRecord) -> None:
        msg = self.format(record)
        self.callback(msg)


def _find_opencode() -> str:
    if cmd := shutil.which("opencode"):
        return cmd
    candidates = [
        Path.home() / ".local" / "bin" / "opencode",
        Path.home() / ".config" / "opencode" / "bin" / "opencode",
        Path.home() / "AppData" / "Local" / "Programs" / "opencode" / "opencode.exe",
        Path.home() / "scoop" / "apps" / "opencode" / "current" / "opencode.exe",
        Path("C:/Program Files/opencode/opencode.exe"),
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    return "opencode"


def _load_env_file(path: Path) -> dict[str, str]:
    result = {}
    if not path.exists():
        return result
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            result[key.strip()] = value.strip()
    return result


class _CTkEntry(ctk.CTkEntry):
    def __init__(self, *args, **kwargs) -> None:
        kwargs.setdefault("height", 44)
        kwargs.setdefault("corner_radius", 12)
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("border_color", COLORS["border"])
        kwargs.setdefault("fg_color", COLORS["bg_secondary"])
        kwargs.setdefault("text_color", COLORS["text_primary"])
        kwargs.setdefault("placeholder_text_color", COLORS["text_secondary"])
        super().__init__(*args, **kwargs)


class _CTkButton(ctk.CTkButton):
    def __init__(self, *args, **kwargs) -> None:
        kwargs.setdefault("height", 44)
        kwargs.setdefault("corner_radius", 12)
        kwargs.setdefault("border_width", 0)
        kwargs.setdefault("fg_color", COLORS["accent"])
        kwargs.setdefault("hover_color", COLORS["accent_hover"])
        kwargs.setdefault("text_color", "#FFFFFF")
        kwargs.setdefault("font", ctk.CTkFont(size=15, weight="bold"))
        super().__init__(*args, **kwargs)


class _CTkButtonSecondary(ctk.CTkButton):
    def __init__(self, *args, **kwargs) -> None:
        kwargs.setdefault("height", 44)
        kwargs.setdefault("corner_radius", 12)
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("border_color", COLORS["button_secondary_border"])
        kwargs.setdefault("fg_color", COLORS["button_secondary"])
        kwargs.setdefault("hover_color", COLORS["border"])
        kwargs.setdefault("text_color", COLORS["text_primary"])
        kwargs.setdefault("font", ctk.CTkFont(size=15, weight="bold"))
        super().__init__(*args, **kwargs)


class _CTkLabel(ctk.CTkLabel):
    def __init__(self, *args, **kwargs) -> None:
        kwargs.setdefault("text_color", COLORS["text_primary"])
        kwargs.setdefault("font", ctk.CTkFont(size=14))
        super().__init__(*args, **kwargs)


class _CTkLabelTitle(ctk.CTkLabel):
    def __init__(self, *args, **kwargs) -> None:
        kwargs.setdefault("text_color", COLORS["text_primary"])
        kwargs.setdefault("font", ctk.CTkFont(size=28, weight="bold"))
        super().__init__(*args, **kwargs)


class _CTkLabelSubtitle(ctk.CTkLabel):
    def __init__(self, *args, **kwargs) -> None:
        kwargs.setdefault("text_color", COLORS["text_secondary"])
        kwargs.setdefault("font", ctk.CTkFont(size=15))
        super().__init__(*args, **kwargs)


class _CTkLabelSmall(ctk.CTkLabel):
    def __init__(self, *args, **kwargs) -> None:
        kwargs.setdefault("text_color", COLORS["text_secondary"])
        kwargs.setdefault("font", ctk.CTkFont(size=12))
        super().__init__(*args, **kwargs)


class _CTkCheckBox(ctk.CTkCheckBox):
    def __init__(self, *args, **kwargs) -> None:
        kwargs.setdefault("corner_radius", 8)
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("fg_color", COLORS["accent"])
        kwargs.setdefault("border_color", COLORS["border"])
        kwargs.setdefault("text_color", COLORS["text_primary"])
        kwargs.setdefault("font", ctk.CTkFont(size=14))
        super().__init__(*args, **kwargs)


class SetupFrame(ctk.CTkFrame):
    def __init__(self, master: Any, on_done: Callable) -> None:
        super().__init__(master, fg_color=COLORS["bg"])
        self.on_done = on_done
        self._build()

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(4, weight=1)

        header = ctk.CTkFrame(self, fg_color=COLORS["bg"], height=120)
        header.grid(row=0, column=0, sticky="ew", padx=0, pady=0)
        header.grid_columnconfigure(0, weight=1)
        header.grid_propagate(False)

        _CTkLabelTitle(header, text="Setup").grid(row=0, column=0, padx=(40, 40), pady=(30, 2), sticky="w")
        _CTkLabelSubtitle(header, text="Configure your OpenCode Telegram Bot").grid(row=1, column=0, padx=(40, 40), pady=(0, 10), sticky="w")

        content = ctk.CTkScrollableFrame(self, fg_color=COLORS["bg"])
        content.grid(row=1, column=0, sticky="nsew", padx=40, pady=10)
        content.grid_columnconfigure(1, weight=1)

        env_file = DEFAULT_CONFIG_DIR / ".env"
        existing = _load_env_file(env_file)

        fields = [
            ("bot_token", "Telegram Bot Token", existing.get("TELEGRAM_BOT_TOKEN", ""), "From @BotFather"),
            ("user_id", "Telegram User ID", existing.get("TELEGRAM_ALLOWED_USER_ID", ""), "From @userinfobot"),
            ("api_url", "OpenCode API URL", existing.get("OPENCODE_API_URL", "http://localhost:4096"), "Default: http://localhost:4096"),
            ("password", "OpenCode Server Password", existing.get("OPENCODE_SERVER_PASSWORD", ""), "Leave empty if none"),
            ("opencode_cmd", "OpenCode Command", existing.get("OPENCODE_COMMAND", _find_opencode()), "Path to opencode binary"),
        ]

        self.entries: dict[str, ctk.CTkEntry] = {}
        for i, (key, label, default, placeholder) in enumerate(fields):
            row = i * 2
            _CTkLabel(content, text=label, anchor="w", font=ctk.CTkFont(size=14, weight="bold")).grid(row=row, column=0, padx=(0, 12), pady=(8, 2), sticky="w")
            entry = _CTkEntry(content, placeholder_text=placeholder)
            entry.insert(0, default)
            entry.grid(row=row, column=1, padx=(0, 0), pady=(8, 2), sticky="ew")
            self.entries[key] = entry

        row_locale = len(fields) * 2
        _CTkLabel(content, text="Locale", anchor="w", font=ctk.CTkFont(size=14, weight="bold")).grid(row=row_locale, column=0, padx=(0, 12), pady=(16, 2), sticky="w")
        locales = get_available_locales()
        current_locale = existing.get("BOT_LOCALE", "en")
        self.locale_var = ctk.StringVar(value=current_locale if current_locale in locales else "en")
        locale_menu = ctk.CTkOptionMenu(content, values=locales, variable=self.locale_var, height=44, corner_radius=12, fg_color=COLORS["bg_secondary"], button_color=COLORS["border"], button_hover_color=COLORS["accent"], text_color=COLORS["text_primary"], dropdown_fg_color=COLORS["bg"], dropdown_text_color=COLORS["text_primary"], dropdown_hover_color=COLORS["bg_secondary"], dropdown_font=ctk.CTkFont(size=14))
        locale_menu.grid(row=row_locale, column=1, padx=(0, 0), pady=(16, 2), sticky="w")

        row_auto = row_locale + 1
        self.auto_start_var = ctk.BooleanVar(value=existing.get("OPENCODE_AUTO_START", "false").lower() == "true")
        _CTkCheckBox(content, text="Auto-start OpenCode server when bot starts", variable=self.auto_start_var).grid(row=row_auto, column=0, columnspan=2, padx=0, pady=(16, 8), sticky="w")

        footer = ctk.CTkFrame(self, fg_color=COLORS["bg"], height=80)
        footer.grid(row=2, column=0, sticky="ew", padx=0, pady=0)
        footer.grid_columnconfigure(0, weight=1)
        footer.grid_propagate(False)

        _CTkButton(footer, text="Save & Continue", command=self._save).grid(row=0, column=0, padx=(40, 40), pady=16, sticky="e")

    def _save(self) -> None:
        DEFAULT_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        env_file = DEFAULT_CONFIG_DIR / ".env"
        lines = [
            f"TELEGRAM_BOT_TOKEN={self.entries['bot_token'].get().strip()}",
            f"TELEGRAM_ALLOWED_USER_ID={self.entries['user_id'].get().strip()}",
            f"OPENCODE_API_URL={self.entries['api_url'].get().strip() or 'http://localhost:4096'}",
            f"OPENCODE_SERVER_PASSWORD={self.entries['password'].get().strip()}",
            f"OPENCODE_COMMAND={self.entries['opencode_cmd'].get().strip() or _find_opencode()}",
            f"BOT_LOCALE={self.locale_var.get()}",
            f"OPENCODE_AUTO_START={'true' if self.auto_start_var.get() else 'false'}",
            "WEB_GUI_ENABLED=true",
            "WEB_GUI_HOST=127.0.0.1",
            "WEB_GUI_PORT=8765",
            "LOG_LEVEL=info",
            "RESPONSE_STREAMING=true",
            "MESSAGE_FORMAT_MODE=raw",
        ]
        env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        self.on_done()


class DashboardFrame(ctk.CTkFrame):
    def __init__(self, master: Any, settings: Settings) -> None:
        super().__init__(master, fg_color=COLORS["bg"])
        self.settings = settings
        self.bot_settings = BotSettings()
        self.session_manager = SessionManager()
        self.scheduler = TaskScheduler(max_tasks=settings.task_limit)

        self.client = OpenCodeClient(
            base_url=settings.opencode_api_url,
            username=settings.opencode_server_username,
            password=settings.opencode_server_password or None,
        )
        opencode_cmd = settings.opencode_command or _find_opencode()
        self.server = OpenCodeServer(
            command=opencode_cmd,
            work_dir=settings.opencode_work_dir or None,
        )
        self.bot_running = False
        self.bot_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._bot_app = None
        self._bot_handler = None

        self._build()
        self._start_status_poll()

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(3, weight=1)

        header = ctk.CTkFrame(self, fg_color=COLORS["bg"], height=100)
        header.grid(row=0, column=0, columnspan=2, sticky="ew")
        header.grid_columnconfigure(0, weight=1)
        header.grid_propagate(False)

        _CTkLabelTitle(header, text="Dashboard").grid(row=0, column=0, padx=(40, 40), pady=(20, 2), sticky="w")
        _CTkLabelSubtitle(header, text="Manage your OpenCode Telegram Bot").grid(row=1, column=0, padx=(40, 40), pady=(0, 10), sticky="w")

        status_bar = ctk.CTkFrame(self, fg_color=COLORS["bg_secondary"], corner_radius=16, height=56)
        status_bar.grid(row=1, column=0, columnspan=2, padx=40, pady=(0, 16), sticky="ew")
        status_bar.grid_columnconfigure((0, 1, 2), weight=1)
        status_bar.grid_propagate(False)

        self.server_label = _CTkLabelSmall(status_bar, text="Server: Checking...", anchor="w")
        self.server_label.grid(row=0, column=0, padx=(20, 10), pady=16, sticky="w")

        self.bot_label = _CTkLabelSmall(status_bar, text="Bot: Stopped", anchor="w")
        self.bot_label.grid(row=0, column=1, padx=10, pady=16, sticky="w")

        self.model_label = _CTkLabelSmall(status_bar, text=f"Model: {self.settings.opencode_model_id}", anchor="w")
        self.model_label.grid(row=0, column=2, padx=(10, 20), pady=16, sticky="w")

        ctrl_frame = ctk.CTkFrame(self, fg_color=COLORS["bg"], height=60)
        ctrl_frame.grid(row=2, column=0, columnspan=2, padx=40, pady=(0, 16), sticky="ew")
        ctrl_frame.grid_columnconfigure(0, weight=1)
        ctrl_frame.grid_propagate(False)

        btn_frame = ctk.CTkFrame(ctrl_frame, fg_color=COLORS["bg"])
        btn_frame.grid(row=0, column=0, padx=0, pady=8, sticky="w")

        self.start_server_btn = _CTkButtonSecondary(btn_frame, text="Start Server", command=self._toggle_server, width=140)
        self.start_server_btn.pack(side="left", padx=(0, 10))

        self.start_bot_btn = _CTkButton(btn_frame, text="Start Bot", command=self._toggle_bot, width=140)
        self.start_bot_btn.pack(side="left", padx=(0, 10))

        _CTkButtonSecondary(btn_frame, text="Reconfigure", command=self._reconfigure, width=140).pack(side="left")

        content_frame = ctk.CTkFrame(self, fg_color=COLORS["bg"])
        content_frame.grid(row=3, column=0, columnspan=2, padx=40, pady=(0, 20), sticky="nsew")
        content_frame.grid_columnconfigure(0, weight=1)
        content_frame.grid_columnconfigure(1, weight=1)
        content_frame.grid_rowconfigure(0, weight=1)

        left_panel = ctk.CTkFrame(content_frame, fg_color=COLORS["bg"])
        left_panel.grid(row=0, column=0, padx=(0, 10), pady=0, sticky="nsew")
        left_panel.grid_columnconfigure(0, weight=1)
        left_panel.grid_rowconfigure(1, weight=1)
        left_panel.grid_rowconfigure(3, weight=1)

        _CTkLabel(left_panel, text="Sessions", font=ctk.CTkFont(size=18, weight="bold"), anchor="w").grid(row=0, column=0, pady=(0, 8), sticky="w")
        self.sessions_text = ctk.CTkTextbox(left_panel, height=150, corner_radius=12, border_width=1, border_color=COLORS["border"], fg_color=COLORS["bg_secondary"], text_color=COLORS["text_primary"], font=ctk.CTkFont(size=13))
        self.sessions_text.grid(row=1, column=0, sticky="ew", pady=(0, 16))

        _CTkLabel(left_panel, text="Models", font=ctk.CTkFont(size=18, weight="bold"), anchor="w").grid(row=2, column=0, pady=(0, 8), sticky="w")
        self.models_frame = ctk.CTkScrollableFrame(left_panel, fg_color=COLORS["bg_secondary"], corner_radius=12, height=250)
        self.models_frame.grid(row=3, column=0, sticky="nsew")

        self._load_models()

        right_panel = ctk.CTkFrame(content_frame, fg_color=COLORS["bg"])
        right_panel.grid(row=0, column=1, padx=(10, 0), pady=0, sticky="nsew")
        right_panel.grid_columnconfigure(0, weight=1)
        right_panel.grid_rowconfigure(1, weight=1)

        _CTkLabel(right_panel, text="Live Logs", font=ctk.CTkFont(size=18, weight="bold"), anchor="w").grid(row=0, column=0, pady=(0, 8), sticky="w")

        log_container = ctk.CTkFrame(right_panel, fg_color=COLORS["bg_secondary"], corner_radius=12)
        log_container.grid(row=1, column=0, sticky="nsew")
        log_container.grid_columnconfigure(0, weight=1)
        log_container.grid_rowconfigure(0, weight=1)

        self.log_text = ctk.CTkTextbox(log_container, wrap="word", corner_radius=12, border_width=0, fg_color=COLORS["bg_secondary"], text_color=COLORS["text_primary"], font=ctk.CTkFont(size=12, family="SF Mono"))
        self.log_text.grid(row=0, column=0, padx=12, pady=12, sticky="nsew")

        self.log_text.insert("end", "Ready. Start the OpenCode server and bot.\n")

        log_handler = LogHandler(self._log_callback)
        logging.getLogger("opencode_telegram_bot").addHandler(log_handler)
        logging.getLogger("telegram").addHandler(log_handler)

        _CTkButtonSecondary(right_panel, text="Clear Logs", command=self._clear_logs, height=36).grid(row=2, column=0, pady=(8, 0), sticky="e")

    def _log_callback(self, msg: str) -> None:
        self.after(0, lambda: self._append_log(msg))

    def _append_log(self, msg: str) -> None:
        self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")

    def _clear_logs(self) -> None:
        self.log_text.delete("1.0", "end")

    def _start_status_poll(self) -> None:
        self._poll_status()

    def _poll_status(self) -> None:
        self.after(0, self._do_poll)
        self.after(5000, self._poll_status)

    def _do_poll(self) -> None:
        def check():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                health = loop.run_until_complete(self.client.health())
                loop.close()
                status_val = health.get("healthy", health.get("status", "unknown"))
                self.after(0, lambda: self.server_label.configure(text=f"Server: {status_val}", text_color=COLORS["success"]))
            except Exception:
                self.after(0, lambda: self.server_label.configure(text="Server: Offline", text_color=COLORS["error"]))

        threading.Thread(target=check, daemon=True).start()

    def _toggle_server(self) -> None:
        if self.server.is_running:
            self.server.stop()
            self.start_server_btn.configure(text="Start Server", fg_color=COLORS["button_secondary"], text_color=COLORS["text_primary"])
            self._append_log("OpenCode server stopped.")
        else:
            try:
                self.server.start()
                self.start_server_btn.configure(text="Stop Server", fg_color=COLORS["error"], text_color="#FFFFFF", border_color=COLORS["error"])
                self._append_log("OpenCode server started.")
            except FileNotFoundError:
                self._append_log("Error: 'opencode' command not found.")
                self._append_log("Install: curl -fsSL https://opencode.ai/install | bash")

    def _toggle_bot(self) -> None:
        if self.bot_running:
            self._stop_bot()
        else:
            self._start_bot()

    def _start_bot(self) -> None:
        if self.settings.opencode_auto_start and not self.server.is_running:
            self._append_log("Auto-starting OpenCode server...")
            try:
                self.server.start()
            except FileNotFoundError:
                self._append_log("Warning: opencode command not found.")

        self._stop_event.clear()
        self.bot_thread = threading.Thread(target=self._run_bot_loop, daemon=True)
        self.bot_thread.start()
        self.bot_running = True
        self.start_bot_btn.configure(text="Stop Bot", fg_color=COLORS["error"], text_color="#FFFFFF")
        self.bot_label.configure(text="Bot: Starting...", text_color=COLORS["warning"])
        self._append_log("Bot thread started.")

    def _run_bot_loop(self) -> None:
        from dotenv import load_dotenv
        load_dotenv(DEFAULT_CONFIG_DIR / ".env", override=True)

        from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters
        from opencode_telegram_bot.bot.handler import BotHandler

        settings = Settings()
        bot_settings = BotSettings()
        session_manager = SessionManager()
        scheduler = TaskScheduler(max_tasks=settings.task_limit)

        client = OpenCodeClient(
            base_url=settings.opencode_api_url,
            username=settings.opencode_server_username,
            password=settings.opencode_server_password or None,
        )
        server = OpenCodeServer(
            command=settings.opencode_command or _find_opencode(),
            work_dir=settings.opencode_work_dir or None,
        )

        handler = BotHandler(settings, bot_settings, session_manager, scheduler, client=client, server=server)
        self._bot_handler = handler

        if settings.telegram_proxy_url:
            app = (
                ApplicationBuilder()
                .token(settings.telegram_bot_token)
                .proxy_url(settings.telegram_proxy_url)
                .get_updates_proxy_url(settings.telegram_proxy_url)
                .build()
            )
        else:
            app = ApplicationBuilder().token(settings.telegram_bot_token).build()

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
        self._bot_app = app

        async def run():
            try:
                await app.initialize()
                await app.start()
                await app.updater.start_polling(drop_pending_updates=True)
                self.after(0, lambda: self.bot_label.configure(text="Bot: Running", text_color=COLORS["success"]))
                self.after(0, lambda: self._append_log("Bot polling started."))
                while not self._stop_event.is_set():
                    await asyncio.sleep(0.5)
            except Exception as e:
                self.after(0, lambda: self._append_log(f"Bot error: {e}"))
                self.after(0, lambda: self.bot_label.configure(text="Bot: Error", text_color=COLORS["error"]))
            finally:
                try:
                    if app.updater.running:
                        await app.updater.stop()
                    await app.stop()
                    await app.shutdown()
                except Exception:
                    pass
                try:
                    await handler.cleanup()
                except Exception:
                    pass
                scheduler.stop()
                self.after(0, lambda: self.bot_label.configure(text="Bot: Stopped", text_color=COLORS["text_secondary"]))
                self.after(0, lambda: self._append_log("Bot stopped."))
                self.bot_running = False
                self.after(0, lambda: self.start_bot_btn.configure(text="Start Bot", fg_color=COLORS["accent"], text_color="#FFFFFF"))

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(run())
        except Exception as e:
            self.after(0, lambda: self._append_log(f"Bot loop error: {e}"))
            self.after(0, lambda: self.bot_label.configure(text="Bot: Error", text_color=COLORS["error"]))
        finally:
            loop.close()

    def _stop_bot(self) -> None:
        self._stop_event.set()
        self.bot_label.configure(text="Bot: Stopping...", text_color=COLORS["warning"])
        self._append_log("Stopping bot...")

    def _reconfigure(self) -> None:
        if self.bot_running:
            self._stop_bot()
            import time
            time.sleep(1)
        self.master._reload_settings_and_show_setup()

    def _load_models(self) -> None:
        def fetch():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                providers = loop.run_until_complete(self.client.get_config_providers())
                loop.close()
                self.after(0, lambda: self._render_models(providers))
            except Exception as e:
                self.after(0, lambda: self._append_log(f"Failed to load models: {e}"))

        threading.Thread(target=fetch, daemon=True).start()

    def _render_models(self, providers_data: dict[str, Any]) -> None:
        for widget in self.models_frame.winfo_children():
            widget.destroy()

        providers = providers_data.get("providers", [])
        if not isinstance(providers, list):
            providers = []

        for p in providers:
            pid = p.get("id", p.get("name", "unknown"))
            models = p.get("models", [])
            if not isinstance(models, list):
                models = []
            _CTkLabel(self.models_frame, text=pid, font=ctk.CTkFont(weight="bold", size=13), text_color=COLORS["text_primary"]).pack(anchor="w", padx=12, pady=(12, 4))
            for m in models[:8]:
                mid = m.get("id", m.get("name", ""))
                btn = ctk.CTkButton(
                    self.models_frame,
                    text=mid,
                    width=220,
                    height=32,
                    corner_radius=8,
                    fg_color=COLORS["bg"],
                    hover_color=COLORS["bg_secondary"],
                    text_color=COLORS["text_primary"],
                    font=ctk.CTkFont(size=12),
                    border_width=1,
                    border_color=COLORS["border"],
                    command=lambda prov=pid, model=mid: self._switch_model(prov, model),
                )
                btn.pack(anchor="w", padx=12, pady=2)

        if not providers:
            _CTkLabelSubtitle(self.models_frame, text="No models found. Configure providers in OpenCode.").pack(pady=20)

    def _switch_model(self, provider: str, model: str) -> None:
        self.model_label.configure(text=f"Model: {provider}/{model}")
        self._append_log(f"Model selected: {provider}/{model}")


class App(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("tp-opencode")
        self.geometry("1000x680")
        self.minsize(800, 500)
        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")

        self.settings: Settings | None = None
        self._build()

    def _build(self) -> None:
        env_file = DEFAULT_CONFIG_DIR / ".env"
        if env_file.exists():
            self._load_settings()
            self.show_dashboard()
        else:
            self.show_setup()

    def _load_settings(self) -> None:
        from dotenv import load_dotenv
        load_dotenv(DEFAULT_CONFIG_DIR / ".env", override=True)
        self.settings = Settings()

    def _reload_settings_and_show_setup(self) -> None:
        from dotenv import load_dotenv
        load_dotenv(DEFAULT_CONFIG_DIR / ".env", override=True)
        self.settings = Settings()
        self.show_setup()

    def show_setup(self) -> None:
        for w in self.winfo_children():
            w.destroy()
        frame = SetupFrame(self, on_done=self._on_setup_done)
        frame.pack(fill="both", expand=True)

    def _on_setup_done(self) -> None:
        self._load_settings()
        self.show_dashboard()

    def show_dashboard(self) -> None:
        for w in self.winfo_children():
            w.destroy()
        if self.settings is None:
            self._load_settings()
        frame = DashboardFrame(self, self.settings)
        frame.pack(fill="both", expand=True)


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] in ("config", "setup", "onboard"):
        from opencode_telegram_bot.main import run_wizard
        run_wizard()
        return

    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()

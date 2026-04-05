from __future__ import annotations

import asyncio
import json
import logging
import os
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


class LogHandler(logging.Handler):
    """Logging handler that feeds messages to the GUI."""

    def __init__(self, callback: Callable[[str], None]) -> None:
        super().__init__()
        self.callback = callback
        self.setLevel(logging.DEBUG)

    def emit(self, record: logging.LogRecord) -> None:
        msg = self.format(record)
        self.callback(msg)


class SetupFrame(ctk.CTkFrame):
    """Configuration wizard frame."""

    def __init__(self, master: Any, on_done: Callable) -> None:
        super().__init__(master)
        self.on_done = on_done
        self._build()

    def _build(self) -> None:
        ctk.CTkLabel(self, text="Setup Wizard", font=ctk.CTkFont(size=24, weight="bold")).pack(pady=(30, 10))
        ctk.CTkLabel(self, text="Configure your OpenCode Telegram Bot", font=ctk.CTkFont(size=14)).pack(pady=(0, 20))

        env_file = DEFAULT_CONFIG_DIR / ".env"
        existing = self._load_env(env_file) if env_file.exists() else {}

        self.grid_columnconfigure(1, weight=1)

        fields = [
            ("bot_token", "Telegram Bot Token", existing.get("TELEGRAM_BOT_TOKEN", "")),
            ("user_id", "Telegram User ID", existing.get("TELEGRAM_ALLOWED_USER_ID", "")),
            ("api_url", "OpenCode API URL", existing.get("OPENCODE_API_URL", "http://localhost:4096")),
            ("password", "OpenCode Server Password", existing.get("OPENCODE_SERVER_PASSWORD", "")),
            ("opencode_cmd", "OpenCode Command", existing.get("OPENCODE_COMMAND", "opencode")),
        ]

        self.entries: dict[str, ctk.CTkEntry] = {}
        for i, (key, label, default) in enumerate(fields):
            ctk.CTkLabel(self, text=label, anchor="w").grid(row=i, column=0, padx=(30, 10), pady=8, sticky="w")
            entry = ctk.CTkEntry(self, width=400, placeholder_text=default)
            entry.insert(0, default)
            entry.grid(row=i, column=1, padx=(0, 30), pady=8, sticky="ew")
            self.entries[key] = entry

        ctk.CTkLabel(self, text="Locale", anchor="w").grid(row=len(fields), column=0, padx=(30, 10), pady=8, sticky="w")
        locales = get_available_locales()
        current_locale = existing.get("BOT_LOCALE", "en")
        self.locale_var = ctk.StringVar(value=current_locale if current_locale in locales else "en")
        ctk.CTkOptionMenu(self, values=locales, variable=self.locale_var).grid(
            row=len(fields), column=1, padx=(0, 30), pady=8, sticky="w"
        )

        self.auto_start_var = ctk.BooleanVar(value=existing.get("OPENCODE_AUTO_START", "true").lower() == "true")
        ctk.CTkCheckBox(self, text="Auto-start OpenCode server when bot starts", variable=self.auto_start_var).grid(
            row=len(fields) + 1, column=0, columnspan=2, padx=30, pady=15, sticky="w"
        )

        ctk.CTkButton(self, text="Save & Continue", command=self._save, fg_color="#2ea043", hover_color="#3fb950").grid(
            row=len(fields) + 2, column=0, columnspan=2, pady=20
        )

    def _load_env(self, path: Path) -> dict[str, str]:
        result = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                result[key.strip()] = value.strip()
        return result

    def _save(self) -> None:
        DEFAULT_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        env_file = DEFAULT_CONFIG_DIR / ".env"
        lines = [
            f"TELEGRAM_BOT_TOKEN={self.entries['bot_token'].get().strip()}",
            f"TELEGRAM_ALLOWED_USER_ID={self.entries['user_id'].get().strip()}",
            f"OPENCODE_API_URL={self.entries['api_url'].get().strip() or 'http://localhost:4096'}",
            f"OPENCODE_SERVER_PASSWORD={self.entries['password'].get().strip()}",
            f"OPENCODE_COMMAND={self.entries['opencode_cmd'].get().strip() or 'opencode'}",
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
    """Main dashboard frame."""

    def __init__(self, master: Any, settings: Settings) -> None:
        super().__init__(master)
        self.settings = settings
        self.bot_settings = BotSettings()
        self.session_manager = SessionManager()
        self.scheduler = TaskScheduler(max_tasks=settings.task_limit)

        self.client = OpenCodeClient(
            base_url=settings.opencode_api_url,
            username=settings.opencode_server_username,
            password=settings.opencode_server_password or None,
        )
        self.server = OpenCodeServer(
            command=settings.opencode_command,
            work_dir=settings.opencode_work_dir or None,
        )
        self.bot_running = False
        self.bot_thread: threading.Thread | None = None
        self.bot_app = None
        self._stop_event = threading.Event()

        self._build()
        self._start_status_poll()

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # Status bar
        status_frame = ctk.CTkFrame(self)
        status_frame.grid(row=0, column=0, columnspan=2, padx=10, pady=10, sticky="ew")

        self.server_label = ctk.CTkLabel(status_frame, text="Server: Checking...", font=ctk.CTkFont(size=13))
        self.server_label.pack(side="left", padx=15, pady=8)

        self.bot_label = ctk.CTkLabel(status_frame, text="Bot: Stopped", font=ctk.CTkFont(size=13))
        self.bot_label.pack(side="left", padx=15, pady=8)

        self.model_label = ctk.CTkLabel(status_frame, text=f"Model: {self.settings.opencode_model_id}", font=ctk.CTkFont(size=13))
        self.model_label.pack(side="left", padx=15, pady=8)

        # Control buttons
        ctrl_frame = ctk.CTkFrame(self)
        ctrl_frame.grid(row=1, column=0, columnspan=2, padx=10, pady=5, sticky="ew")

        self.start_server_btn = ctk.CTkButton(ctrl_frame, text="Start Server", command=self._toggle_server, fg_color="#2ea043")
        self.start_server_btn.pack(side="left", padx=10, pady=8)

        self.start_bot_btn = ctk.CTkButton(ctrl_frame, text="Start Bot", command=self._toggle_bot, fg_color="#58a6ff")
        self.start_bot_btn.pack(side="left", padx=10, pady=8)

        ctk.CTkButton(ctrl_frame, text="Reconfigure", command=self._reconfigure, fg_color="#6e7681").pack(side="right", padx=10, pady=8)

        # Left panel - Info
        info_frame = ctk.CTkFrame(self)
        info_frame.grid(row=2, column=0, padx=10, pady=10, sticky="nsew")

        ctk.CTkLabel(info_frame, text="Sessions", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(15, 10))
        self.sessions_text = ctk.CTkTextbox(info_frame, height=200)
        self.sessions_text.pack(padx=10, pady=5, fill="x")

        ctk.CTkLabel(info_frame, text="Models", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(15, 10))
        self.models_frame = ctk.CTkScrollableFrame(info_frame, height=200)
        self.models_frame.pack(padx=10, pady=5, fill="both", expand=True)

        self._load_models()

        # Right panel - Logs
        log_frame = ctk.CTkFrame(self)
        log_frame.grid(row=2, column=1, padx=10, pady=10, sticky="nsew")

        ctk.CTkLabel(log_frame, text="Live Logs", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(15, 10))

        self.log_text = ctk.CTkTextbox(log_frame, wrap="word")
        self.log_text.pack(padx=10, pady=5, fill="both", expand=True)

        self.log_text.insert("end", "Ready. Start the OpenCode server and bot.\n")

        log_handler = LogHandler(self._log_callback)
        logging.getLogger("opencode_telegram_bot").addHandler(log_handler)
        logging.getLogger("telegram").addHandler(log_handler)

        ctk.CTkButton(log_frame, text="Clear Logs", command=self._clear_logs, fg_color="#6e7681").pack(pady=5)

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
                self.after(0, lambda: self.server_label.configure(text=f"Server: {health.get('healthy', health.get('status', 'unknown'))}", text_color="#3fb950"))
            except Exception:
                self.after(0, lambda: self.server_label.configure(text="Server: Offline", text_color="#f85149"))

        threading.Thread(target=check, daemon=True).start()

    def _toggle_server(self) -> None:
        if self.server.is_running:
            self.server.stop()
            self.start_server_btn.configure(text="Start Server", fg_color="#2ea043")
            self._append_log("OpenCode server stopped.")
        else:
            self.server.start()
            self.start_server_btn.configure(text="Stop Server", fg_color="#f85149")
            self._append_log("OpenCode server started.")

    def _toggle_bot(self) -> None:
        if self.bot_running:
            self._stop_bot()
        else:
            self._start_bot()

    def _start_bot(self) -> None:
        if self.settings.opencode_auto_start and not self.server.is_running:
            self._append_log("Auto-starting OpenCode server...")
            self.server.start()

        self._stop_event.clear()
        self.bot_thread = threading.Thread(target=self._run_bot_loop, daemon=True)
        self.bot_thread.start()
        self.bot_running = True
        self.start_bot_btn.configure(text="Stop Bot", fg_color="#f85149")
        self.bot_label.configure(text="Bot: Starting...", text_color="#d29922")
        self._append_log("Bot thread started.")

    def _run_bot_loop(self) -> None:
        from dotenv import load_dotenv
        load_dotenv(DEFAULT_CONFIG_DIR / ".env", override=True)

        from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters

        handler_cls = __import__("opencode_telegram_bot.bot.handler", fromlist=["BotHandler"])
        BotHandler = handler_cls.BotHandler

        handler = BotHandler(self.settings, self.bot_settings, self.session_manager, self.scheduler)
        self.scheduler.start()

        app = ApplicationBuilder().token(self.settings.telegram_bot_token).build()
        self.bot_app = app

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

        async def run():
            await app.initialize()
            await app.start()
            await app.updater.start_polling(drop_pending_updates=True)
            self.after(0, lambda: self.bot_label.configure(text="Bot: Running", text_color="#3fb950"))
            self.after(0, lambda: self._append_log("Bot polling started."))
            while not self._stop_event.is_set():
                await asyncio.sleep(0.5)
            await app.updater.stop()
            await app.stop()
            await app.shutdown()
            await handler.cleanup()
            self.scheduler.stop()
            self.after(0, lambda: self.bot_label.configure(text="Bot: Stopped", text_color="#8b949e"))
            self.after(0, lambda: self._append_log("Bot stopped."))

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(run())
        except Exception as e:
            self.after(0, lambda: self._append_log(f"Bot error: {e}"))
            self.after(0, lambda: self.bot_label.configure(text="Bot: Error", text_color="#f85149"))
        finally:
            loop.close()
            self.bot_running = False
            self.after(0, lambda: self.start_bot_btn.configure(text="Start Bot", fg_color="#58a6ff"))

    def _stop_bot(self) -> None:
        self._stop_event.set()
        self.bot_running = False
        self.start_bot_btn.configure(text="Start Bot", fg_color="#58a6ff")
        self.bot_label.configure(text="Bot: Stopping...", text_color="#d29922")
        self._append_log("Stopping bot...")

    def _reconfigure(self) -> None:
        self.master.show_setup()

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
        for p in providers:
            pid = p.get("id", p.get("name", "unknown"))
            models = p.get("models", [])
            ctk.CTkLabel(self.models_frame, text=pid, font=ctk.CTkFont(weight="bold", size=13)).pack(anchor="w", padx=5, pady=(8, 2))
            for m in models[:8]:
                mid = m.get("id", m.get("name", ""))
                btn = ctk.CTkButton(
                    self.models_frame,
                    text=mid,
                    width=200,
                    height=28,
                    fg_color="#21262d",
                    hover_color="#30363d",
                    command=lambda prov=pid, model=mid: self._switch_model(prov, model),
                )
                btn.pack(anchor="w", padx=10, pady=1)

        if not providers:
            ctk.CTkLabel(self.models_frame, text="No models found. Configure providers in OpenCode.").pack(pady=20)

    def _switch_model(self, provider: str, model: str) -> None:
        self.model_label.configure(text=f"Model: {provider}/{model}")
        self._append_log(f"Model selected: {provider}/{model}")

    def _refresh_sessions(self) -> None:
        def fetch():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                sessions = loop.run_until_complete(self.client.get_sessions())
                loop.close()
                self.after(0, lambda: self._render_sessions(sessions))
            except Exception:
                pass

        threading.Thread(target=fetch, daemon=True).start()

    def _render_sessions(self, sessions: list[dict[str, Any]]) -> None:
        self.sessions_text.delete("1.0", "end")
        if not sessions:
            self.sessions_text.insert("end", "No sessions yet.")
            return
        for s in sessions[:10]:
            sid = s.get("id", "unknown")
            summary = s.get("summary", s.get("path", ""))
            self.sessions_text.insert("end", f"{sid[:12]}...  {summary}\n")


class App(ctk.CTk):
    """Main application window."""

    def __init__(self) -> None:
        super().__init__()
        self.title("tp-opencode — OpenCode Telegram Bot")
        self.geometry("1100x700")
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")

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

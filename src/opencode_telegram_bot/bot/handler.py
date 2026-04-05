from __future__ import annotations

import asyncio
import logging
import os
import tempfile
import traceback
import uuid
from pathlib import Path
from typing import Any

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from opencode_telegram_bot.api import OpenCodeClient, OpenCodeServer
from opencode_telegram_bot.core import BotSettings, SessionManager
from opencode_telegram_bot.utils import (
    TaskScheduler,
    TextToSpeech,
    VoiceTranscriber,
    t,
)

logger = logging.getLogger(__name__)


class BotHandler:
    """Main Telegram bot handler for OpenCode."""

    def __init__(
        self,
        settings: Any,
        bot_settings: BotSettings,
        session_manager: SessionManager,
        scheduler: TaskScheduler | None = None,
        client: OpenCodeClient | None = None,
        server: OpenCodeServer | None = None,
    ) -> None:
        self.settings = settings
        self.bot_settings = bot_settings
        self.session_manager = session_manager
        self.scheduler = scheduler
        self._lock = asyncio.Lock()
        self._cached_providers: list[dict[str, Any]] = []
        self._cached_agents: list[dict[str, Any]] = []
        self._cached_commands: list[dict[str, Any]] = []

        self.client = client or OpenCodeClient(
            base_url=settings.opencode_api_url,
            username=settings.opencode_server_username,
            password=settings.opencode_server_password or None,
        )

        self.server = server or OpenCodeServer(
            command=settings.opencode_command or "opencode",
            work_dir=settings.opencode_work_dir or None,
        )

        self.transcriber = VoiceTranscriber(
            api_url=getattr(settings, "stt_api_url", ""),
            api_key=getattr(settings, "stt_api_key", ""),
            model=getattr(settings, "stt_model", "whisper-large-v3-turbo"),
            language=getattr(settings, "stt_language", ""),
        )

        self.tts = TextToSpeech(
            api_url=getattr(settings, "tts_api_url", ""),
            api_key=getattr(settings, "tts_api_key", ""),
            model=getattr(settings, "tts_model", "gpt-4o-mini-tts"),
            voice=getattr(settings, "tts_voice", "alloy"),
        )

        if self.scheduler is not None:
            self.scheduler.register_callback("run_task", self._run_scheduled_task)

    def _locale(self) -> str:
        return self.settings.bot_locale or "en"

    def _is_authorized(self, user_id: int) -> bool:
        allowed = self.settings.telegram_allowed_user_id
        if not allowed:
            return True
        return str(user_id) == str(allowed)

    async def _send(self, context: ContextTypes.DEFAULT_TYPE, chat_id: int, text: str, **kwargs: Any) -> Any:
        parse_mode = kwargs.pop("parse_mode", None)
        try:
            return await context.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=parse_mode,
                **kwargs,
            )
        except Exception as e:
            logger.warning("Failed to send with parse_mode=%s: %s", parse_mode, e)
            try:
                return await context.bot.send_message(chat_id=chat_id, text=text, **kwargs)
            except Exception:
                return None

    async def _send_status_bar(self, context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
        try:
            session_id = self.bot_settings.current_session_id
            if not session_id:
                return
            project = await self.client.get_current_project()
            project_name = project.get("path", project.get("name", "unknown"))
            agent_mode = self.bot_settings.get("agent_mode", "build")
            mode_emoji = "📋" if agent_mode == "plan" else "🔨"
            text = f"{mode_emoji} *{agent_mode.upper()}* | {self.settings.opencode_model_id}\n📁 {project_name}"
            msg_id = self.bot_settings.get("status_message_id")
            if msg_id:
                try:
                    await context.bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=msg_id,
                        text=text,
                        parse_mode="Markdown",
                    )
                    return
                except Exception:
                    pass
            msg = await context.bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown")
            self.bot_settings.set("status_message_id", msg.message_id)
        except Exception:
            pass

    async def _ensure_session(self) -> str:
        session_id = self.bot_settings.current_session_id
        if session_id:
            return session_id
        session = await self.client.create_session()
        session_id = session.get("id", str(uuid.uuid4()))
        self.bot_settings.current_session_id = session_id
        return session_id

    async def _cache_metadata(self) -> None:
        if not self._cached_providers:
            try:
                providers_data = await self.client.get_providers()
                self._cached_providers = providers_data.get("all", [])
            except Exception:
                pass
        if not self._cached_agents:
            try:
                self._cached_agents = await self.client.get_agents()
            except Exception:
                pass
        if not self._cached_commands:
            try:
                self._cached_commands = await self.client.get_commands()
            except Exception:
                pass

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_authorized(update.effective_user.id):
            await update.message.reply_text(t("unauthorized", locale=self._locale()))
            return
        await update.message.reply_text(t("welcome", locale=self._locale()))
        await self._send_status_bar(context, update.message.chat_id)

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_authorized(update.effective_user.id):
            return
        await update.message.reply_text(t("help", locale=self._locale()))

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_authorized(update.effective_user.id):
            return
        try:
            health = await self.client.health()
            project = await self.client.get_current_project()
            session_id = self.bot_settings.current_session_id
            session_info = f"{session_id}" if session_id else "None"
            project_name = project.get("path", project.get("name", "unknown"))
            text = (
                f"Server: {health.get('healthy', health.get('status', 'unknown'))}\n"
                f"Project: {project_name}\n"
                f"Session: {session_info}\n"
                f"Model: {self.settings.opencode_model_provider}/{self.settings.opencode_model_id}"
            )
            await update.message.reply_text(text)
        except Exception as e:
            await update.message.reply_text(t("error", locale=self._locale(), message=str(e)))

    async def cmd_new(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_authorized(update.effective_user.id):
            return
        try:
            session = await self.client.create_session()
            session_id = session.get("id", str(uuid.uuid4()))
            self.bot_settings.current_session_id = session_id
            await update.message.reply_text(t("new_session", locale=self._locale(), session_id=session_id[:12]))
            await self._send_status_bar(context, update.message.chat_id)
        except Exception as e:
            await update.message.reply_text(t("error", locale=self._locale(), message=str(e)))

    async def cmd_abort(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_authorized(update.effective_user.id):
            return
        session_id = self.bot_settings.current_session_id
        if not session_id:
            await update.message.reply_text(t("no_session", locale=self._locale()))
            return
        try:
            await self.client.abort_session(session_id)
            await update.message.reply_text(t("abort", locale=self._locale()))
        except Exception as e:
            await update.message.reply_text(t("error", locale=self._locale(), message=str(e)))

    async def cmd_sessions(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_authorized(update.effective_user.id):
            return
        try:
            sessions = await self.client.get_sessions()
            limit = self.settings.sessions_list_limit
            if not sessions:
                await update.message.reply_text("No sessions found.")
                return
            keyboard = []
            for s in sessions[:limit]:
                sid = s.get("id", "")
                title = s.get("summary", s.get("path", sid[:12]))
                keyboard.append([InlineKeyboardButton(title, callback_data=f"session:{sid}")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(t("sessions_title", locale=self._locale()), reply_markup=reply_markup)
        except Exception as e:
            await update.message.reply_text(t("error", locale=self._locale(), message=str(e)))

    async def cmd_projects(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_authorized(update.effective_user.id):
            return
        try:
            projects = await self.client.get_projects()
            limit = self.settings.projects_list_limit
            keyboard = []
            for p in projects[:limit]:
                path = p.get("path", "")
                name = p.get("name", Path(path).name if path else "unknown")
                keyboard.append([InlineKeyboardButton(name, callback_data=f"project:{path}")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(t("projects_title", locale=self._locale()), reply_markup=reply_markup)
        except Exception as e:
            await update.message.reply_text(t("error", locale=self._locale(), message=str(e)))

    async def cmd_tts(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_authorized(update.effective_user.id):
            return
        self.bot_settings.tts_enabled = not self.bot_settings.tts_enabled
        key = "tts_on" if self.bot_settings.tts_enabled else "tts_off"
        await update.message.reply_text(t(key, locale=self._locale()))

    async def cmd_rename(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_authorized(update.effective_user.id):
            return
        session_id = self.bot_settings.current_session_id
        if not session_id:
            await update.message.reply_text(t("no_session", locale=self._locale()))
            return
        if not context.args:
            await update.message.reply_text("Usage: /rename <new title>")
            return
        title = " ".join(context.args)
        try:
            await self.client.rename_session(session_id, title)
            await update.message.reply_text(t("renamed", locale=self._locale(), title=title))
        except Exception as e:
            await update.message.reply_text(t("error", locale=self._locale(), message=str(e)))

    async def cmd_compact(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_authorized(update.effective_user.id):
            return
        session_id = self.bot_settings.current_session_id
        if not session_id:
            await update.message.reply_text(t("no_session", locale=self._locale()))
            return
        try:
            await self.client.summarize_session(session_id)
            await update.message.reply_text(t("compact_done", locale=self._locale()))
        except Exception as e:
            await update.message.reply_text(t("error", locale=self._locale(), message=str(e)))

    async def cmd_mode(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_authorized(update.effective_user.id):
            return
        current = self.bot_settings.get("agent_mode", "build")
        new_mode = "plan" if current == "build" else "build"
        self.bot_settings.set("agent_mode", new_mode)
        key = "mode_plan" if new_mode == "plan" else "mode_build"
        await update.message.reply_text(t("mode_switched", locale=self._locale(), mode=new_mode.capitalize()))

    async def cmd_models(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_authorized(update.effective_user.id):
            return
        try:
            await self._cache_metadata()
            keyboard = []
            providers_data = await self.client.get_config_providers()
            providers = providers_data.get("providers", [])
            for p in providers[:15]:
                pid = p.get("id", p.get("name", ""))
                models = p.get("models", [])
                for m in models[:5]:
                    mid = m.get("id", m.get("name", ""))
                    label = f"{pid}/{mid}"
                    keyboard.append([InlineKeyboardButton(label, callback_data=f"model:{pid}:{mid}")])
            if not keyboard:
                for p in self._cached_providers[:10]:
                    pid = p.get("id", p.get("name", ""))
                    keyboard.append([InlineKeyboardButton(pid, callback_data=f"model:{pid}:")])
            if not keyboard:
                await update.message.reply_text("No models available. Configure providers in OpenCode first.")
                return
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(t("models_title", locale=self._locale()), reply_markup=reply_markup)
        except Exception as e:
            await update.message.reply_text(t("error", locale=self._locale(), message=str(e)))

    async def cmd_commands(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_authorized(update.effective_user.id):
            return
        try:
            await self._cache_metadata()
            commands = self._cached_commands
            if not commands:
                commands = [{"id": "init", "name": "init"}, {"id": "review", "name": "review"}]
            keyboard = []
            for cmd in commands[: self.settings.commands_list_limit]:
                name = cmd.get("name", cmd.get("id", ""))
                keyboard.append([InlineKeyboardButton(name, callback_data=f"runcmd:{name}")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(t("commands_title", locale=self._locale()), reply_markup=reply_markup)
        except Exception as e:
            await update.message.reply_text(t("error", locale=self._locale(), message=str(e)))

    async def cmd_opencode_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_authorized(update.effective_user.id):
            return
        if self.server.is_running:
            await update.message.reply_text(t("server_already_running", locale=self._locale()))
            return
        try:
            self.server.start()
            await asyncio.sleep(3)
            await update.message.reply_text(t("server_started", locale=self._locale()))
        except Exception as e:
            await update.message.reply_text(t("error", locale=self._locale(), message=str(e)))

    async def cmd_opencode_stop(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_authorized(update.effective_user.id):
            return
        if not self.server.is_running:
            await update.message.reply_text(t("server_not_started", locale=self._locale()))
            return
        try:
            self.server.stop()
            await update.message.reply_text(t("server_stopped", locale=self._locale()))
        except Exception as e:
            await update.message.reply_text(t("error", locale=self._locale(), message=str(e)))

    async def cmd_task(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_authorized(update.effective_user.id):
            return
        await update.message.reply_text(
            "Usage: /task <interval_minutes> <prompt>\nExample: /task 60 Run tests and report results"
        )

    async def cmd_tasklist(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_authorized(update.effective_user.id):
            return
        tasks = self.scheduler.list_tasks()
        if not tasks:
            await update.message.reply_text(t("no_tasks", locale=self._locale()))
            return
        for tid, info in tasks.items():
            lines = [f"{tid}: {info.get('prompt', '')[:80]}"]
            keyboard = [[InlineKeyboardButton("Delete", callback_data=f"deltask:{tid}")]]
            await update.message.reply_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(keyboard))

    async def callback_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if not query or not self._is_authorized(query.from_user.id):
            return
        await query.answer()
        data = query.data
        chat_id = query.message.chat_id

        if data.startswith("session:"):
            session_id = data.split(":", 1)[1]
            self.bot_settings.current_session_id = session_id
            await self._send(context, chat_id, t("switched_session", locale=self._locale(), session_id=session_id[:12]))
            await self._send_status_bar(context, chat_id)

        elif data.startswith("project:"):
            project_path = data.split(":", 1)[1]
            await self._send(context, chat_id, t("switched_project", locale=self._locale(), project=project_path))
            await self._send_status_bar(context, chat_id)

        elif data.startswith("model:"):
            parts = data.split(":", 2)
            provider = parts[1]
            model_id = parts[2]
            model_str = f"{provider}/{model_id}" if model_id else provider
            await self._send(context, chat_id, t("model_switched", locale=self._locale(), provider=provider, model=model_id or "default"))

        elif data.startswith("runcmd:"):
            command = data.split(":", 1)[1]
            await self._send(context, chat_id, t("command_running", locale=self._locale(), command=command))
            try:
                session_id = await self._ensure_session()
                result = await self.client.run_command(session_id, command)
                result_text = OpenCodeClient.extract_text_from_response(result)
                if result_text:
                    await self._send(context, chat_id, result_text[:4000])
                else:
                    await self._send(context, chat_id, str(result)[:4000])
            except Exception as e:
                await self._send(context, chat_id, t("error", locale=self._locale(), message=str(e)))

        elif data.startswith("deltask:"):
            task_id = data.split(":", 1)[1]
            if self.scheduler.remove_task(task_id):
                await self._send(context, chat_id, t("task_deleted", locale=self._locale(), task_id=task_id))

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_authorized(update.effective_user.id):
            return
        chat_id = update.message.chat_id

        if update.message.voice or update.message.audio:
            await self._handle_media(update, context)
            return

        if update.message.document and update.message.document.mime_type.startswith("audio"):
            await self._handle_media(update, context)
            return

        text = update.message.text or update.message.caption
        if not text:
            return

        async with self._lock:
            await self._process_prompt(chat_id, text, context)

    async def _handle_media(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = update.message.chat_id
        if not self.transcriber.is_configured:
            await update.message.reply_text(t("voice_not_configured", locale=self._locale()))
            return

        file_obj = None
        if update.message.voice:
            file_obj = update.message.voice
        elif update.message.audio:
            file_obj = update.message.audio
        elif update.message.document and update.message.document.mime_type.startswith("audio"):
            file_obj = update.message.document

        if not file_obj:
            return

        status_msg = await update.message.reply_text("Transcribing audio...")
        try:
            file = await context.bot.get_file(file_obj.file_id)
            with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
                await file.download_to_drive(tmp.name)
                tmp_path = tmp.name
            text = await self.transcriber.transcribe(tmp_path)
            os.unlink(tmp_path)
            if text:
                await status_msg.edit_text(t("voice_transcribed", locale=self._locale(), text=text))
                await self._process_prompt(chat_id, text, context)
            else:
                await status_msg.edit_text("Transcription returned no text.")
        except Exception as e:
            await status_msg.edit_text(f"Transcription failed: {e}")

    async def _process_prompt(
        self,
        chat_id: int,
        prompt: str,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        try:
            session_id = await self._ensure_session()
        except Exception as e:
            logger.error("Failed to create session: %s\n%s", e, traceback.format_exc())
            await self._send(context, chat_id, t("error", locale=self._locale(), message=str(e)))
            return

        thinking_msg = await self._send(context, chat_id, t("thinking", locale=self._locale()))

        try:
            agent_mode = self.bot_settings.get("agent_mode", "build")
            response = await self.client.send_message(session_id, prompt, agent=agent_mode)

            response_text = OpenCodeClient.extract_text_from_response(response)
            tool_calls = OpenCodeClient.extract_tool_calls(response)

            if tool_calls and not self.settings.hide_tool_call_messages:
                for tc in tool_calls:
                    detail = str(tc.get("input", ""))[: self.settings.bash_tool_display_max_length]
                    await self._send(
                        context, chat_id,
                        t("tool_call", locale=self._locale(), tool=tc["name"], detail=detail),
                    )

            if response_text:
                if len(response_text) > 4000:
                    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w", encoding="utf-8") as f:
                        f.write(response_text)
                        f.flush()
                    await context.bot.send_document(
                        chat_id=chat_id,
                        document=open(f.name, "rb"),
                        filename="response.txt",
                    )
                    os.unlink(f.name)
                else:
                    await self._send(context, chat_id, response_text)

                if self.bot_settings.tts_enabled and self.tts.is_configured:
                    audio = await self.tts.synthesize(response_text[:4000])
                    if audio:
                        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                            f.write(audio)
                            audio_path = f.name
                        await context.bot.send_voice(chat_id=chat_id, voice=open(audio_path, "rb"))
                        os.unlink(audio_path)
            else:
                raw = str(response)[:4000]
                if raw and raw != "{}":
                    await self._send(context, chat_id, raw)

        except Exception as e:
            logger.error("Prompt processing failed: %s\n%s", e, traceback.format_exc())
            await self._send(context, chat_id, t("error", locale=self._locale(), message=str(e)))

        await self._send_status_bar(context, chat_id)

    async def _run_scheduled_task(
        self,
        prompt: str,
        project_id: str,
        model_provider: str,
        model_id: str,
    ) -> None:
        logger.info("Running scheduled task: %s", prompt[:100])
        try:
            session = await self.client.create_session()
            session_id = session.get("id", str(uuid.uuid4()))
            await self.client.send_message(session_id, prompt)
            logger.info("Scheduled task sent to session %s", session_id)
        except Exception as e:
            logger.error("Scheduled task failed: %s", e)

    async def cleanup(self) -> None:
        await self.client.close()

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
import uuid
from pathlib import Path
from typing import Any

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.ext import (
    Application,
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
    get_available_locales,
    t,
)

logger = logging.getLogger(__name__)

PENDING_ANSWERS: dict[str, str] = {}


class BotHandler:
    """Main Telegram bot handler for OpenCode."""

    def __init__(
        self,
        settings: Any,
        bot_settings: BotSettings,
        session_manager: SessionManager,
        scheduler: TaskScheduler,
    ) -> None:
        self.settings = settings
        self.bot_settings = bot_settings
        self.session_manager = session_manager
        self.scheduler = scheduler
        self.client = OpenCodeClient(
            base_url=settings.opencode_api_url,
            username=settings.opencode_server_username,
            password=settings.opencode_server_password or None,
        )
        self.server = OpenCodeServer(
            command=settings.opencode_command,
            work_dir=settings.opencode_work_dir or None,
        )
        self.transcriber = VoiceTranscriber(
            api_url=settings.stt_api_url,
            api_key=settings.stt_api_key,
            model=settings.stt_model,
            language=settings.stt_language,
        )
        self.tts = TextToSpeech(
            api_url=settings.tts_api_url,
            api_key=settings.tts_api_key,
            model=settings.tts_model,
            voice=settings.tts_voice,
        )
        self._active_streams: dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()

        self.scheduler.register_callback("run_task", self._run_scheduled_task)

    def _locale(self) -> str:
        return self.settings.bot_locale or "en"

    def _is_authorized(self, user_id: int) -> bool:
        allowed = self.settings.telegram_allowed_user_id
        if not allowed:
            return True
        return str(user_id) == str(allowed)

    async def _send(self, context: ContextTypes.DEFAULT_TYPE, chat_id: int, text: str, **kwargs: Any) -> Any:
        parse_mode = kwargs.pop("parse_mode", "MarkdownV2" if self.settings.message_format_mode == "markdown" else None)
        try:
            return await context.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=parse_mode,
                **kwargs,
            )
        except Exception as e:
            logger.warning("Failed to send message: %s", e)
            try:
                return await context.bot.send_message(chat_id=chat_id, text=text, **kwargs)
            except Exception:
                return None

    async def _send_status_bar(self, context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
        try:
            session_id = self.bot_settings.current_session_id
            if not session_id:
                return
            status = await self.client.get_session_status(session_id)
            project = await self.client.get_current_project()
            project_name = project.get("name", project.get("path", "unknown"))
            model = status.get("model", self.settings.opencode_model_id)
            tokens_data = status.get("tokens", {})
            tokens_used = tokens_data.get("total", tokens_data.get("completion", 0))
            tokens_max = tokens_data.get("limit", "N/A")
            agent = status.get("agent", "build")
            mode_emoji = "📋" if agent == "plan" else "🔨"
            text = (
                f"{mode_emoji} *{agent.upper()}* | {model}\n"
                f"📁 {project_name} | 🔑 {tokens_used}/{tokens_max}"
            )
            try:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=self.bot_settings.get("status_message_id", 0),
                    text=text,
                    parse_mode="Markdown",
                )
            except Exception:
                msg = await context.bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown")
                self.bot_settings.set("status_message_id", msg.message_id)
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
            session_info = "None"
            if session_id:
                status = await self.client.get_session_status(session_id)
                session_info = f"{session_id} ({status.get('status', 'unknown')})"
            project_name = project.get("name", project.get("path", "unknown"))
            text = (
                f"Server: {health.get('status', 'unknown')}\n"
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
            agent = self.bot_settings.get("agent_mode", "build")
            session = await self.client.create_session(agent=agent)
            session_id = session.get("id", session.get("session_id", str(uuid.uuid4())))
            self.bot_settings.current_session_id = session_id
            await update.message.reply_text(t("new_session", locale=self._locale(), session_id=session_id))
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
                sid = s.get("id", s.get("session_id", ""))
                title = s.get("title", s.get("path", sid[:8]))
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
                pid = p.get("id", p.get("path", ""))
                name = p.get("name", p.get("path", pid))
                keyboard.append([InlineKeyboardButton(name, callback_data=f"project:{pid}")])
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
            await self.client.compact_session(session_id)
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
            models_data = await self.client.get_models()
            keyboard = []
            models_list = models_data.get("models", models_data if isinstance(models_data, list) else [])
            for m in models_list[:20]:
                mid = m.get("id", m.get("model", ""))
                provider = m.get("provider", m.get("name", ""))
                label = f"{provider}/{mid}" if provider else mid
                keyboard.append([InlineKeyboardButton(label, callback_data=f"model:{provider}:{mid}")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(t("models_title", locale=self._locale()), reply_markup=reply_markup)
        except Exception as e:
            await update.message.reply_text(t("error", locale=self._locale(), message=str(e)))

    async def cmd_commands(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_authorized(update.effective_user.id):
            return
        try:
            commands = ["init", "review", "commit", "test"]
            keyboard = []
            for cmd in commands[: self.settings.commands_list_limit]:
                keyboard.append([InlineKeyboardButton(cmd, callback_data=f"runcmd:{cmd}")])
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
        lines = [t("task_list", locale=self._locale())]
        for tid, info in tasks.items():
            lines.append(f"• {tid}: {info.get('prompt', '')[:50]}...")
            keyboard = [[InlineKeyboardButton("Delete", callback_data=f"deltask:{tid}")]]
            await update.message.reply_text("\n".join(lines[-2:]), reply_markup=InlineKeyboardMarkup(keyboard))

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
            await self._send(context, chat_id, t("switched_session", locale=self._locale(), session_id=session_id))
            await self._send_status_bar(context, chat_id)

        elif data.startswith("project:"):
            project_id = data.split(":", 1)[1]
            try:
                await self.client.switch_project(project_id)
                self.bot_settings.current_project_id = project_id
                await self._send(context, chat_id, t("switched_project", locale=self._locale(), project=project_id))
            except Exception as e:
                await self._send(context, chat_id, t("error", locale=self._locale(), message=str(e)))
            await self._send_status_bar(context, chat_id)

        elif data.startswith("model:"):
            parts = data.split(":", 2)
            provider = parts[1]
            model_id = parts[2]
            try:
                await self.client.switch_model(provider, model_id)
                await self._send(
                    context,
                    chat_id,
                    t("model_switched", locale=self._locale(), provider=provider, model=model_id),
                )
            except Exception as e:
                await self._send(context, chat_id, t("error", locale=self._locale(), message=str(e)))

        elif data.startswith("runcmd:"):
            command = data.split(":", 1)[1]
            await self._send(context, chat_id, t("command_running", locale=self._locale(), command=command))
            try:
                session_id = self.bot_settings.current_session_id
                result = await self.client.run_custom_command(command, session_id)
                result_text = str(result.get("output", result))[:4000]
                await self._send(context, chat_id, f"```\n{result_text}\n```")
            except Exception as e:
                await self._send(context, chat_id, t("error", locale=self._locale(), message=str(e)))

        elif data.startswith("deltask:"):
            task_id = data.split(":", 1)[1]
            if self.scheduler.remove_task(task_id):
                await self._send(context, chat_id, t("task_deleted", locale=self._locale(), task_id=task_id))

        elif data.startswith("perm:"):
            action = data.split(":")[1]
            question_id = data.split(":")[2]
            answer = "yes" if action == "approve" else "no"
            PENDING_ANSWERS[question_id] = answer
            label = t("permission_approved", locale=self._locale()) if action == "approve" else t("permission_denied", locale=self._locale())
            await self._send(context, chat_id, label)

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_authorized(update.effective_user.id):
            return
        chat_id = update.message.chat_id

        if update.message.voice or update.message.audio or update.message.document:
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
        session_id = self.bot_settings.current_session_id
        if not session_id:
            try:
                agent = self.bot_settings.get("agent_mode", "build")
                session = await self.client.create_session(agent=agent)
                session_id = session.get("id", session.get("session_id", str(uuid.uuid4())))
                self.bot_settings.current_session_id = session_id
            except Exception as e:
                await self._send(context, chat_id, t("error", locale=self._locale(), message=str(e)))
                return

        thinking_msg = await self._send(context, chat_id, t("thinking", locale=self._locale()))

        try:
            await self.client.send_message(session_id, prompt)

            if self.settings.response_streaming:
                await self._stream_response(session_id, chat_id, context, thinking_msg)
            else:
                await self._poll_response(session_id, chat_id, context, thinking_msg)
        except Exception as e:
            await self._send(context, chat_id, t("error", locale=self._locale(), message=str(e)))

        await self._send_status_bar(context, chat_id)

    async def _stream_response(
        self,
        session_id: str,
        chat_id: int,
        context: ContextTypes.DEFAULT_TYPE,
        thinking_msg: Any,
    ) -> None:
        response_text = ""
        response_message = None
        try:
            async for event in self.client.stream_session_events(session_id):
                event_type = event.get("type", "")
                data = event.get("data", {})

                if event_type in ("text", "text/delta", "message.delta"):
                    delta = data.get("delta", data.get("text", ""))
                    if delta:
                        response_text += delta
                        if len(response_text) > 4000:
                            if response_message:
                                try:
                                    await context.bot.edit_message_text(
                                        chat_id=chat_id,
                                        message_id=response_message.message_id,
                                        text=response_text[:4000],
                                    )
                                except Exception:
                                    pass
                            response_text = response_text[4000:]
                            response_message = None

                        if not response_message:
                            response_message = await context.bot.send_message(
                                chat_id=chat_id,
                                text=response_text[:4000],
                            )
                        else:
                            try:
                                await context.bot.edit_message_text(
                                    chat_id=chat_id,
                                    message_id=response_message.message_id,
                                    text=response_text[:4000],
                                )
                            except Exception:
                                response_message = await context.bot.send_message(
                                    chat_id=chat_id,
                                    text=response_text[:4000],
                                )

                elif event_type in ("tool_call", "tool"):
                    tool_name = data.get("tool", data.get("name", "unknown"))
                    tool_input = data.get("input", data.get("args", ""))
                    detail = str(tool_input)[: self.settings.bash_tool_display_max_length]
                    if not self.settings.hide_tool_call_messages:
                        tool_msg = t("tool_call", locale=self._locale(), tool=tool_name, detail=detail)
                        await self._send(context, chat_id, tool_msg)

            if response_text:
                if response_message:
                    try:
                        await context.bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=response_message.message_id,
                            text=response_text[:4000],
                        )
                    except Exception:
                        pass
                else:
                    await context.bot.send_message(chat_id=chat_id, text=response_text[:4000])

                if self.bot_settings.tts_enabled and self.tts.is_configured:
                    audio = await self.tts.synthesize(response_text[:4000])
                    if audio:
                        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                            f.write(audio)
                            audio_path = f.name
                        await context.bot.send_voice(chat_id=chat_id, voice=open(audio_path, "rb"))
                        os.unlink(audio_path)

        except Exception as e:
            logger.error("Streaming error: %s", e)
            if response_text:
                await self._send(context, chat_id, response_text[:4000])
            else:
                await self._send(context, chat_id, t("error", locale=self._locale(), message=str(e)))

    async def _poll_response(
        self,
        session_id: str,
        chat_id: int,
        context: ContextTypes.DEFAULT_TYPE,
        thinking_msg: Any,
    ) -> None:
        max_polls = 300
        interval = self.settings.service_messages_interval_sec
        last_text = ""
        for _ in range(max_polls):
            await asyncio.sleep(interval)
            try:
                status = await self.client.get_session_status(session_id)
                if status.get("status") in ("idle", "done", "error"):
                    break
            except Exception:
                continue

        try:
            session = await self.client.get_session(session_id)
            messages = session.get("messages", [])
            for msg in reversed(messages):
                if msg.get("role") == "assistant":
                    text = msg.get("content", msg.get("text", ""))
                    if text and text != last_text:
                        if len(text) > 4000:
                            with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w") as f:
                                f.write(text)
                                f.flush()
                            await context.bot.send_document(
                                chat_id=chat_id,
                                document=open(f.name, "rb"),
                                filename="response.txt",
                            )
                            os.unlink(f.name)
                        else:
                            await self._send(context, chat_id, text)
                        break
        except Exception as e:
            await self._send(context, chat_id, t("error", locale=self._locale(), message=str(e)))

    async def _run_scheduled_task(
        self,
        prompt: str,
        project_id: str,
        model_provider: str,
        model_id: str,
    ) -> None:
        logger.info("Running scheduled task: %s", prompt[:100])
        try:
            if project_id:
                await self.client.switch_project(project_id)
            if model_provider and model_id:
                await self.client.switch_model(model_provider, model_id)
            session = await self.client.create_session(agent="build")
            session_id = session.get("id", session.get("session_id", str(uuid.uuid4())))
            await self.client.send_message(session_id, prompt)
            logger.info("Scheduled task sent to session %s", session_id)
        except Exception as e:
            logger.error("Scheduled task failed: %s", e)

    async def cleanup(self) -> None:
        await self.client.close()
        for task in self._active_streams.values():
            task.cancel()

from __future__ import annotations

import logging
from threading import Thread

from flask import Flask, Response, jsonify, render_template_string

logger = logging.getLogger(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>OpenCode Telegram Bot — Monitor</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0d1117; color: #c9d1d9; padding: 20px; }
        .container { max-width: 900px; margin: 0 auto; }
        h1 { color: #58a6ff; margin-bottom: 20px; font-size: 1.5rem; }
        h2 { color: #8b949e; margin: 20px 0 10px; font-size: 1.1rem; }
        .card { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 16px; margin-bottom: 12px; }
        .card h3 { color: #58a6ff; font-size: 0.95rem; margin-bottom: 8px; }
        .card p { color: #8b949e; font-size: 0.85rem; line-height: 1.5; }
        .status-ok { color: #3fb950; }
        .status-err { color: #f85149; }
        .badge { display: inline-block; background: #21262d; border: 1px solid #30363d; border-radius: 12px; padding: 2px 10px; font-size: 0.75rem; margin: 2px; }
        .refresh { color: #8b949e; font-size: 0.75rem; margin-top: 20px; }
        a { color: #58a6ff; }
    </style>
    <meta http-equiv="refresh" content="30">
</head>
<body>
<div class="container">
    <h1>OpenCode Telegram Bot</h1>
    <p class="refresh">Auto-refreshes every 30s &middot; <a href="/api/status">JSON API</a></p>

    <h2>Server Status</h2>
    <div class="card">
        <h3>OpenCode Server</h3>
        <p>Status: <span class="{{ 'status-ok' if server_ok else 'status-err' }}">{{ server_status }}</span></p>
        <p>API URL: {{ api_url }}</p>
    </div>

    <h2>Bot Status</h2>
    <div class="card">
        <h3>Telegram Bot</h3>
        <p>Running: <span class="status-ok">{{ bot_running }}</span></p>
        <p>Locale: {{ locale }}</p>
        <p>Model: {{ model_provider }}/{{ model_id }}</p>
    </div>

    <h2>Sessions</h2>
    {% for sid, info in sessions.items() %}
    <div class="card">
        <h3>{{ sid[:12] }}...</h3>
        <p>Created: {{ info.get('created_at', 'N/A') }}</p>
        <p>Updated: {{ info.get('updated_at', 'N/A') }}</p>
    </div>
    {% endfor %}
    {% if not sessions %}
    <div class="card"><p>No active sessions.</p></div>
    {% endif %}

    <h2>Scheduled Tasks</h2>
    {% for tid, info in tasks.items() %}
    <div class="card">
        <h3>{{ tid }}</h3>
        <p>Prompt: {{ info.get('prompt', '')[:100] }}</p>
        <p>Type: {{ info.get('type', 'unknown') }}</p>
        {% if info.get('interval_minutes') %}<p>Interval: {{ info['interval_minutes'] }}m</p>{% endif %}
    </div>
    {% endfor %}
    {% if not tasks %}
    <div class="card"><p>No scheduled tasks.</p></div>
    {% endif %}
</div>
</body>
</html>
"""


class WebGUI:
    """Simple Flask-based monitoring web GUI."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8765,
        bot_handler=None,
    ) -> None:
        self.host = host
        self.port = port
        self.bot_handler = bot_handler
        self.app = Flask(__name__)
        self._thread: Thread | None = None
        self._setup_routes()

    def _setup_routes(self) -> None:
        @self.app.route("/")
        def index():
            if not self.bot_handler:
                return render_template_string(HTML_TEMPLATE, server_ok=False, server_status="Not connected", api_url="", bot_running="No", locale="en", model_provider="", model_id="", sessions={}, tasks={})

            settings = self.bot_handler.settings
            bs = self.bot_handler.bot_settings
            sm = self.bot_handler.session_manager
            tasks = self.bot_handler.scheduler.list_tasks()

            server_ok = True
            server_status = "Running"
            try:
                import asyncio
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                health = loop.run_until_complete(self.bot_handler.client.health())
                server_status = health.get("status", "unknown")
                loop.close()
            except Exception:
                server_ok = False

            return render_template_string(
                HTML_TEMPLATE,
                server_ok=server_ok,
                server_status=server_status,
                api_url=settings.opencode_api_url,
                bot_running="Yes",
                locale=settings.bot_locale,
                model_provider=settings.opencode_model_provider,
                model_id=settings.opencode_model_id,
                sessions=sm.list_all(),
                tasks=tasks,
            )

        @self.app.route("/api/status")
        def api_status():
            if not self.bot_handler:
                return jsonify({"error": "Bot not initialized"})

            settings = self.bot_handler.settings
            return jsonify({
                "server": {
                    "url": settings.opencode_api_url,
                    "model_provider": settings.opencode_model_provider,
                    "model_id": settings.opencode_model_id,
                },
                "bot": {
                    "locale": settings.bot_locale,
                    "tts_enabled": self.bot_handler.bot_settings.tts_enabled,
                    "current_session": self.bot_handler.bot_settings.current_session_id,
                },
                "sessions": self.bot_handler.session_manager.list_all(),
                "tasks": self.bot_handler.scheduler.list_tasks(),
            })

    def start(self) -> None:
        def run_flask():
            self.app.run(host=self.host, port=self.port, debug=False, use_reloader=False)

        self._thread = Thread(target=run_flask, daemon=True)
        self._thread.start()
        logger.info("Web GUI started at http://%s:%d", self.host, self.port)

    def stop(self) -> None:
        pass

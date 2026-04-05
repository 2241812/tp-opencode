from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncGenerator

import httpx

logger = logging.getLogger(__name__)


class OpenCodeClient:
    """HTTP client for the OpenCode server API."""

    def __init__(
        self,
        base_url: str = "http://localhost:4096",
        username: str = "opencode",
        password: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._auth: tuple[str, str] | None = (username, password) if password else None
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            auth=self._auth,
            timeout=httpx.Timeout(300.0, connect=10.0),
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def _get(self, path: str, **kwargs: Any) -> httpx.Response:
        resp = await self._client.get(path, **kwargs)
        resp.raise_for_status()
        return resp

    async def _post(self, path: str, **kwargs: Any) -> httpx.Response:
        resp = await self._client.post(path, **kwargs)
        resp.raise_for_status()
        return resp

    async def health(self) -> dict[str, Any]:
        resp = await self._get("/health")
        return resp.json()

    async def get_projects(self) -> list[dict[str, Any]]:
        resp = await self._get("/api/projects")
        data = resp.json()
        return data if isinstance(data, list) else []

    async def get_current_project(self) -> dict[str, Any]:
        resp = await self._get("/api/project")
        return resp.json()

    async def switch_project(self, project_id: str) -> dict[str, Any]:
        resp = await self._post("/api/project/switch", json={"id": project_id})
        return resp.json()

    async def get_sessions(self) -> list[dict[str, Any]]:
        resp = await self._get("/api/sessions")
        data = resp.json()
        return data if isinstance(data, list) else []

    async def create_session(self, agent: str = "build") -> dict[str, Any]:
        resp = await self._post("/api/sessions", json={"agent": agent})
        return resp.json()

    async def get_session(self, session_id: str) -> dict[str, Any]:
        resp = await self._get(f"/api/sessions/{session_id}")
        return resp.json()

    async def delete_session(self, session_id: str) -> dict[str, Any]:
        resp = await self._post(f"/api/sessions/{session_id}/delete")
        return resp.json()

    async def compact_session(self, session_id: str) -> dict[str, Any]:
        resp = await self._post(f"/api/sessions/{session_id}/compact")
        return resp.json()

    async def rename_session(self, session_id: str, title: str) -> dict[str, Any]:
        resp = await self._post(f"/api/sessions/{session_id}/rename", json={"title": title})
        return resp.json()

    async def abort_session(self, session_id: str) -> dict[str, Any]:
        resp = await self._post(f"/api/sessions/{session_id}/abort")
        return resp.json()

    async def get_models(self) -> dict[str, Any]:
        resp = await self._get("/api/models")
        return resp.json()

    async def switch_model(self, provider: str, model_id: str) -> dict[str, Any]:
        resp = await self._post("/api/models/switch", json={"provider": provider, "model": model_id})
        return resp.json()

    async def send_message(
        self,
        session_id: str,
        message: str,
        files: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"message": message}
        if files:
            payload["files"] = files
        resp = await self._post(f"/api/sessions/{session_id}/message", json=payload)
        return resp.json()

    async def stream_session_events(self, session_id: str) -> AsyncGenerator[dict[str, Any], None]:
        """Subscribe to SSE events for a session."""
        url = f"/api/sessions/{session_id}/events"
        async with self._client.stream("GET", url) as resp:
            resp.raise_for_status()
            buffer = ""
            async for chunk in resp.aiter_text():
                buffer += chunk
                while "\n\n" in buffer:
                    event_str, buffer = buffer.split("\n\n", 1)
                    if event_str.strip():
                        event = self._parse_sse_event(event_str)
                        if event:
                            yield event

    @staticmethod
    def _parse_sse_event(text: str) -> dict[str, Any] | None:
        event_type = None
        data_lines = []
        for line in text.splitlines():
            if line.startswith("event:"):
                event_type = line[len("event:"):].strip()
            elif line.startswith("data:"):
                data_lines.append(line[len("data:"):].strip())
        if data_lines:
            try:
                data = json.loads("\n".join(data_lines))
                return {"type": event_type, "data": data}
            except json.JSONDecodeError:
                return None
        return None

    async def get_session_status(self, session_id: str) -> dict[str, Any]:
        try:
            session = await self.get_session(session_id)
            return {
                "session_id": session_id,
                "status": session.get("status", "idle"),
                "model": session.get("model", ""),
                "tokens": session.get("tokens", {}),
                "agent": session.get("agent", "build"),
            }
        except Exception:
            return {"session_id": session_id, "status": "error"}

    async def run_custom_command(self, command: str, session_id: str | None = None) -> dict[str, Any]:
        payload = {"command": command}
        if session_id:
            payload["session_id"] = session_id
        resp = await self._post("/api/commands/run", json=payload)
        return resp.json()

from __future__ import annotations

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

    async def _post(self, path: str, json: dict | None = None, **kwargs: Any) -> httpx.Response:
        resp = await self._client.post(path, json=json, **kwargs)
        resp.raise_for_status()
        return resp

    async def _delete(self, path: str, **kwargs: Any) -> httpx.Response:
        resp = await self._client.delete(path, **kwargs)
        resp.raise_for_status()
        return resp

    async def _patch(self, path: str, json: dict | None = None, **kwargs: Any) -> httpx.Response:
        resp = await self._client.patch(path, json=json, **kwargs)
        resp.raise_for_status()
        return resp

    async def health(self) -> dict[str, Any]:
        resp = await self._get("/global/health")
        return resp.json()

    async def get_projects(self) -> list[dict[str, Any]]:
        resp = await self._get("/project")
        data = resp.json()
        return data if isinstance(data, list) else []

    async def get_current_project(self) -> dict[str, Any]:
        resp = await self._get("/project/current")
        return resp.json()

    async def get_sessions(self) -> list[dict[str, Any]]:
        resp = await self._get("/session")
        data = resp.json()
        return data if isinstance(data, list) else []

    async def create_session(
        self,
        title: str | None = None,
        parent_id: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {}
        if title:
            body["title"] = title
        if parent_id:
            body["parentID"] = parent_id
        resp = await self._post("/session", json=body)
        return resp.json()

    async def get_session(self, session_id: str) -> dict[str, Any]:
        resp = await self._get(f"/session/{session_id}")
        return resp.json()

    async def delete_session(self, session_id: str) -> bool:
        resp = await self._delete(f"/session/{session_id}")
        return resp.json()

    async def rename_session(self, session_id: str, title: str) -> dict[str, Any]:
        resp = await self._patch(f"/session/{session_id}", json={"title": title})
        return resp.json()

    async def abort_session(self, session_id: str) -> bool:
        resp = await self._post(f"/session/{session_id}/abort")
        return resp.json()

    async def summarize_session(self, session_id: str) -> bool:
        resp = await self._post(f"/session/{session_id}/summarize", json={})
        return resp.json()

    async def get_session_status(self) -> dict[str, Any]:
        resp = await self._get("/session/status")
        return resp.json()

    async def get_session_todo(self, session_id: str) -> list[dict[str, Any]]:
        resp = await self._get(f"/session/{session_id}/todo")
        data = resp.json()
        return data if isinstance(data, list) else []

    async def get_messages(self, session_id: str, limit: int = 50) -> list[dict[str, Any]]:
        resp = await self._get(f"/session/{session_id}/message", params={"limit": limit})
        data = resp.json()
        return data if isinstance(data, list) else []

    async def send_message(
        self,
        session_id: str,
        message: str,
        model: str | None = None,
        agent: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "parts": [{"type": "text", "text": message}]
        }
        if model:
            body["model"] = model
        if agent:
            body["agent"] = agent
        resp = await self._post(f"/session/{session_id}/message", json=body)
        return resp.json()

    async def send_message_async(
        self,
        session_id: str,
        message: str,
        model: str | None = None,
        agent: str | None = None,
    ) -> None:
        body: dict[str, Any] = {
            "parts": [{"type": "text", "text": message}]
        }
        if model:
            body["model"] = model
        if agent:
            body["agent"] = agent
        await self._post(f"/session/{session_id}/prompt_async", json=body)

    async def get_providers(self) -> dict[str, Any]:
        resp = await self._get("/provider")
        return resp.json()

    async def get_config_providers(self) -> dict[str, Any]:
        resp = await self._get("/config/providers")
        return resp.json()

    async def get_agents(self) -> list[dict[str, Any]]:
        resp = await self._get("/agent")
        data = resp.json()
        return data if isinstance(data, list) else []

    async def get_commands(self) -> list[dict[str, Any]]:
        resp = await self._get("/command")
        data = resp.json()
        return data if isinstance(data, list) else []

    async def run_command(
        self,
        session_id: str,
        command: str,
        arguments: str = "",
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"command": command}
        if arguments:
            body["arguments"] = arguments
        resp = await self._post(f"/session/{session_id}/command", json=body)
        return resp.json()

    async def stream_events(self) -> AsyncGenerator[dict[str, Any], None]:
        async with self._client.stream("GET", "/event") as resp:
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

    async def stream_session_events(self, session_id: str) -> AsyncGenerator[dict[str, Any], None]:
        async for event in self.stream_events():
            data = event.get("data", {})
            props = data.get("properties", {})
            if props.get("sessionID") == session_id:
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

    @staticmethod
    def extract_text_from_response(response: dict[str, Any]) -> str:
        parts = response.get("parts", [])
        text_parts = []
        for part in parts:
            if part.get("type") == "text":
                text_parts.append(part.get("text", ""))
        return "\n".join(text_parts)

    @staticmethod
    def extract_tool_calls(response: dict[str, Any]) -> list[dict[str, Any]]:
        parts = response.get("parts", [])
        tool_calls = []
        for part in parts:
            if part.get("type") == "tool":
                tool_calls.append({
                    "name": part.get("name", part.get("toolName", "unknown")),
                    "input": part.get("input", {}),
                    "status": part.get("status", "unknown"),
                })
        return tool_calls

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class VoiceTranscriber:
    """Transcribe voice messages via a Whisper-compatible API."""

    def __init__(
        self,
        api_url: str = "",
        api_key: str = "",
        model: str = "whisper-large-v3-turbo",
        language: str = "",
    ) -> None:
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.language = language

    @property
    def is_configured(self) -> bool:
        return bool(self.api_url and self.api_key)

    async def transcribe(self, audio_file_path: str) -> str:
        if not self.is_configured:
            return ""

        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        data: dict[str, Any] = {"model": self.model}
        if self.language:
            data["language"] = self.language

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                with open(audio_file_path, "rb") as f:
                    files = {"file": f}
                    resp = await client.post(
                        f"{self.api_url}/audio/transcriptions",
                        headers=headers,
                        data=data,
                        files=files,
                    )
                resp.raise_for_status()
                result = resp.json()
                return result.get("text", "")
        except Exception as e:
            logger.error("Voice transcription failed: %s", e)
            return ""


class TextToSpeech:
    """Generate speech via an OpenAI-compatible TTS API."""

    def __init__(
        self,
        api_url: str = "",
        api_key: str = "",
        model: str = "gpt-4o-mini-tts",
        voice: str = "alloy",
    ) -> None:
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.voice = voice

    @property
    def is_configured(self) -> bool:
        return bool(self.api_url and self.api_key)

    async def synthesize(self, text: str) -> bytes | None:
        if not self.is_configured:
            return None

        headers = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "model": self.model,
            "input": text,
            "voice": self.voice,
        }

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"{self.api_url}/audio/speech",
                    headers=headers,
                    json=payload,
                )
                resp.raise_for_status()
                return resp.content
        except Exception as e:
            logger.error("TTS synthesis failed: %s", e)
            return None

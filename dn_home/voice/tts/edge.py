"""Microsoft Edge online TTS adapter."""

from __future__ import annotations

import logging
from pathlib import Path
import tempfile
import time

import edge_tts

from dn_home.voice.models import AudioAsset, Voice
from dn_home.voice.tts.base import TTSEngine, TTSError


LOGGER = logging.getLogger(__name__)


class EdgeTTSEngine(TTSEngine):
    def __init__(self, default_voice: str, *, rate: str = "+0%", pitch: str = "+0Hz"):
        self.default_voice = default_voice
        self.rate = rate
        self.pitch = pitch

    async def list_voices(self, language: str | None = None) -> list[Voice]:
        try:
            raw_voices = await edge_tts.list_voices()
        except Exception as error:  # edge-tts exposes transport-specific exceptions
            raise TTSError(f"Unable to retrieve Edge TTS voices: {error}") from error
        voices = [
            Voice(
                name=str(item.get("ShortName", "")),
                locale=str(item.get("Locale", "")),
                gender=str(item.get("Gender", "unknown")),
            )
            for item in raw_voices
            if item.get("ShortName")
            and (not language or str(item.get("Locale", "")).casefold() == language.casefold())
        ]
        return sorted(voices, key=lambda item: item.name)

    async def generate(self, text: str, voice: str | None = None) -> AudioAsset:
        clean_text = text.strip()
        if not clean_text:
            raise TTSError("Speech text cannot be empty")
        selected_voice = voice or self.default_voice
        temporary_directory = Path(tempfile.mkdtemp(prefix="dn_home_tts_"))
        output = temporary_directory / "speech.tts.mp3"
        started = time.monotonic()
        try:
            communicate = edge_tts.Communicate(
                clean_text,
                selected_voice,
                rate=self.rate,
                pitch=self.pitch,
            )
            await communicate.save(str(output))
            if not output.is_file() or output.stat().st_size == 0:
                raise TTSError("Edge TTS returned an empty audio file")
            output.chmod(0o600)
        except Exception as error:  # cleanup must happen for all provider failures
            AudioAsset(output, "audio/mpeg", temporary_directory).cleanup()
            if isinstance(error, TTSError):
                raise
            raise TTSError(f"Edge TTS generation failed: {error}") from error
        LOGGER.info(
            "event=tts.generated engine=edge voice=%s bytes=%d "
            "tts_generation_ms=%d result=success",
            selected_voice,
            output.stat().st_size,
            round((time.monotonic() - started) * 1000),
        )
        return AudioAsset(output, "audio/mpeg", temporary_directory)

"""Text-to-speech interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

from dn_home.voice.models import AudioAsset, Voice


class TTSError(RuntimeError):
    """Raised when speech synthesis fails."""


class TTSEngine(ABC):
    @abstractmethod
    async def list_voices(self, language: str | None = None) -> list[Voice]:
        """Return available voices, optionally restricted by locale."""

    @abstractmethod
    async def generate(self, text: str, voice: str | None = None) -> AudioAsset:
        """Generate a temporary audio asset."""


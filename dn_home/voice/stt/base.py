"""Speech-to-text contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


class STTError(RuntimeError):
    """Raised when local transcription fails."""


@dataclass(frozen=True, slots=True)
class Transcript:
    text: str
    language: str
    duration_ms: int


class STTEngine(ABC):
    @abstractmethod
    def transcribe(self, pcm: bytes, sample_rate: int) -> Transcript:
        """Transcribe one utterance locally."""

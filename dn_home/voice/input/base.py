"""Audio input contracts."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Iterator


class AudioInputError(RuntimeError):
    """Raised when microphone capture cannot continue."""


@dataclass(frozen=True, slots=True)
class AudioFrame:
    pcm: bytes
    sample_rate: int
    channels: int


class AudioInput(ABC):
    @abstractmethod
    def frames(self) -> Iterator[AudioFrame]:
        """Yield bounded PCM frames until the source is closed."""

    @abstractmethod
    def close(self) -> None:
        """Stop capture and release the audio device."""

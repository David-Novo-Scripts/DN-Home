"""Wake-word engine contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


class WakeWordError(RuntimeError):
    """Raised when wake-word inference fails."""


@dataclass(frozen=True, slots=True)
class WakeWordDetection:
    detected: bool
    score: float
    name: str


class WakeWordEngine(ABC):
    @abstractmethod
    def process(self, pcm: bytes) -> WakeWordDetection:
        """Process mono 16 kHz PCM without retaining it."""

    @abstractmethod
    def reset(self) -> None:
        """Clear temporal state before returning to WAIT_WAKE."""

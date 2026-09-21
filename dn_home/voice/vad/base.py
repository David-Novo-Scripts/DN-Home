"""Voice activity detection contract."""

from __future__ import annotations

from abc import ABC, abstractmethod


class VoiceActivityDetector(ABC):
    @abstractmethod
    def probability(self, pcm: bytes) -> float:
        """Return speech probability for mono 16 kHz PCM."""

    @abstractmethod
    def reset(self) -> None:
        """Clear temporal state."""

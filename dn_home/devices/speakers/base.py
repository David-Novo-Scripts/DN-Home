"""Speaker interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from dn_home.voice.models import AudioAsset


class SpeakerError(RuntimeError):
    """Raised when a speaker operation fails."""


@dataclass(frozen=True, slots=True)
class PlaybackResult:
    device_name: str
    completed: bool
    media_fetched: bool


class Speaker(ABC):
    @abstractmethod
    def speak(
        self,
        asset: AudioAsset,
        *,
        volume: int,
        restore_previous_volume: bool,
    ) -> PlaybackResult:
        """Play a generated audio asset."""


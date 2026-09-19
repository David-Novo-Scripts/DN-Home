"""Speaker interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from dn_home.voice.models import AudioAsset


class SpeakerError(RuntimeError):
    """Raised when a speaker operation fails."""


@dataclass(frozen=True, slots=True)
class PlaybackMetrics:
    http_server_start_ms: int
    cast_connection_ms: int
    receiver_launch_ms: int
    play_media_to_http_get_ms: int
    http_get_to_playback_started_ms: int
    audio_started_at: float


@dataclass(frozen=True, slots=True)
class PlaybackResult:
    device_name: str
    completed: bool
    media_fetched: bool
    metrics: PlaybackMetrics


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

from pathlib import Path
import threading
import time
from types import SimpleNamespace

import pytest

from dn_home.core.config import HttpConfig, NetworkConfig, SpeakerConfig
from dn_home.core.network import NetworkSelection
from dn_home.devices.speakers import cast as cast_module
from dn_home.devices.speakers.cast import CastDeviceInfo, CastSpeaker
from dn_home.voice.models import AudioAsset


class FakeMediaController:
    def __init__(self):
        self.status = SimpleNamespace(player_state="IDLE")
        self.played_url = None

    def play_media(self, url, content_type, **options):
        self.played_url = url
        server = FakeAudioServer.active
        assert server is not None
        server.request_started_at = time.monotonic()
        server.request_started.set()
        server.request_completed.set()

    def block_until_active(self, timeout=None):
        self.status.player_state = "PLAYING"

    def stop(self):
        self.status.player_state = "IDLE"


class FakeCast:
    def __init__(self):
        self.status = SimpleNamespace(volume_level=0.2)
        self.media_controller = FakeMediaController()
        self.volumes = []
        self.disconnected = False

    def set_volume(self, volume, timeout=None):
        self.volumes.append(volume)

    def disconnect(self, timeout=None):
        self.disconnected = True


class FakeAudioServer:
    active = None

    def __init__(self, asset, bind_host, port=0):
        self.url = f"http://{bind_host}:12345/secret.mp3"
        self.sanitized_url = f"http://{bind_host}:12345/<redacted>.mp3"
        self.request_started = threading.Event()
        self.request_completed = threading.Event()
        self.request_started_at = None

    def __enter__(self):
        FakeAudioServer.active = self
        return self

    def __exit__(self, *args):
        FakeAudioServer.active = None
        return None


def _speaker() -> CastSpeaker:
    return CastSpeaker(
        SpeakerConfig(
            provider="cast",
            name="Bedroom",
            host="192.168.20.40",
            port=8009,
            volume=35,
            restore_previous_volume=True,
            connect_timeout=2,
            playback_timeout=5,
        ),
        NetworkConfig(None, None),
        HttpConfig(0, 2),
    )


def test_speak_restores_volume_and_disconnects(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    speaker = _speaker()
    fake_cast = FakeCast()
    device = CastDeviceInfo("Bedroom", "Nest Mini", "Google", "192.168.20.40", 8009)
    monkeypatch.setattr(cast_module, "TemporaryAudioServer", FakeAudioServer)
    monkeypatch.setattr(
        speaker,
        "select_network",
        lambda: NetworkSelection("192.168.20.10", "br0", "192.168.20.40", "route"),
    )
    monkeypatch.setattr(speaker, "_connect", lambda: (fake_cast, device))
    monkeypatch.setattr(
        speaker, "_wait_for_completion", lambda cast, started: time.monotonic()
    )
    path = tmp_path / "speech.tts.mp3"
    path.write_bytes(b"ID3")

    result = speaker.speak(
        AudioAsset(path, "audio/mpeg"),
        volume=35,
        restore_previous_volume=True,
    )

    assert result.completed is True
    assert fake_cast.volumes == [0.35, 0.2]
    assert fake_cast.disconnected is True
    assert fake_cast.media_controller.played_url.endswith("/secret.mp3")
    assert result.metrics.http_server_start_ms >= 0
    assert result.metrics.cast_connection_ms >= 0
    assert result.metrics.receiver_launch_ms >= 0


def test_volume_restore_can_be_disabled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    speaker = _speaker()
    fake_cast = FakeCast()
    device = CastDeviceInfo("Bedroom", "Nest Mini", "Google", "192.168.20.40", 8009)
    monkeypatch.setattr(cast_module, "TemporaryAudioServer", FakeAudioServer)
    monkeypatch.setattr(
        speaker,
        "select_network",
        lambda: NetworkSelection("192.168.20.10", "br0", "192.168.20.40", "route"),
    )
    monkeypatch.setattr(speaker, "_connect", lambda: (fake_cast, device))
    monkeypatch.setattr(
        speaker, "_wait_for_completion", lambda cast, started: time.monotonic()
    )
    path = tmp_path / "speech.tts.mp3"
    path.write_bytes(b"ID3")

    speaker.speak(
        AudioAsset(path, "audio/mpeg"),
        volume=40,
        restore_previous_volume=False,
    )

    assert fake_cast.volumes == [0.4]

import logging
import re
import time
from types import SimpleNamespace

import pytest

from dn_home import cli
from dn_home.devices.speakers.base import PlaybackMetrics, PlaybackResult


class FakeAsset:
    def __init__(self) -> None:
        self.cleaned = False

    def cleanup(self) -> None:
        self.cleaned = True


class FakeTTSEngine:
    asset = FakeAsset()
    options = None

    def __init__(self, *args, **kwargs) -> None:
        FakeTTSEngine.options = kwargs

    async def generate(self, text, voice):
        return self.asset


class FakeSpeaker:
    def __init__(self, *args, **kwargs) -> None:
        pass

    def speak(self, asset, *, volume, restore_previous_volume):
        return PlaybackResult(
            device_name="Bedroom",
            completed=True,
            media_fetched=True,
            metrics=PlaybackMetrics(
                http_server_start_ms=2,
                cast_connection_ms=500,
                receiver_launch_ms=300,
                play_media_to_http_get_ms=100,
                http_get_to_playback_started_ms=200,
                audio_started_at=time.monotonic(),
            ),
        )


@pytest.mark.parametrize(
    ("rate", "pitch", "expected_options"),
    (
        ("+8%", "-5Hz", {"rate": "+8%", "pitch": "-5Hz"}),
        (None, None, {"rate": "+0%", "pitch": "+0Hz"}),
    ),
)
@pytest.mark.asyncio
async def test_speak_logs_latency_to_audio_start(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    rate: str | None,
    pitch: str | None,
    expected_options: dict[str, str],
) -> None:
    async def run_directly(function, *args, **kwargs):
        return function(*args, **kwargs)

    monkeypatch.setattr(cli, "EdgeTTSEngine", FakeTTSEngine)
    monkeypatch.setattr(cli, "CastSpeaker", FakeSpeaker)
    monkeypatch.setattr(cli.asyncio, "to_thread", run_directly)
    args = SimpleNamespace(
        text=["Olá"],
        voice=None,
        rate=rate,
        pitch=pitch,
        volume=None,
        restore_volume=None,
    )
    config = SimpleNamespace(
        voice=SimpleNamespace(
            default_voice="pt-PT-DuarteNeural", rate="+0%", pitch="+0Hz"
        ),
        speaker=SimpleNamespace(volume=35, restore_previous_volume=True),
        network=SimpleNamespace(),
        http=SimpleNamespace(),
    )

    with caplog.at_level(logging.INFO):
        result = await cli._speak(args, config)

    assert result == 0
    assert FakeTTSEngine.asset.cleaned is True
    assert FakeTTSEngine.options == expected_options
    latency_log = next(
        record.getMessage()
        for record in caplog.records
        if "event=speech.latency" in record.getMessage()
    )
    assert "tts_generation_ms=" in latency_log
    assert "http_server_start_ms=2" in latency_log
    assert "cast_connection_ms=500" in latency_log
    assert "receiver_launch_ms=300" in latency_log
    assert "play_media_to_http_get_ms=100" in latency_log
    assert "http_get_to_playback_started_ms=200" in latency_log
    total_match = re.search(r"total_text_to_audio_started_ms=(\d+)", latency_log)
    assert total_match is not None and int(total_match.group(1)) >= 0


def test_speak_parser_keeps_existing_command_compatible() -> None:
    args = cli._parser().parse_args(["speak", "Bem-vindo a casa David."])

    assert args.rate is None
    assert args.pitch is None


def test_speak_parser_accepts_prosody_overrides() -> None:
    args = cli._parser().parse_args(
        [
            "speak",
            "--rate",
            "+8%",
            "--pitch=-5Hz",
            "Bem-vindo a casa David.",
        ]
    )

    assert args.rate == "+8%"
    assert args.pitch == "-5Hz"


@pytest.mark.parametrize(
    "options",
    (("--rate", "8%"), ("--pitch", "+5"), ("--pitch=low",)),
)
def test_speak_parser_rejects_invalid_prosody(options: tuple[str, ...]) -> None:
    with pytest.raises(SystemExit) as error:
        cli._parser().parse_args(["speak", *options, "Teste"])

    assert error.value.code == 2

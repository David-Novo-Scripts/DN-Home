from pathlib import Path

import pytest

from dn_home.voice.tts import edge
from dn_home.voice.tts.base import TTSError


class FakeCommunicate:
    last_options = None

    def __init__(self, text: str, voice: str, **options: str):
        self.text = text
        self.voice = voice
        self.options = options
        FakeCommunicate.last_options = options

    async def save(self, target: str) -> None:
        Path(target).write_bytes(b"ID3fake-mp3")


@pytest.mark.asyncio
async def test_generates_and_cleans_temporary_audio(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(edge.edge_tts, "Communicate", FakeCommunicate)
    engine = edge.EdgeTTSEngine("pt-PT-DuarteNeural")

    asset = await engine.generate("Olá David")

    directory = asset.temporary_directory
    assert asset.path.read_bytes() == b"ID3fake-mp3"
    assert directory is not None and directory.is_dir()
    asset.cleanup()
    assert not directory.exists()


@pytest.mark.asyncio
async def test_passes_rate_and_pitch_to_edge_tts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(edge.edge_tts, "Communicate", FakeCommunicate)
    engine = edge.EdgeTTSEngine(
        "pt-PT-DuarteNeural", rate="+8%", pitch="-5Hz"
    )

    asset = await engine.generate("Olá David")
    try:
        assert FakeCommunicate.last_options == {"rate": "+8%", "pitch": "-5Hz"}
    finally:
        asset.cleanup()


@pytest.mark.asyncio
async def test_rejects_empty_text() -> None:
    engine = edge.EdgeTTSEngine("pt-PT-DuarteNeural")

    with pytest.raises(TTSError, match="cannot be empty"):
        await engine.generate("  ")


@pytest.mark.asyncio
async def test_filters_voices_by_locale(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_list_voices():
        return [
            {"ShortName": "pt-PT-DuarteNeural", "Locale": "pt-PT", "Gender": "Male"},
            {"ShortName": "en-GB-SoniaNeural", "Locale": "en-GB", "Gender": "Female"},
        ]

    monkeypatch.setattr(edge.edge_tts, "list_voices", fake_list_voices)
    engine = edge.EdgeTTSEngine("pt-PT-DuarteNeural")

    voices = await engine.list_voices("pt-PT")

    assert [voice.name for voice in voices] == ["pt-PT-DuarteNeural"]

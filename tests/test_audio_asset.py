from pathlib import Path

from dn_home.voice.models import AudioAsset


def test_cleanup_removes_private_directory(tmp_path: Path) -> None:
    directory = tmp_path / "generated"
    directory.mkdir()
    path = directory / "speech.tts.mp3"
    path.write_bytes(b"ID3")

    AudioAsset(path, "audio/mpeg", directory).cleanup()

    assert not directory.exists()


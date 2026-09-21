from pathlib import Path
from types import SimpleNamespace

from dn_home.core.config import SttConfig
from dn_home.voice.stt.whisper_cpp import WhisperCppEngine


def test_transcription_uses_private_temporary_wav_and_removes_it(
    tmp_path: Path, monkeypatch
) -> None:
    binary = tmp_path / "whisper-cli"
    model = tmp_path / "model.bin"
    binary.write_bytes(b"binary")
    model.write_bytes(b"model")
    config = SttConfig("whisper_cpp", binary, model, "pt", 4, "Jarvis, RER")
    observed: dict[str, object] = {}

    def fake_run(command, **kwargs):
        wav_path = Path(command[command.index("--file") + 1])
        observed["path"] = wav_path
        observed["mode"] = wav_path.stat().st_mode & 0o777
        observed["header"] = wav_path.read_bytes()[:4]
        return SimpleNamespace(returncode=0, stdout=" próximo RER para Paris ", stderr="")

    monkeypatch.setattr("dn_home.voice.stt.whisper_cpp.subprocess.run", fake_run)
    result = WhisperCppEngine(config).transcribe(bytes(3_200), 16_000)

    assert result.text == "próximo RER para Paris"
    assert observed["mode"] == 0o600
    assert observed["header"] == b"RIFF"
    assert not Path(observed["path"]).exists()

"""Local whisper.cpp speech-to-text adapter."""

from __future__ import annotations

import subprocess
import tempfile
import wave
from pathlib import Path

from dn_home.core.config import SttConfig
from dn_home.voice.stt.base import STTEngine, STTError, Transcript


class WhisperCppEngine(STTEngine):
    def __init__(self, config: SttConfig) -> None:
        self.config = config
        if not config.binary_path.is_file():
            raise STTError(f"whisper.cpp executable not found: {config.binary_path}")
        if not config.model_path.is_file():
            raise STTError(f"Whisper model not found: {config.model_path}")

    def transcribe(self, pcm: bytes, sample_rate: int) -> Transcript:
        if sample_rate != 16_000:
            raise STTError("whisper.cpp adapter expects 16 kHz PCM")
        if not pcm:
            return Transcript("", self.config.language, 0)
        duration_ms = len(pcm) // 2 * 1000 // sample_rate
        path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                prefix="dn-home-stt-", suffix=".wav", delete=False
            ) as temporary:
                path = Path(temporary.name)
            path.chmod(0o600)
            with wave.open(str(path), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(sample_rate)
                wav.writeframes(pcm)
            command = [
                str(self.config.binary_path),
                "--model",
                str(self.config.model_path),
                "--file",
                str(path),
                "--language",
                self.config.language,
                "--threads",
                str(self.config.threads),
                "--no-gpu",
                "--no-prints",
                "--no-timestamps",
            ]
            if self.config.prompt:
                command.extend(["--prompt", self.config.prompt])
            result = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=180,
            )
            if result.returncode != 0:
                detail = result.stderr.strip().splitlines()[-1:] or ["unknown error"]
                raise STTError(f"whisper.cpp failed: {detail[0]}")
            text = " ".join(result.stdout.strip().split())
            return Transcript(text, self.config.language, duration_ms)
        except subprocess.TimeoutExpired as error:
            raise STTError("whisper.cpp transcription timed out") from error
        except OSError as error:
            raise STTError(f"Unable to run whisper.cpp: {error}") from error
        finally:
            if path is not None:
                path.unlink(missing_ok=True)

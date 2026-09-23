"""ALSA microphone capture through the system ``arecord`` utility."""

from __future__ import annotations

from array import array
from dataclasses import dataclass
import math
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import wave
from pathlib import Path
from typing import BinaryIO

from dn_home.core.config import AudioInputConfig
from dn_home.voice.input.base import AudioFrame, AudioInput, AudioInputError


@dataclass(frozen=True, slots=True)
class MicrophoneTestResult:
    duration_seconds: float
    frames: int
    samples: int
    peak: int
    rms: int
    full_scale_samples: int
    clipping_percent: float
    max_full_scale_run: int
    initial_window_rms: int
    final_window_rms: int
    silence_threshold_rms: int
    leading_silence_ms: int
    trailing_silence_ms: int
    temporary_file_removed: bool


def _arecord_path() -> str:
    executable = shutil.which("arecord")
    if executable is None:
        raise AudioInputError("arecord is not installed or is not on PATH")
    return executable


def list_alsa_devices() -> tuple[str, str]:
    """Return ALSA hardware and PCM listings without opening a capture device."""

    executable = _arecord_path()
    outputs: list[str] = []
    for flag in ("-l", "-L"):
        result = subprocess.run(
            [executable, flag],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        detail = (result.stdout or result.stderr).strip()
        if result.returncode != 0:
            raise AudioInputError(f"arecord {flag} failed: {detail}")
        outputs.append(detail)
    return outputs[0], outputs[1]


class AlsaArecordSource(AudioInput):
    """Stream bounded raw PCM frames from one explicitly configured ALSA PCM."""

    def __init__(self, config: AudioInputConfig) -> None:
        if config.sample_format != "S16_LE":
            raise AudioInputError("The ALSA PoC currently requires sample_format S16_LE")
        self.config = config
        self._process: subprocess.Popen[bytes] | None = None
        self._closed = False

    @property
    def frame_bytes(self) -> int:
        samples = self.config.sample_rate * self.config.frame_ms // 1000
        return samples * self.config.channels * 2

    def _start(self) -> subprocess.Popen[bytes]:
        if self._closed:
            raise AudioInputError("Microphone source is already closed")
        if self._process is None:
            command = [
                _arecord_path(),
                "-q",
                "-D",
                self.config.device,
                "-t",
                "raw",
                "-f",
                self.config.sample_format,
                "-r",
                str(self.config.sample_rate),
                "-c",
                str(self.config.channels),
            ]
            try:
                self._process = subprocess.Popen(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    start_new_session=True,
                )
            except OSError as error:
                raise AudioInputError(f"Unable to start arecord: {error}") from error
        return self._process

    @staticmethod
    def _read_exact(stream: BinaryIO, count: int) -> bytes:
        chunks: list[bytes] = []
        remaining = count
        while remaining:
            chunk = stream.read(remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def frames(self):
        process = self._start()
        if process.stdout is None:
            raise AudioInputError("arecord did not provide a PCM stream")
        while not self._closed:
            pcm = self._read_exact(process.stdout, self.frame_bytes)
            if len(pcm) == self.frame_bytes:
                yield AudioFrame(pcm, self.config.sample_rate, self.config.channels)
                continue
            if self._closed:
                return
            error = ""
            if process.stderr is not None:
                error = process.stderr.read().decode("utf-8", errors="replace").strip()
            raise AudioInputError(
                f"arecord stopped unexpectedly with code {process.poll()}: {error}"
            )

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        process = self._process
        if process is None:
            return
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=1)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                if process.poll() is None:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    process.wait(timeout=1)
        if process.stdout is not None:
            process.stdout.close()
        if process.stderr is not None:
            process.stderr.close()
        self._process = None

    def __enter__(self) -> "AlsaArecordSource":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()


def test_microphone(config: AudioInputConfig, seconds: float) -> MicrophoneTestResult:
    """Capture a bounded diagnostic WAV and always remove it before returning."""

    if not 0.1 <= seconds <= 30:
        raise AudioInputError("Microphone test duration must be between 0.1 and 30 seconds")
    target_frames = math.ceil(seconds * 1000 / config.frame_ms)
    samples = array("h")
    frame_count = 0
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix="dn-home-mic-", suffix=".wav", delete=False
        ) as temporary:
            temporary_path = Path(temporary.name)
        with AlsaArecordSource(config) as source, wave.open(str(temporary_path), "wb") as wav:
            wav.setnchannels(config.channels)
            wav.setsampwidth(2)
            wav.setframerate(config.sample_rate)
            for frame in source.frames():
                wav.writeframesraw(frame.pcm)
                chunk = array("h")
                chunk.frombytes(frame.pcm)
                if sys.byteorder != "little":
                    chunk.byteswap()
                samples.extend(chunk)
                frame_count += 1
                if frame_count >= target_frames:
                    break
        peak = max((abs(value) for value in samples), default=0)
        square_sum = sum(value * value for value in samples)
        rms = int(math.sqrt(square_sum / len(samples))) if samples else 0
        full_scale = [value in (-32_768, 32_767) for value in samples]
        full_scale_samples = sum(full_scale)
        max_full_scale_run = 0
        current_run = 0
        for clipped in full_scale:
            current_run = current_run + 1 if clipped else 0
            max_full_scale_run = max(max_full_scale_run, current_run)

        samples_per_second = config.sample_rate * config.channels
        analysis_window = min(len(samples) // 4, samples_per_second)

        def window_rms(values: array) -> int:
            if not values:
                return 0
            return int(math.sqrt(sum(value * value for value in values) / len(values)))

        initial_window_rms = window_rms(samples[:analysis_window])
        final_window_rms = window_rms(samples[-analysis_window:])
        silence_threshold_rms = max(
            150, int(min(initial_window_rms, final_window_rms) * 2.5)
        )
        energy_frame_samples = max(1, samples_per_second // 50)
        frame_rms_values = [
            window_rms(samples[offset : offset + energy_frame_samples])
            for offset in range(0, len(samples), energy_frame_samples)
        ]

        def silence_frames_before_speech(values: list[int]) -> int:
            for index in range(max(0, len(values) - 2)):
                if all(
                    value > silence_threshold_rms
                    for value in values[index : index + 3]
                ):
                    return index
            return len(values)

        leading_frames = silence_frames_before_speech(frame_rms_values)
        trailing_frames = silence_frames_before_speech(list(reversed(frame_rms_values)))
        audio_duration = len(samples) / samples_per_second if samples_per_second else 0
        clipping_percent = (
            full_scale_samples / len(samples) * 100 if samples else 0.0
        )
        return MicrophoneTestResult(
            duration_seconds=audio_duration,
            frames=frame_count,
            samples=len(samples),
            peak=peak,
            rms=rms,
            full_scale_samples=full_scale_samples,
            clipping_percent=clipping_percent,
            max_full_scale_run=max_full_scale_run,
            initial_window_rms=initial_window_rms,
            final_window_rms=final_window_rms,
            silence_threshold_rms=silence_threshold_rms,
            leading_silence_ms=leading_frames * 20,
            trailing_silence_ms=trailing_frames * 20,
            temporary_file_removed=True,
        )
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)

"""Bounded in-memory utterance capture driven by voice activity."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Iterator

from dn_home.core.config import VadConfig
from dn_home.voice.input.base import AudioFrame
from dn_home.voice.vad.base import VoiceActivityDetector


@dataclass(frozen=True, slots=True)
class CapturedUtterance:
    pcm: bytes
    speech_detected: bool
    reason: str
    duration_ms: int


class UtteranceCapture:
    """Capture one phrase in RAM and stop at silence, timeout, or max duration."""

    SAMPLE_RATE = 16_000
    VAD_FRAME_SAMPLES = 480
    VAD_FRAME_MS = 30

    def __init__(self, detector: VoiceActivityDetector, config: VadConfig) -> None:
        self.detector = detector
        self.config = config

    def capture(self, frames: Iterator[AudioFrame]) -> CapturedUtterance:
        self.detector.reset()
        pre_roll_count = max(1, (self.config.pre_roll_ms + 29) // 30)
        pre_roll: deque[bytes] = deque(maxlen=pre_roll_count)
        raw = bytearray()
        utterance = bytearray()
        speech_started = False
        silence_ms = 0
        elapsed_ms = 0
        vad_bytes = self.VAD_FRAME_SAMPLES * 2

        for frame in frames:
            if frame.sample_rate != self.SAMPLE_RATE or frame.channels != 1:
                raise ValueError("Utterance capture requires 16 kHz mono PCM")
            raw.extend(frame.pcm)
            while len(raw) >= vad_bytes:
                chunk = bytes(raw[:vad_bytes])
                del raw[:vad_bytes]
                elapsed_ms += self.VAD_FRAME_MS
                speech = self.detector.probability(chunk) >= self.config.threshold
                if not speech_started:
                    pre_roll.append(chunk)
                    if speech:
                        speech_started = True
                        utterance.extend(b"".join(pre_roll))
                        silence_ms = 0
                    elif elapsed_ms >= self.config.speech_start_timeout * 1000:
                        return CapturedUtterance(b"", False, "speech_start_timeout", 0)
                else:
                    utterance.extend(chunk)
                    silence_ms = 0 if speech else silence_ms + self.VAD_FRAME_MS
                    duration_ms = len(utterance) // 2 * 1000 // self.SAMPLE_RATE
                    if silence_ms >= self.config.end_silence_ms:
                        return CapturedUtterance(
                            bytes(utterance), True, "end_silence", duration_ms
                        )
                    if duration_ms >= self.config.max_utterance_seconds * 1000:
                        return CapturedUtterance(
                            bytes(utterance), True, "max_duration", duration_ms
                        )
        duration_ms = len(utterance) // 2 * 1000 // self.SAMPLE_RATE
        return CapturedUtterance(
            bytes(utterance), speech_started, "source_ended", duration_ms
        )

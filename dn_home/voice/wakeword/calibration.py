"""Interactive, in-memory wake-word calibration helpers."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import resource
import time
from typing import Callable

from dn_home.voice.input.base import AudioInput
from dn_home.voice.vad.base import VoiceActivityDetector
from dn_home.voice.wakeword.base import WakeWordEngine


@dataclass(frozen=True, slots=True)
class WakeAttempt:
    number: int
    score: float
    detected: bool
    detection_latency_ms: int | None
    speech_duration_ms: int


@dataclass(frozen=True, slots=True)
class WakeCalibrationResult:
    attempts: tuple[WakeAttempt, ...]
    wall_seconds: float
    cpu_percent: float
    peak_rss_mib: float


def calibrate_wakeword(
    *,
    audio: AudioInput,
    engine: WakeWordEngine,
    vad: VoiceActivityDetector,
    threshold: float,
    attempt_count: int,
    timeout_seconds: float,
    on_attempt: Callable[[WakeAttempt], None] | None = None,
) -> WakeCalibrationResult:
    """Segment deliberate utterances with VAD and score each without saving PCM."""

    wake_bytes = 1_280 * 2
    vad_bytes = 480 * 2
    wake_buffer = bytearray()
    vad_buffer = bytearray()
    recent_scores: deque[tuple[float, float]] = deque(maxlen=8)
    attempts: list[WakeAttempt] = []
    speech_active = False
    speech_candidate_ms = 0
    silence_ms = 0
    speech_started_at = 0.0
    max_score = 0.0
    detection_latency_ms: int | None = None
    started = time.monotonic()
    cpu_started = time.process_time()
    deadline = started + timeout_seconds
    engine.reset()
    vad.reset()

    try:
        for frame in audio.frames():
            now = time.monotonic()
            if now >= deadline or len(attempts) >= attempt_count:
                break
            wake_buffer.extend(frame.pcm)
            vad_buffer.extend(frame.pcm)

            while len(wake_buffer) >= wake_bytes:
                chunk = bytes(wake_buffer[:wake_bytes])
                del wake_buffer[:wake_bytes]
                detection = engine.process(chunk)
                prediction_at = time.monotonic()
                recent_scores.append((prediction_at, detection.score))
                if speech_active:
                    max_score = max(max_score, detection.score)
                    if detection.detected and detection_latency_ms is None:
                        detection_latency_ms = max(
                            0, round((prediction_at - speech_started_at) * 1000)
                        )

            while len(vad_buffer) >= vad_bytes:
                chunk = bytes(vad_buffer[:vad_bytes])
                del vad_buffer[:vad_bytes]
                speech_probability = vad.probability(chunk)
                is_speech = speech_probability >= threshold
                now = time.monotonic()

                if not speech_active:
                    speech_candidate_ms = speech_candidate_ms + 30 if is_speech else 0
                    if speech_candidate_ms >= 60:
                        speech_active = True
                        speech_started_at = now - speech_candidate_ms / 1000
                        silence_ms = 0
                        recent = [
                            (when, score)
                            for when, score in recent_scores
                            if when >= speech_started_at - 0.24
                        ]
                        max_score = max((score for _, score in recent), default=0.0)
                        detected_times = [
                            when for when, score in recent if score >= threshold
                        ]
                        detection_latency_ms = (
                            max(0, round((detected_times[0] - speech_started_at) * 1000))
                            if detected_times
                            else None
                        )
                    continue

                silence_ms = 0 if is_speech else silence_ms + 30
                if silence_ms < 600:
                    continue

                speech_ended_at = now - silence_ms / 1000
                attempt = WakeAttempt(
                    number=len(attempts) + 1,
                    score=max_score,
                    detected=detection_latency_ms is not None,
                    detection_latency_ms=detection_latency_ms,
                    speech_duration_ms=max(
                        0, round((speech_ended_at - speech_started_at) * 1000)
                    ),
                )
                attempts.append(attempt)
                if on_attempt is not None:
                    on_attempt(attempt)
                speech_active = False
                speech_candidate_ms = 0
                silence_ms = 0
                max_score = 0.0
                detection_latency_ms = None
                recent_scores.clear()
    finally:
        audio.close()

    wall_seconds = time.monotonic() - started
    cpu_seconds = time.process_time() - cpu_started
    return WakeCalibrationResult(
        attempts=tuple(attempts),
        wall_seconds=wall_seconds,
        cpu_percent=cpu_seconds / wall_seconds * 100 if wall_seconds else 0.0,
        peak_rss_mib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
    )

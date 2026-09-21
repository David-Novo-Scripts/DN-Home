"""Silero VAD adapter using the ONNX model shipped for the voice PoC."""

from __future__ import annotations

import os
from pathlib import Path

from dn_home.voice.vad.base import VoiceActivityDetector


class SileroVoiceActivityDetector(VoiceActivityDetector):
    def __init__(self, model_path: Path) -> None:
        if not model_path.is_file():
            raise RuntimeError(f"Silero VAD model not found: {model_path}")
        os.environ.setdefault("ORT_DISABLE_TELEMETRY", "1")
        import numpy as np
        import onnxruntime as ort

        ort.disable_telemetry_events()
        from openwakeword.vad import VAD

        self._np = np
        self._vad = VAD(model_path=str(model_path), n_threads=1)

    def probability(self, pcm: bytes) -> float:
        if len(pcm) != 960:
            raise ValueError("Silero VAD expects exactly 30 ms of 16 kHz S16_LE mono PCM")
        samples = self._np.frombuffer(pcm, dtype=self._np.int16)
        return float(self._vad.predict(samples, frame_size=480))

    def reset(self) -> None:
        self._vad.reset_states()
        self._vad.prediction_buffer.clear()

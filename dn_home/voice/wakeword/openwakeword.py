"""Local openWakeWord ONNX adapter."""

from __future__ import annotations

import os
from pathlib import Path

from dn_home.core.config import WakeWordConfig
from dn_home.voice.wakeword.base import (
    WakeWordDetection,
    WakeWordEngine,
    WakeWordError,
)


class OpenWakeWordEngine(WakeWordEngine):
    """Run a single configured wake-word model entirely on the local CPU."""

    def __init__(self, config: WakeWordConfig) -> None:
        model_path = config.model_path
        if not model_path.is_file():
            raise WakeWordError(f"Wake-word model not found: {model_path}")
        model_dir = model_path.parent
        feature_paths = {
            "melspec_model_path": model_dir / "melspectrogram.onnx",
            "embedding_model_path": model_dir / "embedding_model.onnx",
        }
        missing = [str(path) for path in feature_paths.values() if not path.is_file()]
        if missing:
            raise WakeWordError("Missing openWakeWord feature model(s): " + ", ".join(missing))
        try:
            os.environ.setdefault("ORT_DISABLE_TELEMETRY", "1")
            import numpy as np
            import onnxruntime as ort

            ort.disable_telemetry_events()
            from openwakeword.model import Model
            from openwakeword.vad import VAD

            self._np = np
            self._model = Model(
                wakeword_models=[str(model_path)],
                inference_framework="onnx",
                vad_threshold=0,
                melspec_model_path=str(feature_paths["melspec_model_path"]),
                embedding_model_path=str(feature_paths["embedding_model_path"]),
                ncpu=1,
            )
            if config.vad_threshold > 0:
                vad_path = model_dir / "silero_vad.onnx"
                if not vad_path.is_file():
                    raise WakeWordError(f"Wake-word VAD model not found: {vad_path}")
                self._model.vad = VAD(model_path=str(vad_path), n_threads=1)
                self._model.vad_threshold = config.vad_threshold
        except WakeWordError:
            raise
        except (ImportError, OSError, ValueError) as error:
            raise WakeWordError(f"Unable to initialize openWakeWord: {error}") from error
        self.threshold = config.threshold
        self.name = next(iter(self._model.models))

    def process(self, pcm: bytes) -> WakeWordDetection:
        if len(pcm) % 2:
            raise WakeWordError("Wake-word PCM must contain complete 16-bit samples")
        try:
            samples = self._np.frombuffer(pcm, dtype=self._np.int16)
            predictions = self._model.predict(samples)
            score = float(predictions.get(self.name, 0.0))
        except (RuntimeError, ValueError) as error:
            raise WakeWordError(f"Wake-word inference failed: {error}") from error
        return WakeWordDetection(score >= self.threshold, score, self.name)

    def reset(self) -> None:
        self._model.reset()
        vad = getattr(self._model, "vad", None)
        if vad is not None:
            vad.reset_states()
            vad.prediction_buffer.clear()

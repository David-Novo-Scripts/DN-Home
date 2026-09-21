from collections.abc import Iterator

from dn_home.core.config import VadConfig
from dn_home.voice.input.base import AudioFrame
from dn_home.voice.input.capture import UtteranceCapture
from dn_home.voice.vad.base import VoiceActivityDetector


class FakeVad(VoiceActivityDetector):
    def __init__(self, probabilities: list[float]) -> None:
        self.probabilities = iter(probabilities)
        self.reset_count = 0

    def probability(self, pcm: bytes) -> float:
        assert len(pcm) == 960
        return next(self.probabilities)

    def reset(self) -> None:
        self.reset_count += 1


def audio_frames(count: int) -> Iterator[AudioFrame]:
    for _ in range(count):
        yield AudioFrame(bytes(320), 16_000, 1)


def vad_config(**overrides) -> VadConfig:
    values = {
        "threshold": 0.5,
        "speech_start_timeout": 0.09,
        "end_silence_ms": 60,
        "max_utterance_seconds": 2,
        "pre_roll_ms": 30,
    }
    values.update(overrides)
    return VadConfig(**values)


def test_times_out_when_no_speech_follows_wakeword() -> None:
    detector = FakeVad([0.1, 0.2, 0.1])

    result = UtteranceCapture(detector, vad_config()).capture(audio_frames(9))

    assert result.speech_detected is False
    assert result.reason == "speech_start_timeout"
    assert result.pcm == b""


def test_vad_stops_after_configured_end_silence() -> None:
    detector = FakeVad([0.1, 0.9, 0.8, 0.1, 0.1])

    result = UtteranceCapture(detector, vad_config()).capture(audio_frames(15))

    assert result.speech_detected is True
    assert result.reason == "end_silence"
    assert result.duration_ms == 120
    assert len(result.pcm) == 120 * 32

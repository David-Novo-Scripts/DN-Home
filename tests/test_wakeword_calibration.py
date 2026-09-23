from dn_home.voice.input.base import AudioFrame, AudioInput
from dn_home.voice.vad.base import VoiceActivityDetector
from dn_home.voice.wakeword.base import WakeWordDetection, WakeWordEngine
from dn_home.voice.wakeword.calibration import calibrate_wakeword


class FakeAudio(AudioInput):
    def __init__(self, frames: int) -> None:
        self.frame_count = frames
        self.closed = False

    def frames(self):
        for _ in range(self.frame_count):
            yield AudioFrame(bytes(320), 16_000, 1)

    def close(self) -> None:
        self.closed = True


class FakeVad(VoiceActivityDetector):
    def __init__(self, scores: list[float]) -> None:
        self.scores = iter(scores)

    def probability(self, pcm: bytes) -> float:
        return next(self.scores)

    def reset(self) -> None:
        pass


class FakeWakeWord(WakeWordEngine):
    def __init__(self, scores: list[float]) -> None:
        self.scores = iter(scores)

    def process(self, pcm: bytes) -> WakeWordDetection:
        score = next(self.scores, 0.0)
        return WakeWordDetection(score >= 0.5, score, "jarvis")

    def reset(self) -> None:
        pass


def test_calibration_reports_detected_and_missed_attempts() -> None:
    # Two utterances: 90 ms speech followed by 600 ms silence each.
    vad_scores = ([0.9] * 3 + [0.0] * 20) * 2
    audio = FakeAudio(len(vad_scores) * 3)
    attempts = []

    result = calibrate_wakeword(
        audio=audio,
        engine=FakeWakeWord([0.1, 0.8] + [0.1] * 20),
        vad=FakeVad(vad_scores),
        threshold=0.5,
        attempt_count=2,
        timeout_seconds=30,
        on_attempt=attempts.append,
    )

    assert len(result.attempts) == 2
    assert attempts == list(result.attempts)
    assert result.attempts[0].detected is True
    assert result.attempts[1].detected is False
    assert audio.closed is True

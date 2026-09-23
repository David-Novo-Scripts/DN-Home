from datetime import datetime
from types import SimpleNamespace

from dn_home.assistant import (
    AssistantRuntime,
    ResponseOutput,
    VoiceState,
    VoiceStateMachine,
)
from dn_home.core.config import AssistantConfig
from dn_home.core.events import EventBus
from dn_home.skills.transit.base import (
    TransitNoDirectService,
    TransitProvider,
    TransitUnavailable,
)
from dn_home.skills.transit.models import TransitResult
from dn_home.skills.transit.service import TransitSkill
from dn_home.voice.input.base import AudioFrame, AudioInput
from dn_home.voice.input.capture import CapturedUtterance
from dn_home.voice.stt.base import STTEngine, Transcript
from dn_home.voice.wakeword.base import WakeWordDetection, WakeWordEngine


class FakeAudio(AudioInput):
    def __init__(self, count: int = 100) -> None:
        self.count = count
        self.closed = False

    def frames(self):
        for _ in range(self.count):
            yield AudioFrame(bytes(320), 16_000, 1)

    def close(self) -> None:
        self.closed = True


class FakeWakeWord(WakeWordEngine):
    def __init__(self, detections: list[bool]) -> None:
        self.detections = iter(detections)
        self.calls = 0

    def process(self, pcm: bytes) -> WakeWordDetection:
        self.calls += 1
        detected = next(self.detections, False)
        return WakeWordDetection(detected, 0.8 if detected else 0.1, "jarvis")

    def reset(self) -> None:
        pass


class FakeCapture:
    def __init__(self, result: CapturedUtterance) -> None:
        self.result = result

    def capture(self, _frames):
        return self.result


class FakeStt(STTEngine):
    def __init__(self, text: str) -> None:
        self.text = text

    def transcribe(self, pcm: bytes, sample_rate: int) -> Transcript:
        return Transcript(self.text, "pt", len(pcm) // 32)


class FakeTransit(TransitProvider):
    def __init__(self, unavailable: bool = False, no_direct: bool = False) -> None:
        self.destinations: list[str] = []
        self.unavailable = unavailable
        self.no_direct = no_direct

    def next(self, destination: str) -> TransitResult:
        self.destinations.append(destination)
        if self.no_direct:
            raise TransitNoDirectService(destination, "RER A")
        if self.unavailable:
            raise TransitUnavailable("offline")
        return TransitResult(
            destination,
            "Lognes" if destination == "work" else "Nation",
            "RER A",
            datetime(2026, 9, 21, 10, 0),
            4,
            "direction",
            True,
            "standard",
        )


class FakeOutput(ResponseOutput):
    def __init__(self) -> None:
        self.messages: list[str] = []

    def speak(self, text: str) -> None:
        self.messages.append(text)


def runtime_for(text: str, *, capture=None, transit=None):
    output = FakeOutput()
    provider = transit or FakeTransit()
    runtime = AssistantRuntime(
        audio=FakeAudio(),
        wakeword=FakeWakeWord([False, True]),
        utterance_capture=capture
        or FakeCapture(CapturedUtterance(bytes(3200), True, "end_silence", 100)),
        stt=FakeStt(text),
        transit=TransitSkill(provider),
        output=output,
        config=AssistantConfig(cooldown_seconds=0, log_transcripts=False),
    )
    return runtime, provider, output


def test_false_wake_event_is_ignored_before_detection() -> None:
    runtime, _, _ = runtime_for("próximo comboio para o trabalho")
    frames = iter(FakeAudio(24).frames())

    assert runtime._wait_for_wake(frames, None) is True
    assert runtime.wakeword.calls == 2


def test_timeout_after_wakeword_does_not_invoke_stt_or_output() -> None:
    capture = FakeCapture(CapturedUtterance(b"", False, "speech_start_timeout", 0))
    runtime, _, output = runtime_for("unused", capture=capture)

    assert runtime._handle_command(iter(FakeAudio(2).frames())) is False
    assert output.messages == []


def test_empty_stt_result_does_not_execute_an_intent() -> None:
    runtime, provider, output = runtime_for("")

    assert runtime._handle_command(iter(FakeAudio(2).frames())) is False
    assert provider.destinations == []
    assert output.messages == []


def test_unknown_intent_does_not_execute_an_action() -> None:
    runtime, provider, output = runtime_for("acende uma luz inventada")

    assert runtime._handle_command(iter(FakeAudio(2).frames())) is True
    assert provider.destinations == []
    assert output.messages == ["Não reconheci esse comando."]


def test_transit_destinations_are_dispatched_without_chatgpt() -> None:
    for text, expected in (
        ("Qual é o próximo comboio para o trabalho?", "work"),
        ("Quando passa o próximo RER para Paris?", "paris"),
    ):
        runtime, provider, output = runtime_for(text)

        assert runtime._handle_command(iter(FakeAudio(2).frames())) is True
        assert provider.destinations == [expected]
        assert output.messages and "RER A" in output.messages[0]


def test_transit_failure_never_invents_a_timetable() -> None:
    runtime, _, output = runtime_for(
        "próximo comboio para Paris", transit=FakeTransit(unavailable=True)
    )

    assert runtime._handle_command(iter(FakeAudio(2).frames())) is True
    assert output.messages == ["Não foi possível obter horários de transporte agora."]


def test_no_direct_service_is_distinct_from_api_failure() -> None:
    runtime, _, output = runtime_for(
        "próximo comboio para o trabalho", transit=FakeTransit(no_direct=True)
    )

    assert runtime._handle_command(iter(FakeAudio(2).frames())) is True
    assert output.messages == [
        "Não há nenhum RER A direto disponível para o trabalho a esta hora."
    ]


def test_speaking_and_cooldown_reject_self_echo_wakeword() -> None:
    machine = VoiceStateMachine(cooldown_seconds=2)
    machine.enter(VoiceState.SPEAKING)
    assert machine.accepts_wakeword(now=10) is False

    machine.begin_cooldown(now=10)
    assert machine.accepts_wakeword(now=11.9) is False
    assert machine.accepts_wakeword(now=12.0) is True
    assert machine.state == VoiceState.WAIT_WAKE

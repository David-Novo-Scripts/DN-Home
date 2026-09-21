"""Foreground, event-driven voice assistant runtime for the initial PoC."""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
import time
from typing import Iterator

from dn_home.core.config import AssistantConfig
from dn_home.core.events import Event, EventBus
from dn_home.intents.transit import parse_transit_intent
from dn_home.skills.transit.base import TransitError
from dn_home.skills.transit.service import TransitSkill
from dn_home.voice.input.base import AudioFrame, AudioInput
from dn_home.voice.input.capture import UtteranceCapture
from dn_home.voice.stt.base import STTEngine
from dn_home.voice.wakeword.base import WakeWordEngine


class VoiceState(str, Enum):
    WAIT_WAKE = "WAIT_WAKE"
    LISTENING = "LISTENING"
    PROCESSING = "PROCESSING"
    SPEAKING = "SPEAKING"
    COOLDOWN = "COOLDOWN"


class ResponseOutput(ABC):
    @abstractmethod
    def speak(self, text: str) -> None:
        """Deliver a response and return only when output has finished."""


class ConsoleResponseOutput(ResponseOutput):
    """Safe PoC output: display text without invoking TTS or Cast."""

    def speak(self, text: str) -> None:
        print(f"assistant_response={text}", flush=True)


class VoiceStateMachine:
    def __init__(self, cooldown_seconds: float) -> None:
        self.state = VoiceState.WAIT_WAKE
        self.cooldown_seconds = cooldown_seconds
        self.cooldown_until = 0.0

    def accepts_wakeword(self, now: float | None = None) -> bool:
        current = time.monotonic() if now is None else now
        if self.state == VoiceState.COOLDOWN and current >= self.cooldown_until:
            self.state = VoiceState.WAIT_WAKE
        return self.state == VoiceState.WAIT_WAKE

    def enter(self, state: VoiceState) -> None:
        self.state = state

    def begin_cooldown(self, now: float | None = None) -> None:
        current = time.monotonic() if now is None else now
        self.state = VoiceState.COOLDOWN
        self.cooldown_until = current + self.cooldown_seconds


class AssistantRuntime:
    WAKE_CHUNK_BYTES = 1_280 * 2

    def __init__(
        self,
        *,
        audio: AudioInput,
        wakeword: WakeWordEngine,
        utterance_capture: UtteranceCapture,
        stt: STTEngine,
        transit: TransitSkill,
        output: ResponseOutput,
        config: AssistantConfig,
        events: EventBus | None = None,
    ) -> None:
        self.audio = audio
        self.wakeword = wakeword
        self.utterance_capture = utterance_capture
        self.stt = stt
        self.transit = transit
        self.output = output
        self.config = config
        self.events = events or EventBus()
        self.machine = VoiceStateMachine(config.cooldown_seconds)

    def _publish(self, name: str, **data: object) -> None:
        self.events.publish(Event(name, dict(data)))

    def _wait_for_wake(
        self, frames: Iterator[AudioFrame], deadline: float | None
    ) -> bool:
        buffered = bytearray()
        for frame in frames:
            if deadline is not None and time.monotonic() >= deadline:
                return False
            if not self.machine.accepts_wakeword():
                continue
            buffered.extend(frame.pcm)
            while len(buffered) >= self.WAKE_CHUNK_BYTES:
                chunk = bytes(buffered[: self.WAKE_CHUNK_BYTES])
                del buffered[: self.WAKE_CHUNK_BYTES]
                detection = self.wakeword.process(chunk)
                if detection.detected and self.machine.accepts_wakeword():
                    self._publish(
                        "voice.wake_detected",
                        engine=detection.name,
                        score=round(detection.score, 4),
                    )
                    return True
        return False

    def _drain_cooldown(self, frames: Iterator[AudioFrame]) -> None:
        for _frame in frames:
            if self.machine.accepts_wakeword():
                self.wakeword.reset()
                return

    def _handle_command(self, frames: Iterator[AudioFrame]) -> bool:
        self.machine.enter(VoiceState.LISTENING)
        self._publish("voice.listening_started")
        utterance = self.utterance_capture.capture(frames)
        if not utterance.speech_detected:
            self._publish("voice.listen_timeout", reason=utterance.reason)
            self.machine.begin_cooldown()
            self._drain_cooldown(frames)
            return False

        self.machine.enter(VoiceState.PROCESSING)
        self._publish("voice.utterance_captured", duration_ms=utterance.duration_ms)
        transcript = self.stt.transcribe(utterance.pcm, 16_000)
        if not transcript.text.strip():
            self._publish("voice.stt_empty")
            self.machine.begin_cooldown()
            self._drain_cooldown(frames)
            return False
        event_data: dict[str, object] = {"language": transcript.language}
        if self.config.log_transcripts:
            event_data["text"] = transcript.text
        self._publish("voice.transcribed", **event_data)

        intent = parse_transit_intent(transcript.text)
        if intent is None:
            self._publish("intent.unknown")
            response = "Não reconheci esse comando."
        else:
            self._publish("intent.transit_next", destination=intent.destination)
            try:
                _result, response = self.transit.next(intent.destination)
            except TransitError:
                self._publish("transit.unavailable", destination=intent.destination)
                response = "Não foi possível obter horários de transporte agora."

        self.machine.enter(VoiceState.SPEAKING)
        self._publish("voice.response_started", output="console")
        self.output.speak(response)
        self._publish("voice.response_finished", output="console")
        self.machine.begin_cooldown()
        self._drain_cooldown(frames)
        return True

    def run(self, *, once: bool = False, max_wait_seconds: float | None = None) -> int:
        deadline = (
            time.monotonic() + max_wait_seconds
            if max_wait_seconds is not None
            else None
        )
        frames = self.audio.frames()
        completed = 0
        self._publish("assistant.started", output="console")
        try:
            while True:
                self.machine.enter(VoiceState.WAIT_WAKE)
                self._publish("voice.wait_wake")
                if not self._wait_for_wake(frames, deadline):
                    return completed
                if self._handle_command(frames):
                    completed += 1
                    if once:
                        return completed
                if deadline is not None and time.monotonic() >= deadline:
                    return completed
        finally:
            self.audio.close()
            self._publish("assistant.stopped", completed=completed)

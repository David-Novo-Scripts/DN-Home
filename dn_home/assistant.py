"""Foreground, event-driven voice assistant runtime for the initial PoC."""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
import time
from typing import Iterator

from dn_home.core.config import AssistantConfig
from dn_home.core.events import Event, EventBus
from dn_home.intents.transit import parse_transit_intent
from dn_home.skills.transit.base import TransitError, TransitNoDirectService
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

    def _enter_state(self, state: VoiceState) -> None:
        self.machine.enter(state)
        self._publish("voice.state_changed", state=state.value)

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
        self._enter_state(VoiceState.LISTENING)
        self._publish("voice.listening_started")
        capture_started_at = time.monotonic()
        utterance = self.utterance_capture.capture(frames)
        capture_completed_at = time.monotonic()
        capture_ms = round((capture_completed_at - capture_started_at) * 1000)
        if not utterance.speech_detected:
            self._publish(
                "voice.listen_timeout", reason=utterance.reason, capture_ms=capture_ms
            )
            self.machine.begin_cooldown()
            self._publish("voice.state_changed", state=VoiceState.COOLDOWN.value)
            self._drain_cooldown(frames)
            return False

        self._enter_state(VoiceState.PROCESSING)
        end_silence_ms = 0
        capture_config = getattr(self.utterance_capture, "config", None)
        if utterance.reason == "end_silence" and capture_config is not None:
            configured_silence = int(capture_config.end_silence_ms)
            end_silence_ms = (
                (configured_silence + UtteranceCapture.VAD_FRAME_MS - 1)
                // UtteranceCapture.VAD_FRAME_MS
                * UtteranceCapture.VAD_FRAME_MS
            )
        estimated_speech_end_at = capture_completed_at - end_silence_ms / 1000
        self._publish(
            "voice.utterance_captured",
            duration_ms=utterance.duration_ms,
            capture_ms=capture_ms,
            reason=utterance.reason,
            end_silence_ms=end_silence_ms,
        )
        stt_started_at = time.monotonic()
        transcript = self.stt.transcribe(utterance.pcm, 16_000)
        transcript_ready_at = time.monotonic()
        stt_ms = round((transcript_ready_at - stt_started_at) * 1000)
        end_speech_to_transcript_ms = round(
            (transcript_ready_at - estimated_speech_end_at) * 1000
        )
        if not transcript.text.strip():
            self._publish(
                "voice.stt_empty",
                stt_ms=stt_ms,
                end_speech_to_transcript_ms=end_speech_to_transcript_ms,
            )
            self.machine.begin_cooldown()
            self._publish("voice.state_changed", state=VoiceState.COOLDOWN.value)
            self._drain_cooldown(frames)
            return False
        event_data: dict[str, object] = {
            "language": transcript.language,
            "stt_ms": stt_ms,
            "end_speech_to_transcript_ms": end_speech_to_transcript_ms,
        }
        if self.config.log_transcripts:
            event_data["text"] = transcript.text
        self._publish("voice.transcribed", **event_data)

        intent_started_at = time.monotonic()
        intent = parse_transit_intent(transcript.text)
        intent_ms = round((time.monotonic() - intent_started_at) * 1000, 3)
        if intent is None:
            self._publish("intent.unknown", parse_ms=intent_ms)
            response = "Não reconheci esse comando."
        else:
            self._publish(
                "intent.transit_next",
                intent="transit.next",
                destination=intent.destination,
                parse_ms=intent_ms,
            )
            transit_started_at = time.monotonic()
            try:
                result, response = self.transit.next(intent.destination)
                transit_ms = round((time.monotonic() - transit_started_at) * 1000)
                self._publish(
                    "transit.result",
                    destination=result.destination,
                    destination_name=result.destination_name,
                    line=result.line,
                    departure_time=result.departure_time.isoformat(),
                    minutes=result.minutes,
                    following_minutes=list(result.following_minutes),
                    direction=result.direction,
                    realtime=result.realtime,
                    status=result.status,
                    provider_ms=transit_ms,
                )
            except TransitNoDirectService as error:
                transit_ms = round((time.monotonic() - transit_started_at) * 1000)
                self._publish(
                    "transit.no_direct_service",
                    destination=error.destination,
                    line=error.line,
                    provider_ms=transit_ms,
                )
                destination_text = (
                    "o trabalho" if error.destination == "work" else "Paris"
                )
                response = (
                    f"Não há nenhum {error.line} direto disponível para "
                    f"{destination_text} a esta hora."
                )
            except TransitError:
                transit_ms = round((time.monotonic() - transit_started_at) * 1000)
                self._publish(
                    "transit.unavailable",
                    destination=intent.destination,
                    provider_ms=transit_ms,
                )
                response = "Não foi possível obter horários de transporte agora."

        response_ready_at = time.monotonic()
        self._publish(
            "voice.response_ready",
            text=response,
            end_speech_to_response_ready_ms=round(
                (response_ready_at - estimated_speech_end_at) * 1000
            ),
        )
        self._enter_state(VoiceState.SPEAKING)
        self._publish("voice.response_started", output="console")
        output_started_at = time.monotonic()
        self.output.speak(response)
        self._publish(
            "voice.response_finished",
            output="console",
            output_ms=round((time.monotonic() - output_started_at) * 1000),
        )
        self.machine.begin_cooldown()
        self._publish("voice.state_changed", state=VoiceState.COOLDOWN.value)
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
                self._enter_state(VoiceState.WAIT_WAKE)
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

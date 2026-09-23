"""Command-line interface for DN Home Phase 1."""

from __future__ import annotations

import argparse
from array import array
import asyncio
from dataclasses import replace
import json
import logging
from pathlib import Path
import resource
import sys
import time

from dotenv import load_dotenv

from dn_home.core.config import (
    ConfigError,
    load_config,
    validate_voice_pitch,
    validate_voice_rate,
)
from dn_home.assistant import AssistantRuntime, ConsoleResponseOutput
from dn_home.core.events import Event, EventBus
from dn_home.core.logging import configure_logging
from dn_home.devices.speakers.cast import CastSpeaker
from dn_home.doctor import run_doctor
from dn_home.skills.transit.base import TransitError
from dn_home.skills.transit.idfm import IDFMNavitiaProvider
from dn_home.skills.transit.service import TransitSkill
from dn_home.voice.tts.base import TTSError
from dn_home.voice.tts.edge import EdgeTTSEngine
from dn_home.voice.input.alsa import list_alsa_devices, test_microphone
from dn_home.voice.input.alsa import AlsaArecordSource
from dn_home.voice.input.base import AudioInputError
from dn_home.voice.wakeword.base import WakeWordError
from dn_home.voice.wakeword.openwakeword import OpenWakeWordEngine
from dn_home.voice.wakeword.calibration import WakeAttempt, calibrate_wakeword
from dn_home.voice.stt.base import STTError
from dn_home.voice.stt.whisper_cpp import WhisperCppEngine
from dn_home.voice.input.capture import UtteranceCapture
from dn_home.voice.vad.silero import SileroVoiceActivityDetector


LOGGER = logging.getLogger(__name__)


def _rate_argument(value: str) -> str:
    try:
        return validate_voice_rate(value, "--rate")
    except ConfigError as error:
        raise argparse.ArgumentTypeError(str(error)) from error


def _pitch_argument(value: str) -> str:
    try:
        return validate_voice_pitch(value, "--pitch")
    except ConfigError as error:
        raise argparse.ArgumentTypeError(str(error)) from error


def _requested_cast_volume(cli_volume: int | None, speaker_config) -> int | None:
    if cli_volume is not None:
        volume = cli_volume
    elif speaker_config.manage_volume:
        volume = speaker_config.volume
    else:
        return None
    if not 0 <= volume <= 100:
        raise ConfigError("--volume must be between 0 and 100")
    return volume


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m dn_home")
    parser.add_argument(
        "--config",
        default="config/config.yaml",
        help="YAML configuration path (default: config/config.yaml)",
    )
    parser.add_argument("--debug", action="store_true", help="enable debug logging")
    commands = parser.add_subparsers(dest="command", required=True)

    voices = commands.add_parser("voices", help="list available TTS voices")
    voices.add_argument("--language", help="locale to list; defaults to configured locale")
    voices.add_argument("--all", action="store_true", help="list every available locale")

    speak = commands.add_parser("speak", help="speak text through the configured Nest")
    speak.add_argument("--voice", help="TTS voice name")
    speak.add_argument(
        "--rate",
        type=_rate_argument,
        help="Edge TTS speaking rate, for example +8%%; defaults to voice.rate",
    )
    speak.add_argument(
        "--pitch",
        type=_pitch_argument,
        help="Edge TTS pitch, for example -5Hz; defaults to voice.pitch",
    )
    speak.add_argument("--volume", type=int, help="Nest volume from 0 to 100")
    speak.add_argument(
        "--restore-volume",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="restore the previous Nest volume after playback",
    )
    speak.add_argument("text", nargs="+", help="text to speak")

    commands.add_parser("doctor", help="run diagnostics without playing audio")

    transit = commands.add_parser("transit", help="query configured public transport")
    transit_commands = transit.add_subparsers(dest="transit_command", required=True)
    transit_next = transit_commands.add_parser("next", help="show next direct journey")
    transit_next.add_argument(
        "--to",
        required=True,
        help="configured destination alias, for example work or paris",
    )

    mic = commands.add_parser("mic", help="inspect or test the configured microphone")
    mic_commands = mic.add_subparsers(dest="mic_command", required=True)
    mic_commands.add_parser("list", help="list ALSA capture devices and PCMs")
    mic_test = mic_commands.add_parser("test", help="capture and discard a diagnostic WAV")
    mic_test.add_argument("--seconds", type=float, default=5, help="capture duration (default: 5)")
    mic_test.add_argument(
        "--countdown", type=int, default=3, help="seconds before capture begins (default: 3)"
    )

    wakeword = commands.add_parser("wakeword", help="benchmark the local wake-word engine")
    wakeword_commands = wakeword.add_subparsers(dest="wakeword_command", required=True)
    wakeword_benchmark = wakeword_commands.add_parser(
        "benchmark", help="listen in RAM and report Jarvis scores"
    )
    wakeword_benchmark.add_argument(
        "--seconds", type=float, default=30, help="benchmark duration (default: 30)"
    )
    wakeword_benchmark.add_argument(
        "--expected", type=int, default=0, help="number of deliberate utterances"
    )
    wakeword_benchmark.add_argument(
        "--model",
        action="append",
        type=Path,
        help="wake-word model to test; repeat to compare on the same audio",
    )
    wakeword_benchmark.add_argument(
        "--countdown", type=int, default=3, help="seconds before capture begins (default: 3)"
    )
    wakeword_benchmark.add_argument(
        "--disable-vad",
        action="store_true",
        help="diagnostic only: report raw classifier scores without Silero gating",
    )
    wakeword_calibrate = wakeword_commands.add_parser(
        "calibrate", help="score a fixed number of deliberate wake-word attempts"
    )
    wakeword_calibrate.add_argument("--model", required=True, type=Path)
    wakeword_calibrate.add_argument("--attempts", type=int, default=10)
    wakeword_calibrate.add_argument("--timeout", type=float, default=120)
    wakeword_calibrate.add_argument("--countdown", type=int, default=5)

    stt = commands.add_parser("stt", help="benchmark local speech recognition")
    stt_commands = stt.add_subparsers(dest="stt_command", required=True)
    stt_benchmark = stt_commands.add_parser(
        "benchmark", help="capture once in RAM and transcribe with one or more models"
    )
    stt_benchmark.add_argument(
        "--seconds", type=float, default=5, help="fixed capture duration (default: 5)"
    )
    stt_benchmark.add_argument(
        "--model",
        action="append",
        type=Path,
        help="model to test; repeat to compare (defaults to stt.model_path)",
    )
    stt_benchmark.add_argument(
        "--expected", default="", help="authorized phrase expected during this benchmark"
    )
    stt_benchmark.add_argument(
        "--countdown", type=int, default=3, help="seconds before capture begins (default: 3)"
    )

    assistant = commands.add_parser(
        "assistant", help="run the always-listening foreground PoC without Cast"
    )
    assistant.add_argument(
        "--once", action="store_true", help="stop after one successfully handled command"
    )
    assistant.add_argument(
        "--max-wait-seconds",
        type=float,
        help="optional bounded PoC runtime; omitted means run until interrupted",
    )
    return parser


async def _voices(args: argparse.Namespace, config) -> int:
    engine = EdgeTTSEngine(
        config.voice.default_voice,
        rate=config.voice.rate,
        pitch=config.voice.pitch,
        tts_volume=config.voice.tts_volume,
    )
    language = None if args.all else (args.language or config.voice.language)
    voices = await engine.list_voices(language)
    if not voices:
        print(f"No voices found for {language or 'all locales'}")
        return 1
    for voice in voices:
        print(f"{voice.name}\t{voice.locale}\t{voice.gender}")
    return 0


async def _doctor(config) -> int:
    results = await run_doctor(config)
    for result in results:
        print(f"[{'OK' if result.ok else 'FAIL'}] {result.name}: {result.detail}")
    return 0 if all(result.ok for result in results) else 1


async def _speak(args: argparse.Namespace, config) -> int:
    text_request_started_at = time.monotonic()
    text = " ".join(args.text).strip()
    volume = _requested_cast_volume(args.volume, config.speaker)
    restore = (
        config.speaker.restore_previous_volume
        if args.restore_volume is None
        else args.restore_volume
    )
    engine = EdgeTTSEngine(
        config.voice.default_voice,
        rate=config.voice.rate if args.rate is None else args.rate,
        pitch=config.voice.pitch if args.pitch is None else args.pitch,
        tts_volume=config.voice.tts_volume,
    )
    tts_started_at = time.monotonic()
    asset = await engine.generate(text, args.voice)
    tts_generation_ms = round((time.monotonic() - tts_started_at) * 1000)
    try:
        speaker = CastSpeaker(config.speaker, config.network, config.http)
        result = await asyncio.to_thread(
            speaker.speak,
            asset,
            volume=volume,
            restore_previous_volume=restore,
        )
        metrics = result.metrics
        LOGGER.info(
            "event=speech.latency tts_generation_ms=%d http_server_start_ms=%d "
            "cast_connection_ms=%d receiver_launch_ms=%d "
            "play_media_to_http_get_ms=%d http_get_to_playback_started_ms=%d "
            "total_text_to_audio_started_ms=%d",
            tts_generation_ms,
            metrics.http_server_start_ms,
            metrics.cast_connection_ms,
            metrics.receiver_launch_ms,
            metrics.play_media_to_http_get_ms,
            metrics.http_get_to_playback_started_ms,
            round((metrics.audio_started_at - text_request_started_at) * 1000),
        )
    finally:
        asset.cleanup()
        LOGGER.info("event=tts.cleaned result=success")
    print(f"Spoken successfully on {result.device_name}")
    return 0


def _transit_next(args: argparse.Namespace, config) -> int:
    provider = IDFMNavitiaProvider(config.transit)
    result, response = TransitSkill(provider).next(args.to)
    print(response)
    print(
        "destination={destination} station={station} line={line} departure={departure} "
        "minutes={minutes} direction={direction} realtime={realtime} status={status}".format(
            destination=result.destination,
            station=result.destination_name,
            line=result.line,
            departure=result.departure_time.isoformat(),
            minutes=result.minutes,
            direction=result.direction,
            realtime=str(result.realtime).lower(),
            status=result.status,
        )
    )
    return 0


def _mic(args: argparse.Namespace, config) -> int:
    if args.mic_command == "list":
        hardware, pcms = list_alsa_devices()
        print("ALSA capture hardware:\n" + hardware)
        print("\nALSA capture PCMs:\n" + pcms)
        print(f"\nConfigured PCM: {config.audio_input.device}")
        return 0
    if args.mic_command == "test":
        if not 0 <= args.countdown <= 10:
            raise ConfigError("--countdown must be between 0 and 10")
        if args.countdown:
            print(f"capture_starts_in_seconds={args.countdown}", flush=True)
            time.sleep(args.countdown)
        print("capture_started=true", flush=True)
        result = test_microphone(config.audio_input, args.seconds)
        clipping_status = (
            "significant"
            if result.clipping_percent >= 0.1
            else "isolated"
            if result.full_scale_samples
            else "none"
        )
        print(
            "microphone_test=ok device={device} duration_seconds={duration:.3f} "
            "frames={frames} samples={samples} peak={peak} rms={rms} "
            "full_scale_samples={full_scale} clipping_percent={clipping:.6f} "
            "max_full_scale_run={max_run} clipping_status={clipping_status} "
            "initial_window_rms={initial_rms} final_window_rms={final_rms} "
            "silence_threshold_rms={silence_threshold} "
            "leading_silence_ms={leading_silence} "
            "trailing_silence_ms={trailing_silence} "
            "temporary_file_removed={removed}".format(
                device=config.audio_input.device,
                duration=result.duration_seconds,
                frames=result.frames,
                samples=result.samples,
                peak=result.peak,
                rms=result.rms,
                full_scale=result.full_scale_samples,
                clipping=result.clipping_percent,
                max_run=result.max_full_scale_run,
                clipping_status=clipping_status,
                initial_rms=result.initial_window_rms,
                final_rms=result.final_window_rms,
                silence_threshold=result.silence_threshold_rms,
                leading_silence=result.leading_silence_ms,
                trailing_silence=result.trailing_silence_ms,
                removed=str(result.temporary_file_removed).lower(),
            )
        )
        return 0
    raise ConfigError(f"Unknown mic command: {args.mic_command}")


def _current_rss_mib() -> float:
    for line in Path("/proc/self/status").read_text(encoding="utf-8").splitlines():
        if line.startswith("VmRSS:"):
            return int(line.split()[1]) / 1024
    return 0.0


def _wakeword_benchmark(args: argparse.Namespace, config) -> int:
    if not 1 <= args.seconds <= 600:
        raise ConfigError("--seconds must be between 1 and 600")
    if args.expected < 0:
        raise ConfigError("--expected cannot be negative")
    if not 0 <= args.countdown <= 10:
        raise ConfigError("--countdown must be between 0 and 10")
    if config.audio_input.sample_rate != 16_000 or config.audio_input.channels != 1:
        raise ConfigError("openWakeWord requires audio_input at 16000 Hz mono")

    rss_before = _current_rss_mib()
    model_paths = args.model or [config.wake_word.model_path]
    engines: list[OpenWakeWordEngine] = []
    load_times: dict[str, int] = {}
    for model_path in model_paths:
        load_started = time.monotonic()
        engine = OpenWakeWordEngine(
            replace(
                config.wake_word,
                model_path=model_path.expanduser().resolve(),
                vad_threshold=0 if args.disable_vad else config.wake_word.vad_threshold,
            )
        )
        engines.append(engine)
        load_times[engine.name] = round((time.monotonic() - load_started) * 1000)
    source = AlsaArecordSource(config.audio_input)
    chunk_bytes = 1_280 * 2
    buffered = bytearray()
    detections = {engine.name: 0 for engine in engines}
    max_scores = {engine.name: 0.0 for engine in engines}
    last_detection_at = {engine.name: -10.0 for engine in engines}
    audio_peak = 0
    audio_square_sum = 0
    audio_sample_count = 0
    if args.countdown:
        print(f"capture_starts_in_seconds={args.countdown}", flush=True)
        time.sleep(args.countdown)
    print("capture_started=true", flush=True)
    started = time.monotonic()
    cpu_started = time.process_time()
    try:
        for frame in source.frames():
            buffered.extend(frame.pcm)
            while len(buffered) >= chunk_bytes:
                chunk = bytes(buffered[:chunk_bytes])
                del buffered[:chunk_bytes]
                pcm_samples = array("h")
                pcm_samples.frombytes(chunk)
                if sys.byteorder != "little":
                    pcm_samples.byteswap()
                audio_sample_count += len(pcm_samples)
                audio_peak = max(
                    audio_peak,
                    max((abs(sample) for sample in pcm_samples), default=0),
                )
                audio_square_sum += sum(sample * sample for sample in pcm_samples)
                for engine in engines:
                    detection = engine.process(chunk)
                    elapsed = time.monotonic() - started
                    max_scores[engine.name] = max(
                        max_scores[engine.name], detection.score
                    )
                    if (
                        detection.detected
                        and elapsed - last_detection_at[engine.name] >= 1.5
                    ):
                        detections[engine.name] += 1
                        last_detection_at[engine.name] = elapsed
                        print(
                            f"wakeword_detected=true elapsed_seconds={elapsed:.3f} "
                            f"score={detection.score:.4f} model={detection.name}",
                            flush=True,
                        )
            if time.monotonic() - started >= args.seconds:
                break
    finally:
        source.close()
    wall_seconds = time.monotonic() - started
    cpu_seconds = time.process_time() - cpu_started
    cpu_percent = cpu_seconds / wall_seconds * 100 if wall_seconds else 0
    peak_rss_mib = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    audio_rms = (
        int((audio_square_sum / audio_sample_count) ** 0.5)
        if audio_sample_count
        else 0
    )
    for engine in engines:
        recall = detections[engine.name] / args.expected if args.expected else None
        print(
            "wakeword_benchmark=complete model={model} load_ms={load_ms} "
            "wall_seconds={wall:.3f} detections={detections} expected={expected} "
            "recall={recall} max_score={max_score:.4f} cpu_percent_all_models={cpu:.1f} "
            "rss_before_mib={rss_before:.1f} peak_rss_mib_all_models={peak_rss:.1f} "
            "vad_enabled={vad_enabled} audio_peak={audio_peak} audio_rms={audio_rms} "
            "audio_written_to_disk=false".format(
                model=engine.name,
                load_ms=load_times[engine.name],
                wall=wall_seconds,
                detections=detections[engine.name],
                expected=args.expected,
                recall="n/a" if recall is None else f"{recall:.3f}",
                max_score=max_scores[engine.name],
                cpu=cpu_percent,
                rss_before=rss_before,
                peak_rss=peak_rss_mib,
                vad_enabled=str(not args.disable_vad).lower(),
                audio_peak=audio_peak,
                audio_rms=audio_rms,
            )
        )
    return 0


def _wakeword_calibrate(args: argparse.Namespace, config) -> int:
    if not 1 <= args.attempts <= 50:
        raise ConfigError("--attempts must be between 1 and 50")
    if not 10 <= args.timeout <= 600:
        raise ConfigError("--timeout must be between 10 and 600 seconds")
    if not 0 <= args.countdown <= 10:
        raise ConfigError("--countdown must be between 0 and 10")
    if config.audio_input.sample_rate != 16_000 or config.audio_input.channels != 1:
        raise ConfigError("wake-word calibration requires audio_input at 16000 Hz mono")

    model_path = args.model.expanduser().resolve()
    load_started = time.monotonic()
    engine = OpenWakeWordEngine(replace(config.wake_word, model_path=model_path))
    vad = SileroVoiceActivityDetector(model_path.parent / "silero_vad.onnx")
    load_ms = round((time.monotonic() - load_started) * 1000)
    if args.countdown:
        print(f"capture_starts_in_seconds={args.countdown}", flush=True)
        time.sleep(args.countdown)
    print(
        f"calibration_started=true model={engine.name} attempts={args.attempts} "
        f"threshold={config.wake_word.threshold:.3f}",
        flush=True,
    )

    def report(attempt: WakeAttempt) -> None:
        latency = (
            str(attempt.detection_latency_ms)
            if attempt.detection_latency_ms is not None
            else "n/a"
        )
        print(
            f"attempt={attempt.number} score={attempt.score:.4f} "
            f"detected={str(attempt.detected).lower()} "
            f"detection_latency_ms={latency} "
            f"speech_duration_ms={attempt.speech_duration_ms}",
            flush=True,
        )

    result = calibrate_wakeword(
        audio=AlsaArecordSource(config.audio_input),
        engine=engine,
        vad=vad,
        threshold=config.vad.threshold,
        attempt_count=args.attempts,
        timeout_seconds=args.timeout,
        on_attempt=report,
    )
    detected = sum(attempt.detected for attempt in result.attempts)
    print(
        f"wakeword_calibration=complete model={engine.name} "
        f"attempts_completed={len(result.attempts)} detections={detected} "
        f"threshold={config.wake_word.threshold:.3f} load_ms={load_ms} "
        f"wall_seconds={result.wall_seconds:.3f} cpu_percent={result.cpu_percent:.1f} "
        f"peak_rss_mib={result.peak_rss_mib:.1f} audio_written_to_disk=false"
    )
    return 0 if len(result.attempts) == args.attempts else 1


def _capture_fixed_pcm(config, seconds: float) -> bytes:
    if not 0.5 <= seconds <= 30:
        raise ConfigError("--seconds must be between 0.5 and 30")
    target_frames = int(seconds * 1000 / config.frame_ms)
    chunks: list[bytes] = []
    source = AlsaArecordSource(config)
    try:
        for frame in source.frames():
            chunks.append(frame.pcm)
            if len(chunks) >= target_frames:
                break
    finally:
        source.close()
    return b"".join(chunks)


def _stt_benchmark(args: argparse.Namespace, config) -> int:
    if config.audio_input.sample_rate != 16_000 or config.audio_input.channels != 1:
        raise ConfigError("whisper.cpp benchmark requires audio_input at 16000 Hz mono")
    if not 0 <= args.countdown <= 10:
        raise ConfigError("--countdown must be between 0 and 10")
    if args.countdown:
        print(f"capture_starts_in_seconds={args.countdown}", flush=True)
        time.sleep(args.countdown)
    print("capture_started=true", flush=True)
    capture_started = time.monotonic()
    pcm = _capture_fixed_pcm(config.audio_input, args.seconds)
    capture_seconds = time.monotonic() - capture_started
    audio_seconds = len(pcm) / 2 / config.audio_input.sample_rate
    models = args.model or [config.stt.model_path]
    try:
        for model in models:
            model_path = model.expanduser().resolve()
            engine = WhisperCppEngine(replace(config.stt, model_path=model_path))
            started = time.monotonic()
            transcript = engine.transcribe(pcm, config.audio_input.sample_rate)
            elapsed = time.monotonic() - started
            rtf = elapsed / audio_seconds if audio_seconds else 0
            peak_child_mib = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1024
            print(
                "stt_benchmark=model={model} capture_seconds={capture:.3f} "
                "audio_seconds={audio:.3f} transcription_seconds={elapsed:.3f} "
                "rtf={rtf:.3f} peak_child_rss_mib={rss:.1f} expected={expected!r} "
                "transcript={transcript!r} temporary_audio_removed=true".format(
                    model=model_path.name,
                    capture=capture_seconds,
                    audio=audio_seconds,
                    elapsed=elapsed,
                    rtf=rtf,
                    rss=peak_child_mib,
                    expected=args.expected,
                    transcript=transcript.text,
                )
            )
    finally:
        # Keep the only full utterance buffer in RAM and release it promptly.
        del pcm
    return 0


def _assistant(args: argparse.Namespace, config) -> int:
    if args.max_wait_seconds is not None and args.max_wait_seconds <= 0:
        raise ConfigError("--max-wait-seconds must be positive")
    wakeword = OpenWakeWordEngine(config.wake_word)
    vad = SileroVoiceActivityDetector(config.wake_word.model_path.parent / "silero_vad.onnx")
    events = EventBus()

    def report_event(event: Event) -> None:
        payload = {"event": event.name, **event.data}
        print(
            "assistant_event=" + json.dumps(payload, ensure_ascii=False, default=str),
            flush=True,
        )

    events.subscribe("*", report_event)
    runtime = AssistantRuntime(
        audio=AlsaArecordSource(config.audio_input),
        wakeword=wakeword,
        utterance_capture=UtteranceCapture(vad, config.vad),
        stt=WhisperCppEngine(config.stt),
        transit=TransitSkill(IDFMNavitiaProvider(config.transit)),
        output=ConsoleResponseOutput(),
        config=config.assistant,
        events=events,
    )
    print("assistant_mode=foreground output=console cast=false", flush=True)
    completed = runtime.run(
        once=args.once,
        max_wait_seconds=args.max_wait_seconds,
    )
    print(f"assistant_stopped=true commands_completed={completed}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        load_dotenv(".env", override=False)
        config = load_config(Path(args.config))
        configure_logging(config.logging, debug=args.debug)
        if args.command == "voices":
            return asyncio.run(_voices(args, config))
        if args.command == "doctor":
            return asyncio.run(_doctor(config))
        if args.command == "speak":
            return asyncio.run(_speak(args, config))
        if args.command == "transit" and args.transit_command == "next":
            return _transit_next(args, config)
        if args.command == "mic":
            return _mic(args, config)
        if args.command == "wakeword" and args.wakeword_command == "benchmark":
            return _wakeword_benchmark(args, config)
        if args.command == "wakeword" and args.wakeword_command == "calibrate":
            return _wakeword_calibrate(args, config)
        if args.command == "stt" and args.stt_command == "benchmark":
            return _stt_benchmark(args, config)
        if args.command == "assistant":
            return _assistant(args, config)
        raise ConfigError(f"Unknown command: {args.command}")
    except (
        ConfigError,
        TTSError,
        TransitError,
        AudioInputError,
        WakeWordError,
        STTError,
        RuntimeError,
    ) as error:
        if logging.getLogger().handlers:
            LOGGER.error("event=command.failed command=%s error=%s", args.command, error)
        else:
            print(f"Error: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())

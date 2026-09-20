"""Command-line interface for DN Home Phase 1."""

from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path
import sys
import time

from dn_home.core.config import (
    ConfigError,
    load_config,
    validate_voice_pitch,
    validate_voice_rate,
)
from dn_home.core.logging import configure_logging
from dn_home.devices.speakers.cast import CastSpeaker
from dn_home.doctor import run_doctor
from dn_home.voice.tts.base import TTSError
from dn_home.voice.tts.edge import EdgeTTSEngine


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


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        config = load_config(Path(args.config))
        configure_logging(config.logging, debug=args.debug)
        if args.command == "voices":
            return asyncio.run(_voices(args, config))
        if args.command == "doctor":
            return asyncio.run(_doctor(config))
        if args.command == "speak":
            return asyncio.run(_speak(args, config))
        raise ConfigError(f"Unknown command: {args.command}")
    except (ConfigError, TTSError, RuntimeError) as error:
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

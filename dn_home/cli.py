"""Command-line interface for DN Home Phase 1."""

from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path
import sys

from dn_home.core.config import ConfigError, load_config
from dn_home.core.logging import configure_logging
from dn_home.devices.speakers.cast import CastSpeaker
from dn_home.doctor import run_doctor
from dn_home.voice.tts.base import TTSError
from dn_home.voice.tts.edge import EdgeTTSEngine


LOGGER = logging.getLogger(__name__)


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
    text = " ".join(args.text).strip()
    volume = config.speaker.volume if args.volume is None else args.volume
    if not 0 <= volume <= 100:
        raise ConfigError("--volume must be between 0 and 100")
    restore = (
        config.speaker.restore_previous_volume
        if args.restore_volume is None
        else args.restore_volume
    )
    engine = EdgeTTSEngine(
        config.voice.default_voice,
        rate=config.voice.rate,
        pitch=config.voice.pitch,
    )
    asset = await engine.generate(text, args.voice)
    try:
        speaker = CastSpeaker(config.speaker, config.network, config.http)
        result = await asyncio.to_thread(
            speaker.speak,
            asset,
            volume=volume,
            restore_previous_volume=restore,
        )
    finally:
        asset.cleanup()
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


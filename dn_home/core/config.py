"""Typed application configuration loaded from YAML."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

import yaml


class ConfigError(ValueError):
    """Raised when application configuration is missing or invalid."""


RATE_PATTERN = re.compile(r"^[+-]\d+%$")
PITCH_PATTERN = re.compile(r"^[+-]\d+Hz$")


@dataclass(frozen=True, slots=True)
class VoiceConfig:
    engine: str
    language: str
    default_voice: str
    rate: str
    pitch: str
    tts_volume: str


@dataclass(frozen=True, slots=True)
class SpeakerConfig:
    provider: str
    name: str
    host: str | None
    port: int
    manage_volume: bool
    volume: int
    restore_previous_volume: bool
    connect_timeout: float
    playback_timeout: float


@dataclass(frozen=True, slots=True)
class NetworkConfig:
    lan_interface: str | None
    lan_ip: str | None


@dataclass(frozen=True, slots=True)
class HttpConfig:
    port: int
    request_timeout: float


@dataclass(frozen=True, slots=True)
class LoggingConfig:
    level: str
    file: Path
    max_bytes: int
    backup_count: int


@dataclass(frozen=True, slots=True)
class AudioInputConfig:
    provider: str
    device: str
    sample_rate: int
    channels: int
    sample_format: str
    frame_ms: int


@dataclass(frozen=True, slots=True)
class WakeWordConfig:
    engine: str
    model_path: Path
    threshold: float
    vad_threshold: float


@dataclass(frozen=True, slots=True)
class VadConfig:
    threshold: float
    speech_start_timeout: float
    end_silence_ms: int
    max_utterance_seconds: float
    pre_roll_ms: int


@dataclass(frozen=True, slots=True)
class SttConfig:
    engine: str
    binary_path: Path
    model_path: Path
    language: str
    threads: int
    prompt: str


@dataclass(frozen=True, slots=True)
class AssistantConfig:
    cooldown_seconds: float
    log_transcripts: bool


@dataclass(frozen=True, slots=True)
class TransitStopConfig:
    name: str
    stop_id: str
    navitia_id: str
    monitoring_ref: str | None


@dataclass(frozen=True, slots=True)
class TransitConfig:
    provider: str
    api_base: str
    token_env: str
    line_name: str
    line_id: str
    line_code: str
    commercial_mode: str
    origin: TransitStopConfig
    destinations: dict[str, TransitStopConfig]
    timeout: float
    result_count: int


@dataclass(frozen=True, slots=True)
class AppConfig:
    resident_name: str
    voice: VoiceConfig
    speaker: SpeakerConfig
    network: NetworkConfig
    http: HttpConfig
    logging: LoggingConfig
    audio_input: AudioInputConfig
    wake_word: WakeWordConfig
    vad: VadConfig
    stt: SttConfig
    assistant: AssistantConfig
    transit: TransitConfig
    source: Path


def _mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConfigError(f"Configuration section '{name}' must be a mapping")
    return value


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _number(value: Any, name: str, minimum: float, maximum: float) -> float:
    if isinstance(value, bool):
        raise ConfigError(f"'{name}' must be a number")
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise ConfigError(f"'{name}' must be a number") from error
    if not minimum <= result <= maximum:
        raise ConfigError(f"'{name}' must be between {minimum} and {maximum}")
    return result


def _path(value: Any, source: Path) -> Path:
    path = Path(str(value)).expanduser()
    if not path.is_absolute():
        path = source.parent.parent / path
    return path.resolve()


def _required_text(value: Any, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ConfigError(f"'{name}' must not be empty")
    return text


def _transit_stop(value: Any, name: str) -> TransitStopConfig:
    raw = _mapping(value, name)
    return TransitStopConfig(
        name=_required_text(raw.get("name"), f"{name}.name"),
        stop_id=_required_text(raw.get("stop_id"), f"{name}.stop_id"),
        navitia_id=_required_text(raw.get("navitia_id"), f"{name}.navitia_id"),
        monitoring_ref=_optional_text(raw.get("monitoring_ref")),
    )


def validate_voice_rate(value: Any, name: str = "voice.rate") -> str:
    text = str(value).strip()
    if RATE_PATTERN.fullmatch(text) is None:
        raise ConfigError(f"'{name}' must use a signed percentage such as +8%")
    return text


def validate_voice_pitch(value: Any, name: str = "voice.pitch") -> str:
    text = str(value).strip()
    if PITCH_PATTERN.fullmatch(text) is None:
        raise ConfigError(f"'{name}' must use signed Hz such as -5Hz")
    return text


def validate_tts_volume(value: Any, name: str = "voice.tts_volume") -> str:
    text = str(value).strip()
    if RATE_PATTERN.fullmatch(text) is None:
        raise ConfigError(f"'{name}' must use a signed percentage such as +0%")
    return text


def load_config(path: str | Path = "config/config.yaml") -> AppConfig:
    """Load and validate the Phase 1 YAML configuration."""

    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise ConfigError(
            f"Configuration file not found: {source}. "
            "Copy config/config.example.yaml to config/config.yaml first."
        )

    try:
        raw = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as error:
        raise ConfigError(f"Unable to read configuration: {error}") from error

    root = _mapping(raw, "root")
    house = _mapping(root.get("house", {}), "house")
    voice = _mapping(root.get("voice", {}), "voice")
    speaker = _mapping(root.get("speaker", {}), "speaker")
    network = _mapping(root.get("network", {}), "network")
    http = _mapping(root.get("http", {}), "http")
    logging = _mapping(root.get("logging", {}), "logging")
    audio_input = _mapping(root.get("audio_input", {}), "audio_input")
    wake_word = _mapping(root.get("wake_word", {}), "wake_word")
    vad = _mapping(root.get("vad", {}), "vad")
    stt = _mapping(root.get("stt", {}), "stt")
    assistant = _mapping(root.get("assistant", {}), "assistant")
    transit = _mapping(root.get("transit", {}), "transit")

    speaker_volume = int(_number(speaker.get("volume", 35), "speaker.volume", 0, 100))
    speaker_port = int(_number(speaker.get("port", 8009), "speaker.port", 1, 65535))
    http_port = int(_number(http.get("port", 8765), "http.port", 1, 65535))

    name = str(speaker.get("name", "")).strip()
    host = _optional_text(speaker.get("host"))
    if not name and not host:
        raise ConfigError("Configure at least one of speaker.name or speaker.host")

    engine = str(voice.get("engine", "edge")).strip().lower()
    if engine != "edge":
        raise ConfigError("Phase 1 currently supports voice.engine='edge'")

    log_file = _path(logging.get("file", "logs/dn_home.log"), source)

    transit_line = _mapping(transit.get("line", {}), "transit.line")
    transit_origin = transit.get("origin")
    destination_values = _mapping(
        transit.get("destinations", {}),
        "transit.destinations",
    )
    destinations = {
        str(alias).strip().lower(): _transit_stop(
            value, f"transit.destinations.{alias}"
        )
        for alias, value in destination_values.items()
    }
    if not destinations:
        raise ConfigError("'transit.destinations' must contain at least one destination")

    return AppConfig(
        resident_name=str(house.get("resident_name", "David")).strip() or "David",
        voice=VoiceConfig(
            engine=engine,
            language=str(voice.get("language", "pt-PT")).strip() or "pt-PT",
            default_voice=str(voice.get("default_voice", "pt-PT-DuarteNeural")).strip(),
            rate=validate_voice_rate(voice.get("rate", "+0%")),
            pitch=validate_voice_pitch(voice.get("pitch", "+0Hz")),
            tts_volume=validate_tts_volume(voice.get("tts_volume", "+0%")),
        ),
        speaker=SpeakerConfig(
            provider=str(speaker.get("provider", "cast")).strip().lower(),
            name=name,
            host=host,
            port=speaker_port,
            manage_volume=bool(speaker.get("manage_volume", False)),
            volume=speaker_volume,
            restore_previous_volume=bool(speaker.get("restore_previous_volume", True)),
            connect_timeout=_number(
                speaker.get("connect_timeout", 10), "speaker.connect_timeout", 1, 120
            ),
            playback_timeout=_number(
                speaker.get("playback_timeout", 60), "speaker.playback_timeout", 1, 600
            ),
        ),
        network=NetworkConfig(
            lan_interface=_optional_text(network.get("lan_interface")),
            lan_ip=_optional_text(network.get("lan_ip")),
        ),
        http=HttpConfig(
            port=http_port,
            request_timeout=_number(
                http.get("request_timeout", 20), "http.request_timeout", 1, 300
            ),
        ),
        logging=LoggingConfig(
            level=str(logging.get("level", "INFO")).strip().upper(),
            file=log_file,
            max_bytes=int(
                _number(logging.get("max_bytes", 2_097_152), "logging.max_bytes", 1024, 1_000_000_000)
            ),
            backup_count=int(
                _number(logging.get("backup_count", 3), "logging.backup_count", 1, 100)
            ),
        ),
        audio_input=AudioInputConfig(
            provider=str(audio_input.get("provider", "alsa_arecord")).strip().lower(),
            device=_required_text(
                audio_input.get("device", "default"),
                "audio_input.device",
            ),
            sample_rate=int(
                _number(audio_input.get("sample_rate", 16_000), "audio_input.sample_rate", 8_000, 48_000)
            ),
            channels=int(
                _number(audio_input.get("channels", 1), "audio_input.channels", 1, 2)
            ),
            sample_format=str(audio_input.get("sample_format", "S16_LE")).strip().upper(),
            frame_ms=int(
                _number(audio_input.get("frame_ms", 10), "audio_input.frame_ms", 10, 100)
            ),
        ),
        wake_word=WakeWordConfig(
            engine=str(wake_word.get("engine", "openwakeword")).strip().lower(),
            model_path=_path(
                wake_word.get("model_path", "models/wakeword/hey_jarvis_v0.1.onnx"), source
            ),
            threshold=_number(
                wake_word.get("threshold", 0.5), "wake_word.threshold", 0, 1
            ),
            vad_threshold=_number(
                wake_word.get("vad_threshold", 0.5), "wake_word.vad_threshold", 0, 1
            ),
        ),
        vad=VadConfig(
            threshold=_number(vad.get("threshold", 0.5), "vad.threshold", 0, 1),
            speech_start_timeout=_number(
                vad.get("speech_start_timeout_seconds", 5),
                "vad.speech_start_timeout_seconds",
                0.5,
                30,
            ),
            end_silence_ms=int(
                _number(vad.get("end_silence_ms", 800), "vad.end_silence_ms", 100, 5_000)
            ),
            max_utterance_seconds=_number(
                vad.get("max_utterance_seconds", 15),
                "vad.max_utterance_seconds",
                1,
                60,
            ),
            pre_roll_ms=int(
                _number(vad.get("pre_roll_ms", 250), "vad.pre_roll_ms", 0, 2_000)
            ),
        ),
        stt=SttConfig(
            engine=str(stt.get("engine", "whisper_cpp")).strip().lower(),
            binary_path=_path(
                stt.get("binary_path", "vendor/whisper.cpp/build/bin/whisper-cli"), source
            ),
            model_path=_path(
                stt.get("model_path", "models/stt/ggml-base-q5_1.bin"), source
            ),
            language=str(stt.get("language", "pt")).strip().lower() or "pt",
            threads=int(_number(stt.get("threads", 4), "stt.threads", 1, 32)),
            prompt=str(stt.get("prompt", "Jarvis, RER, Paris, Lognes")).strip(),
        ),
        assistant=AssistantConfig(
            cooldown_seconds=_number(
                assistant.get("cooldown_seconds", 2),
                "assistant.cooldown_seconds",
                0,
                30,
            ),
            log_transcripts=bool(assistant.get("log_transcripts", False)),
        ),
        transit=TransitConfig(
            provider=str(transit.get("provider", "idfm_navitia")).strip().lower(),
            api_base=str(
                transit.get(
                    "api_base",
                    "https://prim.iledefrance-mobilites.fr/marketplace/v2/navitia",
                )
            ).rstrip("/"),
            token_env=str(transit.get("token_env", "IDFM_API_TOKEN")).strip(),
            line_name=_required_text(transit_line.get("name"), "transit.line.name"),
            line_id=_required_text(transit_line.get("id"), "transit.line.id"),
            line_code=_required_text(transit_line.get("code"), "transit.line.code"),
            commercial_mode=_required_text(
                transit_line.get("commercial_mode"),
                "transit.line.commercial_mode",
            ),
            origin=_transit_stop(transit_origin, "transit.origin"),
            destinations=destinations,
            timeout=_number(transit.get("timeout_seconds", 10), "transit.timeout_seconds", 1, 60),
            result_count=int(
                _number(transit.get("result_count", 2), "transit.result_count", 1, 5)
            ),
        ),
        source=source,
    )

"""Typed application configuration loaded from YAML."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class ConfigError(ValueError):
    """Raised when application configuration is missing or invalid."""


@dataclass(frozen=True, slots=True)
class VoiceConfig:
    engine: str
    language: str
    default_voice: str
    rate: str
    pitch: str


@dataclass(frozen=True, slots=True)
class SpeakerConfig:
    provider: str
    name: str
    host: str | None
    port: int
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
class AppConfig:
    resident_name: str
    voice: VoiceConfig
    speaker: SpeakerConfig
    network: NetworkConfig
    http: HttpConfig
    logging: LoggingConfig
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

    log_file = Path(str(logging.get("file", "logs/dn_home.log"))).expanduser()
    if not log_file.is_absolute():
        log_file = (source.parent.parent / log_file).resolve()

    return AppConfig(
        resident_name=str(house.get("resident_name", "David")).strip() or "David",
        voice=VoiceConfig(
            engine=engine,
            language=str(voice.get("language", "pt-PT")).strip() or "pt-PT",
            default_voice=str(voice.get("default_voice", "pt-PT-DuarteNeural")).strip(),
            rate=str(voice.get("rate", "+0%")).strip(),
            pitch=str(voice.get("pitch", "+0Hz")).strip(),
        ),
        speaker=SpeakerConfig(
            provider=str(speaker.get("provider", "cast")).strip().lower(),
            name=name,
            host=host,
            port=speaker_port,
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
        source=source,
    )

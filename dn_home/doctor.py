"""Read-only Phase 1 diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tempfile

from dn_home.core.config import AppConfig
from dn_home.devices.speakers.cast import CastSpeaker
from dn_home.media.http_server import TemporaryAudioServer
from dn_home.voice.models import AudioAsset
from dn_home.voice.tts.edge import EdgeTTSEngine


@dataclass(frozen=True, slots=True)
class CheckResult:
    name: str
    ok: bool
    detail: str


async def run_doctor(config: AppConfig) -> list[CheckResult]:
    """Run diagnostics without launching Cast playback."""

    results: list[CheckResult] = [
        CheckResult("config", True, str(config.source)),
    ]
    tts = EdgeTTSEngine(
        config.voice.default_voice,
        rate=config.voice.rate,
        pitch=config.voice.pitch,
    )
    try:
        voices = await tts.list_voices(config.voice.language)
        if not voices:
            raise RuntimeError(f"no voices found for {config.voice.language}")
        results.append(
            CheckResult(
                "tts",
                True,
                f"Edge reachable; {len(voices)} {config.voice.language} voice(s)",
            )
        )
    except Exception as error:
        results.append(CheckResult("tts", False, str(error)))

    speaker = CastSpeaker(config.speaker, config.network, config.http)
    try:
        device = speaker.inspect_device()
        results.append(
            CheckResult(
                "cast",
                True,
                f"{device.model_name} '{device.friendly_name}' at {device.host}:{device.port}",
            )
        )
    except Exception as error:
        results.append(CheckResult("cast", False, str(error)))

    try:
        selection = speaker.select_network()
        results.append(
            CheckResult(
                "route",
                True,
                f"{selection.interface} / {selection.local_ip} ({selection.method})",
            )
        )
    except Exception as error:
        results.append(CheckResult("route", False, str(error)))
        return results

    temp_dir = Path(tempfile.mkdtemp(prefix="dn_home_doctor_"))
    asset = AudioAsset(temp_dir / "probe.tts.mp3", "audio/mpeg", temp_dir)
    try:
        asset.path.write_bytes(b"ID3")
        with TemporaryAudioServer(asset, selection.local_ip, port=config.http.port) as server:
            results.append(CheckResult("http", True, server.sanitized_url))
    except Exception as error:
        results.append(CheckResult("http", False, str(error)))
    finally:
        asset.cleanup()
    return results


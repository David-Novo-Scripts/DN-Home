"""Google Cast speaker implementation with no mDNS dependency."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import time

import pychromecast
from pychromecast import Chromecast
from pychromecast.dial import get_device_info
from pychromecast.models import CastInfo, HostServiceInfo

from dn_home.core.config import HttpConfig, NetworkConfig, SpeakerConfig
from dn_home.core.network import NetworkSelection, select_lan_address
from dn_home.devices.speakers.base import (
    PlaybackMetrics,
    PlaybackResult,
    Speaker,
    SpeakerError,
)
from dn_home.media.http_server import TemporaryAudioServer
from dn_home.voice.models import AudioAsset


LOGGER = logging.getLogger(__name__)


def _milliseconds(started: float, ended: float | None = None) -> int:
    return round(((time.monotonic() if ended is None else ended) - started) * 1000)


@dataclass(frozen=True, slots=True)
class CastDeviceInfo:
    friendly_name: str
    model_name: str
    manufacturer: str
    host: str
    port: int


class CastSpeaker(Speaker):
    def __init__(
        self,
        config: SpeakerConfig,
        network: NetworkConfig,
        http: HttpConfig,
    ):
        self.config = config
        self.network = network
        self.http = http

    def _require_host(self) -> str:
        if not self.config.host:
            raise SpeakerError(
                "speaker.host is required while mDNS-independent Cast mode is enabled"
            )
        return self.config.host

    def _device_status(self):
        host = self._require_host()
        services = {HostServiceInfo(host, self.config.port)}
        status = get_device_info(
            host,
            services=services,
            timeout=self.config.connect_timeout,
        )
        if status is None or status.uuid is None:
            raise SpeakerError(f"No Google Cast device responded at {host}")
        if self.config.name and status.friendly_name != self.config.name:
            raise SpeakerError(
                "Configured Cast name does not match the device at the configured host: "
                f"expected '{self.config.name}', received '{status.friendly_name}'"
            )
        return status

    def inspect_device(self) -> CastDeviceInfo:
        """Read device identity without launching a receiver or playing media."""

        status = self._device_status()
        return CastDeviceInfo(
            friendly_name=status.friendly_name,
            model_name=status.model_name,
            manufacturer=status.manufacturer,
            host=self._require_host(),
            port=self.config.port,
        )

    def select_network(self) -> NetworkSelection:
        return select_lan_address(
            self._require_host(),
            self.config.port,
            explicit_ip=self.network.lan_ip,
            explicit_interface=self.network.lan_interface,
        )

    def _connect(self) -> tuple[Chromecast, CastDeviceInfo]:
        status = self._device_status()
        host = self._require_host()
        cast_info = CastInfo(
            services={HostServiceInfo(host, self.config.port)},
            uuid=status.uuid,
            model_name=status.model_name,
            friendly_name=status.friendly_name,
            host=host,
            port=self.config.port,
            cast_type=status.cast_type,
            manufacturer=status.manufacturer,
        )
        cast = pychromecast.Chromecast(
            cast_info,
            tries=1,
            timeout=self.config.connect_timeout,
            retry_wait=1,
        )
        cast.wait(timeout=self.config.connect_timeout)
        LOGGER.info(
            "event=cast.connected device=%s host=%s port=%d result=success",
            status.friendly_name,
            host,
            self.config.port,
        )
        return cast, CastDeviceInfo(
            friendly_name=status.friendly_name,
            model_name=status.model_name,
            manufacturer=status.manufacturer,
            host=host,
            port=self.config.port,
        )

    def _wait_for_completion(self, cast: Chromecast, requested_at: float) -> float:
        controller = cast.media_controller
        deadline = requested_at + self.config.playback_timeout
        playback_started_at: float | None = None
        while time.monotonic() < deadline:
            state = controller.status.player_state
            if state == "PLAYING":
                if playback_started_at is None:
                    playback_started_at = time.monotonic()
                    LOGGER.info("event=cast.playback_started result=success")
            elif playback_started_at is not None and state in {"IDLE", "UNKNOWN"}:
                LOGGER.info("event=cast.playback_finished result=success")
                return playback_started_at
            time.sleep(0.1)
        try:
            controller.stop()
        except Exception:
            LOGGER.debug("event=cast.stop_failed", exc_info=True)
        raise SpeakerError(
            f"Cast playback did not complete within {self.config.playback_timeout:g}s"
        )

    def speak(
        self,
        asset: AudioAsset,
        *,
        volume: int,
        restore_previous_volume: bool,
    ) -> PlaybackResult:
        selection = self.select_network()
        cast: Chromecast | None = None
        previous_volume: float | None = None
        playback_started = False
        operation_started = time.monotonic()

        try:
            media_server = TemporaryAudioServer(
                asset,
                selection.local_ip,
                port=self.http.port,
            )
            http_start = time.monotonic()
            with media_server:
                http_server_start_ms = _milliseconds(http_start)
                LOGGER.info(
                    "event=cast.media_ready interface=%s local_ip=%s url=%s",
                    selection.interface,
                    selection.local_ip,
                    media_server.sanitized_url,
                )
                cast_connect_started = time.monotonic()
                cast, device = self._connect()
                cast_connection_ms = _milliseconds(cast_connect_started)
                if cast.status is not None:
                    previous_volume = cast.status.volume_level
                cast.set_volume(volume / 100.0, timeout=self.config.connect_timeout)

                controller = cast.media_controller
                LOGGER.info(
                    "event=cast.playback_requested device=%s content_type=%s url=%s",
                    device.friendly_name,
                    asset.content_type,
                    media_server.sanitized_url,
                )
                play_media_started_at = time.monotonic()
                controller.play_media(
                    media_server.url,
                    asset.content_type,
                    title="DN Home",
                    stream_type="BUFFERED",
                )
                playback_started = True
                try:
                    controller.block_until_active(timeout=self.config.connect_timeout)
                except Exception as error:
                    raise SpeakerError(f"Cast receiver did not become active: {error}") from error
                receiver_launch_ms = _milliseconds(play_media_started_at)

                if not media_server.request_started.wait(self.http.request_timeout):
                    raise SpeakerError(
                        "The Nest did not request the temporary audio URL within "
                        f"{self.http.request_timeout:g}s"
                    )
                http_get_at = media_server.request_started_at
                if http_get_at is None:
                    raise SpeakerError("The HTTP GET timestamp was not recorded")
                audio_started_at = self._wait_for_completion(cast, play_media_started_at)
                metrics = PlaybackMetrics(
                    http_server_start_ms=http_server_start_ms,
                    cast_connection_ms=cast_connection_ms,
                    receiver_launch_ms=receiver_launch_ms,
                    play_media_to_http_get_ms=_milliseconds(
                        play_media_started_at, http_get_at
                    ),
                    http_get_to_playback_started_ms=_milliseconds(
                        http_get_at, audio_started_at
                    ),
                    audio_started_at=audio_started_at,
                )
                LOGGER.info(
                    "event=cast.latency http_server_start_ms=%d cast_connection_ms=%d "
                    "receiver_launch_ms=%d play_media_to_http_get_ms=%d "
                    "http_get_to_playback_started_ms=%d",
                    metrics.http_server_start_ms,
                    metrics.cast_connection_ms,
                    metrics.receiver_launch_ms,
                    metrics.play_media_to_http_get_ms,
                    metrics.http_get_to_playback_started_ms,
                )
                LOGGER.info(
                    "event=cast.playback device=%s operation_duration_ms=%d result=success",
                    device.friendly_name,
                    _milliseconds(operation_started),
                )
                return PlaybackResult(
                    device_name=device.friendly_name,
                    completed=True,
                    media_fetched=media_server.request_completed.is_set(),
                    metrics=metrics,
                )
        except SpeakerError:
            raise
        except Exception as error:
            raise SpeakerError(f"Google Cast playback failed: {error}") from error
        finally:
            if cast is not None:
                if restore_previous_volume and previous_volume is not None:
                    try:
                        cast.set_volume(
                            previous_volume,
                            timeout=self.config.connect_timeout,
                        )
                    except Exception:
                        LOGGER.warning(
                            "event=cast.volume_restore result=failure", exc_info=True
                        )
                if playback_started and cast.media_controller.status.player_state == "PLAYING":
                    try:
                        cast.media_controller.stop()
                    except Exception:
                        LOGGER.debug("event=cast.cleanup_stop_failed", exc_info=True)
                try:
                    cast.disconnect(timeout=self.config.connect_timeout)
                except Exception:
                    LOGGER.warning("event=cast.disconnect result=failure", exc_info=True)

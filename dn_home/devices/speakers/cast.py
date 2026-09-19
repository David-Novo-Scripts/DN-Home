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
from dn_home.devices.speakers.base import PlaybackResult, Speaker, SpeakerError
from dn_home.media.http_server import TemporaryAudioServer
from dn_home.voice.models import AudioAsset


LOGGER = logging.getLogger(__name__)


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
        return cast, CastDeviceInfo(
            friendly_name=status.friendly_name,
            model_name=status.model_name,
            manufacturer=status.manufacturer,
            host=host,
            port=self.config.port,
        )

    def _wait_for_completion(self, cast: Chromecast, started: float) -> None:
        controller = cast.media_controller
        deadline = started + self.config.playback_timeout
        has_played = False
        while time.monotonic() < deadline:
            state = controller.status.player_state
            if state == "PLAYING":
                has_played = True
            elif has_played and state in {"IDLE", "UNKNOWN"}:
                return
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
        started = time.monotonic()

        try:
            with TemporaryAudioServer(
                asset,
                selection.local_ip,
                port=self.http.port,
            ) as media_server:
                LOGGER.info(
                    "event=cast.media_ready interface=%s local_ip=%s url=%s",
                    selection.interface,
                    selection.local_ip,
                    media_server.sanitized_url,
                )
                cast, device = self._connect()
                if cast.status is not None:
                    previous_volume = cast.status.volume_level
                cast.set_volume(volume / 100.0, timeout=self.config.connect_timeout)

                controller = cast.media_controller
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

                if not media_server.request_started.wait(self.http.request_timeout):
                    raise SpeakerError(
                        "The Nest did not request the temporary audio URL within "
                        f"{self.http.request_timeout:g}s"
                    )
                self._wait_for_completion(cast, started)
                LOGGER.info(
                    "event=cast.playback device=%s latency_ms=%d result=success",
                    device.friendly_name,
                    round((time.monotonic() - started) * 1000),
                )
                return PlaybackResult(
                    device_name=device.friendly_name,
                    completed=True,
                    media_fetched=media_server.request_completed.is_set(),
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

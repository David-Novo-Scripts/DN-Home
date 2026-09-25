"""Bleak-backed passive data provider for SwitchBot advertisements."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import logging
import time
from typing import Any

from dn_home.sensors.switchbot.contact import (
    ContactSensorChange,
    SwitchBotContactSensor,
)
from dn_home.sensors.switchbot.parser import (
    SwitchBotAdvertisementError,
    parse_contact_service_data,
)


LOGGER = logging.getLogger(__name__)
SWITCHBOT_COMPANY_ID = 0x0969
SWITCHBOT_CONTACT_SERVICE_UUIDS = {
    "0000fd3d-0000-1000-8000-00805f9b34fb",
    "00000d00-0000-1000-8000-00805f9b34fb",
}


class SwitchBotBLEProvider:
    """Receive Contact Sensor service data without connecting to the device."""

    def __init__(
        self,
        sensor: SwitchBotContactSensor,
        *,
        adapter: str = "hci0",
        scanner_factory: Callable[..., Any] | None = None,
    ) -> None:
        self.sensor = sensor
        self.adapter = adapter
        self._scanner_factory = scanner_factory

    async def monitor(
        self,
        *,
        on_change: Callable[[ContactSensorChange], None],
        duration_seconds: float | None = None,
    ) -> None:
        """Run active discovery and report only state transitions."""

        scanner_factory = self._scanner_factory
        if scanner_factory is None:
            try:
                from bleak import BleakScanner
            except ImportError as error:
                raise RuntimeError(
                    "Bleak is required for SwitchBot monitoring; install project dependencies"
                ) from error
            scanner_factory = BleakScanner

        def detection_callback(device: Any, advertisement: Any) -> None:
            if str(device.address).upper() != self.sensor.address:
                return
            service_data = {
                str(key).lower(): bytes(value)
                for key, value in advertisement.service_data.items()
            }
            payload = next(
                (
                    service_data[uuid]
                    for uuid in SWITCHBOT_CONTACT_SERVICE_UUIDS
                    if uuid in service_data
                ),
                None,
            )
            if payload is None:
                return
            try:
                parsed = parse_contact_service_data(payload)
            except SwitchBotAdvertisementError as error:
                LOGGER.debug(
                    "event=switchbot.advertisement_ignored address=%s error=%s",
                    device.address,
                    error,
                )
                return
            for change in self.sensor.update(parsed, rssi=advertisement.rssi):
                on_change(change)

        scanner = scanner_factory(
            detection_callback=detection_callback,
            scanning_mode="active",
            bluez={"adapter": self.adapter},
        )
        started_at = time.monotonic()
        await scanner.start()
        try:
            while duration_seconds is None or time.monotonic() - started_at < duration_seconds:
                await asyncio.sleep(0.25)
                for change in self.sensor.mark_lost_if_stale():
                    on_change(change)
        finally:
            await scanner.stop()

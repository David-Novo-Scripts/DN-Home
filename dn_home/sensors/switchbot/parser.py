"""Deterministic parser for SwitchBot Contact Sensor service data."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


CONTACT_MODEL = "d"
CONTACT_PAIR_MODEL = "D"
CONTACT_SERVICE_DATA_LENGTH = 9


class SwitchBotAdvertisementError(ValueError):
    """Raised when Contact Sensor service data is malformed or unsupported."""


class DoorState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    TIMEOUT = "timeout"


@dataclass(frozen=True, slots=True)
class ContactAdvertisement:
    model: str
    tested: bool
    motion_detected: bool
    battery: int
    door: DoorState
    is_light: bool
    seconds_since_motion: int
    seconds_since_hall: int
    entrance_counter: int
    go_out_counter: int
    button_counter: int

    @property
    def is_pair_mode(self) -> bool:
        return self.model == CONTACT_PAIR_MODEL

    @property
    def contact_open(self) -> bool:
        return self.door is not DoorState.CLOSED

    @property
    def contact_timeout(self) -> bool:
        return self.door is DoorState.TIMEOUT


def parse_contact_service_data(data: bytes) -> ContactAdvertisement:
    """Parse the nine-byte FD3D/000D Contact Sensor service payload.

    The bit layout follows SwitchBot's Contact Sensor BLE Open API. Pair-mode
    payloads are returned for diagnostics; callers decide whether to ignore
    them for operational state.
    """

    if len(data) != CONTACT_SERVICE_DATA_LENGTH:
        raise SwitchBotAdvertisementError(
            "Contact Sensor service data must contain exactly 9 bytes"
        )

    model = chr(data[0] & 0x7F)
    if model not in {CONTACT_MODEL, CONTACT_PAIR_MODEL}:
        raise SwitchBotAdvertisementError(
            f"Unsupported Contact Sensor device type 0x{data[0] & 0x7F:02x}"
        )

    battery = data[2] & 0x7F
    if battery > 100:
        raise SwitchBotAdvertisementError(f"Invalid battery percentage: {battery}")

    door_code = (data[3] >> 1) & 0x03
    try:
        door = {
            0: DoorState.CLOSED,
            1: DoorState.OPEN,
            2: DoorState.TIMEOUT,
        }[door_code]
    except KeyError as error:
        raise SwitchBotAdvertisementError(
            f"Invalid Contact Sensor door state: {door_code}"
        ) from error

    pir_high_bit = 0x10000 if data[3] & 0x80 else 0
    hall_high_bit = 0x10000 if data[3] & 0x40 else 0
    action_counter = data[8]

    return ContactAdvertisement(
        model=model,
        tested=bool(data[1] & 0x80),
        motion_detected=bool(data[1] & 0x40),
        battery=battery,
        door=door,
        is_light=bool(data[3] & 0x01),
        seconds_since_motion=pir_high_bit | int.from_bytes(data[4:6], "big"),
        seconds_since_hall=hall_high_bit | int.from_bytes(data[6:8], "big"),
        entrance_counter=(action_counter >> 6) & 0x03,
        go_out_counter=(action_counter >> 4) & 0x03,
        button_counter=action_counter & 0x0F,
    )

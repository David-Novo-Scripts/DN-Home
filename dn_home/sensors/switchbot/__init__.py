"""SwitchBot BLE Contact Sensor support."""

from dn_home.sensors.switchbot.contact import (
    ContactSensorChange,
    ContactSensorState,
    SwitchBotContactSensor,
)
from dn_home.sensors.switchbot.parser import (
    ContactAdvertisement,
    DoorState,
    SwitchBotAdvertisementError,
    parse_contact_service_data,
)
from dn_home.sensors.switchbot.provider import SwitchBotBLEProvider

__all__ = [
    "ContactAdvertisement",
    "ContactSensorChange",
    "ContactSensorState",
    "DoorState",
    "SwitchBotAdvertisementError",
    "SwitchBotBLEProvider",
    "SwitchBotContactSensor",
    "parse_contact_service_data",
]

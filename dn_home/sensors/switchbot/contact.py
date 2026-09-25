"""State and event projection for a SwitchBot Contact Sensor."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import time
from typing import Any, Callable

from dn_home.core.events import Event, EventBus
from dn_home.sensors.switchbot.parser import ContactAdvertisement, DoorState


@dataclass(frozen=True, slots=True)
class ContactSensorState:
    door: DoorState
    motion: bool
    light: bool
    battery: int
    entrance_counter: int
    go_out_counter: int
    button_counter: int
    last_seen: datetime
    rssi: int


@dataclass(frozen=True, slots=True)
class ContactSensorChange:
    field: str
    previous: Any
    current: Any
    state: ContactSensorState


ChangeHandler = Callable[[ContactSensorChange], None]


class SwitchBotContactSensor:
    """Maintain Contact Sensor state and publish deduplicated transitions."""

    def __init__(
        self,
        name: str,
        address: str,
        *,
        stale_after_seconds: float,
        events: EventBus | None = None,
    ) -> None:
        self.name = name
        self.address = address.upper()
        self.stale_after_seconds = stale_after_seconds
        self.events = events
        self.state: ContactSensorState | None = None
        self._last_seen_monotonic: float | None = None
        self._online = False

    def update(
        self,
        advertisement: ContactAdvertisement,
        *,
        rssi: int,
        seen_at: datetime | None = None,
        monotonic_at: float | None = None,
    ) -> list[ContactSensorChange]:
        """Apply one normal-mode advertisement and return relevant changes."""

        if advertisement.is_pair_mode:
            return []

        seen_at = seen_at or datetime.now(timezone.utc)
        monotonic_at = time.monotonic() if monotonic_at is None else monotonic_at
        new_state = ContactSensorState(
            door=advertisement.door,
            motion=advertisement.motion_detected,
            light=advertisement.is_light,
            battery=advertisement.battery,
            entrance_counter=advertisement.entrance_counter,
            go_out_counter=advertisement.go_out_counter,
            button_counter=advertisement.button_counter,
            last_seen=seen_at,
            rssi=rssi,
        )
        previous = self.state
        self.state = new_state
        self._last_seen_monotonic = monotonic_at

        if not self._online:
            self._online = True
            change = ContactSensorChange("seen", False, True, new_state)
            self._publish("door.sensor_seen", new_state)
            return [change]

        if previous is None:
            return []

        changes: list[ContactSensorChange] = []
        tracked_fields = (
            "door",
            "motion",
            "light",
            "battery",
            "entrance_counter",
            "go_out_counter",
            "button_counter",
        )
        for field in tracked_fields:
            old_value = getattr(previous, field)
            new_value = getattr(new_state, field)
            if old_value != new_value:
                changes.append(
                    ContactSensorChange(field, old_value, new_value, new_state)
                )

        if previous.door is not new_state.door:
            event_name = {
                DoorState.OPEN: "door.opened",
                DoorState.CLOSED: "door.closed",
                DoorState.TIMEOUT: "door.left_open",
            }[new_state.door]
            self._publish(event_name, new_state, previous=previous.door.value)
        if not previous.motion and new_state.motion:
            self._publish("door.motion_detected", new_state)
        if previous.light != new_state.light:
            self._publish(
                "door.light_changed",
                new_state,
                previous=previous.light,
            )
        return changes

    def mark_lost_if_stale(
        self,
        *,
        monotonic_at: float | None = None,
    ) -> list[ContactSensorChange]:
        """Mark the sensor lost once after its advertisement deadline passes."""

        if not self._online or self.state is None or self._last_seen_monotonic is None:
            return []
        monotonic_at = time.monotonic() if monotonic_at is None else monotonic_at
        if monotonic_at - self._last_seen_monotonic < self.stale_after_seconds:
            return []
        self._online = False
        change = ContactSensorChange("seen", True, False, self.state)
        self._publish("door.sensor_lost", self.state)
        return [change]

    def _publish(
        self,
        event_name: str,
        state: ContactSensorState,
        **extra: Any,
    ) -> None:
        if self.events is None:
            return
        self.events.publish(
            Event(
                event_name,
                {
                    "sensor": self.name,
                    "address": self.address,
                    "door": state.door.value,
                    "motion": state.motion,
                    "light": state.light,
                    "battery": state.battery,
                    "rssi": state.rssi,
                    **extra,
                },
            )
        )

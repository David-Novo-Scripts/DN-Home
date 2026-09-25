from datetime import datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from dn_home.core.events import EventBus
from dn_home.sensors.switchbot import (
    DoorState,
    SwitchBotAdvertisementError,
    SwitchBotBLEProvider,
    SwitchBotContactSensor,
    parse_contact_service_data,
)


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "switchbot_contact_advertisements.json"
FD3D_UUID = "0000fd3d-0000-1000-8000-00805f9b34fb"
ADDRESS = "E3:98:BB:9A:FE:85"
CLOSED = bytes.fromhex("6420e401009d00d345")


def _parsed(payload: bytes = CLOSED):
    return parse_contact_service_data(payload)


def _sensor(events: EventBus | None = None, stale_after: float = 15):
    return SwitchBotContactSensor(
        "entry_contact",
        ADDRESS,
        stale_after_seconds=stale_after,
        events=events,
    )


def test_official_fixtures_parse_expected_contact_fields() -> None:
    fixtures = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))["fixtures"]

    for fixture in fixtures:
        parsed = parse_contact_service_data(bytes.fromhex(fixture["service_data_hex"]))
        expected = fixture["expected"]
        assert parsed.model == expected["model"]
        assert parsed.battery == expected["battery"]
        assert parsed.contact_open is expected["contact_open"]
        assert parsed.is_light is expected["light"]
        assert parsed.motion_detected is expected["motion"]
        assert parsed.button_counter == expected["button_count"]


def test_action_counters_and_elapsed_times_follow_official_bit_layout() -> None:
    parsed = _parsed()

    assert parsed.door is DoorState.CLOSED
    assert parsed.seconds_since_motion == 157
    assert parsed.seconds_since_hall == 211
    assert parsed.entrance_counter == 1
    assert parsed.go_out_counter == 0
    assert parsed.button_counter == 5


@pytest.mark.parametrize(
    "payload",
    (
        b"",
        bytes.fromhex("6420e401009d00d3"),
        bytes.fromhex("7820e401009d00d345"),
        bytes.fromhex("6420e406009d00d345"),
    ),
)
def test_invalid_contact_payload_is_rejected(payload: bytes) -> None:
    with pytest.raises(SwitchBotAdvertisementError):
        parse_contact_service_data(payload)


def test_pair_mode_is_diagnostic_only_and_does_not_change_sensor_state() -> None:
    sensor = _sensor()
    pair = _parsed(bytes.fromhex("4460e401002b018946"))

    assert pair.is_pair_mode is True
    assert sensor.update(pair, rssi=-50, monotonic_at=1) == []
    assert sensor.state is None


def test_closed_open_closed_and_timeout_publish_one_event_each() -> None:
    bus = EventBus()
    published = []
    bus.subscribe("*", published.append)
    sensor = _sensor(bus)
    seen_at = datetime(2026, 9, 25, 20, 0, tzinfo=timezone.utc)

    sensor.update(_parsed(), rssi=-54, seen_at=seen_at, monotonic_at=1)
    open_changes = sensor.update(
        _parsed(bytes.fromhex("6420e403009d00d345")),
        rssi=-53,
        seen_at=seen_at,
        monotonic_at=2,
    )
    sensor.update(_parsed(), rssi=-52, seen_at=seen_at, monotonic_at=3)
    sensor.update(
        _parsed(bytes.fromhex("6420e405009d00d345")),
        rssi=-51,
        seen_at=seen_at,
        monotonic_at=4,
    )

    assert [(change.field, change.previous, change.current) for change in open_changes] == [
        ("door", DoorState.CLOSED, DoorState.OPEN)
    ]
    assert [event.name for event in published] == [
        "door.sensor_seen",
        "door.opened",
        "door.closed",
        "door.left_open",
    ]


def test_motion_and_light_changes_publish_semantic_events() -> None:
    bus = EventBus()
    published = []
    bus.subscribe("*", published.append)
    sensor = _sensor(bus)
    sensor.update(_parsed(), rssi=-54, monotonic_at=1)

    changes = sensor.update(
        _parsed(bytes.fromhex("6460e400009d00d345")),
        rssi=-54,
        monotonic_at=2,
    )

    assert [(change.field, change.current) for change in changes] == [
        ("motion", True),
        ("light", False),
    ]
    assert [event.name for event in published] == [
        "door.sensor_seen",
        "door.motion_detected",
        "door.light_changed",
    ]


def test_duplicate_advertisement_only_refreshes_last_seen_and_rssi() -> None:
    bus = EventBus()
    published = []
    bus.subscribe("*", published.append)
    sensor = _sensor(bus)
    first_seen = datetime(2026, 9, 25, 20, 0, tzinfo=timezone.utc)
    second_seen = datetime(2026, 9, 25, 20, 0, 1, tzinfo=timezone.utc)
    sensor.update(_parsed(), rssi=-60, seen_at=first_seen, monotonic_at=1)

    changes = sensor.update(
        _parsed(), rssi=-50, seen_at=second_seen, monotonic_at=2
    )

    assert changes == []
    assert sensor.state is not None
    assert sensor.state.last_seen == second_seen
    assert sensor.state.rssi == -50
    assert [event.name for event in published] == ["door.sensor_seen"]


def test_stale_sensor_emits_lost_once_and_seen_again_after_recovery() -> None:
    bus = EventBus()
    published = []
    bus.subscribe("*", published.append)
    sensor = _sensor(bus, stale_after=10)
    sensor.update(_parsed(), rssi=-54, monotonic_at=1)

    assert sensor.mark_lost_if_stale(monotonic_at=10.9) == []
    assert len(sensor.mark_lost_if_stale(monotonic_at=11)) == 1
    assert sensor.mark_lost_if_stale(monotonic_at=20) == []
    assert len(sensor.update(_parsed(), rssi=-53, monotonic_at=21)) == 1
    assert [event.name for event in published] == [
        "door.sensor_seen",
        "door.sensor_lost",
        "door.sensor_seen",
    ]


@pytest.mark.asyncio
async def test_bleak_provider_filters_address_and_deduplicates() -> None:
    instances = []

    class FakeScanner:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.stopped = False
            instances.append(self)

        async def start(self):
            callback = self.kwargs["detection_callback"]
            advertisement = SimpleNamespace(
                service_data={FD3D_UUID: CLOSED},
                manufacturer_data={2409: bytes.fromhex("e398bb9afe85534c009e00d445")},
                rssi=-54,
            )
            callback(SimpleNamespace(address="00:00:00:00:00:00"), advertisement)
            callback(SimpleNamespace(address=ADDRESS), advertisement)
            callback(SimpleNamespace(address=ADDRESS), advertisement)

        async def stop(self):
            self.stopped = True

    changes = []
    sensor = _sensor(stale_after=60)
    provider = SwitchBotBLEProvider(
        sensor, adapter="hci0", scanner_factory=FakeScanner
    )

    await provider.monitor(on_change=changes.append, duration_seconds=0.01)

    assert len(changes) == 1
    assert changes[0].field == "seen"
    assert instances[0].kwargs["scanning_mode"] == "active"
    assert instances[0].kwargs["bluez"] == {"adapter": "hci0"}
    assert instances[0].stopped is True

from datetime import datetime
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

import pytest

from dn_home.core.config import TransitConfig, TransitStopConfig
from dn_home.skills.transit.base import TransitUnavailable
from dn_home.skills.transit.idfm import IDFMNavitiaProvider
from dn_home.skills.transit.service import format_transit_response


PARIS = ZoneInfo("Europe/Paris")


def transit_config() -> TransitConfig:
    origin = TransitStopConfig(
        "Noisy-le-Grand - Mont d'Est",
        "IDFM:monomodalStopPlace:474082",
        "stop_area:IDFM:412697",
        "STIF:StopArea:SP:474082:",
    )
    return TransitConfig(
        provider="idfm_navitia",
        api_base="https://example.test/navitia",
        token_env="TEST_IDFM_TOKEN",
        line_name="RER A",
        line_id="IDFM:C01742",
        line_code="A",
        commercial_mode="RER",
        origin=origin,
        destinations={
            "work": TransitStopConfig(
                "Lognes",
                "IDFM:monomodalStopPlace:43152",
                "stop_area:IDFM:68123",
                "STIF:StopArea:SP:43152:",
            ),
            "paris": TransitStopConfig(
                "Nation",
                "IDFM:monomodalStopPlace:473875",
                "stop_area:IDFM:71673",
                None,
            ),
        },
        timeout=10,
        result_count=2,
    )


def journey(
    departure: str,
    destination_stop_id: str,
    *,
    freshness: str = "realtime",
    code: str = "A",
    transfers: int = 0,
    status: str = "standard",
) -> dict:
    return {
        "departure_date_time": departure,
        "nb_transfers": transfers,
        "status": status,
        "sections": [
            {
                "type": "public_transport",
                "departure_date_time": departure,
                "data_freshness": freshness,
                "display_informations": {
                    "commercial_mode": "RER",
                    "code": code,
                    "direction": "Torcy (Torcy)",
                },
                "from": {"id": "stop_point:IDFM:monomodalStopPlace:474082"},
                "to": {"id": f"stop_point:{destination_stop_id}"},
            }
        ],
    }


def provider(monkeypatch: pytest.MonkeyPatch, payload: dict) -> IDFMNavitiaProvider:
    monkeypatch.setenv("TEST_IDFM_TOKEN", "not-logged-secret")

    def transport(url, headers, timeout):
        assert headers["apikey"] == "not-logged-secret"
        assert timeout == 10
        return payload

    return IDFMNavitiaProvider(
        transit_config(),
        transport=transport,
        now=lambda: datetime(2026, 9, 21, 8, 0, tzinfo=PARIS),
    )


def test_work_query_uses_configured_origin_and_destination(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = provider(
        monkeypatch,
        {"journeys": [journey("20260921T080600", "IDFM:monomodalStopPlace:43152")]},
    )

    result = client.next("work")
    query = parse_qs(urlsplit(client._url(client.config.destinations["work"])).query)

    assert query["from"] == ["stop_area:IDFM:412697"]
    assert query["to"] == ["stop_area:IDFM:68123"]
    assert query["data_freshness"] == ["realtime"]
    assert result.destination == "work"
    assert result.destination_name == "Lognes"
    assert result.minutes == 6
    assert result.realtime is True


def test_paris_returns_two_next_direct_trains(monkeypatch: pytest.MonkeyPatch) -> None:
    client = provider(
        monkeypatch,
        {
            "journeys": [
                journey("20260921T080900", "IDFM:monomodalStopPlace:473875"),
                journey("20260921T080400", "IDFM:monomodalStopPlace:473875"),
            ]
        },
    )

    result = client.next("paris")

    assert result.minutes == 4
    assert result.following_minutes == (9,)
    assert format_transit_response(result) == (
        "o próximo RER A para Paris passa daqui a 4 minutos "
        "e o seguinte daqui a 9 minutos."
    )


def test_filters_journey_that_does_not_reach_destination(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = provider(
        monkeypatch,
        {"journeys": [journey("20260921T080400", "IDFM:monomodalStopPlace:99999")]},
    )

    with pytest.raises(TransitUnavailable, match="No direct RER A"):
        client.next("work")


def test_filters_transfers_and_other_lines(monkeypatch: pytest.MonkeyPatch) -> None:
    client = provider(
        monkeypatch,
        {
            "journeys": [
                journey(
                    "20260921T080400",
                    "IDFM:monomodalStopPlace:43152",
                    transfers=1,
                ),
                journey(
                    "20260921T080500",
                    "IDFM:monomodalStopPlace:43152",
                    code="E",
                ),
            ]
        },
    )

    with pytest.raises(TransitUnavailable, match="No direct RER A"):
        client.next("work")


def test_absence_of_realtime_is_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    client = provider(
        monkeypatch,
        {
            "journeys": [
                journey(
                    "20260921T080600",
                    "IDFM:monomodalStopPlace:43152",
                    freshness="base_schedule",
                )
            ]
        },
    )

    result = client.next("work")

    assert result.realtime is False
    assert format_transit_response(result).startswith("Segundo o horário planeado")


def test_unavailable_api_never_invents_a_time(monkeypatch: pytest.MonkeyPatch) -> None:
    client = provider(monkeypatch, {"error": {"message": "service unavailable"}})

    with pytest.raises(TransitUnavailable, match="service unavailable"):
        client.next("paris")


def test_missing_token_is_controlled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TEST_IDFM_TOKEN", raising=False)
    client = IDFMNavitiaProvider(transit_config(), transport=lambda *_: {})

    with pytest.raises(TransitUnavailable, match="TEST_IDFM_TOKEN"):
        client.next("work")

"""Île-de-France Mobilités Navitia journeys provider."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
import json
import math
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from dn_home.core.config import TransitConfig, TransitStopConfig
from dn_home.skills.transit.base import (
    TransitNoDirectService,
    TransitUnavailable,
    TransitProvider,
)
from dn_home.skills.transit.models import TransitResult


PARIS_TZ = ZoneInfo("Europe/Paris")
JsonTransport = Callable[[str, dict[str, str], float], dict[str, Any]]


def _http_json(url: str, headers: dict[str, str], timeout: float) -> dict[str, Any]:
    request = Request(url, headers=headers)
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except HTTPError as error:
        raise TransitUnavailable(f"IDFM returned HTTP {error.code}") from error
    except (URLError, TimeoutError, json.JSONDecodeError) as error:
        raise TransitUnavailable("IDFM is unavailable or returned an invalid response") from error


def _parse_datetime(value: Any) -> datetime:
    try:
        parsed = datetime.strptime(str(value), "%Y%m%dT%H%M%S")
    except (TypeError, ValueError) as error:
        raise TransitUnavailable("IDFM returned an invalid departure time") from error
    return parsed.replace(tzinfo=PARIS_TZ)


def _stop_matches(section_end: Any, expected: TransitStopConfig) -> bool:
    if not isinstance(section_end, dict):
        return False
    expected_id = f"stop_point:{expected.stop_id}"
    return section_end.get("id") == expected_id


class IDFMNavitiaProvider(TransitProvider):
    def __init__(
        self,
        config: TransitConfig,
        *,
        transport: JsonTransport = _http_json,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.config = config
        self._transport = transport
        self._now = now or (lambda: datetime.now(PARIS_TZ))

    def _token(self) -> str:
        token = os.environ.get(self.config.token_env, "").strip()
        if not token:
            raise TransitUnavailable(
                f"Transit credential is missing from {self.config.token_env}"
            )
        return token

    def _url(self, destination: TransitStopConfig) -> str:
        params = urlencode(
            {
                "from": self.config.origin.navitia_id,
                "to": destination.navitia_id,
                "data_freshness": "realtime",
                "count": max(self.config.result_count + 2, 3),
                "disable_geojson": "true",
            }
        )
        return f"{self.config.api_base}/journeys?{params}"

    def next(self, destination: str) -> TransitResult:
        alias = destination.strip().lower()
        target = self.config.destinations.get(alias)
        if target is None:
            raise TransitUnavailable(f"Unknown transit destination: {destination}")

        payload = self._transport(
            self._url(target),
            {"Accept": "application/json", "apikey": self._token()},
            self.config.timeout,
        )
        if not isinstance(payload, dict):
            raise TransitUnavailable("IDFM returned an invalid response")

        error = payload.get("error") or {}
        detail = error.get("message") if isinstance(error, dict) else None
        if detail:
            raise TransitUnavailable(str(detail))

        journeys = payload.get("journeys")
        if not isinstance(journeys, list):
            raise TransitUnavailable("IDFM returned an invalid journeys response")

        departures: list[tuple[datetime, str, bool, str]] = []
        for journey in journeys:
            if not isinstance(journey, dict):
                raise TransitUnavailable("IDFM returned an invalid journey")
            if journey.get("nb_transfers") != 0:
                continue
            sections = journey.get("sections")
            if not isinstance(sections, list):
                raise TransitUnavailable("IDFM returned invalid journey sections")
            public_sections = [
                section
                for section in sections
                if isinstance(section, dict) and section.get("type") == "public_transport"
            ]
            if len(public_sections) != 1:
                continue
            section = public_sections[0]
            display = section.get("display_informations") or {}
            if (
                display.get("commercial_mode") != self.config.commercial_mode
                or display.get("code") != self.config.line_code
            ):
                continue
            if not _stop_matches(section.get("from"), self.config.origin):
                continue
            if not _stop_matches(section.get("to"), target):
                continue
            departure_time = _parse_datetime(section.get("departure_date_time"))
            departures.append(
                (
                    departure_time,
                    str(display.get("direction") or "").strip(),
                    section.get("data_freshness") == "realtime",
                    str(journey.get("status") or "standard"),
                )
            )

        if not departures:
            raise TransitNoDirectService(alias, self.config.line_name)

        now = self._now().astimezone(PARIS_TZ)
        departures.sort(key=lambda item: item[0])
        unique: list[tuple[datetime, str, bool, str]] = []
        seen: set[datetime] = set()
        for item in departures:
            if item[0] >= now and item[0] not in seen:
                seen.add(item[0])
                unique.append(item)
            if len(unique) >= self.config.result_count:
                break
        if not unique:
            raise TransitNoDirectService(alias, self.config.line_name)

        minutes = [max(0, math.ceil((item[0] - now).total_seconds() / 60)) for item in unique]
        first = unique[0]
        return TransitResult(
            destination=alias,
            destination_name=target.name,
            line=self.config.line_name,
            departure_time=first[0],
            minutes=minutes[0],
            direction=first[1],
            realtime=first[2],
            status=first[3],
            following_minutes=tuple(minutes[1:]),
        )

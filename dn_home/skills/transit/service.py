"""Transit skill response formatting."""

from __future__ import annotations

from dn_home.skills.transit.base import TransitProvider
from dn_home.skills.transit.models import TransitResult


def _minutes_text(minutes: int) -> str:
    if minutes == 0:
        return "agora"
    if minutes == 1:
        return "daqui a 1 minuto"
    return f"daqui a {minutes} minutos"


def format_transit_response(result: TransitResult) -> str:
    destination = "o trabalho" if result.destination == "work" else "Paris"
    prefix = "" if result.realtime else "Segundo o horário planeado, "
    first = _minutes_text(result.minutes)
    if result.following_minutes:
        following = _minutes_text(result.following_minutes[0])
        return (
            f"{prefix}o próximo {result.line} para {destination} passa {first} "
            f"e o seguinte {following}."
        )
    return f"{prefix}o próximo {result.line} para {destination} passa {first}."


class TransitSkill:
    def __init__(self, provider: TransitProvider) -> None:
        self.provider = provider

    def next(self, destination: str) -> tuple[TransitResult, str]:
        result = self.provider.next(destination)
        return result, format_transit_response(result)

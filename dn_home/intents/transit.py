"""Deterministic Portuguese parser for the initial transit intents."""

from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata


@dataclass(frozen=True, slots=True)
class TransitNextIntent:
    destination: str


def _normalize(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text.casefold())
    without_accents = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", without_accents).strip()


def parse_transit_intent(text: str) -> TransitNextIntent | None:
    """Recognize only the narrow transit command set approved for the PoC."""

    normalized = _normalize(text)
    if not re.search(r"\b(proximo|quando)\b", normalized):
        return None
    if not re.search(r"\b(comboio|rer|passa|e)\b", normalized):
        return None
    if re.search(r"\b(trabalho)\b", normalized):
        return TransitNextIntent("work")
    if re.search(r"\b(paris)\b", normalized):
        return TransitNextIntent("paris")
    return None

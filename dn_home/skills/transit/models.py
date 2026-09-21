"""Structured transit results."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class TransitResult:
    destination: str
    destination_name: str
    line: str
    departure_time: datetime
    minutes: int
    direction: str
    realtime: bool
    status: str
    following_minutes: tuple[int, ...] = ()

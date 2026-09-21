"""Small in-process event bus used by DN Home runtimes."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class Event:
    name: str
    data: dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: uuid4().hex)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


EventHandler = Callable[[Event], None]


class EventBus:
    """Synchronous event bus suitable for the single-process PoC."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)

    def subscribe(self, name: str, handler: EventHandler) -> None:
        self._handlers[name].append(handler)

    def publish(self, event: Event) -> None:
        for handler in (*self._handlers.get(event.name, ()), *self._handlers.get("*", ())):
            handler(event)

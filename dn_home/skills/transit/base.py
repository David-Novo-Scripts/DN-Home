"""Transit provider contract."""

from __future__ import annotations

from abc import ABC, abstractmethod

from dn_home.skills.transit.models import TransitResult


class TransitError(RuntimeError):
    """Base class for controlled transit failures."""


class TransitUnavailable(TransitError):
    """Raised when no trustworthy result can be obtained."""


class TransitNoDirectService(TransitUnavailable):
    """Raised when a valid response contains no eligible direct service."""

    def __init__(self, destination: str, line: str) -> None:
        super().__init__(f"No direct {line} journey was returned")
        self.destination = destination
        self.line = line


class TransitProvider(ABC):
    @abstractmethod
    def next(self, destination: str) -> TransitResult:
        """Return the next direct service that reaches the configured destination."""

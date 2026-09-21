"""Transit provider contract."""

from __future__ import annotations

from abc import ABC, abstractmethod

from dn_home.skills.transit.models import TransitResult


class TransitError(RuntimeError):
    """Base class for controlled transit failures."""


class TransitUnavailable(TransitError):
    """Raised when no trustworthy result can be obtained."""


class TransitProvider(ABC):
    @abstractmethod
    def next(self, destination: str) -> TransitResult:
        """Return the next direct service that reaches the configured destination."""

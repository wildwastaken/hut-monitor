from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import Opening, Watch


class ProviderError(Exception):
    """Raised when a provider couldn't complete a check (network, bad data...).

    The runner treats this as "unknown" and leaves alert state untouched, so a
    transient failure never looks like everything disappeared.
    """


class Provider(ABC):
    name: str = "base"
    supported: bool = True

    @abstractmethod
    def check(self, watch: Watch) -> list[Opening]:
        """Return every opening currently matching `watch`."""

    def booking_url(self, watch: Watch) -> str:
        return watch.url or ""

    def rate_key(self, watch: Watch) -> str:
        """Key used for per-target polling limits."""
        return f"{self.name}:{watch.campground_id}"

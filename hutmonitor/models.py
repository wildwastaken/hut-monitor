from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta


@dataclass(frozen=True)
class Watch:
    name: str
    provider: str
    campground_id: str
    arrive: date
    nights: int = 1
    # Optional: latest acceptable arrival date (flexible window). Defaults to `arrive`.
    arrive_end: date | None = None
    site_types: tuple[str, ...] = ()  # case-insensitive substring match, e.g. "TENT"
    loops: tuple[str, ...] = ()  # case-insensitive exact match
    sites: tuple[str, ...] = ()  # exact site numbers/names, e.g. "044"
    min_interval_s: int = 300  # never poll this campground more often than this
    url: str | None = None  # override booking URL (useful for AMC)

    def arrival_dates(self) -> list[date]:
        end = self.arrive_end or self.arrive
        n = (end - self.arrive).days
        return [self.arrive + timedelta(days=i) for i in range(n + 1)]

    def last_night(self) -> date:
        return (self.arrive_end or self.arrive) + timedelta(days=self.nights - 1)


@dataclass(frozen=True)
class Opening:
    watch: str
    provider: str
    campground: str  # campground id or name
    site: str  # human site name/number
    nights: tuple[date, ...]  # every night of the stay
    url: str
    site_id: str = ""
    loop: str = ""
    site_type: str = ""
    note: str = ""
    extra: dict = field(default_factory=dict, compare=False, hash=False)

    @property
    def arrive(self) -> date:
        return self.nights[0]

    @property
    def depart(self) -> date:
        return self.nights[-1] + timedelta(days=1)

    def key(self) -> str:
        """Stable identity used for dedupe."""
        return f"{self.provider}:{self.campground}:{self.site_id or self.site}:{self.arrive.isoformat()}:{len(self.nights)}"

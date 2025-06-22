"""Recreation.gov provider, using the availability endpoint the website uses."""
from __future__ import annotations

from datetime import date, timedelta

import httpx

from ..http import PoliteClient
from ..models import Opening, Watch
from .base import Provider, ProviderError

BASE = "https://www.recreation.gov"
AVAIL_URL = BASE + "/api/camps/availability/campground/{cid}/month"
SEARCH_URL = BASE + "/api/search"
AVAILABLE = "Available"


def campground_url(cid: str) -> str:
    return f"{BASE}/camping/campgrounds/{cid}"


def campsite_url(site_id: str) -> str:
    return f"{BASE}/camping/campsites/{site_id}"


def months_needed(watch: Watch) -> list[date]:
    """First-of-month dates covering every night we might need."""
    first, last = watch.arrive, watch.last_night()
    out, cur = [], first.replace(day=1)
    while cur <= last:
        out.append(cur)
        cur = (cur.replace(day=28) + timedelta(days=4)).replace(day=1)
    return out


def merge_months(payloads: list[dict]) -> dict[str, dict]:
    """Merge several month payloads into one campsites dict with combined availabilities."""
    merged: dict[str, dict] = {}
    for p in payloads:
        for sid, site in (p.get("campsites") or {}).items():
            cur = merged.setdefault(sid, {**site, "availabilities": {}})
            cur["availabilities"].update(site.get("availabilities") or {})
    return merged


def _night_status(site: dict) -> dict[date, str]:
    out = {}
    for k, v in (site.get("availabilities") or {}).items():
        try:
            out[date.fromisoformat(k[:10])] = v
        except ValueError:
            continue
    return out


def _matches_filters(site: dict, watch: Watch) -> bool:
    if watch.site_types:
        st = (site.get("campsite_type") or "").lower()
        if not any(t.lower() in st for t in watch.site_types):
            return False
    if watch.loops:
        lp = (site.get("loop") or "").lower()
        if lp not in {l.lower() for l in watch.loops}:
            return False
    if watch.sites and str(site.get("site")) not in set(watch.sites):
        return False
    return True


def find_openings(campsites: dict[str, dict], watch: Watch) -> list[Opening]:
    """Pure function: every (site, arrival) where all `nights` nights are Available."""
    openings = []
    for sid, site in campsites.items():
        if not _matches_filters(site, watch):
            continue
        status = _night_status(site)
        for arrive in watch.arrival_dates():
            nights = tuple(arrive + timedelta(days=i) for i in range(watch.nights))
            if all(status.get(n) == AVAILABLE for n in nights):
                site_id = str(site.get("campsite_id") or sid)
                openings.append(
                    Opening(
                        watch=watch.name,
                        provider="recgov",
                        campground=str(watch.campground_id),
                        site=str(site.get("site", sid)),
                        site_id=site_id,
                        loop=site.get("loop") or "",
                        site_type=site.get("campsite_type") or "",
                        nights=nights,
                        url=campsite_url(site_id),
                    )
                )
    openings.sort(key=lambda o: (o.arrive, o.loop, o.site))
    return openings


class RecGovProvider(Provider):
    name = "recgov"

    def __init__(self, http: PoliteClient | None = None):
        self.http = http or PoliteClient()
        self._cache: dict[tuple[str, date], dict] = {}  # per-pass memo, shared by watches

    def booking_url(self, watch: Watch) -> str:
        return watch.url or campground_url(watch.campground_id)

    def fetch_month(self, cid: str, month: date) -> dict:
        key = (cid, month)
        if key not in self._cache:
            self._cache[key] = self.http.get_json(
                AVAIL_URL.format(cid=cid),
                params={"start_date": month.strftime("%Y-%m-01T00:00:00.000Z")},
            )
        return self._cache[key]

    def check(self, watch: Watch) -> list[Opening]:
        try:
            payloads = [self.fetch_month(watch.campground_id, m) for m in months_needed(watch)]
        except (httpx.HTTPError, ValueError) as e:
            raise ProviderError(f"recreation.gov fetch failed for {watch.campground_id}: {e}") from e
        return find_openings(merge_months(payloads), watch)

    def search(self, query: str, limit: int = 10) -> list[dict]:
        data = self.http.get_json(
            SEARCH_URL, params={"q": query, "fq": "entity_type:campground", "size": limit}
        )
        return [
            {
                "id": r.get("entity_id"),
                "name": r.get("name"),
                "parent": r.get("parent_name"),
                "state": r.get("state_code"),
            }
            for r in data.get("results") or []
        ]

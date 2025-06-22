from __future__ import annotations

import tomllib
from datetime import date
from pathlib import Path

from .models import Watch

MIN_INTERVAL_FLOOR_S = 300  # 5 minutes per campground, the polite default


def _tuple(v) -> tuple[str, ...]:
    if v is None:
        return ()
    if isinstance(v, (str, int)):
        return (str(v),)
    return tuple(str(x) for x in v)


def _date(v) -> date:
    return v if isinstance(v, date) else date.fromisoformat(str(v))


def parse_watches(data: dict) -> list[Watch]:
    watches = []
    for i, w in enumerate(data.get("watch", [])):
        try:
            nights = int(w.get("nights", 1))
            if nights < 1:
                raise ValueError("nights must be >= 1")
            arrive = _date(w["arrive"])
            arrive_end = _date(w["arrive_end"]) if w.get("arrive_end") else None
            if arrive_end and arrive_end < arrive:
                raise ValueError("arrive_end is before arrive")
            watches.append(
                Watch(
                    name=w["name"],
                    provider=w.get("provider", "recgov"),
                    campground_id=str(w["campground_id"]),
                    arrive=arrive,
                    nights=nights,
                    arrive_end=arrive_end,
                    site_types=_tuple(w.get("site_types")),
                    loops=_tuple(w.get("loops")),
                    sites=_tuple(w.get("sites")),
                    min_interval_s=max(int(w.get("min_interval_s", MIN_INTERVAL_FLOOR_S)), 60),
                    url=w.get("url"),
                )
            )
        except KeyError as e:
            raise ValueError(f"watch #{i + 1}: missing required key {e}") from e
    names = [w.name for w in watches]
    if len(set(names)) != len(names):
        raise ValueError("watch names must be unique")
    return watches


def load_watches(path: str | Path) -> list[Watch]:
    with open(path, "rb") as f:
        return parse_watches(tomllib.load(f))

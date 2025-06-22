"""Remember what we've alerted on so only NEW openings fire.

A watch's stored set is replaced with the current set on every successful
check, so an opening that disappears and later comes back alerts again.
"""
from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path

from .models import Opening


class State:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.alerted: dict[str, list[str]] = {}
        self.last_checked: dict[str, float] = {}
        if self.path.exists():
            data = json.loads(self.path.read_text() or "{}")
            self.alerted = data.get("alerted", {})
            self.last_checked = data.get("last_checked", {})

    def diff(self, watch_name: str, current: list[Opening]) -> list[Opening]:
        """Return openings not seen last time and record the current set."""
        prev = set(self.alerted.get(watch_name, []))
        new = [o for o in current if o.key() not in prev]
        self.alerted[watch_name] = sorted({o.key() for o in current})
        return new

    def due(self, rate_key: str, min_interval_s: float, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        return now - self.last_checked.get(rate_key, 0) >= min_interval_s

    def mark_checked(self, rate_key: str, now: float | None = None) -> None:
        self.last_checked[rate_key] = time.time() if now is None else now

    def prune(self, watch_names: set[str]) -> None:
        self.alerted = {k: v for k, v in self.alerted.items() if k in watch_names}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".state-")
        with os.fdopen(fd, "w") as f:
            json.dump({"alerted": self.alerted, "last_checked": self.last_checked}, f, indent=2)
        os.replace(tmp, self.path)

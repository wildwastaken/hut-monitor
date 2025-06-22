from __future__ import annotations

import logging
import subprocess
import sys
from typing import Callable

import httpx

from .models import Opening

log = logging.getLogger(__name__)
DISCORD_LIMIT = 2000


def _fmt_date(d) -> str:
    return d.strftime("%a %b %-d")


def format_opening(o: Opening) -> str:
    n = len(o.nights)
    where = f"site {o.site}"
    if o.loop:
        where += f" ({o.loop})"
    if o.site_type:
        where += f" [{o.site_type}]"
    return (
        f"{o.watch}: {where}, {_fmt_date(o.arrive)} -> {_fmt_date(o.depart)} "
        f"({n} night{'s' if n != 1 else ''}) {o.url}"
    )


def format_summary(openings: list[Opening]) -> str:
    return f"{len(openings)} new opening{'s' if len(openings) != 1 else ''}"


def discord_messages(openings: list[Opening], limit: int = DISCORD_LIMIT) -> list[str]:
    """Split alerts into Discord-sized messages (<= 2000 chars each)."""
    header = f"**hut-monitor: {format_summary(openings)}**"
    msgs, cur = [], header
    for o in openings:
        line = "- " + format_opening(o).replace(o.url, f"<{o.url}>")  # <> suppresses embeds
        if len(line) > limit - 10:
            line = line[: limit - 13] + "..."
        if len(cur) + 1 + len(line) > limit:
            msgs.append(cur)
            cur = line
        else:
            cur += "\n" + line
    msgs.append(cur)
    return msgs


class StdoutNotifier:
    def __init__(self, stream=None):
        self.stream = stream or sys.stdout

    def send(self, openings: list[Opening]) -> None:
        for o in openings:
            print("NEW  " + format_opening(o), file=self.stream, flush=True)


class DiscordNotifier:
    def __init__(self, webhook_url: str, post: Callable | None = None):
        self.webhook_url = webhook_url
        self._post = post or (lambda url, json: httpx.post(url, json=json, timeout=15))

    def send(self, openings: list[Opening]) -> None:
        for msg in discord_messages(openings):
            try:
                r = self._post(self.webhook_url, json={"content": msg, "allowed_mentions": {"parse": []}})
                if getattr(r, "status_code", 204) >= 400:
                    log.error("Discord webhook returned HTTP %s", r.status_code)
            except httpx.HTTPError as e:
                log.error("Discord webhook failed: %s", e)


# Text goes in via argv, never interpolated into the AppleScript source.
_OSA = 'on run argv\ndisplay notification (item 2 of argv) with title (item 1 of argv) sound name "Glass"\nend run'


def mac_notification_args(openings: list[Opening]) -> list[str]:
    title = f"hut-monitor: {format_summary(openings)}"
    first = openings[0]
    body = f"{first.watch}: site {first.site}, {_fmt_date(first.arrive)} ({len(first.nights)}n)"
    if len(openings) > 1:
        body += f" +{len(openings) - 1} more"
    return ["osascript", "-e", _OSA, title, body]


class MacNotifier:
    def __init__(self, run: Callable = subprocess.run):
        self._run = run

    def send(self, openings: list[Opening]) -> None:
        try:
            self._run(mac_notification_args(openings), check=False, capture_output=True)
        except OSError as e:
            log.error("osascript failed: %s", e)

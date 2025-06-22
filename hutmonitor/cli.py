from __future__ import annotations

import argparse
import logging
import os
import random
import re
import sys
import time

from .config import MIN_INTERVAL_FLOOR_S, load_watches
from .notifiers import DiscordNotifier, MacNotifier, StdoutNotifier
from .runner import run_once
from .state import State

log = logging.getLogger("hutmonitor")


def parse_duration(s: str) -> int:
    m = re.fullmatch(r"\s*(\d+)\s*([smhd]?)\s*", s.lower())
    if not m:
        raise argparse.ArgumentTypeError(f"bad duration {s!r} (try 10m, 1h, 600s)")
    return int(m.group(1)) * {"": 1, "s": 1, "m": 60, "h": 3600, "d": 86400}[m.group(2)]


def build_notifiers(mac: bool) -> list:
    ns: list = [StdoutNotifier()]
    hook = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    if hook:
        ns.append(DiscordNotifier(hook))
    if mac:
        ns.append(MacNotifier())
    return ns


def cmd_check(args) -> int:
    watches = load_watches(args.config)
    new = run_once(watches, State(args.state), build_notifiers(args.mac_notify), force=args.force)
    if not new:
        print("no new openings")
    return 0


def cmd_watch(args) -> int:
    every = args.every
    if every < MIN_INTERVAL_FLOOR_S:
        log.warning("--every %ss is below the 5 minute floor; using %ss", every, MIN_INTERVAL_FLOOR_S)
        every = MIN_INTERVAL_FLOOR_S
    notifiers = build_notifiers(args.mac_notify)
    while True:
        try:
            watches = load_watches(args.config)  # re-read so edits apply without restart
            run_once(watches, State(args.state), notifiers)
        except Exception:
            log.exception("check pass failed")
        wait = every * random.uniform(0.9, 1.2)  # jitter so we don't hit on the minute
        log.info("sleeping %.0fs", wait)
        try:
            time.sleep(wait)
        except KeyboardInterrupt:
            return 0


def cmd_find(args) -> int:
    from .providers.recgov import RecGovProvider, campground_url

    results = RecGovProvider().search(args.query, limit=args.limit)
    if not results:
        print("no campgrounds found")
    for r in results:
        print(f"{r['id']:>10}  {r['name']}  ({r['parent']}, {r['state']})  {campground_url(r['id'])}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="hutmonitor", description="Watch campgrounds/huts for openings.")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp):
        sp.add_argument("--config", default="watches.toml")
        sp.add_argument("--state", default="state.json")
        sp.add_argument("--mac-notify", action="store_true", help="also show a macOS notification")

    c = sub.add_parser("check", help="run one pass")
    common(c)
    c.add_argument("--force", action="store_true", help="ignore the per-campground poll interval")
    c.set_defaults(fn=cmd_check)

    w = sub.add_parser("watch", help="loop forever")
    common(w)
    w.add_argument("--every", type=parse_duration, default=parse_duration("10m"))
    w.set_defaults(fn=cmd_watch)

    f = sub.add_parser("find", help="search recreation.gov campground ids")
    f.add_argument("query")
    f.add_argument("--limit", type=int, default=10)
    f.set_defaults(fn=cmd_find)

    args = p.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stderr,
    )
    try:
        return args.fn(args)
    except FileNotFoundError as e:
        print(f"error: {e}. Copy watches.example.toml to watches.toml first.", file=sys.stderr)
        return 2
    except ValueError as e:
        print(f"config error: {e}", file=sys.stderr)
        return 2

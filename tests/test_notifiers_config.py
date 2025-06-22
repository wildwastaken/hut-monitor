import io
from datetime import date

import pytest

from hutmonitor.cli import parse_duration
from hutmonitor.config import parse_watches
from hutmonitor.models import Opening
from hutmonitor.notifiers import (DiscordNotifier, MacNotifier, StdoutNotifier, discord_messages,
                                  format_opening, mac_notification_args)


def O(site="044", nights=2, **kw):
    base = dict(watch="Upper Pines", provider="recgov", campground="232447", site=site, site_id="100",
                loop="Upper Pines", site_type="STANDARD NONELECTRIC",
                nights=tuple(date(2027, 6, 29 + i) if 29 + i <= 30 else date(2027, 7, 29 + i - 30) for i in range(nights)),
                url="https://www.recreation.gov/camping/campsites/100")
    base.update(kw)
    return Opening(**base)


def test_format_opening():
    s = format_opening(O())
    assert s == ("Upper Pines: site 044 (Upper Pines) [STANDARD NONELECTRIC], Tue Jun 29 -> Thu Jul 1 "
                 "(2 nights) https://www.recreation.gov/camping/campsites/100")
    assert "(1 night)" in format_opening(O(nights=1, loop="", site_type=""))


def test_stdout():
    buf = io.StringIO()
    StdoutNotifier(buf).send([O(), O(site="045")])
    assert buf.getvalue().count("NEW  ") == 2


def test_discord_chunking_and_payload():
    ops = [O(site=f"{i:03d}") for i in range(60)]
    msgs = discord_messages(ops)
    assert len(msgs) > 1 and all(len(m) <= 2000 for m in msgs)
    assert msgs[0].startswith("**hut-monitor: 60 new openings**")
    assert "<https://www.recreation.gov/camping/campsites/100>" in msgs[0]
    sent = []
    DiscordNotifier("https://discord.invalid/hook", post=lambda url, json: sent.append(json)).send(ops)
    assert len(sent) == len(msgs) and sent[0]["allowed_mentions"] == {"parse": []}


def test_mac_args_pass_text_via_argv():
    evil = O(watch='x" & do shell script "rm -rf ~')
    args = mac_notification_args([evil, O()])
    assert args[0] == "osascript" and "rm -rf" not in args[2]
    assert args[3] == "hut-monitor: 2 new openings" and args[4].endswith("+1 more")
    calls = []
    MacNotifier(run=lambda a, **k: calls.append(a)).send([O()])
    assert calls[0][0] == "osascript"


def test_parse_watches_and_validation():
    ws = parse_watches({"watch": [{"name": "a", "campground_id": 232447, "arrive": date(2027, 6, 1), "nights": 2,
                                   "site_types": "TENT", "min_interval_s": 5}]})
    assert ws[0].campground_id == "232447" and ws[0].site_types == ("TENT",) and ws[0].min_interval_s == 60
    with pytest.raises(ValueError):
        parse_watches({"watch": [{"name": "a", "arrive": "2027-06-01"}]})
    with pytest.raises(ValueError):
        parse_watches({"watch": [{"name": "a", "campground_id": 1, "arrive": "2027-06-01", "nights": 0}]})


def test_example_config_loads():
    from pathlib import Path

    from hutmonitor.config import load_watches

    ws = load_watches(Path(__file__).parent.parent / "watches.example.toml")
    assert [w.provider for w in ws] == ["recgov", "recgov", "amc"]


def test_parse_duration():
    assert parse_duration("10m") == 600 and parse_duration("1h") == 3600 and parse_duration("90") == 90

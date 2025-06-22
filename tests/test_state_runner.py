from datetime import date

from hutmonitor.models import Opening, Watch
from hutmonitor.providers import ProviderError
from hutmonitor.providers.amc import AMCProvider
from hutmonitor.providers.base import Provider
from hutmonitor.runner import run_once
from hutmonitor.state import State


def op(site, day="2027-06-10", nights=1, watch="w"):
    start = date.fromisoformat(day)
    from datetime import timedelta

    return Opening(watch=watch, provider="recgov", campground="1", site=site, site_id=site,
                   nights=tuple(start + timedelta(days=i) for i in range(nights)), url=f"u/{site}")


WATCH = Watch(name="w", provider="fake", campground_id="1", arrive=date(2027, 6, 10))


class FakeProvider(Provider):
    name = "fake"

    def __init__(self, script):
        self.script = list(script)

    def check(self, watch):
        r = self.script.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


class Collect:
    def __init__(self):
        self.batches = []

    def send(self, ops):
        self.batches.append([o.site for o in ops])


def test_state_diff_only_new_and_reappear(tmp_path):
    s = State(tmp_path / "s.json")
    assert [o.site for o in s.diff("w", [op("A"), op("B")])] == ["A", "B"]
    assert s.diff("w", [op("A"), op("B")]) == []
    assert [o.site for o in s.diff("w", [op("A"), op("C")])] == ["C"]  # B gone, C new
    assert [o.site for o in s.diff("w", [op("A"), op("B"), op("C")])] == ["B"]  # B came back


def test_different_nights_are_distinct(tmp_path):
    s = State(tmp_path / "s.json")
    s.diff("w", [op("A", nights=2)])
    assert len(s.diff("w", [op("A", nights=2), op("A", day="2027-06-11", nights=2)])) == 1


def test_state_persists(tmp_path):
    p = tmp_path / "s.json"
    s = State(p)
    s.diff("w", [op("A")])
    s.mark_checked("fake:1", now=1000)
    s.save()
    s2 = State(p)
    assert s2.diff("w", [op("A")]) == []
    assert not s2.due("fake:1", 300, now=1200)
    assert s2.due("fake:1", 300, now=1300)


def test_runner_end_to_end(tmp_path):
    prov = FakeProvider([[op("A")], [op("A"), op("B")], ProviderError("down"), [op("B")], [op("A"), op("B")]])
    notif = Collect()
    state = State(tmp_path / "s.json")
    t = 10_000.0
    for _ in range(5):
        run_once([WATCH], state, [notif], provider_factory=lambda n: prov, now=t)
        t += 301
    # error pass leaves state alone, so B isn't re-alerted after it; A re-alerts after vanishing
    assert notif.batches == [["A"], ["B"], ["A"]]


def test_runner_respects_min_interval(tmp_path):
    prov = FakeProvider([[op("A")], [op("A"), op("B")]])
    notif = Collect()
    state = State(tmp_path / "s.json")
    run_once([WATCH], state, [notif], provider_factory=lambda n: prov, now=1000)
    run_once([WATCH], state, [notif], provider_factory=lambda n: prov, now=1100)  # too soon: skipped
    assert len(prov.script) == 1
    run_once([WATCH], state, [notif], provider_factory=lambda n: prov, now=1100, force=True)
    assert notif.batches == [["A"], ["B"]]


def test_amc_stub_returns_nothing_and_has_url():
    w = Watch(name="Galehead", provider="amc", campground_id="galehead", arrive=date(2027, 8, 14))
    p = AMCProvider()
    assert p.check(w) == []
    assert p.supported is False
    assert p.booking_url(w).startswith("https://")

from datetime import date

import httpx
import pytest

from hutmonitor.http import PoliteClient
from hutmonitor.models import Watch
from hutmonitor.providers import ProviderError
from hutmonitor.providers.recgov import RecGovProvider, find_openings, merge_months, months_needed

from .conftest import FakeHTTP, d, load


def W(**kw):
    base = dict(name="w", provider="recgov", campground_id="999", arrive=d("2027-06-10"), nights=1)
    base.update(kw)
    return Watch(**base)


def sites_of(ops):
    return sorted((o.site, o.arrive.isoformat(), len(o.nights)) for o in ops)


def test_months_needed_single_and_spanning():
    assert months_needed(W(arrive=d("2027-06-10"), nights=2)) == [date(2027, 6, 1)]
    assert months_needed(W(arrive=d("2027-06-29"), nights=3)) == [date(2027, 6, 1), date(2027, 7, 1)]
    assert months_needed(W(arrive=d("2027-12-30"), nights=4)) == [date(2027, 12, 1), date(2028, 1, 1)]
    # flexible window extends coverage
    assert len(months_needed(W(arrive=d("2027-06-01"), arrive_end=d("2027-08-02"), nights=1))) == 3


def test_multi_night_requires_every_night(fab_http):
    data = merge_months([load("fab_2027-06.json")])
    # site 002 free 10,11,12 -> 3 nights ok, 4 nights not
    ops3 = find_openings(data, W(arrive=d("2027-06-10"), nights=3, site_types=("TENT",)))
    assert sites_of(ops3) == [("002", "2027-06-10", 3)]
    ops4 = find_openings(data, W(arrive=d("2027-06-10"), nights=4, site_types=("TENT",)))
    assert ops4 == []


def test_status_other_than_available_blocks(fab_http):
    p = RecGovProvider(http=fab_http)
    # site 002: Jun 30 Available, Jul 1 "Not Reservable" -> no 2-night stay
    ops = p.check(W(arrive=d("2027-06-30"), nights=2, sites=("002",)))
    assert ops == []


def test_month_spanning_stay_fetches_both_months(fab_http):
    p = RecGovProvider(http=fab_http)
    ops = p.check(W(arrive=d("2027-06-29"), nights=3))
    # site 001: Jun 29, 30 + Jul 1 available; site 003 all available; 002 blocked
    assert sites_of(ops) == [("001", "2027-06-29", 3), ("003", "2027-06-29", 3)]
    starts = [c[1]["start_date"] for c in fab_http.calls]
    assert starts == ["2027-06-01T00:00:00.000Z", "2027-07-01T00:00:00.000Z"]
    o = ops[0]
    assert o.depart == d("2027-07-02")
    assert o.url == "https://www.recreation.gov/camping/campsites/1"


def test_filters_type_loop_site(fab_http):
    p = RecGovProvider(http=fab_http)
    w = W(arrive=d("2027-06-30"), nights=1)
    assert {o.site for o in p.check(w)} == {"001", "002", "003"}
    assert {o.site for o in p.check(W(arrive=d("2027-06-30"), loops=("loop b",)))} == {"003"}
    assert {o.site for o in p.check(W(arrive=d("2027-06-30"), site_types=("standard", "tent")))} == {"001", "002"}
    assert {o.site for o in p.check(W(arrive=d("2027-06-30"), sites=("001",)))} == {"001"}


def test_flexible_arrival_window(fab_http):
    p = RecGovProvider(http=fab_http)
    ops = p.check(W(arrive=d("2027-06-28"), arrive_end=d("2027-06-30"), nights=2, sites=("001",)))
    assert sites_of(ops) == [("001", "2027-06-29", 2), ("001", "2027-06-30", 2)]


def test_cache_shared_within_pass(fab_http):
    p = RecGovProvider(http=fab_http)
    p.check(W(arrive=d("2027-06-10")))
    p.check(W(name="other", arrive=d("2027-06-12")))
    assert len(fab_http.calls) == 1


def test_recorded_fixture_shape():
    """Trimmed real response from Upper Pines (Dec 2026)."""
    data = load("recgov_232447_2026-12_recorded.json")
    ops = find_openings(merge_months([data]), W(campground_id="232447", arrive=d("2026-12-14"), nights=4))
    assert [o.site for o in ops] == ["044"]
    assert ops[0].loop == "Upper Pines"
    ops = find_openings(merge_months([data]), W(campground_id="232447", arrive=d("2026-12-01"), nights=3))
    assert [o.site for o in ops] == ["046"]


def test_http_errors_become_provider_error():
    class Bad:
        def get_json(self, *a, **k):
            raise httpx.ConnectError("nope")

    with pytest.raises(ProviderError):
        RecGovProvider(http=Bad()).check(W())


def _client(responses):
    seq = iter(responses)

    def handler(request):
        assert "Mozilla" in request.headers["user-agent"]
        return next(seq)

    from hutmonitor.http import DEFAULT_HEADERS

    return httpx.Client(transport=httpx.MockTransport(handler), headers=DEFAULT_HEADERS)


def test_backoff_on_429_and_5xx_then_success():
    sleeps = []
    pc = PoliteClient(
        client=_client([httpx.Response(429, headers={"Retry-After": "7"}), httpx.Response(503), httpx.Response(200, json={"ok": 1})]),
        backoff_base_s=10,
        sleep=sleeps.append,
    )
    assert pc.get_json("https://example.invalid/x") == {"ok": 1}
    assert len(sleeps) == 2
    assert 7 <= sleeps[0] <= 7 * 1.25  # honours Retry-After
    assert 20 <= sleeps[1] <= 25  # base * 2**1 + jitter


def test_backoff_gives_up():
    pc = PoliteClient(client=_client([httpx.Response(500)] * 3), max_retries=2, backoff_base_s=1, sleep=lambda s: None)
    with pytest.raises(httpx.HTTPStatusError):
        pc.get_json("https://example.invalid/x")


def test_jitter_between_requests():
    sleeps = []
    pc = PoliteClient(client=_client([httpx.Response(200, json={})] * 2), jitter_s=(1, 2), sleep=sleeps.append)
    pc.get_json("https://example.invalid/a")
    pc.get_json("https://example.invalid/b")
    assert len(sleeps) == 1 and 1 <= sleeps[0] <= 2

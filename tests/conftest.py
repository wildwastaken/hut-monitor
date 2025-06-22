import json
from datetime import date
from pathlib import Path

import httpx
import pytest

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("tests must not touch the network")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", boom)


def load(name):
    return json.loads((FIX / name).read_text())


class FakeHTTP:
    """Stands in for PoliteClient; serves fixtures keyed by start_date month."""

    def __init__(self, months: dict[str, dict]):
        self.months = months
        self.calls = []

    def get_json(self, url, params=None):
        self.calls.append((url, params))
        key = params["start_date"][:7]
        return self.months.get(key, {"campsites": {}})


@pytest.fixture
def fab_http():
    return FakeHTTP({"2027-06": load("fab_2027-06.json"), "2027-07": load("fab_2027-07.json")})


def d(s):
    return date.fromisoformat(s)

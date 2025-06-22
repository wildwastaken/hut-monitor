"""AMC huts (Galehead, Lakes of the Clouds, ...): stub provider.

AMC's reservation system has no public JSON API we can confirm, and we don't
scrape anything that needs a login. This provider only surfaces the booking URL
so the watch is visible in your config and output. It never reports openings.
"""
from __future__ import annotations

import logging

from ..models import Opening, Watch
from .base import Provider

log = logging.getLogger(__name__)

DEFAULT_URL = "https://www.outdoors.org/"
NOTE = "AMC huts: automatic checking is not supported yet. Check availability manually"


class AMCProvider(Provider):
    name = "amc"
    supported = False

    def booking_url(self, watch: Watch) -> str:
        return watch.url or DEFAULT_URL

    def check(self, watch: Watch) -> list[Opening]:
        log.warning("%s [%s]: %s: %s", NOTE, watch.name, watch.campground_id, self.booking_url(watch))
        return []

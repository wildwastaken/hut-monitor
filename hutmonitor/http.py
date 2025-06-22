"""Small polite HTTP helper: browser-like UA, jitter, backoff on 429/5xx."""
from __future__ import annotations

import logging
import random
import time
from typing import Callable

import httpx

log = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)
DEFAULT_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}


class PoliteClient:
    def __init__(
        self,
        client: httpx.Client | None = None,
        max_retries: int = 3,
        backoff_base_s: float = 30.0,
        jitter_s: tuple[float, float] = (1.0, 4.0),
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.client = client or httpx.Client(headers=DEFAULT_HEADERS, timeout=30.0, follow_redirects=True)
        self.max_retries = max_retries
        self.backoff_base_s = backoff_base_s
        self.jitter_s = jitter_s
        self.sleep = sleep
        self._first = True

    def get_json(self, url: str, params: dict | None = None):
        # Jitter between consecutive requests so we never fire a burst.
        if not self._first and self.jitter_s[1] > 0:
            self.sleep(random.uniform(*self.jitter_s))
        self._first = False

        attempt = 0
        while True:
            resp = self.client.get(url, params=params)
            if resp.status_code == 429 or resp.status_code >= 500:
                if attempt >= self.max_retries:
                    resp.raise_for_status()
                wait = self._retry_after(resp) or self.backoff_base_s * (2**attempt)
                wait += random.uniform(0, wait * 0.25)
                log.warning("HTTP %s from %s; backing off %.0fs", resp.status_code, url, wait)
                self.sleep(wait)
                attempt += 1
                continue
            resp.raise_for_status()
            return resp.json()

    @staticmethod
    def _retry_after(resp: httpx.Response) -> float | None:
        val = resp.headers.get("Retry-After")
        try:
            return float(val) if val else None
        except ValueError:
            return None

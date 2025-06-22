from __future__ import annotations

import logging
import time
from typing import Callable

from .models import Opening, Watch
from .providers import Provider, ProviderError, get_provider
from .state import State

log = logging.getLogger(__name__)


def run_once(
    watches: list[Watch],
    state: State,
    notifiers: list,
    provider_factory: Callable[[str], Provider] = get_provider,
    force: bool = False,
    now: float | None = None,
) -> list[Opening]:
    """One pass over all watches. Returns the NEW openings that were alerted."""
    now = time.time() if now is None else now
    providers: dict[str, Provider] = {}  # fresh per pass, so caches don't go stale
    due: dict[str, bool] = {}
    all_new: list[Opening] = []

    for w in watches:
        prov = providers.get(w.provider) or providers.setdefault(w.provider, provider_factory(w.provider))
        rk = prov.rate_key(w)
        if rk not in due:
            due[rk] = force or not prov.supported or state.due(rk, w.min_interval_s, now)
        if not due[rk]:
            log.info("%s: skipped, %s polled less than %ss ago", w.name, rk, w.min_interval_s)
            continue
        try:
            current = prov.check(w)
        except ProviderError as e:
            log.error("%s: %s (state left unchanged)", w.name, e)
            continue
        log.info("%s: %d matching opening(s) right now", w.name, len(current))
        all_new.extend(state.diff(w.name, current))

    for rk, was_due in due.items():
        if was_due:
            state.mark_checked(rk, now)
    state.prune({w.name for w in watches})
    state.save()

    if all_new:
        for n in notifiers:
            n.send(all_new)
    return all_new

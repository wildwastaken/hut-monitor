from __future__ import annotations

from .base import Provider, ProviderError


def get_provider(name: str, **kwargs) -> Provider:
    name = name.lower()
    if name in ("recgov", "recreation.gov", "recreationgov"):
        from .recgov import RecGovProvider

        return RecGovProvider(**kwargs)
    if name in ("amc", "amc_huts"):
        from .amc import AMCProvider

        return AMCProvider()
    raise ValueError(f"unknown provider: {name!r} (known: recgov, amc)")


__all__ = ["Provider", "ProviderError", "get_provider"]

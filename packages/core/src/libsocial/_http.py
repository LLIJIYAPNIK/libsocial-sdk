"""HTTP headers shared by every client the SDKs open (not public API).

Lives in its own module rather than in ``client.py`` because it isn't specific to the
api.cdnlibs.org JSON API: a site package's image-downloading clients (cover.cdnlibs.org,
the site's own uploads) need the same headers.
"""

from __future__ import annotations

from collections.abc import Mapping

import httpx

BROWSER_USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/18.5 Mobile/15E148 Safari/604.1"
)
"""A real browser's ``User-Agent``, sent instead of advertising ``python-httpx``."""


def browser_headers_for(origin: str) -> dict[str, str]:
    """Headers a browser on the site at ``origin`` sends, so requests look like the site's.

    The DDoS-Guard edge in front of api.cdnlibs.org and cover.cdnlibs.org rejects requests
    without a non-empty ``Referer`` with an HTML 403 page (see docs/api-notes.md, section
    "WAF 403"). Any ``Referer`` value was enough when checked; the site's own one is sent,
    together with ``Origin`` and a real browser ``User-Agent``, so the request as a whole
    matches what the site itself sends.

    Args:
        origin: The site's web origin, e.g. ``"https://ranobelib.me"`` (see ``Site.origin``).
    """
    return {"Origin": origin, "Referer": f"{origin}/", "User-Agent": BROWSER_USER_AGENT}


def browser_headers(origin: str, overrides: Mapping[str, str] | None = None) -> httpx.Headers:
    """``browser_headers_for(origin)`` with ``overrides`` merged over them.

    A key in ``overrides`` replaces the default one, matched case-insensitively (``httpx``
    headers semantics) — the same merge ``ApiClient(headers=...)`` does for API requests.
    """
    headers = httpx.Headers(browser_headers_for(origin))
    if overrides:
        headers.update(overrides)
    return headers

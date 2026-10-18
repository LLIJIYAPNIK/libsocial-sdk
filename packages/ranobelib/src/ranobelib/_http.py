"""HTTP settings shared by every client the SDK opens (not public API).

Lives in its own module rather than in ``client.py`` because it isn't specific to the
api.cdnlibs.org JSON API: the exporters' image-downloading clients (cover.cdnlibs.org,
ranobelib.me uploads) need the same headers, and importing them from here keeps the
exporters from depending on ``ApiClient``'s module just for a constant.
"""

from __future__ import annotations

from collections.abc import Mapping

import httpx

SITE_ORIGIN = "https://ranobelib.me"
"""Origin of the ranobelib.me website, as its own pages send it."""

BROWSER_HEADERS: dict[str, str] = {
    "Origin": SITE_ORIGIN,
    "Referer": f"{SITE_ORIGIN}/",
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/18.5 Mobile/15E148 Safari/604.1"
    ),
}
"""Headers a browser on ranobelib.me sends, so requests look like they come from the site.

The DDoS-Guard edge in front of api.cdnlibs.org and cover.cdnlibs.org rejects requests
without a non-empty ``Referer`` with an HTML 403 page (see docs/api-notes.md, section
"WAF 403"). Any ``Referer`` value was enough when checked; the site's own one is sent,
together with ``Origin`` and a real browser ``User-Agent``, so the request as a whole matches
what the site itself sends rather than advertising ``python-httpx``.
"""


def browser_headers(overrides: Mapping[str, str] | None = None) -> httpx.Headers:
    """``BROWSER_HEADERS`` with ``overrides`` merged over them.

    A key in ``overrides`` replaces the default one, matched case-insensitively (``httpx``
    headers semantics) — the same merge ``ApiClient(headers=...)`` does for API requests.
    """
    headers = httpx.Headers(BROWSER_HEADERS)
    if overrides:
        headers.update(overrides)
    return headers

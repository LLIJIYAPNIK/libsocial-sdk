"""ranobelib.me's site identity and browser headers (not public API).

The headers themselves are built by ``libsocial-core`` from the site's origin; this module
pins them to ranobelib.me for the exporters' image downloads (cover.cdnlibs.org, ranobelib.me
uploads) and for ``ApiClient``.
"""

from __future__ import annotations

from collections.abc import Mapping

import httpx

from libsocial import Site, browser_headers_for
from libsocial import browser_headers as _browser_headers_for_origin

SITE_ORIGIN = "https://ranobelib.me"
"""Origin of the ranobelib.me website, as its own pages send it."""

RANOBELIB = Site(id=3, origin=SITE_ORIGIN)
"""ranobelib.me on the shared lib.social API: ``Site-Id: 3`` (see docs/api-notes.md)."""

BROWSER_HEADERS: dict[str, str] = browser_headers_for(SITE_ORIGIN)
"""Headers a browser on ranobelib.me sends, so requests look like they come from the site.

The DDoS-Guard edge in front of api.cdnlibs.org and cover.cdnlibs.org rejects requests
without a non-empty ``Referer`` with an HTML 403 page (see docs/api-notes.md, section
"WAF 403"); the site's own ``Origin``/``Referer`` and a real browser ``User-Agent`` are sent.
"""


def browser_headers(overrides: Mapping[str, str] | None = None) -> httpx.Headers:
    """``BROWSER_HEADERS`` with ``overrides`` merged over them.

    A key in ``overrides`` replaces the default one, matched case-insensitively (``httpx``
    headers semantics) — the same merge ``ApiClient(headers=...)`` does for API requests.
    """
    return _browser_headers_for_origin(SITE_ORIGIN, overrides)

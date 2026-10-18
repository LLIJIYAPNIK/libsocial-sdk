"""mangalib.me's site identity and browser headers (not public API)."""

from __future__ import annotations

from collections.abc import Mapping

import httpx

from libsocial import Site, browser_headers_for

SITE_ORIGIN = "https://mangalib.me"
"""Origin of the mangalib.me website, as its own pages send it."""

MANGALIB = Site(id=1, origin=SITE_ORIGIN)
"""mangalib.me on the shared lib.social API: ``Site-Id: 1`` (see docs/api-notes.md)."""

IMAGE_ACCEPT = "image/*"
"""``Accept`` sent for page images, as a browser's ``<img>`` request would."""


def image_headers(overrides: Mapping[str, str] | None = None) -> httpx.Headers:
    """Headers for downloading page images: mangalib.me's browser headers, ``Accept: image/*``.

    A key in ``overrides`` replaces the default one, matched case-insensitively — the same
    merge ``ApiClient(headers=...)`` does for API requests.
    """
    headers = httpx.Headers({**browser_headers_for(SITE_ORIGIN), "Accept": IMAGE_ACCEPT})
    if overrides:
        headers.update(overrides)
    return headers

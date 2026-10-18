"""Chapter numbering helpers (``number`` / ``number_secondary``) and title URL parsing."""

from __future__ import annotations

import re
from urllib.parse import urlsplit

_SLUG_URL_RE = re.compile(r"^\d+--[^/?#]+$")


def parse_slug_url(source: str) -> str:
    """Extract a title's ``slug_url`` (``{id}--{slug}``) from a URL or pass it through.

    Args:
        source: Either a full title URL (e.g.
            ``https://ranobelib.me/ru/book/6712--high-school-dxd-novel``) or an already
            bare ``slug_url`` (``6712--high-school-dxd-novel``).

    Returns:
        The bare ``slug_url``, as used by the ``/api/manga/{slug_url}`` endpoint.

    Raises:
        ValueError: If no ``{id}--{slug}`` segment could be found in ``source``.
    """
    candidate = source
    if "://" in source:
        path = urlsplit(source).path
        segments = [segment for segment in path.split("/") if segment]
        candidate = segments[-1] if segments else ""

    if not _SLUG_URL_RE.match(candidate):
        raise ValueError(f"Could not extract a title slug from: {source!r}")

    return candidate

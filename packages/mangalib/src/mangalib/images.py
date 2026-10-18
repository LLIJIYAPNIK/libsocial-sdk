"""Page images: their URLs on an image server, and downloading them with server fallback.

The API lists several image servers (``ImageServer``) and doesn't say which one a page is
on — every server serves every page under the same path. They don't all let a script in,
though: when checked, the DDoS-Guard edge in front of ``main``/``secondary`` answered every
request with an HTML 403 whatever the headers, while ``compress``/``download`` served the
full-size image (see docs/api-notes.md, "MangaLib"). So downloads start from
``compress`` and fall back through the others.
"""

from __future__ import annotations

import httpx

from mangalib.exceptions import PageDownloadError
from mangalib.models import ImageServer, Page

__all__ = ["DEFAULT_SERVER_ORDER", "page_url"]

DEFAULT_SERVER_ORDER = ("compress", "download", "main", "secondary")
"""Image servers tried, in this order, when no server is chosen. ``crop`` isn't one of
them: it serves 310×450 previews, not the page itself — choose it explicitly if that's what
you want."""


def page_url(page: Page, server: ImageServer) -> str:
    """The full URL of ``page``'s image on ``server``.

    ``Page.url`` starts with ``//``; the slashes are collapsed to one (both forms serve the
    same image, checked on every server).
    """
    return f"{server.url.rstrip('/')}/{page.url.lstrip('/')}"


def server_order(servers: list[ImageServer], server: str | None) -> list[ImageServer]:
    """The servers to try for a page, in order (not public API).

    ``server`` first, if given, then ``DEFAULT_SERVER_ORDER``, skipping any that has the
    same URL as one already in the list — retrying the same host under another name
    wouldn't help.

    Raises:
        ValueError: If ``server`` isn't one of ``servers``, or none of the servers is known.
    """
    by_id = {item.id: item for item in servers}
    if server is not None and server not in by_id:
        available = ", ".join(sorted(by_id)) or "(none)"
        raise ValueError(f"Unknown image server {server!r}. Available: {available}")

    ids = [server] if server is not None else []
    ids += [item for item in DEFAULT_SERVER_ORDER if item != server]
    order: list[ImageServer] = []
    for item in ids:
        candidate = by_id.get(item)
        if candidate is not None and all(other.url != candidate.url for other in order):
            order.append(candidate)
    if not order:
        raise ValueError(
            "None of the API's image servers is one the SDK knows how to use "
            f"({', '.join(sorted(by_id)) or 'none listed'}); pass server= explicitly."
        )
    return order


async def download_page(client: httpx.AsyncClient, page: Page, servers: list[ImageServer]) -> bytes:
    """Download ``page`` from the first of ``servers`` that serves it (not public API).

    A server fails over to the next one on a network error, a non-2xx status, or a response
    that isn't an image — DDoS-Guard's refusal is an HTML page.

    Raises:
        PageDownloadError: If every server failed.
    """
    failures: list[tuple[str, str]] = []
    for server in servers:
        url = page_url(page, server)
        try:
            response = await client.get(url)
        except httpx.HTTPError as exc:
            failures.append((url, f"{type(exc).__name__}: {exc}"))
            continue
        content_type = response.headers.get("Content-Type", "")
        if not response.is_success:
            failures.append((url, f"HTTP {response.status_code} ({content_type or 'no type'})"))
        elif not content_type.lower().startswith("image/"):
            failures.append((url, f"not an image ({content_type or 'no type'})"))
        else:
            return response.content
    raise PageDownloadError(failures)

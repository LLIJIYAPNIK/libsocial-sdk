"""Page images: their URLs on an image server, and downloading them with server fallback.

The API lists several image servers (``ImageServer``) and doesn't say which one a page is
on — every server serves every page under the same path. They don't all let a script in,
though: when checked, the DDoS-Guard edge in front of ``main``/``secondary`` answered every
request with an HTML 403 whatever the headers, while ``compress``/``download`` served the
full-size image (see docs/api-notes.md, "MangaLib"). So downloads start from
``compress`` and fall back through the others.

Requests to each image host are paced by the process-wide ``libsocial.shared_pacer`` for
that host (not api.cdnlibs.org's), and a 429, a 5xx or a network error is retried with
backoff on the same server before moving on to the next one: the image host rate-limits
too (DDoS-Guard's HTML 429, without ``Retry-After``, see docs/api-notes.md).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

import httpx

from libsocial.pacing import shared_pacer
from mangalib.exceptions import PageDownloadError
from mangalib.models import ImageServer, Page

__all__ = [
    "DEFAULT_IMAGE_CONCURRENCY",
    "DEFAULT_IMAGE_REQUEST_DELAY",
    "DEFAULT_SERVER_ORDER",
    "page_url",
]

DEFAULT_SERVER_ORDER = ("compress", "download", "main", "secondary")
"""Image servers tried, in this order, when no server is chosen. ``crop`` isn't one of
them: it serves 310×450 previews, not the page itself — choose it explicitly if that's what
you want."""

DEFAULT_IMAGE_CONCURRENCY = 5
"""Page requests in flight at once by default (``download_pages()``, ``export()``, size
methods)."""

DEFAULT_IMAGE_REQUEST_DELAY = 0.2
"""Minimum time, in seconds, between the starts of two requests to the same image host,
across every client in the process. With five at once, 300 full-size pages went through
without a single 429 when checked; much denser request rates got DDoS-Guard's 429."""

_MAX_RETRIES = 3
"""Retries of one request on the same server (429, 5xx, network error) before falling back
to the next server."""

_RETRY_BASE_DELAY = 1.0
"""Backoff before the first retry, in seconds, doubled per retry. The 429 sends no
``Retry-After``; when checked, the host let requests through again a minute or two later."""


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


class ImageFetcher:
    """Paced, retried requests for page images, falling back across servers (not public API).

    Args:
        client: The HTTP client to send requests with (browser headers, ``Accept: image/*``).
        request_delay: See ``DEFAULT_IMAGE_REQUEST_DELAY``.
        sleep: Sleep function for pacing and backoff. Overridable for tests.
    """

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        request_delay: float = DEFAULT_IMAGE_REQUEST_DELAY,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._client = client
        self._request_delay = request_delay
        self._sleep = sleep

    async def download(self, page: Page, servers: list[ImageServer]) -> bytes:
        """Download ``page`` from the first of ``servers`` that serves it.

        A server is given up on after a non-retryable error (a 4xx other than 429, or a
        response that isn't an image — DDoS-Guard's refusal is an HTML page) or once its
        retries run out.

        Raises:
            PageDownloadError: If every server failed.
        """
        response = await self._first_image(page, servers, "GET")
        return response.content

    async def size(self, page: Page, servers: list[ImageServer]) -> int:
        """The size in bytes of ``page``'s image, from a ``HEAD`` request's ``Content-Length``.

        The image servers answer ``HEAD`` with the exact length of the file (checked against
        the downloaded body), so this costs no image traffic. A server that sends no
        ``Content-Length`` is treated like one that failed.

        Raises:
            PageDownloadError: If no server gave a size.
        """
        response = await self._first_image(page, servers, "HEAD", needs_length=True)
        return int(response.headers["Content-Length"])

    async def _first_image(
        self, page: Page, servers: list[ImageServer], method: str, *, needs_length: bool = False
    ) -> httpx.Response:
        failures: list[tuple[str, str]] = []
        for server in servers:
            url = page_url(page, server)
            outcome = await self._request(method, url)
            if isinstance(outcome, str):
                failures.append((url, outcome))
                continue
            length = outcome.headers.get("Content-Length", "")
            if needs_length and not length.isdigit():
                failures.append((url, "no Content-Length"))
                continue
            return outcome
        raise PageDownloadError(failures)

    async def _request(self, method: str, url: str) -> httpx.Response | str:
        """One server's answer: an image response, or why it failed (after any retries)."""
        pacer = shared_pacer(httpx.URL(url).host)
        attempt = 0
        while True:
            await pacer.wait(self._request_delay, sleep=self._sleep)
            try:
                response = await self._client.request(method, url)
            except httpx.TransportError as exc:
                # Includes a connection DDoS-Guard broke by sending a body with its 429 to a
                # HEAD request: the next response on it can't be parsed (see api-notes).
                reason = f"{type(exc).__name__}: {exc}"
                retryable = True
            else:
                content_type = response.headers.get("Content-Type", "")
                if response.is_success:
                    if content_type.lower().startswith("image/"):
                        return response
                    return f"not an image ({content_type or 'no type'})"
                reason = f"HTTP {response.status_code} ({content_type or 'no type'})"
                retryable = response.status_code == 429 or response.status_code >= 500
            if not retryable or attempt >= _MAX_RETRIES:
                return reason
            await self._sleep(_RETRY_BASE_DELAY * (2**attempt))
            attempt += 1

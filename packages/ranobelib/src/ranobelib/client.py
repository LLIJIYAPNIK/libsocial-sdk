"""Low-level HTTP client for the api.cdnlibs.org JSON API."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable, Mapping
from types import TracebackType
from typing import Any, Self

import httpx

from ranobelib._http import BROWSER_HEADERS
from ranobelib.exceptions import (
    AccessBlockedError,
    AuthRequiredError,
    ChapterNotFoundError,
    RanobeLibError,
    RateLimitError,
    TitleNotFoundError,
)

API_BASE_URL = "https://api.cdnlibs.org/api"
"""Base URL of the lib.social JSON API shared across the network's sites."""

RANOBELIB_SITE_ID = "3"
"""``Site-Id`` header value that scopes requests to ranobelib.me. See docs/api-notes.md."""

_RETRYABLE_STATUSES = frozenset({429, *range(500, 600)})

DEFAULT_REQUEST_DELAY = 0.2
"""Default minimum time, in seconds, between the start of one request and the next."""


class ApiClient:
    """Thin async wrapper around the undocumented api.cdnlibs.org JSON API.

    Bounds concurrency with a semaphore, paces request starts with a small fixed delay, and
    retries 429/5xx responses with exponential backoff — see docs/api-notes.md for why a
    manual implementation was chosen over a dependency like ``tenacity`` for this.

    Every request carries browser-like ``Origin``/``Referer``/``User-Agent`` headers on top
    of the API-specific ``Site-Id``/``Accept``: without a non-empty ``Referer``, the
    DDoS-Guard edge in front of the API answers every request with an HTML 403 page (see
    docs/api-notes.md, section "WAF 403").
    """

    def __init__(
        self,
        *,
        base_url: str = API_BASE_URL,
        timeout: float = 15.0,
        transport: httpx.AsyncBaseTransport | None = None,
        headers: Mapping[str, str] | None = None,
        max_concurrency: int = 5,
        request_delay: float | None = None,
        max_retries: int = 3,
        retry_base_delay: float = 1.0,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Initialize the client.

        Args:
            base_url: API base URL.
            timeout: Per-request timeout, in seconds.
            transport: Custom ``httpx`` transport, e.g. a mock transport for tests.
            headers: Extra headers merged over the defaults (browser-like ``Origin``/
                ``Referer``/``User-Agent`` plus the API's ``Site-Id``/``Accept``); a key
                given here replaces the default one, matched case-insensitively. Meant for
                swapping in a different ``User-Agent`` if the site's edge protection changes
                its rules, without waiting for an SDK release. Overriding ``Site-Id`` or
                ``Accept`` is possible but breaks the API's contract (see
                docs/api-notes.md) — only do it knowingly.
            max_concurrency: Maximum number of requests in flight at once.
            request_delay: Minimum time, in seconds, between the start of one request and
                the next, even under ``max_concurrency``. ``None`` (the default) uses
                ``DEFAULT_REQUEST_DELAY``.
            max_retries: How many times to retry a 429 or 5xx response before giving up and
                raising.
            retry_base_delay: Base delay, in seconds, for exponential backoff between
                retries (doubled per attempt) — used unless a 429 response's
                ``Retry-After`` header says otherwise.
            sleep: Sleep function used for pacing and backoff. Overridable for tests.
            clock: Time source used for pacing. Overridable for tests.
        """
        self._http = httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout,
            transport=transport,
            headers={
                **BROWSER_HEADERS,
                "Site-Id": RANOBELIB_SITE_ID,
                "Accept": "application/json",
            },
        )
        if headers is not None:
            self._http.headers.update(headers)
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._request_delay = DEFAULT_REQUEST_DELAY if request_delay is None else request_delay
        self._max_retries = max_retries
        self._retry_base_delay = retry_base_delay
        self._sleep = sleep
        self._clock = clock
        self._pacing_lock = asyncio.Lock()
        self._last_request_at: float | None = None

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Close the underlying HTTP connection pool."""
        await self._http.aclose()

    async def get_title(self, slug_url: str, *, fields: list[str] | None = None) -> dict[str, Any]:
        """Fetch raw title metadata for ``slug_url``.

        Args:
            slug_url: The title's ``{id}--{slug}`` identifier.
            fields: Extra ``fields[]`` values to request from the API.

        Returns:
            The ``data`` object from the API response.
        """
        params = httpx.QueryParams([("fields[]", field) for field in fields or []])
        response = await self._get(f"/manga/{slug_url}", params=params)
        self._raise_for_status(response, not_found=TitleNotFoundError(slug_url))
        data: dict[str, Any] = response.json()["data"]
        return data

    async def get_chapters(self, slug_url: str) -> list[dict[str, Any]]:
        """Fetch the raw chapter list for ``slug_url`` (single request, no pagination).

        Args:
            slug_url: The title's ``{id}--{slug}`` identifier.

        Returns:
            The ``data`` array from the API response.
        """
        response = await self._get(f"/manga/{slug_url}/chapters")
        self._raise_for_status(response, not_found=TitleNotFoundError(slug_url))
        data: list[dict[str, Any]] = response.json()["data"]
        return data

    async def get_chapter(
        self,
        slug_url: str,
        *,
        number: str,
        volume: str,
        branch_id: int | None = None,
    ) -> dict[str, Any]:
        """Fetch a single chapter's metadata and content.

        Args:
            slug_url: The title's ``{id}--{slug}`` identifier.
            number: The chapter number, as returned by the API (may contain a decimal).
            volume: The volume number.
            branch_id: Which translation team's branch to fetch, for chapters with more
                than one. Defaults to whichever branch the API picks (see
                docs/api-notes.md — this is not simply the first branch listed).

        Returns:
            The ``data`` object from the API response.
        """
        params = {"number": number, "volume": volume}
        if branch_id is not None:
            params["branch_id"] = str(branch_id)
        response = await self._get(f"/manga/{slug_url}/chapter", params=params)
        self._raise_for_status(
            response, not_found=ChapterNotFoundError(slug_url, volume=volume, number=number)
        )
        data: dict[str, Any] = response.json()["data"]
        return data

    async def list_titles(
        self,
        *,
        page: int,
        per_page: int,
        query: str | None,
        genres: list[int] | None,
        tags: list[int] | None,
        statuses: list[int] | None,
        countries: list[int] | None,
        min_chapters: int | None,
        max_chapters: int | None,
        sort: str,
    ) -> dict[str, Any]:
        """Fetch one page of the catalog listing/search results.

        Unlike the other ``ApiClient`` methods, this returns the *whole* response body, not
        just ``data`` — callers need ``meta.has_next_page`` too, and there's no total count
        to derive it from otherwise (see docs/api-notes.md).

        Args:
            page: 1-based page number.
            per_page: Page size. The API only accepts ``10..60`` (validated by the caller,
                see ``Catalog.list_titles``); values outside that raise here via a 422.
            query: Free-text search term, matched against name/rus_name/eng_name. ``None``
                or empty omits the ``q`` parameter entirely.
            genres: Genre ids to filter by. A title must have *all* of them (AND, not OR —
                see docs/api-notes.md), not just any one.
            tags: Tag ids to filter by. Same AND semantics as ``genres`` — a title must have
                *all* of them, not just any one (see docs/api-notes.md).
            statuses: ``Title.status.id``s to filter by. A title matches if its own status
                is *any* of these (OR, like ``countries`` — a title only has one status, see
                docs/api-notes.md). Sent on the wire as repeated ``status[]`` parameters.
            countries: ``Country.id``s to filter by. A title matches if its own country is
                *any* of these (OR, not AND like ``genres``/``tags`` — a title only has one
                country, confirmed against the live API, see docs/api-notes.md). Sent on the
                wire as repeated ``types[]`` parameters — the API's own name for this concept
                is "type", not "country" (see docs/api-notes.md).
            min_chapters: Minimum chapter count, inclusive. Sent as ``chap_count_min``.
            max_chapters: Maximum chapter count, inclusive. Sent as ``chap_count_max``.
            sort: Forwarded as the API's ``sort_by`` parameter, not ``sort`` — the API
                silently ignores an actual ``sort`` parameter (see docs/api-notes.md); this
                mismatch between the SDK's public keyword and the wire parameter name is
                deliberate, not a typo.

        Returns:
            The full JSON response: ``{"data": [...], "meta": {...}, "links": {...}}``.
        """
        params: list[tuple[str, str | int | float | bool | None]] = [
            ("site_id[]", RANOBELIB_SITE_ID),
            ("page", str(page)),
            ("limit", str(per_page)),
            ("sort_by", sort),
        ]
        if query:
            params.append(("q", query))
        for genre_id in genres or []:
            params.append(("genres[]", str(genre_id)))
        for tag_id in tags or []:
            params.append(("tags[]", str(tag_id)))
        for status_id in statuses or []:
            params.append(("status[]", str(status_id)))
        for country_id in countries or []:
            params.append(("types[]", str(country_id)))
        if min_chapters is not None:
            params.append(("chap_count_min", str(min_chapters)))
        if max_chapters is not None:
            params.append(("chap_count_max", str(max_chapters)))

        response = await self._get("/manga", params=httpx.QueryParams(params))
        self._raise_for_status(
            response,
            not_found=RanobeLibError(f"Unexpected 404 from catalog listing (page={page})"),
        )
        result: dict[str, Any] = response.json()
        return result

    async def list_genres(self) -> list[dict[str, Any]]:
        """Fetch the raw genre list shared across the whole lib.social network.

        Unlike ``list_titles``, this endpoint isn't site-scoped by any request parameter
        (confirmed: a ``Site-Id`` header changes nothing about the response) — it returns
        every genre known to the network at once, each tagged with the site ids it applies
        to via a ``site_ids`` field. Callers must filter to ``RANOBELIB_SITE_ID`` themselves
        (see ``Catalog.list_genres``, which drops e.g. site-5-only genres like "Детское"
        before returning).

        Returns:
            The raw ``data.genres`` array from the API response, unfiltered by site.
        """
        response = await self._get("/constants", params=httpx.QueryParams([("fields[]", "genres")]))
        self._raise_for_status(response, not_found=RanobeLibError("Unexpected 404 from genre list"))
        data: list[dict[str, Any]] = response.json()["data"]["genres"]
        return data

    async def list_countries(self) -> list[dict[str, Any]]:
        """Fetch the raw country/type list shared across the whole lib.social network.

        Same shape and caveats as ``list_genres``: not site-scoped by any request parameter,
        returns every "type" known to the network at once, each tagged with the site ids it
        applies to via ``site_ids``. Named ``list_countries``/``fields[]=types`` mismatch is
        deliberate — see ``Catalog.list_countries`` and docs/api-notes.md for why this reuses
        the API's own "type" concept rather than the unrelated ``fields[]=countries`` field.

        Returns:
            The raw ``data.types`` array from the API response, unfiltered by site.
        """
        response = await self._get("/constants", params=httpx.QueryParams([("fields[]", "types")]))
        self._raise_for_status(response, not_found=RanobeLibError("Unexpected 404 from type list"))
        data: list[dict[str, Any]] = response.json()["data"]["types"]
        return data

    async def list_statuses(self) -> list[dict[str, Any]]:
        """Fetch the raw title status list shared across the whole lib.social network.

        Same shape and caveats as ``list_genres``: not site-scoped by any request parameter,
        returns every status known to the network at once, each tagged with the site ids it
        applies to via ``site_ids``.

        Returns:
            The raw ``data.status`` array from the API response, unfiltered by site.
        """
        response = await self._get("/constants", params=httpx.QueryParams([("fields[]", "status")]))
        self._raise_for_status(
            response, not_found=RanobeLibError("Unexpected 404 from status list")
        )
        data: list[dict[str, Any]] = response.json()["data"]["status"]
        return data

    async def _get(self, url: str, *, params: Any = None) -> httpx.Response:
        """Issue a GET request, bounded by concurrency/pacing and retried on 429/5xx."""
        attempt = 0
        while True:
            async with self._semaphore:
                await self._pace()
                response = await self._http.get(url, params=params)
            if response.status_code not in _RETRYABLE_STATUSES or attempt >= self._max_retries:
                return response
            await self._sleep(self._backoff_delay(attempt, response))
            attempt += 1

    async def _pace(self) -> None:
        """Wait, if needed, so this request starts at least ``request_delay`` after the last."""
        async with self._pacing_lock:
            now = self._clock()
            if self._last_request_at is not None:
                wait = self._last_request_at + self._request_delay - now
                if wait > 0:
                    await self._sleep(wait)
            self._last_request_at = self._clock()

    def _backoff_delay(self, attempt: int, response: httpx.Response) -> float:
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            if retry_after is not None:
                try:
                    return float(retry_after)
                except ValueError:
                    pass
        delay: float = self._retry_base_delay * (2**attempt)
        return delay

    def _raise_for_status(self, response: httpx.Response, *, not_found: RanobeLibError) -> None:
        if response.status_code == 404:
            raise not_found
        if response.status_code == 403:
            # The API's own 403 is JSON; the DDoS-Guard edge in front of it answers with an
            # HTML page instead. Told apart by Content-Type, not by the page's wording, which
            # can change (see docs/api-notes.md, section "WAF 403").
            media_type = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
            if media_type != "application/json":
                raise AccessBlockedError(str(response.request.url))
            raise AuthRequiredError(str(response.request.url))
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            raise RateLimitError(float(retry_after) if retry_after else None)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise RanobeLibError(f"Unexpected API response: {exc}") from exc

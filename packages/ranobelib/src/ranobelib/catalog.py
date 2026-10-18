"""Catalog listing/search: the ``Catalog`` class.

Unlike ``RanobeLib`` (scoped to one title via its URL/slug), catalog listing isn't scoped to
any title at all — see CLAUDE.md's roadmap entry for why this is a separate entry point with
its own ``ApiClient``/``DiskCache`` rather than a method on ``RanobeLib``.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from types import TracebackType
from typing import Any, Self

from ranobelib.cache import DEFAULT_CACHE_DIR, DiskCache
from ranobelib.client import RANOBELIB_SITE_ID, ApiClient
from ranobelib.models import CatalogPage, Country, Genre, Label, Title

DEFAULT_SORT = "last_chapter_at"
"""Default sort order: title's last-chapter timestamp — the closest real equivalent to
"recently updated" (the API has no ``updated_at`` sort value, see docs/api-notes.md)."""

MIN_PER_PAGE = 10
MAX_PER_PAGE = 60


class Catalog:
    """Entry point for listing/searching the ranobelib.me catalog.

    Example:
        ```python
        async with Catalog() as catalog:
            page = await catalog.list_titles(query="dxd", genres=[34], statuses=[1])
            for title in page.items:
                print(title.name)
        ```
    """

    def __init__(
        self,
        *,
        cache_dir: str | Path | None = None,
        cache_ttl: float | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        """Initialize the catalog client.

        Args:
            cache_dir: Where to cache raw API responses on disk, one entry per distinct set
                of listing parameters (page/filters/sort) — same disk cache as ``RanobeLib``
                uses (``cache.py``), just keyed by listing parameters instead of a title's
                slug. Defaults to ``.ranobelib_cache`` in the current working directory.
            cache_ttl: Seconds after which a cached page is treated as stale and re-fetched.
                ``None`` (the default) means cached pages never expire on their own — see
                ``refresh=True`` on ``list_titles()`` to force one anyway.
            headers: Extra HTTP headers merged over the SDK's defaults, same as
                ``RanobeLib(headers=...)`` — see there.
        """
        self._client = ApiClient(headers=headers)
        self._cache = DiskCache(
            cache_dir if cache_dir is not None else DEFAULT_CACHE_DIR, ttl=cache_ttl
        )

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
        """Close the underlying HTTP client."""
        await self._client.aclose()

    async def list_titles(
        self,
        *,
        page: int = 1,
        per_page: int = 30,
        query: str | None = None,
        genres: list[int] | None = None,
        tags: list[int] | None = None,
        statuses: list[int] | None = None,
        countries: list[int] | None = None,
        min_chapters: int | None = None,
        max_chapters: int | None = None,
        sort: str = DEFAULT_SORT,
        refresh: bool = False,
    ) -> CatalogPage:
        """Fetch one page of catalog listing/search results.

        Args:
            page: 1-based page number.
            per_page: How many titles per page. Must be between ``MIN_PER_PAGE`` (10) and
                ``MAX_PER_PAGE`` (60) — the API's own limits (see docs/api-notes.md);
                anything outside that range raises here instead of a confusing 422 from
                the API.
            query: Free-text search term, matched against name/rus_name/eng_name. ``None``
                (the default) or an empty string lists without searching.
            genres: Genre ids to filter by. A title must have *all* of them, not just one
                (AND, not OR — see docs/api-notes.md). Not validated against ``list_genres()``
                before sending — an unrecognized id just matches nothing rather than erroring.
            tags: ``Tag.id``s (from ``Title.tags``) to filter by. Same AND semantics as
                ``genres`` — a title must have *all* of them, not just any one (confirmed
                against the live API, see docs/api-notes.md; not the OR some might expect
                from tags being more numerous/specific than genres). Also not validated
                before sending, same as ``genres``.
            statuses: ``Title.status.id``s to filter by (e.g. ongoing, completed). A title
                matches if its own status is *any* of these (OR, same as ``countries`` — a
                title only has one status, see docs/api-notes.md). ``None`` or an empty list
                applies no status filter. Ids come from ``list_statuses()``.
            countries: ``Country.id``s to filter by. A title matches if its own country is
                *any* of these (OR, not AND like ``genres``/``tags`` — a title only has one
                country of origin, so requiring all of them could never match past the first,
                see docs/api-notes.md). ``None`` or an empty list applies no country filter.
                Ids come from ``list_countries()``. Sent on the wire as the API's ``types[]``
                parameter, not a ``country``/``countries[]`` one — see docs/api-notes.md for
                why (``Country`` mirrors the API's own "type" concept, which isn't strictly
                limited to literal countries).
            min_chapters: Only titles with at least this many chapters (inclusive). Counts
                the same number as ``Title.chapter_count`` (uploaded chapters). ``None``
                (the default) applies no lower bound.
            max_chapters: Only titles with at most this many chapters (inclusive). ``None``
                (the default) applies no upper bound.
            sort: Sort order. Despite the name, this is sent as the API's ``sort_by``
                parameter — an actual ``sort`` parameter exists but is silently ignored by
                the API (see docs/api-notes.md). Known accepted values: ``"name"``,
                ``"created_at"``, ``"views"``, ``"chap_count"``, ``"last_chapter_at"``
                (the default), ``"rate_avg"``, ``"random"`` — this list isn't guaranteed
                exhaustive.
            refresh: Bypass the disk cache and re-fetch from the API even if this exact
                combination of parameters was already cached.

        Returns:
            A ``CatalogPage``: the matching titles (as ``Title`` models) plus whether a next
            page exists.

        Raises:
            ValueError: If ``page`` is less than 1, ``per_page`` is outside
                ``MIN_PER_PAGE..MAX_PER_PAGE``, ``min_chapters``/``max_chapters`` is
                negative, or ``min_chapters`` is greater than ``max_chapters``.
        """
        if page < 1:
            raise ValueError(f"page must be at least 1, got {page}.")
        if not MIN_PER_PAGE <= per_page <= MAX_PER_PAGE:
            raise ValueError(
                f"per_page must be between {MIN_PER_PAGE} and {MAX_PER_PAGE}, got {per_page}."
            )
        for name, value in (("min_chapters", min_chapters), ("max_chapters", max_chapters)):
            if value is not None and value < 0:
                raise ValueError(f"{name} must be at least 0, got {value}.")
        if min_chapters is not None and max_chapters is not None and min_chapters > max_chapters:
            # The API itself silently swaps the bounds instead (see docs/api-notes.md) —
            # raising here rather than relying on that undocumented behavior.
            raise ValueError(
                f"min_chapters ({min_chapters}) must not be greater than "
                f"max_chapters ({max_chapters})."
            )

        key = _cache_key(
            page=page,
            per_page=per_page,
            query=query,
            genres=genres,
            tags=tags,
            statuses=statuses,
            countries=countries,
            min_chapters=min_chapters,
            max_chapters=max_chapters,
            sort=sort,
        )
        if not refresh:
            cached = self._cache.get(key)
            if cached is not None:
                return _build_page(cached)

        data = await self._client.list_titles(
            page=page,
            per_page=per_page,
            query=query,
            genres=genres,
            tags=tags,
            statuses=statuses,
            countries=countries,
            min_chapters=min_chapters,
            max_chapters=max_chapters,
            sort=sort,
        )
        self._cache.set(key, data)
        return _build_page(data)

    async def list_genres(self, *, refresh: bool = False) -> list[Genre]:
        """Fetch the full list of catalog genres (id → name), for use as filter options
        with ``list_titles(genres=[...])``.

        The underlying endpoint (``GET /api/constants?fields[]=genres``) has no site-scoping
        parameter — it returns the full genre list shared across the whole lib.social
        network in one shot, each tagged with the site ids it applies to (see
        docs/api-notes.md). This filters that down to genres tagged for ranobelib.me before
        returning, so callers don't get filter options (e.g. "Детское") that could never
        match any ranobelib title.

        Args:
            refresh: Bypass the disk cache and re-fetch from the API even if the genre list
                was already cached.

        Returns:
            Every ``Genre`` (id, name, adult flag) that applies to ranobelib.me.
        """
        key = "catalog:genres"
        if not refresh:
            cached = self._cache.get(key)
            if cached is not None:
                return _build_genres(cached)

        data = await self._client.list_genres()
        self._cache.set(key, data)
        return _build_genres(data)

    async def list_countries(self, *, refresh: bool = False) -> list[Country]:
        """Fetch the full list of catalog countries (id → name), for use as filter options
        with ``list_titles(countries=...)``.

        Mirrors ``list_genres()`` exactly, down to the network-wide, not-site-scoped shape
        of the underlying endpoint (``GET /api/constants?fields[]=types`` — the API's own
        name for what this SDK calls "country" is "type", see docs/api-notes.md and
        ``Country``'s docstring). This filters that down to entries tagged for ranobelib.me
        before returning, same as ``list_genres()`` does for genres.

        Args:
            refresh: Bypass the disk cache and re-fetch from the API even if the country
                list was already cached.

        Returns:
            Every ``Country`` (id, name) that applies to ranobelib.me.
        """
        key = "catalog:countries"
        if not refresh:
            cached = self._cache.get(key)
            if cached is not None:
                return _build_countries(cached)

        data = await self._client.list_countries()
        self._cache.set(key, data)
        return _build_countries(data)

    async def list_statuses(self, *, refresh: bool = False) -> list[Label]:
        """Fetch the full list of title statuses (id → label), for use as filter options
        with ``list_titles(statuses=...)``.

        Mirrors ``list_genres()``/``list_countries()``: the underlying endpoint
        (``GET /api/constants?fields[]=status``) isn't site-scoped, so entries not tagged for
        ranobelib.me are dropped before returning (see docs/api-notes.md). Returns the same
        ``Label`` model as ``Title.status``, so a title's status can be compared against
        these directly.

        Args:
            refresh: Bypass the disk cache and re-fetch from the API even if the status list
                was already cached.

        Returns:
            Every status (``Label``: id, label) that applies to ranobelib.me.
        """
        key = "catalog:statuses"
        if not refresh:
            cached = self._cache.get(key)
            if cached is not None:
                return _build_statuses(cached)

        data = await self._client.list_statuses()
        self._cache.set(key, data)
        return _build_statuses(data)


def _cache_key(
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
) -> str:
    genres_part = ",".join(str(genre_id) for genre_id in genres or [])
    tags_part = ",".join(str(tag_id) for tag_id in tags or [])
    statuses_part = ",".join(str(status_id) for status_id in statuses or [])
    countries_part = ",".join(str(country_id) for country_id in countries or [])
    return (
        f"catalog:{page}:{per_page}:{query or ''}:{genres_part}:{tags_part}:"
        f"{statuses_part}:{countries_part}:{min_chapters}:{max_chapters}:{sort}"
    )


def _build_page(data: dict[str, Any]) -> CatalogPage:
    items = [Title.model_validate(item) for item in data["data"]]
    meta = data["meta"]
    return CatalogPage(items=items, page=meta["current_page"], has_next_page=meta["has_next_page"])


def _build_genres(data: list[dict[str, Any]]) -> list[Genre]:
    site_id = int(RANOBELIB_SITE_ID)
    return [Genre.model_validate(item) for item in data if site_id in item.get("site_ids", [])]


def _build_countries(data: list[dict[str, Any]]) -> list[Country]:
    site_id = int(RANOBELIB_SITE_ID)
    return [Country.model_validate(item) for item in data if site_id in item.get("site_ids", [])]


def _build_statuses(data: list[dict[str, Any]]) -> list[Label]:
    site_id = int(RANOBELIB_SITE_ID)
    return [Label.model_validate(item) for item in data if site_id in item.get("site_ids", [])]

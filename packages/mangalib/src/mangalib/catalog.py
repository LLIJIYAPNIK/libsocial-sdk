"""Catalog listing/search: the ``Catalog`` class.

Catalog listing isn't scoped to any title, so it's a separate entry point rather than a
method on ``MangaLib``. The listing itself is ``libsocial-core``'s (``libsocial.Catalog``);
this class points it at mangalib.me and its own models.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from libsocial import Catalog as _CoreCatalog
from libsocial.catalog import DEFAULT_SORT, MAX_PER_PAGE, MIN_PER_PAGE
from mangalib._http import MANGALIB
from mangalib.cache import DEFAULT_CACHE_DIR
from mangalib.client import ApiClient
from mangalib.models import CatalogPage, Title

__all__ = ["DEFAULT_SORT", "MAX_PER_PAGE", "MIN_PER_PAGE", "Catalog"]


class Catalog(_CoreCatalog[Title]):
    """Entry point for listing/searching the mangalib.me catalog.

    Lists titles (``list_titles()``) and the filter options for them (``list_genres()``,
    ``list_countries()`` — on mangalib.me these are the title types: manga, manhwa, manhua,
    ... — and ``list_statuses()``), each filtered to mangalib.me.

    Example:
        ```python
        async with Catalog() as catalog:
            page = await catalog.list_titles(query="chainsaw", statuses=[1])
            for title in page.items:
                print(title.name)
        ```
    """

    site = MANGALIB
    page_model = CatalogPage

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
                of listing parameters. Defaults to ``.mangalib_cache`` in the current
                working directory, the same as ``MangaLib``'s.
            cache_ttl: Seconds after which a cached page is treated as stale and re-fetched.
                ``None`` (the default) means cached pages never expire on their own — see
                ``refresh=True`` on ``list_titles()`` to force one anyway.
            headers: Extra HTTP headers merged over the SDK's defaults, same as
                ``MangaLib(headers=...)`` — see there.
        """
        super().__init__(
            cache_dir=cache_dir if cache_dir is not None else DEFAULT_CACHE_DIR,
            cache_ttl=cache_ttl,
            headers=headers,
        )

    def _create_client(self, headers: Mapping[str, str] | None) -> ApiClient:
        return ApiClient(headers=headers)

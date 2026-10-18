"""Catalog listing/search: the ``Catalog`` class.

Unlike ``RanobeLib`` (scoped to one title via its URL/slug), catalog listing isn't scoped to
any title at all — see CLAUDE.md's roadmap entry for why this is a separate entry point
rather than a method on ``RanobeLib``. The listing itself is ``libsocial-core``'s
(``libsocial.Catalog``); this class points it at ranobelib.me and its own models.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from libsocial import Catalog as _CoreCatalog
from libsocial.catalog import DEFAULT_SORT, MAX_PER_PAGE, MIN_PER_PAGE
from ranobelib._http import RANOBELIB
from ranobelib.cache import DEFAULT_CACHE_DIR
from ranobelib.client import ApiClient
from ranobelib.models import CatalogPage, Title

__all__ = ["DEFAULT_SORT", "MAX_PER_PAGE", "MIN_PER_PAGE", "Catalog"]


class Catalog(_CoreCatalog[Title]):
    """Entry point for listing/searching the ranobelib.me catalog.

    Lists titles (``list_titles()``) and the filter options for them (``list_genres()``,
    ``list_countries()``, ``list_statuses()``), each filtered to ranobelib.me.

    Example:
        ```python
        async with Catalog() as catalog:
            page = await catalog.list_titles(query="dxd", genres=[34], statuses=[1])
            for title in page.items:
                print(title.name)
        ```
    """

    site = RANOBELIB
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
                of listing parameters (page/filters/sort) — same disk cache as ``RanobeLib``
                uses, just keyed by listing parameters instead of a title's slug. Defaults
                to ``.ranobelib_cache`` in the current working directory.
            cache_ttl: Seconds after which a cached page is treated as stale and re-fetched.
                ``None`` (the default) means cached pages never expire on their own — see
                ``refresh=True`` on ``list_titles()`` to force one anyway.
            headers: Extra HTTP headers merged over the SDK's defaults, same as
                ``RanobeLib(headers=...)`` — see there.
        """
        super().__init__(
            cache_dir=cache_dir if cache_dir is not None else DEFAULT_CACHE_DIR,
            cache_ttl=cache_ttl,
            headers=headers,
        )

    def _create_client(self, headers: Mapping[str, str] | None) -> ApiClient:
        return ApiClient(headers=headers)

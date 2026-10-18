"""Unit tests for libsocial.catalog.Catalog, using a mock transport (no network).

Tests taking the ``site`` fixture run once per site: the catalog must list, filter and cache
for whichever site its subclass names.
"""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

from libsocial.catalog import Catalog, _cache_key
from libsocial.client import ApiClient
from libsocial.models import CatalogPage, Country, Genre, Label, Title
from libsocial.pacing import Pacer
from libsocial.site import Site

_TITLE_ITEM = {
    "id": 1,
    "name": "Example",
    "slug": "example",
    "slug_url": "1--example",
    "cover": {},
    "ageRestriction": {"id": 0, "label": "16+"},
    "status": {"id": 1, "label": "Ongoing"},
}

# /constants lists are network-wide: each entry says which sites it's for.
_GENRES = [
    {"id": 34, "name": "Боевик", "adult": False, "site_ids": [1, 2, 3, 4, 5]},
    {"id": 88, "name": "Детское", "adult": False, "site_ids": [5]},
    {"id": 90, "name": "Ranobelib only", "adult": False, "site_ids": [3]},
    {"id": 91, "name": "Mangalib only", "adult": False, "site_ids": [1]},
]
_TYPES = [
    {"id": 1, "label": "Манга", "site_ids": [1, 2, 4]},
    {"id": 10, "label": "Япония", "site_ids": [3]},
]
_STATUSES = [
    {"id": 1, "label": "Онгоинг", "site_ids": [0, 1, 2, 3, 4, 5]},
    {"id": 6, "label": "Other site only", "site_ids": [5]},
]


class _SiteTitle(Title):
    """Stands in for a site package's own Title subclass."""


def _catalog(
    site: Site,
    tmp_path: Path,
    handler: Callable[[httpx.Request], httpx.Response] | None = None,
    **kwargs: Any,
) -> Catalog[_SiteTitle]:
    class SiteCatalog(Catalog[_SiteTitle]):
        pass

    SiteCatalog.site = site
    SiteCatalog.title_model = _SiteTitle
    catalog = SiteCatalog(cache_dir=tmp_path, **kwargs)
    if handler is not None:
        catalog._client = ApiClient(site, transport=httpx.MockTransport(handler), pacer=Pacer())
    return catalog


def _constants_handler(
    calls: list[httpx.Request] | None = None,
) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(request)
        field = request.url.params["fields[]"]
        data = {"genres": _GENRES, "types": _TYPES, "status": _STATUSES}[field]
        return httpx.Response(200, json={"data": {field: data}})

    return handler


async def test_list_titles_scopes_the_listing_to_the_site_and_uses_its_title_model(
    site: Site, tmp_path: Path
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params.get_list("site_id[]") == [str(site.id)]
        assert request.headers["Site-Id"] == str(site.id)
        return httpx.Response(
            200, json={"data": [_TITLE_ITEM], "meta": {"current_page": 2, "has_next_page": True}}
        )

    async with _catalog(site, tmp_path, handler) as catalog:
        page = await catalog.list_titles(page=2)

    assert isinstance(page, CatalogPage)
    assert isinstance(page.items[0], _SiteTitle)
    assert page.items[0].id == 1
    assert page.page == 2
    assert page.has_next_page is True


async def test_list_titles_handles_empty_results(site: Site, tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"data": [], "meta": {"current_page": 5, "has_next_page": False}}
        )

    async with _catalog(site, tmp_path, handler) as catalog:
        page = await catalog.list_titles(page=5)

    assert page.items == []
    assert page.has_next_page is False


async def test_list_titles_is_cached_per_parameters_until_refresh(
    site: Site, tmp_path: Path
) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200, json={"data": [_TITLE_ITEM], "meta": {"current_page": 1, "has_next_page": False}}
        )

    async with _catalog(site, tmp_path, handler) as catalog:
        first = await catalog.list_titles(query="dxd")
        cached = await catalog.list_titles(query="dxd")
        assert calls == 1
        await catalog.list_titles(query="other")
        assert calls == 2
        await catalog.list_titles(query="dxd", refresh=True)
        assert calls == 3

    assert cached == first
    assert isinstance(cached.items[0], _SiteTitle)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"page": 0},
        {"per_page": 9},
        {"per_page": 61},
        {"min_chapters": -1},
        {"max_chapters": -1},
        {"min_chapters": 10, "max_chapters": 5},
    ],
)
async def test_list_titles_rejects_invalid_arguments_before_any_request(
    site: Site, tmp_path: Path, kwargs: dict[str, Any]
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover - must not run
        raise AssertionError("no request expected")

    async with _catalog(site, tmp_path, handler) as catalog:
        with pytest.raises(ValueError):
            await catalog.list_titles(**kwargs)


async def test_list_genres_keeps_only_genres_tagged_for_the_site(
    site: Site, tmp_path: Path
) -> None:
    async with _catalog(site, tmp_path, _constants_handler()) as catalog:
        genres = await catalog.list_genres()

    expected = [genre["id"] for genre in _GENRES if site.id in genre["site_ids"]]
    assert [genre.id for genre in genres] == expected
    assert all(isinstance(genre, Genre) for genre in genres)
    assert 88 not in expected  # Site 5 only: never offered on either test site.


async def test_list_countries_keeps_only_types_tagged_for_the_site(
    site: Site, tmp_path: Path
) -> None:
    async with _catalog(site, tmp_path, _constants_handler()) as catalog:
        countries = await catalog.list_countries()

    expected = [Country.model_validate(t) for t in _TYPES if site.id in t["site_ids"]]
    assert countries == expected


async def test_list_statuses_keeps_only_statuses_tagged_for_the_site(
    site: Site, tmp_path: Path
) -> None:
    async with _catalog(site, tmp_path, _constants_handler()) as catalog:
        statuses = await catalog.list_statuses()

    assert statuses == [Label(id=1, label="Онгоинг")]


@pytest.mark.parametrize("method", ["list_genres", "list_countries", "list_statuses"])
async def test_constants_lists_are_cached_until_refresh(
    site: Site, tmp_path: Path, method: str
) -> None:
    calls: list[httpx.Request] = []

    async with _catalog(site, tmp_path, _constants_handler(calls)) as catalog:
        first = await getattr(catalog, method)()
        cached = await getattr(catalog, method)()
        await getattr(catalog, method)(refresh=True)

    assert cached == first
    assert len(calls) == 2


async def test_constants_cache_is_filtered_for_each_site_reading_it(tmp_path: Path) -> None:
    # The cache stores the network-wide list; filtering happens on every read, so two sites
    # sharing one cache_dir still get only their own genres.
    ranobelib, mangalib = Site(3, "https://ranobelib.me"), Site(1, "https://mangalib.me")
    async with _catalog(ranobelib, tmp_path, _constants_handler()) as catalog:
        await catalog.list_genres()
    async with _catalog(mangalib, tmp_path) as catalog:
        genres = await catalog.list_genres()  # Served from the cache, no handler needed.

    assert [genre.id for genre in genres] == [34, 91]


async def test_list_titles_cache_is_not_shared_between_sites(tmp_path: Path) -> None:
    # Same parameters, same cache_dir: each site still gets its own listing, not the page
    # cached for the other one (the listing is scoped by site_id[]).
    ranobelib, mangalib = Site(3, "https://ranobelib.me"), Site(1, "https://mangalib.me")
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        site_id = request.url.params["site_id[]"]
        requested.append(site_id)
        item = {**_TITLE_ITEM, "id": int(site_id), "name": f"Site {site_id} title"}
        return httpx.Response(
            200, json={"data": [item], "meta": {"current_page": 1, "has_next_page": False}}
        )

    async with _catalog(ranobelib, tmp_path, handler) as catalog:
        ranobelib_page = await catalog.list_titles(query="dxd")
    async with _catalog(mangalib, tmp_path, handler) as catalog:
        mangalib_page = await catalog.list_titles(query="dxd")
        mangalib_again = await catalog.list_titles(query="dxd")  # Its own cache entry.

    assert requested == ["3", "1"]
    assert [title.name for title in ranobelib_page.items] == ["Site 3 title"]
    assert [title.name for title in mangalib_page.items] == ["Site 1 title"]
    assert mangalib_again == mangalib_page


def test_cache_key_differs_by_site() -> None:
    params: dict[str, Any] = {
        "page": 1,
        "per_page": 30,
        "query": "dxd",
        "genres": None,
        "tags": None,
        "statuses": None,
        "countries": None,
        "min_chapters": None,
        "max_chapters": None,
        "sort": "name",
    }

    assert _cache_key(site_id=3, **params) != _cache_key(site_id=1, **params)


async def test_catalog_headers_are_merged_into_the_api_client(site: Site, tmp_path: Path) -> None:
    async with _catalog(site, tmp_path, headers={"user-agent": "CustomAgent/1.0"}) as catalog:
        sent = catalog._client._http.headers

    assert sent.get_list("User-Agent") == ["CustomAgent/1.0"]
    assert sent["Referer"] == f"{site.origin}/"
    assert sent["Site-Id"] == str(site.id)


async def test_catalog_uses_the_subclass_default_cache_dir(site: Site, tmp_path: Path) -> None:
    class SiteCatalog(Catalog[Title]):
        pass

    SiteCatalog.site = site
    SiteCatalog.title_model = Title
    SiteCatalog.default_cache_dir = tmp_path / "site-cache"

    async with SiteCatalog() as catalog:
        assert catalog._cache._dir == tmp_path / "site-cache"


def test_cache_key_differs_by_page() -> None:
    key1 = _cache_key(
        site_id=3,
        page=1,
        per_page=30,
        query=None,
        genres=None,
        tags=None,
        statuses=None,
        countries=None,
        min_chapters=None,
        max_chapters=None,
        sort="name",
    )
    key2 = _cache_key(
        site_id=3,
        page=2,
        per_page=30,
        query=None,
        genres=None,
        tags=None,
        statuses=None,
        countries=None,
        min_chapters=None,
        max_chapters=None,
        sort="name",
    )

    assert key1 != key2


def test_cache_key_differs_by_every_filter_and_sort() -> None:
    base = _cache_key(
        site_id=3,
        page=1,
        per_page=30,
        query=None,
        genres=None,
        tags=None,
        statuses=None,
        countries=None,
        min_chapters=None,
        max_chapters=None,
        sort="name",
    )

    assert base != _cache_key(
        site_id=3,
        page=1,
        per_page=30,
        query="dxd",
        genres=None,
        tags=None,
        statuses=None,
        countries=None,
        min_chapters=None,
        max_chapters=None,
        sort="name",
    )
    assert base != _cache_key(
        site_id=3,
        page=1,
        per_page=30,
        query=None,
        genres=[34],
        tags=None,
        statuses=None,
        countries=None,
        min_chapters=None,
        max_chapters=None,
        sort="name",
    )
    assert base != _cache_key(
        site_id=3,
        page=1,
        per_page=30,
        query=None,
        genres=None,
        tags=[218],
        statuses=None,
        countries=None,
        min_chapters=None,
        max_chapters=None,
        sort="name",
    )
    assert base != _cache_key(
        site_id=3,
        page=1,
        per_page=30,
        query=None,
        genres=None,
        tags=None,
        statuses=[1, 2],
        countries=None,
        min_chapters=None,
        max_chapters=None,
        sort="name",
    )
    assert base != _cache_key(
        site_id=3,
        page=1,
        per_page=30,
        query=None,
        genres=None,
        tags=None,
        statuses=None,
        countries=[10],
        min_chapters=None,
        max_chapters=None,
        sort="name",
    )
    assert base != _cache_key(
        site_id=3,
        page=1,
        per_page=30,
        query=None,
        genres=None,
        tags=None,
        statuses=None,
        countries=None,
        min_chapters=None,
        max_chapters=None,
        sort="views",
    )
    assert base != _cache_key(
        site_id=3,
        page=1,
        per_page=30,
        query=None,
        genres=None,
        tags=None,
        statuses=None,
        countries=None,
        min_chapters=100,
        max_chapters=None,
        sort="name",
    )
    # The same number as an upper instead of a lower bound is a different query.
    assert _cache_key(
        site_id=3,
        page=1,
        per_page=30,
        query=None,
        genres=None,
        tags=None,
        statuses=None,
        countries=None,
        min_chapters=100,
        max_chapters=None,
        sort="name",
    ) != _cache_key(
        site_id=3,
        page=1,
        per_page=30,
        query=None,
        genres=None,
        tags=None,
        statuses=None,
        countries=None,
        min_chapters=None,
        max_chapters=100,
        sort="name",
    )


def test_cache_key_stable_for_equivalent_calls() -> None:
    key1 = _cache_key(
        site_id=3,
        page=1,
        per_page=30,
        query="dxd",
        genres=[1, 2],
        tags=[218],
        statuses=[1, 2],
        countries=[10, 11],
        min_chapters=None,
        max_chapters=None,
        sort="name",
    )
    key2 = _cache_key(
        site_id=3,
        page=1,
        per_page=30,
        query="dxd",
        genres=[1, 2],
        tags=[218],
        statuses=[1, 2],
        countries=[10, 11],
        min_chapters=None,
        max_chapters=None,
        sort="name",
    )

    assert key1 == key2

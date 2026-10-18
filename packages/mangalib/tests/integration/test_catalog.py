"""Integration tests for mangalib.Catalog, backed by VCR cassettes.

The listing logic is libsocial-core's and tested there; these check it's pointed at
mangalib.me (``site_id[]=1``, lists filtered to site 1) and returns mangalib's models.
"""

import pytest

from mangalib import Catalog, CatalogPage, Title


@pytest.mark.vcr
async def test_list_titles_returns_mangalib_titles() -> None:
    async with Catalog() as catalog:
        page = await catalog.list_titles(query="chainsaw")

    assert isinstance(page, CatalogPage)
    assert page.items and all(isinstance(title, Title) for title in page.items)
    assert "7965--chainsaw-man" in {title.slug_url for title in page.items}


@pytest.mark.vcr
async def test_list_countries_returns_mangalib_types() -> None:
    async with Catalog() as catalog:
        countries = await catalog.list_countries()

    names = {country.name for country in countries}
    assert {"Манга", "Манхва", "Маньхуа"} <= names
    assert "Япония" not in names  # ranobelib.me's


@pytest.mark.vcr
async def test_list_genres_and_statuses_are_filtered_to_mangalib() -> None:
    async with Catalog() as catalog:
        genres = await catalog.list_genres()
        statuses = await catalog.list_statuses()

    assert genres
    assert [status.id for status in statuses] == [1, 2, 3, 4, 5]

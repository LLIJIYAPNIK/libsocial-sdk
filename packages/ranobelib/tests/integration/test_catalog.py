"""Integration tests for Catalog.list_titles(), backed by VCR cassettes.

These exercise the real api.cdnlibs.org API. Cassettes are recorded once (see
tests/conftest.py, record_mode="once") and replayed afterwards, so CI does not need
network access.
"""

from pathlib import Path

import pytest

from ranobelib import Catalog, CatalogPage, Country, Genre, Label, Title


@pytest.mark.vcr
async def test_list_titles_returns_matching_titles() -> None:
    async with Catalog() as catalog:
        page = await catalog.list_titles(query="dxd")

    assert isinstance(page, CatalogPage)
    assert page.page == 1
    assert isinstance(page.has_next_page, bool)
    assert page.items
    assert all(isinstance(item, Title) for item in page.items)
    # Every result should be a real DxD-adjacent title, matched by name/rus_name/eng_name.
    assert any("dxd" in (item.eng_name or "").lower() for item in page.items)


@pytest.mark.vcr
async def test_list_titles_filters_by_status() -> None:
    async with Catalog() as catalog:
        page = await catalog.list_titles(statuses=[1], per_page=10)

    assert page.items
    assert all(item.status.id == 1 for item in page.items)


@pytest.mark.vcr
async def test_list_titles_statuses_filter_uses_or_not_and_semantics() -> None:
    async with Catalog() as catalog:
        # 1 = ongoing, 2 = completed (see docs/api-notes.md, "Status filter"). OR, same as
        # `countries` — a title only has one status. Confirmed by checking both ids show up
        # in the combined results, not just one.
        page = await catalog.list_titles(statuses=[1, 2], per_page=60, sort="name")

    assert {item.status.id for item in page.items} == {1, 2}


@pytest.mark.vcr
async def test_list_titles_filters_by_country() -> None:
    async with Catalog() as catalog:
        # 11 = Korea (see docs/api-notes.md, "Country/origin filter").
        page = await catalog.list_titles(countries=[11], per_page=10)

    assert page.items
    assert all(item.country is not None and item.country.id == 11 for item in page.items)


@pytest.mark.vcr
async def test_list_titles_countries_filter_uses_or_not_and_semantics() -> None:
    async with Catalog() as catalog:
        # 10 = Japan, 11 = Korea (see docs/api-notes.md, "Country/origin filter"). Unlike
        # `genres`/`tags`, this is OR, not AND — a title only ever has one country, so
        # requiring all of the given ids could never match past the first one. Confirmed by
        # checking both ids show up in the combined results, not just one.
        page = await catalog.list_titles(countries=[10, 11], per_page=60, sort="name")

    country_ids = {item.country.id for item in page.items if item.country is not None}
    assert country_ids == {10, 11}


@pytest.mark.vcr
async def test_list_titles_filters_by_genres_and_statuses_combined() -> None:
    async with Catalog() as catalog:
        page = await catalog.list_titles(genres=[34], statuses=[1], per_page=10)

    assert isinstance(page, CatalogPage)
    assert all(item.status.id == 1 for item in page.items)


@pytest.mark.vcr
async def test_list_titles_filters_by_tags() -> None:
    async with Catalog() as catalog:
        # 218 = "Боги" (Gods) — see docs/api-notes.md, "Tag filter". Catalog listing items
        # don't send `tags` (same as `genres`, see docs/api-notes.md), so unlike the country
        # filter test above this can only confirm the filter narrows results, not inspect
        # each item's tags directly.
        page = await catalog.list_titles(tags=[218], per_page=10)

    assert page.items


@pytest.mark.vcr
async def test_list_titles_tags_filter_uses_and_not_or_semantics() -> None:
    async with Catalog() as catalog:
        # Combining a real tag id with a nonexistent one: an OR filter would still match on
        # the real id, an AND filter matches nothing — confirms `tags` behaves like `genres`
        # (AND), not the OR the linked issue considered plausible. See docs/api-notes.md.
        page = await catalog.list_titles(tags=[218, 999999], per_page=10)

    assert page.items == []


@pytest.mark.vcr
async def test_list_titles_pagination_advances_to_different_items() -> None:
    async with Catalog() as catalog:
        first = await catalog.list_titles(page=1, per_page=10, sort="name")
        second = await catalog.list_titles(page=2, per_page=10, sort="name")

    first_ids = {item.id for item in first.items}
    second_ids = {item.id for item in second.items}
    assert first_ids.isdisjoint(second_ids)


@pytest.mark.vcr
async def test_list_titles_page_past_the_end_returns_empty_with_no_more_pages() -> None:
    async with Catalog() as catalog:
        page = await catalog.list_titles(page=99999, statuses=[1], per_page=10)

    assert page.items == []
    assert page.has_next_page is False


@pytest.mark.vcr
async def test_list_titles_second_call_same_params_is_served_from_cache(
    tmp_path: Path, vcr: object
) -> None:
    async with Catalog(cache_dir=tmp_path) as catalog:
        first = await catalog.list_titles(query="dxd")
        second = await catalog.list_titles(query="dxd")

    assert first == second
    assert len(vcr.requests) == 1  # type: ignore[attr-defined]


@pytest.mark.vcr
async def test_list_titles_refresh_bypasses_cache(tmp_path: Path, vcr: object) -> None:
    async with Catalog(cache_dir=tmp_path) as catalog:
        await catalog.list_titles(query="dxd")
        await catalog.list_titles(query="dxd", refresh=True)

    assert len(vcr.requests) == 2  # type: ignore[attr-defined]


async def test_list_titles_rejects_page_below_one() -> None:
    async with Catalog() as catalog:
        with pytest.raises(ValueError, match="page"):
            await catalog.list_titles(page=0)


@pytest.mark.parametrize("per_page", [9, 61])
async def test_list_titles_rejects_per_page_out_of_range(per_page: int) -> None:
    async with Catalog() as catalog:
        with pytest.raises(ValueError, match="per_page"):
            await catalog.list_titles(per_page=per_page)


@pytest.mark.parametrize(
    "bounds",
    [{"min_chapters": -1}, {"max_chapters": -1}, {"min_chapters": 500, "max_chapters": 100}],
)
async def test_list_titles_rejects_invalid_chapter_bounds(bounds: dict[str, int]) -> None:
    async with Catalog() as catalog:
        with pytest.raises(ValueError, match="chapters"):
            await catalog.list_titles(**bounds)


@pytest.mark.vcr
async def test_list_titles_chapter_bounds_are_inclusive() -> None:
    async with Catalog() as catalog:
        # 6712 (High School DxD, completed) has exactly 308 chapters — see
        # examples/01_title_metadata.py's expected output. Catalog items don't carry a chapter
        # count (see docs/api-notes.md), so a title known to sit exactly on both bounds is
        # the check.
        page = await catalog.list_titles(min_chapters=308, max_chapters=308, per_page=60)

    assert any(item.id == 6712 for item in page.items)


@pytest.mark.vcr
async def test_list_titles_min_chapters_above_every_title_matches_nothing() -> None:
    async with Catalog() as catalog:
        page = await catalog.list_titles(min_chapters=99_999_999, per_page=10)

    assert page.items == []


@pytest.mark.vcr
async def test_list_genres_returns_genres_with_id_and_name() -> None:
    async with Catalog() as catalog:
        genres = await catalog.list_genres()

    assert genres
    assert all(isinstance(genre, Genre) for genre in genres)
    assert all(genre.id and genre.name for genre in genres)
    # Genre 34 is used elsewhere in this test suite as a `list_titles(genres=[34])` filter
    # value (see test_list_titles_filters_by_genres_and_statuses_combined) — confirm it
    # resolves to a real name here.
    assert any(genre.id == 34 and genre.name == "Боевик" for genre in genres)


@pytest.mark.vcr
async def test_list_genres_excludes_genres_not_tagged_for_ranobelib() -> None:
    async with Catalog() as catalog:
        genres = await catalog.list_genres()

    # Genre 88 ("Детское") is tagged site_ids: [5] only in the raw API response (see
    # docs/api-notes.md) — ranobelib.me is site 3, so it must be filtered out.
    assert all(genre.id != 88 for genre in genres)


@pytest.mark.vcr
async def test_list_genres_second_call_same_params_is_served_from_cache(
    tmp_path: Path, vcr: object
) -> None:
    async with Catalog(cache_dir=tmp_path) as catalog:
        first = await catalog.list_genres()
        second = await catalog.list_genres()

    assert first == second
    assert len(vcr.requests) == 1  # type: ignore[attr-defined]


@pytest.mark.vcr
async def test_list_genres_refresh_bypasses_cache(tmp_path: Path, vcr: object) -> None:
    async with Catalog(cache_dir=tmp_path) as catalog:
        await catalog.list_genres()
        await catalog.list_genres(refresh=True)

    assert len(vcr.requests) == 2  # type: ignore[attr-defined]


@pytest.mark.vcr
async def test_list_countries_returns_countries_with_id_and_name() -> None:
    async with Catalog() as catalog:
        countries = await catalog.list_countries()

    assert countries
    assert all(isinstance(country, Country) for country in countries)
    assert all(country.id and country.name for country in countries)
    # Id 11 is used elsewhere in this test suite as a `list_titles(countries=[11])` filter
    # value (see test_list_titles_filters_by_country) — confirm it resolves to "Корея" (Korea)
    # here.
    assert any(country.id == 11 and country.name == "Корея" for country in countries)


@pytest.mark.vcr
async def test_list_countries_excludes_types_not_tagged_for_ranobelib() -> None:
    async with Catalog() as catalog:
        countries = await catalog.list_countries()

    # Type 1 ("Манга") is tagged site_ids: [1, 2, 4] only in the raw API response (see
    # docs/api-notes.md, "Country/origin filter") — ranobelib.me is site 3, so it must be
    # filtered out, same as list_genres() does for genre 88.
    assert all(country.id != 1 for country in countries)


@pytest.mark.vcr
async def test_list_countries_second_call_same_params_is_served_from_cache(
    tmp_path: Path, vcr: object
) -> None:
    async with Catalog(cache_dir=tmp_path) as catalog:
        first = await catalog.list_countries()
        second = await catalog.list_countries()

    assert first == second
    assert len(vcr.requests) == 1  # type: ignore[attr-defined]


@pytest.mark.vcr
async def test_list_countries_refresh_bypasses_cache(tmp_path: Path, vcr: object) -> None:
    async with Catalog(cache_dir=tmp_path) as catalog:
        await catalog.list_countries()
        await catalog.list_countries(refresh=True)

    assert len(vcr.requests) == 2  # type: ignore[attr-defined]


@pytest.mark.vcr
async def test_list_statuses_returns_statuses_with_id_and_label() -> None:
    async with Catalog() as catalog:
        statuses = await catalog.list_statuses()

    assert statuses
    assert all(isinstance(status, Label) for status in statuses)
    assert all(status.id and status.label for status in statuses)
    # Ids 1 and 2 are used as `list_titles(statuses=[...])` filter values elsewhere in this
    # test suite — confirm they resolve to the labels Title.status carries for them.
    assert Label(id=1, label="Онгоинг") in statuses
    assert Label(id=2, label="Завершён") in statuses


@pytest.mark.vcr
async def test_list_statuses_second_call_same_params_is_served_from_cache(
    tmp_path: Path, vcr: object
) -> None:
    async with Catalog(cache_dir=tmp_path) as catalog:
        first = await catalog.list_statuses()
        second = await catalog.list_statuses()

    assert first == second
    assert len(vcr.requests) == 1  # type: ignore[attr-defined]


@pytest.mark.vcr
async def test_list_statuses_refresh_bypasses_cache(tmp_path: Path, vcr: object) -> None:
    async with Catalog(cache_dir=tmp_path) as catalog:
        await catalog.list_statuses()
        await catalog.list_statuses(refresh=True)

    assert len(vcr.requests) == 2  # type: ignore[attr-defined]

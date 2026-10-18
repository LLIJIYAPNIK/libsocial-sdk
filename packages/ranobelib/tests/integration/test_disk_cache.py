"""Integration tests for RanobeLib's disk cache, backed by VCR cassettes.

Each test's cassette proves caching by its own interaction count (asserted via
``len(vcr.requests)``, from pytest-recording/vcrpy's `vcr` fixture) rather than just by not
erroring: a cassette recorded once caching worked correctly has exactly as many interactions
as real requests should happen, so a future regression that makes the code fetch more than
that would fail here (VCR has no interaction left to replay), not silently pass.

Tests use their own isolated cache_dir (tmp_path) even though tests/conftest.py's autouse
fixture already redirects RanobeLib's *default* cache_dir per test — passing it explicitly
here makes each test's caching behavior the point, not an implicit side effect.
"""

from pathlib import Path

import pytest

from ranobelib import RanobeLib


@pytest.mark.vcr
async def test_get_info_second_call_is_served_from_cache(tmp_path: Path, vcr: object) -> None:
    async with RanobeLib(
        "https://ranobelib.me/ru/book/91443--new-hero-in-dxd", cache_dir=tmp_path
    ) as lib:
        first = await lib.get_info()
        second = await lib.get_info()

    assert first == second
    assert len(vcr.requests) == 1  # type: ignore[attr-defined]


@pytest.mark.vcr
async def test_get_info_refresh_bypasses_cache(tmp_path: Path, vcr: object) -> None:
    async with RanobeLib(
        "https://ranobelib.me/ru/book/91443--new-hero-in-dxd", cache_dir=tmp_path
    ) as lib:
        await lib.get_info()
        await lib.get_info(refresh=True)

    assert len(vcr.requests) == 2  # type: ignore[attr-defined]


@pytest.mark.vcr
async def test_get_table_of_contents_second_call_is_served_from_cache(
    tmp_path: Path, vcr: object
) -> None:
    async with RanobeLib(
        "https://ranobelib.me/ru/book/91443--new-hero-in-dxd", cache_dir=tmp_path
    ) as lib:
        first = await lib.get_table_of_contents()
        second = await lib.get_table_of_contents()

    assert first == second
    assert len(vcr.requests) == 1  # type: ignore[attr-defined]


@pytest.mark.vcr
async def test_get_chapter_second_call_is_served_from_cache(tmp_path: Path, vcr: object) -> None:
    # First call: one request for the chapter list (to check for translation ambiguity)
    # plus one for the chapter content. Second call should hit neither, since both are
    # cached (the chapter list is what makes get_chapter's caching worth having at all —
    # see docs/api-notes.md's "Translation selection" section on why it fetches that list).
    async with RanobeLib(
        "https://ranobelib.me/ru/book/91443--new-hero-in-dxd", cache_dir=tmp_path
    ) as lib:
        first = await lib.get_chapter(volume=1, number="1")
        second = await lib.get_chapter(volume=1, number="1")

    assert first == second
    assert len(vcr.requests) == 2  # type: ignore[attr-defined]

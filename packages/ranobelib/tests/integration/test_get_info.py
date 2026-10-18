"""Integration tests for RanobeLib.get_info(), backed by VCR cassettes.

These exercise the real api.cdnlibs.org API. Cassettes are recorded once (see
tests/conftest.py, record_mode="once") and replayed afterwards, so CI does not need
network access.
"""

import pytest

from ranobelib import RanobeLib, Title, TitleNotFoundError


@pytest.mark.vcr
async def test_get_info_returns_title_metadata() -> None:
    async with RanobeLib("https://ranobelib.me/ru/book/91443--new-hero-in-dxd") as lib:
        info = await lib.get_info()

    assert isinstance(info, Title)
    assert info.id == 91443
    assert info.slug_url == "91443--new-hero-in-dxd"
    assert info.name
    assert info.summary
    assert info.chapter_count is not None
    assert info.chapter_count > 0
    assert info.last_chapter_at is not None
    assert info.genres
    assert info.teams


@pytest.mark.vcr
async def test_get_info_raises_title_not_found_for_missing_title() -> None:
    url = "https://ranobelib.me/ru/book/1--this-title-does-not-exist-zzz"
    async with RanobeLib(url) as lib:
        with pytest.raises(TitleNotFoundError):
            await lib.get_info()

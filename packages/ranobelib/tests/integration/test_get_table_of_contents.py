"""Integration tests for RanobeLib.get_table_of_contents(), backed by VCR cassettes.

These exercise the real api.cdnlibs.org API. Cassettes are recorded once (see
tests/conftest.py, record_mode="once") and replayed afterwards, so CI does not need
network access.
"""

import pytest

from ranobelib import RanobeLib, TitleNotFoundError
from ranobelib.models import Volume


@pytest.mark.vcr
async def test_get_table_of_contents_returns_volumes_with_chapters() -> None:
    async with RanobeLib("https://ranobelib.me/ru/book/91443--new-hero-in-dxd") as lib:
        volumes = await lib.get_table_of_contents()

    assert volumes
    assert all(isinstance(volume, Volume) for volume in volumes)

    all_chapters = [chapter for volume in volumes for chapter in volume.chapters]
    assert all_chapters
    for chapter in all_chapters:
        assert chapter.number
    for volume in volumes:
        assert all(chapter.volume == volume.number for chapter in volume.chapters)


@pytest.mark.vcr
async def test_get_table_of_contents_raises_title_not_found_for_missing_title() -> None:
    url = "https://ranobelib.me/ru/book/1--this-title-does-not-exist-zzz"
    async with RanobeLib(url) as lib:
        with pytest.raises(TitleNotFoundError):
            await lib.get_table_of_contents()

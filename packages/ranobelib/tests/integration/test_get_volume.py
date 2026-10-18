"""Integration tests for RanobeLib.get_volume(), backed by VCR cassettes.

These exercise the real api.cdnlibs.org API. Volume 0 of 91443--new-hero-in-dxd has a
single chapter (see docs/api-notes.md's note on there being no bulk "volume content"
endpoint — get_volume fetches the chapter list plus one request per chapter), which keeps
this test's cassette small.
"""

import pytest

from ranobelib import MultipleTranslationsError, RanobeLib, VolumeNotFoundError
from ranobelib.models import Chapter, Volume


@pytest.mark.vcr
async def test_get_volume_returns_all_chapters_with_content() -> None:
    async with RanobeLib("https://ranobelib.me/ru/book/91443--new-hero-in-dxd") as lib:
        volume = await lib.get_volume(0)

    assert isinstance(volume, Volume)
    assert volume.number == "0"
    assert len(volume.chapters) == 1
    chapter = volume.chapters[0]
    assert isinstance(chapter, Chapter)
    assert chapter.volume == "0"
    assert chapter.content is not None
    assert "<p" in chapter.content


@pytest.mark.vcr
async def test_get_volume_raises_volume_not_found_for_missing_volume() -> None:
    async with RanobeLib("https://ranobelib.me/ru/book/91443--new-hero-in-dxd") as lib:
        with pytest.raises(VolumeNotFoundError) as exc_info:
            await lib.get_volume(999)

    assert exc_info.value.volume == "999"


@pytest.mark.vcr
async def test_get_volume_raises_multiple_translations_for_ambiguous_chapter() -> None:
    # 11407--solo-leveling volume 1 starts with chapters that have two translation
    # branches (see docs/api-notes.md's "Translation selection" section) — get_volume
    # can't silently pick one for the caller, same as get_chapter.
    async with RanobeLib("https://ranobelib.me/ru/book/11407--solo-leveling") as lib:
        with pytest.raises(MultipleTranslationsError) as exc_info:
            await lib.get_volume(1)

    assert exc_info.value.volume == "1"

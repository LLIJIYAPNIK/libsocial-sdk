"""Integration tests for RanobeLib.get_chapter(), backed by VCR cassettes.

These exercise the real api.cdnlibs.org API through the public facade (int volume, str
number). See test_get_chapter_content.py for lower-level ApiClient.get_chapter() coverage
of both chapter-content formats, and test_get_translations.py for get_translations()
itself. The multi-branch chapter used below (11407--solo-leveling, volume=1 number=0) is
the same one docs/api-notes.md's "Translation selection" section was researched against.
"""

import pytest

from ranobelib import ChapterNotFoundError, MultipleTranslationsError, RanobeLib
from ranobelib.models import Chapter


@pytest.mark.vcr
async def test_get_chapter_returns_chapter_with_content() -> None:
    async with RanobeLib("https://ranobelib.me/ru/book/91443--new-hero-in-dxd") as lib:
        chapter = await lib.get_chapter(volume=1, number="1")

    assert isinstance(chapter, Chapter)
    assert chapter.volume == "1"
    assert chapter.number == "1"
    assert chapter.content is not None
    assert "<p" in chapter.content


@pytest.mark.vcr
async def test_get_chapter_raises_chapter_not_found_for_missing_chapter() -> None:
    async with RanobeLib("https://ranobelib.me/ru/book/91443--new-hero-in-dxd") as lib:
        with pytest.raises(ChapterNotFoundError):
            await lib.get_chapter(volume=999, number="9999")


@pytest.mark.vcr
async def test_get_chapter_raises_multiple_translations_without_branch_id() -> None:
    async with RanobeLib("https://ranobelib.me/ru/book/11407--solo-leveling") as lib:
        with pytest.raises(MultipleTranslationsError) as exc_info:
            await lib.get_chapter(volume=1, number="0")

    assert exc_info.value.volume == "1"
    assert exc_info.value.number == "0"
    assert {branch.branch_id for branch in exc_info.value.branches} == {2251, 635}


@pytest.mark.vcr
async def test_get_chapter_returns_selected_branch_content() -> None:
    async with RanobeLib("https://ranobelib.me/ru/book/11407--solo-leveling") as lib:
        chapter = await lib.get_chapter(volume=1, number="0", branch_id=2251)

    assert chapter.content is not None

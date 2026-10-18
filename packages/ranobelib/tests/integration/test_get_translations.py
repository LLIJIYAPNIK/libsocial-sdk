"""Integration tests for RanobeLib.get_translations(), backed by VCR cassettes.

Uses 11407--solo-leveling, volume=1 number=0, which has two translation branches (see
docs/api-notes.md's "Translation selection" section for how this chapter was found and how
the two branch_id values were confirmed against the real API).
"""

import pytest

from ranobelib import ChapterNotFoundError, RanobeLib
from ranobelib.models import ChapterBranch


@pytest.mark.vcr
async def test_get_translations_returns_all_branches() -> None:
    async with RanobeLib("https://ranobelib.me/ru/book/11407--solo-leveling") as lib:
        branches = await lib.get_translations(volume=1, number="0")

    assert len(branches) == 2
    assert all(isinstance(branch, ChapterBranch) for branch in branches)
    assert {branch.branch_id for branch in branches} == {2251, 635}


@pytest.mark.vcr
async def test_get_translations_raises_chapter_not_found_for_missing_chapter() -> None:
    async with RanobeLib("https://ranobelib.me/ru/book/11407--solo-leveling") as lib:
        with pytest.raises(ChapterNotFoundError):
            await lib.get_translations(volume=999, number="9999")

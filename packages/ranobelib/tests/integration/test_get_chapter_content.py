"""Integration tests for ApiClient.get_chapter(), backed by VCR cassettes.

These exercise the real api.cdnlibs.org API against chapters known (from manual research,
see docs/api-notes.md) to use each of the two content formats the API returns, at the
client level (raw slug_url/number/volume strings). See test_get_chapter.py for the
RanobeLib facade (int volume, translation selection via branch_id).
"""

import pytest

from ranobelib.client import ApiClient
from ranobelib.exceptions import ChapterNotFoundError
from ranobelib.models import Chapter


@pytest.mark.vcr
async def test_get_chapter_normalizes_html_string_content() -> None:
    async with ApiClient() as client:
        data = await client.get_chapter("91443--new-hero-in-dxd", number="1", volume="1")

    chapter = Chapter.model_validate(data)
    assert chapter.content is not None
    assert "<p" in chapter.content
    assert "<img" in chapter.content


@pytest.mark.vcr
async def test_get_chapter_normalizes_prosemirror_content() -> None:
    async with ApiClient() as client:
        data = await client.get_chapter("6712--high-school-dxd-novel", number="44.2", volume="4")

    chapter = Chapter.model_validate(data)
    assert chapter.content is not None
    assert "<p>" in chapter.content
    assert "<img" in chapter.content


@pytest.mark.vcr
async def test_get_chapter_raises_chapter_not_found_for_bad_number() -> None:
    async with ApiClient() as client:
        with pytest.raises(ChapterNotFoundError):
            await client.get_chapter("91443--new-hero-in-dxd", number="9999", volume="999")

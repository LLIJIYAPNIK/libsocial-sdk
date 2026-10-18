"""Integration tests for MangaLib's size methods, backed by VCR cassettes.

They ask the real image server (``compress``) for ``HEAD`` responses — no image bodies, so
the cassettes stay small.
"""

import pytest

from mangalib import MangaLib

CHAINSAW_MAN = "https://mangalib.me/ru/manga/7965--chainsaw-man"
EARLY_ACCESS = "https://mangalib.me/ru/manga/226780--online-game-god-level-assassin-i-am-the-shadow"


@pytest.mark.vcr
async def test_chapter_size_sums_each_pages_content_length() -> None:
    async with MangaLib(CHAINSAW_MAN) as lib:
        chapter = await lib.get_chapter(volume=1, number="1", branch_id=4667)
        size = await lib.chapter_size(chapter)

    # 55 pages; the first alone is 443,530 bytes (see docs/api-notes.md, "MangaLib").
    assert size > 443_530 * 10


@pytest.mark.vcr
async def test_estimate_title_size_samples_open_chapters_only() -> None:
    async with MangaLib(EARLY_ACCESS) as lib:
        estimate = await lib.estimate_title_size(sample_size=2)
        volumes = await lib.get_table_of_contents()

    chapters = [chapter for volume in volumes for chapter in volume.chapters]
    open_chapters = [chapter for chapter in chapters if chapter.branches[0].is_open]
    assert len(open_chapters) < len(chapters)
    # Two chapters sampled out of the open ones, each a few MB of webtoon strips.
    assert estimate > len(open_chapters) * 100_000

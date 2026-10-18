"""Integration tests for MangaLib's title and chapter methods, backed by VCR cassettes.

Titles used (see docs/api-notes.md, "MangaLib"):

- ``7965--chainsaw-man``: two translations (branch_id 4667 and 4666) of every early chapter.
- ``226780--online-game-god-level-assassin-i-am-the-shadow``: chapter 1/133 was in early
  access when recorded (``restricted_view.is_open: false``), 1/73 had been in early access
  and had opened by then.
"""

import pytest

from mangalib import (
    AuthRequiredError,
    ChapterNotFoundError,
    MangaLib,
    MultipleTranslationsError,
    TitleNotFoundError,
)
from mangalib.models import Chapter, ChapterBranch, Title

CHAINSAW_MAN = "https://mangalib.me/ru/manga/7965--chainsaw-man"
EARLY_ACCESS = "https://mangalib.me/ru/manga/226780--online-game-god-level-assassin-i-am-the-shadow"


@pytest.mark.vcr
async def test_get_info_returns_title_metadata() -> None:
    async with MangaLib(CHAINSAW_MAN) as lib:
        info = await lib.get_info()

    assert isinstance(info, Title)
    assert info.id == 7965
    assert info.name == "Chainsaw Man"
    assert info.rus_name == "Человек-бензопила"
    assert info.country is not None
    assert info.country.name == "Манга"
    assert info.chapter_count is not None and info.chapter_count > 0
    assert info.genres and info.authors


@pytest.mark.vcr
async def test_get_info_raises_title_not_found_for_missing_title() -> None:
    async with MangaLib("999999999--no-such-title") as lib:
        with pytest.raises(TitleNotFoundError):
            await lib.get_info()


@pytest.mark.vcr
async def test_get_table_of_contents_carries_mangalib_branches() -> None:
    async with MangaLib(EARLY_ACCESS) as lib:
        volumes = await lib.get_table_of_contents()

    chapters = {chapter.number: chapter for volume in volumes for chapter in volume.chapters}
    closed = chapters["133"].branches[0]
    assert isinstance(closed, ChapterBranch)
    assert closed.restricted_view is not None
    assert closed.restricted_view.expired_at is not None
    assert not closed.is_open
    assert chapters["73"].branches[0].is_open
    assert all(not chapter.pages for chapter in chapters.values())


@pytest.mark.vcr
async def test_get_chapter_returns_pages_in_reading_order() -> None:
    async with MangaLib(CHAINSAW_MAN) as lib:
        chapter = await lib.get_chapter(volume=1, number="1", branch_id=4667)

    assert isinstance(chapter, Chapter)
    assert chapter.volume == "1"
    assert chapter.number == "1"
    assert len(chapter.pages) == 55
    assert [page.number for page in chapter.pages] == list(range(1, 56))
    first = chapter.pages[0]
    assert first.url == "//manga/chainsaw-man/chapters/1-1/00.png_res.jpg"
    assert (first.width, first.height) == (1425, 2048)
    assert chapter.restricted_view is None


@pytest.mark.vcr
async def test_get_chapter_raises_multiple_translations_without_branch_id() -> None:
    async with MangaLib(CHAINSAW_MAN) as lib:
        with pytest.raises(MultipleTranslationsError) as exc_info:
            await lib.get_chapter(volume=1, number="1")

    assert {branch.branch_id for branch in exc_info.value.branches} == {4667, 4666}


@pytest.mark.vcr
async def test_get_chapter_raises_chapter_not_found_for_missing_chapter() -> None:
    async with MangaLib(CHAINSAW_MAN) as lib:
        with pytest.raises(ChapterNotFoundError):
            await lib.get_chapter(volume=999, number="9999", branch_id=4667)


@pytest.mark.vcr
async def test_get_translations_says_whether_each_is_open() -> None:
    async with MangaLib(EARLY_ACCESS) as lib:
        closed = await lib.get_translations(volume=1, number="133")
        opened = await lib.get_translations(volume=1, number="73")

    assert [(branch.branch_id, branch.is_open) for branch in closed] == [(23320, False)]
    assert [(branch.branch_id, branch.is_open) for branch in opened] == [(23320, True)]
    assert all(isinstance(branch, ChapterBranch) for branch in closed + opened)


@pytest.mark.vcr
async def test_get_translations_raises_chapter_not_found_for_missing_chapter() -> None:
    async with MangaLib(EARLY_ACCESS) as lib:
        with pytest.raises(ChapterNotFoundError):
            await lib.get_translations(volume=999, number="9999")


@pytest.mark.vcr
async def test_get_chapter_raises_auth_required_for_closed_chapter_and_does_not_cache_it() -> None:
    async with MangaLib(EARLY_ACCESS) as lib:
        with pytest.raises(AuthRequiredError) as exc_info:
            await lib.get_chapter(volume=1, number="133")
        # Asked again, the API is asked again: a cached refusal would outlive the chapter
        # opening when its early access ends. (The cassette holds two chapter requests.)
        with pytest.raises(AuthRequiredError):
            await lib.get_chapter(volume=1, number="133")

    assert "/manga/226780--online-game-god-level-assassin-i-am-the-shadow/chapter" in (
        exc_info.value.url
    )
    assert "number=133" in exc_info.value.url


@pytest.mark.vcr
async def test_get_chapter_of_opened_early_access_chapter_returns_pages() -> None:
    async with MangaLib(EARLY_ACCESS) as lib:
        chapter = await lib.get_chapter(volume=1, number="73")

    assert chapter.pages
    assert chapter.restricted_view is not None
    assert chapter.restricted_view.is_open
    assert chapter.restricted_view.price is not None


@pytest.mark.vcr
async def test_list_image_servers_returns_mangalib_servers_only() -> None:
    async with MangaLib(CHAINSAW_MAN) as lib:
        servers = await lib.list_image_servers()

    assert [server.id for server in servers] == [
        "main",
        "secondary",
        "compress",
        "download",
        "crop",
    ]
    assert all("hentai" not in server.url for server in servers)

"""ranobelib and mangalib in one script, and what they share through libsocial-core.

Both packages are built on the core, so their models derive from the same ones and their
exceptions *are* the same classes:

- Models: ranobelib.Title and mangalib.Title are both libsocial.Title (with their own extras,
  e.g. base_names); Person, Team, Cover, Tag, Genre, Label, Country, ChapterBranch and
  ChapterUser are the core's own classes in both. Code that only needs the shared fields can
  take a libsocial.Title and accept either site's.
- Exceptions: every exception either package raises derives from libsocial.LibSocialError —
  ranobelib.RanobeLibError and mangalib.MangaLibError are that same class under another name
  — and the shared ones (TitleNotFoundError, ...) are identical objects. So one
  `except LibSocialError` catches both SDKs' errors. mangalib adds PageDownloadError.
"""

import asyncio
import tempfile

import mangalib
import ranobelib
from libsocial import (
    AccessBlockedError,
    AuthRequiredError,
    ChapterNotFoundError,
    ChapterUser,
    Cover,
    DownloadTitleInterruptedError,
    LibSocialError,
    MultipleTitleTranslationsError,
    MultipleTranslationsError,
    Person,
    RateLimitError,
    Tag,
    Team,
    Title,
    TitleNotFoundError,
    VolumeNotFoundError,
)

SHARED_ERRORS: list[type[LibSocialError]] = [
    TitleNotFoundError,
    ChapterNotFoundError,
    VolumeNotFoundError,
    MultipleTranslationsError,
    MultipleTitleTranslationsError,
    DownloadTitleInterruptedError,
    AuthRequiredError,
    AccessBlockedError,
    RateLimitError,
]


def describe(title: Title) -> str:
    # Takes the core's Title, so either site's title fits.
    authors: list[Person] = title.authors
    cover: Cover = title.cover
    return f"{title.name} by {[a.name for a in authors]}, cover {cover.default is not None}"


async def main() -> None:
    with tempfile.TemporaryDirectory() as cache_dir:
        # One franchise in both catalogs: the novel on ranobelib.me, the manga on mangalib.me.
        async with (
            ranobelib.Catalog(cache_dir=cache_dir) as novels,
            mangalib.Catalog(cache_dir=cache_dir) as manga,
        ):
            novel_page, manga_page = await asyncio.gather(
                novels.list_titles(query="Re:Zero kara Hajimeru", sort="views", per_page=10),
                manga.list_titles(query="Re:Zero kara Hajimeru", sort="views", per_page=10),
            )
        print("ranobelib:", [title.slug_url for title in novel_page.items[:2]])
        print("mangalib:", [title.slug_url for title in manga_page.items[:2]])
        novel_slug, manga_slug = novel_page.items[0].slug_url, manga_page.items[0].slug_url

        async with (
            ranobelib.RanobeLib(novel_slug, cache_dir=cache_dir) as novel,
            mangalib.MangaLib(manga_slug, cache_dir=cache_dir) as comic,
        ):
            novel_info, manga_info = await asyncio.gather(novel.get_info(), comic.get_info())
            for info in (novel_info, manga_info):
                print(
                    f"{type(info).__module__}.Title is a libsocial.Title: {isinstance(info, Title)}"
                )
                print("  ", describe(info))
            tags: list[Tag] = [tag for tag in novel_info.tags if tag in manga_info.tags]
            print("tags on both:", [tag.name for tag in tags])
            teams: list[Team] = manga_info.teams
            print("manga translated by:", [team.name for team in teams])

            # Translations in the table of contents: the core's ChapterBranch / ChapterUser.
            novel_toc, manga_toc = await asyncio.gather(
                novel.get_table_of_contents(), comic.get_table_of_contents()
            )
            for toc in (novel_toc, manga_toc):
                chapters = [chapter for volume in toc for chapter in volume.chapters]
                uploaders: set[int] = set()
                for chapter in chapters:
                    for branch in chapter.branches:
                        user: ChapterUser = branch.user
                        uploaders.add(user.id)
                print(
                    f"{type(chapters[0]).__module__}: {len(chapters)} chapters,",
                    f"uploaded by {len(uploaders)} users",
                )

        # One exception hierarchy.
        print(
            "RanobeLibError is MangaLibError is LibSocialError:",
            ranobelib.RanobeLibError is mangalib.MangaLibError is LibSocialError,
        )
        same = all(
            getattr(ranobelib, e.__name__) is e is getattr(mangalib, e.__name__)
            for e in SHARED_ERRORS
        )
        print(f"{len(SHARED_ERRORS)} shared exceptions, the same classes in both packages: {same}")
        print(
            "mangalib.PageDownloadError is a LibSocialError:",
            issubclass(mangalib.PageDownloadError, LibSocialError),
        )

        async def from_ranobelib() -> None:
            async with ranobelib.RanobeLib(novel_slug, cache_dir=cache_dir) as lib:
                await lib.get_chapter(volume=999, number="1")

        async def from_mangalib() -> None:
            async with mangalib.MangaLib("1--no-such-title", cache_dir=cache_dir) as lib:
                await lib.get_info()

        for call in (from_ranobelib, from_mangalib):
            try:
                await call()
            except LibSocialError as exc:
                print(f"caught {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    asyncio.run(main())

# Expected output (real run against the live sites on 2026-10-25; the searches, chapter counts
# and teams change over time. On Windows without the GTK runtime, importing ranobelib first prints
# WeasyPrint's warning that it couldn't load its libraries: ranobelib's pdf export is then
# unavailable, and nothing else is affected):
#
#
# -----
#
# WeasyPrint could not import some external libraries. Please carefully follow the installation
#   steps before reporting an issue:
# https://doc.courtbouillon.org/weasyprint/stable/first_steps.html#installation
# https://doc.courtbouillon.org/weasyprint/stable/first_steps.html#troubleshooting
#
# -----
#
# ranobelib: ['94231--rezero-kara-hajimeru-isekai-seikatsu-outo-no-ichinichi-hen',
#   '51438--rezero-harem']
# mangalib: ['162683--re', '56275--re-zero-kara-hajimeru-isekai-seikatsu-anthology-comic']
# ranobelib.models.Title is a libsocial.Title: True
#    Re:Zero kara Hajimeru Isekai Seikatsu Outo no Ichinichi Hen by ['Tappei Nagatsuki'], cover True
# mangalib.models.Title is a libsocial.Title: True
#    Re:Zero kara Hajimeru Isekai Seikatsu - Daigoshou - Mizu no Miyako to Eiyuu no Uta by ['Tappei
#   Nagatsuki'], cover True
# tags on both: ['Магия', 'ГГ мужчина', 'Средневековье']
# manga translated by: ['Dead Inside Team', 'Хранилище Плеяд', 'AdzuVerse', 'Chot perevod']
# ranobelib.models: 742 chapters, uploaded by 6 users
# mangalib.models: 16 chapters, uploaded by 6 users
# RanobeLibError is MangaLibError is LibSocialError: True
# 9 shared exceptions, the same classes in both packages: True
# mangalib.PageDownloadError is a LibSocialError: True
# caught ChapterNotFoundError: Chapter not found:
#   '94231--rezero-kara-hajimeru-isekai-seikatsu-outo-no-ichinichi-hen' volume='999' number='1'
# caught TitleNotFoundError: Title not found: '1--no-such-title'

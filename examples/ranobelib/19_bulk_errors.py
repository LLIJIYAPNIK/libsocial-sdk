"""Errors from the bulk methods, and catching every SDK error at once.

11_error_handling.py covers single requests. The bulk methods add two failure modes:

- `VolumeNotFoundError` — get_volume()/get_volumes() asked for a volume number the title
  has no chapters in. get_volumes() checks every requested number against the chapter list
  before downloading anything, so one bad number fails the call up front instead of halfway.
- `MultipleTitleTranslationsError` — download_title() found chapters with more than one
  translation and wasn't told which to take. It checks the whole title first and lists every
  ambiguous chapter (`.chapters`, a list of `AmbiguousChapter(volume, number, branches)`),
  so you can pick once instead of fixing chapters one rerun at a time.

Every exception the SDK raises derives from `RanobeLibError`, so `except RanobeLibError`
catches all of them — when you only need "the SDK couldn't do it" rather than which case.
(`DownloadTitleInterruptedError`, raised when a long download_title() gives up partway and
carries what it already fetched, is described in 08_download_title.py.)
"""

import asyncio

from ranobelib import (
    AmbiguousChapter,
    ChapterBranch,
    MultipleTitleTranslationsError,
    RanobeLib,
    RanobeLibError,
    VolumeNotFoundError,
)


def describe(branch: ChapterBranch) -> str:
    teams = ", ".join(team.name for team in branch.teams) or "no team"
    return f"{branch.branch_id} ({teams})"


def common_branch_ids(chapters: list[AmbiguousChapter]) -> set[int]:
    # branch_id identifies one "line" of translation across the title, so an id present in
    # every ambiguous chapter resolves them all with the same translator.
    ids = [
        {branch.branch_id for branch in chapter.branches if branch.branch_id is not None}
        for chapter in chapters
    ]
    return set.intersection(*ids)


async def main() -> None:
    async with RanobeLib("https://ranobelib.me/ru/book/91443--new-hero-in-dxd") as lib:
        try:
            await lib.get_volume(volume=999)
        except VolumeNotFoundError as exc:
            print(exc)

        # One bad number among good ones: nothing is downloaded, exc.volume says which.
        try:
            await lib.get_volumes([1, 7])
        except VolumeNotFoundError as exc:
            print("bad volume:", exc.volume)

    slug = "113306--bungou-stray-dogs-gaiden-ayatsuji-yukito-vs-kyogoku-natsuhiko"
    async with RanobeLib(f"https://ranobelib.me/ru/book/{slug}") as lib:
        try:
            await lib.download_title()
        except MultipleTitleTranslationsError as exc:
            for chapter in exc.chapters:
                branches = [describe(branch) for branch in chapter.branches]
                print(f"chapter {chapter.volume}/{chapter.number}:", branches)
            common = common_branch_ids(exc.chapters)
            print("branch ids shared by all of them:", sorted(common))

            # Pick one and download again. translation_index=N would instead take the N-th
            # branch of *each* chapter's own list, whose order differs between chapters.
            volumes = await lib.download_title(branch_id=min(common))
            print("downloaded", [chapter.number for chapter in volumes[0].chapters])

        # The base class catches every SDK error, whichever method raised it: here a missing
        # volume, an ambiguous chapter (get_chapter() without a branch_id) and a whole title
        # with ambiguous chapters, all through one except clause.
        attempts = (
            lambda: lib.get_volume(volume=999),
            lambda: lib.get_chapter(volume=1, number="0"),
            lambda: lib.download_title(),
        )
        for attempt in attempts:
            try:
                await attempt()
            except RanobeLibError as exc:
                print("caught", type(exc).__name__)


asyncio.run(main())

# Expected output (real run against the live site):
#
# Volume not found: '91443--new-hero-in-dxd' volume='999'
# bad volume: 7
# chapter 1/0: ['12954 (K&F)', '12955 (ChelkaDostaTrans)']
# chapter 1/1: ['12955 (ChelkaDostaTrans)', '12954 (K&F)']
# chapter 1/2: ['12954 (K&F)', '12955 (ChelkaDostaTrans)']
# branch ids shared by all of them: [12954, 12955]
# downloaded ['0', '1', '2', '3', '4', '5']
# caught VolumeNotFoundError
# caught MultipleTranslationsError
# caught MultipleTitleTranslationsError

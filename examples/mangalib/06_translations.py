"""Translations of a manga chapter, choosing one, and closed (paid / early-access) chapters.

A chapter can be translated by several teams; each translation is a *branch*, identified by
`branch_id`. When there's more than one, get_chapter() won't pick for you: the API's own
choice when no branch_id is sent isn't predictable, so the SDK raises
`MultipleTranslationsError` instead, listing the options (`.branches`).

mangalib.me adds closed translations on top of that: paid chapters, and chapters in early
access that open for everyone on a date. The SDK has no login, so it can't read them. A
branch says up front whether it's open (`ChapterBranch.is_open`, from `restricted_view`);
fetching a closed one raises `AuthRequiredError`.
"""

import asyncio
import tempfile

from mangalib import (
    AuthRequiredError,
    ChapterBranch,
    MangaLib,
    MultipleTranslationsError,
    RestrictedView,
    cache_stats,
)


def describe(branch: ChapterBranch) -> str:
    teams = ", ".join(team.name for team in branch.teams) or "no team"
    uploader = branch.user.username if branch.user else "?"
    return f"{branch.branch_id} {teams} (uploaded by {uploader}, {branch.created_at:%Y-%m-%d})"


async def main() -> None:
    # A temporary cache directory, to show below what does and doesn't get cached.
    with tempfile.TemporaryDirectory() as cache_dir:
        async with MangaLib(
            "https://mangalib.me/ru/manga/261420--husband-thief", cache_dir=cache_dir
        ) as lib:
            # Chapter 1 has two translations. get_translations() lists them as
            # mangalib.ChapterBranch: branch_id, teams, the uploading user, created_at, and
            # restricted_view (None here: both are open).
            branches = await lib.get_translations(volume=1, number="1")
            for branch in branches:
                print(describe(branch), "open" if branch.is_open else "closed")

            # Without a branch_id the SDK refuses to guess.
            try:
                await lib.get_chapter(volume=1, number="1")
            except MultipleTranslationsError as exc:
                print("pick one of:", [branch.branch_id for branch in exc.branches])

            # Pick one. branch_id is stable across a title's chapters for one "line" of
            # translation, so the same id can be used for the next chapters as well.
            chapter = await lib.get_chapter(volume=1, number="1", branch_id=branches[0].branch_id)
            print([team.name for team in chapter.teams], len(chapter.pages), "pages")

            # Chapter 6 has a single translation, in early access. restricted_view says so,
            # and until when (expired_at; None for a chapter that stays paid). The chapter
            # list doesn't send the price, so it is None here.
            (closed,) = await lib.get_translations(volume=1, number="6")
            view: RestrictedView | None = closed.restricted_view
            print(describe(closed), "open" if closed.is_open else "closed")
            if view is not None:
                print("opens for everyone at", view.expired_at, "price", view.price)

            # Fetching it fails. The API itself answers 200 with no pages for a closed
            # chapter; the SDK turns that into AuthRequiredError, *before* the answer reaches
            # the disk cache — a cached refusal would outlive the chapter opening up on
            # expired_at. So a retry after that date goes to the API again and succeeds.
            entries = cache_stats(cache_dir).entries
            try:
                await lib.get_chapter(volume=1, number="6")
            except AuthRequiredError as exc:
                print(type(exc).__name__, exc.url)
            print("new cache entries:", cache_stats(cache_dir).entries - entries)


if __name__ == "__main__":
    asyncio.run(main())

# Expected output (real run against the live site on 2026-10-25; chapter 6 leaves early
# access on 2026-10-31, after which it reads "open" and fetching it succeeds):
#
# 26208 Bam Byeol (uploaded by lee-devils, 2026-08-11) open
# 26207 Lexiopia (uploaded by SeeYourSoul, 2026-05-01) open
# pick one of: [26208, 26207]
# ['Bam Byeol'] 6 pages
# 26208 Bam Byeol (uploaded by lee-devils, 2026-10-24) closed
# opens for everyone at 2026-10-31 18:05:00+00:00 price None
# AuthRequiredError https://api.cdnlibs.org/api/manga/261420--husband-thief/chapter?number=6&volume=1
# new cache entries: 0

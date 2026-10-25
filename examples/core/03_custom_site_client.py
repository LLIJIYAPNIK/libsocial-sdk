"""A client for a site that has no package of its own: slashlib.me, built on TitleClient.

ranobelib and mangalib are both a TitleClient subclass plus their own models; any other
lib.social site works the same way. slashlib.me (site 2) is a manga site, so its chapters
are lists of pages like mangalib's. What a site package sets:

- class attributes `site`, `title_model`, `chapter_model`, `volume_model` (and optionally
  `default_cache_dir`, `info_fields`). Set as attributes, not constructor arguments, so the
  constructor stays `SlashLib(url, ...)` and a type checker knows what get_info(),
  get_chapter() and get_volume() return.
- its own models on top of libsocial.models: `Chapter` has no content (the core doesn't know
  what a chapter contains), so the site's Chapter adds it, optional, because the same model
  also holds table-of-contents entries. Its Volume is `Volume[ItsChapter]`, or every
  chapter in it would be validated (and dumped) as the core's bare Chapter.
- optionally `_create_client()`, to use its own ApiClient subclass (here: so
  AccessBlockedError names SlashLib in its advice), and `_plan_chapters()`, which decides
  the chapters and translations of a whole-title operation. mangalib uses it to leave out
  closed chapters; here it prefers a translation team by name.
"""

import asyncio
import tempfile
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any, ClassVar

from pydantic import BaseModel, Field

from libsocial import (
    AmbiguousChapter,
    ApiClient,
    ChapterBranch,
    MultipleTitleTranslationsError,
    MultipleTranslationsError,
    PlannedChapter,
    Site,
    TitleClient,
    Verbosity,
)
from libsocial.models import Chapter, Team, Title, Volume

SLASHLIB = Site(id=2, origin="https://slashlib.me")


class Page(BaseModel):
    """One page image. `url` is relative; the image hosts are listed by /constants."""

    id: int
    url: str
    width: int | None = None
    height: int | None = None


class SlashChapter(Chapter):
    # Only a fetched chapter has these; table-of-contents entries leave them at None / [].
    pages: list[Page] | None = None
    teams: list[Team] = Field(default_factory=list)


class SlashVolume(Volume[SlashChapter]):
    pass


class SlashApiClient(ApiClient):
    headers_hint = "SlashLib(..., headers=...)"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(SLASHLIB, **kwargs)


class SlashLib(TitleClient[Title, SlashChapter, SlashVolume]):
    site = SLASHLIB
    title_model = Title
    chapter_model = SlashChapter
    volume_model = SlashVolume
    default_cache_dir = Path(".slashlib_cache")
    # get_info()'s extra fields[]: the core's list minus the ones this site leaves empty.
    info_fields: ClassVar[tuple[str, ...]] = tuple(
        field for field in TitleClient.info_fields if field not in ("background", "artists")
    )

    def __init__(
        self,
        url: str,
        *,
        preferred_team: str | None = None,
        cache_dir: str | Path | None = None,
        verbosity: Verbosity = False,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(url, cache_dir=cache_dir, verbosity=verbosity, headers=headers)
        self.preferred_team = preferred_team

    def _create_client(self, headers: Mapping[str, str] | None) -> ApiClient:
        return SlashApiClient(headers=headers)

    def _plan_chapters(
        self,
        raw_chapters: list[dict[str, Any]],
        *,
        branch_id: int | None,
        translation_index: int | None,
    ) -> tuple[list[PlannedChapter], list[dict[str, Any]]]:
        # A chapter with several translations, one of them by preferred_team, gets that one;
        # everything else goes to the core's plan (branch_id / translation_index / error).
        pinned: dict[tuple[str, str], int | None] = {}
        for item in raw_chapters:
            branches = item.get("branches") or []
            for branch in branches if len(branches) > 1 else []:
                if any(team["name"] == self.preferred_team for team in branch["teams"]):
                    pinned[item["volume"], item["number"]] = branch["branch_id"]
                    break
        rest = [item for item in raw_chapters if (item["volume"], item["number"]) not in pinned]
        planned, unresolved = super()._plan_chapters(
            rest, branch_id=branch_id, translation_index=translation_index
        )
        # Back in the API's order, which download_title() keeps.
        by_key = {(chapter.volume, chapter.number): chapter for chapter in planned}
        for key, pinned_branch in pinned.items():
            by_key[key] = PlannedChapter(*key, pinned_branch)
        ordered = [
            by_key[key]
            for item in raw_chapters
            if (key := (item["volume"], item["number"])) in by_key
        ]
        return ordered, unresolved


def ambiguous(chapters: list[AmbiguousChapter]) -> list[str]:
    return [chapter.number for chapter in chapters]


async def main() -> None:
    # Chapters 1-11 have two translations. Branch 14369 is VISS's in chapters 1-9 but
    # "жесть."'s in 10-11, so neither a branch_id nor a position says "VISS where they did it".
    url = "https://slashlib.me/ru/manga/96466--old-clothes-collection-bin-of-love"
    with tempfile.TemporaryDirectory() as cache_dir:
        async with SlashLib(url, cache_dir=cache_dir) as lib:
            info = await lib.get_info()
            print(info.name, "|", info.rus_name, "|", info.country.name if info.country else "?")
            print(
                "genres:",
                [genre.name for genre in info.genres],
                "teams:",
                [team.name for team in info.teams],
            )

            volumes = await lib.get_table_of_contents()
            print(type(volumes[0]).__name__, [(v.number, len(v.chapters)) for v in volumes])

            branches: list[ChapterBranch] = await lib.get_translations(volume=1, number="10")
            print("chapter 10:", [(b.branch_id, [t.name for t in b.teams]) for b in branches])
            try:
                await lib.get_chapter(volume=1, number="10")
            except MultipleTranslationsError as exc:
                print(type(exc).__name__, "- options:", [b.branch_id for b in exc.branches])
            chapter = await lib.get_chapter(volume=1, number="12")
            pages = chapter.pages or []
            print(
                f"chapter 12: {type(chapter).__name__}, {len(pages)} pages,",
                f"by {[t.name for t in chapter.teams]}",
            )
            print("  first page:", pages[0].url, pages[0].width, "x", pages[0].height)

            # The whole title. The ambiguity check runs before any chapter is fetched, and
            # lists every ambiguous chapter at once.
            try:
                await lib.download_title()
            except MultipleTitleTranslationsError as exc:
                print("no preference:", type(exc).__name__, ambiguous(exc.chapters))

        async with SlashLib(url, cache_dir=cache_dir, preferred_team="VISS") as lib:
            try:
                await lib.download_title()
            except MultipleTitleTranslationsError as exc:
                print("VISS preferred:", type(exc).__name__, ambiguous(exc.chapters))

            # translation_index covers what the preference doesn't: 10-11 take the first.
            volumes = await lib.download_title(translation_index=0)
            chapters = [chapter for volume in volumes for chapter in volume.chapters]
            by_team = Counter(team.name for chapter in chapters for team in chapter.teams)
            print(
                f"VISS preferred + translation_index=0: {len(chapters)} chapters,",
                f"by team {dict(by_team)}",
            )


if __name__ == "__main__":
    asyncio.run(main())

# Expected output (real run against slashlib.me on 2026-10-25; the title is completed, but new
# translations can still be added to it):
#
# Old Clothes Collection Bin of Love | Контейнер для чувств | Манхва
# genres: ['Комедия', 'Романтика', 'Сёдзё', 'Школа'] teams: ['VISS', 'SleepMode', 'Sour Sweet
#   Cherry']
# SlashVolume [('1', 41)]
# chapter 10: [(14368, ['SleepMode']), (14369, ['жесть.'])]
# MultipleTranslationsError - options: [14368, 14369]
# chapter 12: SlashChapter, 4 pages, by ['SleepMode']
#   first page: //manga/old-clothes-collection-bin-of-love/chapters/2470946/01_DW2t.png 900 x 30974
# no preference: MultipleTitleTranslationsError ['1', '2', '3', '4', '5', '6', '7', '8', '9', '10',
#   '11']
# VISS preferred: MultipleTitleTranslationsError ['10', '11']
# VISS preferred + translation_index=0: 41 chapters, by team {'VISS': 9, 'SleepMode': 32}

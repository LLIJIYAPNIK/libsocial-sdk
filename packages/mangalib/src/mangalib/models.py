"""Pydantic models: Title, Chapter, Page, Volume, and related types.

Everything that isn't specific to mangalib.me is ``libsocial-core``'s and re-exported here
unchanged (``Cover``, ``Label``, ``Genre``, ``Tag``, ``Country``, ``Person``, ``Team``,
``ChapterUser``). ``Title``, ``ChapterBranch``, ``Chapter``, ``Volume`` and ``CatalogPage``
subclass the core's with what is: a chapter's ``pages`` instead of text, whether a
translation is closed to readers without an account (``restricted_view``), and
``Title.base_names`` without mangalib's format suffixes.
"""

from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from libsocial import models as _core
from libsocial.models import ChapterUser, Country, Cover, Genre, Label, Person, Tag, Team

__all__ = [
    "CatalogPage",
    "Chapter",
    "ChapterBranch",
    "ChapterUser",
    "Country",
    "Cover",
    "Genre",
    "ImageServer",
    "Label",
    "Page",
    "Person",
    "RestrictedView",
    "Tag",
    "Team",
    "Title",
    "Volume",
]

_FORMAT_WORD = (
    r"manga|манга|manhwa|манхва|manhua|маньхуа|webtoon|вебтун"
    r"|web\s*-?\s*comics?|веб\s*-?\s*комикс|comics?|comic\s+book|комикс"
)
_FORMAT_SUFFIX = re.compile(
    rf"[\s,:/]*(?:\(\s*(?:{_FORMAT_WORD})\s*\)|\[\s*(?:{_FORMAT_WORD})\s*\])\s*$",
    re.IGNORECASE,
)
"""A bare format marker at the end of a title name — ``(Manhwa)``, ``(webtoon)``,
``[Вебтун]``, ``(Манга)``, ``(Комикс)``, ... — plus the separator (``,``/``:``/``/``) sometimes
left before it. The word list comes from every name in the live catalog (see
docs/api-notes.md, "Title names without a format marker"). Tails that say more than the
format — ``(манга-версия)``, ``(Color Webtoon)``, ``(Fan Comics)``, ``(Graphic Novel)`` — tell
versions of a work apart, so they're kept."""


def _strip_format_suffix(name: str) -> str:
    """``name`` without its trailing format marker(s) — the same rule as ranobelib's."""
    while (match := _FORMAT_SUFFIX.search(name)) is not None:
        name = name[: match.start()]
    return name.strip()


class Title(_core.Title):
    """Metadata for a single title (manga, manhwa, manhua, comic, ...)."""

    @property
    def base_names(self) -> list[str]:
        """The title's names without a trailing format marker.

        ``rus_name``, ``eng_name``, ``name`` and ``other_names``, in that order, each with a
        bare format marker at the end removed — ``"Return of the Runebound Professor
        (webtoon)"`` → ``"Return of the Runebound Professor"``, likewise ``(Manhwa)``,
        ``(Манга)``, ``[Вебтун]``, ``(Комикс)``, ... Unlike ranobelib.me's ``(Новелла)``,
        mangalib.me doesn't append one itself: only a few dozen names have one, typed by
        hand. Other bracketed tails — ``(Doujinshi)``, ``(Colored)``, ``(перезапуск)``, a
        year, ``(манга-версия)`` — tell titles apart and are kept. Whitespace is trimmed;
        empty names and duplicates (keeping the first) are dropped. Nothing else is
        normalized (case, punctuation): that's up to whatever compares the names.

        The original fields are left as they are. On ``Catalog.list_titles()`` items
        ``other_names`` is empty (the listing doesn't return it), so it contributes nothing.
        """
        names = [self.rus_name, self.eng_name, self.name, *self.other_names]
        stripped = (_strip_format_suffix(name) for name in names if name)
        return list(dict.fromkeys(name for name in stripped if name))


class RestrictedView(BaseModel):
    """Access to a paid or early-access chapter translation.

    Present only on translations that are (or were) restricted. Logging in isn't supported
    by the SDK, so a closed one can't be read through it — see ``ChapterBranch.is_open``.
    """

    is_open: bool
    """Whether anyone can read it now, without an account."""
    expired_at: datetime | None = None
    """When early access ends and the chapter opens for everyone; ``None`` for a chapter
    that stays paid."""
    price: int | None = None
    """The price the site asks, in its own currency. The chapter list leaves it ``None``;
    fetching the chapter fills it in."""


class ChapterBranch(_core.ChapterBranch):
    """A single team's (or solo uploader's) translation of a chapter.

    A chapter has more than one branch when several teams have translated it
    independently; see ``Chapter.branches_count``.
    """

    restricted_view: RestrictedView | None = None
    """Set when this translation is paid or in early access — see ``is_open``."""

    @property
    def is_open(self) -> bool:
        """Whether this translation can be read without an account.

        ``False`` means ``MangaLib.get_chapter()`` raises ``AuthRequiredError`` for it.
        """
        return self.restricted_view is None or self.restricted_view.is_open


class Page(BaseModel):
    """One page image of a chapter.

    ``url`` is relative to an image server (see ``ImageServer`` and ``mangalib.page_url()``):
    the API doesn't say which server a page is on, every server serves every page.
    """

    model_config = ConfigDict(populate_by_name=True)

    id: int
    number: int = Field(alias="slug")
    """1-based position in the chapter — the API's ``slug``."""
    image: str
    """The image's file name. Its extension isn't reliable as a format: the ``compress``
    server sends a JPEG for a ``.png`` name (see docs/api-notes.md)."""
    url: str
    """Path of the image on an image server, e.g. ``"//manga/{slug}/chapters/1-1/00.jpg"``."""
    width: int | None = None
    height: int | None = None


class Chapter(_core.Chapter):
    """A chapter: volume, number, name, available translations, and optionally its pages.

    ``index``/``item_number``/``branches_count``/``branches`` come from the chapter-list
    endpoint (see ``MangaLib.get_table_of_contents()``) and are ``None``/empty when a
    ``Chapter`` instead comes from fetching a single chapter, which has a different response
    shape. ``pages`` is the reverse: only filled in by fetching the chapter
    (``MangaLib.get_chapter()`` and friends), in reading order.
    """

    # list[ChapterBranch] here vs list[core ChapterBranch] in the base class: lists are
    # invariant, so mypy flags the narrower item type, which pydantic itself is fine with.
    branches: list[ChapterBranch] = Field(default_factory=list)  # type: ignore[assignment]
    pages: list[Page] = Field(default_factory=list)
    teams: list[Team] = Field(default_factory=list)
    """The teams credited for the fetched translation (empty on the chapter list's entries,
    where each of ``branches`` has its own)."""
    restricted_view: RestrictedView | None = None
    """Set on a fetched chapter whose translation is (or was) paid or in early access."""


class ImageServer(BaseModel):
    """A server page images are downloaded from (``GET /constants?fields[]=imageServers``).

    A page's full URL is the server's ``url`` followed by ``Page.url``.
    """

    id: str
    """The API's name for it: ``"main"``, ``"secondary"``, ``"compress"``, ``"download"``,
    ``"crop"`` (see docs/api-notes.md for which of them actually serve pages)."""
    label: str
    url: str


class Volume(_core.Volume[Chapter]):
    """A volume: its number and the chapters it contains, in title order."""


class CatalogPage(_core.CatalogPage[Title]):
    """One page of catalog listing/search results, as returned by ``Catalog.list_titles()``.

    ``items`` reuses ``Title`` as-is: the fields a listing doesn't send (``genres``,
    ``summary``, ``chapter_count``, ``last_chapter_at``, ...) come back at their defaults.
    """

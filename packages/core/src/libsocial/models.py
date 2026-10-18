"""Pydantic models shared by every lib.social site: Title, Chapter, Volume, and related types.

What a chapter *contains* differs per site (ranobelib.me: text; mangalib.me: page images),
so ``Chapter`` here carries only what the chapter list and the chapter endpoint have in
common, and a site package subclasses it with its content fields. ``Volume`` and
``CatalogPage`` are generic over the chapter/title model for the same reason: a site
package's ``Volume[ItsChapter]`` validates and serializes its own chapter fields, which a
``Volume`` typed with the base ``Chapter`` would drop on ``model_dump()``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _prosemirror_to_text(doc: dict[str, Any]) -> str:
    """Flatten a prosemirror-doc JSON structure into plain text paragraphs.

    A minimal parser (text leaves only, joined paragraph by paragraph), sufficient for a
    title's summary. Chapter content needs a richer, site-specific renderer.
    """

    def extract(node: dict[str, Any]) -> str:
        if node.get("type") == "text":
            return str(node.get("text", ""))
        return "".join(extract(child) for child in node.get("content", []))

    paragraphs = [extract(block) for block in doc.get("content", [])]
    return "\n\n".join(paragraph for paragraph in paragraphs if paragraph)


class Cover(BaseModel):
    """A set of cover image URLs at different sizes."""

    filename: str | None = None
    thumbnail: str | None = None
    default: str | None = None
    md: str | None = None


class Label(BaseModel):
    """A small ``{id, label}`` enum value used throughout the API (status, age rating, ...)."""

    id: int
    label: str


class Genre(BaseModel):
    """A genre tag (e.g. Fantasy, Romance)."""

    id: int
    name: str
    adult: bool = False


class Tag(BaseModel):
    """A free-form content tag."""

    id: int
    name: str
    adult: bool = False


class Country(BaseModel):
    """A title's country/region of origin.

    Maps onto what the raw API itself calls "type" (``Title``'s raw ``type`` field; the
    catalog filter's ``types[]`` parameter; ``GET /api/constants?fields[]=types``) — not a
    ``country``/``countries[]``/``fields[]=countries`` concept, which turned out to be
    something unrelated (see docs/api-notes.md). The values aren't all literal countries: on
    ranobelib.me, Japan, Korea and China sit next to original English-language work, original
    web novel and fanfiction, all surfaced as-is.
    """

    model_config = ConfigDict(populate_by_name=True)

    id: int
    name: str = Field(alias="label")


class Person(BaseModel):
    """An author or artist credited on a title."""

    id: int
    slug: str
    slug_url: str
    name: str
    rus_name: str | None = None


class Team(BaseModel):
    """A translation team."""

    id: int
    slug: str
    slug_url: str
    name: str


class Title(BaseModel):
    """Metadata for a single title."""

    model_config = ConfigDict(populate_by_name=True)

    id: int
    name: str
    rus_name: str | None = None
    eng_name: str | None = None
    other_names: list[str] = Field(default_factory=list, alias="otherNames")
    slug: str
    slug_url: str
    cover: Cover
    age_restriction: Label = Field(alias="ageRestriction")
    status: Label
    summary: str | None = None
    release_date: str | None = Field(default=None, alias="releaseDate")
    is_licensed: bool = False
    country: Country | None = Field(default=None, alias="type")
    genres: list[Genre] = Field(default_factory=list)
    tags: list[Tag] = Field(default_factory=list)
    authors: list[Person] = Field(default_factory=list)
    artists: list[Person] = Field(default_factory=list)
    teams: list[Team] = Field(default_factory=list)
    chapter_count: int | None = None
    """Number of uploaded chapters. Only ``TitleClient.get_info()`` fills it in: the catalog
    listing endpoint doesn't return it (see docs/api-notes.md), so it's ``None`` on
    ``Catalog.list_titles()`` items."""
    last_chapter_at: datetime | None = Field(default=None, alias="last_item_at")
    """When the most recent chapter was published — the value the catalog's
    ``sort="last_chapter_at"`` orders by. Only ``TitleClient.get_info()`` fills it in: the
    catalog listing endpoint doesn't return it (see docs/api-notes.md), so it's ``None`` on
    ``Catalog.list_titles()`` items, and on a title with no chapters yet."""

    @model_validator(mode="before")
    @classmethod
    def _flatten_chapter_count(cls, data: Any) -> Any:
        if isinstance(data, dict) and "chapter_count" not in data:
            items_count = data.get("items_count")
            if isinstance(items_count, dict):
                data = {**data, "chapter_count": items_count.get("uploaded")}
        return data

    @field_validator("summary", mode="before")
    @classmethod
    def _parse_summary(cls, value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, dict):
            return _prosemirror_to_text(value)
        return str(value)


class ChapterUser(BaseModel):
    """The uploader of a chapter branch."""

    id: int
    username: str


class ChapterBranch(BaseModel):
    """A single team's (or solo uploader's) translation of a chapter.

    A chapter has more than one branch when several teams have translated it
    independently; see ``Chapter.branches_count``.
    """

    id: int
    branch_id: int | None = None
    created_at: datetime
    teams: list[Team] = Field(default_factory=list)
    user: ChapterUser


class Chapter(BaseModel):
    """A chapter: volume, number, name and available translations — not its content.

    ``index``/``item_number``/``branches_count``/``branches`` come from the chapter-list
    endpoint (see ``TitleClient.get_table_of_contents()``) and are ``None``/empty when a
    ``Chapter`` instead comes from fetching a single chapter, which has a different response
    shape (see docs/api-notes.md). What the chapter contains is site-specific: a site
    package subclasses this with its content fields and parsing.
    """

    id: int
    volume: str
    number: str
    name: str | None = None
    index: int | None = None
    item_number: int | None = None
    branches_count: int = 1
    branches: list[ChapterBranch] = Field(default_factory=list)
    bundle_id: int | None = None


ChapterT = TypeVar("ChapterT", bound=Chapter)
TitleT = TypeVar("TitleT", bound=Title)


class Volume(BaseModel, Generic[ChapterT]):
    """A volume: its number and the chapters it contains, in title order.

    Generic over the chapter model — a site package uses ``Volume[ItsChapter]`` (or a
    subclass of it) so its chapters keep their content fields.
    """

    number: str
    chapters: list[ChapterT] = Field(default_factory=list)


class CatalogPage(BaseModel, Generic[TitleT]):
    """One page of catalog listing/search results, as returned by ``Catalog.list_titles()``.

    ``items`` reuses the title model as-is — a catalog list item has every field ``Title``
    requires, the ones it doesn't send (``genres``, ``summary``, ``chapter_count``,
    ``last_chapter_at``, ...) just come back at their defaults, same as any other
    partially-populated ``Title`` (see docs/api-notes.md).
    """

    items: list[TitleT]
    page: int
    has_next_page: bool

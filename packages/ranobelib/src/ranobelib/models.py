"""Pydantic models: Title, Chapter, Volume, Team, Branch, and related types."""

from __future__ import annotations

import html
import re
from datetime import datetime
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SITE_BASE_URL = "https://ranobelib.me"
"""Base URL used to resolve relative asset paths (e.g. in-chapter image attachments)."""


def _prosemirror_to_text(doc: dict[str, Any]) -> str:
    """Flatten a prosemirror-doc JSON structure into plain text paragraphs.

    This is a minimal parser (text leaves only, joined paragraph by paragraph) sufficient
    for a title's summary. Chapter content will need a richer version that preserves
    formatting (bold/italic/headings/lists) once that feature is implemented.
    """

    def extract(node: dict[str, Any]) -> str:
        if node.get("type") == "text":
            return str(node.get("text", ""))
        return "".join(extract(child) for child in node.get("content", []))

    paragraphs = [extract(block) for block in doc.get("content", [])]
    return "\n\n".join(paragraph for paragraph in paragraphs if paragraph)


def _child_nodes(node: dict[str, Any]) -> list[dict[str, Any]]:
    content: list[dict[str, Any]] = node.get("content") or []
    return content


def _resolve_attachment_url(image_id: str, attachments: list[dict[str, Any]]) -> str | None:
    for attachment in attachments:
        if attachment.get("name") == image_id:
            url = attachment.get("url")
            return f"{SITE_BASE_URL}{url}" if url else None
    return None


def _render_prosemirror_marks(text: str, marks: list[dict[str, Any]]) -> str:
    for mark in marks:
        if mark.get("type") == "bold":
            text = f"<strong>{text}</strong>"
        elif mark.get("type") == "italic":
            text = f"<em>{text}</em>"
    return text


def _render_prosemirror_inline(node: dict[str, Any], attachments: list[dict[str, Any]]) -> str:
    node_type = node.get("type")
    if node_type == "text":
        text = html.escape(str(node.get("text", "")))
        return _render_prosemirror_marks(text, node.get("marks") or [])
    if node_type == "hardBreak":
        return "<br />"
    if node_type == "image":
        images = node.get("attrs", {}).get("images") or []
        urls = (_resolve_attachment_url(image.get("image", ""), attachments) for image in images)
        return "".join(f'<img loading="lazy" src="{url}" />' for url in urls if url)
    return "".join(_render_prosemirror_inline(child, attachments) for child in _child_nodes(node))


_FOOTNOTE_ARROW = "↑"
"""The "↑" a translator footnote paragraph starts with — see ``Chapter.footnotes``."""


def _strip_footnote_arrow(paragraph: dict[str, Any]) -> dict[str, Any] | None:
    """Return ``paragraph`` without its leading ``_FOOTNOTE_ARROW``, or ``None`` if its first
    non-blank text doesn't start with one (i.e. it's a regular paragraph, not a footnote).

    Non-text children (an image, a hard break) before that text are kept and skipped over,
    same as ``_ContentSanitizer`` does for the HTML-string format.
    """
    children = _child_nodes(paragraph)
    for index, child in enumerate(children):
        if child.get("type") != "text":
            continue
        text = str(child.get("text", "")).lstrip()
        if not text:
            continue
        if not text.startswith(_FOOTNOTE_ARROW):
            return None
        stripped = {**child, "text": text[len(_FOOTNOTE_ARROW) :].lstrip()}
        return {**paragraph, "content": [*children[:index], stripped, *children[index + 1 :]]}
    return None


def _render_prosemirror_block(
    node: dict[str, Any], attachments: list[dict[str, Any]], footnotes: list[str]
) -> str:
    node_type = node.get("type")
    if node_type == "paragraph":
        footnote = _strip_footnote_arrow(node)
        paragraph = footnote if footnote is not None else node
        inner = "".join(
            _render_prosemirror_inline(child, attachments) for child in _child_nodes(paragraph)
        )
        if footnote is None:
            return f"<p>{inner}</p>"
        if inner.strip():
            footnotes.append(inner.strip())
        return ""
    if node_type == "image":
        return _render_prosemirror_inline(node, attachments)
    if node_type == "horizontalRule":
        return "<hr />"
    return "".join(
        _render_prosemirror_block(child, attachments, footnotes) for child in _child_nodes(node)
    )


def _prosemirror_to_html(
    doc: dict[str, Any], attachments: list[dict[str, Any]]
) -> tuple[str, list[str]]:
    """Render a prosemirror-doc JSON structure as an HTML fragment, plus its footnotes.

    Chapter content comes from the API in one of two formats — an HTML string, or
    prosemirror-doc JSON (see docs/api-notes.md) — this makes the latter match the tag
    vocabulary (``p``/``img``/``strong``/``em``) the former already uses natively, so
    downstream consumers (exporters) only ever handle one shape. Image nodes reference
    attachments by an opaque id, resolved against the chapter response's ``attachments``
    array. Footnote paragraphs (see ``Chapter.footnotes``) are left out of the returned HTML
    and returned separately instead, as inline HTML fragments without the leading arrow.
    """
    footnotes: list[str] = []
    rendered = "".join(
        _render_prosemirror_block(block, attachments, footnotes) for block in _child_nodes(doc)
    )
    return rendered, footnotes


_ALLOWED_CONTENT_TAGS = frozenset({"p", "img", "strong", "em", "br", "hr"})
_CONTENT_TAG_ALIASES = {"b": "strong", "i": "em"}
_VOID_CONTENT_TAGS = frozenset({"br", "hr", "img"})
_DROPPED_CONTENT_TEXT_TAGS = frozenset({"script", "style"})
_SAFE_IMG_SCHEMES = frozenset({"http", "https"})


_DROPPED_BLOCK_TAGS = frozenset(
    {
        "address",
        "article",
        "aside",
        "blockquote",
        "caption",
        "center",
        "dd",
        "details",
        "div",
        "dl",
        "dt",
        "fieldset",
        "figcaption",
        "figure",
        "footer",
        "form",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "hgroup",
        "li",
        "main",
        "nav",
        "ol",
        "pre",
        "section",
        "summary",
        "table",
        "tbody",
        "td",
        "tfoot",
        "th",
        "thead",
        "tr",
        "ul",
    }
)
_BLOCK_TAGS = _DROPPED_BLOCK_TAGS | {"p"}


class _Block:
    """A ``p`` or dropped block-level tag still being parsed.

    ``run`` is the inline content collected since the block opened or since its last child
    block — for a ``p`` that's its whole content; for a dropped block it's flushed into its
    own ``<p>`` in ``segments`` whenever a child block (or ``hr``) starts, and when the block
    closes. Each such paragraph is checked for a footnote on its own, so buffering is needed:
    whether it is one is only known once its first non-blank text arrives.
    """

    def __init__(self, tag: str) -> None:
        self.tag = tag
        self.segments: list[str] = []
        self.run: list[str] = []
        self.arrow_index: int | None = None
        self.seen_text = False


class _ContentSanitizer(HTMLParser):
    """Rebuilds an HTML-string-format chapter body using only the same restricted tag
    vocabulary ``_prosemirror_to_html`` already produces for the other content format
    (``p``/``img``/``strong``/``em``/``br``/``hr``) — see ``_normalize_content``.

    The HTML-string format passes the site's own markup straight from its editor (see
    docs/api-notes.md), so unlike the prosemirror path it isn't SDK-generated and can't be
    trusted as-is: any tag/attribute outside that vocabulary is dropped rather than kept,
    including all attributes on the tags that are kept (``img`` is the one exception, and
    only its ``src`` survives, and only when it resolves to an http(s) URL). ``b``/``i`` are
    folded into ``strong``/``em`` (observed as interchangeable in samples, see
    docs/api-notes.md) rather than dropped, since they're semantically equivalent and not a
    safety concern. Text inside a dropped ``script``/``style`` tag is discarded rather than
    kept as escaped text — anywhere else, a dropped tag's text content is kept (e.g. a
    stripped ``<a href="...">text</a>`` still leaves ``text`` behind).

    A dropped *block-level* tag (``li``, ``div``, ``h3``, ...) keeps the paragraph boundary
    it gave its text: its inline content is wrapped in ``<p>`` rather than inlined into the
    parent, one ``<p>`` per run of inline content between nested blocks, so the output stays
    a flat sequence of paragraphs whatever the nesting was. Opening a block inside an open
    ``p`` closes that ``p`` first, as HTML itself does (a ``p`` can't contain blocks).

    A paragraph — an explicit ``p`` or one made from a dropped block's text — whose first
    non-blank text starts with ``_FOOTNOTE_ARROW`` is a translator footnote: it's collected
    into ``footnotes`` (sanitized inner HTML, arrow stripped) instead of the output.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._output: list[str] = []
        self._blocks: list[_Block] = []
        self._skip_text_depth = 0
        self.footnotes: list[str] = []

    def _out(self) -> list[str]:
        return self._blocks[-1].run if self._blocks else self._output

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _BLOCK_TAGS:
            self._open_block(tag)
        else:
            self._emit(tag, attrs)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _BLOCK_TAGS:
            self._open_block(tag)
            self._close_block()
        else:
            self._emit(tag, attrs)

    def _open_block(self, tag: str) -> None:
        # Same implicit closes HTML itself does: any block ends an open <p>, and a new <li>
        # ends an open <li>.
        if self._blocks and (self._blocks[-1].tag == "p" or self._blocks[-1].tag == tag == "li"):
            self._close_block()
        self._blocks.append(_Block(tag))

    def _close_block(self) -> None:
        block = self._blocks.pop()
        if block.tag == "p":
            paragraph = self._take_paragraph(block, keep_empty=True)
        else:
            self._flush_run(block)
            paragraph = "".join(block.segments)
        if paragraph:
            self._append_block_html(paragraph)

    def _take_paragraph(self, block: _Block, *, keep_empty: bool) -> str:
        """Turn ``block.run`` into a ``<p>`` (or a footnote, returning ``""``) and reset it."""
        run, arrow_index = block.run, block.arrow_index
        block.run, block.arrow_index, block.seen_text = [], None, False
        if arrow_index is not None:
            run[arrow_index] = run[arrow_index].lstrip()[len(_FOOTNOTE_ARROW) :].lstrip()
            inner = "".join(run).strip()
            if inner:
                self.footnotes.append(inner)
            return ""
        inner = "".join(run)
        if keep_empty:
            return f"<p>{inner}</p>"
        return f"<p>{inner.strip()}</p>" if inner.strip() else ""

    def _flush_run(self, block: _Block) -> None:
        paragraph = self._take_paragraph(block, keep_empty=False)
        if paragraph:
            block.segments.append(paragraph)

    def _append_block_html(self, block_html: str) -> None:
        if not self._blocks:
            self._output.append(block_html)
            return
        parent = self._blocks[-1]
        self._flush_run(parent)
        parent.segments.append(block_html)

    def _emit(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        resolved = _CONTENT_TAG_ALIASES.get(tag, tag)
        if resolved not in _ALLOWED_CONTENT_TAGS:
            if tag in _DROPPED_CONTENT_TEXT_TAGS:
                self._skip_text_depth += 1
            return
        if resolved == "img":
            src = dict(attrs).get("src")
            if src and urlsplit(src).scheme in _SAFE_IMG_SCHEMES:
                self._out().append(f'<img loading="lazy" src="{html.escape(src, quote=True)}" />')
            return
        if resolved == "hr" and self._blocks and self._blocks[-1].tag != "p":
            # Between a dropped block's paragraphs, not inside one.
            self._append_block_html("<hr />")
            return
        if resolved in _VOID_CONTENT_TAGS:
            self._out().append(f"<{resolved} />")
        else:
            self._out().append(f"<{resolved}>")

    def handle_endtag(self, tag: str) -> None:
        if tag in _BLOCK_TAGS:
            # Close up to the matching open block; a stray end tag with none open is dropped.
            if any(block.tag == tag for block in self._blocks):
                while self._blocks[-1].tag != tag:
                    self._close_block()
                self._close_block()
            return
        resolved = _CONTENT_TAG_ALIASES.get(tag, tag)
        if resolved not in _ALLOWED_CONTENT_TAGS:
            if tag in _DROPPED_CONTENT_TEXT_TAGS and self._skip_text_depth > 0:
                self._skip_text_depth -= 1
            return
        if resolved not in _VOID_CONTENT_TAGS:
            self._out().append(f"</{resolved}>")

    def handle_data(self, data: str) -> None:
        if self._skip_text_depth > 0:
            return
        if self._blocks and not self._blocks[-1].seen_text and data.strip():
            block = self._blocks[-1]
            block.seen_text = True
            if data.lstrip().startswith(_FOOTNOTE_ARROW):
                block.arrow_index = len(block.run)
        self._out().append(html.escape(data))

    def get_html(self) -> str:
        while self._blocks:
            self._close_block()
        return "".join(self._output)


def _sanitize_content_html(content: str) -> tuple[str, list[str]]:
    """Sanitize an HTML-string-format chapter body down to the restricted tag vocabulary.

    Counterpart to ``_prosemirror_to_html`` for the other content format the API returns
    (see docs/api-notes.md) — without this, ``Chapter.content`` would only actually be safe
    to render as raw HTML for prosemirror-sourced chapters, not HTML-string-sourced ones.
    Returns the sanitized HTML and, separately, the footnotes taken out of it (see
    ``Chapter.footnotes``).
    """
    sanitizer = _ContentSanitizer()
    sanitizer.feed(content)
    return sanitizer.get_html(), sanitizer.footnotes


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

    Despite the name (matching issue #48's requested public shape), this maps onto what the
    raw API itself calls "type" (`Title`'s raw `type` field; the catalog filter's `types[]`
    parameter; `GET /api/constants?fields[]=types`) — not a `country`/`countries[]`/
    `fields[]=countries` concept, which turned out to be something unrelated (see
    docs/api-notes.md). For ranobelib.me specifically, the values are three literal
    countries (Japan, Korea, China) plus three additional non-national origin categories the
    site groups the same way: original English-language work, original (non-translated) web
    novel, and fanfiction — surfaced as-is, not filtered down to "real" countries only.
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


_FORMAT_WORD = (
    r"(?:(?:light|lite|web|лайт|веб|вэб)\s*-?\s*)?(?:novel(?:la|l|a)?|новелл?а)"
    r"|web\s*-?\s*serial|ranobe|ранобэ|ln|wn|лн|quest|квест"
)
_FORMAT_SUFFIX = re.compile(
    rf"[\s,:/]*(?:\(\s*(?:{_FORMAT_WORD})\s*\)|\[\s*(?:{_FORMAT_WORD})\s*\])\s*$",
    re.IGNORECASE,
)
"""A publication-format marker at the end of a title name — ``(Новелла)``, ``(Novel)``,
``(LN)``, ``[квест]``, ... — plus the separator (``,``/``:``/``/``) sometimes left before it.
The word list comes from every name in the live catalog (see docs/api-notes.md, "Title
names without the format suffix"); other bracketed tails (a year, ``(18+)``, ``(Фанфик)``,
``[LitRPG]``, a franchise) tell titles apart, so they're not on it."""


def _strip_format_suffix(name: str) -> str:
    """``name`` without its trailing format marker(s) — they can stack: ``(LN) (Novel)``."""
    while (match := _FORMAT_SUFFIX.search(name)) is not None:
        name = name[: match.start()]
    return name.strip()


class Title(BaseModel):
    """Metadata for a single title (novel)."""

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
    """Number of uploaded chapters. Only ``RanobeLib.get_info()`` fills it in: the catalog
    listing endpoint doesn't return it (see docs/api-notes.md), so it's ``None`` on
    ``Catalog.list_titles()`` items."""
    last_chapter_at: datetime | None = Field(default=None, alias="last_item_at")
    """When the most recent chapter was published — the value the catalog's
    ``sort="last_chapter_at"`` orders by. Only ``RanobeLib.get_info()`` fills it in: the
    catalog listing endpoint doesn't return it (see docs/api-notes.md), so it's ``None`` on
    ``Catalog.list_titles()`` items, and on a title with no chapters yet."""

    @property
    def base_names(self) -> list[str]:
        """The title's names without the format suffix ranobelib.me appends to them.

        ``rus_name``, ``eng_name``, ``name`` and ``other_names``, in that order, each with
        trailing publication-format markers removed — ``"Старшая школа D×D (Новелла)"`` →
        ``"Старшая школа D×D"``, likewise ``(Novel)``, ``(LN)``, ``(WN)``, ``(Light Novel)``,
        ``(Ранобэ)``, ``[квест]``, ... (stacked ones too, ``(LN) (Novel)``). Other bracketed
        tails — a year, ``(18+)``, ``(Фанфик)``, ``[LitRPG]``, a franchise name — distinguish
        one title from another and are kept. Whitespace is trimmed; empty names and
        duplicates (keeping the first) are dropped. Nothing else is normalized (case,
        punctuation, ``×``): that's up to whatever compares the names.

        The original fields are left as they are. On ``Catalog.list_titles()`` items
        ``other_names`` is empty (the listing doesn't return it), so it contributes nothing.
        """
        names = [self.rus_name, self.eng_name, self.name, *self.other_names]
        stripped = (_strip_format_suffix(name) for name in names if name)
        return list(dict.fromkeys(name for name in stripped if name))

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


class Footnote(BaseModel):
    """A translator footnote (term explanation, translation note) taken out of a chapter.

    The API has no structured footnotes (see docs/api-notes.md): they're ordinary
    paragraphs/list items whose text starts with ``↑``, so that arrow is what the SDK detects
    them by — and strips from ``content``. There's no ``marker`` linking a footnote back to a
    point in the text: translators mark the reference with an unnumbered ``*`` at best, which
    the text also uses for scene breaks and censored words, so ``Chapter.footnotes``'s order
    (the order they appear in the source) is the only link there is.
    """

    content: str
    """Sanitized inline HTML (same tag vocabulary as ``Chapter.content``), without the arrow
    and without a wrapping ``<p>``."""


class Chapter(BaseModel):
    """A chapter: volume, number, name, available translations, and optionally its content.

    ``index``/``item_number``/``branches_count``/``branches`` come from the chapter-list
    endpoint (see ``RanobeLib.get_table_of_contents()``) and are ``None``/empty when a
    ``Chapter`` instead comes from fetching a single chapter's content, which has a
    different response shape (see docs/api-notes.md). ``content`` is the reverse: only
    populated by the single-chapter endpoint.

    ``footnotes`` holds the chapter's translator footnotes (see ``Footnote``), which are
    removed from ``content`` rather than kept in both places — empty when the chapter has
    none, or when ``content`` isn't fetched.
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
    content: str | None = None
    footnotes: list[Footnote] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _normalize_content(cls, data: Any) -> Any:
        if isinstance(data, dict):
            content = data.get("content")
            if isinstance(content, dict):
                attachments = data.get("attachments") or []
                rendered, footnotes = _prosemirror_to_html(content, attachments)
            elif isinstance(content, str):
                rendered, footnotes = _sanitize_content_html(content)
            else:
                return data
            # A Chapter being re-validated from its own dump (model_validate(model_dump()))
            # already has its footnotes out of ``content`` — keep them rather than overwrite
            # them with the now-empty re-extraction.
            data = {
                **data,
                "content": rendered,
                "footnotes": data.get("footnotes")
                or [{"content": footnote} for footnote in footnotes],
            }
        return data


class Volume(BaseModel):
    """A volume: its number and the chapters it contains, in title order."""

    number: str
    chapters: list[Chapter] = Field(default_factory=list)


class CatalogPage(BaseModel):
    """One page of catalog listing/search results, as returned by ``Catalog.list_titles()``.

    ``items`` reuses ``Title`` as-is — a catalog list item has every field ``Title`` requires,
    the ones it doesn't send (``genres``, ``summary``, ``chapter_count``, ``last_chapter_at``,
    ...) just come back at their defaults, same as any other partially-populated ``Title``
    (see docs/api-notes.md).
    """

    items: list[Title]
    page: int
    has_next_page: bool

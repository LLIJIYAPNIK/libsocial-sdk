"""A fetched chapter's top-level blocks as plain text, indexed like the DOM.

``Chapter.content`` is a flat, sanitized sequence of block-level elements (``<p>``,
``<hr />``, ``<img>`` — see ``Chapter``), so a client rendering it as HTML sees one child
element per block. ``chapter_paragraphs()`` gives each of those blocks' text at the same
index, so e.g. a comment keyed by a paragraph's position in the reader's DOM
(``content.children[i]``) can be shown next to that paragraph's text without a second HTML
parser on the caller's side.
"""

from __future__ import annotations

from html.parser import HTMLParser

from ranobelib.models import Chapter

_VOID_TAGS = frozenset({"br", "hr", "img"})


class _TopLevelTextCollector(HTMLParser):
    """Collects the text of each top-level element of an HTML fragment, in order.

    Every start tag at depth 0 begins a new entry, void ones (``br``/``hr``/``img``)
    included, since each is an element child in the DOM too. Text outside any element at the
    top level isn't an entry (it's a text node, not an element child) and is ignored. A
    ``<br />`` inside an entry separates words, like a space.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._depth = 0
        self.entries: list[list[str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._depth == 0:
            self.entries.append([])
        if tag in _VOID_TAGS:
            if self._depth > 0:
                self.entries[-1].append(" ")
        else:
            self._depth += 1

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in _VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag not in _VOID_TAGS and self._depth > 0:
            self._depth -= 1

    def handle_data(self, data: str) -> None:
        if self._depth > 0:
            self.entries[-1].append(data)


def chapter_paragraphs(chapter: Chapter) -> list[str]:
    """A fetched chapter's top-level blocks as plain text, in document order.

    Entry ``i`` is the text of the ``i``-th top-level element of ``chapter.content`` — the
    same position a browser gives it among the rendered content's element children — so a
    paragraph index counted in the DOM can be used to look it up directly.

    Args:
        chapter: A chapter with content already fetched (e.g. via ``get_chapter()``).

    Returns:
        One string per top-level element: its text with entities decoded and whitespace
        collapsed to single spaces (``""`` for a block without text, such as ``<hr />`` or
        an image-only paragraph). ``chapter.footnotes`` aren't included — they're not part
        of ``content`` (see ``Chapter.footnotes``).

    Raises:
        ValueError: If ``chapter.content`` is ``None`` (not yet fetched — see ``Chapter``'s
            docstring for when that happens).
    """
    if chapter.content is None:
        raise ValueError(
            f"Chapter {chapter.volume}/{chapter.number} has no content — "
            "fetch it first, e.g. via get_chapter()."
        )
    collector = _TopLevelTextCollector()
    collector.feed(chapter.content)
    collector.close()
    return [" ".join("".join(parts).split()) for parts in collector.entries]

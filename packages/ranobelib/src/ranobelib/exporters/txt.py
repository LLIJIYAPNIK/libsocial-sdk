"""Plain text exporter."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from html.parser import HTMLParser
from pathlib import Path
from typing import ClassVar

from ranobelib.exporters import register
from ranobelib.exporters._shared import chapter_body_html, chapter_heading
from ranobelib.models import Chapter, Title

_BLOCK_TAGS = frozenset({"p", "div"})


class _HtmlToText(HTMLParser):
    """Extracts readable plain text from the SDK's normalized chapter-content HTML.

    Built on the stdlib parser rather than a regex, since chapter content isn't limited to
    the small tag vocabulary ``Chapter.content`` normalizes prosemirror-doc chapters to —
    HTML-string-format chapters pass the site's own markup through as-is, which can include
    tags/entities a regex would mishandle (see docs/api-notes.md's chapter-content notes).
    Images carry no text and are dropped automatically, matching the "no illustrations in
    txt/fb2" decision in CLAUDE.md.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._paragraphs: list[str] = []
        self._current: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _BLOCK_TAGS:
            self._flush()
        elif tag == "br":
            self._current.append("\n")
        elif tag == "hr":
            self._flush()
            self._paragraphs.append("---")

    def handle_endtag(self, tag: str) -> None:
        if tag in _BLOCK_TAGS:
            self._flush()

    def handle_data(self, data: str) -> None:
        self._current.append(data)

    def _flush(self) -> None:
        text = "".join(self._current).strip()
        if text:
            self._paragraphs.append(text)
        self._current = []

    def get_text(self) -> str:
        self._flush()
        return "\n\n".join(self._paragraphs)


def html_to_text(html_fragment: str) -> str:
    """Convert an HTML chapter-content fragment to plain text paragraphs."""
    parser = _HtmlToText()
    parser.feed(html_fragment)
    return parser.get_text()


@register
class TxtExporter:
    """Exports chapters as a single plain-text file, one heading per chapter."""

    format: ClassVar[str] = "txt"

    async def export(
        self,
        title: Title,
        chapters: list[Chapter],
        output_path: Path,
        *,
        on_chapter: Callable[[], None] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Path:
        """Write ``chapters`` to ``output_path`` as plain text.

        Args:
            title: The chapters' parent title; only its name is used.
            chapters: The chapters to include, in the order they should appear.
            output_path: Where to write the ``.txt`` file.
            on_chapter: Called once per chapter written, if given.
            headers: Accepted for the ``Exporter`` protocol and ignored — this format
                downloads nothing (no illustrations in txt, see CLAUDE.md).

        Returns:
            ``output_path``.
        """
        sections = [title.name]
        for chapter in chapters:
            body = html_to_text(chapter_body_html(chapter))
            sections.append(f"{chapter_heading(chapter)}\n\n{body}")
            if on_chapter is not None:
                on_chapter()

        output_path.write_text("\n\n\n".join(sections) + "\n", encoding="utf-8")
        return output_path

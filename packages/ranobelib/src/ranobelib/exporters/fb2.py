"""FB2 exporter."""

from __future__ import annotations

import datetime
import xml.etree.ElementTree as ET
from collections.abc import Callable, Mapping
from html.parser import HTMLParser
from pathlib import Path
from typing import ClassVar

from ranobelib.exporters import register
from ranobelib.exporters._shared import chapter_body_html, chapter_heading
from ranobelib.models import Chapter, Title

FB2_NS = "http://www.gribuser.ru/xml/fictionbook/2.0"
ET.register_namespace("", FB2_NS)

_BLOCK_TAGS = frozenset({"p", "div"})
_STRONG_TAGS = frozenset({"strong", "b"})
_EMPHASIS_TAGS = frozenset({"em", "i"})

_FALLBACK_GENRE = "prose_contemporary"
"""FB2's genre vocabulary is a fixed, controlled list with no reliable mapping from
ranobelib's free-text genres — guessing wrong would be worse than a generic, always-valid
fallback (title-info requires at least one genre), so genre mapping is out of scope for now.
"""


def _tag(name: str) -> str:
    return f"{{{FB2_NS}}}{name}"


class _HtmlToFb2Paragraphs(HTMLParser):
    """Parses the SDK's normalized chapter-content HTML into FB2 ``<p>``/``<empty-line/>``
    elements, preserving ``<strong>``/``<em>`` marks (mapped from ``b``/``i`` too — see
    docs/api-notes.md's chapter-content notes on that tag variance).

    Built on the stdlib parser rather than a regex, same reasoning as the txt exporter's
    ``html_to_text``: HTML-string-format chapters pass the site's own markup through as-is.
    Images carry no text and are dropped, matching CLAUDE.md's "no illustrations in fb2/txt"
    decision.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._paragraphs: list[ET.Element] = []
        self._current: ET.Element | None = None
        self._stack: list[ET.Element] = []

    def _open_paragraph(self) -> None:
        if self._current is None:
            self._current = ET.Element(_tag("p"))
            self._stack = [self._current]

    def _close_paragraph(self) -> None:
        if self._current is not None:
            if (self._current.text and self._current.text.strip()) or len(self._current):
                self._paragraphs.append(self._current)
            self._current = None
            self._stack = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _BLOCK_TAGS or tag == "br":
            self._close_paragraph()
            self._open_paragraph()
        elif tag == "hr":
            self._close_paragraph()
            self._paragraphs.append(ET.Element(_tag("empty-line")))
        elif tag in _STRONG_TAGS:
            self._open_paragraph()
            self._stack.append(ET.SubElement(self._stack[-1], _tag("strong")))
        elif tag in _EMPHASIS_TAGS:
            self._open_paragraph()
            self._stack.append(ET.SubElement(self._stack[-1], _tag("emphasis")))

    def handle_endtag(self, tag: str) -> None:
        if tag in _BLOCK_TAGS:
            self._close_paragraph()
        elif (tag in _STRONG_TAGS or tag in _EMPHASIS_TAGS) and len(self._stack) > 1:
            self._stack.pop()

    def handle_data(self, data: str) -> None:
        self._open_paragraph()
        target = self._stack[-1]
        if len(target) == 0:
            target.text = (target.text or "") + data
        else:
            last = target[-1]
            last.tail = (last.tail or "") + data

    def get_paragraphs(self) -> list[ET.Element]:
        self._close_paragraph()
        return self._paragraphs


def html_to_fb2_paragraphs(html_fragment: str) -> list[ET.Element]:
    """Convert an HTML chapter-content fragment to a list of FB2 body elements."""
    parser = _HtmlToFb2Paragraphs()
    parser.feed(html_fragment)
    return parser.get_paragraphs()


def _build_description(title: Title) -> ET.Element:
    description = ET.Element(_tag("description"))

    title_info = ET.SubElement(description, _tag("title-info"))
    ET.SubElement(title_info, _tag("genre")).text = _FALLBACK_GENRE
    for author in title.authors:
        author_el = ET.SubElement(title_info, _tag("author"))
        ET.SubElement(author_el, _tag("nickname")).text = author.name
    ET.SubElement(title_info, _tag("book-title")).text = title.name
    if title.summary:
        annotation = ET.SubElement(title_info, _tag("annotation"))
        for paragraph in title.summary.split("\n\n"):
            ET.SubElement(annotation, _tag("p")).text = paragraph
    ET.SubElement(title_info, _tag("lang")).text = "ru"

    document_info = ET.SubElement(description, _tag("document-info"))
    document_author = ET.SubElement(document_info, _tag("author"))
    ET.SubElement(document_author, _tag("nickname")).text = "ranobelib-python-sdk"
    today = datetime.date.today().isoformat()
    ET.SubElement(document_info, _tag("date"), value=today).text = today
    ET.SubElement(document_info, _tag("id")).text = title.slug_url
    ET.SubElement(document_info, _tag("version")).text = "1.0"

    return description


def _build_body(chapters: list[Chapter], on_chapter: Callable[[], None] | None) -> ET.Element:
    body = ET.Element(_tag("body"))
    for chapter in chapters:
        section = ET.SubElement(body, _tag("section"))
        section_title = ET.SubElement(section, _tag("title"))
        ET.SubElement(section_title, _tag("p")).text = chapter_heading(chapter)
        for paragraph in html_to_fb2_paragraphs(chapter_body_html(chapter)):
            section.append(paragraph)
        if on_chapter is not None:
            on_chapter()
    return body


@register
class Fb2Exporter:
    """Exports chapters as a single FB2 (FictionBook 2) file, one section per chapter."""

    format: ClassVar[str] = "fb2"

    async def export(
        self,
        title: Title,
        chapters: list[Chapter],
        output_path: Path,
        *,
        on_chapter: Callable[[], None] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Path:
        """Write ``chapters`` to ``output_path`` as FB2 XML.

        Args:
            title: The chapters' parent title; supplies ``description`` metadata.
            chapters: The chapters to include, in the order they should appear.
            output_path: Where to write the ``.fb2`` file.
            on_chapter: Called once per chapter written, if given.
            headers: Accepted for the ``Exporter`` protocol and ignored — this format
                downloads nothing (no illustrations in fb2, see CLAUDE.md).

        Returns:
            ``output_path``.
        """
        root = ET.Element(_tag("FictionBook"))
        root.append(_build_description(title))
        root.append(_build_body(chapters, on_chapter))

        tree = ET.ElementTree(root)
        ET.indent(tree, space="  ")
        tree.write(output_path, encoding="utf-8", xml_declaration=True)
        return output_path

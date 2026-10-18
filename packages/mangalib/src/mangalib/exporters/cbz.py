"""CBZ exporter: a zip of the page images in reading order, with ``ComicInfo.xml``."""

from __future__ import annotations

import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import ClassVar

from mangalib._http import SITE_ORIGIN
from mangalib.exporters import FetchPages, register
from mangalib.exporters._shared import chapter_label, image_extension
from mangalib.exporters._writing import atomic_output
from mangalib.models import Chapter, Title

_RIGHT_TO_LEFT_TYPES = frozenset({"Манга"})
"""Title types (``Title.country``) read right to left — ``ComicInfo``'s
``Manga=YesAndRightToLeft``. Manhwa, manhua and the rest are read left to right, and the
field is left out for them rather than guessed further."""


@register
class CbzExporter:
    """Writes chapters as one CBZ: every page image in reading order, plus ``ComicInfo.xml``.

    Pages are stored without recompression (they're JPEGs already), named by their position
    in the book with zero padding (``0001.jpg``, ``0002.jpg``, ...) so every reader sorts
    them right, with the extension taken from the image's bytes. Where each chapter starts is
    recorded as a ``Bookmark`` on its first page in ``ComicInfo.xml`` (schema 2.1, as read by
    Komga, Kavita, ComicRack and others), which also carries the title's metadata.
    """

    format: ClassVar[str] = "cbz"

    async def export(
        self,
        title: Title,
        chapters: list[Chapter],
        output_path: Path,
        *,
        fetch_pages: FetchPages,
        on_chapter: Callable[[], None] | None = None,
    ) -> Path:
        """Write ``chapters`` to ``output_path`` as a CBZ — see ``Exporter.export()``."""
        total_pages = sum(len(chapter.pages) for chapter in chapters)
        width = max(4, len(str(total_pages)))
        entries: list[_PageEntry] = []
        with (
            atomic_output(output_path) as temporary,
            zipfile.ZipFile(temporary, "w", zipfile.ZIP_STORED) as archive,
        ):
            for chapter in chapters:
                images = await fetch_pages(chapter)
                for position, (page, data) in enumerate(zip(chapter.pages, images, strict=True)):
                    index = len(entries)
                    archive.writestr(f"{index + 1:0{width}}.{image_extension(data)}", data)
                    entries.append(
                        _PageEntry(
                            size=len(data),
                            width=page.width,
                            height=page.height,
                            bookmark=chapter_label(chapter) if position == 0 else None,
                        )
                    )
                if on_chapter is not None:
                    on_chapter()
            archive.writestr("ComicInfo.xml", comic_info(title, chapters, entries))
        return output_path


class _PageEntry:
    """What ``ComicInfo.xml`` says about one page of the book."""

    def __init__(
        self, *, size: int, width: int | None, height: int | None, bookmark: str | None
    ) -> None:
        self.size = size
        self.width = width
        self.height = height
        self.bookmark = bookmark


def comic_info(title: Title, chapters: list[Chapter], pages: list[_PageEntry]) -> bytes:
    """``ComicInfo.xml`` for a book of ``chapters`` (not public API).

    Elements are written in the schema's order, only when there's a value. ``Number`` (and
    a chapter's name as ``Title``) is set for a single chapter, ``Volume`` when every chapter
    is in the same numbered volume — a book spanning several has neither.
    """
    root = ET.Element(
        "ComicInfo",
        {
            "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
            "xmlns:xsd": "http://www.w3.org/2001/XMLSchema",
        },
    )

    def add(tag: str, value: object) -> None:
        if value not in (None, "", []):
            ET.SubElement(root, tag).text = str(value)

    volumes = {chapter.volume for chapter in chapters}
    single = chapters[0] if len(chapters) == 1 else None
    volume = next(iter(volumes)) if len(volumes) == 1 else None
    if single is not None:
        book_title = single.name
    elif volume is not None:
        book_title = f"Том {volume}"
    else:
        book_title = None
    teams = dict.fromkeys(team.name for chapter in chapters for team in chapter.teams)

    add("Title", book_title)
    add("Series", title.rus_name or title.name)
    add("Number", single.number if single is not None else None)
    add("Volume", volume if volume is not None and volume.isdigit() else None)
    add("Summary", title.summary)
    add("Year", title.release_date if (title.release_date or "").isdigit() else None)
    add("Writer", ", ".join(person.name for person in title.authors))
    add("Penciller", ", ".join(person.name for person in title.artists))
    add("Translator", ", ".join(teams))
    add("Genre", ", ".join(genre.name for genre in title.genres))
    add("Tags", ", ".join(tag.name for tag in title.tags))
    add("Web", f"{SITE_ORIGIN}/ru/manga/{title.slug_url}")
    add("PageCount", len(pages))
    add("LanguageISO", "ru")
    if title.country is not None and title.country.name in _RIGHT_TO_LEFT_TYPES:
        add("Manga", "YesAndRightToLeft")

    pages_element = ET.SubElement(root, "Pages")
    for index, page in enumerate(pages):
        attributes = {"Image": str(index), "ImageSize": str(page.size)}
        if page.width is not None and page.height is not None:
            attributes["ImageWidth"] = str(page.width)
            attributes["ImageHeight"] = str(page.height)
        if page.bookmark is not None:
            attributes["Bookmark"] = page.bookmark
        ET.SubElement(pages_element, "Page", attributes)

    ET.indent(root)
    data: bytes = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    return data

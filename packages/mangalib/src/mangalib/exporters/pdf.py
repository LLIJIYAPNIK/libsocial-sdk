"""PDF exporter: one PDF page per page image, via img2pdf (``mangalib-python-sdk[pdf]``)."""

from __future__ import annotations

import asyncio
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import ClassVar

from mangalib.exporters import FetchPages, register
from mangalib.exporters._shared import chapter_label, image_extension
from mangalib.exporters._writing import atomic_output
from mangalib.models import Chapter, Title

try:
    import img2pdf
    import pikepdf
except ImportError:
    img2pdf = None
    pikepdf = None  # type: ignore[assignment]
    # The "pdf" extra isn't installed: "pdf" just isn't registered below, and
    # MangaLib.export(fmt="pdf") raises the same ValueError as for any unknown format.


class PdfExporter:
    """Writes chapters as one PDF: a page per page image, an outline entry per chapter.

    JPEGs are embedded as they are, without recompression (img2pdf), so the file is about
    the size of the images. Each PDF page is the image's own size; a tall webtoon strip
    beyond the PDF page-size limit is scaled with ``/UserUnit`` rather than cut. The PDF is
    assembled in memory, so for a whole long title CBZ is the lighter choice.
    """

    format: ClassVar[str] = "pdf"

    async def export(
        self,
        title: Title,
        chapters: list[Chapter],
        output_path: Path,
        *,
        fetch_pages: FetchPages,
        on_chapter: Callable[[], None] | None = None,
    ) -> Path:
        """Write ``chapters`` to ``output_path`` as a PDF — see ``Exporter.export()``."""
        with tempfile.TemporaryDirectory(prefix="mangalib-pdf-") as directory:
            files: list[Path] = []
            outline: list[tuple[str, int]] = []
            for chapter in chapters:
                images = await fetch_pages(chapter)
                if images:
                    outline.append((chapter_label(chapter), len(files)))
                for data in images:
                    path = Path(directory) / f"{len(files):06}.{image_extension(data)}"
                    path.write_bytes(data)
                    files.append(path)
                if on_chapter is not None:
                    on_chapter()
            with atomic_output(output_path) as temporary:
                await asyncio.to_thread(_write_pdf, title, files, outline, temporary)
        return output_path


def _write_pdf(title: Title, files: list[Path], outline: list[tuple[str, int]], path: Path) -> None:
    """Assemble the PDF (CPU-bound and synchronous, so it runs off the event loop)."""
    with path.open("wb") as stream:
        img2pdf.convert(
            [str(file) for file in files],
            outputstream=stream,
            title=title.rus_name or title.name,
            author=", ".join(person.name for person in title.authors) or None,
            nodate=True,
        )
    with pikepdf.open(path, allow_overwriting_input=True) as pdf:
        with pdf.open_outline() as document_outline:
            for label, page_index in outline:
                document_outline.root.append(pikepdf.OutlineItem(label, page_index))
        pdf.save(path)


if img2pdf is not None:
    register(PdfExporter)

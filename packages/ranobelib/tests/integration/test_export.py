"""Integration tests for RanobeLib.export(), backed by VCR cassettes.

Exercises the full pipeline through the public facade: fetching chapters, then exporting
them with a registered exporter (currently "txt", "fb2", and "epub" — see exporters/txt.py,
exporters/fb2.py, exporters/epub.py). VCR intercepts httpx globally, so it also records the
epub exporter's own image-downloading client, not just the SDK's ApiClient.

No VCR-backed test for "pdf" here: recording its cassette needs a machine where WeasyPrint's
native dependencies actually work (this repo's Windows dev environment doesn't have them —
see docs/api-notes.md's "PDF export" notes), and CI runs with --record-mode=none, so it
can't record one either. tests/unit/test_pdf_exporter.py covers the full download-then-
render pipeline instead, via an injected mock transport (no cassette needed) — it exercises
the real WeasyPrint rendering path in any environment that has it (including CI, since
ci.yml installs the needed system packages), just without going through RanobeLib itself.
"""

import zipfile
from pathlib import Path

import ebooklib
import pytest
from ebooklib import epub as ebooklib_epub
from lxml import etree

from ranobelib import RanobeLib
from ranobelib.exporters.fb2 import FB2_NS


@pytest.mark.vcr
async def test_export_writes_txt_file_with_fetched_chapters(tmp_path: Path) -> None:
    output_path = tmp_path / "output.txt"
    async with RanobeLib("https://ranobelib.me/ru/book/91443--new-hero-in-dxd") as lib:
        chapters = await lib.get_chapters([(1, "1"), (1, "2")])
        result = await lib.export(chapters, fmt="txt", path=output_path)

    assert result == output_path
    text = output_path.read_text(encoding="utf-8")
    assert "Volume 1, Chapter 1" in text
    assert "Volume 1, Chapter 2" in text


@pytest.mark.vcr
async def test_export_writes_fb2_file_with_fetched_chapters(tmp_path: Path) -> None:
    output_path = tmp_path / "output.fb2"
    async with RanobeLib("https://ranobelib.me/ru/book/91443--new-hero-in-dxd") as lib:
        chapters = await lib.get_chapters([(1, "1"), (1, "2")])
        result = await lib.export(chapters, fmt="fb2", path=output_path)

    assert result == output_path
    root = etree.parse(str(output_path)).getroot()
    sections = root.findall(f"{{{FB2_NS}}}body/{{{FB2_NS}}}section")
    assert len(sections) == 2


@pytest.mark.vcr
async def test_export_writes_epub_file_with_fetched_chapters(tmp_path: Path) -> None:
    output_path = tmp_path / "output.epub"
    async with RanobeLib("https://ranobelib.me/ru/book/91443--new-hero-in-dxd") as lib:
        chapters = await lib.get_chapters([(1, "1"), (1, "2")])
        result = await lib.export(chapters, fmt="epub", path=output_path)

    assert result == output_path
    book = ebooklib_epub.read_epub(str(output_path))
    documents = [item for item in book.get_items() if item.get_type() == ebooklib.ITEM_DOCUMENT]
    assert sum(1 for item in documents if item.file_name.startswith("chapter_")) == 2
    with zipfile.ZipFile(output_path) as archive:
        assert any(name.startswith("EPUB/images/") for name in archive.namelist())


async def test_export_raises_value_error_for_unknown_format(tmp_path: Path) -> None:
    # No @pytest.mark.vcr / cassette needed: an unknown fmt is rejected before any request.
    # "docx", not "pdf": pdf is a real (if conditionally-registered) format now.
    async with RanobeLib("https://ranobelib.me/ru/book/91443--new-hero-in-dxd") as lib:
        with pytest.raises(ValueError, match="Unknown export format"):
            await lib.export([], fmt="docx", path=tmp_path / "output.docx")

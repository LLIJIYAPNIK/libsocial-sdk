"""Unit tests for mangalib.exporters: the registry, CBZ and PDF output (no network)."""

import io
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any

import pypdf
import pytest
from PIL import Image

from mangalib.exporters import EXPORTERS, Exporter
from mangalib.exporters._shared import image_extension
from mangalib.exporters.cbz import CbzExporter
from mangalib.exporters.pdf import PdfExporter
from mangalib.models import Chapter, Page, Title


def _image(fmt: str, size: tuple[int, int] = (40, 60), mode: str = "RGB") -> bytes:
    buffer = io.BytesIO()
    Image.new(mode, size, "white").save(buffer, fmt)
    return buffer.getvalue()


JPEG = _image("JPEG")
PNG = _image("PNG", mode="RGBA")
WEBP = _image("WEBP")


def _title(**extra: Any) -> Title:
    return Title.model_validate(
        {
            "id": 7965,
            "name": "Chainsaw Man",
            "rus_name": "Человек-бензопила",
            "slug": "chainsaw-man",
            "slug_url": "7965--chainsaw-man",
            "cover": {},
            "ageRestriction": {"id": 4, "label": "18+"},
            "status": {"id": 1, "label": "Онгоинг"},
            "type": {"id": 1, "label": "Манга"},
            "summary": "Денджи...",
            "releaseDate": "2018",
            "authors": [{"id": 1, "slug": "f", "slug_url": "1--f", "name": "Tatsuki Fujimoto"}],
            "artists": [{"id": 1, "slug": "f", "slug_url": "1--f", "name": "Tatsuki Fujimoto"}],
            "genres": [{"id": 1, "name": "Экшен"}, {"id": 2, "name": "Ужасы"}],
            "tags": [{"id": 3, "name": "Демоны"}],
            **extra,
        }
    )


def _chapter(volume: str, number: str, pages: int, name: str | None = None) -> Chapter:
    return Chapter(
        id=int(float(number) * 10),
        volume=volume,
        number=number,
        name=name,
        teams=[{"id": 1273, "slug": "nippa", "slug_url": "1273--nippa", "name": "Nippa"}],
        pages=[
            Page(
                id=i,
                number=i,
                image=f"{i:02}.png",
                url=f"//manga/x/chapters/{number}/{i:02}.png",
                width=40,
                height=60,
            )
            for i in range(1, pages + 1)
        ],
    )


class _Pages:
    """A ``fetch_pages`` stand-in: serves the same images for every chapter, counting calls."""

    def __init__(self, *images: bytes) -> None:
        self.images = images
        self.fetched: list[str] = []

    async def __call__(self, chapter: Chapter) -> list[bytes]:
        self.fetched.append(chapter.number)
        return [self.images[i % len(self.images)] for i in range(len(chapter.pages))]


def test_registry_has_cbz_and_pdf_exporters() -> None:
    assert EXPORTERS["cbz"] is CbzExporter
    assert EXPORTERS["pdf"] is PdfExporter
    assert all(isinstance(exporter(), Exporter) for exporter in EXPORTERS.values())


@pytest.mark.parametrize(
    ("data", "extension"),
    [(JPEG, "jpg"), (PNG, "png"), (WEBP, "webp"), (b"GIF89a...", "gif"), (b"???", "jpg")],
)
def test_image_extension_comes_from_the_bytes(data: bytes, extension: str) -> None:
    assert image_extension(data) == extension


async def test_cbz_holds_pages_in_order_with_padded_names_and_comic_info(tmp_path: Path) -> None:
    chapters = [_chapter("1", "1", 2, name="Пёс и бензопила"), _chapter("1", "2", 1)]
    pages = _Pages(JPEG, PNG)
    done: list[None] = []

    path = await CbzExporter().export(
        _title(),
        chapters,
        tmp_path / "book.cbz",
        fetch_pages=pages,
        on_chapter=lambda: done.append(None),
    )

    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        assert names == ["0001.jpg", "0002.png", "0003.jpg", "ComicInfo.xml"]
        assert archive.read("0002.png") == PNG
        assert all(info.compress_type == zipfile.ZIP_STORED for info in archive.infolist())
        info = ET.fromstring(archive.read("ComicInfo.xml"))
    assert pages.fetched == ["1", "2"]
    assert len(done) == 2

    fields = {element.tag: element.text for element in info if element.tag != "Pages"}
    assert fields == {
        "Title": "Том 1",
        "Series": "Человек-бензопила",
        "Volume": "1",
        "Summary": "Денджи...",
        "Year": "2018",
        "Writer": "Tatsuki Fujimoto",
        "Penciller": "Tatsuki Fujimoto",
        "Translator": "Nippa",
        "Genre": "Экшен, Ужасы",
        "Tags": "Демоны",
        "Web": "https://mangalib.me/ru/manga/7965--chainsaw-man",
        "PageCount": "3",
        "LanguageISO": "ru",
        "Manga": "YesAndRightToLeft",
    }
    page_entries = [page.attrib for page in info.find("Pages") or []]
    assert page_entries[0] == {
        "Image": "0",
        "ImageSize": str(len(JPEG)),
        "ImageWidth": "40",
        "ImageHeight": "60",
        "Bookmark": "Том 1 Глава 1 — Пёс и бензопила",
    }
    assert "Bookmark" not in page_entries[1]
    assert page_entries[2]["Bookmark"] == "Том 1 Глава 2"


async def test_cbz_comic_info_for_one_chapter_and_for_several_volumes(tmp_path: Path) -> None:
    title = _title(type={"id": 5, "label": "Манхва"}, releaseDate="2018 г.")

    one = await CbzExporter().export(
        title, [_chapter("2", "9", 1, name="Name")], tmp_path / "one.cbz", fetch_pages=_Pages(JPEG)
    )
    several = await CbzExporter().export(
        title,
        [_chapter("1", "1", 1), _chapter("2", "9", 1)],
        tmp_path / "several.cbz",
        fetch_pages=_Pages(JPEG),
    )

    with zipfile.ZipFile(one) as archive:
        single = ET.fromstring(archive.read("ComicInfo.xml"))
    with zipfile.ZipFile(several) as archive:
        multi = ET.fromstring(archive.read("ComicInfo.xml"))
    assert (single.findtext("Title"), single.findtext("Number")) == ("Name", "9")
    assert single.findtext("Volume") == "2"
    assert single.find("Year") is None  # not a bare year
    assert single.find("Manga") is None  # manhwa: not right to left
    assert multi.find("Title") is None and multi.find("Number") is None
    assert multi.find("Volume") is None


async def test_failed_export_leaves_no_file_and_keeps_an_earlier_one(tmp_path: Path) -> None:
    path = tmp_path / "book.cbz"
    path.write_bytes(b"earlier export")

    async def failing(chapter: Chapter) -> list[bytes]:
        raise RuntimeError("page download failed")

    with pytest.raises(RuntimeError):
        await CbzExporter().export(_title(), [_chapter("1", "1", 1)], path, fetch_pages=failing)

    assert path.read_bytes() == b"earlier export"
    assert list(tmp_path.iterdir()) == [path]


async def test_pdf_has_a_page_per_image_and_an_outline_entry_per_chapter(tmp_path: Path) -> None:
    chapters = [_chapter("1", "1", 2, name="Пёс и бензопила"), _chapter("1", "2", 1)]
    done: list[None] = []

    path = await PdfExporter().export(
        _title(),
        chapters,
        tmp_path / "book.pdf",
        fetch_pages=_Pages(JPEG, PNG, WEBP),
        on_chapter=lambda: done.append(None),
    )

    reader = pypdf.PdfReader(path)
    assert len(reader.pages) == 3
    assert reader.metadata is not None
    assert reader.metadata.title == "Человек-бензопила"
    assert reader.metadata.author == "Tatsuki Fujimoto"
    outline = [(item.title, reader.get_destination_page_number(item)) for item in reader.outline]
    assert outline == [("Том 1 Глава 1 — Пёс и бензопила", 0), ("Том 1 Глава 2", 2)]
    assert len(done) == 2
    assert list(tmp_path.iterdir()) == [path]


async def test_pdf_embeds_jpeg_without_recompressing(tmp_path: Path) -> None:
    path = await PdfExporter().export(
        _title(), [_chapter("1", "1", 1)], tmp_path / "book.pdf", fetch_pages=_Pages(JPEG)
    )

    images = pypdf.PdfReader(path).pages[0].images
    assert images[0].data == JPEG


def test_pdf_is_not_registered_without_img2pdf(monkeypatch: pytest.MonkeyPatch) -> None:
    import importlib
    import sys

    import mangalib.exporters.pdf as pdf_module

    monkeypatch.setitem(sys.modules, "img2pdf", None)  # makes `import img2pdf` fail
    monkeypatch.delitem(EXPORTERS, "pdf")
    try:
        importlib.reload(pdf_module)
        assert "pdf" not in EXPORTERS
        assert "cbz" in EXPORTERS
    finally:
        monkeypatch.undo()
        importlib.reload(pdf_module)
    assert "pdf" in EXPORTERS

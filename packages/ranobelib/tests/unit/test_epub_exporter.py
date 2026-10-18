"""Unit tests for the epub exporter.

Content-level assertions read the generated .epub's zip entries directly rather than going
through ebooklib.epub.read_epub() + get_content(): round-tripping through the reader
re-derives some attributes (observed: chapter <html lang> falls back to the reader's own
book-level default) differently from what was actually written to disk. Structural checks
(item list, types, file names) do use read_epub(), where that quirk doesn't apply.
"""

import zipfile
from pathlib import Path

import ebooklib
import httpx
import pytest
from ebooklib import epub as ebooklib_epub

from ranobelib._http import BROWSER_HEADERS
from ranobelib.exporters import EXPORTERS
from ranobelib.exporters.epub import EpubExporter, extract_image_urls, rewrite_image_srcs
from ranobelib.models import Chapter, Cover, Label, Title


def _title(**overrides: object) -> Title:
    defaults: dict[str, object] = {
        "id": 1,
        "name": "Example Title",
        "slug": "1--example-title",
        "slug_url": "1--example-title",
        "cover": Cover(),
        "age_restriction": Label(id=0, label="16+"),
        "status": Label(id=1, label="Ongoing"),
    }
    return Title.model_validate({**defaults, **overrides})


def _chapter(*, volume: str, number: str, name: str | None, content: str | None) -> Chapter:
    return Chapter.model_validate(
        {"id": 1, "volume": volume, "number": number, "name": name, "content": content}
    )


def _read_zip_entry(path: Path, name: str) -> bytes:
    with zipfile.ZipFile(path) as archive:
        return archive.read(name)


def test_epub_exporter_is_registered_under_its_format() -> None:
    assert EXPORTERS["epub"] is EpubExporter


def test_extract_image_urls_finds_all_images() -> None:
    html = '<p>Text.</p><img src="a.jpg" /><p>More.</p><img loading="lazy" src="b.png" />'

    assert extract_image_urls(html) == ["a.jpg", "b.png"]


def test_extract_image_urls_handles_no_images() -> None:
    assert extract_image_urls("<p>No images here.</p>") == []


def test_rewrite_image_srcs_replaces_mapped_urls_and_drops_unmapped() -> None:
    html = '<img src="a.jpg" /><img src="unmapped.jpg" />'

    result = rewrite_image_srcs(html, {"a.jpg": "images/img0001.jpg"})

    assert result == '<img src="images/img0001.jpg" />'


def test_rewrite_image_srcs_preserves_text_and_marks() -> None:
    html = "<p>Plain <strong>bold</strong> and <em>italic</em>.</p>"

    assert rewrite_image_srcs(html, {}) == html


def test_rewrite_image_srcs_escapes_entities() -> None:
    assert rewrite_image_srcs("<p>Tom &amp; Jerry</p>", {}) == "<p>Tom &amp; Jerry</p>"


def test_rewrite_image_srcs_preserves_valueless_attributes() -> None:
    html = "<p hidden>Text.</p>"

    assert rewrite_image_srcs(html, {}) == html


async def test_epub_exporter_embeds_cover_and_rewrites_chapter_images(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "cover" in str(request.url):
            return httpx.Response(200, content=b"COVERBYTES")
        return httpx.Response(200, content=b"IMAGEBYTES")

    title = _title(
        name="My Novel",
        cover=Cover(default="https://cover.example/cover.jpg"),
        authors=[{"id": 1, "slug": "a", "slug_url": "1--a", "name": "Author Name"}],
    )
    chapters = [
        _chapter(
            volume="1",
            number="1",
            name="Beginnings",
            content='<p>Hello <strong>world</strong>.</p><img src="https://img.example/1.jpg" />',
        ),
    ]
    output_path = tmp_path / "out.epub"

    result = await EpubExporter(transport=httpx.MockTransport(handler)).export(
        title, chapters, output_path
    )

    assert result == output_path

    book = ebooklib_epub.read_epub(str(output_path))
    file_names = {
        item.file_name for item in book.get_items() if item.get_type() != ebooklib.ITEM_UNKNOWN
    }
    assert "cover.jpg" in file_names
    assert "images/img0001.jpg" in file_names
    assert "chapter_1.xhtml" in file_names

    assert _read_zip_entry(output_path, "EPUB/cover.jpg") == b"COVERBYTES"
    assert _read_zip_entry(output_path, "EPUB/images/img0001.jpg") == b"IMAGEBYTES"

    chapter_xhtml = _read_zip_entry(output_path, "EPUB/chapter_1.xhtml").decode("utf-8")
    assert "Volume 1, Chapter 1: Beginnings" in chapter_xhtml
    assert 'src="images/img0001.jpg"' in chapter_xhtml
    assert "img.example" not in chapter_xhtml


async def test_epub_exporter_skips_failed_downloads(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    title = _title(cover=Cover(default="https://cover.example/cover.jpg"))
    chapters = [
        _chapter(
            volume="1",
            number="1",
            name=None,
            content='<p>Text.</p><img src="https://img.example/broken.jpg" />',
        )
    ]
    output_path = tmp_path / "out.epub"

    await EpubExporter(transport=httpx.MockTransport(handler)).export(title, chapters, output_path)

    book = ebooklib_epub.read_epub(str(output_path))
    file_names = {
        item.file_name for item in book.get_items() if item.get_type() != ebooklib.ITEM_UNKNOWN
    }
    assert not any(name.startswith("images/") for name in file_names)
    assert "cover.jpg" not in file_names

    chapter_xhtml = _read_zip_entry(output_path, "EPUB/chapter_1.xhtml").decode("utf-8")
    assert "img.example" not in chapter_xhtml


async def test_epub_exporter_handles_no_cover_and_no_chapters(tmp_path: Path) -> None:
    title = _title(cover=Cover())
    output_path = tmp_path / "out.epub"

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no requests expected without a cover or images")

    await EpubExporter(transport=httpx.MockTransport(handler)).export(title, [], output_path)

    book = ebooklib_epub.read_epub(str(output_path))
    documents = [item for item in book.get_items() if item.get_type() == ebooklib.ITEM_DOCUMENT]
    assert all("chapter_" not in item.file_name for item in documents)


@pytest.mark.parametrize("status_code", [500, 429])
async def test_epub_exporter_skips_cover_on_any_http_error(
    tmp_path: Path, status_code: int
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code)

    title = _title(cover=Cover(default="https://cover.example/cover.jpg"))
    output_path = tmp_path / "out.epub"

    await EpubExporter(transport=httpx.MockTransport(handler)).export(title, [], output_path)

    book = ebooklib_epub.read_epub(str(output_path))
    file_names = {item.file_name for item in book.get_items()}
    assert "cover.jpg" not in file_names


async def test_epub_exporter_downloads_images_with_browser_headers(tmp_path: Path) -> None:
    requested: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(request)
        return httpx.Response(200, content=b"IMAGEBYTES")

    title = _title(cover=Cover(default="https://cover.example/cover.jpg"))
    chapter = _chapter(
        volume="1", number="1", name=None, content='<p><img src="https://img.example/a.png"></p>'
    )

    await EpubExporter(transport=httpx.MockTransport(handler)).export(
        title, [chapter], tmp_path / "out.epub"
    )

    assert {str(request.url) for request in requested} == {
        "https://cover.example/cover.jpg",
        "https://img.example/a.png",
    }
    for request in requested:
        for name, value in BROWSER_HEADERS.items():
            assert request.headers[name] == value
        assert "Site-Id" not in request.headers


async def test_epub_exporter_headers_override_browser_defaults(tmp_path: Path) -> None:
    requested: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(request)
        return httpx.Response(200, content=b"IMAGEBYTES")

    title = _title(cover=Cover(default="https://cover.example/cover.jpg"))

    await EpubExporter(transport=httpx.MockTransport(handler)).export(
        title, [], tmp_path / "out.epub", headers={"user-agent": "CustomAgent/1.0"}
    )

    [request] = requested
    assert request.headers.get_list("User-Agent") == ["CustomAgent/1.0"]
    assert request.headers["Referer"] == BROWSER_HEADERS["Referer"]


async def test_epub_exporter_calls_on_chapter_once_per_chapter(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"IMAGEBYTES")

    title = _title()
    chapters = [
        _chapter(volume="1", number="1", name=None, content="<p>A</p>"),
        _chapter(volume="1", number="2", name=None, content="<p>B</p>"),
    ]
    calls = 0

    def on_chapter() -> None:
        nonlocal calls
        calls += 1

    await EpubExporter(transport=httpx.MockTransport(handler)).export(
        title, chapters, tmp_path / "out.epub", on_chapter=on_chapter
    )

    assert calls == 2


async def test_epub_exporter_includes_footnotes_and_their_images(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"IMAGEBYTES")

    content = '<p>Story.</p><p>↑ Note <img src="https://img.example/fn.jpg" /></p>'
    chapters = [_chapter(volume="1", number="1", name=None, content=content)]
    output_path = tmp_path / "out.epub"

    await EpubExporter(transport=httpx.MockTransport(handler)).export(
        _title(), chapters, output_path
    )

    chapter_xhtml = _read_zip_entry(output_path, "EPUB/chapter_1.xhtml").decode("utf-8")
    assert "Notes" in chapter_xhtml
    assert "Note" in chapter_xhtml
    assert 'src="images/img0001.jpg"' in chapter_xhtml

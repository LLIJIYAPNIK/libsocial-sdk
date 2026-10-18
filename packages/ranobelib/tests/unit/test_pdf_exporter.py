"""Unit tests for the pdf exporter.

PdfExporter needs WeasyPrint's native dependencies (Pango/cairo/gobject, via a GTK3 runtime
on Windows/macOS) to actually render -- see docs/api-notes.md's "PDF export" notes. Tests
that exercise real rendering are skipped when it's unavailable (e.g. this repo's Windows dev
environment) rather than failing; CI installs the needed system packages so they run there.
The pure HTML-fragment-building helpers don't need WeasyPrint at all and always run.
"""

from pathlib import Path

import httpx
import pytest
from pypdf import PdfReader

from ranobelib._http import BROWSER_HEADERS
from ranobelib.exporters import EXPORTERS
from ranobelib.exporters.pdf import _chapter_html, _data_uri, _title_page_html, weasyprint
from ranobelib.models import Chapter, Cover, Label, Title

needs_weasyprint = pytest.mark.skipif(
    weasyprint is None, reason="WeasyPrint's native dependencies aren't available"
)


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


def test_data_uri_encodes_base64() -> None:
    assert _data_uri("image/jpeg", b"hello") == "data:image/jpeg;base64,aGVsbG8="


def test_title_page_html_includes_name_and_authors() -> None:
    title = _title(
        name="My Novel",
        authors=[{"id": 1, "slug": "a", "slug_url": "1--a", "name": "Author Name"}],
    )

    result = _title_page_html(title, None)

    assert "<h1>My Novel</h1>" in result
    assert "Author Name" in result
    assert "<img" not in result


def test_title_page_html_embeds_cover_when_given() -> None:
    result = _title_page_html(_title(), "data:image/jpeg;base64,AAAA")

    assert '<img src="data:image/jpeg;base64,AAAA" />' in result


def test_title_page_html_escapes_name_and_authors() -> None:
    title = _title(
        name="A & B", authors=[{"id": 1, "slug": "a", "slug_url": "1--a", "name": "X & Y"}]
    )

    result = _title_page_html(title, None)

    assert "A &amp; B" in result
    assert "X &amp; Y" in result


def test_chapter_html_includes_heading_and_rewritten_body() -> None:
    chapter = _chapter(
        volume="1",
        number="1",
        name="Beginnings",
        content='<p>Hi <img src="https://img.example/1.jpg" /></p>',
    )

    result = _chapter_html(chapter, {"https://img.example/1.jpg": "data:image/jpeg;base64,AAAA"})

    assert "<h1>Volume 1, Chapter 1: Beginnings</h1>" in result
    assert 'src="data:image/jpeg;base64,AAAA"' in result
    assert "img.example" not in result


def test_chapter_html_handles_no_content() -> None:
    chapter = _chapter(volume="1", number="1", name=None, content=None)

    result = _chapter_html(chapter, {})

    assert "<h1>Volume 1, Chapter 1</h1>" in result


@needs_weasyprint
def test_pdf_exporter_is_registered_under_its_format() -> None:
    from ranobelib.exporters.pdf import PdfExporter

    assert EXPORTERS["pdf"] is PdfExporter


@needs_weasyprint
async def test_pdf_exporter_writes_pdf_with_chapters_and_cover(tmp_path: Path) -> None:
    from ranobelib.exporters.pdf import PdfExporter

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=b"\xff\xd8\xff\xe0FAKEJPEG", headers={"content-type": "image/jpeg"}
        )

    title = _title(name="My Novel", cover=Cover(default="https://cover.example/cover.jpg"))
    chapters = [
        _chapter(volume="1", number="1", name="Beginnings", content="<p>Hello world.</p>"),
        _chapter(volume="1", number="2", name="Middle", content="<p>More text.</p>"),
    ]
    output_path = tmp_path / "out.pdf"

    result = await PdfExporter(transport=httpx.MockTransport(handler)).export(
        title, chapters, output_path
    )

    assert result == output_path
    assert output_path.read_bytes().startswith(b"%PDF")

    reader = PdfReader(output_path)
    assert len(reader.pages) >= 3  # Title page + one fresh page per chapter.
    full_text = "\n".join(page.extract_text() for page in reader.pages)
    assert "My Novel" in full_text
    assert "Beginnings" in full_text
    assert "Hello world." in full_text
    assert "Middle" in full_text
    assert "More text." in full_text


@needs_weasyprint
async def test_pdf_exporter_skips_failed_cover_download(tmp_path: Path) -> None:
    from ranobelib.exporters.pdf import PdfExporter

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    title = _title(cover=Cover(default="https://cover.example/cover.jpg"))
    output_path = tmp_path / "out.pdf"

    await PdfExporter(transport=httpx.MockTransport(handler)).export(title, [], output_path)

    assert output_path.read_bytes().startswith(b"%PDF")


@needs_weasyprint
async def test_pdf_exporter_downloads_images_with_browser_headers(tmp_path: Path) -> None:
    from ranobelib.exporters.pdf import PdfExporter

    requested: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(request)
        return httpx.Response(404)

    title = _title(cover=Cover(default="https://cover.example/cover.jpg"))
    chapter = _chapter(
        volume="1", number="1", name=None, content='<p><img src="https://img.example/a.png"></p>'
    )

    await PdfExporter(transport=httpx.MockTransport(handler)).export(
        title, [chapter], tmp_path / "out.pdf"
    )

    assert {str(request.url) for request in requested} == {
        "https://cover.example/cover.jpg",
        "https://img.example/a.png",
    }
    for request in requested:
        for name, value in BROWSER_HEADERS.items():
            assert request.headers[name] == value
        assert "Site-Id" not in request.headers


@needs_weasyprint
async def test_pdf_exporter_headers_override_browser_defaults(tmp_path: Path) -> None:
    from ranobelib.exporters.pdf import PdfExporter

    requested: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(request)
        return httpx.Response(404)

    title = _title(cover=Cover(default="https://cover.example/cover.jpg"))

    await PdfExporter(transport=httpx.MockTransport(handler)).export(
        title, [], tmp_path / "out.pdf", headers={"user-agent": "CustomAgent/1.0"}
    )

    [request] = requested
    assert request.headers.get_list("User-Agent") == ["CustomAgent/1.0"]
    assert request.headers["Referer"] == BROWSER_HEADERS["Referer"]


@needs_weasyprint
async def test_pdf_exporter_handles_no_cover_and_no_chapters(tmp_path: Path) -> None:
    from ranobelib.exporters.pdf import PdfExporter

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no requests expected without a cover or images")

    title = _title(name="Empty Book", cover=Cover())
    output_path = tmp_path / "out.pdf"

    await PdfExporter(transport=httpx.MockTransport(handler)).export(title, [], output_path)

    reader = PdfReader(output_path)
    assert "Empty Book" in reader.pages[0].extract_text()


@needs_weasyprint
async def test_pdf_exporter_calls_on_chapter_once_per_chapter(tmp_path: Path) -> None:
    from ranobelib.exporters.pdf import PdfExporter

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    title = _title()
    chapters = [
        _chapter(volume="1", number="1", name=None, content="<p>A</p>"),
        _chapter(volume="1", number="2", name=None, content="<p>B</p>"),
    ]
    calls = 0

    def on_chapter() -> None:
        nonlocal calls
        calls += 1

    await PdfExporter(transport=httpx.MockTransport(handler)).export(
        title, chapters, tmp_path / "out.pdf", on_chapter=on_chapter
    )

    assert calls == 2


def test_chapter_html_includes_footnotes() -> None:
    chapter = _chapter(volume="1", number="1", name=None, content="<p>Story.</p><p>↑ Note.</p>")

    result = _chapter_html(chapter, {})

    assert "<p>Story.</p><hr /><p><strong>Notes</strong></p><p>Note.</p>" in result

"""Unit tests for the exporter registry and the txt exporter."""

from pathlib import Path

import pytest

from ranobelib.exporters import EXPORTERS, Exporter, register
from ranobelib.exporters._shared import chapter_body_html
from ranobelib.exporters.txt import TxtExporter, html_to_text
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


def test_txt_exporter_is_registered_under_its_format() -> None:
    assert EXPORTERS["txt"] is TxtExporter


def test_txt_exporter_satisfies_exporter_protocol() -> None:
    assert isinstance(TxtExporter(), Exporter)


def test_register_adds_class_to_registry_and_returns_it_unchanged() -> None:
    class _DummyExporter:
        format = "dummy-test-format"

        async def export(self, title: Title, chapters: list[Chapter], output_path: Path) -> Path:
            return output_path

    try:
        registered = register(_DummyExporter)
        assert registered is _DummyExporter
        assert EXPORTERS["dummy-test-format"] is _DummyExporter
    finally:
        del EXPORTERS["dummy-test-format"]


def test_html_to_text_joins_paragraphs_with_blank_line() -> None:
    html = "<p>First paragraph.</p><p>Second paragraph.</p>"

    assert html_to_text(html) == "First paragraph.\n\nSecond paragraph."


def test_html_to_text_converts_br_to_newline_within_paragraph() -> None:
    html = "<p>Line one.<br />Line two.</p>"

    assert html_to_text(html) == "Line one.\nLine two."


def test_html_to_text_converts_hr_to_separator() -> None:
    html = "<p>Before.</p><hr /><p>After.</p>"

    assert html_to_text(html) == "Before.\n\n---\n\nAfter."


def test_html_to_text_drops_images_but_keeps_marked_up_text() -> None:
    html = '<p><strong>Bold</strong> and <em>italic</em>.</p><img loading="lazy" src="x.jpg" />'

    assert html_to_text(html) == "Bold and italic."


def test_html_to_text_decodes_entities() -> None:
    assert html_to_text("<p>Tom &amp; Jerry</p>") == "Tom & Jerry"


def test_html_to_text_handles_empty_content() -> None:
    assert html_to_text("") == ""


async def test_txt_exporter_writes_title_and_chapter_headings(tmp_path: Path) -> None:
    title = _title(name="My Novel")
    chapters = [
        _chapter(volume="1", number="1", name="Beginnings", content="<p>Once upon a time.</p>"),
        _chapter(volume="1", number="2", name=None, content="<p>Continued.</p>"),
    ]
    output_path = tmp_path / "out.txt"

    result = await TxtExporter().export(title, chapters, output_path)

    assert result == output_path
    text = output_path.read_text(encoding="utf-8")
    assert text.startswith("My Novel\n\n\n")
    assert "Volume 1, Chapter 1: Beginnings" in text
    assert "Once upon a time." in text
    assert "Volume 1, Chapter 2" in text
    assert "Volume 1, Chapter 2:" not in text  # No name -> no trailing colon.
    assert "Continued." in text


async def test_txt_exporter_handles_chapter_without_content(tmp_path: Path) -> None:
    title = _title()
    chapters = [_chapter(volume="1", number="1", name=None, content=None)]
    output_path = tmp_path / "out.txt"

    await TxtExporter().export(title, chapters, output_path)

    assert output_path.read_text(encoding="utf-8").strip().endswith("Volume 1, Chapter 1")


@pytest.mark.parametrize("chapters", [[]])
async def test_txt_exporter_handles_no_chapters(tmp_path: Path, chapters: list[Chapter]) -> None:
    title = _title(name="Empty Book")
    output_path = tmp_path / "out.txt"

    await TxtExporter().export(title, chapters, output_path)

    assert output_path.read_text(encoding="utf-8").strip() == "Empty Book"


async def test_txt_exporter_calls_on_chapter_once_per_chapter(tmp_path: Path) -> None:
    title = _title()
    chapters = [
        _chapter(volume="1", number="1", name=None, content="<p>A</p>"),
        _chapter(volume="1", number="2", name=None, content="<p>B</p>"),
    ]
    calls = 0

    def on_chapter() -> None:
        nonlocal calls
        calls += 1

    await TxtExporter().export(title, chapters, tmp_path / "out.txt", on_chapter=on_chapter)

    assert calls == 2


async def test_txt_exporter_works_without_on_chapter(tmp_path: Path) -> None:
    title = _title()
    chapters = [_chapter(volume="1", number="1", name=None, content="<p>A</p>")]

    result = await TxtExporter().export(title, chapters, tmp_path / "out.txt")

    assert result.exists()


async def test_txt_exporter_accepts_and_ignores_headers(tmp_path: Path) -> None:
    output_path = tmp_path / "out.txt"

    await TxtExporter().export(_title(), [], output_path, headers={"User-Agent": "X"})

    assert output_path.exists()


def test_chapter_body_html_is_content_when_no_footnotes() -> None:
    chapter = _chapter(volume="1", number="1", name=None, content="<p>Text.</p>")

    assert chapter_body_html(chapter) == "<p>Text.</p>"


def test_chapter_body_html_appends_footnotes_after_content() -> None:
    chapter = _chapter(
        volume="1", number="1", name=None, content="<p>Text*.</p><p>↑ A <b>note</b>.</p>"
    )

    assert chapter_body_html(chapter) == (
        "<p>Text*.</p><hr /><p><strong>Notes</strong></p><p>A <strong>note</strong>.</p>"
    )


async def test_txt_exporter_includes_footnotes(tmp_path: Path) -> None:
    chapters = [_chapter(volume="1", number="1", name=None, content="<p>Story.</p><p>↑ Note.</p>")]
    output_path = tmp_path / "out.txt"

    await TxtExporter().export(_title(), chapters, output_path)

    text = output_path.read_text(encoding="utf-8")
    assert text.endswith("Story.\n\n---\n\nNotes\n\nNote.\n")

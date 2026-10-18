"""Unit tests for the fb2 exporter, validating structure via lxml (not just "file exists")."""

from pathlib import Path

from lxml import etree

from ranobelib.exporters import EXPORTERS
from ranobelib.exporters.fb2 import FB2_NS, Fb2Exporter, html_to_fb2_paragraphs
from ranobelib.models import Chapter, Cover, Label, Title

_NSMAP = {"fb": FB2_NS}


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


def test_fb2_exporter_is_registered_under_its_format() -> None:
    assert EXPORTERS["fb2"] is Fb2Exporter


def test_html_to_fb2_paragraphs_splits_on_block_tags() -> None:
    paragraphs = html_to_fb2_paragraphs("<p>First.</p><p>Second.</p>")

    assert [p.text for p in paragraphs] == ["First.", "Second."]


def test_html_to_fb2_paragraphs_splits_br_into_separate_paragraphs() -> None:
    paragraphs = html_to_fb2_paragraphs("<p>Line one.<br />Line two.</p>")

    assert [p.text for p in paragraphs] == ["Line one.", "Line two."]


def _local_name(element: object) -> str:
    """The unprefixed tag name of a stdlib ElementTree element, e.g. "p" for "{ns}p"."""
    tag = element.tag  # type: ignore[attr-defined]
    return tag.split("}", 1)[1] if "}" in tag else tag


def test_html_to_fb2_paragraphs_converts_hr_to_empty_line() -> None:
    paragraphs = html_to_fb2_paragraphs("<p>Before.</p><hr /><p>After.</p>")

    assert [_local_name(p) for p in paragraphs] == ["p", "empty-line", "p"]


def test_html_to_fb2_paragraphs_preserves_strong_and_emphasis_marks() -> None:
    (paragraph,) = html_to_fb2_paragraphs("<p>Plain <strong>bold</strong> and <em>italic</em>.</p>")

    strong, emphasis = list(paragraph)
    assert paragraph.text == "Plain "
    assert _local_name(strong) == "strong"
    assert strong.text == "bold"
    assert strong.tail == " and "
    assert _local_name(emphasis) == "emphasis"
    assert emphasis.text == "italic"
    assert emphasis.tail == "."


def test_html_to_fb2_paragraphs_maps_b_and_i_tags_too() -> None:
    (paragraph,) = html_to_fb2_paragraphs("<p><b>Bold</b> <i>italic</i></p>")

    strong, emphasis = list(paragraph)
    assert _local_name(strong) == "strong"
    assert _local_name(emphasis) == "emphasis"


def test_html_to_fb2_paragraphs_drops_images() -> None:
    paragraphs = html_to_fb2_paragraphs('<p>Text.</p><img loading="lazy" src="x.jpg" />')

    assert len(paragraphs) == 1
    assert paragraphs[0].text == "Text."


def test_html_to_fb2_paragraphs_handles_empty_content() -> None:
    assert html_to_fb2_paragraphs("") == []


async def test_fb2_exporter_writes_well_formed_xml_with_expected_structure(tmp_path: Path) -> None:
    title = _title(
        name="My Novel",
        summary="First paragraph.\n\nSecond paragraph.",
        authors=[{"id": 1, "slug": "a", "slug_url": "1--a", "name": "Author Name"}],
    )
    chapters = [
        _chapter(volume="1", number="1", name="Beginnings", content="<p>Once upon a time.</p>"),
        _chapter(volume="1", number="2", name=None, content="<p>Continued.</p>"),
    ]
    output_path = tmp_path / "out.fb2"

    result = await Fb2Exporter().export(title, chapters, output_path)

    assert result == output_path
    tree = etree.parse(str(output_path))
    root = tree.getroot()
    assert etree.QName(root).localname == "FictionBook"
    assert etree.QName(root).namespace == FB2_NS

    book_title = root.find("fb:description/fb:title-info/fb:book-title", namespaces=_NSMAP)
    assert book_title is not None
    assert book_title.text == "My Novel"

    author_nickname = root.find(
        "fb:description/fb:title-info/fb:author/fb:nickname", namespaces=_NSMAP
    )
    assert author_nickname is not None
    assert author_nickname.text == "Author Name"

    annotation_paragraphs = root.findall(
        "fb:description/fb:title-info/fb:annotation/fb:p", namespaces=_NSMAP
    )
    assert [p.text for p in annotation_paragraphs] == ["First paragraph.", "Second paragraph."]

    sections = root.findall("fb:body/fb:section", namespaces=_NSMAP)
    assert len(sections) == 2

    first_title = sections[0].find("fb:title/fb:p", namespaces=_NSMAP)
    assert first_title is not None
    assert first_title.text == "Volume 1, Chapter 1: Beginnings"
    first_body_paragraph = sections[0].find("fb:p", namespaces=_NSMAP)
    assert first_body_paragraph is not None
    assert first_body_paragraph.text == "Once upon a time."

    second_title = sections[1].find("fb:title/fb:p", namespaces=_NSMAP)
    assert second_title is not None
    assert second_title.text == "Volume 1, Chapter 2"


async def test_fb2_exporter_handles_title_without_authors_or_summary(tmp_path: Path) -> None:
    title = _title(name="Bare Title")
    output_path = tmp_path / "out.fb2"

    await Fb2Exporter().export(title, [], output_path)

    tree = etree.parse(str(output_path))
    root = tree.getroot()
    assert root.find("fb:description/fb:title-info/fb:annotation", namespaces=_NSMAP) is None
    assert root.find("fb:description/fb:title-info/fb:author", namespaces=_NSMAP) is None
    assert root.findall("fb:body/fb:section", namespaces=_NSMAP) == []


async def test_fb2_exporter_handles_chapter_without_content(tmp_path: Path) -> None:
    title = _title()
    chapters = [_chapter(volume="1", number="1", name=None, content=None)]
    output_path = tmp_path / "out.fb2"

    await Fb2Exporter().export(title, chapters, output_path)

    tree = etree.parse(str(output_path))
    section = tree.getroot().find("fb:body/fb:section", namespaces=_NSMAP)
    assert section is not None
    assert section.findall("fb:p", namespaces=_NSMAP) == []


async def test_fb2_exporter_calls_on_chapter_once_per_chapter(tmp_path: Path) -> None:
    title = _title()
    chapters = [
        _chapter(volume="1", number="1", name=None, content="<p>A</p>"),
        _chapter(volume="1", number="2", name=None, content="<p>B</p>"),
    ]
    calls = 0

    def on_chapter() -> None:
        nonlocal calls
        calls += 1

    await Fb2Exporter().export(title, chapters, tmp_path / "out.fb2", on_chapter=on_chapter)

    assert calls == 2


async def test_fb2_exporter_includes_footnotes(tmp_path: Path) -> None:
    chapters = [_chapter(volume="1", number="1", name=None, content="<p>Story.</p><p>↑ Note.</p>")]
    output_path = tmp_path / "out.fb2"

    await Fb2Exporter().export(_title(), chapters, output_path)

    section = etree.parse(str(output_path)).getroot().find("fb:body/fb:section", namespaces=_NSMAP)
    assert section is not None
    texts = ["".join(p.itertext()).strip() for p in section.findall("fb:p", namespaces=_NSMAP)]
    assert texts == ["Story.", "Notes", "Note."]


async def test_fb2_exporter_accepts_and_ignores_headers(tmp_path: Path) -> None:
    output_path = tmp_path / "out.fb2"

    await Fb2Exporter().export(_title(), [], output_path, headers={"User-Agent": "X"})

    assert output_path.exists()

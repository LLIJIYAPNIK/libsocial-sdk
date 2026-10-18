"""Unit tests for ranobelib.paragraphs."""

from typing import Any

import pytest

from ranobelib import chapter_paragraphs
from ranobelib.models import Chapter

RAW_CHAPTER: dict[str, Any] = {"id": 1, "volume": "1", "number": "1", "name": "One"}

IMG = "https://ranobelib.me/uploads/a.jpg"


def _chapter(content: str | dict[str, Any] | None, **extra: Any) -> Chapter:
    return Chapter.model_validate({**RAW_CHAPTER, "content": content, **extra})


def test_one_entry_per_top_level_element_in_order() -> None:
    chapter = _chapter(f'<p>First.</p><hr /><p>Second.</p><img src="{IMG}" /><p></p>')

    assert chapter_paragraphs(chapter) == ["First.", "", "Second.", "", ""]


def test_inline_markup_is_flattened_to_text() -> None:
    chapter = _chapter("<p>a <strong>bold</strong> and <em>italic</em> word</p>")

    assert chapter_paragraphs(chapter) == ["a bold and italic word"]


def test_whitespace_collapsed_and_br_separates_words() -> None:
    chapter = _chapter("<p>  line one<br />line\n\n two  </p>")

    assert chapter_paragraphs(chapter) == ["line one line two"]


def test_entities_are_decoded() -> None:
    chapter = _chapter("<p>Tom &amp; Jerry &lt;3 &quot;hi&quot;</p>")

    assert chapter_paragraphs(chapter) == ['Tom & Jerry <3 "hi"']


def test_image_only_paragraph_is_empty_string() -> None:
    chapter = _chapter(f'<p>Text</p><p><img src="{IMG}" /></p>')

    assert chapter_paragraphs(chapter) == ["Text", ""]


def test_footnotes_are_not_included() -> None:
    chapter = _chapter("<p>Story*.</p><p>↑ A translator note.</p>")

    assert chapter.footnotes
    assert chapter_paragraphs(chapter) == ["Story*."]


def test_dropped_blocks_count_as_their_wrapped_paragraphs() -> None:
    # #59: a dropped block's text becomes its own <p>, so it's an entry like any other.
    chapter = _chapter("<h3>Part one</h3><p>Body.</p><ul><li>a</li><li>b</li></ul>")

    assert chapter_paragraphs(chapter) == ["Part one", "Body.", "a", "b"]


def test_prosemirror_content() -> None:
    chapter = _chapter(
        {
            "type": "doc",
            "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": "One"}]},
                {"type": "horizontalRule"},
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "text", "text": "Two"},
                        {"type": "hardBreak"},
                        {"type": "text", "text": "lines", "marks": [{"type": "bold"}]},
                    ],
                },
            ],
        }
    )

    assert chapter_paragraphs(chapter) == ["One", "", "Two lines"]


def test_top_level_text_outside_elements_is_not_an_entry() -> None:
    # Bypass the sanitizer: chapter_paragraphs counts whatever ends up in content.
    chapter = _chapter(None).model_copy(update={"content": "stray <p>Kept</p> text<br />"})

    assert chapter_paragraphs(chapter) == ["Kept", ""]


def test_self_closed_non_void_element_is_one_empty_entry() -> None:
    chapter = _chapter(None).model_copy(update={"content": "<p /><p>After</p>"})

    assert chapter_paragraphs(chapter) == ["", "After"]


def test_empty_content_has_no_entries() -> None:
    assert chapter_paragraphs(_chapter("")) == []


def test_raises_when_content_not_fetched() -> None:
    with pytest.raises(ValueError, match="no content"):
        chapter_paragraphs(_chapter(None))

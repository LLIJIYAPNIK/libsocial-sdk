"""Unit tests for ranobelib.sizing."""

from typing import Any

import pytest

from ranobelib.models import Chapter, Volume
from ranobelib.sizing import DEFAULT_AVERAGE_IMAGE_SIZE, chapter_size, volume_size

RAW_CHAPTER: dict[str, Any] = {
    "id": 1,
    "volume": "1",
    "number": "1",
    "content": None,
}


def _chapter(content: str | None) -> Chapter:
    return Chapter.model_validate({**RAW_CHAPTER, "content": content})


def test_chapter_size_counts_exact_text_bytes_without_images() -> None:
    chapter = _chapter("<p>hello</p>")

    assert chapter_size(chapter) == len(b"<p>hello</p>")


def test_chapter_size_adds_average_size_per_image() -> None:
    content = '<p>text</p><img src="https://ranobelib.me/a.jpg" />'
    chapter = _chapter(content)

    # chapter.content is the sanitized form (see test_chapter_content.py), not the raw
    # `content` passed in above — that's what chapter_size actually measures.
    expected = len(chapter.content.encode()) + DEFAULT_AVERAGE_IMAGE_SIZE  # type: ignore[union-attr]
    assert chapter_size(chapter) == expected


def test_chapter_size_counts_multiple_images() -> None:
    content = '<img src="https://ranobelib.me/a.jpg" /><img src="https://ranobelib.me/b.jpg" />'
    chapter = _chapter(content)

    expected = len(chapter.content.encode()) + 2 * DEFAULT_AVERAGE_IMAGE_SIZE  # type: ignore[union-attr]
    assert chapter_size(chapter) == expected


def test_chapter_size_accepts_custom_average_image_size() -> None:
    content = '<img src="https://ranobelib.me/a.jpg" />'
    chapter = _chapter(content)

    expected = len(chapter.content.encode()) + 1_000  # type: ignore[union-attr]
    assert chapter_size(chapter, average_image_size=1_000) == expected


def test_chapter_size_raises_value_error_when_content_not_fetched() -> None:
    chapter = _chapter(None)

    with pytest.raises(ValueError, match="no content to size"):
        chapter_size(chapter)


def test_volume_size_sums_chapter_sizes() -> None:
    chapters = [_chapter("<p>aaaa</p>"), _chapter("<p>bb</p>")]
    volume = Volume(number="1", chapters=chapters)

    assert volume_size(volume) == chapter_size(chapters[0]) + chapter_size(chapters[1])


def test_volume_size_is_zero_for_empty_volume() -> None:
    volume = Volume(number="1", chapters=[])

    assert volume_size(volume) == 0


def test_volume_size_raises_value_error_when_any_chapter_missing_content() -> None:
    volume = Volume(number="1", chapters=[_chapter("<p>ok</p>"), _chapter(None)])

    with pytest.raises(ValueError, match="no content to size"):
        volume_size(volume)


def test_chapter_size_includes_footnotes_and_their_images() -> None:
    chapter = _chapter('<p>a</p><p>↑ note <img src="https://ranobelib.me/a.jpg" /></p>')

    footnote = chapter.footnotes[0].content
    expected = len(b"<p>a</p>") + len(footnote.encode()) + DEFAULT_AVERAGE_IMAGE_SIZE
    assert chapter_size(chapter) == expected

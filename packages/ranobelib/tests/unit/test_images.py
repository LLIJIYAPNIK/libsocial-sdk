"""Unit tests for ranobelib.images."""

from typing import Any
from urllib.parse import quote

import pytest

from ranobelib import chapter_image_urls, rewrite_image_urls
from ranobelib.models import Chapter, Footnote

A = "https://ranobelib.me/uploads/a.jpg"
B = "https://ranobelib.me/uploads/b.jpg"
C = "https://cover.cdnlibs.org/c.png"

RAW_CHAPTER: dict[str, Any] = {"id": 1, "volume": "1", "number": "1", "name": "One"}


def _chapter(content: str | None, footnotes: list[str] | None = None) -> Chapter:
    return Chapter.model_validate(
        {
            **RAW_CHAPTER,
            "content": content,
            "footnotes": [{"content": footnote} for footnote in footnotes or []],
        }
    )


def test_chapter_image_urls_lists_content_then_footnotes_in_order() -> None:
    chapter = _chapter(f'<p>x<img src="{B}" /></p><img src="{A}" />', [f'note <img src="{C}" />'])

    assert chapter_image_urls(chapter) == [B, A, C]


def test_chapter_image_urls_deduplicates_keeping_first_occurrence() -> None:
    chapter = _chapter(
        f'<img src="{A}" /><img src="{B}" /><img src="{A}" />', [f'<img src="{B}" />']
    )

    assert chapter_image_urls(chapter) == [A, B]


def test_chapter_image_urls_empty_without_images() -> None:
    assert chapter_image_urls(_chapter("<p>text</p>", ["note"])) == []


def test_chapter_image_urls_raises_when_content_not_fetched() -> None:
    with pytest.raises(ValueError, match="no content"):
        chapter_image_urls(_chapter(None))


def test_rewrite_image_urls_rewrites_content_and_footnotes() -> None:
    chapter = _chapter(f'<p>a<img loading="lazy" src="{A}" /></p>', [f'n<img src="{C}" />'])

    result = rewrite_image_urls(chapter, lambda url: f"/images/view?url={quote(url, safe='')}")

    assert result.content == (
        f'<p>a<img loading="lazy" src="/images/view?url={quote(A, safe="")}" /></p>'
    )
    assert result.footnotes == [
        Footnote(content=f'n<img src="/images/view?url={quote(C, safe="")}" />')
    ]
    assert chapter_image_urls(result) == [
        f"/images/view?url={quote(A, safe='')}",
        f"/images/view?url={quote(C, safe='')}",
    ]


def test_rewrite_image_urls_escapes_the_attribute_value() -> None:
    chapter = _chapter(f'<img src="{A}" />')

    result = rewrite_image_urls(chapter, lambda url: f'/p?u={url}&x="1"')

    assert result.content == f'<img loading="lazy" src="/p?u={A}&amp;x=&quot;1&quot;" />'
    assert chapter_image_urls(result) == [f'/p?u={A}&x="1"']


def test_rewrite_image_urls_returns_copy_and_keeps_other_fields() -> None:
    chapter = _chapter(f'<p>Tom &amp; Jerry</p><img src="{A}" />', ["plain note"])

    result = rewrite_image_urls(chapter, lambda url: "x.jpg")

    assert result is not chapter
    assert chapter.content == f'<p>Tom &amp; Jerry</p><img loading="lazy" src="{A}" />'
    assert result.content == '<p>Tom &amp; Jerry</p><img loading="lazy" src="x.jpg" />'
    assert result.footnotes == [Footnote(content="plain note")]
    assert result.model_dump(exclude={"content", "footnotes"}) == chapter.model_dump(
        exclude={"content", "footnotes"}
    )


def test_rewrite_image_urls_calls_replace_once_per_img() -> None:
    chapter = _chapter(f'<img src="{A}" /><img src="{A}" />')
    seen: list[str] = []

    def replace(url: str) -> str:
        seen.append(url)
        return "y.jpg"

    rewrite_image_urls(chapter, replace)

    assert seen == [A, A]


def test_rewrite_image_urls_raises_when_content_not_fetched() -> None:
    with pytest.raises(ValueError, match="no content"):
        rewrite_image_urls(_chapter(None), lambda url: url)

"""Listing and rewriting the images a fetched chapter references.

Chapter illustrations are ``<img>`` tags with absolute URLs on ranobelib.me /
``*.cdnlibs.org`` (see docs/api-notes.md), inside ``Chapter.content`` and, occasionally,
``Chapter.footnotes``. These helpers expose the same ``<img>`` parsing the epub/pdf
exporters and ``sizing.chapter_size()`` use internally, so a caller that serves chapters
itself (e.g. through its own same-origin image proxy, for offline caching) doesn't need a
second HTML parser of its own.
"""

from __future__ import annotations

from collections.abc import Callable

from ranobelib.exporters._illustrations import extract_image_urls, replace_image_srcs
from ranobelib.models import Chapter, Footnote


def _require_content(chapter: Chapter) -> str:
    if chapter.content is None:
        raise ValueError(
            f"Chapter {chapter.volume}/{chapter.number} has no content — "
            "fetch it first, e.g. via get_chapter()."
        )
    return chapter.content


def chapter_image_urls(chapter: Chapter) -> list[str]:
    """List the image URLs a fetched chapter references.

    Args:
        chapter: A chapter with content already fetched (e.g. via ``get_chapter()``).

    Returns:
        Every ``<img src>`` in ``chapter.content`` and then ``chapter.footnotes``, in
        document order, each URL listed once (its first occurrence).

    Raises:
        ValueError: If ``chapter.content`` is ``None`` (not yet fetched — see ``Chapter``'s
            docstring for when that happens).
    """
    fragments = [_require_content(chapter), *(footnote.content for footnote in chapter.footnotes)]
    urls = (url for fragment in fragments for url in extract_image_urls(fragment))
    return list(dict.fromkeys(urls))


def rewrite_image_urls(chapter: Chapter, replace: Callable[[str], str]) -> Chapter:
    """Return a copy of a fetched chapter with every ``<img src>`` passed through ``replace``.

    Args:
        chapter: A chapter with content already fetched (e.g. via ``get_chapter()``).
        replace: Called with each image URL (once per ``<img>``, so possibly more than once
            for the same URL); its result becomes the new ``src``, HTML-escaped as an
            attribute value. An ``<img>`` without a ``src`` is left as it is.

    Returns:
        A new ``Chapter`` whose ``content`` and ``footnotes`` have their ``<img src>``
        rewritten; every other field is unchanged, and ``chapter`` itself is not modified.

    Raises:
        ValueError: If ``chapter.content`` is ``None`` — see ``chapter_image_urls()``.
    """
    content = _require_content(chapter)

    def rewrite(fragment: str) -> str:
        return replace_image_srcs(fragment, lambda src: replace(src) if src else src)

    return chapter.model_copy(
        update={
            "content": rewrite(content),
            "footnotes": [Footnote(content=rewrite(f.content)) for f in chapter.footnotes],
        }
    )

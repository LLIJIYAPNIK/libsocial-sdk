"""Rough size estimation for already-fetched chapters/volumes, and whole-title sampling.

The API exposes no content-length or image-size field anywhere (see docs/api-notes.md), so
any size here is necessarily approximate for the image portion: chapter text is measured
exactly (the UTF-8 byte length of ``Chapter.content`` plus its footnotes), but each embedded
``<img>`` is assumed to weigh ``average_image_size`` bytes rather than downloaded to measure
precisely — doing that would cost the same network traffic this module exists to help avoid
paying upfront. The result approximates the underlying content size, not a specific export
format's file size (epub's zip compression, pdf's layout overhead, fb2's XML verbosity are
not modeled) — enough to decide whether a title is worth downloading, not to predict an
exported file's exact byte count.
"""

from __future__ import annotations

from ranobelib.exporters._illustrations import extract_image_urls
from ranobelib.models import Chapter, Volume

DEFAULT_AVERAGE_IMAGE_SIZE = 150_000
"""Assumed bytes per embedded image when its real size isn't fetched. A rough guess, not
measured — override with a better estimate for a given title if you have one."""

DEFAULT_SAMPLE_SIZE = 5
"""Default number of chapters ``RanobeLib.estimate_title_size()`` samples."""


def chapter_size(chapter: Chapter, *, average_image_size: int = DEFAULT_AVERAGE_IMAGE_SIZE) -> int:
    """Estimate a fetched chapter's size in bytes: exact text plus assumed-average images.

    Args:
        chapter: A chapter with content already fetched (e.g. via ``get_chapter()``).
        average_image_size: Assumed bytes per ``<img>`` referenced in the chapter's content.

    Raises:
        ValueError: If ``chapter.content`` is ``None`` (not yet fetched — see
            ``Chapter``'s docstring for when that happens).
    """
    if chapter.content is None:
        raise ValueError(
            f"Chapter {chapter.volume}/{chapter.number} has no content to size — "
            "fetch it first, e.g. via get_chapter()."
        )
    # Footnotes are split out of ``content`` (see ``Chapter.footnotes``) but are still part
    # of what was downloaded — and of what every exporter writes out.
    text = chapter.content + "".join(footnote.content for footnote in chapter.footnotes)
    text_bytes = len(text.encode("utf-8"))
    image_count = len(extract_image_urls(text))
    return text_bytes + image_count * average_image_size


def volume_size(volume: Volume, *, average_image_size: int = DEFAULT_AVERAGE_IMAGE_SIZE) -> int:
    """Estimate a fetched volume's size in bytes: the sum of its chapters' ``chapter_size()``.

    Args:
        volume: A volume whose chapters have content already fetched (e.g. via
            ``get_volume()``).
        average_image_size: Forwarded to ``chapter_size()`` for each chapter.

    Raises:
        ValueError: If any chapter in ``volume.chapters`` has no content — see
            ``chapter_size()``.
    """
    return sum(
        chapter_size(chapter, average_image_size=average_image_size) for chapter in volume.chapters
    )

"""Helpers shared between exporter implementations (not part of the public Exporter protocol)."""

from __future__ import annotations

from ranobelib.models import Chapter


def chapter_heading(chapter: Chapter) -> str:
    """A human-readable "Volume X, Chapter Y[: Name]" heading for ``chapter``."""
    heading = f"Volume {chapter.volume}, Chapter {chapter.number}"
    return f"{heading}: {chapter.name}" if chapter.name else heading


FOOTNOTES_HEADING = "Notes"


def chapter_body_html(chapter: Chapter) -> str:
    """``chapter.content`` with its footnotes appended as a trailing "Notes" block.

    Footnotes aren't part of ``Chapter.content`` (see ``Chapter.footnotes``), so exporters
    render a chapter's body through this rather than reading ``content`` directly — otherwise
    an export would silently drop them. There's no in-text link to point them back to (see
    ``Footnote``), so they're listed after the chapter, in source order.
    """
    body = chapter.content or ""
    if not chapter.footnotes:
        return body
    notes = "".join(f"<p>{footnote.content}</p>" for footnote in chapter.footnotes)
    return f"{body}<hr /><p><strong>{FOOTNOTES_HEADING}</strong></p>{notes}"

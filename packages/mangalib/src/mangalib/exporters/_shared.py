"""Helpers shared by the exporters (not public API)."""

from __future__ import annotations

from mangalib.models import Chapter

_SIGNATURES = (
    (b"\xff\xd8\xff", "jpg"),
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"GIF87a", "gif"),
    (b"GIF89a", "gif"),
)


def image_extension(data: bytes) -> str:
    """The file extension for an image, from its bytes rather than its name.

    A page's file name isn't a reliable guide: the ``compress`` server sends JPEG for
    ``.png`` names (see docs/api-notes.md). Unrecognized data gets ``"jpg"``, what the
    servers send nearly always.
    """
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    for signature, extension in _SIGNATURES:
        if data.startswith(signature):
            return extension
    return "jpg"


def chapter_label(chapter: Chapter) -> str:
    """``"Том 1 Глава 5"`` plus the chapter's name, as the site shows a chapter."""
    label = f"Том {chapter.volume} Глава {chapter.number}"
    return f"{label} — {chapter.name}" if chapter.name else label

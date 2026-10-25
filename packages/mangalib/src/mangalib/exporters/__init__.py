"""Exporter protocol and format registry — the same contract as ``ranobelib.exporters``.

A new export format is a new module in this package: define a class implementing
``Exporter`` and decorate it with ``@register`` — no changes needed here or in ``sdk.py``.
Every module in this package is auto-imported below so its ``@register`` runs on its own.
A format whose optional dependency isn't installed (``pdf`` needs ``img2pdf``) skips its
``@register``, so it's simply not in ``EXPORTERS``.
"""

from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import ClassVar, Protocol, TypeVar, runtime_checkable

from mangalib.models import Chapter, Title

__all__ = ["EXPORTERS", "Exporter", "FetchPages", "register"]

FetchPages = Callable[[Chapter], Awaitable[list[bytes]]]
"""Downloads a chapter's page images, in reading order — ``MangaLib.download_pages()``."""


@runtime_checkable
class Exporter(Protocol):
    """Renders a title's chapters, as page images, to a single file in some format."""

    format: ClassVar[str]
    """The registry key this exporter is selected by, e.g. ``"cbz"``."""

    async def export(
        self,
        title: Title,
        chapters: list[Chapter],
        output_path: Path,
        *,
        fetch_pages: FetchPages,
        on_chapter: Callable[[], None] | None = None,
    ) -> Path:
        """Write ``chapters`` (in the given order) to ``output_path``.

        Args:
            title: The chapters' parent title, for metadata (name, authors, ...).
            chapters: The chapters to include, in the order they should appear — fetched
                ones, with ``pages``.
            output_path: Where to write the exported file.
            fetch_pages: Downloads one chapter's page images. The exporter calls it once per
                chapter, in order, so it never holds more than it has to in memory.
            on_chapter: Called once per chapter written, if given — drives
                ``MangaLib.export()``'s progress reporting.

        Returns:
            ``output_path``, once the file has been written.
        """
        ...


ExporterT = TypeVar("ExporterT", bound=type[Exporter])

EXPORTERS: dict[str, type[Exporter]] = {}
"""Registered exporters, keyed by ``Exporter.format``."""


def register(exporter: ExporterT) -> ExporterT:
    """Class decorator: register ``exporter`` under its ``format`` key."""
    EXPORTERS[exporter.format] = exporter
    return exporter


for _module_info in pkgutil.iter_modules(__path__, f"{__name__}."):
    importlib.import_module(_module_info.name)

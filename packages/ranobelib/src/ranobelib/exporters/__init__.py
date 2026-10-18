"""Exporter protocol and format registry.

A new export format is a new module in this package: define a class implementing
``Exporter`` and decorate it with ``@register`` — no changes needed here or in ``sdk.py``.
Every module in this package is auto-imported below so its ``@register`` runs on its own.
"""

from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import ClassVar, Protocol, TypeVar, runtime_checkable

from ranobelib.models import Chapter, Title


@runtime_checkable
class Exporter(Protocol):
    """Renders a title's chapters to a single file in some format."""

    format: ClassVar[str]
    """The registry key this exporter is selected by, e.g. ``"txt"``."""

    async def export(
        self,
        title: Title,
        chapters: list[Chapter],
        output_path: Path,
        *,
        on_chapter: Callable[[], None] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Path:
        """Write ``chapters`` (in the given order) to ``output_path``.

        ``async`` since embedding illustrations (epub, pdf) requires downloading them —
        the SDK is async-only throughout (see CLAUDE.md), so this can't drop to a sync
        HTTP call. txt/fb2 do no I/O and just don't ``await`` anything in their bodies.

        Args:
            title: The chapters' parent title, for metadata (name, authors, ...).
            chapters: The chapters to include, in the order they should appear.
            output_path: Where to write the exported file.
            on_chapter: Called once per chapter processed, if given — drives
                ``RanobeLib.export()``'s progress bar (see CLAUDE.md's roadmap step 23).
                For epub/pdf this covers the per-chapter embedding step, not the earlier
                illustration-download step, which isn't itself progress-reported.
            headers: Extra HTTP headers for any downloads the exporter makes (epub/pdf
                illustrations), merged over the SDK's browser-like defaults —
                ``RanobeLib.export()`` passes its own ``headers=`` through here. Exporters
                that make no requests (txt, fb2) accept and ignore it.

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

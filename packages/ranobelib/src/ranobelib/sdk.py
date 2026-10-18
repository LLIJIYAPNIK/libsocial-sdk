"""Public facade of the SDK: the ``RanobeLib`` class.

Fetching a title, its chapters and translations is ``libsocial-core``'s
(``libsocial.TitleClient``); ``RanobeLib`` points it at ranobelib.me and its own models, and
adds what depends on a chapter being text: ``estimate_title_size()`` and ``export()``.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from libsocial import TitleClient
from libsocial.title import DEFAULT_RATE_LIMIT_RETRIES
from ranobelib._http import RANOBELIB
from ranobelib.cache import DEFAULT_CACHE_DIR
from ranobelib.client import ApiClient
from ranobelib.console import Verbosity
from ranobelib.exporters import EXPORTERS
from ranobelib.models import Chapter, Title, Volume
from ranobelib.sizing import DEFAULT_AVERAGE_IMAGE_SIZE, DEFAULT_SAMPLE_SIZE, chapter_size

__all__ = ["DEFAULT_RATE_LIMIT_RETRIES", "RanobeLib"]


class RanobeLib(TitleClient[Title, Chapter, Volume]):
    """Entry point for interacting with a single ranobelib.me title.

    Example:
        ```python
        async with RanobeLib("https://ranobelib.me/ru/book/6712--high-school-dxd-novel") as lib:
            info = await lib.get_info()
        ```
    """

    site = RANOBELIB
    title_model = Title
    chapter_model = Chapter
    volume_model = Volume

    def __init__(
        self,
        url: str,
        *,
        cache_dir: str | Path | None = None,
        cache_ttl: float | None = None,
        verbosity: Verbosity = False,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        """Initialize the SDK for a title.

        Args:
            url: A ranobelib.me title URL, or a bare ``{id}--{slug}`` identifier.
            cache_dir: Where to cache raw API responses (title metadata, chapter list,
                chapter content) on disk, so a repeated export or downloading newly added
                chapters doesn't re-fetch data already on hand. Defaults to
                ``.ranobelib_cache`` in the current working directory.
            cache_ttl: Seconds after which a cached response is treated as stale and
                re-fetched. ``None`` (the default) means cached responses never expire on
                their own — see ``refresh=True`` on individual methods to force one anyway.
            verbosity: Console output level. ``False`` (default): silent. ``"progress_only"``:
                progress bars during ``download_title()``/``export()``/``estimate_title_size()``.
                ``"full"``: the same progress bars, plus a line logged for every title/
                chapter-list/chapter-content fetch, noting whether it was served from the
                disk cache or the API.
            headers: Extra HTTP headers merged over the SDK's defaults (browser-like
                ``Origin``/``Referer``/``User-Agent``, see docs/api-notes.md, section "WAF
                403") — a key given here replaces the default one, matched
                case-insensitively. Applied to every API request and, through ``export()``,
                to epub/pdf illustration downloads. Meant for when the site's edge protection
                changes which requests it lets through (``AccessBlockedError``): send what it
                now expects without waiting for an SDK release. ``None`` (the default) sends
                the defaults as-is.
        """
        super().__init__(
            url,
            cache_dir=cache_dir if cache_dir is not None else DEFAULT_CACHE_DIR,
            cache_ttl=cache_ttl,
            verbosity=verbosity,
            headers=headers,
        )

    def _create_client(self, headers: Mapping[str, str] | None) -> ApiClient:
        return ApiClient(headers=headers)

    async def estimate_title_size(
        self,
        *,
        sample_size: int = DEFAULT_SAMPLE_SIZE,
        average_image_size: int = DEFAULT_AVERAGE_IMAGE_SIZE,
        branch_id: int | None = None,
        translation_index: int | None = None,
    ) -> int:
        """Estimate the whole title's download size in bytes, from a sample of its chapters.

        Fetches the chapter list (cheap, cached), then the content of up to ``sample_size``
        chapters spread evenly across the title — not just the first ones, since early and
        late chapters can differ in length — and extrapolates the sample's average
        ``sizing.chapter_size()`` across the title's total chapter count. This trades
        exactness for cost: an exact total requires fetching every chapter's content, the
        same cost as ``download_title()`` itself, which defeats the purpose of checking
        "is this worth downloading" *before* paying that cost.

        Sampled chapters go through the same disk cache as any other chapter fetch, so a
        later ``download_title()`` call doesn't refetch them.

        Args:
            sample_size: How many chapters to sample. Clamped to the number of chapters the
                title actually has (or that resolve to a usable translation, see below) if
                that's fewer.
            average_image_size: Forwarded to ``sizing.chapter_size()`` for each sampled
                chapter.
            branch_id: Same meaning as ``download_title(branch_id=...)`` — which translation
                to sample for chapters that have more than one. Mutually exclusive with
                ``translation_index``.
            translation_index: Same meaning as ``download_title(translation_index=...)``.
                Mutually exclusive with ``branch_id``.

        Returns:
            The estimated size in bytes, or ``0`` if the title has no chapters, or none of
            its chapters have a translation ``branch_id``/``translation_index`` resolves.

        Raises:
            ValueError: If both ``branch_id`` and ``translation_index`` are given, or if
                ``sample_size`` is less than 1.

        Note:
            Unlike ``download_title()``, a chapter with more than one translation that
            ``branch_id``/``translation_index`` doesn't resolve is skipped when picking the
            sample rather than raising ``MultipleTitleTranslationsError`` — an estimate
            doesn't need a specific translation to be correct, only *a* chapter's worth of
            this title's content to measure.
        """
        self._check_translation_selectors(branch_id, translation_index)
        if sample_size < 1:
            raise ValueError(f"sample_size must be at least 1, got {sample_size}.")

        raw_chapters = await self._get_chapters()
        if not raw_chapters:
            return 0

        resolvable, _ = self._plan_chapters(
            raw_chapters, branch_id=branch_id, translation_index=translation_index
        )
        if not resolvable:
            return 0

        size = min(sample_size, len(resolvable))
        step = max(1, len(resolvable) // size)
        sample = [resolvable[index] for index in range(0, len(resolvable), step)][:size]

        total_sample_bytes = 0
        with self._reporter.progress(f"Sampling {self._slug_url}", len(sample)) as advance:
            for volume_str, number, selected_branch_id in sample:
                chapter = await self._fetch_chapter(volume_str, number, selected_branch_id)
                total_sample_bytes += chapter_size(chapter, average_image_size=average_image_size)
                advance()

        average_bytes = total_sample_bytes / len(sample)
        return round(average_bytes * len(raw_chapters))

    async def export(self, chapters: list[Chapter], *, fmt: str, path: str | Path) -> Path:
        """Export chapters to a file.

        Args:
            chapters: The chapters to include, in the order they should appear.
            path: Where to write the exported file.
            fmt: Export format — a key of ``ranobelib.exporters.EXPORTERS``
                (currently: ``"txt"``, ``"fb2"``, ``"epub"``, and ``"pdf"`` where
                WeasyPrint's native libraries are available).

        Raises:
            ValueError: If ``fmt`` isn't a registered export format.
        """
        exporter_cls = EXPORTERS.get(fmt)
        if exporter_cls is None:
            available = ", ".join(sorted(EXPORTERS)) or "(none registered)"
            raise ValueError(f"Unknown export format {fmt!r}. Available: {available}")
        title = await self.get_info()
        with self._reporter.progress(f"Exporting to {fmt}", len(chapters)) as advance:
            return await exporter_cls().export(
                title, chapters, Path(path), on_chapter=advance, headers=self._headers
            )

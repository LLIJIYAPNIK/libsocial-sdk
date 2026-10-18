"""Public facade of the SDK: the ``RanobeLib`` class."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from pathlib import Path
from types import TracebackType
from typing import Any, Self

from ranobelib.cache import DEFAULT_CACHE_DIR, DiskCache
from ranobelib.client import ApiClient
from ranobelib.console import Reporter, Verbosity
from ranobelib.exceptions import (
    AmbiguousChapter,
    ChapterNotFoundError,
    DownloadTitleInterruptedError,
    MultipleTitleTranslationsError,
    MultipleTranslationsError,
    RanobeLibError,
    RateLimitError,
    VolumeNotFoundError,
)
from ranobelib.exporters import EXPORTERS
from ranobelib.models import Chapter, ChapterBranch, Title, Volume
from ranobelib.numbering import parse_slug_url
from ranobelib.sizing import DEFAULT_AVERAGE_IMAGE_SIZE, DEFAULT_SAMPLE_SIZE, chapter_size

DEFAULT_RATE_LIMIT_RETRIES = 6
"""Default ``download_title(max_rate_limit_retries=...)`` — see docs/api-notes.md."""

_RATE_LIMIT_RETRY_BASE_DELAY = 5.0
"""Base delay, in seconds, for download_title()'s bulk rate-limit backoff (doubled per
attempt, capped at _RATE_LIMIT_RETRY_MAX_DELAY) — used when the API's 429 doesn't send a
Retry-After header."""

_RATE_LIMIT_RETRY_MAX_DELAY = 60.0

_INFO_FIELDS = [
    "background",
    "eng_name",
    "otherNames",
    "summary",
    "releaseDate",
    "genres",
    "tags",
    "teams",
    "authors",
    "artists",
    "chap_count",
    "last_item_at",
]


class RanobeLib:
    """Entry point for interacting with a single ranobelib.me title.

    Example:
        ```python
        async with RanobeLib("https://ranobelib.me/ru/book/6712--high-school-dxd-novel") as lib:
            info = await lib.get_info()
        ```
    """

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
        self._slug_url = parse_slug_url(url)
        self._headers = dict(headers) if headers is not None else None
        self._client = ApiClient(headers=self._headers)
        self._cache = DiskCache(
            cache_dir if cache_dir is not None else DEFAULT_CACHE_DIR, ttl=cache_ttl
        )
        self._reporter = Reporter(verbosity)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    async def get_info(self, *, refresh: bool = False) -> Title:
        """Fetch title metadata: names, cover, summary, genres, tags, authors, teams.

        Args:
            refresh: Bypass the disk cache and re-fetch from the API even if a cached
                response is on hand.
        """
        data = await self._get_title(refresh=refresh)
        return Title.model_validate(data)

    async def get_table_of_contents(self, *, refresh: bool = False) -> list[Volume]:
        """Fetch the title's volumes and chapter names/numbers, without chapter content.

        Args:
            refresh: Bypass the disk cache and re-fetch from the API even if a cached
                response is on hand — needed to pick up newly published chapters, since
                otherwise the cached chapter list would keep being reused.
        """
        raw_chapters = await self._get_chapters(refresh=refresh)
        chapters = [Chapter.model_validate(item) for item in raw_chapters]
        return _group_into_volumes(chapters)

    async def get_chapter(
        self,
        volume: int,
        number: str,
        *,
        branch_id: int | None = None,
        refresh: bool = False,
    ) -> Chapter:
        """Fetch a single chapter, including its content.

        When a chapter has more than one team's translation and ``branch_id`` isn't given,
        this raises ``MultipleTranslationsError`` rather than guessing — see
        ``get_translations()`` and docs/api-notes.md for why the API's own default (when
        ``branch_id`` is omitted) isn't relied on. Doing this check costs an extra request
        to fetch the chapter list, only when ``branch_id`` isn't already given.

        Args:
            volume: The chapter's volume number.
            number: The chapter number, as returned by the API — may contain a decimal
                (e.g. ``"51.6"``).
            branch_id: Which translation to fetch, as returned by ``get_translations()``.
                Only required when the chapter has more than one.
            refresh: Bypass the disk cache and re-fetch from the API even if a cached
                response is on hand.

        Raises:
            MultipleTranslationsError: If the chapter has more than one translation and
                ``branch_id`` wasn't given.
        """
        volume_str = str(volume)
        if branch_id is None:
            raw_chapters = await self._get_chapters(refresh=refresh)
            branch_id = self._resolve_branch_id(volume_str, number, raw_chapters)
        return await self._fetch_chapter(volume_str, number, branch_id, refresh=refresh)

    async def get_chapters(self, chapters: list[tuple[int, str]]) -> list[Chapter]:
        """Fetch several chapters, including their content.

        Fetches the chapter list once, shared across all requested chapters (also used to
        detect chapters with more than one translation — see ``get_chapter``), then each
        chapter individually and sequentially, in the order given.

        Args:
            chapters: A list of ``(volume, number)`` pairs identifying each chapter.

        Raises:
            ChapterNotFoundError: If any requested chapter doesn't exist.
            MultipleTranslationsError: If any requested chapter has more than one
                translation.
        """
        raw_chapters = await self._get_chapters()
        result = []
        for volume, number in chapters:
            volume_str = str(volume)
            branch_id = self._resolve_branch_id(volume_str, number, raw_chapters)
            result.append(await self._fetch_chapter(volume_str, number, branch_id))
        return result

    async def get_translations(self, volume: int, number: str) -> list[ChapterBranch]:
        """Fetch the available translations (branches) for a chapter.

        Args:
            volume: The chapter's volume number.
            number: The chapter number.

        Raises:
            ChapterNotFoundError: If no chapter exists for this volume/number.
        """
        volume_str = str(volume)
        raw_chapters = await self._get_chapters()
        item = _find_raw_chapter(raw_chapters, volume_str, number)
        if item is None:
            raise ChapterNotFoundError(self._slug_url, volume=volume_str, number=number)
        return [ChapterBranch.model_validate(branch) for branch in item.get("branches") or []]

    async def get_volume(self, volume: int) -> Volume:
        """Fetch a whole volume: all its chapters, each including content.

        The API has no bulk "volume content" endpoint (see docs/api-notes.md), so this
        fetches the chapter list once to find which numbers belong to the volume, then
        fetches each of those chapters individually and sequentially.

        Args:
            volume: The volume number.

        Raises:
            VolumeNotFoundError: If the title has no chapters for this volume.
            MultipleTranslationsError: If any of the volume's chapters has more than one
                translation.
        """
        raw_chapters = await self._get_chapters()
        return await self._build_volume(volume, raw_chapters)

    async def get_volumes(self, volumes: list[int]) -> list[Volume]:
        """Fetch several whole volumes, each including chapter content.

        Fetches the chapter list once, shared across all requested volumes, then each
        chapter individually and sequentially — same approach as ``get_volume``, applied
        to more than one volume without re-fetching the chapter list per volume.

        Args:
            volumes: The volume numbers to fetch.

        Raises:
            VolumeNotFoundError: If the title has no chapters for one of the volumes.
            MultipleTranslationsError: If any of the volumes' chapters has more than one
                translation.
        """
        raw_chapters = await self._get_chapters()
        return [await self._build_volume(volume, raw_chapters) for volume in volumes]

    async def download_title(
        self,
        *,
        branch_id: int | None = None,
        translation_index: int | None = None,
        chapter_delay: float = 0.0,
        on_chapter: Callable[[int, int], None] | None = None,
        max_rate_limit_retries: int = DEFAULT_RATE_LIMIT_RETRIES,
    ) -> list[Volume]:
        """Download every chapter of the title, across all its volumes.

        Fetches the chapter list once, then every chapter's content, sequentially, in the
        API's own order — same pacing/retry/backoff as any other chapter fetch (see
        ``ApiClient``), plus ``chapter_delay`` on top if given.

        Resolving translations is checked for the whole title up front, not chapter by
        chapter: if any chapters have more than one translation, this fetches nothing and
        raises ``MultipleTitleTranslationsError`` listing *all* of them at once (unless
        ``branch_id`` or ``translation_index`` resolves every one of them), rather than
        failing partway through a long download on the first ambiguous chapter.

        A long title's sequential download can outlast ``ApiClient``'s own retry budget for
        429s (tuned for a single one-off request, not hundreds/thousands of sequential
        fetches — see docs/api-notes.md). On top of that, each chapter fetch that still comes
        back rate-limited is retried again here, up to ``max_rate_limit_retries`` times, with
        its own (coarser) backoff. If a chapter fetch still fails after that — from rate
        limiting or anything else — the chapters already downloaded are not discarded: they're
        attached to a raised ``DownloadTitleInterruptedError`` instead of being lost.

        Args:
            branch_id: Translation to use for every chapter that has more than one — same
                meaning as ``get_chapter(..., branch_id=...)``, applied title-wide. Chapters
                with only one translation are unaffected. Mutually exclusive with
                ``translation_index``.
            translation_index: Alternative to ``branch_id``: pick the translation at this
                position in each ambiguous chapter's ``branches`` list (``0`` for the first,
                and so on) — useful when ambiguous chapters don't share one ``branch_id``
                across the title. Mutually exclusive with ``branch_id``.
            chapter_delay: Extra delay, in seconds, after fetching each chapter, on top of
                ``ApiClient``'s own per-request pacing — to be gentler on the API during a
                large bulk download. Defaults to no extra delay.
            on_chapter: Called with ``(completed, total)`` after each chapter is fetched, if
                given — a programmatic progress hook for callers that aren't printing to a
                console (e.g. a web app polling/streaming download progress to a browser),
                who would otherwise have no way to observe anything before this whole
                ``await`` returns. Independent of ``verbosity``: both can be set at once,
                each drives its own output.
            max_rate_limit_retries: How many extra times to retry a single chapter fetch that
                comes back rate-limited, on top of ``ApiClient``'s own retries, before giving
                up on the whole download — see above. Each retry honors the API's
                ``Retry-After`` if it sent one, otherwise waits with its own capped
                exponential backoff. Set to ``0`` to disable this extra layer and let a
                persistent ``RateLimitError`` end the download immediately (still wrapped in
                ``DownloadTitleInterruptedError`` with whatever was already fetched).

        Raises:
            ValueError: If both ``branch_id`` and ``translation_index`` are given.
            MultipleTitleTranslationsError: If the title has one or more chapters with more
                than one translation that ``branch_id``/``translation_index`` didn't resolve.
            DownloadTitleInterruptedError: If fetching a chapter fails unrecoverably partway
                through the download — carries every chapter already fetched.
        """
        if branch_id is not None and translation_index is not None:
            raise ValueError("Pass at most one of branch_id or translation_index, not both.")

        raw_chapters = await self._get_chapters()

        planned: list[tuple[str, str, int | None]] = []
        unresolved: list[AmbiguousChapter] = []
        for item in raw_chapters:
            volume_str: str = item["volume"]
            number: str = item["number"]
            branches = item.get("branches") or []
            if len(branches) <= 1:
                planned.append((volume_str, number, None))
                continue

            resolved, selected = _resolve_bulk_branch_id(
                branches, branch_id=branch_id, translation_index=translation_index
            )
            if resolved:
                planned.append((volume_str, number, selected))
            else:
                unresolved.append(
                    AmbiguousChapter(
                        volume=volume_str,
                        number=number,
                        branches=[ChapterBranch.model_validate(branch) for branch in branches],
                    )
                )

        if unresolved:
            raise MultipleTitleTranslationsError(self._slug_url, chapters=unresolved)

        chapters: list[Chapter] = []
        total = len(planned)
        try:
            with self._reporter.progress(f"Downloading {self._slug_url}", total) as advance:
                for index, (volume_str, number, selected_branch_id) in enumerate(planned):
                    chapters.append(
                        await self._fetch_chapter_riding_out_rate_limits(
                            volume_str,
                            number,
                            selected_branch_id,
                            max_rate_limit_retries=max_rate_limit_retries,
                        )
                    )
                    advance()
                    if on_chapter is not None:
                        on_chapter(index + 1, total)
                    if chapter_delay and index < total - 1:
                        await asyncio.sleep(chapter_delay)
        except RanobeLibError as exc:
            raise DownloadTitleInterruptedError(
                self._slug_url,
                volumes=_group_into_volumes(chapters),
                completed=len(chapters),
                total=total,
            ) from exc
        return _group_into_volumes(chapters)

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
        if branch_id is not None and translation_index is not None:
            raise ValueError("Pass at most one of branch_id or translation_index, not both.")
        if sample_size < 1:
            raise ValueError(f"sample_size must be at least 1, got {sample_size}.")

        raw_chapters = await self._get_chapters()
        if not raw_chapters:
            return 0

        resolvable: list[tuple[str, str, int | None]] = []
        for item in raw_chapters:
            volume_str: str = item["volume"]
            number: str = item["number"]
            branches = item.get("branches") or []
            if len(branches) <= 1:
                resolvable.append((volume_str, number, None))
                continue
            resolved, selected = _resolve_bulk_branch_id(
                branches, branch_id=branch_id, translation_index=translation_index
            )
            if resolved:
                resolvable.append((volume_str, number, selected))

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

    async def _build_volume(self, volume: int, raw_chapters: list[dict[str, Any]]) -> Volume:
        volume_str = str(volume)
        numbers = [item["number"] for item in raw_chapters if item.get("volume") == volume_str]
        if not numbers:
            raise VolumeNotFoundError(self._slug_url, volume=volume_str)

        chapters = []
        for number in numbers:
            branch_id = self._resolve_branch_id(volume_str, number, raw_chapters)
            chapters.append(await self._fetch_chapter(volume_str, number, branch_id))
        return Volume(number=volume_str, chapters=chapters)

    async def _get_title(self, *, refresh: bool = False) -> dict[str, Any]:
        key = f"title:{self._slug_url}:{','.join(sorted(_INFO_FIELDS))}"
        if not refresh:
            cached = self._cache.get(key)
            if cached is not None:
                self._reporter.log(f"[cache] title metadata for {self._slug_url}")
                return cached  # type: ignore[no-any-return]
        self._reporter.log(f"[api] fetching title metadata for {self._slug_url}")
        data = await self._client.get_title(self._slug_url, fields=_INFO_FIELDS)
        self._cache.set(key, data)
        return data

    async def _get_chapters(self, *, refresh: bool = False) -> list[dict[str, Any]]:
        key = f"chapters:{self._slug_url}"
        if not refresh:
            cached = self._cache.get(key)
            if cached is not None:
                self._reporter.log(f"[cache] chapter list for {self._slug_url}")
                return cached  # type: ignore[no-any-return]
        self._reporter.log(f"[api] fetching chapter list for {self._slug_url}")
        data = await self._client.get_chapters(self._slug_url)
        self._cache.set(key, data)
        return data

    async def _fetch_chapter(
        self, volume_str: str, number: str, branch_id: int | None, *, refresh: bool = False
    ) -> Chapter:
        key = f"chapter:{self._slug_url}:{volume_str}:{number}:{branch_id}"
        if not refresh:
            cached = self._cache.get(key)
            if cached is not None:
                self._reporter.log(f"[cache] chapter {volume_str}/{number}")
                return Chapter.model_validate(cached)
        self._reporter.log(f"[api] fetching chapter {volume_str}/{number}")
        data = await self._client.get_chapter(
            self._slug_url, number=number, volume=volume_str, branch_id=branch_id
        )
        self._cache.set(key, data)
        return Chapter.model_validate(data)

    async def _fetch_chapter_riding_out_rate_limits(
        self,
        volume_str: str,
        number: str,
        branch_id: int | None,
        *,
        max_rate_limit_retries: int,
    ) -> Chapter:
        """Fetch one chapter for a bulk download, retrying past ``ApiClient``'s own budget.

        ``ApiClient._get()`` already retries a 429 a few times with its own backoff, tuned
        for a single request (see docs/api-notes.md) — not enough to ride out sustained rate
        limiting partway through a long sequential download. This adds a second, coarser
        retry layer on top: on a ``RateLimitError`` that already survived ``ApiClient``'s own
        retries, wait (honoring ``Retry-After`` if given, otherwise capped exponential
        backoff) and try again, up to ``max_rate_limit_retries`` times, before finally letting
        the error propagate to the caller (``download_title()``, which turns it into
        ``DownloadTitleInterruptedError`` carrying whatever was already downloaded).
        """
        attempt = 0
        while True:
            try:
                return await self._fetch_chapter(volume_str, number, branch_id)
            except RateLimitError as exc:
                if attempt >= max_rate_limit_retries:
                    raise
                delay = exc.retry_after
                if delay is None:
                    delay = min(
                        _RATE_LIMIT_RETRY_BASE_DELAY * (2**attempt), _RATE_LIMIT_RETRY_MAX_DELAY
                    )
                self._reporter.log(
                    f"[rate-limit] chapter {volume_str}/{number}: retrying in {delay:g}s "
                    f"(attempt {attempt + 1}/{max_rate_limit_retries})"
                )
                await asyncio.sleep(delay)
                attempt += 1

    def _resolve_branch_id(
        self, volume_str: str, number: str, raw_chapters: list[dict[str, Any]]
    ) -> int | None:
        item = _find_raw_chapter(raw_chapters, volume_str, number)
        if item is None:
            return None  # Let the chapter fetch itself raise ChapterNotFoundError.

        branches = item.get("branches") or []
        if len(branches) <= 1:
            return None

        raise MultipleTranslationsError(
            self._slug_url,
            volume=volume_str,
            number=number,
            branches=[ChapterBranch.model_validate(branch) for branch in branches],
        )


def _group_into_volumes(chapters: list[Chapter]) -> list[Volume]:
    """Group a flat, API-ordered chapter list into volumes, preserving that order."""
    grouped: dict[str, list[Chapter]] = {}
    for chapter in chapters:
        grouped.setdefault(chapter.volume, []).append(chapter)
    return [Volume(number=number, chapters=items) for number, items in grouped.items()]


def _resolve_bulk_branch_id(
    branches: list[dict[str, Any]], *, branch_id: int | None, translation_index: int | None
) -> tuple[bool, int | None]:
    """Resolve which branch_id to request for one ambiguous chapter in ``download_title()``.

    Returns ``(True, branch_id)`` if resolved, ``(False, None)`` if ``branch_id``/
    ``translation_index`` doesn't identify one of this chapter's branches.
    """
    if branch_id is not None:
        for branch in branches:
            if branch.get("branch_id") == branch_id:
                return True, branch_id
        return False, None
    if translation_index is not None and 0 <= translation_index < len(branches):
        return True, branches[translation_index].get("branch_id")
    return False, None


def _find_raw_chapter(
    raw_chapters: list[dict[str, Any]], volume_str: str, number: str
) -> dict[str, Any] | None:
    """Find a chapter-list entry by volume/number, or ``None`` if there isn't one."""
    return next(
        (
            item
            for item in raw_chapters
            if item.get("volume") == volume_str and item.get("number") == number
        ),
        None,
    )

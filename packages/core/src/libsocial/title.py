"""One title on one site: the ``TitleClient`` base class site packages build their facade on."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from pathlib import Path
from types import TracebackType
from typing import Any, ClassVar, Generic, NamedTuple, Self, TypeVar

from libsocial.cache import DEFAULT_CACHE_DIR, DiskCache
from libsocial.client import ApiClient
from libsocial.console import Reporter, Verbosity
from libsocial.exceptions import (
    AmbiguousChapter,
    ChapterNotFoundError,
    DownloadTitleInterruptedError,
    LibSocialError,
    MultipleTitleTranslationsError,
    MultipleTranslationsError,
    RateLimitError,
    VolumeNotFoundError,
)
from libsocial.models import ChapterBranch, ChapterT, TitleT, Volume
from libsocial.numbering import parse_slug_url
from libsocial.site import Site

DEFAULT_RATE_LIMIT_RETRIES = 6
"""Default ``download_title(max_rate_limit_retries=...)`` — see docs/api-notes.md."""

_RATE_LIMIT_RETRY_BASE_DELAY = 5.0
"""Base delay, in seconds, for download_title()'s bulk rate-limit backoff (doubled per
attempt, capped at _RATE_LIMIT_RETRY_MAX_DELAY) — used when the API's 429 doesn't send a
Retry-After header."""

_RATE_LIMIT_RETRY_MAX_DELAY = 60.0

VolumeT = TypeVar("VolumeT", bound=Volume[Any])


class PlannedChapter(NamedTuple):
    """A chapter a bulk operation will fetch, with the translation to fetch it in.

    Attributes:
        volume: The chapter's volume number.
        number: The chapter number.
        branch_id: The branch to request, or ``None`` to let the API pick — only for
            chapters with a single translation, where there's nothing to pick between.
    """

    volume: str
    number: str
    branch_id: int | None


class TitleClient(Generic[TitleT, ChapterT, VolumeT]):
    """One title on one lib.social site: metadata, chapters, translations, bulk download.

    Not used directly: a site package subclasses it, setting the class attributes below —
    which site it talks to, and which models a title, a chapter (with the site's own
    content fields) and a volume are validated as — and adds whatever is specific to the
    site's content (export, size estimates, ...).

    Example:
        ```python
        class RanobeLib(TitleClient[Title, Chapter, Volume]):
            site = Site(id=3, origin="https://ranobelib.me")
            title_model = Title
            chapter_model = Chapter
            volume_model = Volume

        async with RanobeLib("https://ranobelib.me/ru/book/6712--high-school-dxd-novel") as lib:
            info = await lib.get_info()
        ```

    Attributes:
        site: The site the title is on. Set by the subclass.
        title_model: The model ``get_info()`` returns. Set by the subclass.
        chapter_model: The model chapters are validated as — both table-of-contents entries
            and fetched chapters, so its content fields must be optional. Set by the
            subclass.
        volume_model: The model chapters are grouped into, ``Volume[chapter_model]`` or a
            subclass of it. Set by the subclass.
        default_cache_dir: ``cache_dir`` used when none is passed.
        info_fields: Extra ``fields[]`` ``get_info()`` requests on top of the API's default
            response (see docs/api-notes.md for what each adds).
    """

    site: Site
    title_model: type[TitleT]
    chapter_model: type[ChapterT]
    volume_model: type[VolumeT]
    default_cache_dir: Path = DEFAULT_CACHE_DIR
    info_fields: ClassVar[tuple[str, ...]] = (
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
    )

    def __init__(
        self,
        url: str,
        *,
        cache_dir: str | Path | None = None,
        cache_ttl: float | None = None,
        verbosity: Verbosity = False,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        """Initialize the client for a title.

        Args:
            url: The title's URL on the site, or a bare ``{id}--{slug}`` identifier.
            cache_dir: Where to cache raw API responses (title metadata, chapter list,
                chapter content) on disk, so a repeated export or downloading newly added
                chapters doesn't re-fetch data already on hand. Defaults to
                ``default_cache_dir``.
            cache_ttl: Seconds after which a cached response is treated as stale and
                re-fetched. ``None`` (the default) means cached responses never expire on
                their own — see ``refresh=True`` on individual methods to force one anyway.
            verbosity: Console output level. ``False`` (default): silent. ``"progress_only"``:
                progress bars for bulk operations (``download_title()``, ...). ``"full"``:
                the same progress bars, plus a line logged for every title/chapter-list/
                chapter fetch, noting whether it was served from the disk cache or the API.
            headers: Extra HTTP headers merged over the SDK's defaults (browser-like
                ``Origin``/``Referer``/``User-Agent``, see docs/api-notes.md, section "WAF
                403") — a key given here replaces the default one, matched
                case-insensitively. Meant for when the site's edge protection changes which
                requests it lets through (``AccessBlockedError``): send what it now expects
                without waiting for an SDK release. ``None`` (the default) sends the
                defaults as-is.
        """
        self._slug_url = parse_slug_url(url)
        self._headers = dict(headers) if headers is not None else None
        self._client = ApiClient(self.site, headers=self._headers)
        self._cache = DiskCache(
            cache_dir if cache_dir is not None else self.default_cache_dir, ttl=cache_ttl
        )
        self._reporter = Reporter(verbosity)

    @property
    def slug_url(self) -> str:
        """The title's ``{id}--{slug}`` identifier."""
        return self._slug_url

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

    async def get_info(self, *, refresh: bool = False) -> TitleT:
        """Fetch title metadata: names, cover, summary, genres, tags, authors, teams.

        Args:
            refresh: Bypass the disk cache and re-fetch from the API even if a cached
                response is on hand.
        """
        data = await self._get_title(refresh=refresh)
        return self.title_model.model_validate(data)

    async def get_table_of_contents(self, *, refresh: bool = False) -> list[VolumeT]:
        """Fetch the title's volumes and chapter names/numbers, without chapter content.

        Args:
            refresh: Bypass the disk cache and re-fetch from the API even if a cached
                response is on hand — needed to pick up newly published chapters, since
                otherwise the cached chapter list would keep being reused.
        """
        raw_chapters = await self._get_chapters(refresh=refresh)
        chapters = [self.chapter_model.model_validate(item) for item in raw_chapters]
        return self._group_into_volumes(chapters)

    async def get_chapter(
        self,
        volume: int,
        number: str,
        *,
        branch_id: int | None = None,
        refresh: bool = False,
    ) -> ChapterT:
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

    async def get_chapters(self, chapters: list[tuple[int, str]]) -> list[ChapterT]:
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

    async def get_volume(self, volume: int) -> VolumeT:
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

    async def get_volumes(self, volumes: list[int]) -> list[VolumeT]:
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
    ) -> list[VolumeT]:
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
        self._check_translation_selectors(branch_id, translation_index)
        raw_chapters = await self._get_chapters()
        planned, unresolved = self._plan_chapters(
            raw_chapters, branch_id=branch_id, translation_index=translation_index
        )
        if unresolved:
            raise MultipleTitleTranslationsError(self._slug_url, chapters=unresolved)

        chapters: list[ChapterT] = []
        total = len(planned)
        try:
            with self._reporter.progress(f"Downloading {self._slug_url}", total) as advance:
                for index, chapter in enumerate(planned):
                    chapters.append(
                        await self._fetch_chapter_riding_out_rate_limits(
                            chapter.volume,
                            chapter.number,
                            chapter.branch_id,
                            max_rate_limit_retries=max_rate_limit_retries,
                        )
                    )
                    advance()
                    if on_chapter is not None:
                        on_chapter(index + 1, total)
                    if chapter_delay and index < total - 1:
                        await asyncio.sleep(chapter_delay)
        except LibSocialError as exc:
            raise DownloadTitleInterruptedError(
                self._slug_url,
                volumes=self._group_into_volumes(chapters),
                completed=len(chapters),
                total=total,
            ) from exc
        return self._group_into_volumes(chapters)

    @staticmethod
    def _check_translation_selectors(branch_id: int | None, translation_index: int | None) -> None:
        """Raise ``ValueError`` if both ``branch_id`` and ``translation_index`` are given."""
        if branch_id is not None and translation_index is not None:
            raise ValueError("Pass at most one of branch_id or translation_index, not both.")

    def _plan_chapters(
        self,
        raw_chapters: list[dict[str, Any]],
        *,
        branch_id: int | None,
        translation_index: int | None,
    ) -> tuple[list[PlannedChapter], list[AmbiguousChapter]]:
        """Decide which translation to fetch for every chapter of a title-wide operation.

        Chapters with a single translation are planned as-is; those with more are resolved
        by ``branch_id`` or ``translation_index`` (see ``download_title()``) or, failing
        that, returned as unresolved — the caller decides whether that's an error
        (``download_title()``) or just a chapter to skip (a size estimate).

        Returns:
            The planned chapters, in the API's order, and the unresolved ones.

        Raises:
            ValueError: If both ``branch_id`` and ``translation_index`` are given — callers
                that fetch the chapter list first should check that before, with
                ``_check_translation_selectors()``, so a bad call doesn't cost a request.
        """
        self._check_translation_selectors(branch_id, translation_index)

        planned: list[PlannedChapter] = []
        unresolved: list[AmbiguousChapter] = []
        for item in raw_chapters:
            volume_str: str = item["volume"]
            number: str = item["number"]
            branches = item.get("branches") or []
            if len(branches) <= 1:
                planned.append(PlannedChapter(volume_str, number, None))
                continue

            resolved, selected = _resolve_bulk_branch_id(
                branches, branch_id=branch_id, translation_index=translation_index
            )
            if resolved:
                planned.append(PlannedChapter(volume_str, number, selected))
            else:
                unresolved.append(
                    AmbiguousChapter(
                        volume=volume_str,
                        number=number,
                        branches=[ChapterBranch.model_validate(branch) for branch in branches],
                    )
                )
        return planned, unresolved

    async def _build_volume(self, volume: int, raw_chapters: list[dict[str, Any]]) -> VolumeT:
        volume_str = str(volume)
        numbers = [item["number"] for item in raw_chapters if item.get("volume") == volume_str]
        if not numbers:
            raise VolumeNotFoundError(self._slug_url, volume=volume_str)

        chapters = []
        for number in numbers:
            branch_id = self._resolve_branch_id(volume_str, number, raw_chapters)
            chapters.append(await self._fetch_chapter(volume_str, number, branch_id))
        return self.volume_model(number=volume_str, chapters=chapters)

    def _group_into_volumes(self, chapters: list[ChapterT]) -> list[VolumeT]:
        """Group a flat, API-ordered chapter list into volumes, preserving that order."""
        grouped: dict[str, list[ChapterT]] = {}
        for chapter in chapters:
            grouped.setdefault(chapter.volume, []).append(chapter)
        return [
            self.volume_model(number=number, chapters=items) for number, items in grouped.items()
        ]

    def _cache_key(self, kind: str, *parts: object) -> str:
        """Disk-cache key for one response, scoped to the site.

        Every endpoint here answers per site (the ``Site-Id`` header), so clients for
        different sites sharing a ``cache_dir`` must not read each other's entries.
        """
        return ":".join([kind, str(self.site.id), self._slug_url, *map(str, parts)])

    async def _get_title(self, *, refresh: bool = False) -> dict[str, Any]:
        key = self._cache_key("title", ",".join(sorted(self.info_fields)))
        if not refresh:
            cached = self._cache.get(key)
            if cached is not None:
                self._reporter.log(f"[cache] title metadata for {self._slug_url}")
                return cached  # type: ignore[no-any-return]
        self._reporter.log(f"[api] fetching title metadata for {self._slug_url}")
        data = await self._client.get_title(self._slug_url, fields=list(self.info_fields))
        self._cache.set(key, data)
        return data

    async def _get_chapters(self, *, refresh: bool = False) -> list[dict[str, Any]]:
        key = self._cache_key("chapters")
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
    ) -> ChapterT:
        key = self._cache_key("chapter", volume_str, number, branch_id)
        if not refresh:
            cached = self._cache.get(key)
            if cached is not None:
                self._reporter.log(f"[cache] chapter {volume_str}/{number}")
                return self.chapter_model.model_validate(cached)
        self._reporter.log(f"[api] fetching chapter {volume_str}/{number}")
        data = await self._client.get_chapter(
            self._slug_url, number=number, volume=volume_str, branch_id=branch_id
        )
        self._cache.set(key, data)
        return self.chapter_model.model_validate(data)

    async def _fetch_chapter_riding_out_rate_limits(
        self,
        volume_str: str,
        number: str,
        branch_id: int | None,
        *,
        max_rate_limit_retries: int,
    ) -> ChapterT:
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


def _resolve_bulk_branch_id(
    branches: list[dict[str, Any]], *, branch_id: int | None, translation_index: int | None
) -> tuple[bool, int | None]:
    """Resolve which branch_id to request for one ambiguous chapter of a title-wide operation.

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

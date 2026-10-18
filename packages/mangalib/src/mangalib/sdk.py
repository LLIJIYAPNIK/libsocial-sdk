"""Public facade of the SDK: the ``MangaLib`` class.

Fetching a title, its chapters and translations is ``libsocial-core``'s
(``libsocial.TitleClient``); ``MangaLib`` points it at mangalib.me and its own models, and
adds what depends on a chapter being page images: the image servers, page downloads, sizes
and export.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, TypeVar

import httpx

from libsocial import TitleClient
from libsocial.console import Verbosity
from libsocial.exceptions import ChapterNotFoundError
from libsocial.title import DEFAULT_RATE_LIMIT_RETRIES, PlannedChapter
from mangalib import images
from mangalib._http import MANGALIB, image_headers
from mangalib.cache import DEFAULT_CACHE_DIR
from mangalib.client import ApiClient
from mangalib.exporters import EXPORTERS
from mangalib.images import DEFAULT_IMAGE_CONCURRENCY
from mangalib.models import Chapter, ChapterBranch, ImageServer, Page, Title, Volume

__all__ = ["DEFAULT_RATE_LIMIT_RETRIES", "DEFAULT_SAMPLE_SIZE", "MangaLib"]

DEFAULT_SAMPLE_SIZE = 5
"""Default number of chapters ``MangaLib.estimate_title_size()`` samples."""

_IMAGE_SERVERS_CACHE_KEY = "constants:imageServers"
"""Disk-cache key of the image server list. Not per site: the cached response covers the
whole network, and is filtered to mangalib.me on every read."""

_T = TypeVar("_T")


class MangaLib(TitleClient[Title, Chapter, Volume]):
    """Entry point for interacting with a single mangalib.me title.

    Closed chapters (paid, or in early access) can't be read without an account, which the
    SDK doesn't support: ``get_chapter()`` raises ``AuthRequiredError`` for one, while
    ``download_title()`` and ``estimate_title_size()`` leave out every translation the
    chapter list marks as closed (``ChapterBranch.is_open``) — a chapter with only closed
    ones is skipped, and ``translation_index`` counts the open translations only.

    Example:
        ```python
        async with MangaLib("https://mangalib.me/ru/manga/7965--chainsaw-man") as lib:
            chapter = await lib.get_chapter(volume=1, number="1", branch_id=4667)
            first_page = await lib.download_page(chapter.pages[0])
            await lib.export([chapter], fmt="cbz", path="chainsaw-man-1.cbz")
        ```
    """

    site = MANGALIB
    title_model = Title
    chapter_model = Chapter
    volume_model = Volume
    _client: ApiClient

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
            url: A mangalib.me title URL, or a bare ``{id}--{slug}`` identifier.
            cache_dir: Where to cache raw API responses (title metadata, chapter list,
                chapter pages, image servers) on disk. Page images themselves aren't
                cached. Defaults to ``.mangalib_cache`` in the current working directory.
            cache_ttl: Seconds after which a cached response is treated as stale and
                re-fetched. ``None`` (the default) means cached responses never expire on
                their own — see ``refresh=True`` on individual methods to force one anyway.
            verbosity: Console output level. ``False`` (default): silent. ``"progress_only"``:
                progress bars during ``download_title()``, ``export()`` and
                ``estimate_title_size()``. ``"full"``: the same, plus a line logged for every
                title/chapter-list/chapter fetch, noting whether it was served from the disk
                cache or the API, and for every closed chapter a whole-title download skips.
            headers: Extra HTTP headers merged over the SDK's defaults (browser-like
                ``Origin``/``Referer``/``User-Agent``, see docs/api-notes.md, section "WAF
                403") — a key given here replaces the default one, matched
                case-insensitively. Applied to every API request and to page image
                downloads. Meant for when the site's edge protection changes which requests
                it lets through (``AccessBlockedError``). ``None`` (the default) sends the
                defaults as-is.
        """
        super().__init__(
            url,
            cache_dir=cache_dir if cache_dir is not None else DEFAULT_CACHE_DIR,
            cache_ttl=cache_ttl,
            verbosity=verbosity,
            headers=headers,
        )
        self._image_client: httpx.AsyncClient | None = None
        self._image_fetcher: images.ImageFetcher | None = None
        self._image_servers: list[ImageServer] | None = None

    def _create_client(self, headers: Mapping[str, str] | None) -> ApiClient:
        return ApiClient(headers=headers)

    def _create_image_client(self) -> httpx.AsyncClient:
        """The HTTP client page images are downloaded with — separate from the API's: other
        hosts, no ``Site-Id``, ``Accept: image/*``."""
        return httpx.AsyncClient(headers=image_headers(self._headers), timeout=30.0)

    def _create_image_fetcher(self, client: httpx.AsyncClient) -> images.ImageFetcher:
        """The paced, retried fetcher page requests go through."""
        return images.ImageFetcher(client, request_delay=images.DEFAULT_IMAGE_REQUEST_DELAY)

    async def aclose(self) -> None:
        """Close the underlying HTTP clients."""
        await super().aclose()
        if self._image_client is not None:
            await self._image_client.aclose()

    # The base class returns list[libsocial.ChapterBranch]; this returns mangalib's subclass
    # of it (with restricted_view), which lists' invariance makes mypy reject as an override.
    async def get_translations(  # type: ignore[override]
        self, volume: int, number: str
    ) -> list[ChapterBranch]:
        """Fetch the available translations (branches) for a chapter.

        Each one says whether it's open to read without an account (``ChapterBranch.is_open``).

        Args:
            volume: The chapter's volume number.
            number: The chapter number.

        Raises:
            ChapterNotFoundError: If no chapter exists for this volume/number.
        """
        volume_str = str(volume)
        for item in await self._get_chapters():
            if item.get("volume") == volume_str and item.get("number") == number:
                return [ChapterBranch.model_validate(branch) for branch in item["branches"] or []]
        raise ChapterNotFoundError(self.slug_url, volume=volume_str, number=number)

    async def list_image_servers(self, *, refresh: bool = False) -> list[ImageServer]:
        """List the servers mangalib.me serves page images from.

        Not every one serves pages to a script: see ``download_page()`` for which are tried.

        Args:
            refresh: Bypass the disk cache and re-fetch from the API.
        """
        if self._image_servers is not None and not refresh:
            return self._image_servers
        data = None if refresh else self._cache.get(_IMAGE_SERVERS_CACHE_KEY)
        if data is None:
            data = await self._client.list_image_servers()
            self._cache.set(_IMAGE_SERVERS_CACHE_KEY, data)
        self._image_servers = [
            ImageServer.model_validate(item)
            for item in data
            if self.site.id in item.get("site_ids", []) and item.get("url")
        ]
        return self._image_servers

    async def download_page(self, page: Page, *, server: str | None = None) -> bytes:
        """Download one page image.

        Tries ``server`` first, if given, then ``images.DEFAULT_SERVER_ORDER`` (``compress``,
        ``download``, ``main``, ``secondary``). ``compress`` comes first because it's the one
        that served full-size pages when checked; ``main``/``secondary`` sit behind a
        DDoS-Guard check scripts don't pass (see docs/api-notes.md, "MangaLib"). Requests to
        an image host are paced across the process (``images.DEFAULT_IMAGE_REQUEST_DELAY``),
        and a 429, a 5xx or a network error is retried with backoff on the same server before
        moving on to the next one; a refusal (another 4xx, a response that isn't an image)
        moves on at once.

        Args:
            page: The page, from a fetched chapter's ``pages``.
            server: The ``ImageServer.id`` to try first (see ``list_image_servers()``).

        Returns:
            The image file's bytes, as the server sent them.

        Raises:
            ValueError: If ``server`` isn't one of ``list_image_servers()``.
            PageDownloadError: If no server served the image.
        """
        order = images.server_order(await self.list_image_servers(), server)
        return await self._fetcher().download(page, order)

    async def download_pages(
        self,
        chapter: Chapter,
        *,
        server: str | None = None,
        concurrency: int = DEFAULT_IMAGE_CONCURRENCY,
    ) -> list[bytes]:
        """Download every page image of a fetched chapter, in reading order.

        Each page as ``download_page()`` does it, up to ``concurrency`` at a time.

        Args:
            chapter: A chapter fetched with ``get_chapter()`` (or ``get_chapters()``,
                ``get_volume()``, ...): one from ``get_table_of_contents()`` has no pages.
            server: The ``ImageServer.id`` to try first — see ``download_page()``.
            concurrency: How many pages to download at once. The pacing per image host
                applies on top, so more than a few mostly adds waiting.

        Raises:
            ValueError: If ``server`` isn't one of ``list_image_servers()``, or
                ``concurrency`` is less than 1.
            PageDownloadError: If a page couldn't be downloaded from any server; the other
                downloads still in flight are cancelled.
        """
        order = await self._server_order(server, concurrency)
        return await self._download_all(chapter.pages, order, concurrency)

    async def chapter_size(
        self,
        chapter: Chapter,
        *,
        server: str | None = None,
        concurrency: int = DEFAULT_IMAGE_CONCURRENCY,
    ) -> int:
        """The exact size in bytes of a fetched chapter's page images, without downloading them.

        One ``HEAD`` request per page: the image servers answer it with the file's exact
        ``Content-Length`` (see docs/api-notes.md, "MangaLib"), so this costs requests, not
        image traffic. Servers are tried, paced and retried as in ``download_page()``.

        Args:
            chapter: A chapter fetched with ``get_chapter()`` (or another fetching method).
            server: The ``ImageServer.id`` to try first — see ``download_page()``.
            concurrency: How many pages to ask about at once.

        Raises:
            ValueError: If ``chapter`` has no pages (not fetched), ``server`` isn't one of
                ``list_image_servers()``, or ``concurrency`` is less than 1.
            PageDownloadError: If no server gave a page's size.
        """
        if not chapter.pages:
            raise ValueError(
                f"Chapter {chapter.volume}/{chapter.number} has no pages to size — fetch it "
                "with get_chapter() first; get_table_of_contents() doesn't include pages."
            )
        order = await self._server_order(server, concurrency)
        fetcher = self._fetcher()
        sizes = await _gather_bounded(
            [_bind(fetcher.size, page, order) for page in chapter.pages], concurrency
        )
        return sum(sizes)

    async def volume_size(
        self,
        volume: Volume,
        *,
        server: str | None = None,
        concurrency: int = DEFAULT_IMAGE_CONCURRENCY,
    ) -> int:
        """The exact size in bytes of a fetched volume's page images — ``chapter_size()`` summed.

        Args:
            volume: A volume fetched with ``get_volume()``/``get_volumes()``/
                ``download_title()``.
            server: The ``ImageServer.id`` to try first — see ``download_page()``.
            concurrency: How many pages to ask about at once.

        Raises:
            ValueError: See ``chapter_size()``.
            PageDownloadError: If no server gave a page's size.
        """
        total = 0
        for chapter in volume.chapters:
            total += await self.chapter_size(chapter, server=server, concurrency=concurrency)
        return total

    async def estimate_title_size(
        self,
        *,
        sample_size: int = DEFAULT_SAMPLE_SIZE,
        branch_id: int | None = None,
        translation_index: int | None = None,
        server: str | None = None,
        concurrency: int = DEFAULT_IMAGE_CONCURRENCY,
    ) -> int:
        """Estimate the whole title's page images in bytes, from a sample of its chapters.

        Fetches the chapter list, then up to ``sample_size`` chapters spread evenly across
        the title (their page lists, cached like any chapter fetch), sizes their pages
        exactly with ``chapter_size()`` — ``HEAD`` requests, no image traffic — and
        extrapolates the sample's average across every chapter ``download_title()`` would
        download. The chapter list has no page counts, so the sample is what both the page
        count and the page weight are estimated from.

        Args:
            sample_size: How many chapters to sample — clamped to how many there are.
            branch_id: Same as ``download_title(branch_id=...)``. Mutually exclusive with
                ``translation_index``.
            translation_index: Same as ``download_title(translation_index=...)``.
            server: The ``ImageServer.id`` to try first — see ``download_page()``.
            concurrency: How many pages to ask about at once.

        Returns:
            The estimated size in bytes, or ``0`` if the title has no chapter with an open
            translation that ``branch_id``/``translation_index`` resolves.

        Raises:
            ValueError: If both ``branch_id`` and ``translation_index`` are given, or if
                ``sample_size`` or ``concurrency`` is less than 1.

        Note:
            Chapters with more than one translation that ``branch_id``/``translation_index``
            doesn't resolve are left out of the sample rather than raising, like closed
            chapters: the estimate needs *a* chapter of this title to measure, not a
            particular translation.
        """
        self._check_translation_selectors(branch_id, translation_index)
        if sample_size < 1:
            raise ValueError(f"sample_size must be at least 1, got {sample_size}.")
        _check_concurrency(concurrency)

        planned, _ = self._plan_chapters(
            await self._get_chapters(), branch_id=branch_id, translation_index=translation_index
        )
        if not planned:
            return 0
        size = min(sample_size, len(planned))
        step = len(planned) / size
        sample = [planned[int(index * step)] for index in range(size)]

        total = 0
        with self._reporter.progress(f"Sampling {self.slug_url}", len(sample)) as advance:
            for volume_str, number, selected_branch_id in sample:
                chapter = await self._fetch_chapter(volume_str, number, selected_branch_id)
                if chapter.pages:
                    total += await self.chapter_size(
                        chapter, server=server, concurrency=concurrency
                    )
                advance()
        return round(total / len(sample) * len(planned))

    async def export(
        self,
        chapters: Chapter | Volume | Sequence[Chapter | Volume],
        *,
        fmt: str,
        path: str | Path,
        server: str | None = None,
        concurrency: int = DEFAULT_IMAGE_CONCURRENCY,
        on_chapter: Callable[[int, int], None] | None = None,
    ) -> Path:
        """Export fetched chapters to one file, downloading their page images as it goes.

        One chapter, several, a volume, several, or a whole title — ``download_title()``'s
        result — all go in: volumes are expanded into their chapters, in order. Pages are
        downloaded chapter by chapter (as ``download_pages()`` does it) and written into the
        file, which only appears at ``path`` once complete.

        Args:
            chapters: Fetched chapters and/or volumes, in the order they should appear.
            fmt: Export format — a key of ``mangalib.exporters.EXPORTERS``: ``"cbz"``, and
                ``"pdf"`` when the ``pdf`` extra (img2pdf) is installed.
            path: Where to write the exported file.
            server: The ``ImageServer.id`` to try first — see ``download_page()``.
            concurrency: How many pages to download at once.
            on_chapter: Called with ``(completed, total)`` after each chapter is written —
                the same progress hook as ``download_title(on_chapter=...)``, independent of
                ``verbosity``.

        Raises:
            ValueError: If ``fmt`` isn't a registered format, there are no chapters, one of
                them has no pages (not fetched), ``server`` isn't one of
                ``list_image_servers()``, or ``concurrency`` is less than 1 — all checked
                before anything is downloaded.
            PageDownloadError: If a page couldn't be downloaded from any server. Nothing is
                written to ``path`` then.
        """
        exporter_cls = EXPORTERS.get(fmt)
        if exporter_cls is None:
            available = ", ".join(sorted(EXPORTERS)) or "(none registered)"
            raise ValueError(f"Unknown export format {fmt!r}. Available: {available}")
        flat = _flatten(chapters)
        if not flat:
            raise ValueError("Nothing to export: no chapters given.")
        for chapter in flat:
            if not chapter.pages:
                raise ValueError(
                    f"Chapter {chapter.volume}/{chapter.number} has no pages — fetch it with "
                    "get_chapter() (or download_title(), ...) first; get_table_of_contents() "
                    "doesn't include pages."
                )
        order = await self._server_order(server, concurrency)
        title = await self.get_info()

        async def fetch_pages(chapter: Chapter) -> list[bytes]:
            return await self._download_all(chapter.pages, order, concurrency)

        total = len(flat)
        completed = 0
        with self._reporter.progress(f"Exporting to {fmt}", total) as advance:

            def chapter_done() -> None:
                nonlocal completed
                completed += 1
                advance()
                if on_chapter is not None:
                    on_chapter(completed, total)

            return await exporter_cls().export(
                title, flat, Path(path), fetch_pages=fetch_pages, on_chapter=chapter_done
            )

    def _plan_chapters(
        self,
        raw_chapters: list[dict[str, Any]],
        *,
        branch_id: int | None,
        translation_index: int | None,
    ) -> tuple[list[PlannedChapter], list[dict[str, Any]]]:
        """The core's plan, over open translations only (see the class docstring).

        A chapter whose only open translation is one of several is planned with that one's
        ``branch_id`` rather than none: without it the API picks its own default, which may
        be a closed one.
        """
        open_chapters: list[dict[str, Any]] = []
        pinned: dict[tuple[str, str], int | None] = {}
        for item in raw_chapters:
            branches = item.get("branches") or []
            open_branches = [branch for branch in branches if _branch_is_open(branch)]
            if branches and not open_branches:
                self._reporter.log(
                    f"[skip] chapter {item['volume']}/{item['number']}: closed "
                    "(paid or early access)"
                )
                continue
            if len(open_branches) < len(branches):
                item = {**item, "branches": open_branches}
                if len(open_branches) == 1:
                    pinned[(item["volume"], item["number"])] = open_branches[0].get("branch_id")
            open_chapters.append(item)

        planned, unresolved = super()._plan_chapters(
            open_chapters, branch_id=branch_id, translation_index=translation_index
        )
        return [
            chapter._replace(branch_id=pinned[(chapter.volume, chapter.number)])
            if chapter.branch_id is None and (chapter.volume, chapter.number) in pinned
            else chapter
            for chapter in planned
        ], unresolved

    async def _server_order(self, server: str | None, concurrency: int) -> list[ImageServer]:
        """Check ``concurrency`` and resolve the servers to try, before any page request."""
        _check_concurrency(concurrency)
        return images.server_order(await self.list_image_servers(), server)

    async def _download_all(
        self, pages: list[Page], order: list[ImageServer], concurrency: int
    ) -> list[bytes]:
        fetcher = self._fetcher()
        return await _gather_bounded(
            [_bind(fetcher.download, page, order) for page in pages], concurrency
        )

    def _fetcher(self) -> images.ImageFetcher:
        if self._image_fetcher is None:
            self._image_client = self._create_image_client()
            self._image_fetcher = self._create_image_fetcher(self._image_client)
        return self._image_fetcher


def _branch_is_open(branch: dict[str, Any]) -> bool:
    """Whether a raw chapter-list branch can be read without an account."""
    restricted_view = branch.get("restricted_view")
    return not isinstance(restricted_view, dict) or bool(restricted_view.get("is_open", True))


def _check_concurrency(concurrency: int) -> None:
    if concurrency < 1:
        raise ValueError(f"concurrency must be at least 1, got {concurrency}.")


def _flatten(chapters: Chapter | Volume | Sequence[Chapter | Volume]) -> list[Chapter]:
    items: Sequence[Chapter | Volume] = (
        [chapters] if isinstance(chapters, Chapter | Volume) else chapters
    )
    flat: list[Chapter] = []
    for item in items:
        flat.extend(item.chapters if isinstance(item, Volume) else [item])
    return flat


def _bind(
    call: Callable[[Page, list[ImageServer]], Awaitable[_T]],
    page: Page,
    order: list[ImageServer],
) -> Callable[[], Awaitable[_T]]:
    return lambda: call(page, order)


async def _gather_bounded(calls: list[Callable[[], Awaitable[_T]]], concurrency: int) -> list[_T]:
    """Run ``calls`` with at most ``concurrency`` at once; results in the calls' order.

    The first failure cancels the rest and is raised as itself, not inside an
    ``ExceptionGroup``.
    """
    semaphore = asyncio.Semaphore(concurrency)

    async def bounded(call: Callable[[], Awaitable[_T]]) -> _T:
        async with semaphore:
            return await call()

    try:
        async with asyncio.TaskGroup() as group:
            tasks = [group.create_task(bounded(call)) for call in calls]
    except* Exception as errors:
        raise errors.exceptions[0] from None
    return [task.result() for task in tasks]

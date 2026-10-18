"""Public facade of the SDK: the ``MangaLib`` class.

Fetching a title, its chapters and translations is ``libsocial-core``'s
(``libsocial.TitleClient``); ``MangaLib`` points it at mangalib.me and its own models, and
adds what depends on a chapter being page images: the image servers and page downloads.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from pathlib import Path

import httpx

from libsocial import TitleClient
from libsocial.console import Verbosity
from libsocial.exceptions import ChapterNotFoundError
from libsocial.title import DEFAULT_RATE_LIMIT_RETRIES
from mangalib import images
from mangalib._http import MANGALIB, image_headers
from mangalib.cache import DEFAULT_CACHE_DIR
from mangalib.client import ApiClient
from mangalib.models import Chapter, ChapterBranch, ImageServer, Page, Title, Volume

__all__ = ["DEFAULT_RATE_LIMIT_RETRIES", "MangaLib"]

_IMAGE_CONCURRENCY = 5
"""Page images downloaded at once by ``download_pages()`` — the same conservative value as
``ApiClient``'s ``max_concurrency``: the image servers' limits are unknown."""

_IMAGE_SERVERS_CACHE_KEY = "constants:imageServers"
"""Disk-cache key of the image server list. Not per site: the cached response covers the
whole network, and is filtered to mangalib.me on every read."""


class MangaLib(TitleClient[Title, Chapter, Volume]):
    """Entry point for interacting with a single mangalib.me title.

    Example:
        ```python
        async with MangaLib("https://mangalib.me/ru/manga/7965--chainsaw-man") as lib:
            chapter = await lib.get_chapter(volume=1, number="1", branch_id=4667)
            first_page = await lib.download_page(chapter.pages[0])
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
                progress bars during ``download_title()``. ``"full"``: the same, plus a line
                logged for every title/chapter-list/chapter fetch, noting whether it was
                served from the disk cache or the API.
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
        self._image_servers: list[ImageServer] | None = None

    def _create_client(self, headers: Mapping[str, str] | None) -> ApiClient:
        return ApiClient(headers=headers)

    def _create_image_client(self) -> httpx.AsyncClient:
        """The HTTP client page images are downloaded with — separate from the API's: other
        hosts, no ``Site-Id``, ``Accept: image/*``."""
        return httpx.AsyncClient(headers=image_headers(self._headers), timeout=30.0)

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
        ``download``, ``main``, ``secondary``), moving on to the next on a network error,
        an HTTP error or a response that isn't an image. ``compress`` comes first because
        it's the one that served full-size pages when checked; ``main``/``secondary`` sit
        behind a DDoS-Guard check scripts don't pass (see docs/api-notes.md, "MangaLib").

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
        if self._image_client is None:
            self._image_client = self._create_image_client()
        return await images.download_page(self._image_client, page, order)

    async def download_pages(self, chapter: Chapter, *, server: str | None = None) -> list[bytes]:
        """Download every page image of a fetched chapter, in reading order.

        Up to five pages are downloaded at once, each with ``download_page()``'s server
        fallback.

        Args:
            chapter: A chapter fetched with ``get_chapter()`` (or ``get_chapters()``,
                ``get_volume()``, ...): one from ``get_table_of_contents()`` has no pages.
            server: The ``ImageServer.id`` to try first — see ``download_page()``.

        Raises:
            ValueError: If ``server`` isn't one of ``list_image_servers()``.
            PageDownloadError: If a page couldn't be downloaded from any server; the other
                downloads still in flight are cancelled.
        """
        semaphore = asyncio.Semaphore(_IMAGE_CONCURRENCY)

        async def fetch(page: Page) -> bytes:
            async with semaphore:
                return await self.download_page(page, server=server)

        # Resolve the servers once, before starting the downloads, so a bad ``server``
        # raises ValueError itself rather than inside a task group's ExceptionGroup.
        images.server_order(await self.list_image_servers(), server)
        try:
            async with asyncio.TaskGroup() as group:
                tasks = [group.create_task(fetch(page)) for page in chapter.pages]
        except* Exception as errors:
            raise errors.exceptions[0] from None
        return [task.result() for task in tasks]

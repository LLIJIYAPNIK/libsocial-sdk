"""Illustration handling shared between exporters that embed images (epub, pdf).

Not part of the public Exporter protocol. Chapter content's ``<img>`` tags carry absolute
URLs (see docs/api-notes.md); embedding them means downloading the bytes and rewriting each
``src`` to wherever the target format keeps embedded resources (a local file inside an epub
zip, a ``data:`` URI inline in an HTML string for pdf) — everything up to that last,
format-specific rewrite step is identical between the two, hence living here once.
"""

from __future__ import annotations

import asyncio
import html
from collections.abc import Callable
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from ranobelib.models import Cover

_VOID_TAGS = frozenset({"br", "hr", "img"})

_MEDIA_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
}
_DEFAULT_EXTENSION = ".jpg"

IMAGE_CONCURRENCY = 5
"""Same conservative default as ApiClient's max_concurrency (see client.py) — these are a
different host (site/CDN uploads, not api.cdnlibs.org) with unknown rate limits of their
own, so this doesn't reuse ApiClient's own semaphore/retry machinery, just a plain cap.
A failed download is skipped rather than retried: embedding is best-effort, one broken
image shouldn't fail the whole export."""


class _ImageUrlCollector(HTMLParser):
    """Collects every ``<img src="...">`` URL referenced in a chapter-content HTML fragment."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.urls: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "img":
            src = dict(attrs).get("src")
            if src:
                self.urls.append(src)

    handle_startendtag = handle_starttag


def extract_image_urls(html_fragment: str) -> list[str]:
    """List the ``<img src="...">`` URLs referenced in a chapter-content HTML fragment."""
    collector = _ImageUrlCollector()
    collector.feed(html_fragment)
    return collector.urls


class _ImageSrcRewriter(HTMLParser):
    """Re-emits chapter-content HTML with each ``<img src="...">`` passed through a function.

    Rebuilds the markup tag-by-tag (rather than a targeted regex substitution) for the same
    reason the txt/fb2 exporters use ``HTMLParser`` over regex: HTML-string-format chapters
    pass the site's own markup through as-is (see docs/api-notes.md). Everything other than
    ``img`` passes through unchanged; both consumers (ebooklib's ``lxml.html``-based parser
    for epub, WeasyPrint's own HTML parser for pdf) are lenient enough not to need strict
    XHTML here.

    ``replace`` gets each ``<img>``'s ``src`` (``""`` if it has none) and returns the new
    value, or ``None`` to drop that ``<img>`` entirely.
    """

    def __init__(self, replace: Callable[[str], str | None]) -> None:
        super().__init__(convert_charrefs=True)
        self._replace = replace
        self._output: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._emit(tag, attrs, self_closing=tag in _VOID_TAGS)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._emit(tag, attrs, self_closing=True)

    def _emit(self, tag: str, attrs: list[tuple[str, str | None]], *, self_closing: bool) -> None:
        if tag == "img":
            new_src = self._replace(dict(attrs).get("src") or "")
            if new_src is None:
                return
            attrs = [(name, new_src if name == "src" else value) for name, value in attrs]

        parts = [f"<{tag}"]
        for name, value in attrs:
            if value is None:
                parts.append(f" {name}")
            else:
                parts.append(f' {name}="{html.escape(value, quote=True)}"')
        parts.append(" />" if self_closing else ">")
        self._output.append("".join(parts))

    def handle_endtag(self, tag: str) -> None:
        if tag not in _VOID_TAGS:
            self._output.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        self._output.append(html.escape(data))

    def get_html(self) -> str:
        return "".join(self._output)


def replace_image_srcs(html_fragment: str, replace: Callable[[str], str | None]) -> str:
    """Pass every ``<img src="...">`` in ``html_fragment`` through ``replace``.

    ``replace`` returns the new ``src``, or ``None`` to drop that ``<img>``.
    """
    rewriter = _ImageSrcRewriter(replace)
    rewriter.feed(html_fragment)
    return rewriter.get_html()


def rewrite_image_srcs(html_fragment: str, url_to_local: dict[str, str]) -> str:
    """Rewrite ``<img src="...">`` URLs in ``html_fragment`` per ``url_to_local``.

    An ``<img>`` whose URL isn't in ``url_to_local`` (download failed or was never
    attempted) is dropped entirely rather than kept pointing at the original external URL —
    a dangling absolute-URL reference isn't a self-contained embed, just a broken-looking
    image in most consumers, so "not embedded" reads as "not present" instead.
    """
    return replace_image_srcs(html_fragment, url_to_local.get)


def pick_cover_url(cover: Cover) -> str | None:
    """The best available cover URL, preferring the largest: default, then md, then thumbnail."""
    return cover.default or cover.md or cover.thumbnail


def guess_extension(url: str) -> str:
    """A file extension for ``url``, from its path, falling back to a default."""
    suffix = Path(urlsplit(url).path).suffix.lower()
    return suffix if suffix in _MEDIA_TYPES else _DEFAULT_EXTENSION


def media_type_for(extension: str) -> str:
    """The MIME media type for a file extension from ``guess_extension``."""
    return _MEDIA_TYPES.get(extension, _MEDIA_TYPES[_DEFAULT_EXTENSION])


async def _try_download(
    client: httpx.AsyncClient, semaphore: asyncio.Semaphore, url: str
) -> bytes | None:
    async with semaphore:
        try:
            response = await client.get(url)
            response.raise_for_status()
        except httpx.HTTPError:
            return None
    return response.content


async def download_images(
    client: httpx.AsyncClient, urls: list[str], *, concurrency: int = IMAGE_CONCURRENCY
) -> dict[str, bytes]:
    """Download each of ``urls`` concurrently, skipping (not retrying) any that fail.

    Args:
        client: The client to download with.
        urls: URLs to fetch. Not deduplicated — that's the caller's job (chapters often
            share images).
        concurrency: Maximum simultaneous downloads.

    Returns:
        A mapping from URL to its downloaded bytes, containing only the URLs that
        succeeded — failed URLs are simply absent, not mapped to ``None``.
    """
    semaphore = asyncio.Semaphore(concurrency)
    results = await asyncio.gather(*(_try_download(client, semaphore, url) for url in urls))
    return {url: data for url, data in zip(urls, results, strict=True) if data is not None}

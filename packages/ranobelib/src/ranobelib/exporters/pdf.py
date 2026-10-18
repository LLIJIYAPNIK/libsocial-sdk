"""PDF exporter (WeasyPrint, reuses the HTML template from the epub exporter)."""

from __future__ import annotations

import asyncio
import base64
import html
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import ClassVar

import httpx

from ranobelib._http import browser_headers
from ranobelib.exporters import register
from ranobelib.exporters._illustrations import (
    download_images,
    extract_image_urls,
    guess_extension,
    media_type_for,
    pick_cover_url,
    rewrite_image_srcs,
)
from ranobelib.exporters._shared import chapter_body_html, chapter_heading
from ranobelib.models import Chapter, Title

try:
    import weasyprint
except (ImportError, OSError):
    weasyprint = None
    # WeasyPrint's native dependencies (Pango/cairo/gobject, normally provided by a GTK3
    # runtime on Windows/macOS; readily apt-installable on Linux) aren't available on this
    # system -- see docs/api-notes.md's "PDF export" notes. The pip package itself installs
    # fine everywhere; only this native check at weasyprint's own import time can fail. When
    # it does, "pdf" simply isn't registered as an export format below -- RanobeLib.export(
    # fmt="pdf") then raises the same ValueError it would for any other unknown format,
    # rather than crashing `import ranobelib` itself.

_PAGE_CSS = """
@page { margin: 2cm 1.5cm; }
body { font-family: serif; line-height: 1.4; }
.titlepage { text-align: center; break-after: page; }
.titlepage img { max-width: 60%; max-height: 70vh; }
.chapter { break-before: page; }
.chapter:first-of-type { break-before: avoid; }
img { max-width: 100%; }
"""


def _data_uri(media_type: str, data: bytes) -> str:
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{media_type};base64,{encoded}"


def _title_page_html(title: Title, cover_data_uri: str | None) -> str:
    cover_html = f'<img src="{cover_data_uri}" />' if cover_data_uri else ""
    authors_html = ""
    if title.authors:
        names = ", ".join(html.escape(author.name) for author in title.authors)
        authors_html = f"<p>{names}</p>"
    heading = html.escape(title.name)
    return f'<section class="titlepage">{cover_html}<h1>{heading}</h1>{authors_html}</section>'


def _chapter_html(chapter: Chapter, url_to_data_uri: dict[str, str]) -> str:
    heading = html.escape(chapter_heading(chapter))
    body = rewrite_image_srcs(chapter_body_html(chapter), url_to_data_uri)
    return f'<section class="chapter"><h1>{heading}</h1>{body}</section>'


if weasyprint is not None:

    def _render_pdf(document: str, output_path: Path) -> None:
        weasyprint.HTML(string=document).write_pdf(str(output_path))

    @register
    class PdfExporter:
        """Exports chapters as a single PDF file, with cover and in-chapter illustrations.

        Reuses the same illustration-downloading pipeline as ``EpubExporter``
        (``exporters/_illustrations.py``) and the same chapter-heading/content shape — only
        the final embedding step differs: images become base64 ``data:`` URIs directly in
        the HTML string instead of separate files in a zip, since a PDF has no container to
        put them in. WeasyPrint then renders that self-contained HTML/CSS to PDF; no network
        access happens during rendering itself, only during the earlier httpx-based download
        step, keeping all network I/O on the SDK's own async client (WeasyPrint has no async
        API, so rendering runs in a thread via ``asyncio.to_thread`` rather than blocking the
        event loop for however long a large book takes to lay out).
        """

        format: ClassVar[str] = "pdf"

        def __init__(self, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
            """Initialize the exporter.

            Args:
                transport: Custom ``httpx`` transport for the image-downloading client, e.g.
                    a mock transport for tests. Not part of the ``Exporter`` protocol itself
                    — see ``EpubExporter.__init__`` for why.
            """
            self._transport = transport

        async def export(
            self,
            title: Title,
            chapters: list[Chapter],
            output_path: Path,
            *,
            on_chapter: Callable[[], None] | None = None,
            headers: Mapping[str, str] | None = None,
        ) -> Path:
            """Write ``chapters`` to ``output_path`` as a PDF file.

            Args:
                title: The chapters' parent title; supplies metadata, cover, and authors.
                chapters: The chapters to include, in the order they should appear.
                output_path: Where to write the ``.pdf`` file.
                on_chapter: Called once per chapter rendered to HTML, if given — after
                    illustrations have already been downloaded, see the ``Exporter``
                    protocol's docstring.
                headers: Extra HTTP headers for illustration downloads, merged over the
                    SDK's browser-like defaults (a given key replaces the default one).

            Returns:
                ``output_path``.
            """
            # Browser headers for the cover CDN's edge — see the same comment in epub.py.
            async with httpx.AsyncClient(
                timeout=15.0,
                follow_redirects=True,
                transport=self._transport,
                headers=browser_headers(headers),
            ) as client:
                cover_url = pick_cover_url(title.cover)
                cover_data_uri = None
                if cover_url is not None:
                    cover_images = await download_images(client, [cover_url])
                    cover_bytes = cover_images.get(cover_url)
                    if cover_bytes is not None:
                        cover_media_type = media_type_for(guess_extension(cover_url))
                        cover_data_uri = _data_uri(cover_media_type, cover_bytes)

                image_urls = list(
                    dict.fromkeys(
                        url
                        for chapter in chapters
                        for url in extract_image_urls(chapter_body_html(chapter))
                    )
                )
                images = await download_images(client, image_urls)

            url_to_data_uri = {
                url: _data_uri(media_type_for(guess_extension(url)), data)
                for url, data in images.items()
            }

            chapter_html_parts = []
            for chapter in chapters:
                chapter_html_parts.append(_chapter_html(chapter, url_to_data_uri))
                if on_chapter is not None:
                    on_chapter()
            body = _title_page_html(title, cover_data_uri) + "".join(chapter_html_parts)
            document = (
                f"<html><head><meta charset='utf-8'><style>{_PAGE_CSS}</style></head>"
                f"<body>{body}</body></html>"
            )

            await asyncio.to_thread(_render_pdf, document, output_path)
            return output_path

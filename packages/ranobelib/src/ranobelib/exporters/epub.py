"""EPUB exporter (cover and in-chapter illustrations included)."""

from __future__ import annotations

import html
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import ClassVar

import httpx
from ebooklib import epub

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


@register
class EpubExporter:
    """Exports chapters as a single EPUB file, with cover and in-chapter illustrations."""

    format: ClassVar[str] = "epub"

    def __init__(self, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        """Initialize the exporter.

        Args:
            transport: Custom ``httpx`` transport for the image-downloading client, e.g. a
                mock transport for tests. Not part of the ``Exporter`` protocol itself —
                ``RanobeLib.export()`` always constructs exporters with no arguments, so
                this is only reachable by instantiating ``EpubExporter`` directly.
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
        """Write ``chapters`` to ``output_path`` as an EPUB file.

        Downloads the title's cover and every image referenced in the chapters' content and
        embeds them; a download that fails is skipped rather than failing the whole export
        (see docs/api-notes.md's "Illustrations" notes).

        Args:
            title: The chapters' parent title; supplies metadata, cover, and authors.
            chapters: The chapters to include, in the order they should appear.
            output_path: Where to write the ``.epub`` file.
            on_chapter: Called once per chapter embedded, if given — after illustrations
                have already been downloaded, see the ``Exporter`` protocol's docstring.
            headers: Extra HTTP headers for illustration downloads, merged over the
                SDK's browser-like defaults (a given key replaces the default one).

        Returns:
            ``output_path``.
        """
        book = epub.EpubBook()
        book.set_identifier(title.slug_url)
        book.set_title(title.name)
        book.set_language("ru")
        for author in title.authors:
            book.add_author(author.name)

        # Browser headers: cover.cdnlibs.org's edge answers requests without a (non-empty)
        # Referer with a 403, same as the API (see docs/api-notes.md, section "WAF 403").
        async with httpx.AsyncClient(
            timeout=15.0,
            follow_redirects=True,
            transport=self._transport,
            headers=browser_headers(headers),
        ) as client:
            cover_url = pick_cover_url(title.cover)
            if cover_url is not None:
                cover_images = await download_images(client, [cover_url])
                cover_bytes = cover_images.get(cover_url)
                if cover_bytes is not None:
                    book.set_cover(f"cover{guess_extension(cover_url)}", cover_bytes)

            image_urls = list(
                dict.fromkeys(
                    url
                    for chapter in chapters
                    for url in extract_image_urls(chapter_body_html(chapter))
                )
            )
            images = await download_images(client, image_urls)

        url_to_local: dict[str, str] = {}
        for index, (url, data) in enumerate(images.items(), start=1):
            extension = guess_extension(url)
            local_name = f"images/img{index:04d}{extension}"
            url_to_local[url] = local_name
            book.add_item(
                epub.EpubItem(
                    uid=local_name,
                    file_name=local_name,
                    media_type=media_type_for(extension),
                    content=data,
                )
            )

        spine: list[object] = ["nav"]
        toc: list[object] = []
        for index, chapter in enumerate(chapters, start=1):
            heading = chapter_heading(chapter)
            body = rewrite_image_srcs(chapter_body_html(chapter), url_to_local)
            doc = epub.EpubHtml(
                uid=f"chapter_{index}",
                file_name=f"chapter_{index}.xhtml",
                title=heading,
                lang="ru",
            )
            doc.content = f"<h1>{html.escape(heading)}</h1>{body}"
            book.add_item(doc)
            spine.append(doc)
            toc.append(doc)
            if on_chapter is not None:
                on_chapter()

        book.toc = toc
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())
        book.spine = spine

        epub.write_epub(str(output_path), book)
        return output_path

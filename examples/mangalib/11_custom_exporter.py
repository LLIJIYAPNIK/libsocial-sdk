"""Add your own manga export format: implement `Exporter`, `@register` it, export(fmt=...) it.

Same idea as ranobelib's custom exporters (examples/ranobelib/18_custom_exporter.py):
export() looks the format up in `mangalib.exporters.EXPORTERS`, and `@register` puts a class
there under its `format`. One difference in the `mangalib.exporters.Exporter` protocol: the
exporter gets the chapters' *page lists*, not their images, plus a `fetch_pages(chapter)`
coroutine that downloads one chapter's images (in reading order, with the SDK's server
fallback, pacing and retries — download_pages() underneath). Call it once per chapter as you
write, so only one chapter's images are in memory at a time.

    format: ClassVar[str]
    async def export(self, title, chapters, output_path, *, fetch_pages, on_chapter=None)
        -> Path

`on_chapter()` is called once per chapter written; MangaLib.export() turns it into its own
`on_chapter(completed, total)` and the `verbosity` progress bar. The class is instantiated
with no arguments, once per export() call.

This one writes a single HTML file with the pages embedded as data: URIs — readable in any
browser, offline, no viewer needed.
"""

import asyncio
import base64
import html
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import ClassVar

from mangalib import Chapter, MangaLib, Title
from mangalib.exporters import EXPORTERS, Exporter, FetchPages, register


def mime_type(data: bytes) -> str:
    # By the bytes, not the file name: the compress server sends JPEG for ".png" names.
    if data.startswith(b"\x89PNG"):
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"


@register
class HtmlExporter:
    format: ClassVar[str] = "html"

    async def export(
        self,
        title: Title,
        chapters: list[Chapter],
        output_path: Path,
        *,
        fetch_pages: FetchPages,
        on_chapter: Callable[[], None] | None = None,
    ) -> Path:
        # Written as it goes, chapter by chapter, so memory holds one chapter's images at
        # most — not the whole book. And to a temporary file next to the target, moved into
        # place only once complete, like the built-in exporters: a failure halfway leaves no
        # truncated file and doesn't clobber an earlier export.
        name = html.escape(title.rus_name or title.name)
        temporary = output_path.with_name(output_path.name + ".part")
        try:
            with temporary.open("w", encoding="utf-8") as stream:
                stream.write(f"<!doctype html><meta charset='utf-8'><title>{name}</title>\n")
                stream.write(f"<h1>{name}</h1>\n")
                for chapter in chapters:
                    stream.write(f"<h2>Том {chapter.volume}, глава {chapter.number}</h2>\n")
                    for data in await fetch_pages(chapter):
                        encoded = base64.b64encode(data).decode()
                        stream.write(f"<img src='data:{mime_type(data)};base64,{encoded}'")
                        stream.write(" style='display:block;max-width:100%'>\n")
                    if on_chapter is not None:
                        on_chapter()
            temporary.replace(output_path)
        finally:
            temporary.unlink(missing_ok=True)
        return output_path


async def main() -> None:
    # Registered next to the built-in formats ("pdf" only with the pdf extra installed).
    # Exporter is a runtime-checkable Protocol: matching it is about having `format` and
    # `export`, not about inheriting from anything.
    print(sorted(EXPORTERS))
    print(isinstance(HtmlExporter(), Exporter))

    async with MangaLib("https://mangalib.me/ru/manga/267618--07-sedai-no-omoide-zukuri") as lib:
        volumes = await lib.get_volumes([2, 3])
        with tempfile.TemporaryDirectory() as directory:
            path = await lib.export(
                volumes,
                fmt="html",
                path=Path(directory) / "comic.html",
                on_chapter=lambda done, total: print(f"  {done}/{total} chapters"),
            )
            text = path.read_text(encoding="utf-8")
            print(path.name, f"{len(text) / 1e6:.1f} MB,", text.count("<img"), "images")
            print(text[text.index("<h1>") : text.index("</h2>") + 5])


asyncio.run(main())

# Expected output (real run against the live site, with the pdf extra installed — without
# it, "pdf" isn't in the list):
#
# ['cbz', 'html', 'pdf']
# True
#   1/2 chapters
#   2/2 chapters
# comic.html 18.3 MB, 45 images
# <h1>Создание воспоминаний поколения 2007</h1>
# <h2>Том 2, глава 1</h2>

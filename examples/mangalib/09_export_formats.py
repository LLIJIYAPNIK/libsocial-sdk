"""Export manga to CBZ or PDF with MangaLib.export().

export() takes fetched chapters and/or volumes and downloads their page images as it writes
one file. Any of these go in as they are, volumes expanded into their chapters in order:

- one Chapter, or one Volume;
- a list of chapters, of volumes, or a mix;
- the result of download_title() (a list of volumes) — a whole title in one file.

Formats (`mangalib.exporters.EXPORTERS`):

- "cbz": a zip of the page images in reading order, plus ComicInfo.xml with the title's
  metadata and a bookmark where each chapter starts — what comic readers and servers like
  Komga, Kavita or ComicRack read. Built in.
- "pdf": a page per image (JPEGs embedded as-is, not recompressed) with an outline entry per
  chapter. Needs the extra: `pip install "mangalib-python-sdk[pdf]"` (img2pdf + pikepdf).
  Without it, "pdf" just isn't in EXPORTERS, and export(fmt="pdf") is a ValueError.

The file is written to a temporary name next to `path` and only moved into place once it's
complete, so a failure halfway (a page no server serves, say) leaves no truncated file and
doesn't clobber an older export. `server` and `concurrency` work as in download_pages()
(08_page_images.py), `on_chapter(completed, total)` reports progress.
"""

import asyncio
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Awaitable, Callable
from pathlib import Path

from mangalib import MangaLib
from mangalib.exporters import EXPORTERS


def progress(completed: int, total: int) -> None:
    print(f"  written {completed}/{total} chapters")


async def main() -> None:
    print(sorted(EXPORTERS))

    # A short, finished comic: three volumes of one chapter each, 61 pages in all.
    async with MangaLib("https://mangalib.me/ru/manga/267618--07-sedai-no-omoide-zukuri") as lib:
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)

            # One chapter. Nothing is downloaded beforehand: export() fetches the pages.
            chapter = await lib.get_chapter(volume=3, number="1")
            path = await lib.export(chapter, fmt="cbz", path=out / "chapter.cbz")
            with zipfile.ZipFile(path) as archive:
                names = archive.namelist()
                comic_info = ET.fromstring(archive.read("ComicInfo.xml"))
            print(path.name, names[:2], "...", names[-2:])
            for field in ("Series", "Volume", "Writer", "Year", "Genre", "PageCount"):
                print(f"  {field}: {comic_info.findtext(field)}")

            # The whole title, from download_title(), as one file. server and concurrency as
            # in download_pages(); on_chapter after each chapter is written.
            volumes = await lib.download_title()
            fmt = "pdf" if "pdf" in EXPORTERS else "cbz"
            path = await lib.export(
                volumes,
                fmt=fmt,
                path=out / f"title.{fmt}",
                server="compress",
                concurrency=3,
                on_chapter=progress,
            )
            print(path.name, f"{path.stat().st_size / 1e6:.1f} MB")
            if fmt == "pdf":
                import pikepdf  # installed with the pdf extra

                with pikepdf.open(path) as pdf, pdf.open_outline() as outline:
                    print("  pages:", len(pdf.pages))
                    print("  outline:", [item.title for item in outline.root])

            # A single Volume, a list of chapters, or a mix like this one: volume 1, then the
            # chapter of volume 3 fetched above.
            path = await lib.export([volumes[0], chapter], fmt="cbz", path=out / "mix.cbz")
            with zipfile.ZipFile(path) as archive:
                comic_info = ET.fromstring(archive.read("ComicInfo.xml"))
            bookmarks = [page.get("Bookmark") for page in comic_info.iter("Page")]
            print(path.name, comic_info.findtext("PageCount"), "pages,", end=" ")
            print("chapters start at:", [bookmark for bookmark in bookmarks if bookmark])

            # Checked before any download: an unknown format, nothing to export, or a
            # chapter without pages (one from get_table_of_contents()).
            toc = await lib.get_table_of_contents()
            attempts: tuple[Callable[[], Awaitable[Path]], ...] = (
                lambda: lib.export(chapter, fmt="epub", path=out / "x.epub"),
                lambda: lib.export([], fmt="cbz", path=out / "x.cbz"),
                lambda: lib.export(toc[0].chapters, fmt="cbz", path=out / "x.cbz"),
            )
            for attempt in attempts:
                try:
                    await attempt()
                except ValueError as exc:
                    print("ValueError:", exc)
            print("files left:", sorted(item.name for item in out.iterdir()))


if __name__ == "__main__":
    asyncio.run(main())

# Expected output (real run against the live site, with the pdf extra installed — without
# it, the title is exported as title.cbz instead; the long ValueError is wrapped here):
#
# ['cbz', 'pdf']
# chapter.cbz ['0001.jpg', '0002.jpg'] ... ['0016.jpg', 'ComicInfo.xml']
#   Series: Создание воспоминаний поколения 2007
#   Volume: 3
#   Writer: 4n_nek0
#   Year: 2023
#   Genre: Комедия, Повседневность, Школа
#   PageCount: 16
#   written 1/3 chapters
#   written 2/3 chapters
#   written 3/3 chapters
# title.pdf 19.8 MB
#   pages: 61
#   outline: ['Том 1 Глава 1', 'Том 2 Глава 1', 'Том 3 Глава 1']
# mix.cbz 32 pages, chapters start at: ['Том 1 Глава 1', 'Том 3 Глава 1']
# ValueError: Unknown export format 'epub'. Available: cbz, pdf
# ValueError: Nothing to export: no chapters given.
# ValueError: Chapter 1/1 has no pages — fetch it with get_chapter() (or download_title(), ...)
#   first; get_table_of_contents() doesn't include pages.
# files left: ['chapter.cbz', 'mix.cbz', 'title.pdf']

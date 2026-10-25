"""Export manga chapters to CBZ/PDF, and size them first (`pip install "mangalib-python-sdk[pdf]"`).

`MangaLib.export()` takes fetched chapters and/or volumes — one chapter, a volume, or a whole
title from `download_title()` — and downloads their page images as it writes the file:
"cbz" (the pages in order plus a ComicInfo.xml that comic readers like Komga/Kavita read) or
"pdf" (a page per image; needs the `pdf` extra, img2pdf). Before committing to a big
download, `chapter_size()`/`estimate_title_size()` tell you how much it is, from HEAD
requests that don't download any image. See the "MangaLib" section of docs/api-notes.md.
"""

import asyncio
import zipfile

from mangalib import MangaLib
from mangalib.exporters import EXPORTERS


async def main() -> None:
    # Which formats this install can write: "pdf" only shows up with the pdf extra.
    print(sorted(EXPORTERS))

    async with MangaLib("https://mangalib.me/ru/manga/7965--chainsaw-man") as lib:
        chapter = await lib.get_chapter(volume=1, number="1", branch_id=4667)

        # Exact size of the chapter's page images: one HEAD request per page.
        print(await lib.chapter_size(chapter), "bytes in", len(chapter.pages), "pages")

        # on_chapter gets (completed, total) after each chapter is written — the same hook as
        # download_title(on_chapter=...), for showing progress somewhere other than a console.
        path = await lib.export(
            [chapter],
            fmt="cbz",
            path="chainsaw-man-1.cbz",
            on_chapter=lambda completed, total: print(f"{completed}/{total} chapters"),
        )
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
        print(names[:2], "...", names[-2:])

        if "pdf" in EXPORTERS:
            await lib.export([chapter], fmt="pdf", path="chainsaw-man-1.pdf")

    # A title with early access: the estimate (and download_title()) leave the closed
    # chapters out instead of failing on them. Chapters 0-2 have two translations, so pick.
    async with MangaLib("226780--online-game-god-level-assassin-i-am-the-shadow") as lib:
        estimate = await lib.estimate_title_size(sample_size=3, branch_id=23320)
        print(f"~{estimate / 1e6:.0f} MB for the whole title")


asyncio.run(main())

# Expected output (real run against the live site, 2026-10-18; the estimate comes from a
# sample, so it moves with the sample and as chapters are added or open up):
#
# ['cbz', 'pdf']
# 17943292 bytes in 55 pages
# 1/1 chapters
# ['0001.jpg', '0002.jpg'] ... ['0055.jpg', 'ComicInfo.xml']
# ~525 MB for the whole title

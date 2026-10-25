"""Read a manga chapter's pages with mangalib-python-sdk (`pip install mangalib-python-sdk`).

mangalib.me runs on the same API as ranobelib.me, and `MangaLib` has the same methods as
`RanobeLib` for titles, chapters and translations — what differs is the chapter itself: it's
a list of page images (`Chapter.pages`) instead of text. Each page is a path relative to an
image server; `download_page()`/`download_pages()` pick the server and fall back to the next
one if it refuses. See the "MangaLib" section of docs/api-notes.md for how the servers and
paid chapters were checked.
"""

import asyncio
from pathlib import Path

from mangalib import AuthRequiredError, MangaLib


async def main() -> None:
    async with MangaLib("https://mangalib.me/ru/manga/7965--chainsaw-man") as lib:
        # Chapter 1 has two translations. As on ranobelib, get_chapter() won't guess which
        # one you want (the API's own default isn't predictable), so pick one explicitly.
        branches = await lib.get_translations(volume=1, number="1")
        for branch in branches:
            # is_open: whether the translation can be read without an account. The SDK has
            # no login, so a closed one can't be fetched through it.
            print(branch.branch_id, [team.name for team in branch.teams], branch.is_open)

        chapter = await lib.get_chapter(volume=1, number="1", branch_id=branches[0].branch_id)
        print(len(chapter.pages), "pages")
        first = chapter.pages[0]
        print(first.number, first.width, first.height, first.url)

        # The servers mangalib.me lists. Not all of them let a script in: main/secondary sit
        # behind a DDoS-Guard check, so downloads start from "compress" (full-size images).
        servers = await lib.list_image_servers()
        print([server.id for server in servers])

        # Pages come back as bytes, in reading order, a few at a time. Don't trust the file
        # name's extension for the format: "compress" sends JPEG even for ".png" names.
        images = await lib.download_pages(chapter.model_copy(update={"pages": chapter.pages[:3]}))
        out = Path("chainsaw-man-1")
        out.mkdir(exist_ok=True)
        for page, data in zip(chapter.pages, images, strict=False):
            (out / f"{page.number:03}.jpg").write_bytes(data)
        print([len(data) for data in images])

    # A chapter in early access (paid until its expired_at) is refused with
    # AuthRequiredError — the API itself answers 200 with no pages for it.
    async with MangaLib("226780--online-game-god-level-assassin-i-am-the-shadow") as lib:
        volumes = await lib.get_table_of_contents()
        closed = [
            chapter
            for volume in volumes
            for chapter in volume.chapters
            if not any(branch.is_open for branch in chapter.branches)
        ]
        if closed:
            try:
                await lib.get_chapter(volume=int(closed[0].volume), number=closed[0].number)
            except AuthRequiredError:
                print("closed:", closed[0].volume, closed[0].number)


asyncio.run(main())

# Expected output (real run against the live site, 2026-10-18; the closed chapter changes as
# early access ends):
#
# 4667 ['Nippa'] True
# 4666 ['Japit Comics'] True
# 55 pages
# 1 1425 2048 //manga/chainsaw-man/chapters/1-1/00.png_res.jpg
# ['main', 'secondary', 'compress', 'download', 'crop']
# [443530, 268038, 878867]
# closed: 1 132

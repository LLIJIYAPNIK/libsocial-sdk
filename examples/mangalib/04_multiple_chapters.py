"""Fetch several manga chapters in one call with MangaLib.get_chapters().

Pass (volume, number) pairs, get back a list of chapters with their pages, in the order you
asked for them (not sorted). Better than awaiting get_chapter() in a loop of your own: the
chapter list is fetched once for the whole batch, and the requests run concurrently within
the client's limits and pacing.
"""

import asyncio

from mangalib import MangaLib


async def main() -> None:
    url = "https://mangalib.me/ru/manga/262329--kidou-senshi-gundam-battle-operation-code-fairy"
    async with MangaLib(url) as lib:
        # Deliberately out of order, and across two volumes.
        chapters = await lib.get_chapters([(2, "8"), (1, "1"), (1, "6.5")])

        for chapter in chapters:
            print(chapter.volume, chapter.number, len(chapter.pages), "pages")


asyncio.run(main())

# Expected output (real run against the live site):
#
# 2 8 43 pages
# 1 1 44 pages
# 1 6.5 5 pages

"""Download several chapters in one call with RanobeLib.get_chapters().

get_chapters() is the batch form of get_chapter(): pass a list of (volume, number) pairs and
get back a list[Chapter] with content already filled in for each of them. It's not just a
convenience loop — the underlying ApiClient still bounds concurrency and paces requests
across the whole batch (see the "Rate limiting" section of CLAUDE.md), so calling this once
is friendlier to the API than awaiting get_chapter() in a hand-written loop.
"""

import asyncio

from ranobelib import RanobeLib


async def main() -> None:
    async with RanobeLib("https://ranobelib.me/ru/book/91443--new-hero-in-dxd") as lib:
        # Each tuple is (volume, number), matching get_chapter()'s two positional concepts.
        chapters = await lib.get_chapters([(1, "1"), (1, "2")])

        for chapter in chapters:
            print(chapter.volume, chapter.number, len(chapter.content))


asyncio.run(main())

# Expected output (real run against the live site):
#
# 1 1 30722
# 1 2 22747

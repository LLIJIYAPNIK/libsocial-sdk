"""List a manga's volumes and chapters with MangaLib.get_table_of_contents().

One request to the title's chapter list returns every volume and chapter — numbers, names,
translations — already grouped into volumes and sorted, fractional numbers included. It has
no pages: a chapter's page images are only listed when the chapter itself is fetched
(get_chapter() and friends, 03_single_chapter.py). So this is the cheap way to see what a
title has before deciding what to download.
"""

import asyncio

from mangalib import MangaLib


async def main() -> None:
    url = "https://mangalib.me/ru/manga/262329--kidou-senshi-gundam-battle-operation-code-fairy"
    async with MangaLib(url) as lib:
        volumes = await lib.get_table_of_contents()

        for volume in volumes:
            print(f"Volume {volume.number}: {len(volume.chapters)} chapters")

        # `number` is a string: chapter numbers can be fractional ("6.5" — an extra between
        # chapters 6 and 7 here), and the SDK sorts them numerically, not as text.
        print([chapter.number for chapter in volumes[0].chapters])

        chapter = volumes[0].chapters[0]
        print(chapter.volume, chapter.number, chapter.name)

        # branches_count / branches: the chapter's translations. One here, so get_chapter()
        # needs no branch_id; 06_translations.py covers chapters with several.
        print(chapter.branches_count, [branch.user.username for branch in chapter.branches])

        # No pages in the table of contents — fetch the chapter to get them.
        print(chapter.pages)


if __name__ == "__main__":
    asyncio.run(main())

# Expected output (real run against the live site):
#
# Volume 1: 7 chapters
# Volume 2: 5 chapters
# ['1', '2', '3', '4', '5', '6', '6.5']
# 1 1 Феи на поле боя
# 1 ['Ave_Jalter']
# []

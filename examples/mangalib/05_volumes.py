"""Fetch whole volumes with MangaLib.get_volume() and get_volumes().

get_volume(n) finds the volume's chapters in the table of contents and fetches each with its
pages, returning one Volume. get_volumes([...]) does the same for several volumes, sharing a
single chapter-list request; every requested number is checked first, so an unknown one
fails the call before anything is downloaded (VolumeNotFoundError, see 14_error_handling.py).
"""

import asyncio

from mangalib import MangaLib


async def main() -> None:
    url = "https://mangalib.me/ru/manga/262329--kidou-senshi-gundam-battle-operation-code-fairy"
    async with MangaLib(url) as lib:
        volume = await lib.get_volume(2)
        print(volume.number, [chapter.number for chapter in volume.chapters])

        # Volume 2 is already in the disk cache from the call above, so only volume 1's
        # chapters are requested here.
        volumes = await lib.get_volumes([1, 2])
        for volume in volumes:
            pages = sum(len(chapter.pages) for chapter in volume.chapters)
            print(f"volume {volume.number}: {len(volume.chapters)} chapters, {pages} pages")


asyncio.run(main())

# Expected output (real run against the live site):
#
# 2 ['7', '8', '9', '10', '11']
# volume 1: 7 chapters, 215 pages
# volume 2: 5 chapters, 213 pages

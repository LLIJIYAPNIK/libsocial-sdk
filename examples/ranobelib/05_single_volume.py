"""Download a whole volume with RanobeLib.get_volume().

get_volume() is get_chapters() pre-filled with every chapter belonging to one volume: it
fetches the table of contents to find which chapters make up the volume, then downloads
content for all of them, returning a single Volume with Chapter.content populated.
"""

import asyncio

from ranobelib import RanobeLib


async def main() -> None:
    async with RanobeLib("https://ranobelib.me/ru/book/91443--new-hero-in-dxd") as lib:
        # Volume 0 is a prologue-style volume with just one chapter on this title.
        volume = await lib.get_volume(0)
        print(volume.number, [chapter.number for chapter in volume.chapters])


asyncio.run(main())

# Expected output (real run against the live site):
#
# 0 ['1']

"""Download several volumes at once with RanobeLib.get_volumes().

get_volumes() is the batch form of get_volume(), analogous to how get_chapters() batches
get_chapter(): pass a list of volume numbers and get back a list[Volume], each with every
chapter's content already downloaded.
"""

import asyncio

from ranobelib import RanobeLib


async def main() -> None:
    async with RanobeLib("https://ranobelib.me/ru/book/91443--new-hero-in-dxd") as lib:
        volumes = await lib.get_volumes([0, 1])
        for volume in volumes:
            print(volume.number, len(volume.chapters))


asyncio.run(main())

# Expected output (real run against the live site):
#
# 0 1
# 1 46

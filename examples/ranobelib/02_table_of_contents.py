"""List every volume and chapter of a title with RanobeLib.get_table_of_contents().

get_table_of_contents() returns the full volume/chapter structure (numbers, names, branch
info) in a single request to the title's chapter-list endpoint — but *without* chapter
content (Chapter.content is None here). Use it to browse a title's structure cheaply before
deciding which chapters to actually download with get_chapter()/get_chapters().
"""

import asyncio

from ranobelib import RanobeLib


async def main() -> None:
    async with RanobeLib("https://ranobelib.me/ru/book/91443--new-hero-in-dxd") as lib:
        # A list[Volume], each Volume holding its list[Chapter] — already grouped and
        # sorted by the SDK (including fractional chapter numbers like "6.5"), so no manual
        # sorting/grouping is needed on the caller's side.
        volumes = await lib.get_table_of_contents()

        for volume in volumes:
            print(f"Volume {volume.number}: {len(volume.chapters)} chapters")

        # Chapter.name is the chapter's title as shown on the site; it can be empty for
        # untitled chapters, but here the first chapter of volume 0 does have one.
        print(volumes[0].chapters[0].name)


asyncio.run(main())

# Expected output (real run against the live site):
#
# Volume 0: 1 chapters
# Volume 1: 46 chapters
# (НЕ ГОТОВО) Возможный гарем

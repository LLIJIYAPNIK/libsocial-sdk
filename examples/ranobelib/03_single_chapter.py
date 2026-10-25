"""Download one chapter's content with RanobeLib.get_chapter().

Unlike get_table_of_contents(), get_chapter() fetches the chapter's actual content (raw HTML
as returned by the API) in addition to its metadata. `volume`/`number` are matched against
what the site itself calls them — `number` is a string because ranobelib.me chapter numbers
can be fractional (e.g. "6.5"), not because of any SDK-side formatting choice.
"""

import asyncio

from ranobelib import RanobeLib


async def main() -> None:
    async with RanobeLib("https://ranobelib.me/ru/book/91443--new-hero-in-dxd") as lib:
        # volume=1, number="1" addresses volume 1, chapter 1 exactly as shown on the site.
        chapter = await lib.get_chapter(volume=1, number="1")
        print(chapter.name)

        # `content` is raw HTML straight from the API (paragraphs, formatting tags, etc.),
        # not plain text — that's why it's sliced here rather than printed whole; export()
        # is what turns this HTML into txt/fb2/epub/pdf (see 10_export_formats.py).
        print(chapter.content[:200])


asyncio.run(main())

# Expected output (real run against the live site):
#
# Глава 1
# <p data-paragraph-index="1">"Наконец, я наконец-то могу вернуться." - говорю я с широкой
# улыбкой на лице, хотя по моим щекам текут слезы. Прошло слишком много времени с тех пор,
# как я застрял в этом м

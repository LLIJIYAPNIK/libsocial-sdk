"""Fetch one manga chapter and its pages with MangaLib.get_chapter().

On mangalib.me a chapter is a list of page images, so where RanobeLib's Chapter has
`content` (text), MangaLib's has `pages`: one `Page` per image, in reading order. A page is a
path on an image server, not the image itself — 08_page_images.py downloads them.

`volume` and `number` are what the site calls them; `number` is a string because it can be
fractional ("6.5"). `branch_id` picks a translation when a chapter has several; this title
has one per chapter, so it's left out (06_translations.py shows the other case).
"""

import asyncio

from mangalib import MangaLib


async def main() -> None:
    url = "https://mangalib.me/ru/manga/262329--kidou-senshi-gundam-battle-operation-code-fairy"
    async with MangaLib(url) as lib:
        # A fractional chapter, passed as the same string the table of contents shows.
        chapter = await lib.get_chapter(volume=1, number="6.5")
        print(chapter.volume, chapter.number, chapter.name)

        # The team credited for this translation (the chapter list has these per branch).
        print([team.name for team in chapter.teams])

        print(len(chapter.pages), "pages")
        for page in chapter.pages[:3]:
            # number: 1-based position. width/height: pixels, as the API reports them.
            # image: the file name — its extension isn't a reliable format (one server
            # sends JPEG for ".png").
            print(page.number, page.width, page.height, page.image)

        # url: the image's path on an image server, starting with "//". page_url() (in
        # 08_page_images.py) puts a server in front of it.
        print(chapter.pages[0].url)


if __name__ == "__main__":
    asyncio.run(main())

# Expected output (real run against the live site; the last line is wrapped here):
#
# 1 6.5 Экстры 1 тома
# ['Ave_Jalter']
# 5 pages
# 1 1440 2048 1d411e81-4a45-4ede-971b-b046151e7ace.jpg
# 2 1440 2048 ca809075-b09c-41f5-b5c7-2d9b4ac43719.jpg
# 3 2880 1278 f61be9be-83bc-44b9-bb43-2a5779256a34.jpg
# //manga/kidou-senshi-gundam-battle-operation-code-fairy/chapters/4293241/
#   1d411e81-4a45-4ede-971b-b046151e7ace.jpg

"""List a chapter's illustrations and rewrite their URLs with chapter_image_urls() /
rewrite_image_urls().

Chapter illustrations are plain `<img>` tags inside `Chapter.content` (and, rarely,
`Chapter.footnotes`), hotlinked to ranobelib.me / *.cdnlibs.org. If you serve chapters
yourself — say, a web reader that caches chapters for offline reading — you usually want to
route those images through your own same-origin proxy and know up front which images to
cache. These two helpers do the `<img>` parsing for you, so you don't need an HTML parser of
your own on top of the SDK.
"""

import asyncio
from urllib.parse import quote

from ranobelib import RanobeLib, chapter_image_urls, rewrite_image_urls


async def main() -> None:
    async with RanobeLib("https://ranobelib.me/ru/book/91443--new-hero-in-dxd") as lib:
        chapter = await lib.get_chapter(volume=1, number="1")

        # Every <img src> in content, then footnotes, in document order. A URL used twice
        # (the same illustration repeated) is listed once — handy as a "what to cache" list.
        urls = chapter_image_urls(chapter)
        print(len(urls), "images")
        for url in urls:
            print(url)
        print()

        # rewrite_image_urls() never modifies `chapter` — it returns a copy whose content and
        # footnotes have every src replaced by your function's result. The SDK HTML-escapes
        # the value as an attribute for you, so the function returns a plain URL string.
        proxied = rewrite_image_urls(chapter, lambda url: f"/images/view?url={quote(url, safe='')}")
        print(chapter_image_urls(proxied)[0])

        # Both helpers need fetched content: on a chapter from get_table_of_contents()
        # (content is None) they raise ValueError, same as chapter_size().


asyncio.run(main())

# Expected output (real run against the live site; the last line is wrapped here, it's a single
# line in the real output):
#
# 5 images
# https://ranobelib.me/uploads/ranobe/new-hero-in-dxd/chapters/1593948/image_jaVT.png
# https://ranobelib.me/uploads/ranobe/new-hero-in-dxd/chapters/1593948/image_TT8s.png
# https://ranobelib.me/uploads/ranobe/new-hero-in-dxd/chapters/1593948/image_INtT.png
# https://ranobelib.me/uploads/ranobe/new-hero-in-dxd/chapters/1593948/image_brGE.png
# https://ranobelib.me/uploads/ranobe/new-hero-in-dxd/chapters/1593948/image_2Q1M.png
#
# /images/view?url=https%3A%2F%2Franobelib.me%2Fuploads%2Franobe%2Fnew-hero-in-dxd
# %2Fchapters%2F1593948%2Fimage_jaVT.png

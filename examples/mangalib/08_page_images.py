"""Download a manga chapter's page images: image servers, page URLs, fallback, errors.

A fetched chapter's `pages` (03_single_chapter.py) are paths, not images. The images live on
several image servers, every one serving every page; `list_image_servers()` lists them
(`ImageServer`: id, label, url). Not all of them let a script in: `main`/`secondary` sit
behind a DDoS-Guard check, `crop` serves small previews. So downloads try `compress` (full
size) first, then `download`, `main`, `secondary`, moving on when a server refuses —
see the "MangaLib" section of docs/api-notes.md for how that was checked.

- `page_url(page, server)`: the full URL, if something else should fetch the image (a web
  frontend, an external downloader) rather than the SDK.
- `download_page(page, server=...)`: one page as bytes; `server` is tried first.
- `download_pages(chapter, concurrency=...)`: all pages, in reading order. Requests to one
  image host are paced across the whole process (one start every 0.2 s by default), so a
  higher `concurrency` mostly overlaps slow transfers; it doesn't raise the request rate.
- `PageDownloadError`: a page no server would serve; `.failures` lists every attempt.

Page images aren't cached on disk (the chapter's metadata is): download them once and keep
the files.
"""

import asyncio
import tempfile
from pathlib import Path

from mangalib import ImageServer, MangaLib, Page, PageDownloadError, page_url


def extension(data: bytes) -> str:
    # The page's file name isn't a reliable guide to the format (the compress server sends
    # JPEG for ".png" names), so look at the bytes.
    if data.startswith(b"\x89PNG"):
        return "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return "jpg"


async def main() -> None:
    url = "https://mangalib.me/ru/manga/262329--kidou-senshi-gundam-battle-operation-code-fairy"
    async with MangaLib(url) as lib:
        # Cached on disk like the rest of the API's answers; refresh=True refetches.
        servers: list[ImageServer] = await lib.list_image_servers()
        for server in servers:
            print(server.id, server.label, server.url)

        chapter = await lib.get_chapter(volume=1, number="6.5")
        page: Page = chapter.pages[0]
        compress = next(server for server in servers if server.id == "compress")
        print(page_url(page, compress))

        # main refuses scripts, so this falls back to the next server — same bytes as
        # asking compress directly. crop is a preview: far fewer bytes.
        via_main = await lib.download_page(page, server="main")
        direct = await lib.download_page(page, server="compress")
        preview = await lib.download_page(page, server="crop")
        print(len(via_main), via_main == direct, len(preview))

        # The whole chapter, then saved as 001.jpg, 002.jpg, ... with the real extension.
        images = await lib.download_pages(chapter, concurrency=3)
        with tempfile.TemporaryDirectory() as directory:
            for item, data in zip(chapter.pages, images, strict=True):
                path = Path(directory) / f"{item.number:03}.{extension(data)}"
                path.write_bytes(data)
            print(sorted(path.name for path in Path(directory).iterdir()))

        # A page that isn't on any server: every one is tried, then PageDownloadError. In
        # download_pages(), one such page cancels the downloads still running. (Takes a few
        # seconds: the cdnlibs hosts answer a missing file with a 502, and a 5xx is retried
        # with backoff before moving on. compress and download share a host, so it's asked
        # once.)
        missing = page.model_copy(update={"url": "//manga/no-such-title/chapters/1/01.jpg"})
        try:
            await lib.download_page(missing)
        except PageDownloadError as exc:
            for attempt_url, reason in exc.failures:
                print(attempt_url.split("/manga/")[0], "->", reason)

        # Bad arguments fail before any request.
        try:
            await lib.download_pages(chapter, server="nope")
        except ValueError as exc:
            print("ValueError:", exc)
        try:
            await lib.download_pages(chapter, concurrency=0)
        except ValueError as exc:
            print("ValueError:", exc)


asyncio.run(main())

# Expected output (real run against the live site; the page URL is wrapped here):
#
# main Первый https://img2.imglib.info
# secondary Второй https://img3.cdnrulib.link
# compress Сжатия https://img3.cdnlibs.org
# download Скачивание https://img3.cdnlibs.org
# crop Crop pages https://crops.mangalib.me
# https://img3.cdnlibs.org/manga/kidou-senshi-gundam-battle-operation-code-fairy/chapters/
#   4293241/1d411e81-4a45-4ede-971b-b046151e7ace.jpg
# 301735 True 59191
# ['001.jpg', '002.jpg', '003.jpg', '004.jpg', '005.jpg']
# https://img3.cdnlibs.org -> HTTP 502 (text/plain; charset=utf-8)
# https://img2.imglib.info -> HTTP 403 (text/html; charset=utf-8)
# https://img3.cdnrulib.link -> HTTP 502 (text/plain; charset=utf-8)
# ValueError: Unknown image server 'nope'. Available: compress, crop, download, main, secondary
# ValueError: concurrency must be at least 1, got 0.

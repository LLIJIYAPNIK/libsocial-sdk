"""Export downloaded chapters to txt / fb2 / epub / pdf with RanobeLib.export().

export() takes chapters you've already downloaded (with content filled in — from
get_chapter(s)/get_volume(s)/download_title(), not get_table_of_contents()) and writes them
to a file in the requested format. It fetches the title's metadata itself (used for the
book title/author on the output file, cached the same way get_info() is), so you don't need
to call get_info() separately first.

`fmt="pdf"` needs WeasyPrint's native dependencies (Pango/cairo/GTK3) installed on the
system — `pip install`/`uv add` alone doesn't guarantee that on every platform. Without them,
PdfExporter isn't registered at all, so export(fmt="pdf") raises the same "unknown format"
ValueError the other three formats would raise for a typo, not an import-time crash.
"""

import asyncio

from ranobelib import RanobeLib


async def main() -> None:
    async with RanobeLib("https://ranobelib.me/ru/book/91443--new-hero-in-dxd") as lib:
        chapters = await lib.get_chapters([(1, "1"), (1, "2")])

        for fmt in ("txt", "fb2", "epub", "pdf"):
            path = f"output.{fmt}"
            # export() returns the Path it wrote to (the same `path` passed in), which is
            # handy when path is left to a default or built dynamically.
            result = await lib.export(chapters, fmt=fmt, path=path)
            print(fmt, "->", result)


asyncio.run(main())

# Expected output (real run against the live site — file sizes from that run; if WeasyPrint's
# native dependencies aren't installed, the "pdf" iteration raises
# `ValueError: Unknown export format 'pdf'. Available: epub, fb2, txt` instead of the line
# shown below):
#
# txt -> output.txt      (84,044 bytes)
# fb2 -> output.fb2      (87,691 bytes)
# epub -> output.epub  (1,442,724 bytes, cover + illustrations embedded)
# pdf -> output.pdf      (cover + illustrations embedded, needs WeasyPrint)
#
# output.txt's first few lines, for a sense of the format:
#
# New Hero in DxD
#
#
# Volume 1, Chapter 1: Глава 1
#
# "Наконец, я наконец-то могу вернуться." - говорю я с широкой улыбкой на лице, хотя по моим
# щекам текут слезы. Прошло слишком много времени с тех пор, как я застрял в этом месте, я
# больше не могу с этим справляться. Поначалу это было круто, но через нек...

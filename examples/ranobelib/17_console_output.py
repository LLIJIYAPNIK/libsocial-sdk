"""Console output: progress bars and a log of what the SDK does, via `verbosity`.

`RanobeLib(..., verbosity=...)` takes one of three values:

- `False` (the default): prints nothing. A library shouldn't write to your terminal unless
  asked, so this is what you get without the parameter.
- `"progress_only"`: a progress bar (via `rich`) around the long operations —
  download_title(), export() and the sampling in estimate_title_size().
- `"full"`: the same bars plus one log line per title / chapter-list / chapter fetch, saying
  whether it came from the disk cache (`[cache]`) or went to the API (`[api]`). Useful to see
  why a run is slow, or that a second run really is served from the cache.

This is console output for a human at a terminal, printed straight to stdout — not
`logging`. A program that needs to *report* progress elsewhere (a web backend telling a
browser "chapter 3 of 6") wants download_title()'s `on_chapter(completed, total)` callback
instead, see 08_download_title.py; the two work together and don't replace each other.
"""

import asyncio
import tempfile

from ranobelib import RanobeLib

URL = "https://ranobelib.me/ru/book/40195--enbizaka-no-shitateya"


async def main() -> None:
    # A fresh cache directory, so the first run below really goes to the API.
    with tempfile.TemporaryDirectory() as cache_dir:
        # Default: silent. download_title() still downloads everything, it just says nothing.
        async with RanobeLib(URL, cache_dir=cache_dir) as lib:
            volumes = await lib.download_title()
            print("silent run:", sum(len(volume.chapters) for volume in volumes), "chapters")

        # Progress bars only: one bar for the download, no per-request lines.
        async with RanobeLib(URL, cache_dir=cache_dir, verbosity="progress_only") as lib:
            await lib.download_title()

        # Full: bars plus a line per fetch. Everything was cached by the first run, so the
        # log says [cache] throughout...
        async with RanobeLib(URL, cache_dir=cache_dir, verbosity="full") as lib:
            await lib.download_title()
            # ...except what's explicitly refetched: refresh=True skips the cache. Without a
            # branch_id, get_chapter() first checks the chapter list for competing
            # translations, so that list is refetched too.
            await lib.get_chapter(volume=1, number="1", refresh=True)


asyncio.run(main())

# Expected output (real run against the live site; rich draws the bar across the terminal's
# width, timestamps the log lines and adds where they came from on the right):
#
# silent run: 6 chapters
# Downloading 40195--enbizaka-no-shitateya -------------------------- 6/6 0:00:00
# [13:03:36] [cache] chapter list for 40195--enbizaka-no-shitateya  console.py:52
#            [cache] chapter 1/0                                    console.py:52
#            [cache] chapter 1/1                                    console.py:52
#            [cache] chapter 1/2.1                                  console.py:52
#            [cache] chapter 1/2.2                                  console.py:52
#            [cache] chapter 1/2.3                                  console.py:52
#            [cache] chapter 1/2.4                                  console.py:52
# Downloading 40195--enbizaka-no-shitateya -------------------------- 6/6 0:00:00
#            [api] fetching chapter list for                        console.py:52
#            40195--enbizaka-no-shitateya
#            [api] fetching chapter 1/1                             console.py:52

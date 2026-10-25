"""Disk caching of raw API responses, and what isn't cached.

MangaLib (and Catalog) cache raw API responses on disk: title metadata, the chapter list,
each chapter's page list, the image server list. Re-running a script, or exporting the same
chapters to another format, doesn't ask the API again for what it already answered.

- `cache_dir`: where; `.mangalib_cache` in the current directory by default (shared by
  MangaLib and Catalog). `cache_ttl`: seconds before an entry counts as stale; `None` (the
  default) never expires.
- `refresh=True` on get_info(), get_table_of_contents(), get_chapter(): ask the API anyway
  and overwrite the cached copy.
- `cache_stats()` -> `CacheStats(entries, bytes)`, `clear_cache(older_than=...)`: measure and
  empty the cache without touching its files (their layout is an SDK internal).
- Not cached: page images (they're the bulk of the traffic, and a disk cache of them is
  what CBZ/PDF export already gives you) and closed chapters (a cached refusal would outlive
  the chapter opening up).
"""

import asyncio
import tempfile

from mangalib import AuthRequiredError, CacheStats, MangaLib, cache_stats, clear_cache
from mangalib.cache import DEFAULT_CACHE_DIR

GUNDAM = "https://mangalib.me/ru/manga/262329--kidou-senshi-gundam-battle-operation-code-fairy"
# Chapters 6-11 are in early access (closed) until 2026-10-31...12-05.
HUSBAND_THIEF = "https://mangalib.me/ru/manga/261420--husband-thief"


async def main() -> None:
    print("default cache_dir:", DEFAULT_CACHE_DIR)

    # A fresh directory, so the first calls really go to the API.
    with tempfile.TemporaryDirectory() as cache_dir:
        # verbosity="full" logs every title/chapter-list/chapter lookup as [api] or [cache].
        async with MangaLib(GUNDAM, cache_dir=cache_dir, verbosity="full") as lib:
            print("--- first run")
            await lib.get_info()
            chapter = await lib.get_chapter(volume=1, number="6.5")
            print("--- the same calls again")
            await lib.get_info()
            await lib.get_chapter(volume=1, number="6.5")
            # Without branch_id, get_chapter() checks the chapter list for competing
            # translations first, so refresh=True re-fetches that list too (a cached one
            # wouldn't show a translation added since). With branch_id, only the chapter.
            print("--- refresh=True")
            await lib.get_chapter(volume=1, number="6.5", refresh=True)

            # One entry per response: title, chapter list, chapter.
            stats: CacheStats = cache_stats(cache_dir)
            print(stats)

            # Page images aren't cached: downloading the same page twice adds one entry, the
            # image server list (looked up on the first download), and no image bytes.
            for attempt in (1, 2):
                image = await lib.download_page(chapter.pages[0])
                print(f"page 1, download {attempt}: {len(image)} bytes")
            print("after two image downloads:", cache_stats(cache_dir))

        # A closed chapter isn't cached either: the refusal is raised before the answer
        # reaches the disk, so the next try asks the API again (and succeeds once it opens).
        async with MangaLib(HUSBAND_THIEF, cache_dir=cache_dir) as lib:
            await lib.get_table_of_contents()
            before = cache_stats(cache_dir).entries
            try:
                await lib.get_chapter(volume=1, number="6")
            except AuthRequiredError:
                print("closed chapter, new cache entries:", cache_stats(cache_dir).entries - before)

        # cache_ttl: an entry older than this many seconds is a miss and gets re-fetched.
        # The title cached above is already older than that, so write a fresh copy first.
        async with MangaLib(GUNDAM, cache_dir=cache_dir, cache_ttl=2, verbosity="full") as lib:
            print("--- cache_ttl=2: refresh, right away, after 3s")
            await lib.get_info(refresh=True)
            await lib.get_info()
            await asyncio.sleep(3)
            await lib.get_info()

        # Maintenance. older_than drops only entries written longer ago than that (the same
        # age check as cache_ttl): nothing here is a day old, so nothing goes.
        print("older than a day:", clear_cache(cache_dir, older_than=24 * 60 * 60))
        # Without older_than everything goes. Safe while another process uses the cache: a
        # read racing the removal is just a miss.
        print("everything:", clear_cache(cache_dir))
        print("left:", cache_stats(cache_dir))


asyncio.run(main())

# Expected output (real run against the live site on 2026-10-25, starting from an empty cache
# directory; rich timestamps the log lines and adds where they came from on the right. The
# byte counts change with the site's data; once chapter 6 of Husband Thief opens on
# 2026-10-31, the closed-chapter line is no longer printed):
#
# default cache_dir: .mangalib_cache
# --- first run
# [16:48:03] [api] fetching title metadata for                                      console.py:52
#            262329--kidou-senshi-gundam-battle-operation-code-fairy
# [16:48:04] [api] fetching chapter list for                                        console.py:52
#            262329--kidou-senshi-gundam-battle-operation-code-fairy
#            [api] fetching chapter 1/6.5                                           console.py:52
# --- the same calls again
#            [cache] title metadata for                                             console.py:52
#            262329--kidou-senshi-gundam-battle-operation-code-fairy
#            [cache] chapter list for                                               console.py:52
#            262329--kidou-senshi-gundam-battle-operation-code-fairy
#            [cache] chapter 1/6.5                                                  console.py:52
# --- refresh=True
#            [api] fetching chapter list for                                        console.py:52
#            262329--kidou-senshi-gundam-battle-operation-code-fairy
#            [api] fetching chapter 1/6.5                                           console.py:52
# CacheStats(entries=3, bytes=23727)
# page 1, download 1: 301735 bytes
# page 1, download 2: 301735 bytes
# after two image downloads: CacheStats(entries=4, bytes=25426)
# closed chapter, new cache entries: 0
# --- cache_ttl=2: refresh, right away, after 3s
# [16:48:06] [api] fetching title metadata for                                      console.py:52
#            262329--kidou-senshi-gundam-battle-operation-code-fairy
#            [cache] title metadata for                                             console.py:52
#            262329--kidou-senshi-gundam-battle-operation-code-fairy
# [16:48:09] [api] fetching title metadata for                                      console.py:52
#            262329--kidou-senshi-gundam-battle-operation-code-fairy
# older than a day: CacheStats(entries=0, bytes=0)
# everything: CacheStats(entries=5, bytes=39007)
# left: CacheStats(entries=0, bytes=0)

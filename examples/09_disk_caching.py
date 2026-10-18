"""Disk caching of raw API responses.

Every RanobeLib instance caches raw API responses to disk by default (see cache.py /
"Кэширование" in CLAUDE.md), keyed separately per operation (title metadata, chapter list,
chapter content). This means re-exporting a title in a different format, or re-running a
script during development, doesn't re-hit the network for data already fetched once.
"""

import asyncio
import time

from ranobelib import RanobeLib, cache_stats, clear_cache


async def main() -> None:
    async with RanobeLib(
        # cache_dir defaults to ".ranobelib_cache" in the current directory; passed
        # explicitly here just to make it visible what's being demonstrated.
        "https://ranobelib.me/ru/book/91443--new-hero-in-dxd",
        cache_dir=".ranobelib_cache",
    ) as lib:
        start = time.perf_counter()
        await lib.get_table_of_contents()
        print(f"first call:  {time.perf_counter() - start:.3f}s (hits the API)")

        # Same call again: served entirely from the on-disk cache, no network request.
        start = time.perf_counter()
        await lib.get_table_of_contents()
        print(f"second call: {time.perf_counter() - start:.3f}s (served from disk cache)")

        # refresh=True bypasses the cache for this one call and re-fetches from the API,
        # then updates the cached copy — use it when you know the site's data has changed
        # since it was cached (e.g. new chapters were just released).
        await lib.get_table_of_contents(refresh=True)

    # Cache maintenance. The on-disk layout (file names, format) is an SDK internal, so
    # measure and empty the cache through these helpers rather than touching its files.
    # Both only look at files the cache itself wrote — anything else in the directory is
    # left alone — and a missing directory is just an empty cache, not an error.
    print(cache_stats(".ranobelib_cache"))

    # Drop only entries written more than a day ago (the same age check cache_ttl uses) —
    # e.g. after a fix on the site's side, without waiting for every entry's TTL. Nothing
    # here is that old yet, so nothing is removed.
    print(clear_cache(".ranobelib_cache", older_than=24 * 60 * 60))

    # Without older_than, every entry goes. Safe even while another process uses the same
    # cache: a read racing the removal is just a cache miss, and the entry gets re-fetched.
    print(clear_cache(".ranobelib_cache"))


asyncio.run(main())

# Expected output (real run against the live site, starting from an empty cache directory —
# your exact timings will vary, but the gap between the two calls won't; the byte count is
# the size of this title's chapter list and changes as chapters are added):
#
# first call:  0.361s (hits the API)
# second call: 0.012s (served from disk cache)
# CacheStats(entries=1, bytes=36277)
# CacheStats(entries=0, bytes=0)
# CacheStats(entries=1, bytes=36277)

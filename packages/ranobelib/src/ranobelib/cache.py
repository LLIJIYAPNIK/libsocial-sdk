"""Disk cache maintenance: ``cache_stats()`` and ``clear_cache()``.

The cache itself is ``libsocial-core``'s; this module only gives its helpers ranobelib's
default directory, ``.ranobelib_cache``, the one ``RanobeLib``/``Catalog`` use. The on-disk
layout is internal, so code outside the SDK should go through these rather than measure or
delete the cache's files itself.
"""

from __future__ import annotations

from pathlib import Path

from libsocial import cache as _core
from libsocial.cache import CacheStats, DiskCache

DEFAULT_CACHE_DIR = Path(".ranobelib_cache")
"""Default cache directory, relative to the current working directory."""

__all__ = ["DEFAULT_CACHE_DIR", "CacheStats", "DiskCache", "cache_stats", "clear_cache"]


def cache_stats(cache_dir: str | Path = DEFAULT_CACHE_DIR) -> CacheStats:
    """Count the entries in an SDK disk cache and their total size on disk.

    Only files the cache itself writes are counted, not anything else that happens to be in
    the directory.

    Args:
        cache_dir: The cache directory — the same ``cache_dir`` passed to ``RanobeLib`` /
            ``Catalog`` (default: theirs, ``.ranobelib_cache`` in the current directory).

    Returns:
        The number of entries and their total size in bytes. A missing directory is an empty
        cache, ``CacheStats(entries=0, bytes=0)``, not an error.
    """
    return _core.cache_stats(cache_dir)


def clear_cache(
    cache_dir: str | Path = DEFAULT_CACHE_DIR, *, older_than: float | None = None
) -> CacheStats:
    """Remove entries from an SDK disk cache.

    Only files the cache itself writes are removed — anything else in the directory, and the
    directory itself, is left alone. Safe to call while clients are using the same cache: an
    entry being read as it's removed is just a cache miss, and one written after it's
    removed is simply recreated.

    Args:
        cache_dir: The cache directory — see ``cache_stats()``.
        older_than: If given, only remove entries written more than this many seconds ago
            (the same age check ``cache_ttl`` uses), plus any corrupted entry, which the
            cache can't serve anyway. ``None`` (the default) removes every entry.

    Returns:
        The number of entries removed and the bytes they took. A missing directory removes
        nothing, ``CacheStats(entries=0, bytes=0)``, rather than raising.

    Raises:
        ValueError: If ``older_than`` is negative.
    """
    return _core.clear_cache(cache_dir, older_than=older_than)

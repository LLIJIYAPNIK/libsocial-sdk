"""Disk cache for raw JSON API responses, keyed by request identity.

Also the public cache-maintenance helpers, ``cache_stats()`` and ``clear_cache()`` — the
on-disk layout is an SDK internal, so code outside the SDK should go through these rather
than measure or delete the cache's files itself.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_CACHE_DIR = Path(".ranobelib_cache")
"""Default cache directory, relative to the current working directory."""

_ENTRY_NAME = re.compile(r"[0-9a-f]{64}\.json")
"""Name of a file ``DiskCache`` writes (``_path_for``) — anything else in the directory
isn't the cache's and is never counted or removed."""


@dataclass(frozen=True)
class CacheStats:
    """How many cache entries there are (or were removed), and their total size on disk."""

    entries: int
    bytes: int


class DiskCache:
    """Caches JSON-serializable values to disk, keyed by an arbitrary string.

    One file per key, named by the key's hash (so keys built from slugs, chapter numbers,
    etc. are always safe filenames), holding the cached value plus the time it was written
    so ``ttl`` can be checked on read without touching any other entry. Corrupted or
    unreadable entries are treated as a cache miss rather than raised as an error, since a
    stale/broken cache file shouldn't stop the SDK from just re-fetching the data.
    """

    def __init__(
        self,
        cache_dir: str | Path,
        *,
        ttl: float | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        """Initialize the cache.

        Args:
            cache_dir: Directory to store cache files in. Created lazily on first write.
            ttl: Seconds after which a cache entry is treated as a miss. ``None`` (the
                default) means entries never expire.
            clock: Time source used to stamp and check entries. Overridable for tests.
        """
        self._dir = Path(cache_dir)
        self._ttl = ttl
        self._clock = clock

    def get(self, key: str) -> Any | None:
        """Return the cached value for ``key``, or ``None`` on a miss or expiry."""
        try:
            payload = json.loads(self._path_for(key).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, KeyError):
            return None
        if self._ttl is not None and self._clock() - payload["cached_at"] > self._ttl:
            return None
        return payload["data"]

    def set(self, key: str, data: Any) -> None:
        """Write ``data`` to disk under ``key``, creating the cache directory if needed."""
        path = self._path_for(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"cached_at": self._clock(), "data": data}
        path.write_text(json.dumps(payload), encoding="utf-8")

    def stats(self) -> CacheStats:
        """Count the cache's entries and their total size. See ``cache_stats()``."""
        entries = size = 0
        for path in self._entry_paths():
            try:
                size += path.stat().st_size
            except OSError:  # Removed since it was listed.
                continue
            entries += 1
        return CacheStats(entries=entries, bytes=size)

    def clear(self, *, older_than: float | None = None) -> CacheStats:
        """Remove the cache's entries, or only those older than ``older_than`` seconds.

        See ``clear_cache()``.
        """
        if older_than is not None and older_than < 0:
            raise ValueError(f"older_than must be >= 0, got {older_than}")
        now = self._clock()
        entries = size = 0
        for path in self._entry_paths():
            if older_than is not None and not self._is_older_than(path, now - older_than):
                continue
            try:
                entry_size = path.stat().st_size
                path.unlink()
            except OSError:
                # Already removed by someone else, or (on Windows) open in another process
                # right now — either way, not ours to count as removed.
                continue
            entries += 1
            size += entry_size
        return CacheStats(entries=entries, bytes=size)

    def _is_older_than(self, path: Path, cutoff: float) -> bool:
        try:
            cached_at = float(json.loads(path.read_text(encoding="utf-8"))["cached_at"])
        except FileNotFoundError:
            return False
        except (OSError, ValueError, KeyError, TypeError):
            # Unreadable/corrupted: get() can never serve it, so it's as good as expired.
            return True
        return cached_at < cutoff

    def _entry_paths(self) -> Iterator[Path]:
        try:
            children = list(self._dir.iterdir())
        except (FileNotFoundError, NotADirectoryError):
            return
        for path in children:
            if _ENTRY_NAME.fullmatch(path.name) and path.is_file() and not path.is_symlink():
                yield path

    def _path_for(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self._dir / f"{digest}.json"


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
    return DiskCache(cache_dir).stats()


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
    return DiskCache(cache_dir).clear(older_than=older_than)

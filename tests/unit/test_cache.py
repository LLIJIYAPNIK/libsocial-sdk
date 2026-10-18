"""Unit tests for ranobelib.cache."""

import time
from pathlib import Path

import pytest

from ranobelib.cache import CacheStats, DiskCache, cache_stats, clear_cache


def test_get_returns_none_for_missing_key(tmp_path: Path) -> None:
    cache = DiskCache(tmp_path)

    assert cache.get("missing") is None


def test_set_then_get_roundtrips_value(tmp_path: Path) -> None:
    cache = DiskCache(tmp_path)

    cache.set("key", {"id": 1, "name": "Example"})

    assert cache.get("key") == {"id": 1, "name": "Example"}


def test_set_creates_cache_directory(tmp_path: Path) -> None:
    cache_dir = tmp_path / "nested" / "cache"
    cache = DiskCache(cache_dir)

    cache.set("key", [1, 2, 3])

    assert cache_dir.exists()
    assert cache.get("key") == [1, 2, 3]


def test_get_returns_value_before_ttl_expires(tmp_path: Path) -> None:
    clock = _FakeClock(start=1000.0)
    cache = DiskCache(tmp_path, ttl=60, clock=clock)

    cache.set("key", "value")
    clock.advance(59)

    assert cache.get("key") == "value"


def test_get_returns_none_after_ttl_expires(tmp_path: Path) -> None:
    clock = _FakeClock(start=1000.0)
    cache = DiskCache(tmp_path, ttl=60, clock=clock)

    cache.set("key", "value")
    clock.advance(61)

    assert cache.get("key") is None


def test_get_never_expires_without_ttl(tmp_path: Path) -> None:
    clock = _FakeClock(start=1000.0)
    cache = DiskCache(tmp_path, ttl=None, clock=clock)

    cache.set("key", "value")
    clock.advance(10_000_000)

    assert cache.get("key") == "value"


def test_get_treats_corrupted_cache_file_as_a_miss(tmp_path: Path) -> None:
    cache = DiskCache(tmp_path)
    cache.set("key", "value")

    for path in tmp_path.iterdir():
        path.write_text("not json", encoding="utf-8")

    assert cache.get("key") is None


def test_different_keys_do_not_collide(tmp_path: Path) -> None:
    cache = DiskCache(tmp_path)

    cache.set("a", "value-a")
    cache.set("b", "value-b")

    assert cache.get("a") == "value-a"
    assert cache.get("b") == "value-b"


_GHOST = "0" * 64 + ".json"
"""A validly-named entry that's listed but gone by the time it's touched (a concurrent
clear_cache() got there first)."""


def _fill(cache: DiskCache, count: int) -> None:
    for index in range(count):
        cache.set(f"key-{index}", {"index": index})


def _entry_sizes(cache_dir: Path) -> int:
    return sum(path.stat().st_size for path in cache_dir.glob("*.json"))


def test_cache_stats_counts_entries_and_bytes(tmp_path: Path) -> None:
    _fill(DiskCache(tmp_path), 3)

    assert cache_stats(tmp_path) == CacheStats(entries=3, bytes=_entry_sizes(tmp_path))


def test_cache_stats_of_missing_directory_is_empty(tmp_path: Path) -> None:
    assert cache_stats(tmp_path / "missing") == CacheStats(0, 0)


def test_cache_stats_of_a_file_instead_of_directory_is_empty(tmp_path: Path) -> None:
    path = tmp_path / "file"
    path.write_text("x", encoding="utf-8")

    assert cache_stats(path) == CacheStats(0, 0)


def test_cache_stats_and_clear_ignore_files_the_cache_did_not_write(tmp_path: Path) -> None:
    _fill(DiskCache(tmp_path), 2)
    entries_bytes = _entry_sizes(tmp_path)
    foreign = [
        tmp_path / "notes.json",
        tmp_path / ("A" * 64 + ".json"),  # uppercase hex — not a name _path_for produces
        tmp_path / ("0" * 64 + ".json.bak"),
        tmp_path / "readme.txt",
    ]
    for path in foreign:
        path.write_text("keep me", encoding="utf-8")
    (tmp_path / ("1" * 64 + ".json")).mkdir()  # right name, but not a file

    assert cache_stats(tmp_path) == CacheStats(2, entries_bytes)
    assert clear_cache(tmp_path) == CacheStats(2, entries_bytes)

    assert all(path.exists() for path in foreign)
    assert (tmp_path / ("1" * 64 + ".json")).is_dir()


def test_clear_cache_removes_every_entry_and_keeps_directory(tmp_path: Path) -> None:
    cache = DiskCache(tmp_path)
    _fill(cache, 3)
    entries_bytes = _entry_sizes(tmp_path)

    assert clear_cache(tmp_path) == CacheStats(3, entries_bytes)

    assert tmp_path.is_dir()
    assert cache_stats(tmp_path) == CacheStats(0, 0)
    assert cache.get("key-0") is None


def test_clear_cache_of_missing_directory_removes_nothing(tmp_path: Path) -> None:
    assert clear_cache(tmp_path / "missing") == CacheStats(0, 0)
    assert not (tmp_path / "missing").exists()


def test_cache_is_usable_again_after_clear(tmp_path: Path) -> None:
    cache = DiskCache(tmp_path)
    cache.set("key", "old")
    clear_cache(tmp_path)

    cache.set("key", "new")

    assert cache.get("key") == "new"


def test_clear_older_than_removes_only_expired_entries(tmp_path: Path) -> None:
    clock = _FakeClock(start=1000.0)
    cache = DiskCache(tmp_path, clock=clock)
    cache.set("old", "a")
    clock.advance(100)
    cache.set("new", "b")
    clock.advance(30)
    old_size = cache._path_for("old").stat().st_size

    removed = cache.clear(older_than=60)

    assert removed == CacheStats(1, old_size)
    assert cache.get("old") is None
    assert cache.get("new") == "b"


def test_clear_older_than_keeps_entry_exactly_at_the_cutoff(tmp_path: Path) -> None:
    clock = _FakeClock(start=1000.0)
    cache = DiskCache(tmp_path, clock=clock)
    cache.set("key", "value")
    clock.advance(60)

    assert cache.clear(older_than=60) == CacheStats(0, 0)
    assert cache.get("key") == "value"


def test_clear_cache_older_than_uses_wall_clock(tmp_path: Path) -> None:
    clock = _FakeClock(start=time.time() - 3600)
    DiskCache(tmp_path, clock=clock).set("hour-old", "a")
    DiskCache(tmp_path).set("fresh", "b")

    assert clear_cache(tmp_path, older_than=60).entries == 1
    assert DiskCache(tmp_path).get("fresh") == "b"


def test_clear_older_than_removes_corrupted_entries(tmp_path: Path) -> None:
    cache = DiskCache(tmp_path)
    cache.set("broken-json", "a")
    cache.set("not-a-number", "b")
    cache.set("fine", "c")
    cache._path_for("broken-json").write_text("not json", encoding="utf-8")
    cache._path_for("not-a-number").write_text('{"cached_at": "soon", "data": 1}', "utf-8")

    assert cache.clear(older_than=3600).entries == 2
    assert cache.get("fine") == "c"


def test_clear_rejects_negative_older_than(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="older_than"):
        clear_cache(tmp_path, older_than=-1)


def test_stats_and_clear_skip_entries_removed_concurrently(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = _FakeClock(start=1000.0)
    cache = DiskCache(tmp_path, clock=clock)
    cache.set("key", "value")
    clock.advance(10)
    real = [*cache._entry_paths()]
    monkeypatch.setattr(DiskCache, "_entry_paths", lambda self: iter([tmp_path / _GHOST, *real]))

    assert cache.stats().entries == 1
    assert cache.clear(older_than=0).entries == 1
    assert cache.clear().entries == 0


def test_clear_skips_entries_it_cannot_remove(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache = DiskCache(tmp_path)
    cache.set("locked", "a")
    cache.set("free", "b")
    locked = cache._path_for("locked")
    real_unlink = Path.unlink

    def unlink(self: Path, missing_ok: bool = False) -> None:
        if self == locked:  # e.g. open in another process on Windows
            raise PermissionError(self)
        real_unlink(self, missing_ok=missing_ok)

    free_size = cache._path_for("free").stat().st_size
    monkeypatch.setattr(Path, "unlink", unlink)

    assert clear_cache(tmp_path) == CacheStats(1, free_size)
    assert cache.get("locked") == "a"


class _FakeClock:
    def __init__(self, *, start: float) -> None:
        self._now = start

    def advance(self, seconds: float) -> None:
        self._now += seconds

    def __call__(self) -> float:
        return self._now

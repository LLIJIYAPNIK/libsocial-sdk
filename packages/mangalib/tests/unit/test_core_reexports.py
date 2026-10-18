"""mangalib on top of libsocial-core: the names it re-exports are the core's own objects."""

from pathlib import Path

import pytest

import libsocial
import mangalib
from libsocial import models as core_models
from mangalib import models
from mangalib.cache import DEFAULT_CACHE_DIR

_EXCEPTIONS = [
    "AccessBlockedError",
    "AmbiguousChapter",
    "AuthRequiredError",
    "ChapterNotFoundError",
    "DownloadTitleInterruptedError",
    "MultipleTitleTranslationsError",
    "MultipleTranslationsError",
    "RateLimitError",
    "TitleNotFoundError",
    "VolumeNotFoundError",
]


@pytest.mark.parametrize("name", _EXCEPTIONS)
def test_exceptions_are_the_cores(name: str) -> None:
    assert getattr(mangalib, name) is getattr(libsocial, name)


def test_mangalib_error_catches_errors_raised_by_the_core() -> None:
    assert mangalib.MangaLibError is libsocial.LibSocialError
    assert issubclass(mangalib.PageDownloadError, libsocial.LibSocialError)

    with pytest.raises(mangalib.MangaLibError):
        raise libsocial.TitleNotFoundError("1--x")


@pytest.mark.parametrize(
    "name", ["ChapterUser", "Country", "Cover", "Genre", "Label", "Person", "Tag", "Team"]
)
def test_site_independent_models_are_the_cores(name: str) -> None:
    assert getattr(models, name) is getattr(core_models, name)


@pytest.mark.parametrize("name", ["Title", "Chapter", "ChapterBranch"])
def test_site_models_extend_the_cores(name: str) -> None:
    assert issubclass(getattr(models, name), getattr(core_models, name))


def test_cache_helpers_default_to_mangalib_cache(tmp_path: Path) -> None:
    assert Path(".mangalib_cache") == DEFAULT_CACHE_DIR
    assert mangalib.cache_stats(tmp_path) == mangalib.CacheStats(entries=0, bytes=0)
    assert mangalib.clear_cache(tmp_path, older_than=0) == mangalib.CacheStats(0, 0)

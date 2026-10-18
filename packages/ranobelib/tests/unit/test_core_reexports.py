"""ranobelib on top of libsocial-core: the names it re-exports are the core's own objects.

So ``except ranobelib.TitleNotFoundError`` catches what the core raises, ``isinstance`` keeps
working in both directions, and ``RanobeLibError`` still catches every error.
"""

import pytest

import libsocial
import ranobelib
from libsocial import models as core_models
from ranobelib import exceptions, models

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
    assert getattr(ranobelib.exceptions, name) is getattr(libsocial, name)


def test_ranobelib_error_catches_errors_raised_by_the_core() -> None:
    assert ranobelib.RanobeLibError is exceptions.RanobeLibError is libsocial.LibSocialError

    with pytest.raises(ranobelib.RanobeLibError):
        raise libsocial.TitleNotFoundError("1--x")
    with pytest.raises(ranobelib.TitleNotFoundError):
        raise libsocial.TitleNotFoundError("1--x")


@pytest.mark.parametrize(
    "name",
    ["ChapterBranch", "ChapterUser", "Country", "Cover", "Genre", "Label", "Person", "Tag", "Team"],
)
def test_site_independent_models_are_the_cores(name: str) -> None:
    assert getattr(models, name) is getattr(core_models, name)


def test_site_models_extend_the_cores() -> None:
    assert issubclass(models.Title, core_models.Title)
    assert issubclass(models.Chapter, core_models.Chapter)
    assert issubclass(models.Volume, core_models.Volume)
    assert issubclass(models.CatalogPage, core_models.CatalogPage)
    assert issubclass(ranobelib.RanobeLib, libsocial.TitleClient)
    assert issubclass(ranobelib.Catalog, libsocial.Catalog)


def test_ranobelib_is_scoped_to_its_site() -> None:
    assert (
        ranobelib.RanobeLib.site
        == ranobelib.Catalog.site
        == libsocial.Site(id=3, origin="https://ranobelib.me")
    )

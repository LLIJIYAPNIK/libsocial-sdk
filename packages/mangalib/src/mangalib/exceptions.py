"""Exceptions raised by the SDK.

Everything but ``PageDownloadError`` is ``libsocial-core``'s, re-exported here: the core
raises them, so ``except mangalib.TitleNotFoundError`` and ``except libsocial.TitleNotFoundError``
catch the same thing. ``MangaLibError`` is the core's base class, so ``except MangaLibError``
catches every error the SDK raises.
"""

from __future__ import annotations

from libsocial.exceptions import (
    AccessBlockedError,
    AmbiguousChapter,
    AuthRequiredError,
    ChapterNotFoundError,
    DownloadTitleInterruptedError,
    LibSocialError,
    MultipleTitleTranslationsError,
    MultipleTranslationsError,
    RateLimitError,
    TitleNotFoundError,
    VolumeNotFoundError,
)

MangaLibError = LibSocialError
"""Base class for all errors raised by the SDK (``libsocial.LibSocialError``)."""


class PageDownloadError(LibSocialError):
    """Raised when a page image couldn't be downloaded from any image server.

    Each server is tried in turn (see ``MangaLib.download_page()``); this is raised only
    after the last one failed too.

    Attributes:
        failures: ``(url, reason)`` for every attempt, in the order they were made.
    """

    def __init__(self, failures: list[tuple[str, str]]) -> None:
        self.failures = failures
        attempts = "; ".join(f"{url}: {reason}" for url, reason in failures)
        super().__init__(f"Couldn't download the page from any image server ({attempts})")


__all__ = [
    "AccessBlockedError",
    "AmbiguousChapter",
    "AuthRequiredError",
    "ChapterNotFoundError",
    "DownloadTitleInterruptedError",
    "MangaLibError",
    "MultipleTitleTranslationsError",
    "MultipleTranslationsError",
    "PageDownloadError",
    "RateLimitError",
    "TitleNotFoundError",
    "VolumeNotFoundError",
]

"""Exceptions raised by the SDK.

All of them are ``libsocial-core``'s, re-exported here: the core raises them, so
``except ranobelib.TitleNotFoundError`` and ``except libsocial.TitleNotFoundError`` catch the
same thing. ``RanobeLibError`` is the core's base class under its old name, so
``except RanobeLibError`` still catches every error the SDK raises.
"""

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

RanobeLibError = LibSocialError
"""Base class for all errors raised by the SDK (``libsocial.LibSocialError``)."""

__all__ = [
    "AccessBlockedError",
    "AmbiguousChapter",
    "AuthRequiredError",
    "ChapterNotFoundError",
    "DownloadTitleInterruptedError",
    "MultipleTitleTranslationsError",
    "MultipleTranslationsError",
    "RanobeLibError",
    "RateLimitError",
    "TitleNotFoundError",
    "VolumeNotFoundError",
]

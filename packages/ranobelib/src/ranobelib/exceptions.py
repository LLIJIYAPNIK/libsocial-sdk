"""Custom exceptions raised by the SDK."""

from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from ranobelib.models import ChapterBranch, Volume


class RanobeLibError(Exception):
    """Base class for all errors raised by the SDK."""


class TitleNotFoundError(RanobeLibError):
    """Raised when a title cannot be found on ranobelib.me.

    Attributes:
        slug_url: The title's ``{id}--{slug}`` identifier that couldn't be found.
    """

    def __init__(self, slug_url: str) -> None:
        self.slug_url = slug_url
        super().__init__(f"Title not found: {slug_url!r}")


class ChapterNotFoundError(RanobeLibError):
    """Raised when a chapter cannot be found for a given volume/number.

    Attributes:
        slug_url: The title's ``{id}--{slug}`` identifier.
        volume: The volume number that was requested.
        number: The chapter number that was requested.
    """

    def __init__(self, slug_url: str, *, volume: str, number: str) -> None:
        self.slug_url = slug_url
        self.volume = volume
        self.number = number
        super().__init__(f"Chapter not found: {slug_url!r} volume={volume!r} number={number!r}")


class VolumeNotFoundError(RanobeLibError):
    """Raised when a title has no chapters for a given volume number.

    Attributes:
        slug_url: The title's ``{id}--{slug}`` identifier.
        volume: The volume number that was requested.
    """

    def __init__(self, slug_url: str, *, volume: str) -> None:
        self.slug_url = slug_url
        self.volume = volume
        super().__init__(f"Volume not found: {slug_url!r} volume={volume!r}")


class MultipleTranslationsError(RanobeLibError):
    """Raised when a chapter has more than one team's translation and none was selected.

    The SDK does not guess a default: the API's own default when ``branch_id`` is omitted
    is not simply the first branch listed, and the actual rule it uses isn't documented
    (see docs/api-notes.md) — returning it silently would be unpredictable. Call
    ``RanobeLib.get_translations()`` to list the available branches, then pass one's
    ``branch_id`` explicitly.

    Attributes:
        slug_url: The title's ``{id}--{slug}`` identifier.
        volume: The chapter's volume number.
        number: The chapter number.
        branches: The chapter's available translations, as returned by
            ``RanobeLib.get_translations()``.
    """

    def __init__(
        self, slug_url: str, *, volume: str, number: str, branches: list[ChapterBranch]
    ) -> None:
        self.slug_url = slug_url
        self.volume = volume
        self.number = number
        self.branches = branches
        options = ", ".join(
            f"branch_id={branch.branch_id} ({_describe_branch(branch)})" for branch in branches
        )
        super().__init__(
            f"Multiple translations for {slug_url!r} volume={volume!r} number={number!r}: "
            f"{options}. Pass branch_id to select one (see RanobeLib.get_translations())."
        )


def _describe_branch(branch: ChapterBranch) -> str:
    if branch.teams:
        return ", ".join(team.name for team in branch.teams)
    return branch.user.username


class AmbiguousChapter(NamedTuple):
    """One chapter that ``RanobeLib.download_title()`` couldn't resolve a translation for.

    Attributes:
        volume: The chapter's volume number.
        number: The chapter number.
        branches: The chapter's available translations, as returned by
            ``RanobeLib.get_translations()``.
    """

    volume: str
    number: str
    branches: list[ChapterBranch]


class MultipleTitleTranslationsError(RanobeLibError):
    """Raised by ``download_title()`` when one or more chapters have an unresolved translation.

    Unlike ``MultipleTranslationsError`` (one chapter), this can list several: a title-wide
    bulk download checks every chapter up front rather than stopping at the first ambiguous
    one, so a caller doesn't have to fix one chapter, rerun, hit the next, and rerun again.
    Pass ``branch_id`` or ``translation_index`` to ``download_title()`` to resolve them, or
    fetch the listed chapters individually with ``get_chapter(..., branch_id=...)``.

    Attributes:
        slug_url: The title's ``{id}--{slug}`` identifier.
        chapters: The ambiguous chapters and their available translations.
    """

    def __init__(self, slug_url: str, *, chapters: list[AmbiguousChapter]) -> None:
        self.slug_url = slug_url
        self.chapters = chapters
        lines = [
            f"  volume={chapter.volume!r} number={chapter.number!r}: "
            + ", ".join(
                f"branch_id={branch.branch_id} ({_describe_branch(branch)})"
                for branch in chapter.branches
            )
            for chapter in chapters
        ]
        super().__init__(
            f"{len(chapters)} chapter(s) in {slug_url!r} have more than one translation "
            "unresolved by the given branch_id/translation_index. Pass branch_id or "
            "translation_index to download_title() to select one for every chapter listed, "
            "or fetch them individually with get_chapter(..., branch_id=...):\n" + "\n".join(lines)
        )


class AuthRequiredError(RanobeLibError):
    """Raised when the requested content requires authorization (paid or early access).

    Attributes:
        url: The request URL that returned 403.
    """

    def __init__(self, url: str) -> None:
        self.url = url
        super().__init__(f"Authorization required to access: {url}")


class AccessBlockedError(RanobeLibError):
    """Raised when the site's edge protection rejects a request before it reaches the API.

    Not an authorization problem, unlike ``AuthRequiredError``: the DDoS-Guard edge in front
    of api.cdnlibs.org answers with an HTML 403 page (the API's own 403 is JSON) when it
    doesn't like the request — so far, a missing or empty ``Referer`` (see
    docs/api-notes.md, section "WAF 403"). The SDK already sends browser-like headers, so
    seeing this means either the edge changed its rules — check for an SDK update, or send
    what it now expects via ``headers=`` on ``RanobeLib``/``Catalog`` (or ``ApiClient``, if
    using it directly) — or the edge is blocking the network/IP itself, which no header
    fixes. Not retried: resending the same request gets
    the same answer.

    Attributes:
        url: The request URL that returned 403.
    """

    def __init__(self, url: str) -> None:
        self.url = url
        super().__init__(
            f"Request blocked by the site's protection (not an authorization issue): {url}. "
            "The site may have changed which requests it accepts: check for an SDK update, "
            "or send different headers via RanobeLib(..., headers=...) / "
            "Catalog(headers=...). If the same URL doesn't open in a browser on this network "
            "either, the IP itself is blocked and no header change will help."
        )


class RateLimitError(RanobeLibError):
    """Raised when the API responds with 429 Too Many Requests.

    Attributes:
        retry_after: The response's ``Retry-After`` value, in seconds, if it sent one.
    """

    def __init__(self, retry_after: float | None = None) -> None:
        self.retry_after = retry_after
        suffix = f" (retry after {retry_after}s)" if retry_after is not None else ""
        super().__init__(f"Rate limited by the API{suffix}")


class DownloadTitleInterruptedError(RanobeLibError):
    """Raised by ``download_title()`` when a chapter fetch fails unrecoverably partway through.

    ``download_title()`` fetches hundreds-to-thousands of chapters sequentially for a long
    title, which can outlast even the extra, bulk-specific rate-limit retry budget described
    in ``download_title()``'s ``max_rate_limit_retries`` — or hit some other unrecoverable
    error (e.g. ``AuthRequiredError`` on a chapter that turns out to need a paywall/auth
    token). Rather than letting that error propagate on its own and silently discard every
    chapter already fetched, it's wrapped in this exception instead, carrying what was
    already downloaded — so a caller can keep that partial result, or simply call
    ``download_title()`` again: the SDK's disk cache means already-fetched chapters aren't
    re-requested, so a retry resumes close to where this one stopped rather than restarting
    the whole title. See docs/api-notes.md's "Rate limiting и retry" section and issue #41.

    Attributes:
        slug_url: The title's ``{id}--{slug}`` identifier.
        volumes: Chapters fetched before the failure, grouped into volumes the same way a
            successful ``download_title()`` call would return them.
        completed: How many chapters were fetched before the failure.
        total: How many chapters ``download_title()`` had planned to fetch in total.
    """

    def __init__(self, slug_url: str, *, volumes: list[Volume], completed: int, total: int) -> None:
        self.slug_url = slug_url
        self.volumes = volumes
        self.completed = completed
        self.total = total
        super().__init__(
            f"download_title() for {slug_url!r} was interrupted after {completed}/{total} "
            "chapter(s) fetched — see __cause__ for why, .volumes for what was already fetched."
        )

"""Catching the SDK's exceptions.

Every exception the SDK raises derives from MangaLibError (an alias of libsocial-core's
LibSocialError, so it also catches what the core raises), and each carries what it's about as
attributes, not only in the message:

- `TitleNotFoundError` (`.slug_url`): no such title, or not a mangalib.me one — the API
  answers both with the same 404.
- `ChapterNotFoundError` (`.volume`, `.number`), `VolumeNotFoundError` (`.volume`).
- `MultipleTranslationsError` (`.branches`): the chapter has several translations and no
  `branch_id` was given. The whole-title variants, `MultipleTitleTranslationsError` /
  `AmbiguousChapter` and `DownloadTitleInterruptedError`, are in 07_download_title.py.
- `AuthRequiredError` (`.url`): a closed chapter (early access, paid). The API answers it with
  200 and no pages; the SDK turns that into this error.
- `PageDownloadError` (`.failures`): no image server would serve a page.
- `AccessBlockedError` (`.url`): the DDoS-Guard filter in front of the API refused the request
  before the API saw it. Not an authorization problem: the SDK already sends the headers the
  filter wants, so seeing it means the site changed its rules (pass `headers=` to MangaLib /
  Catalog until an SDK update) or blocks your IP (no header helps; try the URL in a browser).
- `RateLimitError` (`.retry_after`): the API kept answering 429 after the client's retries
  (3, with backoff, honoring Retry-After). It takes sustained traffic, so this script can't
  trigger it; download_title() rides out more of them on its own.
"""

import asyncio

from mangalib import (
    AccessBlockedError,
    AuthRequiredError,
    ChapterNotFoundError,
    MangaLib,
    MangaLibError,
    MultipleTranslationsError,
    PageDownloadError,
    RateLimitError,
    TitleNotFoundError,
    VolumeNotFoundError,
)

GUNDAM = "https://mangalib.me/ru/manga/262329--kidou-senshi-gundam-battle-operation-code-fairy"
# Chapters 0-5 have two translations each; 6-11 are in early access until 2026-10-31...12-05.
HUSBAND_THIEF = "https://mangalib.me/ru/manga/261420--husband-thief"


async def main() -> None:
    # A URL shaped like a title page, for a title that doesn't exist. ranobelib.me titles
    # end up here too: the API scopes titles by site and answers 404 for another site's.
    async with MangaLib("https://mangalib.me/ru/manga/1--this-title-does-not-exist-zzz") as lib:
        try:
            await lib.get_info()
        except TitleNotFoundError as exc:
            print(f"{type(exc).__name__}: {exc} (slug_url={exc.slug_url!r})")

    async with MangaLib(GUNDAM) as lib:
        # A real title, a chapter it doesn't have.
        try:
            await lib.get_chapter(volume=1, number="999")
        except ChapterNotFoundError as exc:
            print(f"{type(exc).__name__}: {exc}")

        # A volume it doesn't have.
        try:
            await lib.get_volume(volume=99)
        except VolumeNotFoundError as exc:
            print(f"{type(exc).__name__}: {exc}")

        # A page no server has: every server is tried, then PageDownloadError. (A few
        # seconds: a missing file is a 502 on these hosts, and a 5xx is retried first.)
        chapter = await lib.get_chapter(volume=1, number="6.5")
        missing = chapter.pages[0].model_copy(update={"url": "//manga/no-such-title/1/01.jpg"})
        try:
            await lib.download_page(missing)
        except PageDownloadError as exc:
            print(f"{type(exc).__name__}: {len(exc.failures)} servers tried")
            for server, reason in exc.failures:
                print(f"  {server}: {reason}")

    async with MangaLib(HUSBAND_THIEF) as lib:
        # Two translations, no branch_id: the SDK doesn't guess (the API's own pick isn't
        # predictable). The options are on the exception.
        try:
            await lib.get_chapter(volume=1, number="1")
        except MultipleTranslationsError as exc:
            options = [
                (branch.branch_id, [team.name for team in branch.teams]) for branch in exc.branches
            ]
            print(f"{type(exc).__name__}: choose a branch_id from {options}")

        # A closed chapter.
        try:
            await lib.get_chapter(volume=1, number="6")
        except AuthRequiredError as exc:
            print(f"{type(exc).__name__}: {exc.url}")

    # AccessBlockedError, on purpose: `headers=` merges over the SDK's browser-like defaults,
    # and the filter refuses a request with an empty Referer (docs/api-notes.md, "WAF 403").
    # The same `headers=` is the way out in the other direction, if the site starts wanting
    # something the SDK doesn't send yet, e.g. headers={"User-Agent": "..."}.
    async with MangaLib(GUNDAM, headers={"Referer": ""}) as lib:
        try:
            # refresh=True: a title cached by an earlier call would otherwise come from disk.
            await lib.get_info(refresh=True)
        except AccessBlockedError as exc:
            # The message names the request (also exc.url) and what to try next.
            print(f"{type(exc).__name__}: {exc}")

    # Callers that don't care which one it was catch the base class. RateLimitError is the
    # one worth telling apart: waiting helps (retry_after is the API's Retry-After in
    # seconds, when it sent one). It doesn't fire here.
    async with MangaLib(HUSBAND_THIEF) as lib:
        for number in ("0", "1", "6", "999"):
            try:
                await lib.get_chapter(volume=1, number=number, branch_id=26208)
                print(f"chapter {number}: ok")
            except RateLimitError as exc:
                print(f"chapter {number}: rate limited, retry in {exc.retry_after or 60}s")
            except MangaLibError as exc:
                print(f"chapter {number}: {type(exc).__name__}")


asyncio.run(main())

# Expected output (real run against the live site on 2026-10-25. The main server answers a
# missing file with a 404 or a DDoS-Guard 403 from run to run; chapter 6 of Husband Thief opens
# on 2026-10-31, after which it no longer raises AuthRequiredError. The AccessBlockedError
# message is one line with the whole fields[] query string; shortened and wrapped here):
#
# TitleNotFoundError: Title not found: '1--this-title-does-not-exist-zzz'
#   (slug_url='1--this-title-does-not-exist-zzz')
# ChapterNotFoundError: Chapter not found: '262329--kidou-senshi-gundam-battle-operation-code-fairy'
#   volume='1' number='999'
# VolumeNotFoundError: Volume not found: '262329--kidou-senshi-gundam-battle-operation-code-fairy'
#   volume='99'
# PageDownloadError: 3 servers tried
#   https://img3.cdnlibs.org/manga/no-such-title/1/01.jpg: HTTP 502 (text/plain; charset=utf-8)
#   https://img2.imglib.info/manga/no-such-title/1/01.jpg: HTTP 403 (text/html; charset=utf-8)
#   https://img3.cdnrulib.link/manga/no-such-title/1/01.jpg: HTTP 502 (text/plain; charset=utf-8)
# MultipleTranslationsError: choose a branch_id from [(26208, ['Bam Byeol']), (26207, ['Lexiopia'])]
# AuthRequiredError:
#   https://api.cdnlibs.org/api/manga/261420--husband-thief/chapter?number=6&volume=1
# AccessBlockedError: Request blocked by the site's protection (not an authorization issue):
#   https://api.cdnlibs.org/api/manga/262329--kidou-senshi-gundam-battle-operation-code-fairy?fields%5B%5D=background&...
#   The site may have changed which requests it accepts: check for an SDK update, or send different
#   headers via MangaLib(..., headers=...) / Catalog(headers=...). If the same URL doesn't open in a
#   browser on this network either, the IP itself is blocked and no header change will help.
# chapter 0: ok
# chapter 1: ok
# chapter 6: AuthRequiredError
# chapter 999: ChapterNotFoundError

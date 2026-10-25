"""Catching the SDK's custom exceptions.

All SDK-specific exceptions derive from RanobeLibError (see exceptions.py), so callers who
don't care about the distinction can catch just that base class. This script shows the two
most common ones: TitleNotFoundError (bad/removed title URL) and ChapterNotFoundError (valid
title, but the volume/chapter combination doesn't exist), plus AccessBlockedError — the site's
edge protection rejecting a request outright.

AccessBlockedError vs AuthRequiredError: both come from a 403, but they mean different things
and call for different fixes. AuthRequiredError is the API itself saying "this content needs a
logged-in user" (paid/early-access chapters) — nothing short of authorization helps.
AccessBlockedError is the DDoS-Guard filter in front of the API refusing the request before
the API ever sees it — so far because of missing browser-like headers, which the SDK already
sends. Seeing it in normal use means the site changed its rules (check for an SDK update) or
is blocking your IP (no header change helps then — try the same URL in a browser).

AuthRequiredError and RateLimitError (429 after retries are exhausted) aren't reliably
reproducible in a short standalone script (they need a paywalled title / sustained rate
limiting respectively) — see the API reference for their attributes.
"""

import asyncio

from ranobelib import (
    AccessBlockedError,
    ChapterNotFoundError,
    RanobeLib,
    TitleNotFoundError,
)


async def main() -> None:
    # A URL shaped like a valid title page, but for a title id that doesn't exist.
    async with RanobeLib("https://ranobelib.me/ru/book/1--this-title-does-not-exist-zzz") as lib:
        try:
            await lib.get_info()
        except TitleNotFoundError as exc:
            print(exc)

    # A real title, but a volume/chapter combination it doesn't have.
    async with RanobeLib("https://ranobelib.me/ru/book/91443--new-hero-in-dxd") as lib:
        try:
            await lib.get_chapter(volume=999, number="9999")
        except ChapterNotFoundError as exc:
            print(exc)

    # AccessBlockedError, reproduced on purpose. By default the SDK sends browser-like headers
    # the edge accepts; `headers=` merges overrides over them, and here it blanks out the
    # Referer — the edge filter rejects requests without a non-empty one (see
    # docs/api-notes.md, section "WAF 403"). The same `headers=` (on RanobeLib and Catalog
    # alike) is the escape hatch in the other direction too: sending what the edge expects
    # if the site's rules change before an SDK release catches up, e.g.
    # `headers={"User-Agent": "..."}`.
    async with RanobeLib(
        "https://ranobelib.me/ru/book/91443--new-hero-in-dxd", headers={"Referer": ""}
    ) as lib:
        try:
            # refresh=True skips the disk cache, so the request really goes out: a title
            # cached by an earlier run would otherwise be returned without touching the API.
            await lib.get_info(refresh=True)
        except AccessBlockedError as exc:
            # The message names the blocked request (also on exc.url) and what to try next.
            print(exc)


asyncio.run(main())

# Expected output (real run against the live site):
#
# Title not found: '1--this-title-does-not-exist-zzz'
# Chapter not found: '91443--new-hero-in-dxd' volume='999' number='9999'
# Request blocked by the site's protection (not an authorization issue):
# https://api.cdnlibs.org/api/manga/91443--new-hero-in-dxd?fields%5B%5D=background&...
# The site may have changed which requests it accepts: check for an SDK update, or send
# different headers via RanobeLib(..., headers=...) / Catalog(headers=...). If the same URL
# doesn't open in a browser on this network either, the IP itself is blocked and no header
# change will help.
#
# (The last message is printed as a single line, with the full fields[] query string in the
# URL; wrapped and shortened here to fit the line length.)

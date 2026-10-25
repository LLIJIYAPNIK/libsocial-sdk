"""Title URLs, sites and the headers every request carries.

The building blocks below everything else in libsocial-core. They make no requests.

- `parse_slug_url(source)`: a title's `{id}--{slug}` from a full URL on any lib.social site,
  or a bare one passed through; ValueError if there's none.
- `Site(id, origin)`: which site a client works for. The API is shared by the whole network
  and tells sites apart by id (the Site-Id header, site_id[] on catalog listings); the origin
  goes into the browser-like headers. The core knows no site by itself: ranobelib defines
  Site(3, "https://ranobelib.me"), mangalib Site(1, "https://mangalib.me").
- `browser_headers_for(origin)`: the Origin / Referer / User-Agent a browser on that site
  sends. The DDoS-Guard edge in front of the API refuses requests without a Referer, so every
  client sends these. `browser_headers(origin, overrides)`: the same as httpx.Headers, with
  your own merged over them — what `headers=` on the clients does — for your own HTTP client
  (covers, images) against the same edge.
"""

import httpx

from libsocial import Site, browser_headers, browser_headers_for, parse_slug_url

SLASHLIB = Site(id=2, origin="https://slashlib.me")


def main() -> None:
    # Any lib.social site, with or without the language prefix, query or fragment.
    for source in (
        "https://ranobelib.me/ru/book/6712--high-school-dxd-novel",
        "https://mangalib.me/ru/manga/7965--chainsaw-man?section=chapters",
        "https://slashlib.me/ru/manga/96466--old-clothes-collection-bin-of-love#comments",
        "7965--chainsaw-man",
    ):
        print(parse_slug_url(source))
    # A chapter's reader URL ends in its chapter, not the title, so it isn't accepted.
    for bad in (
        "https://mangalib.me/ru/manga",
        "chainsaw-man",
        "https://mangalib.me/ru/7965--chainsaw-man/read/v1/c1",
    ):
        try:
            parse_slug_url(bad)
        except ValueError as exc:
            print("ValueError:", exc)

    # Site is a frozen dataclass: hashable, comparable, checked on creation.
    same = Site(2, "https://slashlib.me")
    print(SLASHLIB, same == SLASHLIB, {SLASHLIB: "slashlib"}[same])
    for args in ((-1, "https://slashlib.me"), (2, "slashlib.me"), (2, "https://slashlib.me/")):
        try:
            Site(*args)
        except ValueError as exc:
            print("ValueError:", exc)

    print(browser_headers_for(SLASHLIB.origin))
    headers: httpx.Headers = browser_headers(SLASHLIB.origin, {"user-agent": "my-app/1.0"})
    # Keys merge case-insensitively, so "user-agent" replaced User-Agent.
    print(dict(headers))


main()

# Expected output (no requests are made, so this doesn't change):
#
# 6712--high-school-dxd-novel
# 7965--chainsaw-man
# 96466--old-clothes-collection-bin-of-love
# 7965--chainsaw-man
# ValueError: Could not extract a title slug from: 'https://mangalib.me/ru/manga'
# ValueError: Could not extract a title slug from: 'chainsaw-man'
# ValueError: Could not extract a title slug from:
#   'https://mangalib.me/ru/7965--chainsaw-man/read/v1/c1'
# Site(id=2, origin='https://slashlib.me') True slashlib
# ValueError: Site id must be >= 0, got -1.
# ValueError: Site origin must be a scheme://host URL without a trailing slash, got 'slashlib.me'.
# ValueError: Site origin must be a scheme://host URL without a trailing slash, got
#   'https://slashlib.me/'.
# {'Origin': 'https://slashlib.me', 'Referer': 'https://slashlib.me/', 'User-Agent': 'Mozilla/5.0
#   (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5
#   Mobile/15E148 Safari/604.1'}
# {'origin': 'https://slashlib.me', 'referer': 'https://slashlib.me/', 'user-agent': 'my-app/1.0'}

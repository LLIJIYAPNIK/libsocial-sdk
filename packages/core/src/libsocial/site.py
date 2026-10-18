"""``Site``: which lib.social site a client talks to the shared API on behalf of."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Site:
    """One lib.social site, as the shared api.cdnlibs.org API tells them apart.

    The core knows no site by itself: each site package defines its own (ranobelib.me is
    ``Site(id=3, origin="https://ranobelib.me")``, mangalib.me ``id=1``) and passes it in.

    Attributes:
        id: The site's id — sent as the ``Site-Id`` header on title/chapter requests and as
            ``site_id[]`` on catalog listings, and used to filter the network-wide
            ``/constants`` lists (genres, types, statuses) down to this site. Without the
            right one, the API answers 404 for titles that exist (see docs/api-notes.md).
        origin: The site's web origin, e.g. ``"https://ranobelib.me"`` — sent as
            ``Origin``/``Referer`` so requests look like they come from the site's own pages
            (see docs/api-notes.md, section "WAF 403"), and the base for site-relative URLs.
    """

    id: int
    origin: str

    def __post_init__(self) -> None:
        if self.id < 0:
            raise ValueError(f"Site id must be >= 0, got {self.id}.")
        if not self.origin.startswith(("https://", "http://")) or self.origin.endswith("/"):
            raise ValueError(
                f"Site origin must be a scheme://host URL without a trailing slash, "
                f"got {self.origin!r}."
            )

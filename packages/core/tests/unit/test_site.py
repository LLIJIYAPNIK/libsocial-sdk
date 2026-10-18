"""Unit tests for libsocial.site.Site and the browser headers built from it."""

import pytest

from libsocial import browser_headers
from libsocial.site import Site


def test_site_holds_id_and_origin(site: Site) -> None:
    assert site.id in (1, 3)
    assert site.origin.startswith("https://")


def test_site_is_hashable_and_compared_by_value() -> None:
    assert Site(id=3, origin="https://ranobelib.me") == Site(id=3, origin="https://ranobelib.me")
    assert len({Site(id=3, origin="https://ranobelib.me")} | {Site(3, "https://ranobelib.me")}) == 1


@pytest.mark.parametrize(
    ("site_id", "origin"),
    [
        (-1, "https://ranobelib.me"),
        (3, "ranobelib.me"),
        (3, "https://ranobelib.me/"),
    ],
)
def test_site_rejects_invalid_values(site_id: int, origin: str) -> None:
    with pytest.raises(ValueError):
        Site(id=site_id, origin=origin)


def test_browser_headers_point_at_the_site(site: Site) -> None:
    headers = browser_headers(site.origin)

    assert headers["Origin"] == site.origin
    assert headers["Referer"] == f"{site.origin}/"
    assert headers["User-Agent"].startswith("Mozilla/5.0 (iPhone;")


def test_browser_headers_overrides_replace_case_insensitively(site: Site) -> None:
    headers = browser_headers(site.origin, {"user-agent": "CustomAgent/1.0", "X-Extra": "yes"})

    assert headers.get_list("User-Agent") == ["CustomAgent/1.0"]
    assert headers["X-Extra"] == "yes"
    assert headers["Referer"] == f"{site.origin}/"

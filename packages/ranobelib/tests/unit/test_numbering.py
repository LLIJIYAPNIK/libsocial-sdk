"""Unit tests for ranobelib.numbering."""

import pytest

from ranobelib.numbering import parse_slug_url


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (
            "https://ranobelib.me/ru/book/6712--high-school-dxd-novel",
            "6712--high-school-dxd-novel",
        ),
        (
            "https://ranobelib.me/book/6712--high-school-dxd-novel",
            "6712--high-school-dxd-novel",
        ),
        (
            "https://ranobelib.me/ru/book/6712--high-school-dxd-novel?tab=info",
            "6712--high-school-dxd-novel",
        ),
        (
            "https://ranobelib.me/ru/book/6712--high-school-dxd-novel/",
            "6712--high-school-dxd-novel",
        ),
        ("6712--high-school-dxd-novel", "6712--high-school-dxd-novel"),
    ],
)
def test_parse_slug_url_extracts_slug(source: str, expected: str) -> None:
    assert parse_slug_url(source) == expected


@pytest.mark.parametrize(
    "source",
    [
        "https://ranobelib.me/ru/catalog",
        "not-a-valid-slug",
        "",
        "https://ranobelib.me/ru/book/",
    ],
)
def test_parse_slug_url_rejects_invalid_input(source: str) -> None:
    with pytest.raises(ValueError, match="Could not extract a title slug"):
        parse_slug_url(source)

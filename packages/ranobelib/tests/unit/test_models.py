"""Unit tests for ranobelib.models."""

from datetime import UTC, datetime
from typing import Any

import pytest

from ranobelib.models import Country, Title

RAW_TITLE: dict[str, Any] = {
    "id": 91443,
    "name": "New Hero in DxD",
    "rus_name": "Новый герой в мире DXD (Новелла)",
    "eng_name": "New Hero in DxD (Novel)",
    "otherNames": [],
    "model": "manga",
    "slug": "new-hero-in-dxd",
    "slug_url": "91443--new-hero-in-dxd",
    "cover": {
        "filename": "CuhkYTqxqJc0",
        "thumbnail": "https://cover.cdnlibs.org/.../thumb.jpg",
        "default": "https://cover.cdnlibs.org/.../250x350.jpg",
        "md": "https://cover.cdnlibs.org/.../250x350.jpg",
    },
    "ageRestriction": {"id": 1, "label": "6+"},
    "site": 3,
    "type": {"id": 15, "label": "Фанфик"},
    "summary": {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": "Первый абзац."}],
            },
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "Второй "},
                    {"type": "text", "text": "абзац."},
                ],
            },
        ],
    },
    "releaseDate": "2021",
    "is_licensed": False,
    "teams": [
        {
            "id": 23286,
            "slug": "stixs-team",
            "slug_url": "23286--stixs-team",
            "model": "team",
            "name": "Stixs TEAM",
        }
    ],
    "genres": [{"id": 37, "name": "Гарем", "adult": False, "alert": False}],
    "tags": [{"id": 218, "name": "Богиня", "adult": False, "alert": False}],
    "authors": [
        {
            "id": 57847,
            "slug": "kingch",
            "slug_url": "57847--kingch",
            "model": "people",
            "name": "kingCH",
            "rus_name": None,
        }
    ],
    "content_marking": [],
    "status": {"id": 1, "label": "Онгоинг"},
    "items_count": {"uploaded": 47, "total": 0},
    "last_item_at": "2022-02-23T13:26:48.000000Z",
    "scanlateStatus": {"id": 4, "label": "Забросили"},
    "artists": [],
    "releaseDateString": "2021 г.",
}


def test_title_model_validate_maps_aliases_and_nested_models() -> None:
    title = Title.model_validate(RAW_TITLE)

    assert title.id == 91443
    assert title.name == "New Hero in DxD"
    assert title.rus_name == "Новый герой в мире DXD (Новелла)"
    assert title.other_names == []
    assert title.slug_url == "91443--new-hero-in-dxd"
    assert title.cover.filename == "CuhkYTqxqJc0"
    assert title.age_restriction.label == "6+"
    assert title.status.label == "Онгоинг"
    assert title.release_date == "2021"
    assert title.teams[0].name == "Stixs TEAM"
    assert title.genres[0].name == "Гарем"
    assert title.tags[0].name == "Богиня"
    assert title.authors[0].name == "kingCH"
    assert title.artists == []
    assert title.country == Country(id=15, name="Фанфик")


def test_title_model_parses_prosemirror_summary_to_text() -> None:
    title = Title.model_validate(RAW_TITLE)

    assert title.summary == "Первый абзац.\n\nВторой абзац."


def test_title_model_flattens_chapter_count_from_items_count() -> None:
    title = Title.model_validate(RAW_TITLE)

    assert title.chapter_count == 47


def test_title_model_chapter_count_is_none_without_items_count() -> None:
    raw = {k: v for k, v in RAW_TITLE.items() if k != "items_count"}

    title = Title.model_validate(raw)

    assert title.chapter_count is None


def test_title_model_parses_last_item_at_as_last_chapter_at() -> None:
    title = Title.model_validate(RAW_TITLE)

    assert title.last_chapter_at == datetime(2022, 2, 23, 13, 26, 48, tzinfo=UTC)


def test_title_model_summary_none_stays_none() -> None:
    raw = {**RAW_TITLE, "summary": None}

    title = Title.model_validate(raw)

    assert title.summary is None


def test_title_model_summary_accepts_plain_string() -> None:
    raw = {**RAW_TITLE, "summary": "Already plain text."}

    title = Title.model_validate(raw)

    assert title.summary == "Already plain text."


def test_title_model_handles_missing_optional_fields() -> None:
    minimal = {
        "id": 1,
        "name": "Minimal Title",
        "slug": "minimal-title",
        "slug_url": "1--minimal-title",
        "cover": {},
        "ageRestriction": {"id": 1, "label": "6+"},
        "status": {"id": 1, "label": "Онгоинг"},
    }

    title = Title.model_validate(minimal)

    assert title.summary is None
    assert title.chapter_count is None
    assert title.last_chapter_at is None
    assert title.other_names == []
    assert title.genres == []
    assert title.country is None


def test_country_maps_label_to_name() -> None:
    country = Country.model_validate({"id": 10, "label": "Япония"})

    assert country.id == 10
    assert country.name == "Япония"


def test_country_accepts_name_by_field_name_too() -> None:
    country = Country(id=10, name="Япония")

    assert country.name == "Япония"


def _title_named(**names: Any) -> Title:
    return Title.model_validate({**RAW_TITLE, "rus_name": None, "eng_name": None, **names})


def test_base_names_strips_format_suffix_in_field_order() -> None:
    title = Title.model_validate(
        {
            **RAW_TITLE,
            "rus_name": "Старшая школа D×D (Новелла)",
            "eng_name": "High School D×D (Novel)",
            "name": "Haisukuru Di Di",
            "otherNames": ["Демоны старшей школы", "ハイスクールD×D"],
        }
    )

    assert title.base_names == [
        "Старшая школа D×D",
        "High School D×D",
        "Haisukuru Di Di",
        "Демоны старшей школы",
        "ハイスクールD×D",
    ]
    assert title.rus_name == "Старшая школа D×D (Новелла)"  # the field itself is unchanged


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        # Every spelling family seen in the live catalog (docs/api-notes.md).
        ("Добро пожаловать в класс превосходства (LN)", "Добро пожаловать в класс превосходства"),
        ("Токийский гуль: Перерождение [квест]", "Токийский гуль: Перерождение"),
        ("A (WN)", "A"),
        ("A (novel)", "A"),
        ("A (Novella)", "A"),
        ("A (Novell)", "A"),
        ("A (Light Novel)", "A"),
        ("A (light novel)", "A"),
        ("A (Web Novel)", "A"),
        ("A (webnovel)", "A"),
        ("A (web-novel)", "A"),
        ("A (web serial)", "A"),
        ("A (Lite-Novel)", "A"),
        ("A (Webnovela)", "A"),
        ("A (Ranobe)", "A"),
        ("A (Ранобэ)", "A"),
        ("A (новелла)", "A"),
        ("A (новела)", "A"),
        ("A (Лайт-новелла)", "A"),
        ("A (Лайт Новелла)", "A"),
        ("A (Веб-Новелла)", "A"),
        ("A ( веб - новелла)", "A"),
        ("A (Вэб Новелла)", "A"),
        ("A (ЛН)", "A"),
        ("A (лн)", "A"),
        ("A [quest]", "A"),
        ("A [ln]", "A"),
        ("A ( LN )", "A"),
        ("A ( Новелла)", "A"),
        # Stacked markers.
        ("A (LN) (Novel)", "A"),
        ("A (WN) (Новелла)", "A"),
        ("A (новелла) (Novel)", "A"),
        ("A (Вэб Новелла) (WN)", "A"),
        # A separator left in front of the marker goes with it...
        ("Цитрусовый маг, (Новелла)", "Цитрусовый маг"),
        ("Bundrion Koko no Shuren: (Novel)", "Bundrion Koko no Shuren"),
        ("Dansou Shoujo wa Kishi wo Mezasu! / (Novel)", "Dansou Shoujo wa Kishi wo Mezasu!"),
        # ...but a dash closing a subtitle is part of the name.
        (
            "Devil May Cry 5 -Before the Nightmare- (Novel)",
            "Devil May Cry 5 -Before the Nightmare-",
        ),
        # Bracketed tails that aren't the format stay.
        ("Тёмный Путь: Эхо Убийц (Перезапуск) (Новелла)", "Тёмный Путь: Эхо Убийц (Перезапуск)"),
        ("A (Фанфик)", "A (Фанфик)"),
        ("A (18+)", "A (18+)"),
        ("A (2013)", "A (2013)"),
        ("A [LitRPG]", "A [LitRPG]"),
        ("A (Oneshot)", "A (Oneshot)"),
        ("A (Star Wars) (Novel)", "A (Star Wars)"),
        # Only a whole bracketed marker at the very end counts.
        ("Novel (LN) Academy", "Novel (LN) Academy"),
        ("My Light Novel", "My Light Novel"),
        ("A (Novelist)", "A (Novelist)"),
        ("A (LN", "A (LN"),
    ],
)
def test_base_names_suffix_rules(name: str, expected: str) -> None:
    assert _title_named(name=name).base_names == [expected]


def test_base_names_drops_duplicates_and_empty_names() -> None:
    title = _title_named(
        rus_name=" (Новелла)",  # nothing left once the marker goes
        eng_name="Same (Novel)",
        name="Same (LN)",
        otherNames=["", "Same", "Other\xa0", "Other"],
    )

    assert title.base_names == ["Same", "Other"]


def test_base_names_skips_missing_optional_names() -> None:
    assert _title_named(name="Only (Novel)").base_names == ["Only"]

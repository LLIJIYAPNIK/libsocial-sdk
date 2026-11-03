"""Unit tests for libsocial.models."""

from datetime import UTC, datetime
from typing import Any

from libsocial.models import CatalogPage, Country, Relation, Title

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


def test_title_leaves_site_specific_name_handling_to_the_site_package() -> None:
    # Stripping "(Новелла)"/"(LN)"-style format suffixes is ranobelib.me's, not the core's.
    title = Title.model_validate(RAW_TITLE)

    assert not hasattr(title, "base_names")
    assert title.rus_name == "Новый герой в мире DXD (Новелла)"


class _SiteTitle(Title):
    @property
    def shout(self) -> str:
        return self.name.upper()


def test_catalog_page_validates_items_as_the_given_title_model() -> None:
    page = CatalogPage[_SiteTitle].model_validate(
        {"items": [RAW_TITLE], "page": 1, "has_next_page": False}
    )

    assert isinstance(page.items[0], _SiteTitle)
    assert page.items[0].shout == "NEW HERO IN DXD"


# Trimmed from GET /api/manga/6712--high-school-dxd-novel/relations: a readable title on
# ranobelib.me (with the novel-only "edition" field) and an anime on anilib.me (with its own
# extra fields), both ignored by the model.
RAW_NOVEL_RELATION: dict[str, Any] = {
    "order": 0,
    "related_type": {"id": 4, "label": "Продолжение"},
    "media": {
        "id": 22513,
        "name": "Shin Haisukuru Di Di",
        "rus_name": "Истинная Старшая Школа D×D",
        "eng_name": "True High School D×D",
        "model": "manga",
        "slug": "shin-high-school-dxd",
        "slug_url": "22513--shin-high-school-dxd",
        "cover": {"filename": "HaRtTLeDuYc3", "default": "https://cover.imglib.info/x.jpg"},
        "ageRestriction": {"id": 3, "label": "16+"},
        "site": 3,
        "type": {"id": 10, "label": "Япония"},
        "content_marking": [],
        "status": {"id": 4, "label": "Приостановлен"},
        "edition": {"id": 9, "slug": "light-novel", "name": "Лайт-новелла", "short_name": "LN"},
        "releaseDateString": "",
    },
}
RAW_ANIME_RELATION: dict[str, Any] = {
    "order": 9,
    "related_type": {"id": 1, "label": "Адаптация"},
    "media": {
        "id": 6515,
        "name": "High School DxD",
        "rus_name": "Старшая школа DxD",
        "eng_name": None,
        "model": "anime",
        "slug": "high-school-dxd-anime",
        "slug_url": "6515--high-school-dxd-anime",
        "cover": {"filename": "04071c37"},
        "ageRestriction": {"id": 4, "label": "R+"},
        "site": 5,
        "type": {"id": 16, "label": "TV Сериал"},
        "content_marking": [],
        "status": {"id": 2, "label": "Завершён"},
        "releaseDateString": "",
        "anilist_id": None,
        "shiki_rate": None,
    },
}


def test_relation_maps_the_raw_field_names() -> None:
    relation = Relation.model_validate(RAW_NOVEL_RELATION)

    assert relation.type.id == 4
    assert relation.type.label == "Продолжение"
    media = relation.media
    assert media.slug_url == "22513--shin-high-school-dxd"
    assert media.kind == "manga"
    assert media.site_id == 3
    assert media.age_restriction is not None and media.age_restriction.label == "16+"
    assert media.status is not None and media.status.id == 4
    assert media.type is not None and media.type.label == "Япония"
    assert media.cover.default == "https://cover.imglib.info/x.jpg"


def test_relation_to_an_anime_on_another_site() -> None:
    media = Relation.model_validate(RAW_ANIME_RELATION).media

    assert media.kind == "anime"
    assert media.site_id == 5
    assert media.eng_name is None
    assert media.type is not None and media.type.label == "TV Сериал"  # A format, not a country.


def test_related_media_needs_only_identity_fields() -> None:
    relation = Relation.model_validate(
        {
            "related_type": {"id": 10, "label": "Другое"},
            "media": {
                "id": 1,
                "name": "X",
                "slug": "x",
                "slug_url": "1--x",
                "model": "manga",
                "site": 1,
            },
        }
    )

    assert relation.media.status is None
    assert relation.media.age_restriction is None
    assert relation.media.cover.default is None


def test_relation_round_trips_through_model_dump() -> None:
    relation = Relation.model_validate(RAW_ANIME_RELATION)

    assert Relation.model_validate(relation.model_dump()) == relation
    assert Relation.model_validate(relation.model_dump(by_alias=True)) == relation

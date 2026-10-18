"""Unit tests for mangalib.models."""

from typing import Any

import pytest

from mangalib.models import Chapter, ChapterBranch, Page, RestrictedView, Title, Volume


def _branch(**extra: Any) -> dict[str, Any]:
    return {
        "id": 1,
        "branch_id": 10,
        "created_at": "2026-10-01T00:00:00.000000Z",
        "teams": [],
        "user": {"id": 1, "username": "uploader"},
        **extra,
    }


def _page(slug: int) -> dict[str, Any]:
    return {
        "id": 100 + slug,
        "image": f"{slug:02}.jpg",
        "slug": slug,
        "external": 0,
        "chunks": 1,
        "chapter_id": 5,
        "height": 2048,
        "width": 1425,
        "url": f"//manga/example/chapters/1-1/{slug:02}.jpg",
        "ratio": "0.6958",
    }


def test_page_maps_slug_to_number_and_ignores_unmodelled_fields() -> None:
    page = Page.model_validate(_page(3))

    assert page.number == 3
    assert page.image == "03.jpg"
    assert page.url == "//manga/example/chapters/1-1/03.jpg"
    assert (page.width, page.height) == (1425, 2048)


def test_branch_without_restricted_view_is_open() -> None:
    branch = ChapterBranch.model_validate(_branch())

    assert branch.restricted_view is None
    assert branch.is_open


def test_branch_with_closed_restricted_view_is_not_open() -> None:
    branch = ChapterBranch.model_validate(
        _branch(
            restricted_view={"is_open": False, "expired_at": "2026-10-23T05:05:00Z", "price": None}
        )
    )

    assert branch.restricted_view is not None
    assert branch.restricted_view.expired_at is not None
    assert not branch.is_open


def test_branch_with_opened_restricted_view_is_open() -> None:
    branch = ChapterBranch.model_validate(_branch(restricted_view={"is_open": True}))

    assert branch.is_open


def test_chapter_validates_its_branches_and_pages_as_mangalib_models() -> None:
    chapter = Chapter.model_validate(
        {
            "id": 5,
            "volume": "1",
            "number": "1",
            "branches": [_branch(restricted_view={"is_open": False})],
            "pages": [_page(1), _page(2)],
            "restricted_view": {"is_open": True, "price": 15, "can_open_with_content_key": False},
        }
    )

    assert isinstance(chapter.branches[0], ChapterBranch)
    assert not chapter.branches[0].is_open
    assert [page.number for page in chapter.pages] == [1, 2]
    assert chapter.restricted_view == RestrictedView(is_open=True, price=15)


def test_chapter_from_the_chapter_list_has_no_pages() -> None:
    chapter = Chapter.model_validate({"id": 5, "volume": "1", "number": "1"})

    assert chapter.pages == []
    assert chapter.restricted_view is None


def test_volume_round_trips_its_chapters_pages() -> None:
    volume = Volume(
        number="1",
        chapters=[
            Chapter.model_validate({"id": 5, "volume": "1", "number": "1", "pages": [_page(1)]})
        ],
    )

    restored = Volume.model_validate(volume.model_dump())

    assert restored.chapters[0].pages[0].number == 1
    assert restored == volume


def _title(**names: Any) -> Title:
    return Title.model_validate(
        {
            "id": 1,
            "name": "x",
            "slug": "x",
            "slug_url": "1--x",
            "cover": {},
            "ageRestriction": {"id": 0, "label": "Нет"},
            "status": {"id": 1, "label": "Онгоинг"},
            **names,
        }
    )


@pytest.mark.parametrize(
    ("name", "base"),
    [
        ("Return of the Runebound Professor (webtoon)", "Return of the Runebound Professor"),
        ("Исаак [Вебтун]", "Исаак"),
        ("Вайолет: Сердце помнит (Манга)", "Вайолет: Сердце помнит"),
        ("geu noyedeul-ui sayugbeob (manhwa)", "geu noyedeul-ui sayugbeob"),
        ("Black and White (Manhua)", "Black and White"),
        ("Руины (Комикс)", "Руины"),
        ("Lordran & Beyond  (comic book)", "Lordran & Beyond"),
        ("Zannen desu ne. Himekishi-sensei (Webcomic)", "Zannen desu ne. Himekishi-sensei"),
        ("Agdangdeul-eul Wihan Donghwa(webtoon)", "Agdangdeul-eul Wihan Donghwa"),
        ("Skullgirls, (WEBTOON) (Manhwa)", "Skullgirls"),
        # Tails that tell titles or versions apart stay.
        ("Вакфу: Великая Волна (манга-версия)", "Вакфу: Великая Волна (манга-версия)"),
        ("Gangcheolui yeongeumsulsa (Color Webtoon)", "Gangcheolui yeongeumsulsa (Color Webtoon)"),
        ("Gravity Falls: Adults (Fan Comics)", "Gravity Falls: Adults (Fan Comics)"),
        ("Bleach (Doujinshi)", "Bleach (Doujinshi)"),
        ("Chainsaw Man (Colored)", "Chainsaw Man (Colored)"),
        ("Heroines - One Piece (novel)", "Heroines - One Piece (novel)"),
    ],
)
def test_base_names_strip_only_bare_format_markers(name: str, base: str) -> None:
    assert _title(name=name).base_names == [base]


def test_base_names_keep_order_and_drop_empty_and_duplicate_names() -> None:
    title = _title(
        rus_name="Золотой час (вебтун)",
        eng_name="",
        name="Golden Hour (webtoon)",
        otherNames=["Golden Hour", "(Manga)", "황금시간"],
    )

    assert title.base_names == ["Золотой час", "Golden Hour", "황금시간"]
    assert title.name == "Golden Hour (webtoon)"

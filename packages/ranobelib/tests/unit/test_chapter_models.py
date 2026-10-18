"""Unit tests for ranobelib.models.Chapter/ChapterBranch/Volume."""

from datetime import datetime
from typing import Any

from ranobelib.models import Chapter, Volume

RAW_CHAPTER: dict[str, Any] = {
    "id": 1599920,
    "index": 1,
    "item_number": 1,
    "volume": "0",
    "number": "1",
    "number_secondary": "0",
    "name": "(НЕ ГОТОВО) Возможный гарем",
    "branches_count": 1,
    "branches": [
        {
            "id": 1599920,
            "branch_id": None,
            "created_at": "2021-08-20T08:40:09.000000Z",
            "teams": [
                {
                    "id": 23286,
                    "slug": "stixs-team",
                    "slug_url": "23286--stixs-team",
                    "model": "team",
                    "name": "Stixs TEAM",
                }
            ],
            "expired_type": 0,
            "user": {"username": "stixs", "id": 1188113},
        }
    ],
    "bundle_id": None,
}


def test_chapter_model_validate_maps_fields() -> None:
    chapter = Chapter.model_validate(RAW_CHAPTER)

    assert chapter.id == 1599920
    assert chapter.volume == "0"
    assert chapter.number == "1"
    assert chapter.name == "(НЕ ГОТОВО) Возможный гарем"
    assert chapter.index == 1
    assert chapter.item_number == 1
    assert chapter.branches_count == 1
    assert chapter.bundle_id is None


def test_chapter_model_ignores_unrelated_number_secondary_field() -> None:
    # number_secondary mirrors volume in the real API and carries no extra information the
    # SDK needs (see docs/api-notes.md) — the model simply doesn't map it to anything.
    chapter = Chapter.model_validate(RAW_CHAPTER)

    assert not hasattr(chapter, "number_secondary")


def test_chapter_model_accepts_fractional_number() -> None:
    raw = {**RAW_CHAPTER, "number": "6.5"}

    chapter = Chapter.model_validate(raw)

    assert chapter.number == "6.5"


def test_chapter_model_parses_branch_and_team() -> None:
    chapter = Chapter.model_validate(RAW_CHAPTER)

    branch = chapter.branches[0]
    assert branch.id == 1599920
    assert branch.branch_id is None
    assert branch.created_at == datetime.fromisoformat("2021-08-20T08:40:09+00:00")
    assert branch.user.id == 1188113
    assert branch.user.username == "stixs"
    assert branch.teams[0].name == "Stixs TEAM"


def test_chapter_model_handles_missing_name() -> None:
    raw = {k: v for k, v in RAW_CHAPTER.items() if k != "name"}

    chapter = Chapter.model_validate(raw)

    assert chapter.name is None


def test_chapter_model_handles_no_branches() -> None:
    raw = {**RAW_CHAPTER, "branches": [], "branches_count": 0}

    chapter = Chapter.model_validate(raw)

    assert chapter.branches == []


def test_volume_model_holds_number_and_chapters() -> None:
    chapter = Chapter.model_validate(RAW_CHAPTER)

    volume = Volume(number="0", chapters=[chapter])

    assert volume.number == "0"
    assert volume.chapters == [chapter]


def test_volume_model_defaults_to_empty_chapter_list() -> None:
    volume = Volume(number="1")

    assert volume.chapters == []

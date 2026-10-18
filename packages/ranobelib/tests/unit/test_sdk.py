"""Unit tests for ranobelib.sdk helpers."""

import io
from pathlib import Path
from typing import Any

import pytest
from rich.console import Console

from ranobelib.console import Reporter
from ranobelib.exceptions import (
    AccessBlockedError,
    DownloadTitleInterruptedError,
    RateLimitError,
)
from ranobelib.exporters import EXPORTERS
from ranobelib.models import Chapter, Title
from ranobelib.sdk import RanobeLib, _group_into_volumes, _resolve_bulk_branch_id


def _chapter(*, volume: str, number: str, index: int) -> Chapter:
    return Chapter.model_validate(
        {
            "id": index,
            "volume": volume,
            "number": number,
            "name": f"Chapter {number}",
            "index": index,
            "item_number": index,
            "branches_count": 0,
            "branches": [],
            "bundle_id": None,
        }
    )


def test_group_into_volumes_preserves_api_order() -> None:
    chapters = [
        _chapter(volume="1", number="1", index=1),
        _chapter(volume="1", number="2", index=2),
        _chapter(volume="2", number="3", index=3),
    ]

    volumes = _group_into_volumes(chapters)

    assert [v.number for v in volumes] == ["1", "2"]
    assert [c.number for c in volumes[0].chapters] == ["1", "2"]
    assert [c.number for c in volumes[1].chapters] == ["3"]


def test_group_into_volumes_handles_empty_list() -> None:
    assert _group_into_volumes([]) == []


def test_group_into_volumes_keeps_first_seen_volume_order_even_if_interleaved() -> None:
    chapters = [
        _chapter(volume="0", number="0.1", index=1),
        _chapter(volume="1", number="1", index=2),
        _chapter(volume="0", number="0.2", index=3),
    ]

    volumes = _group_into_volumes(chapters)

    assert [v.number for v in volumes] == ["0", "1"]
    assert [c.number for c in volumes[0].chapters] == ["0.1", "0.2"]


def _raw_branch(branch_id: int) -> dict[str, int]:
    return {"id": branch_id * 1000, "branch_id": branch_id}


def test_resolve_bulk_branch_id_matches_branch_id_regardless_of_position() -> None:
    branches = [_raw_branch(635), _raw_branch(2251)]

    resolved, selected = _resolve_bulk_branch_id(branches, branch_id=2251, translation_index=None)

    assert resolved is True
    assert selected == 2251


def test_resolve_bulk_branch_id_fails_when_branch_id_not_among_branches() -> None:
    branches = [_raw_branch(635), _raw_branch(2251)]

    resolved, selected = _resolve_bulk_branch_id(branches, branch_id=999, translation_index=None)

    assert resolved is False
    assert selected is None


def test_resolve_bulk_branch_id_uses_translation_index_position() -> None:
    branches = [_raw_branch(635), _raw_branch(2251)]

    resolved, selected = _resolve_bulk_branch_id(branches, branch_id=None, translation_index=1)

    assert resolved is True
    assert selected == 2251


def test_resolve_bulk_branch_id_fails_when_translation_index_out_of_range() -> None:
    branches = [_raw_branch(635), _raw_branch(2251)]

    resolved, selected = _resolve_bulk_branch_id(branches, branch_id=None, translation_index=5)

    assert resolved is False
    assert selected is None


def test_resolve_bulk_branch_id_fails_when_neither_option_given() -> None:
    branches = [_raw_branch(635), _raw_branch(2251)]

    resolved, selected = _resolve_bulk_branch_id(branches, branch_id=None, translation_index=None)

    assert resolved is False
    assert selected is None


def _raw_toc_chapter(
    volume: str, number: str, *, branches: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    return {"volume": volume, "number": number, "branches": branches or []}


def _fake_content_chapter(volume_str: str, number: str, branch_id: int | None) -> Chapter:
    return Chapter.model_validate(
        {"id": 1, "volume": volume_str, "number": number, "content": "<p>" + "x" * 40 + "</p>"}
    )


async def test_estimate_title_size_samples_evenly_and_extrapolates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_chapters = [_raw_toc_chapter("1", str(index)) for index in range(10)]
    fetched: list[str] = []

    async def fake_get_chapters(*, refresh: bool = False) -> list[dict[str, Any]]:
        return raw_chapters

    async def fake_fetch_chapter(
        volume_str: str, number: str, branch_id: int | None, *, refresh: bool = False
    ) -> Chapter:
        fetched.append(number)
        return _fake_content_chapter(volume_str, number, branch_id)

    async with RanobeLib("1--slug") as lib:
        monkeypatch.setattr(lib, "_get_chapters", fake_get_chapters)
        monkeypatch.setattr(lib, "_fetch_chapter", fake_fetch_chapter)

        estimate = await lib.estimate_title_size(sample_size=3)

    # Evenly spread across all 10 chapters, not just the first 3.
    assert fetched == ["0", "3", "6"]
    assert estimate > 0


async def test_estimate_title_size_clamps_sample_size_to_chapter_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_chapters = [_raw_toc_chapter("1", str(index)) for index in range(2)]
    fetched: list[str] = []

    async def fake_get_chapters(*, refresh: bool = False) -> list[dict[str, Any]]:
        return raw_chapters

    async def fake_fetch_chapter(
        volume_str: str, number: str, branch_id: int | None, *, refresh: bool = False
    ) -> Chapter:
        fetched.append(number)
        return _fake_content_chapter(volume_str, number, branch_id)

    async with RanobeLib("1--slug") as lib:
        monkeypatch.setattr(lib, "_get_chapters", fake_get_chapters)
        monkeypatch.setattr(lib, "_fetch_chapter", fake_fetch_chapter)

        await lib.estimate_title_size(sample_size=5)

    assert fetched == ["0", "1"]


async def test_estimate_title_size_skips_unresolved_ambiguous_chapters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_chapters = [
        _raw_toc_chapter("1", "0", branches=[_raw_branch(1), _raw_branch(2)]),
        _raw_toc_chapter("1", "1"),
    ]
    fetched: list[str] = []

    async def fake_get_chapters(*, refresh: bool = False) -> list[dict[str, Any]]:
        return raw_chapters

    async def fake_fetch_chapter(
        volume_str: str, number: str, branch_id: int | None, *, refresh: bool = False
    ) -> Chapter:
        fetched.append(number)
        return _fake_content_chapter(volume_str, number, branch_id)

    async with RanobeLib("1--slug") as lib:
        monkeypatch.setattr(lib, "_get_chapters", fake_get_chapters)
        monkeypatch.setattr(lib, "_fetch_chapter", fake_fetch_chapter)

        estimate = await lib.estimate_title_size()

    # Chapter "0" is ambiguous with no branch_id/translation_index to resolve it — skipped as
    # a sampling candidate rather than raising, unlike download_title().
    assert fetched == ["1"]
    assert estimate > 0


async def test_estimate_title_size_resolves_ambiguous_chapter_via_branch_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_chapters = [
        _raw_toc_chapter("1", "0", branches=[_raw_branch(635), _raw_branch(2251)]),
        _raw_toc_chapter("1", "1"),
    ]
    fetched: list[tuple[str, int | None]] = []

    async def fake_get_chapters(*, refresh: bool = False) -> list[dict[str, Any]]:
        return raw_chapters

    async def fake_fetch_chapter(
        volume_str: str, number: str, branch_id: int | None, *, refresh: bool = False
    ) -> Chapter:
        fetched.append((number, branch_id))
        return _fake_content_chapter(volume_str, number, branch_id)

    async with RanobeLib("1--slug") as lib:
        monkeypatch.setattr(lib, "_get_chapters", fake_get_chapters)
        monkeypatch.setattr(lib, "_fetch_chapter", fake_fetch_chapter)

        estimate = await lib.estimate_title_size(branch_id=2251)

    # Both chapters resolve now: "0" via the given branch_id, "1" has no ambiguity at all.
    assert fetched == [("0", 2251), ("1", None)]
    assert estimate > 0


async def test_estimate_title_size_returns_zero_when_no_chapter_resolves(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_chapters = [_raw_toc_chapter("1", "0", branches=[_raw_branch(1), _raw_branch(2)])]

    async def fake_get_chapters(*, refresh: bool = False) -> list[dict[str, Any]]:
        return raw_chapters

    async with RanobeLib("1--slug") as lib:
        monkeypatch.setattr(lib, "_get_chapters", fake_get_chapters)

        estimate = await lib.estimate_title_size()

    assert estimate == 0


async def test_estimate_title_size_returns_zero_for_title_with_no_chapters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_get_chapters(*, refresh: bool = False) -> list[dict[str, Any]]:
        return []

    async with RanobeLib("1--slug") as lib:
        monkeypatch.setattr(lib, "_get_chapters", fake_get_chapters)

        estimate = await lib.estimate_title_size()

    assert estimate == 0


async def test_estimate_title_size_raises_value_error_when_both_selectors_given() -> None:
    async with RanobeLib("1--slug") as lib:
        with pytest.raises(ValueError, match="not both"):
            await lib.estimate_title_size(branch_id=1, translation_index=0)


async def test_estimate_title_size_raises_value_error_for_non_positive_sample_size() -> None:
    async with RanobeLib("1--slug") as lib:
        with pytest.raises(ValueError, match="sample_size"):
            await lib.estimate_title_size(sample_size=0)


def _reporter_with_buffer(verbosity: str) -> tuple[Reporter, io.StringIO]:
    buffer = io.StringIO()
    console = Console(file=buffer, force_terminal=False, width=80)
    return Reporter(verbosity, console=console), buffer  # type: ignore[arg-type]


async def test_download_title_progress_bar_shows_up_in_progress_only_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_chapters = [_raw_toc_chapter("1", str(index)) for index in range(3)]

    async def fake_get_chapters(*, refresh: bool = False) -> list[dict[str, Any]]:
        return raw_chapters

    async def fake_fetch_chapter(
        volume_str: str, number: str, branch_id: int | None, *, refresh: bool = False
    ) -> Chapter:
        return _fake_content_chapter(volume_str, number, branch_id)

    reporter, buffer = _reporter_with_buffer("progress_only")
    async with RanobeLib("1--slug") as lib:
        monkeypatch.setattr(lib, "_get_chapters", fake_get_chapters)
        monkeypatch.setattr(lib, "_fetch_chapter", fake_fetch_chapter)
        lib._reporter = reporter

        await lib.download_title()

    assert "1--slug" in buffer.getvalue()


async def test_download_title_full_mode_logs_cache_and_api_fetches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_chapters = [_raw_toc_chapter("1", "0")]

    async def fake_get_chapters(*, refresh: bool = False) -> list[dict[str, Any]]:
        return raw_chapters

    reporter, buffer = _reporter_with_buffer("full")
    async with RanobeLib("1--slug") as lib:
        monkeypatch.setattr(lib, "_get_chapters", fake_get_chapters)
        lib._reporter = reporter
        # Prime the disk cache for chapter "0" so the fetch is served from cache, not the API.
        lib._cache.set("chapter:1--slug:1:0:None", {"id": 1, "volume": "1", "number": "0"})

        await lib.download_title()

    output = buffer.getvalue()
    assert "[cache] chapter 1/0" in output


async def test_download_title_retries_past_a_rate_limit_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_chapters = [_raw_toc_chapter("1", str(index)) for index in range(3)]
    sleeps: list[float] = []
    attempts_for_chapter_1 = 0

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    async def fake_get_chapters(*, refresh: bool = False) -> list[dict[str, Any]]:
        return raw_chapters

    async def fake_fetch_chapter(
        volume_str: str, number: str, branch_id: int | None, *, refresh: bool = False
    ) -> Chapter:
        nonlocal attempts_for_chapter_1
        if number == "1":
            attempts_for_chapter_1 += 1
            if attempts_for_chapter_1 == 1:
                raise RateLimitError(retry_after=45.0)
        return _fake_content_chapter(volume_str, number, branch_id)

    monkeypatch.setattr("ranobelib.sdk.asyncio.sleep", fake_sleep)

    async with RanobeLib("1--slug") as lib:
        monkeypatch.setattr(lib, "_get_chapters", fake_get_chapters)
        monkeypatch.setattr(lib, "_fetch_chapter", fake_fetch_chapter)

        volumes = await lib.download_title()

    # Retried once, honoring Retry-After, then kept going without losing later chapters.
    assert sleeps == [45.0]
    assert [chapter.number for chapter in volumes[0].chapters] == ["0", "1", "2"]


async def test_download_title_backs_off_without_retry_after(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_chapters = [_raw_toc_chapter("1", "0")]
    sleeps: list[float] = []
    attempts = 0

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    async def fake_get_chapters(*, refresh: bool = False) -> list[dict[str, Any]]:
        return raw_chapters

    async def fake_fetch_chapter(
        volume_str: str, number: str, branch_id: int | None, *, refresh: bool = False
    ) -> Chapter:
        nonlocal attempts
        attempts += 1
        if attempts <= 2:
            raise RateLimitError()
        return _fake_content_chapter(volume_str, number, branch_id)

    monkeypatch.setattr("ranobelib.sdk.asyncio.sleep", fake_sleep)

    async with RanobeLib("1--slug") as lib:
        monkeypatch.setattr(lib, "_get_chapters", fake_get_chapters)
        monkeypatch.setattr(lib, "_fetch_chapter", fake_fetch_chapter)

        await lib.download_title()

    # No Retry-After header on either 429 -> capped exponential backoff, doubling per attempt.
    assert sleeps == [5.0, 10.0]


async def test_download_title_raises_interrupted_error_with_partial_progress(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_chapters = [_raw_toc_chapter("1", str(index)) for index in range(3)]

    async def fake_sleep(delay: float) -> None:
        return None

    async def fake_get_chapters(*, refresh: bool = False) -> list[dict[str, Any]]:
        return raw_chapters

    async def fake_fetch_chapter(
        volume_str: str, number: str, branch_id: int | None, *, refresh: bool = False
    ) -> Chapter:
        if number == "1":
            raise RateLimitError()
        return _fake_content_chapter(volume_str, number, branch_id)

    monkeypatch.setattr("ranobelib.sdk.asyncio.sleep", fake_sleep)

    async with RanobeLib("1--slug") as lib:
        monkeypatch.setattr(lib, "_get_chapters", fake_get_chapters)
        monkeypatch.setattr(lib, "_fetch_chapter", fake_fetch_chapter)

        with pytest.raises(DownloadTitleInterruptedError) as exc_info:
            await lib.download_title(max_rate_limit_retries=2)

    error = exc_info.value
    # Chapter "0" was already fetched before chapter "1" started failing for good.
    assert error.slug_url == "1--slug"
    assert error.completed == 1
    assert error.total == 3
    assert [chapter.number for chapter in error.volumes[0].chapters] == ["0"]
    assert isinstance(error.__cause__, RateLimitError)


async def test_download_title_wraps_access_blocked_without_retrying(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_chapters = [_raw_toc_chapter("1", str(index)) for index in range(3)]
    fetched: list[str] = []
    sleeps: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    async def fake_get_chapters(*, refresh: bool = False) -> list[dict[str, Any]]:
        return raw_chapters

    async def fake_fetch_chapter(
        volume_str: str, number: str, branch_id: int | None, *, refresh: bool = False
    ) -> Chapter:
        fetched.append(number)
        if number == "1":
            raise AccessBlockedError("https://api.cdnlibs.org/api/manga/1--slug/chapter")
        return _fake_content_chapter(volume_str, number, branch_id)

    monkeypatch.setattr("ranobelib.sdk.asyncio.sleep", fake_sleep)

    async with RanobeLib("1--slug") as lib:
        monkeypatch.setattr(lib, "_get_chapters", fake_get_chapters)
        monkeypatch.setattr(lib, "_fetch_chapter", fake_fetch_chapter)

        with pytest.raises(DownloadTitleInterruptedError) as exc_info:
            await lib.download_title()

    error = exc_info.value
    assert error.completed == 1
    assert error.total == 3
    assert [chapter.number for chapter in error.volumes[0].chapters] == ["0"]
    assert isinstance(error.__cause__, AccessBlockedError)
    # The bulk rate-limit retry layer only rides out RateLimitError: a blocked request is
    # given up on immediately, not waited on and resent.
    assert fetched == ["0", "1"]
    assert sleeps == []


async def test_download_title_max_rate_limit_retries_zero_disables_extra_retrying(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_chapters = [_raw_toc_chapter("1", "0")]
    sleeps: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    async def fake_get_chapters(*, refresh: bool = False) -> list[dict[str, Any]]:
        return raw_chapters

    async def fake_fetch_chapter(
        volume_str: str, number: str, branch_id: int | None, *, refresh: bool = False
    ) -> Chapter:
        raise RateLimitError()

    monkeypatch.setattr("ranobelib.sdk.asyncio.sleep", fake_sleep)

    async with RanobeLib("1--slug") as lib:
        monkeypatch.setattr(lib, "_get_chapters", fake_get_chapters)
        monkeypatch.setattr(lib, "_fetch_chapter", fake_fetch_chapter)

        with pytest.raises(DownloadTitleInterruptedError) as exc_info:
            await lib.download_title(max_rate_limit_retries=0)

    assert sleeps == []
    assert exc_info.value.completed == 0


async def test_export_wires_on_chapter_to_progress_bar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _RecordingExporter:
        format = "recording-test-format"

        async def export(
            self,
            title: Title,
            chapters: list[Chapter],
            output_path: Path,
            *,
            on_chapter: Any = None,
            headers: Any = None,
        ) -> Path:
            for _ in chapters:
                if on_chapter is not None:
                    on_chapter()
            output_path.write_text("ok")
            return output_path

    EXPORTERS["recording-test-format"] = _RecordingExporter
    try:
        reporter, buffer = _reporter_with_buffer("progress_only")
        chapters = [
            _fake_content_chapter("1", "0", None),
            _fake_content_chapter("1", "1", None),
        ]

        async def fake_get_title(*, refresh: bool = False) -> dict[str, Any]:
            return {
                "id": 1,
                "name": "Title",
                "slug": "1--slug",
                "slug_url": "1--slug",
                "cover": {},
                "age_restriction": {"id": 0, "label": "16+"},
                "status": {"id": 1, "label": "Ongoing"},
            }

        async with RanobeLib("1--slug") as lib:
            monkeypatch.setattr(lib, "_get_title", fake_get_title)
            lib._reporter = reporter

            await lib.export(chapters, fmt="recording-test-format", path=tmp_path / "out")
    finally:
        del EXPORTERS["recording-test-format"]

    assert "Exporting to recording-test-format" in buffer.getvalue()


@pytest.mark.parametrize("headers", [None, {"User-Agent": "CustomAgent/1.0"}])
async def test_export_forwards_headers_to_exporter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, headers: dict[str, str] | None
) -> None:
    received: list[Any] = []

    class _HeadersExporter:
        format = "headers-test-format"

        async def export(
            self,
            title: Title,
            chapters: list[Chapter],
            output_path: Path,
            *,
            on_chapter: Any = None,
            headers: Any = None,
        ) -> Path:
            received.append(headers)
            return output_path

    async def fake_get_title(*, refresh: bool = False) -> dict[str, Any]:
        return {
            "id": 1,
            "name": "Title",
            "slug": "1--slug",
            "slug_url": "1--slug",
            "cover": {},
            "age_restriction": {"id": 0, "label": "16+"},
            "status": {"id": 1, "label": "Ongoing"},
        }

    EXPORTERS["headers-test-format"] = _HeadersExporter
    try:
        async with RanobeLib("1--slug", headers=headers) as lib:
            monkeypatch.setattr(lib, "_get_title", fake_get_title)
            await lib.export([], fmt="headers-test-format", path=tmp_path / "out")
    finally:
        del EXPORTERS["headers-test-format"]

    assert received == [headers]


async def test_headers_are_merged_into_the_api_client() -> None:
    async with RanobeLib("1--slug", headers={"user-agent": "CustomAgent/1.0"}) as lib:
        sent = lib._client._http.headers

    assert sent.get_list("User-Agent") == ["CustomAgent/1.0"]
    assert sent["Referer"] == "https://ranobelib.me/"
    assert sent["Site-Id"] == "3"


async def test_headers_default_to_browser_like_ones() -> None:
    async with RanobeLib("1--slug") as lib:
        sent = lib._client._http.headers

    assert sent["User-Agent"].startswith("Mozilla/5.0 (iPhone;")
    assert sent["Referer"] == "https://ranobelib.me/"

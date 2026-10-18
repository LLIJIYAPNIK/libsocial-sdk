"""Unit tests for MangaLib's sizes, estimate, whole-title plan and export, on a fake API."""

import io
import zipfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import httpx
import pytest
from PIL import Image

from mangalib import MangaLib, MultipleTitleTranslationsError, PageDownloadError
from mangalib.client import ApiClient
from mangalib.images import ImageFetcher
from mangalib.models import Chapter, Page, Volume

SERVERS = [{"id": "compress", "label": "Сжатия", "url": "https://img.test", "site_ids": [1]}]
TITLE = {
    "id": 1,
    "name": "Example",
    "slug": "example",
    "slug_url": "1--example",
    "cover": {},
    "ageRestriction": {"id": 0, "label": "Нет"},
    "status": {"id": 1, "label": "Онгоинг"},
}


def _jpeg() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (4, 6), "white").save(buffer, "JPEG")
    return buffer.getvalue()


JPEG = _jpeg()


def _branch(branch_id: int | None, *, closed: bool = False) -> dict[str, Any]:
    branch: dict[str, Any] = {
        "id": 1,
        "branch_id": branch_id,
        "created_at": "2026-10-01T00:00:00Z",
        "teams": [],
        "user": {"id": 1, "username": "u"},
    }
    if closed:
        branch["restricted_view"] = {"is_open": False, "expired_at": None, "price": None}
    return branch


def _entry(number: str, *branches: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(number),
        "volume": "1",
        "number": number,
        "branches_count": len(branches),
        "branches": list(branches),
    }


class FakeApi:
    """The parts of api.cdnlibs.org MangaLib touches, plus an image host."""

    def __init__(self, chapters: list[dict[str, Any]], pages: int = 2) -> None:
        self.chapters = chapters
        self.pages = pages
        self.chapter_requests: list[tuple[str, str | None]] = []
        self.image_requests: list[str] = []
        self.missing: set[str] = set()

    def api(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/constants":
            return httpx.Response(200, json={"data": {"imageServers": SERVERS}})
        if path.endswith("/chapters"):
            return httpx.Response(200, json={"data": self.chapters})
        if path.endswith("/chapter"):
            number = request.url.params["number"]
            self.chapter_requests.append((number, request.url.params.get("branch_id")))
            pages = [
                {"id": i, "slug": i, "image": f"{i}.jpg", "url": f"//c/{number}/{i}.jpg"}
                for i in range(1, self.pages + 1)
            ]
            data = {"id": int(number), "volume": "1", "number": number, "pages": pages}
            return httpx.Response(200, json={"data": data})
        return httpx.Response(200, json={"data": TITLE})

    def images(self, request: httpx.Request) -> httpx.Response:
        self.image_requests.append(f"{request.method} {request.url.path}")
        if request.url.path in self.missing:
            return httpx.Response(404)
        headers = {"Content-Type": "image/jpeg", "Content-Length": str(len(JPEG))}
        if request.method == "HEAD":
            return httpx.Response(200, headers=headers)
        return httpx.Response(200, content=JPEG, headers={"Content-Type": "image/jpeg"})


class _Lib(MangaLib):
    def __init__(self, fake: FakeApi, **kwargs: Any) -> None:
        self._fake = fake
        super().__init__("1--example", **kwargs)

    def _create_client(self, headers: Mapping[str, str] | None) -> ApiClient:
        return ApiClient(transport=httpx.MockTransport(self._fake.api), headers=headers)

    def _create_image_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(self._fake.images))

    def _create_image_fetcher(self, client: httpx.AsyncClient) -> ImageFetcher:
        async def no_sleep(delay: float) -> None:
            pass

        return ImageFetcher(client, request_delay=0.0, sleep=no_sleep)


def _outputs(directory: Path) -> list[Path]:
    """Files in ``directory`` other than the per-test disk cache (see conftest.py)."""
    return [path for path in directory.iterdir() if path.name != ".mangalib_cache"]


def _fetched(number: str, pages: int) -> Chapter:
    return Chapter(
        id=int(number),
        volume="1",
        number=number,
        pages=[
            Page(id=i, number=i, image="p.jpg", url=f"//c/{number}/{i}.jpg")
            for i in range(1, pages + 1)
        ],
    )


async def test_download_title_skips_closed_chapters_and_closed_translations() -> None:
    fake = FakeApi(
        [
            _entry("1", _branch(None)),
            _entry("2", _branch(10, closed=True), _branch(11)),
            _entry("3", _branch(10, closed=True)),
            _entry("4", _branch(10), _branch(11, closed=True), _branch(12)),
        ]
    )
    async with _Lib(fake) as lib:
        volumes = await lib.download_title(branch_id=12)

    assert [chapter.number for chapter in volumes[0].chapters] == ["1", "2", "4"]
    # Chapter 2's only open translation is requested by id, not left to the API's default.
    assert fake.chapter_requests == [("1", None), ("2", "11"), ("4", "12")]


async def test_download_title_lists_only_open_translations_when_ambiguous() -> None:
    fake = FakeApi([_entry("1", _branch(10), _branch(11), _branch(12, closed=True))])
    async with _Lib(fake) as lib:
        with pytest.raises(MultipleTitleTranslationsError) as exc_info:
            await lib.download_title()

    branches = exc_info.value.chapters[0].branches
    assert [branch.branch_id for branch in branches] == [10, 11]
    assert fake.chapter_requests == []


async def test_translation_index_counts_open_translations_only() -> None:
    fake = FakeApi([_entry("1", _branch(10, closed=True), _branch(11), _branch(12))])
    async with _Lib(fake) as lib:
        await lib.download_title(translation_index=1)

    assert fake.chapter_requests == [("1", "12")]


async def test_download_pages_respects_concurrency() -> None:
    fake = FakeApi([])
    in_flight = peak = 0

    class _Counting(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            nonlocal in_flight, peak
            in_flight += 1
            peak = max(peak, in_flight)
            await __import__("asyncio").sleep(0.001)
            in_flight -= 1
            return fake.images(request)

    class _CountingLib(_Lib):
        def _create_image_client(self) -> httpx.AsyncClient:
            return httpx.AsyncClient(transport=_Counting())

    async with _CountingLib(fake) as lib:
        data = await lib.download_pages(_fetched("1", 8), concurrency=2)

    assert data == [JPEG] * 8
    assert peak == 2


@pytest.mark.parametrize("method", ["download_pages", "chapter_size"])
async def test_concurrency_below_one_is_rejected_before_any_request(method: str) -> None:
    fake = FakeApi([])
    async with _Lib(fake) as lib:
        with pytest.raises(ValueError, match="concurrency must be at least 1"):
            await getattr(lib, method)(_fetched("1", 1), concurrency=0)

    assert fake.image_requests == []


async def test_chapter_and_volume_size_sum_content_lengths_from_head_requests() -> None:
    fake = FakeApi([])
    volume = Volume(number="1", chapters=[_fetched("1", 2), _fetched("2", 3)])
    async with _Lib(fake) as lib:
        assert await lib.chapter_size(volume.chapters[0]) == 2 * len(JPEG)
        assert await lib.volume_size(volume) == 5 * len(JPEG)

    assert all(request.startswith("HEAD ") for request in fake.image_requests)


async def test_chapter_size_needs_a_fetched_chapter() -> None:
    async with _Lib(FakeApi([])) as lib:
        with pytest.raises(ValueError, match="no pages to size"):
            await lib.chapter_size(Chapter(id=1, volume="1", number="1"))


async def test_estimate_title_size_samples_evenly_and_extrapolates() -> None:
    entries = [_entry(str(number), _branch(None)) for number in range(1, 11)]
    entries.append(_entry("11", _branch(None, closed=True)))
    fake = FakeApi(entries, pages=3)
    async with _Lib(fake) as lib:
        estimate = await lib.estimate_title_size(sample_size=4)

    # 4 sampled chapters of 3 pages each, extrapolated over the 10 open chapters.
    assert estimate == 30 * len(JPEG)
    assert [number for number, _ in fake.chapter_requests] == ["1", "3", "6", "8"]


async def test_estimate_title_size_clamps_the_sample_and_handles_no_open_chapter(
    tmp_path: Path,
) -> None:
    fake = FakeApi([_entry("1", _branch(None))], pages=1)
    async with _Lib(fake) as lib:
        assert await lib.estimate_title_size(sample_size=50) == len(JPEG)
    closed = FakeApi([_entry("1", _branch(None, closed=True))])
    async with _Lib(closed, cache_dir=tmp_path / "other-cache") as lib:
        assert await lib.estimate_title_size() == 0
    assert closed.chapter_requests == []


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"sample_size": 0}, "sample_size"),
        ({"concurrency": 0}, "concurrency"),
        ({"branch_id": 1, "translation_index": 0}, "at most one"),
    ],
)
async def test_estimate_title_size_rejects_bad_arguments(
    kwargs: dict[str, Any], message: str
) -> None:
    async with _Lib(FakeApi([])) as lib:
        with pytest.raises(ValueError, match=message):
            await lib.estimate_title_size(**kwargs)


async def test_export_accepts_chapters_and_volumes_and_reports_progress(tmp_path: Path) -> None:
    fake = FakeApi([])
    progress: list[tuple[int, int]] = []
    volume = Volume(number="1", chapters=[_fetched("1", 2), _fetched("2", 1)])
    async with _Lib(fake) as lib:
        path = await lib.export(
            [volume, _fetched("3", 1)],
            fmt="cbz",
            path=tmp_path / "book.cbz",
            on_chapter=lambda completed, total: progress.append((completed, total)),
        )

    with zipfile.ZipFile(path) as archive:
        assert [name for name in archive.namelist() if name.endswith(".jpg")] == [
            "0001.jpg",
            "0002.jpg",
            "0003.jpg",
            "0004.jpg",
        ]
    assert progress == [(1, 3), (2, 3), (3, 3)]


async def test_export_of_a_single_chapter_or_volume(tmp_path: Path) -> None:
    async with _Lib(FakeApi([])) as lib:
        one = await lib.export(_fetched("1", 1), fmt="pdf", path=tmp_path / "one.pdf")
        volume = Volume(number="1", chapters=[_fetched("1", 1)])
        whole = await lib.export(volume, fmt="cbz", path=str(tmp_path / "vol.cbz"))

    assert one.exists() and whole == tmp_path / "vol.cbz"


@pytest.mark.parametrize(
    ("chapters", "kwargs", "message"),
    [
        ([_fetched("1", 1)], {"fmt": "epub"}, "Unknown export format 'epub'. Available: cbz, pdf"),
        ([], {"fmt": "cbz"}, "no chapters given"),
        ([Chapter(id=1, volume="1", number="1")], {"fmt": "cbz"}, "has no pages"),
        ([_fetched("1", 1)], {"fmt": "cbz", "server": "main"}, "Unknown image server"),
        ([_fetched("1", 1)], {"fmt": "cbz", "concurrency": 0}, "concurrency"),
    ],
)
async def test_export_rejects_bad_input_before_downloading(
    tmp_path: Path, chapters: list[Chapter], kwargs: dict[str, Any], message: str
) -> None:
    fake = FakeApi([])
    async with _Lib(fake) as lib:
        with pytest.raises(ValueError, match=message):
            await lib.export(chapters, path=tmp_path / "x", **kwargs)

    assert fake.image_requests == []
    assert _outputs(tmp_path) == []


async def test_export_writes_nothing_when_a_page_fails(tmp_path: Path) -> None:
    fake = FakeApi([])
    fake.missing = {"/c/2/1.jpg"}
    async with _Lib(fake) as lib:
        with pytest.raises(PageDownloadError):
            await lib.export(
                [_fetched("1", 1), _fetched("2", 1)], fmt="cbz", path=tmp_path / "b.cbz"
            )

    assert _outputs(tmp_path) == []

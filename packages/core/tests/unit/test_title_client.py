"""Unit tests for libsocial.title.TitleClient, against a fake API (mock transport, no network).

``_Client`` is what a site package does: a ``TitleClient`` subclass naming its site and a
chapter model with its own content field. Tests taking the ``site`` fixture run once per
site.
"""

import io
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
from rich.console import Console

from libsocial.client import ApiClient
from libsocial.console import Reporter
from libsocial.exceptions import (
    AccessBlockedError,
    ChapterNotFoundError,
    DownloadTitleInterruptedError,
    MultipleTitleTranslationsError,
    MultipleTranslationsError,
    RateLimitError,
    TitleNotFoundError,
    VolumeNotFoundError,
)
from libsocial.models import Chapter, Title, Volume
from libsocial.pacing import Pacer
from libsocial.site import Site
from libsocial.title import PlannedChapter, TitleClient, _resolve_bulk_branch_id

SLUG = "7--example"


class _TextChapter(Chapter):
    content: str | None = None


class _TextVolume(Volume[_TextChapter]):
    pass


class _SiteTitle(Title):
    pass


def _branch(branch_id: int | None, *, username: str = "uploader") -> dict[str, Any]:
    return {
        "id": (branch_id or 0) * 10 + 1,
        "branch_id": branch_id,
        "created_at": "2020-01-01T00:00:00.000000Z",
        "teams": [],
        "user": {"id": 1, "username": username},
    }


def _toc_entry(volume: str, number: str, *branch_ids: int | None) -> dict[str, Any]:
    branches = [_branch(branch_id) for branch_id in branch_ids] or [_branch(None)]
    return {
        "id": int(float(number) * 10) + 1000 * int(volume),
        "volume": volume,
        "number": number,
        "name": f"Chapter {number}",
        "branches_count": len(branches),
        "branches": branches,
    }


_TITLE = {
    "id": 7,
    "name": "Example",
    "slug": "example",
    "slug_url": SLUG,
    "cover": {},
    "ageRestriction": {"id": 1, "label": "6+"},
    "status": {"id": 1, "label": "Онгоинг"},
    "items_count": {"uploaded": 4},
}

# Volume "0" interleaved with "1" on purpose: grouping keeps first-seen volume order.
_TOC = [
    _toc_entry("0", "0.1"),
    _toc_entry("1", "1"),
    _toc_entry("0", "0.2"),
    _toc_entry("1", "2"),
]


class _FakeApi:
    """Answers the three title endpoints; records every request it sees."""

    def __init__(self, site: Site, toc: list[dict[str, Any]] | None = None) -> None:
        self.site = site
        self.toc = _TOC if toc is None else toc
        self.requests: list[httpx.Request] = []
        self.chapter_status: dict[str, int] = {}  # number -> forced error status

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        assert request.headers["Site-Id"] == str(self.site.id)
        path = request.url.path
        if path == f"/api/manga/{SLUG}":
            return httpx.Response(200, json={"data": _TITLE})
        if path == f"/api/manga/{SLUG}/chapters":
            return httpx.Response(200, json={"data": self.toc})
        if path == f"/api/manga/{SLUG}/chapter":
            params = request.url.params
            number = params["number"]
            if number in self.chapter_status:
                return httpx.Response(self.chapter_status[number], json={"data": {}})
            entry = next(
                (e for e in self.toc if e["volume"] == params["volume"] and e["number"] == number),
                None,
            )
            if entry is None:
                return httpx.Response(404, json={"data": {}})
            content = f"{params['volume']}/{number}/{params.get('branch_id')}"
            data = {**entry, "content": content}
            return httpx.Response(200, json={"data": data})
        return httpx.Response(404, json={"data": {}})  # pragma: no cover

    def paths(self) -> list[str]:
        return [request.url.path.removeprefix(f"/api/manga/{SLUG}") for request in self.requests]


def _client_class(site: Site) -> type[TitleClient[_SiteTitle, _TextChapter, _TextVolume]]:
    class Client(TitleClient[_SiteTitle, _TextChapter, _TextVolume]):
        title_model = _SiteTitle
        chapter_model = _TextChapter
        volume_model = _TextVolume

    Client.site = site
    return Client


def _client(
    site: Site, tmp_path: Path, api: Callable[[httpx.Request], httpx.Response], **kwargs: Any
) -> TitleClient[_SiteTitle, _TextChapter, _TextVolume]:
    client = _client_class(site)(SLUG, cache_dir=tmp_path, **kwargs)
    client._client = ApiClient(site, transport=httpx.MockTransport(api), pacer=Pacer())
    return client


async def test_get_info_returns_the_title_model_with_the_requested_fields(
    site: Site, tmp_path: Path
) -> None:
    api = _FakeApi(site)
    async with _client(site, tmp_path, api) as client:
        info = await client.get_info()

    assert isinstance(info, _SiteTitle)
    assert info.chapter_count == 4
    fields = api.requests[0].url.params.get_list("fields[]")
    assert "last_item_at" in fields
    assert "summary" in fields


async def test_get_info_is_cached_until_refresh(site: Site, tmp_path: Path) -> None:
    api = _FakeApi(site)
    async with _client(site, tmp_path, api) as client:
        first = await client.get_info()
        assert await client.get_info() == first
        await client.get_info(refresh=True)

    assert api.paths() == ["", ""]


async def test_get_info_raises_title_not_found(site: Site, tmp_path: Path) -> None:
    def api(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"data": {}})

    async with _client(site, tmp_path, api) as client:
        with pytest.raises(TitleNotFoundError):
            await client.get_info()


async def test_get_table_of_contents_groups_chapters_into_volumes(
    site: Site, tmp_path: Path
) -> None:
    api = _FakeApi(site)
    async with _client(site, tmp_path, api) as client:
        volumes = await client.get_table_of_contents()
        await client.get_table_of_contents()  # From the cache.
        await client.get_table_of_contents(refresh=True)

    assert all(isinstance(volume, _TextVolume) for volume in volumes)
    assert [volume.number for volume in volumes] == ["0", "1"]
    assert [chapter.number for chapter in volumes[0].chapters] == ["0.1", "0.2"]
    assert [chapter.number for chapter in volumes[1].chapters] == ["1", "2"]
    assert all(isinstance(c, _TextChapter) and c.content is None for c in volumes[0].chapters)
    assert api.paths() == ["/chapters", "/chapters"]


async def test_get_table_of_contents_of_a_title_without_chapters(
    site: Site, tmp_path: Path
) -> None:
    async with _client(site, tmp_path, _FakeApi(site, toc=[])) as client:
        assert await client.get_table_of_contents() == []


async def test_get_chapter_returns_the_site_chapter_model_with_content(
    site: Site, tmp_path: Path
) -> None:
    api = _FakeApi(site)
    async with _client(site, tmp_path, api) as client:
        chapter = await client.get_chapter(volume=1, number="2")
        cached = await client.get_chapter(volume=1, number="2")
        await client.get_chapter(volume=1, number="2", refresh=True)

    assert isinstance(chapter, _TextChapter)
    assert chapter.content == "1/2/None"
    assert cached == chapter
    # The chapter list is checked for ambiguity; refresh=True re-fetches both.
    assert api.paths() == ["/chapters", "/chapter", "/chapters", "/chapter"]


async def test_get_chapter_refuses_to_guess_between_translations(
    site: Site, tmp_path: Path
) -> None:
    api = _FakeApi(site, toc=[_toc_entry("1", "1", 635, 2251)])
    async with _client(site, tmp_path, api) as client:
        with pytest.raises(MultipleTranslationsError) as exc_info:
            await client.get_chapter(volume=1, number="1")
        chapter = await client.get_chapter(volume=1, number="1", branch_id=2251)

    assert [branch.branch_id for branch in exc_info.value.branches] == [635, 2251]
    assert chapter.content == "1/1/2251"
    assert api.requests[-1].url.params["branch_id"] == "2251"


async def test_get_chapter_raises_chapter_not_found(site: Site, tmp_path: Path) -> None:
    async with _client(site, tmp_path, _FakeApi(site)) as client:
        with pytest.raises(ChapterNotFoundError):
            await client.get_chapter(volume=9, number="99")


async def test_get_chapters_fetches_the_list_once_and_keeps_the_given_order(
    site: Site, tmp_path: Path
) -> None:
    api = _FakeApi(site)
    async with _client(site, tmp_path, api) as client:
        chapters = await client.get_chapters([(1, "2"), (0, "0.1")])

    assert [chapter.content for chapter in chapters] == ["1/2/None", "0/0.1/None"]
    assert api.paths() == ["/chapters", "/chapter", "/chapter"]


async def test_get_chapters_raises_for_an_ambiguous_chapter(site: Site, tmp_path: Path) -> None:
    api = _FakeApi(site, toc=[_toc_entry("1", "1"), _toc_entry("1", "2", 1, 2)])
    async with _client(site, tmp_path, api) as client:
        with pytest.raises(MultipleTranslationsError):
            await client.get_chapters([(1, "1"), (1, "2")])


async def test_get_translations_lists_a_chapters_branches(site: Site, tmp_path: Path) -> None:
    api = _FakeApi(site, toc=[_toc_entry("1", "1", 635, 2251)])
    async with _client(site, tmp_path, api) as client:
        branches = await client.get_translations(volume=1, number="1")
        with pytest.raises(ChapterNotFoundError):
            await client.get_translations(volume=1, number="404")

    assert [branch.branch_id for branch in branches] == [635, 2251]


async def test_get_volume_and_get_volumes(site: Site, tmp_path: Path) -> None:
    api = _FakeApi(site)
    async with _client(site, tmp_path, api) as client:
        volume = await client.get_volume(0)
        volumes = await client.get_volumes([1, 0])
        with pytest.raises(VolumeNotFoundError):
            await client.get_volume(5)

    assert isinstance(volume, _TextVolume)
    assert [chapter.content for chapter in volume.chapters] == ["0/0.1/None", "0/0.2/None"]
    assert [v.number for v in volumes] == ["1", "0"]
    assert volumes[1] == volume  # Served from the chapter cache the second time.


async def test_download_title_fetches_every_chapter_grouped_into_volumes(
    site: Site, tmp_path: Path
) -> None:
    progress: list[tuple[int, int]] = []
    api = _FakeApi(site)
    async with _client(site, tmp_path, api) as client:
        volumes = await client.download_title(
            on_chapter=lambda done, total: progress.append((done, total))
        )

    assert [v.number for v in volumes] == ["0", "1"]
    assert [c.content for c in volumes[0].chapters] == ["0/0.1/None", "0/0.2/None"]
    assert progress == [(1, 4), (2, 4), (3, 4), (4, 4)]
    assert volumes[0].model_dump()["chapters"][0]["content"] == "0/0.1/None"


async def test_download_title_lists_every_unresolved_chapter_up_front(
    site: Site, tmp_path: Path
) -> None:
    toc = [_toc_entry("1", "1", 1, 2), _toc_entry("1", "2"), _toc_entry("1", "3", 3, 4)]
    api = _FakeApi(site, toc=toc)
    async with _client(site, tmp_path, api) as client:
        with pytest.raises(MultipleTitleTranslationsError) as exc_info:
            await client.download_title()
        with pytest.raises(MultipleTitleTranslationsError) as only_some:
            await client.download_title(branch_id=1)

    assert [(c.volume, c.number) for c in exc_info.value.chapters] == [("1", "1"), ("1", "3")]
    assert [c.number for c in only_some.value.chapters] == ["3"]
    assert api.paths() == ["/chapters"]  # Nothing fetched before the error.


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"branch_id": 2}, ["1/1/2", "1/2/None", "1/3/2"]),
        ({"translation_index": 0}, ["1/1/1", "1/2/None", "1/3/2"]),
    ],
)
async def test_download_title_resolves_translations_title_wide(
    site: Site, tmp_path: Path, kwargs: dict[str, int], expected: list[str]
) -> None:
    toc = [_toc_entry("1", "1", 1, 2), _toc_entry("1", "2"), _toc_entry("1", "3", 2, 3)]
    async with _client(site, tmp_path, _FakeApi(site, toc=toc)) as client:
        volumes = await client.download_title(**kwargs)

    assert [chapter.content for chapter in volumes[0].chapters] == expected


async def test_download_title_rejects_both_selectors_before_any_request(
    site: Site, tmp_path: Path
) -> None:
    api = _FakeApi(site)
    async with _client(site, tmp_path, api) as client:
        with pytest.raises(ValueError):
            await client.download_title(branch_id=1, translation_index=0)

    assert api.requests == []


async def test_download_title_sleeps_chapter_delay_between_chapters_only(
    site: Site, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sleeps: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr("libsocial.title.asyncio.sleep", fake_sleep)
    async with _client(site, tmp_path, _FakeApi(site)) as client:
        await client.download_title(chapter_delay=0.5)

    assert sleeps == [0.5, 0.5, 0.5]


async def test_download_title_retries_past_a_rate_limit_then_succeeds(
    site: Site, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sleeps: list[float] = []
    responses = {"1": [httpx.Response(429, headers={"Retry-After": "45"}, json={"data": {}})]}
    api = _FakeApi(site)

    def flaky(request: httpx.Request) -> httpx.Response:
        queued = responses.get(request.url.params.get("number", ""))
        if request.url.path.endswith("/chapter") and queued:
            api.requests.append(request)
            return queued.pop()
        return api(request)

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr("libsocial.title.asyncio.sleep", fake_sleep)
    async with _client(site, tmp_path, flaky) as client:
        client._client._max_retries = 0  # Let the 429 reach the bulk retry layer at once.
        volumes = await client.download_title()

    assert sleeps == [45.0]
    assert [c.number for v in volumes for c in v.chapters] == ["0.1", "0.2", "1", "2"]


async def test_download_title_backs_off_without_retry_after(
    site: Site, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sleeps: list[float] = []
    attempts = 0

    async def fake_fetch_chapter(
        volume_str: str, number: str, branch_id: int | None, *, refresh: bool = False
    ) -> _TextChapter:
        nonlocal attempts
        attempts += 1
        if attempts <= 2:
            raise RateLimitError()
        return _TextChapter(id=1, volume=volume_str, number=number, content="x")

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr("libsocial.title.asyncio.sleep", fake_sleep)
    async with _client(site, tmp_path, _FakeApi(site, toc=[_toc_entry("1", "0")])) as client:
        monkeypatch.setattr(client, "_fetch_chapter", fake_fetch_chapter)
        await client.download_title()

    # No Retry-After -> capped exponential backoff, doubling per attempt.
    assert sleeps == [5.0, 10.0]


async def test_download_title_keeps_partial_progress_when_interrupted(
    site: Site, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_sleep(delay: float) -> None:
        return None

    monkeypatch.setattr("libsocial.title.asyncio.sleep", fake_sleep)
    api = _FakeApi(site)
    api.chapter_status["1"] = 429
    async with _client(site, tmp_path, api) as client:
        client._client._max_retries = 0
        with pytest.raises(DownloadTitleInterruptedError) as exc_info:
            await client.download_title(max_rate_limit_retries=2)

    error = exc_info.value
    assert error.slug_url == SLUG
    assert (error.completed, error.total) == (1, 4)
    assert isinstance(error.volumes[0], _TextVolume)
    assert [c.number for c in error.volumes[0].chapters] == ["0.1"]
    assert isinstance(error.__cause__, RateLimitError)
    assert [r.url.params.get("number") for r in api.requests].count("1") == 3


async def test_download_title_gives_up_on_a_blocked_request_at_once(
    site: Site, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sleeps: list[float] = []

    async def fake_fetch_chapter(
        volume_str: str, number: str, branch_id: int | None, *, refresh: bool = False
    ) -> _TextChapter:
        if number == "1":
            raise AccessBlockedError("https://api.cdnlibs.org/api/manga/7--example/chapter")
        return _TextChapter(id=1, volume=volume_str, number=number)

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr("libsocial.title.asyncio.sleep", fake_sleep)
    async with _client(site, tmp_path, _FakeApi(site)) as client:
        monkeypatch.setattr(client, "_fetch_chapter", fake_fetch_chapter)
        with pytest.raises(DownloadTitleInterruptedError) as exc_info:
            await client.download_title()

    assert exc_info.value.completed == 1
    assert isinstance(exc_info.value.__cause__, AccessBlockedError)
    assert sleeps == []


async def test_download_title_max_rate_limit_retries_zero_disables_extra_retrying(
    site: Site, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sleeps: list[float] = []

    async def always_limited(
        volume_str: str, number: str, branch_id: int | None, *, refresh: bool = False
    ) -> _TextChapter:
        raise RateLimitError()

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr("libsocial.title.asyncio.sleep", fake_sleep)
    async with _client(site, tmp_path, _FakeApi(site)) as client:
        monkeypatch.setattr(client, "_fetch_chapter", always_limited)
        with pytest.raises(DownloadTitleInterruptedError) as exc_info:
            await client.download_title(max_rate_limit_retries=0)

    assert sleeps == []
    assert exc_info.value.completed == 0


def _reporter_with_buffer(verbosity: str) -> tuple[Reporter, io.StringIO]:
    buffer = io.StringIO()
    console = Console(file=buffer, force_terminal=False, width=80)
    return Reporter(verbosity, console=console), buffer  # type: ignore[arg-type]


async def test_progress_only_shows_a_download_progress_bar(site: Site, tmp_path: Path) -> None:
    reporter, buffer = _reporter_with_buffer("progress_only")
    async with _client(site, tmp_path, _FakeApi(site)) as client:
        client._reporter = reporter
        await client.download_title()

    output = buffer.getvalue()
    assert SLUG in output
    assert "[api]" not in output


async def test_full_verbosity_logs_cache_hits_and_api_fetches(site: Site, tmp_path: Path) -> None:
    reporter, buffer = _reporter_with_buffer("full")
    async with _client(site, tmp_path, _FakeApi(site)) as client:
        client._reporter = reporter
        await client.get_info()
        await client.get_info()
        await client.get_chapter(volume=1, number="1")
        await client.get_chapter(volume=1, number="1")

    output = buffer.getvalue()
    for line in (
        f"[api] fetching title metadata for {SLUG}",
        f"[cache] title metadata for {SLUG}",
        f"[api] fetching chapter list for {SLUG}",
        f"[cache] chapter list for {SLUG}",
        "[api] fetching chapter 1/1",
        "[cache] chapter 1/1",
    ):
        assert line in output


def test_plan_chapters_separates_resolved_and_unresolved(site: Site, tmp_path: Path) -> None:
    client = _client_class(site)(SLUG, cache_dir=tmp_path)
    toc = [_toc_entry("1", "1"), _toc_entry("1", "2", 5, 6), _toc_entry("1", "3", 7, 8)]

    planned, unresolved = client._plan_chapters(toc, branch_id=6, translation_index=None)

    assert planned == [PlannedChapter("1", "1", None), PlannedChapter("1", "2", 6)]
    assert [chapter.number for chapter in unresolved] == ["3"]
    with pytest.raises(ValueError):
        client._plan_chapters(toc, branch_id=6, translation_index=0)


def test_client_takes_a_title_url_or_bare_slug(site: Site, tmp_path: Path) -> None:
    client_class = _client_class(site)

    from_url = client_class(f"{site.origin}/ru/book/{SLUG}", cache_dir=tmp_path)
    bare = client_class(SLUG, cache_dir=tmp_path)

    assert from_url.slug_url == bare.slug_url == SLUG
    with pytest.raises(ValueError):
        client_class(f"{site.origin}/ru/catalog", cache_dir=tmp_path)


async def test_client_uses_its_site_and_merges_headers(site: Site, tmp_path: Path) -> None:
    client_class = _client_class(site)
    async with client_class(SLUG, cache_dir=tmp_path, headers={"user-agent": "Agent/1"}) as client:
        sent = client._client._http.headers

    assert sent["Site-Id"] == str(site.id)
    assert sent["Origin"] == site.origin
    assert sent.get_list("User-Agent") == ["Agent/1"]


def test_client_uses_the_subclass_default_cache_dir(site: Site, tmp_path: Path) -> None:
    client_class = _client_class(site)
    client_class.default_cache_dir = tmp_path / "site-cache"

    assert client_class(SLUG)._cache._dir == tmp_path / "site-cache"


def _raw_branch(branch_id: int) -> dict[str, int]:
    return {"id": branch_id * 1000, "branch_id": branch_id}


@pytest.mark.parametrize(
    ("branch_id", "translation_index", "expected"),
    [
        (2251, None, (True, 2251)),  # Matched regardless of position.
        (999, None, (False, None)),  # Not among the chapter's branches.
        (None, 1, (True, 2251)),  # By position.
        (None, 5, (False, None)),  # Position out of range.
        (None, None, (False, None)),  # Nothing to resolve with.
    ],
)
def test_resolve_bulk_branch_id(
    branch_id: int | None, translation_index: int | None, expected: tuple[bool, int | None]
) -> None:
    branches = [_raw_branch(635), _raw_branch(2251)]

    assert (
        _resolve_bulk_branch_id(branches, branch_id=branch_id, translation_index=translation_index)
        == expected
    )

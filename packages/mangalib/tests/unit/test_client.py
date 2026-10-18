"""Unit tests for mangalib.client.ApiClient, using a mock transport (no network)."""

from collections.abc import Callable
from typing import Any

import httpx
import pytest

from mangalib.client import ApiClient
from mangalib.exceptions import AccessBlockedError, AuthRequiredError, MangaLibError


async def _no_sleep(delay: float) -> None:
    """Stand-in for asyncio.sleep: skips real waiting for pacing/backoff delays."""


def _client(handler: Callable[[httpx.Request], httpx.Response], **kwargs: Any) -> ApiClient:
    kwargs.setdefault("sleep", _no_sleep)
    return ApiClient(transport=httpx.MockTransport(handler), **kwargs)


async def test_requests_are_scoped_to_mangalib() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Site-Id"] == "1"
        assert request.headers["Origin"] == "https://mangalib.me"
        assert request.headers["Referer"] == "https://mangalib.me/"
        return httpx.Response(200, json={"data": {"id": 1}})

    async with _client(handler) as client:
        assert await client.get_title("1--example") == {"id": 1}


async def test_get_chapter_returns_open_chapter() -> None:
    data = {"id": 1, "pages": [], "restricted_view": {"is_open": True, "price": 15}}

    async with _client(lambda request: httpx.Response(200, json={"data": data})) as client:
        assert await client.get_chapter("1--example", number="1", volume="1") == data


@pytest.mark.parametrize("branch_id", [None, 23320])
async def test_get_chapter_raises_auth_required_for_closed_chapter(branch_id: int | None) -> None:
    data = {"id": 1, "restricted_view": {"is_open": False, "price": 18}}

    async with _client(lambda request: httpx.Response(200, json={"data": data})) as client:
        with pytest.raises(AuthRequiredError) as exc_info:
            await client.get_chapter("1--example", number="133", volume="1", branch_id=branch_id)

    url = httpx.URL(exc_info.value.url)
    assert url.path == "/api/manga/1--example/chapter"
    assert url.params["number"] == "133"
    assert url.params.get("branch_id") == (None if branch_id is None else str(branch_id))


async def test_list_image_servers_returns_raw_list() -> None:
    servers = [{"id": "compress", "url": "https://img3.cdnlibs.org", "site_ids": [1, 3]}]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/constants"
        return httpx.Response(200, json={"data": {"imageServers": servers}})

    async with _client(handler) as client:
        assert await client.list_image_servers() == servers


async def test_list_image_servers_404_is_an_sdk_error() -> None:
    async with _client(lambda request: httpx.Response(404)) as client:
        with pytest.raises(MangaLibError, match="image server list"):
            await client.list_image_servers()


async def test_access_blocked_error_names_mangalib_entry_points() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text="<html/>", headers={"Content-Type": "text/html"})

    async with _client(handler) as client:
        with pytest.raises(AccessBlockedError, match=r"MangaLib\(\.\.\., headers=\.\.\.\)"):
            await client.get_title("1--example")

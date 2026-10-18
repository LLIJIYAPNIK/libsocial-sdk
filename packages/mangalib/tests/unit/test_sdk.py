"""Unit tests for MangaLib's image server list and page downloads, with mock transports."""

import asyncio
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import httpx
import pytest

from mangalib import MangaLib, PageDownloadError
from mangalib.client import ApiClient
from mangalib.models import Chapter, Page

SERVERS = [
    {"id": "main", "label": "Первый", "url": "https://img2.imglib.info", "site_ids": [1, 3]},
    {"id": "compress", "label": "Сжатия", "url": "https://img3.cdnlibs.org", "site_ids": [1, 3]},
    {"id": "crop", "label": "Crop pages", "url": "", "site_ids": [2]},
    {"id": "main", "label": "Первый", "url": "https://img2.hentaicdn.org", "site_ids": [2]},
]


class _Lib(MangaLib):
    """MangaLib with both its HTTP clients on mock transports."""

    def __init__(
        self,
        api: Callable[[httpx.Request], httpx.Response],
        images: Callable[[httpx.Request], httpx.Response],
        **kwargs: Any,
    ) -> None:
        self._api_handler = api
        self._images_handler = images
        super().__init__("7965--chainsaw-man", **kwargs)

    def _create_client(self, headers: Mapping[str, str] | None) -> ApiClient:
        return ApiClient(transport=httpx.MockTransport(self._api_handler), headers=headers)

    def _create_image_client(self) -> httpx.AsyncClient:
        client = super()._create_image_client()
        return httpx.AsyncClient(
            transport=httpx.MockTransport(self._images_handler), headers=client.headers
        )


def _api(calls: list[str]) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        assert request.url.params.get_list("fields[]") == ["imageServers"]
        return httpx.Response(200, json={"data": {"imageServers": SERVERS}})

    return handler


def _image(request: httpx.Request) -> httpx.Response:
    if request.url.host == "img2.imglib.info":
        return httpx.Response(403, text="<html>403</html>", headers={"Content-Type": "text/html"})
    return httpx.Response(
        200, content=request.url.path.encode(), headers={"Content-Type": "image/jpeg"}
    )


def _chapter(pages: int) -> Chapter:
    return Chapter(
        id=1,
        volume="1",
        number="1",
        pages=[
            Page(id=i, number=i, image=f"{i}.jpg", url=f"//manga/x/chapters/1-1/{i}.jpg")
            for i in range(1, pages + 1)
        ],
    )


async def test_list_image_servers_filters_to_mangalib_and_drops_empty_urls() -> None:
    calls: list[str] = []
    async with _Lib(_api(calls), _image) as lib:
        servers = await lib.list_image_servers()

    assert [(server.id, server.url) for server in servers] == [
        ("main", "https://img2.imglib.info"),
        ("compress", "https://img3.cdnlibs.org"),
    ]


async def test_list_image_servers_is_cached_in_memory_and_on_disk(tmp_path: Path) -> None:
    calls: list[str] = []
    async with _Lib(_api(calls), _image, cache_dir=tmp_path) as lib:
        await lib.list_image_servers()
        await lib.list_image_servers()
    async with _Lib(_api(calls), _image, cache_dir=tmp_path) as lib:
        await lib.list_image_servers()
        assert len(calls) == 1
        await lib.list_image_servers(refresh=True)

    assert len(calls) == 2


async def test_download_page_falls_back_from_a_blocked_server() -> None:
    async with _Lib(_api([]), _image) as lib:
        data = await lib.download_page(_chapter(1).pages[0], server="main")

    assert data == b"/manga/x/chapters/1-1/1.jpg"


async def test_page_downloads_send_mangalib_browser_headers_and_overrides() -> None:
    seen: list[httpx.Headers] = []

    def images(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers)
        return _image(request)

    async with _Lib(_api([]), images, headers={"User-Agent": "Custom/1.0"}) as lib:
        await lib.download_page(_chapter(1).pages[0])

    assert seen[0]["Referer"] == "https://mangalib.me/"
    assert seen[0]["Origin"] == "https://mangalib.me"
    assert seen[0]["Accept"] == "image/*"
    assert seen[0]["User-Agent"] == "Custom/1.0"
    assert "Site-Id" not in seen[0]


async def test_download_pages_keeps_reading_order_with_bounded_concurrency() -> None:
    in_flight = 0
    peak = 0

    class _Slow(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            nonlocal in_flight, peak
            in_flight += 1
            peak = max(peak, in_flight)
            # Later pages answer first, so order can't come from completion order.
            await asyncio.sleep(0.001 * (20 - int(request.url.path.rsplit("/", 1)[1][:-4])))
            in_flight -= 1
            return _image(request)

    class _SlowLib(_Lib):
        def _create_image_client(self) -> httpx.AsyncClient:
            return httpx.AsyncClient(transport=_Slow())

    async with _SlowLib(_api([]), _image) as lib:
        data = await lib.download_pages(_chapter(12))

    assert data == [f"/manga/x/chapters/1-1/{i}.jpg".encode() for i in range(1, 13)]
    assert 1 < peak <= 5


async def test_download_pages_raises_page_download_error_itself() -> None:
    def images(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/2.jpg"):
            return httpx.Response(404)
        return _image(request)

    async with _Lib(_api([]), images) as lib:
        with pytest.raises(PageDownloadError):
            await lib.download_pages(_chapter(3))


async def test_download_pages_rejects_unknown_server_before_downloading() -> None:
    def images(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no page should be requested")

    async with _Lib(_api([]), images) as lib:
        with pytest.raises(ValueError, match="Unknown image server 'nope'"):
            await lib.download_pages(_chapter(2), server="nope")


async def test_chapter_without_pages_downloads_nothing() -> None:
    async with _Lib(_api([]), _image) as lib:
        assert await lib.download_pages(_chapter(0)) == []


async def test_aclose_closes_the_image_client_once_opened() -> None:
    lib = _Lib(_api([]), _image)
    await lib.download_page(_chapter(1).pages[0])
    image_client = lib._image_client
    await lib.aclose()

    assert image_client is not None and image_client.is_closed

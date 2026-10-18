"""Unit tests for mangalib.images: page URLs, server order and fallback (no network)."""

from collections.abc import Callable

import httpx
import pytest

from mangalib import PageDownloadError, page_url
from mangalib.images import DEFAULT_SERVER_ORDER, download_page, server_order
from mangalib.models import ImageServer, Page

MAIN = ImageServer(id="main", label="Первый", url="https://img2.imglib.info")
SECONDARY = ImageServer(id="secondary", label="Второй", url="https://img2.imglib.info")
COMPRESS = ImageServer(id="compress", label="Сжатия", url="https://img3.cdnlibs.org")
DOWNLOAD = ImageServer(id="download", label="Скачивание", url="https://img3.cdnlibs.org")
CROP = ImageServer(id="crop", label="Crop pages", url="https://crops.mangalib.me")
SERVERS = [MAIN, SECONDARY, COMPRESS, DOWNLOAD, CROP]

PAGE = Page(id=1, number=1, image="00.jpg", url="//manga/example/chapters/1-1/00.jpg")
JPEG = b"\xff\xd8\xff\xe0fake-jpeg"


def test_page_url_joins_server_and_page_path_with_one_slash() -> None:
    assert page_url(PAGE, COMPRESS) == "https://img3.cdnlibs.org/manga/example/chapters/1-1/00.jpg"
    server = ImageServer(id="x", label="x", url="https://example.org/")
    page = PAGE.model_copy(update={"url": "manga/a.jpg"})
    assert page_url(page, server) == "https://example.org/manga/a.jpg"


def test_default_order_starts_from_compress_and_skips_same_host_and_crop() -> None:
    assert DEFAULT_SERVER_ORDER[0] == "compress"
    assert server_order(SERVERS, None) == [COMPRESS, MAIN]


def test_chosen_server_comes_first_then_the_default_order() -> None:
    assert server_order(SERVERS, "main") == [MAIN, COMPRESS]
    assert server_order(SERVERS, "crop") == [CROP, COMPRESS, MAIN]


def test_unknown_server_raises_value_error_listing_available_ones() -> None:
    with pytest.raises(ValueError, match="Unknown image server 'nope'.*compress"):
        server_order(SERVERS, "nope")


def test_no_known_server_raises_value_error() -> None:
    with pytest.raises(ValueError, match="pass server= explicitly"):
        server_order([CROP], None)


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_download_page_returns_first_image_served() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "img3.cdnlibs.org"
        return httpx.Response(200, content=JPEG, headers={"Content-Type": "image/jpeg"})

    async with _client(handler) as client:
        assert await download_page(client, PAGE, [COMPRESS, MAIN]) == JPEG


async def test_download_page_falls_back_past_html_403_and_network_errors() -> None:
    hosts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        hosts.append(request.url.host)
        if request.url.host == "img2.imglib.info":
            return httpx.Response(
                403, text="<html>403</html>", headers={"Content-Type": "text/html; charset=utf-8"}
            )
        if request.url.host == "crops.mangalib.me":
            raise httpx.ConnectError("unreachable", request=request)
        return httpx.Response(200, content=JPEG, headers={"Content-Type": "image/jpeg"})

    async with _client(handler) as client:
        assert await download_page(client, PAGE, [MAIN, CROP, COMPRESS]) == JPEG
    assert hosts == ["img2.imglib.info", "crops.mangalib.me", "img3.cdnlibs.org"]


async def test_download_page_raises_after_every_server_failed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "img2.imglib.info":
            return httpx.Response(200, text="<html>challenge</html>")
        return httpx.Response(404)

    async with _client(handler) as client:
        with pytest.raises(PageDownloadError) as exc_info:
            await download_page(client, PAGE, [MAIN, COMPRESS])

    failures = exc_info.value.failures
    assert [url for url, _ in failures] == [page_url(PAGE, MAIN), page_url(PAGE, COMPRESS)]
    assert "not an image" in failures[0][1]
    assert failures[1][1] == "HTTP 404 (no type)"
    assert page_url(PAGE, COMPRESS) in str(exc_info.value)

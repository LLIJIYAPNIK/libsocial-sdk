"""Unit tests for mangalib.images: page URLs, server order, pacing, retries, fallback."""

from collections.abc import Callable

import httpx
import pytest

from mangalib import PageDownloadError, page_url
from mangalib.images import DEFAULT_SERVER_ORDER, ImageFetcher, server_order
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


class _Sleeps:
    """Records sleeps instead of waiting."""

    def __init__(self) -> None:
        self.delays: list[float] = []

    async def __call__(self, delay: float) -> None:
        self.delays.append(delay)


def _fetcher(
    handler: Callable[[httpx.Request], httpx.Response], *, request_delay: float = 0.0
) -> tuple[ImageFetcher, _Sleeps]:
    sleeps = _Sleeps()
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return ImageFetcher(client, request_delay=request_delay, sleep=sleeps), sleeps


def _jpeg(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, content=JPEG, headers={"Content-Type": "image/jpeg"})


def _html_403(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        403, text="<html>403</html>", headers={"Content-Type": "text/html; charset=utf-8"}
    )


async def test_download_returns_first_image_served() -> None:
    fetcher, sleeps = _fetcher(_jpeg)

    assert await fetcher.download(PAGE, [COMPRESS, MAIN]) == JPEG
    assert sleeps.delays == []


async def test_download_falls_back_at_once_past_a_refusal() -> None:
    hosts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        hosts.append(request.url.host)
        return _html_403(request) if request.url.host == "img2.imglib.info" else _jpeg(request)

    fetcher, sleeps = _fetcher(handler)

    assert await fetcher.download(PAGE, [MAIN, COMPRESS]) == JPEG
    assert hosts == ["img2.imglib.info", "img3.cdnlibs.org"]
    assert sleeps.delays == []  # a 403 isn't retried


@pytest.mark.parametrize(
    "failure",
    [
        lambda request: httpx.Response(429, text="<html>429</html>"),
        lambda request: httpx.Response(503),
    ],
)
async def test_download_retries_429_and_5xx_with_backoff_on_the_same_server(
    failure: Callable[[httpx.Request], httpx.Response],
) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return failure(request) if calls <= 2 else _jpeg(request)

    fetcher, sleeps = _fetcher(handler)

    assert await fetcher.download(PAGE, [COMPRESS]) == JPEG
    assert sleeps.delays == [1.0, 2.0]


async def test_download_retries_a_broken_connection() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.RemoteProtocolError("illegal status line", request=request)
        return _jpeg(request)

    fetcher, _ = _fetcher(handler)

    assert await fetcher.download(PAGE, [COMPRESS]) == JPEG


async def test_download_falls_back_once_a_servers_retries_run_out() -> None:
    hosts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        hosts.append(request.url.host)
        if request.url.host == "img3.cdnlibs.org":
            raise httpx.ConnectError("unreachable", request=request)
        return _jpeg(request)

    fetcher, sleeps = _fetcher(handler)

    assert await fetcher.download(PAGE, [COMPRESS, MAIN]) == JPEG
    assert hosts == ["img3.cdnlibs.org"] * 4 + ["img2.imglib.info"]
    assert sleeps.delays == [1.0, 2.0, 4.0]


async def test_download_raises_after_every_server_failed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "img2.imglib.info":
            return httpx.Response(200, text="<html>challenge</html>")
        return httpx.Response(404)

    fetcher, _ = _fetcher(handler)
    with pytest.raises(PageDownloadError) as exc_info:
        await fetcher.download(PAGE, [MAIN, COMPRESS])

    failures = exc_info.value.failures
    assert [url for url, _ in failures] == [page_url(PAGE, MAIN), page_url(PAGE, COMPRESS)]
    assert "not an image" in failures[0][1]
    assert failures[1][1] == "HTTP 404 (no type)"
    assert page_url(PAGE, COMPRESS) in str(exc_info.value)


async def test_requests_are_paced_per_image_host() -> None:
    host = "pacing-test.example"  # no other test uses it: its pacer starts idle
    server = ImageServer(id="compress", label="x", url=f"https://{host}")
    fetcher, sleeps = _fetcher(_jpeg, request_delay=10.0)

    await fetcher.download(PAGE, [server])
    await fetcher.download(PAGE, [server])

    assert len(sleeps.delays) == 1
    assert 9.0 < sleeps.delays[0] <= 10.0


async def test_size_reads_content_length_from_a_head_request() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "HEAD"
        return httpx.Response(
            200, headers={"Content-Type": "image/jpeg", "Content-Length": "478689"}
        )

    fetcher, _ = _fetcher(handler)

    assert await fetcher.size(PAGE, [COMPRESS]) == 478689


async def test_size_falls_back_when_a_server_sends_no_content_length() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "img3.cdnlibs.org":
            return httpx.Response(200, headers={"Content-Type": "image/jpeg"})
        return httpx.Response(200, headers={"Content-Type": "image/jpeg", "Content-Length": "5"})

    fetcher, _ = _fetcher(handler)

    assert await fetcher.size(PAGE, [COMPRESS, MAIN]) == 5

    with pytest.raises(PageDownloadError, match="no Content-Length"):
        await fetcher.size(PAGE, [COMPRESS])

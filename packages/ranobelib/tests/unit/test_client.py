"""Unit tests for ranobelib.client.ApiClient, using a mock transport (no network)."""

import asyncio
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from ranobelib.client import ApiClient
from ranobelib.exceptions import (
    AccessBlockedError,
    AuthRequiredError,
    ChapterNotFoundError,
    RanobeLibError,
    RateLimitError,
    TitleNotFoundError,
)


async def _no_sleep(delay: float) -> None:
    """Stand-in for asyncio.sleep in tests: skips real waiting for pacing/backoff delays."""


def _client(handler: Callable[[httpx.Request], httpx.Response], **kwargs: Any) -> ApiClient:
    kwargs.setdefault("sleep", _no_sleep)
    return ApiClient(transport=httpx.MockTransport(handler), **kwargs)


async def test_get_title_returns_data_payload() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/manga/1--example"
        assert request.headers["Site-Id"] == "3"
        assert request.headers["Accept"] == "application/json"
        return httpx.Response(200, json={"data": {"id": 1, "name": "Example"}})

    async with _client(handler) as client:
        data = await client.get_title("1--example")

    assert data == {"id": 1, "name": "Example"}


async def test_requests_carry_browser_like_headers() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Origin"] == "https://ranobelib.me"
        assert request.headers["Referer"] == "https://ranobelib.me/"
        assert request.headers["User-Agent"].startswith("Mozilla/5.0 (iPhone;")
        assert "python-httpx" not in request.headers["User-Agent"]
        assert request.headers["Site-Id"] == "3"
        assert request.headers["Accept"] == "application/json"
        return httpx.Response(200, json={"data": {}})

    async with _client(handler) as client:
        await client.get_title("1--example")


async def test_headers_override_defaults_and_keep_the_rest() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["User-Agent"] == "CustomAgent/1.0"
        assert request.headers.get_list("User-Agent") == ["CustomAgent/1.0"]
        assert request.headers["X-Extra"] == "yes"
        assert request.headers["Referer"] == "https://ranobelib.me/"
        assert request.headers["Site-Id"] == "3"
        assert request.headers["Accept"] == "application/json"
        return httpx.Response(200, json={"data": {}})

    headers = {"user-agent": "CustomAgent/1.0", "X-Extra": "yes"}
    async with _client(handler, headers=headers) as client:
        await client.get_title("1--example")


async def test_get_title_sends_requested_fields_as_query_params() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params.get_list("fields[]") == ["summary", "genres"]
        return httpx.Response(200, json={"data": {}})

    async with _client(handler) as client:
        await client.get_title("1--example", fields=["summary", "genres"])


async def test_get_title_raises_title_not_found_on_404() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"data": {"toast": {"message": "Not Found"}}})

    async with _client(handler) as client:
        with pytest.raises(TitleNotFoundError) as exc_info:
            await client.get_title("1--missing")

    assert exc_info.value.slug_url == "1--missing"


async def test_get_title_raises_auth_required_on_403() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"data": {}})

    async with _client(handler) as client:
        with pytest.raises(AuthRequiredError):
            await client.get_title("1--paywalled")


_EDGE_403_PAGE = (
    "<!DOCTYPE html><html lang=en><title>403 - Forbidden</title>"
    "<p>403 - Forbidden . That's an error.</p></html>"
)

_CATALOG_CALL_KWARGS: dict[str, Any] = {
    "page": 1,
    "per_page": 30,
    "query": None,
    "genres": None,
    "tags": None,
    "statuses": None,
    "countries": None,
    "min_chapters": None,
    "max_chapters": None,
    "sort": "last_chapter_at",
}


def _edge_403(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        403, headers={"Content-Type": "text/html; charset=utf-8"}, text=_EDGE_403_PAGE
    )


@pytest.mark.parametrize(
    "call",
    [
        pytest.param(lambda client: client.get_title("1--example"), id="title"),
        pytest.param(lambda client: client.get_chapters("1--example"), id="chapters"),
        pytest.param(
            lambda client: client.get_chapter("1--example", volume="1", number="1"),
            id="chapter",
        ),
        pytest.param(lambda client: client.list_titles(**_CATALOG_CALL_KWARGS), id="catalog"),
        pytest.param(lambda client: client.list_genres(), id="genres"),
        pytest.param(lambda client: client.list_countries(), id="countries"),
        pytest.param(lambda client: client.list_statuses(), id="statuses"),
    ],
)
async def test_html_403_raises_access_blocked_not_auth_required(
    call: Callable[[ApiClient], Any],
) -> None:
    async with _client(_edge_403) as client:
        with pytest.raises(AccessBlockedError) as exc_info:
            await call(client)

    assert not isinstance(exc_info.value, AuthRequiredError)
    assert exc_info.value.url.startswith("https://api.cdnlibs.org/api/")


@pytest.mark.parametrize(
    ("content_type", "expected"),
    [
        ("application/json", AuthRequiredError),
        ("Application/JSON; charset=utf-8", AuthRequiredError),
        ("text/html; charset=utf-8", AccessBlockedError),
        ("text/plain", AccessBlockedError),
        (None, AccessBlockedError),
    ],
)
async def test_403_is_classified_by_content_type(
    content_type: str | None, expected: type[Exception]
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        response = httpx.Response(403, content=b'{"message": "User is not logged in."}')
        if content_type is not None:
            response.headers["Content-Type"] = content_type
        return response

    async with _client(handler) as client:
        with pytest.raises(expected):
            await client.get_title("1--example")


async def test_html_403_is_not_retried() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return _edge_403(request)

    async with _client(handler) as client:
        with pytest.raises(AccessBlockedError):
            await client.get_title("1--example")

    assert calls == 1


async def test_get_title_raises_rate_limit_error_on_429_with_retry_after() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "30"}, json={"data": {}})

    async with _client(handler) as client:
        with pytest.raises(RateLimitError) as exc_info:
            await client.get_title("1--throttled")

    assert exc_info.value.retry_after == 30.0


async def test_get_title_raises_rate_limit_error_on_429_without_retry_after() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"data": {}})

    async with _client(handler) as client:
        with pytest.raises(RateLimitError) as exc_info:
            await client.get_title("1--throttled")

    assert exc_info.value.retry_after is None


async def test_get_title_wraps_other_error_statuses_in_ranobelib_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="internal error")

    async with _client(handler) as client:
        with pytest.raises(RanobeLibError):
            await client.get_title("1--broken")


async def test_get_chapters_returns_data_array() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/manga/1--example/chapters"
        assert request.headers["Site-Id"] == "3"
        return httpx.Response(200, json={"data": [{"id": 1, "volume": "1", "number": "1"}]})

    async with _client(handler) as client:
        data = await client.get_chapters("1--example")

    assert data == [{"id": 1, "volume": "1", "number": "1"}]


async def test_get_chapters_raises_title_not_found_on_404() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"data": {"toast": {"message": "Not Found"}}})

    async with _client(handler) as client:
        with pytest.raises(TitleNotFoundError):
            await client.get_chapters("1--missing")


async def test_get_chapter_sends_number_and_volume_query_params() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/manga/1--example/chapter"
        assert request.url.params["number"] == "51.6"
        assert request.url.params["volume"] == "6"
        assert "branch_id" not in request.url.params
        return httpx.Response(200, json={"data": {"id": 1, "content": "<p>Hi.</p>"}})

    async with _client(handler) as client:
        data = await client.get_chapter("1--example", number="51.6", volume="6")

    assert data == {"id": 1, "content": "<p>Hi.</p>"}


async def test_get_chapter_sends_branch_id_when_given() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["branch_id"] == "2251"
        return httpx.Response(200, json={"data": {}})

    async with _client(handler) as client:
        await client.get_chapter("1--example", number="1", volume="1", branch_id=2251)


async def test_get_chapter_raises_chapter_not_found_on_404() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"data": {"toast": {"message": "Not Found"}}})

    async with _client(handler) as client:
        with pytest.raises(ChapterNotFoundError) as exc_info:
            await client.get_chapter("1--example", number="9999", volume="999")

    assert exc_info.value.slug_url == "1--example"
    assert exc_info.value.volume == "999"
    assert exc_info.value.number == "9999"


async def test_get_chapter_raises_auth_required_on_403() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"data": {}})

    async with _client(handler) as client:
        with pytest.raises(AuthRequiredError):
            await client.get_chapter("1--example", number="1", volume="1")


async def test_list_titles_sends_expected_query_params() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/manga"
        assert request.url.params.get_list("site_id[]") == ["3"]
        assert request.url.params["page"] == "1"
        assert request.url.params["limit"] == "30"
        assert request.url.params["sort_by"] == "last_chapter_at"
        assert request.url.params["q"] == "dxd"
        assert request.url.params.get_list("genres[]") == ["34", "35"]
        assert request.url.params.get_list("tags[]") == ["218", "232"]
        assert request.url.params.get_list("status[]") == ["1", "2"]
        assert request.url.params.get_list("types[]") == ["10", "11"]
        assert request.url.params["chap_count_min"] == "100"
        assert request.url.params["chap_count_max"] == "500"
        return httpx.Response(200, json={"data": [], "meta": {}})

    async with _client(handler) as client:
        await client.list_titles(
            page=1,
            per_page=30,
            query="dxd",
            genres=[34, 35],
            tags=[218, 232],
            statuses=[1, 2],
            countries=[10, 11],
            min_chapters=100,
            max_chapters=500,
            sort="last_chapter_at",
        )


async def test_list_titles_omits_optional_params_when_not_given() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "q" not in request.url.params
        assert "genres[]" not in request.url.params
        assert "tags[]" not in request.url.params
        assert "status[]" not in request.url.params
        assert "types[]" not in request.url.params
        assert "chap_count_min" not in request.url.params
        assert "chap_count_max" not in request.url.params
        return httpx.Response(200, json={"data": [], "meta": {}})

    async with _client(handler) as client:
        await client.list_titles(
            page=1,
            per_page=30,
            query=None,
            genres=None,
            tags=None,
            statuses=None,
            countries=None,
            min_chapters=None,
            max_chapters=None,
            sort="name",
        )


async def test_list_titles_returns_full_response_body() -> None:
    payload = {"data": [{"id": 1}], "meta": {"current_page": 1, "has_next_page": True}}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    async with _client(handler) as client:
        result = await client.list_titles(
            page=1,
            per_page=30,
            query=None,
            genres=None,
            tags=None,
            statuses=None,
            countries=None,
            min_chapters=None,
            max_chapters=None,
            sort="name",
        )

    assert result == payload


async def test_list_titles_raises_rate_limit_error_on_429() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"data": {}})

    async with _client(handler) as client:
        with pytest.raises(RateLimitError):
            await client.list_titles(
                page=1,
                per_page=30,
                query=None,
                genres=None,
                tags=None,
                statuses=None,
                countries=None,
                min_chapters=None,
                max_chapters=None,
                sort="name",
            )


async def test_list_titles_wraps_validation_error_in_ranobelib_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"data": {"sort_by": ["The selected sort_by is invalid."]}})

    async with _client(handler) as client:
        with pytest.raises(RanobeLibError):
            await client.list_titles(
                page=1,
                per_page=30,
                query=None,
                genres=None,
                tags=None,
                statuses=None,
                countries=None,
                min_chapters=None,
                max_chapters=None,
                sort="bogus",
            )


async def test_list_genres_sends_expected_query_params() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/constants"
        assert request.url.params.get_list("fields[]") == ["genres"]
        return httpx.Response(200, json={"data": {"genres": []}})

    async with _client(handler) as client:
        await client.list_genres()


async def test_list_genres_returns_raw_genres_array() -> None:
    genres = [{"id": 34, "name": "Боевик", "adult": False, "site_ids": [1, 2, 3, 4, 5]}]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {"genres": genres}})

    async with _client(handler) as client:
        result = await client.list_genres()

    assert result == genres


async def test_list_genres_raises_rate_limit_error_on_429() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"data": {}})

    async with _client(handler) as client:
        with pytest.raises(RateLimitError):
            await client.list_genres()


async def test_list_titles_sends_countries_as_repeated_types_query_param() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params.get_list("types[]") == ["10", "11"]
        return httpx.Response(200, json={"data": [], "meta": {}})

    async with _client(handler) as client:
        await client.list_titles(
            page=1,
            per_page=30,
            query=None,
            genres=None,
            tags=None,
            statuses=None,
            countries=[10, 11],
            min_chapters=None,
            max_chapters=None,
            sort="name",
        )


async def test_list_titles_sends_tags_query_param() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params.get_list("tags[]") == ["218"]
        return httpx.Response(200, json={"data": [], "meta": {}})

    async with _client(handler) as client:
        await client.list_titles(
            page=1,
            per_page=30,
            query=None,
            genres=None,
            tags=[218],
            statuses=None,
            countries=None,
            min_chapters=None,
            max_chapters=None,
            sort="name",
        )


async def test_list_countries_sends_expected_query_params() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/constants"
        assert request.url.params.get_list("fields[]") == ["types"]
        return httpx.Response(200, json={"data": {"types": []}})

    async with _client(handler) as client:
        await client.list_countries()


async def test_list_countries_returns_raw_types_array() -> None:
    types_ = [{"id": 10, "label": "Япония", "site_ids": [3]}]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {"types": types_}})

    async with _client(handler) as client:
        result = await client.list_countries()

    assert result == types_


async def test_list_countries_raises_rate_limit_error_on_429() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"data": {}})

    async with _client(handler) as client:
        with pytest.raises(RateLimitError):
            await client.list_countries()


async def test_list_statuses_sends_expected_query_params() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/constants"
        assert request.url.params.get_list("fields[]") == ["status"]
        return httpx.Response(200, json={"data": {"status": []}})

    async with _client(handler) as client:
        await client.list_statuses()


async def test_list_statuses_returns_raw_status_array() -> None:
    statuses = [{"id": 1, "label": "Онгоинг", "site_ids": [0, 1, 2, 3, 4, 5]}]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {"status": statuses}})

    async with _client(handler) as client:
        result = await client.list_statuses()

    assert result == statuses


async def test_list_statuses_raises_rate_limit_error_on_429() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"data": {}})

    async with _client(handler) as client:
        with pytest.raises(RateLimitError):
            await client.list_statuses()


async def test_aclose_without_context_manager() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {}})

    client = _client(handler)
    await client.get_title("1--example")
    await client.aclose()


async def test_get_title_retries_on_429_then_succeeds() -> None:
    responses = iter(
        [
            httpx.Response(429, headers={"Retry-After": "5"}, json={"data": {}}),
            httpx.Response(200, json={"data": {"id": 1}}),
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return next(responses)

    async with _client(handler) as client:
        data = await client.get_title("1--example")

    assert data == {"id": 1}


async def test_get_title_retries_on_5xx_then_succeeds() -> None:
    responses = iter(
        [httpx.Response(503, text="unavailable"), httpx.Response(200, json={"data": {}})]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return next(responses)

    async with _client(handler) as client:
        await client.get_title("1--example")  # Doesn't raise.


async def test_get_title_gives_up_after_max_retries() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(429, json={"data": {}})

    async with _client(handler, max_retries=2) as client:
        with pytest.raises(RateLimitError):
            await client.get_title("1--example")

    assert attempts == 3  # Initial attempt plus 2 retries.


async def test_retry_backoff_doubles_and_honors_retry_after() -> None:
    delays: list[float] = []

    async def recording_sleep(delay: float) -> None:
        delays.append(delay)

    responses = iter(
        [
            httpx.Response(500, text="a"),
            httpx.Response(500, text="b"),
            httpx.Response(429, headers={"Retry-After": "9"}, json={"data": {}}),
            httpx.Response(200, json={"data": {}}),
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return next(responses)

    async with _client(
        handler, sleep=recording_sleep, max_retries=3, retry_base_delay=1.0, request_delay=0.0
    ) as client:
        await client.get_title("1--example")

    assert delays == [1.0, 2.0, 9.0]


async def test_retry_backoff_ignores_unparseable_retry_after() -> None:
    delays: list[float] = []

    async def recording_sleep(delay: float) -> None:
        delays.append(delay)

    responses = iter(
        [
            httpx.Response(429, headers={"Retry-After": "not-a-number"}, json={"data": {}}),
            httpx.Response(200, json={"data": {}}),
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return next(responses)

    async with _client(handler, sleep=recording_sleep, retry_base_delay=1.0) as client:
        await client.get_title("1--example")

    assert delays == [1.0]


async def test_pace_waits_for_request_delay_between_calls() -> None:
    delays: list[float] = []

    async def recording_sleep(delay: float) -> None:
        delays.append(delay)

    clock_values = iter([0.0, 0.0, 0.15, 0.15])

    def fake_clock() -> float:
        return next(clock_values)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {}})

    async with _client(
        handler, sleep=recording_sleep, clock=fake_clock, request_delay=0.2
    ) as client:
        await client.get_title("1--a")
        await client.get_title("1--b")

    assert delays == [pytest.approx(0.05)]


async def test_max_concurrency_limits_in_flight_requests() -> None:
    in_flight = 0
    max_in_flight = 0
    lock = asyncio.Lock()

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal in_flight, max_in_flight
        async with lock:
            in_flight += 1
            max_in_flight = max(max_in_flight, in_flight)
        await asyncio.sleep(0.05)
        async with lock:
            in_flight -= 1
        return httpx.Response(200, json={"data": {}})

    async with _client(handler, max_concurrency=2, request_delay=0.0) as client:
        await asyncio.gather(*(client.get_title(f"{i}--x") for i in range(5)))

    assert max_in_flight == 2

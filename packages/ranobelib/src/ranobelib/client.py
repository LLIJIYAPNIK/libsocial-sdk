"""Low-level HTTP client for the api.cdnlibs.org JSON API, scoped to ranobelib.me.

The client is ``libsocial-core``'s (``libsocial.ApiClient``); this subclass only fixes its
site to ranobelib.me, so it keeps the constructor it always had, without a ``site``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping

import httpx

from libsocial import ApiClient as _CoreApiClient
from libsocial import Pacer
from libsocial.client import API_BASE_URL
from ranobelib._http import RANOBELIB

__all__ = ["API_BASE_URL", "DEFAULT_REQUEST_DELAY", "RANOBELIB_SITE_ID", "ApiClient"]

RANOBELIB_SITE_ID = str(RANOBELIB.id)
"""``Site-Id`` header value that scopes requests to ranobelib.me. See docs/api-notes.md."""

DEFAULT_REQUEST_DELAY = 0.2
"""Default minimum time, in seconds, between the start of one request and the next."""


class ApiClient(_CoreApiClient):
    """``libsocial.ApiClient`` for ranobelib.me.

    Bounds concurrency, paces request starts and retries 429/5xx with backoff — see
    ``libsocial.ApiClient``. Pacing is shared with every other client in the process talking
    to api.cdnlibs.org (a mangalib client too), unless ``clock`` or ``pacer`` is given.
    """

    headers_hint = "RanobeLib(..., headers=...) / Catalog(headers=...)"

    def __init__(
        self,
        *,
        base_url: str = API_BASE_URL,
        timeout: float = 15.0,
        transport: httpx.AsyncBaseTransport | None = None,
        headers: Mapping[str, str] | None = None,
        max_concurrency: int = 5,
        request_delay: float | None = None,
        max_retries: int = 3,
        retry_base_delay: float = 1.0,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        clock: Callable[[], float] | None = None,
        pacer: Pacer | None = None,
    ) -> None:
        """Initialize the client.

        Args:
            base_url: API base URL.
            timeout: Per-request timeout, in seconds.
            transport: Custom ``httpx`` transport, e.g. a mock transport for tests.
            headers: Extra headers merged over the defaults (browser-like ``Origin``/
                ``Referer``/``User-Agent`` plus the API's ``Site-Id``/``Accept``); a key
                given here replaces the default one, matched case-insensitively.
            max_concurrency: Maximum number of requests in flight at once.
            request_delay: Minimum time, in seconds, between the start of one request and
                the next. ``None`` (the default) uses ``DEFAULT_REQUEST_DELAY``.
            max_retries: How many times to retry a 429 or 5xx response before raising.
            retry_base_delay: Base delay, in seconds, for exponential backoff between
                retries (doubled per attempt), unless a 429's ``Retry-After`` says otherwise.
            sleep: Sleep function used for pacing and backoff. Overridable for tests.
            clock: Time source for pacing. Given, the client paces with its own ``Pacer``
                on this clock instead of the process-wide one. Overridable for tests.
            pacer: Pacer to space request starts with — see ``libsocial.ApiClient``.
                Takes precedence over ``clock``.
        """
        if pacer is None and clock is not None:
            pacer = Pacer(clock=clock)
        super().__init__(
            RANOBELIB,
            base_url=base_url,
            timeout=timeout,
            transport=transport,
            headers=headers,
            max_concurrency=max_concurrency,
            request_delay=DEFAULT_REQUEST_DELAY if request_delay is None else request_delay,
            max_retries=max_retries,
            retry_base_delay=retry_base_delay,
            sleep=sleep,
            pacer=pacer,
        )

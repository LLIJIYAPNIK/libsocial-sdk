"""Low-level HTTP client for the api.cdnlibs.org JSON API, scoped to mangalib.me.

The client is ``libsocial-core``'s (``libsocial.ApiClient``); this subclass fixes its site to
mangalib.me and adds what only a manga chapter needs: refusing closed (paid/early-access)
chapters, and the list of image servers its pages are served from.
"""

from __future__ import annotations

from typing import Any

import httpx

from libsocial import ApiClient as _CoreApiClient
from libsocial.exceptions import AuthRequiredError, LibSocialError
from mangalib._http import MANGALIB

__all__ = ["ApiClient"]


class ApiClient(_CoreApiClient):
    """``libsocial.ApiClient`` for mangalib.me.

    Bounds concurrency, paces request starts and retries 429/5xx with backoff — see
    ``libsocial.ApiClient``. Pacing is shared with every other client in the process talking
    to api.cdnlibs.org (a ranobelib client too), unless ``pacer`` is given.
    """

    headers_hint = "MangaLib(..., headers=...) / Catalog(headers=...)"

    def __init__(self, **kwargs: Any) -> None:
        """Initialize the client.

        Args:
            **kwargs: The keyword arguments of ``libsocial.ApiClient`` (``base_url``,
                ``timeout``, ``transport``, ``headers``, ``max_concurrency``,
                ``request_delay``, ``max_retries``, ``retry_base_delay``, ``sleep``,
                ``pacer``) — everything but ``site``, which is always mangalib.me.
        """
        super().__init__(MANGALIB, **kwargs)

    async def get_chapter(
        self,
        slug_url: str,
        *,
        number: str,
        volume: str,
        branch_id: int | None = None,
    ) -> dict[str, Any]:
        """Fetch a single chapter's metadata and pages.

        A closed chapter (paid, or still in early access) doesn't come back as a 403: the API
        answers 200 with ``restricted_view.is_open: false`` and no ``pages`` at all (see
        docs/api-notes.md, "MangaLib"). That's turned into ``AuthRequiredError`` here, before
        the response reaches the disk cache — a cached refusal would outlive the chapter
        opening up when its early access ends.

        Args:
            slug_url: The title's ``{id}--{slug}`` identifier.
            number: The chapter number, as returned by the API (may contain a decimal).
            volume: The volume number.
            branch_id: Which translation to fetch, for chapters with more than one.

        Returns:
            The ``data`` object from the API response.

        Raises:
            AuthRequiredError: If the chapter is closed to readers without an account.
        """
        data = await super().get_chapter(
            slug_url, number=number, volume=volume, branch_id=branch_id
        )
        restricted_view = data.get("restricted_view")
        if isinstance(restricted_view, dict) and not restricted_view.get("is_open", True):
            params = {"number": number, "volume": volume}
            if branch_id is not None:
                params["branch_id"] = str(branch_id)
            url = self._http.build_request("GET", f"/manga/{slug_url}/chapter", params=params).url
            raise AuthRequiredError(str(url))
        return data

    async def list_image_servers(self) -> list[dict[str, Any]]:
        """Fetch the raw image server list shared across the whole lib.social network.

        Same shape and caveats as ``list_genres``: not site-scoped by any request parameter,
        every server known to the network at once, each tagged with the site ids it serves
        via ``site_ids``.

        Returns:
            The raw ``data.imageServers`` array from the API response, unfiltered by site.
        """
        response = await self._get(
            "/constants", params=httpx.QueryParams([("fields[]", "imageServers")])
        )
        self._raise_for_status(
            response, not_found=LibSocialError("Unexpected 404 from image server list")
        )
        data: list[dict[str, Any]] = response.json()["data"]["imageServers"]
        return data

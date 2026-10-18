"""Shared pytest fixtures for libsocial-core."""

import pytest

from libsocial.site import Site

RANOBELIB = Site(id=3, origin="https://ranobelib.me")
MANGALIB = Site(id=1, origin="https://mangalib.me")


@pytest.fixture(params=[RANOBELIB, MANGALIB], ids=["ranobelib", "mangalib"])
def site(request: pytest.FixtureRequest) -> Site:
    """Each test using it runs once per site: nothing in the core may assume one site."""
    site: Site = request.param
    return site


@pytest.fixture(autouse=True)
def _no_request_pacing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Zero out ApiClient's default inter-request delay for the test suite.

    Every ApiClient shares the process-wide pacer for its host (see ``libsocial.pacing``),
    so without this, tests making several requests would wait out the real default delay —
    and wait on each other's requests too. Pacing itself is covered in ``test_pacing.py``
    with its own ``Pacer`` and a fake clock.
    """
    monkeypatch.setattr("libsocial.client.DEFAULT_REQUEST_DELAY", 0.0)

"""Shared pytest fixtures."""

from pathlib import Path
from typing import Any

import pytest

CASSETTE_DIR = Path(__file__).parent / "cassettes"


@pytest.fixture(scope="module")
def vcr_cassette_dir() -> str:
    return str(CASSETTE_DIR)


@pytest.fixture(scope="module")
def vcr_config() -> dict[str, Any]:
    return {"record_mode": "once"}


@pytest.fixture(autouse=True)
def _isolated_disk_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point MangaLib's and Catalog's default cache_dir at a per-test tmp_path.

    Otherwise tests that don't pass ``cache_dir`` would share a real ``.mangalib_cache/``
    across runs, and a response cached by an earlier run would stand in for the cassette.
    ``mangalib.sdk`` and ``mangalib.catalog`` each bind their own ``DEFAULT_CACHE_DIR``, so
    both are patched.
    """
    monkeypatch.setattr("mangalib.sdk.DEFAULT_CACHE_DIR", tmp_path / ".mangalib_cache")
    monkeypatch.setattr("mangalib.catalog.DEFAULT_CACHE_DIR", tmp_path / ".mangalib_cache")


@pytest.fixture(autouse=True)
def _no_request_pacing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Zero out the core ApiClient's default inter-request delay for the test suite.

    mangalib's ``ApiClient`` takes the core's default, read when a client is created; pacing
    itself is covered by libsocial-core's own tests.
    """
    monkeypatch.setattr("libsocial.client.DEFAULT_REQUEST_DELAY", 0.0)
    # Same for page images: MangaLib reads the image delay when it creates its fetcher.
    monkeypatch.setattr("mangalib.images.DEFAULT_IMAGE_REQUEST_DELAY", 0.0)

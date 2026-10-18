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
    """Point RanobeLib's and Catalog's default cache_dir at a per-test tmp_path.

    Without this, every ``RanobeLib(url)``/``Catalog()`` call in the test suite (the vast
    majority don't pass ``cache_dir`` explicitly) would share one real ``.ranobelib_cache/``
    directory under the repo root across test runs — polluting the repo and letting cached
    responses from a previous run silently replace what a cassette is supposed to be
    verifying. Both ``ranobelib.sdk`` and ``ranobelib.catalog`` import their own
    ``DEFAULT_CACHE_DIR`` binding from ``ranobelib.cache`` (module-level `from ... import`,
    not an attribute lookup through ``ranobelib.cache`` at call time), so each needs its own
    patch target — patching one doesn't affect the other.
    """
    monkeypatch.setattr("ranobelib.sdk.DEFAULT_CACHE_DIR", tmp_path / ".ranobelib_cache")
    monkeypatch.setattr("ranobelib.catalog.DEFAULT_CACHE_DIR", tmp_path / ".ranobelib_cache")


@pytest.fixture(autouse=True)
def _no_request_pacing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Zero out ApiClient's default inter-request delay for the test suite.

    RanobeLib doesn't expose ``request_delay`` (rate-limiting knobs live on ApiClient only,
    same as e.g. ``timeout`` — see docs/api-notes.md), so tests that make several requests
    through one RanobeLib instance (get_volume() and friends) would otherwise wait through
    the real default pacing delay for no benefit: that delay's own behavior is covered
    directly and deterministically in tests/unit/test_client.py with an injected fake clock.
    """
    monkeypatch.setattr("ranobelib.client.DEFAULT_REQUEST_DELAY", 0.0)

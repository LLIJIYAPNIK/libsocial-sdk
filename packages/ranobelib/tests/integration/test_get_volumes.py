"""Integration tests for RanobeLib.get_volumes(), backed by VCR cassettes.

These exercise the real api.cdnlibs.org API. Volumes 0 and 1 of 91443--new-hero-in-dxd
are small (1 and 3 chapters respectively), which keeps this test's cassette small.
"""

import pytest

from ranobelib import RanobeLib, VolumeNotFoundError
from ranobelib.models import Chapter, Volume


@pytest.mark.vcr
async def test_get_volumes_returns_volumes_in_requested_order() -> None:
    async with RanobeLib("https://ranobelib.me/ru/book/91443--new-hero-in-dxd") as lib:
        volumes = await lib.get_volumes([1, 0])

    assert len(volumes) == 2
    assert all(isinstance(volume, Volume) for volume in volumes)
    assert volumes[0].number == "1"
    assert volumes[1].number == "0"
    for volume in volumes:
        assert volume.chapters
        for chapter in volume.chapters:
            assert isinstance(chapter, Chapter)
            assert chapter.volume == volume.number
            assert chapter.content is not None


@pytest.mark.vcr
async def test_get_volumes_raises_volume_not_found_for_missing_volume() -> None:
    async with RanobeLib("https://ranobelib.me/ru/book/91443--new-hero-in-dxd") as lib:
        with pytest.raises(VolumeNotFoundError) as exc_info:
            await lib.get_volumes([0, 999])

    assert exc_info.value.volume == "999"

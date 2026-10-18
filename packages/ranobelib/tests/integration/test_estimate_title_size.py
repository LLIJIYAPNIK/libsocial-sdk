"""Integration tests for RanobeLib.estimate_title_size(), backed by VCR cassettes.

Reuses the same two small real titles as tests/integration/test_download_title.py — see its
module docstring — for exactly the same reason: small enough to keep cassettes tight while
still covering the two behaviors specific to this feature:

- 40195--enbizaka-no-shitateya: two chapters, no ambiguous translations — with the default
  sample_size (5, more than the title has), every chapter gets sampled, so the extrapolated
  estimate must equal the exact sum computed from sizing.chapter_size() once the same
  chapters are fully downloaded via download_title().
- 113306--bungou-stray-dogs-gaiden-ayatsuji-yukito-vs-kyogoku-natsuhiko: six chapters, three
  of which (numbers 0/1/2) are ambiguous. Without branch_id/translation_index,
  estimate_title_size() must skip those three as sampling candidates (unlike
  download_title(), which raises MultipleTitleTranslationsError) and still produce a
  positive estimate from the three unambiguous ones.
"""

import pytest

from ranobelib import RanobeLib
from ranobelib.sizing import chapter_size

_AMBIGUOUS_TITLE_URL = "https://ranobelib.me/ru/book/113306--bungou-stray-dogs-gaiden-ayatsuji-yukito-vs-kyogoku-natsuhiko"


@pytest.mark.vcr
async def test_estimate_title_size_matches_exact_sum_when_every_chapter_is_sampled() -> None:
    async with RanobeLib("https://ranobelib.me/ru/book/40195--enbizaka-no-shitateya") as lib:
        estimate = await lib.estimate_title_size()
        volumes = await lib.download_title()  # served from cache: same chapters already fetched

    exact = sum(chapter_size(chapter) for volume in volumes for chapter in volume.chapters)
    assert estimate == exact


@pytest.mark.vcr
async def test_estimate_title_size_skips_unresolved_ambiguous_chapters_by_default() -> None:
    async with RanobeLib(_AMBIGUOUS_TITLE_URL) as lib:
        estimate = await lib.estimate_title_size()

    assert estimate > 0


async def test_estimate_title_size_raises_value_error_when_both_selectors_given() -> None:
    async with RanobeLib("https://ranobelib.me/ru/book/40195--enbizaka-no-shitateya") as lib:
        with pytest.raises(ValueError):
            await lib.estimate_title_size(branch_id=1, translation_index=0)

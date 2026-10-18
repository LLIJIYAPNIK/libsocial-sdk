"""Integration tests for RanobeLib.download_title(), backed by VCR cassettes.

These exercise the real api.cdnlibs.org API through the public facade. Two small real
titles keep the cassettes small while still covering the feature:

- 40195--enbizaka-no-shitateya: a two-chapter, single-volume title with no ambiguous
  translations — the plain "download everything" happy path.
- 113306--bungou-stray-dogs-gaiden-ayatsuji-yukito-vs-kyogoku-natsuhiko: six chapters,
  three of which (numbers 0/1/2) have two competing translation branches each (branch_id
  12954 "dazaltix" and 12955 "ChelkaDostaTrans"), in a different order per chapter — exactly
  the case download_title()'s branch_id/translation_index resolution has to handle. See
  docs/api-notes.md's "Translation selection" section.
"""

import pytest

from ranobelib import MultipleTitleTranslationsError, RanobeLib

_AMBIGUOUS_TITLE_URL = "https://ranobelib.me/ru/book/113306--bungou-stray-dogs-gaiden-ayatsuji-yukito-vs-kyogoku-natsuhiko"


@pytest.mark.vcr
async def test_download_title_returns_all_volumes_with_content() -> None:
    async with RanobeLib("https://ranobelib.me/ru/book/40195--enbizaka-no-shitateya") as lib:
        volumes = await lib.download_title()

    assert len(volumes) == 1
    assert volumes[0].number == "1"
    assert [chapter.number for chapter in volumes[0].chapters] == ["0", "1"]
    assert all(chapter.content is not None for chapter in volumes[0].chapters)


async def test_download_title_raises_value_error_when_both_selectors_given() -> None:
    async with RanobeLib("https://ranobelib.me/ru/book/40195--enbizaka-no-shitateya") as lib:
        with pytest.raises(ValueError):
            await lib.download_title(branch_id=1, translation_index=0)


@pytest.mark.vcr
async def test_download_title_raises_multiple_title_translations_error_without_selection() -> None:
    async with RanobeLib(_AMBIGUOUS_TITLE_URL) as lib:
        with pytest.raises(MultipleTitleTranslationsError) as exc_info:
            await lib.download_title()

    assert {chapter.number for chapter in exc_info.value.chapters} == {"0", "1", "2"}


@pytest.mark.vcr
async def test_download_title_resolves_translation_index_positionally() -> None:
    # translation_index=0 must resolve per chapter by branches-list position, not a shared
    # branch_id: chapters 0/2 list branches [dazaltix, ChelkaDostaTrans] while chapter 1
    # lists them in the opposite order (see module docstring).
    async with RanobeLib(_AMBIGUOUS_TITLE_URL) as lib:
        volumes = await lib.download_title(translation_index=0)

    assert len(volumes) == 1
    assert [chapter.number for chapter in volumes[0].chapters] == ["0", "1", "2", "3", "4", "5"]
    assert all(chapter.content is not None for chapter in volumes[0].chapters)


@pytest.mark.vcr
async def test_download_title_applies_chapter_delay_between_chapters_not_after_last(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sleeps: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr("ranobelib.sdk.asyncio.sleep", fake_sleep)

    async with RanobeLib("https://ranobelib.me/ru/book/40195--enbizaka-no-shitateya") as lib:
        volumes = await lib.download_title(chapter_delay=0.75)

    assert sleeps == [0.75]
    assert [chapter.number for chapter in volumes[0].chapters] == ["0", "1"]


@pytest.mark.vcr
async def test_download_title_reports_progress_via_on_chapter_callback() -> None:
    calls: list[tuple[int, int]] = []

    async with RanobeLib("https://ranobelib.me/ru/book/40195--enbizaka-no-shitateya") as lib:
        await lib.download_title(
            on_chapter=lambda completed, total: calls.append((completed, total))
        )

    assert calls == [(1, 2), (2, 2)]

"""Integration tests for RanobeLib.get_relations() and Catalog.list_relation_types().

The logic is libsocial-core's and tested there; these check that ranobelib exposes it and
that real relations cross sites. Backed by VCR cassettes, like the other integration tests.
"""

import pytest

from ranobelib import Catalog, Label, RanobeLib, RelatedMedia, Relation, TitleNotFoundError

NOVEL = "https://ranobelib.me/ru/book/14841--beginning-after-the-end-novel"
ADAPTATION = 1


@pytest.mark.vcr
async def test_get_relations_returns_relations_across_sites() -> None:
    async with RanobeLib(NOVEL) as lib:
        relations = await lib.get_relations()

    assert relations
    assert all(isinstance(r, Relation) and isinstance(r.media, RelatedMedia) for r in relations)
    sites = {r.media.site_id for r in relations}
    assert {1, 3} <= sites  # A manga adaptation on mangalib.me and a novel on ranobelib.me.
    manga = [r.media for r in relations if r.media.site_id == 1]
    assert all(m.kind == "manga" for m in manga)
    assert any(r.type.id == ADAPTATION for r in relations)


@pytest.mark.vcr
async def test_get_relations_second_call_is_served_from_cache(vcr: object) -> None:
    async with RanobeLib(NOVEL) as lib:
        first = await lib.get_relations()
        second = await lib.get_relations()

    assert second == first
    assert len(vcr.requests) == 1  # type: ignore[attr-defined]


@pytest.mark.vcr
async def test_get_relations_raises_title_not_found_for_missing_title() -> None:
    async with RanobeLib("1--this-title-does-not-exist-zzz") as lib:
        with pytest.raises(TitleNotFoundError):
            await lib.get_relations()


@pytest.mark.vcr
async def test_list_relation_types_returns_labels() -> None:
    async with Catalog() as catalog:
        types = await catalog.list_relation_types()

    assert all(isinstance(t, Label) for t in types)
    labels = {t.id: t.label for t in types}
    assert labels[ADAPTATION] == "Адаптация"
    assert labels[2] == "Источник"

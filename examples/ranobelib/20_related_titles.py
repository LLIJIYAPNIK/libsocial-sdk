"""Related titles: sequels, prequels, spin-offs and adaptations with RanobeLib.get_relations().

get_relations() lists what a title's page shows under related titles. Each Relation has:

- type: a Label ("Продолжение", "Спин-офф", "Адаптация", ...). The full vocabulary is
  Catalog.list_relation_types(), so code can compare ids instead of Russian labels.
- media: the related title as RelatedMedia, not as a Title. Relations cross the whole
  lib.social network: a novel links to its manga (mangalib.me, slashlib.me) and its anime
  (anilib.me), and those aren't ranobelib.me titles. RelatedMedia.site_id says which site the
  related title lives on, and kind is "manga" (the API's word for any readable title, novels
  included) or "anime".

Only titles with site_id == RanobeLib.site.id (3) can be opened with RanobeLib: pass
media.slug_url. Manga on mangalib.me (site 1) open with mangalib.MangaLib (see
examples/core/07_related_titles.py); there is no SDK package for anime (site 5), and some
slashlib.me (site 2) titles can't be opened without logging in.
"""

import asyncio
import tempfile
from collections import defaultdict

from ranobelib import Catalog, Label, RanobeLib, RelatedMedia, Relation

NOVEL = "https://ranobelib.me/ru/book/6712--high-school-dxd-novel"
NOVEL_SLUG = "6712--high-school-dxd-novel"  # RelatedMedia.slug_url has this form.

SITE_NAMES = {1: "mangalib.me", 2: "slashlib.me", 3: "ranobelib.me", 5: "anilib.me"}


async def main() -> None:
    # A throwaway cache, so the "Expected output" doesn't depend on an earlier run.
    with tempfile.TemporaryDirectory() as cache_dir:
        # Relation types are the same on every site (they carry no site_ids, so Catalog
        # doesn't filter them). Cached on disk like the other lookups; refresh=True re-fetches.
        async with Catalog(cache_dir=cache_dir) as catalog:
            types: list[Label] = await catalog.list_relation_types()
        by_label = {t.label: t.id for t in types}
        sequel, spin_off, adaptation = by_label["Продолжение"], by_label["Спин-офф"], 1
        print(f"{len(types)} relation types; sequel={sequel}, spin-off={spin_off}")

        async with RanobeLib(NOVEL, cache_dir=cache_dir) as lib:
            # In the order the title page shows them. Cached like get_info() — the second
            # call doesn't hit the API — and refresh=True bypasses the cache.
            relations: list[Relation] = await lib.get_relations()
            assert await lib.get_relations() == relations

        # Group by site: what each one points at, and who can open it.
        per_site: dict[int, list[RelatedMedia]] = defaultdict(list)
        for relation in relations:
            per_site[relation.media.site_id].append(relation.media)
        print(f"\n{len(relations)} related titles:")
        for site_id, group in per_site.items():
            kinds = sorted({m.kind for m in group})
            print(f"  site {site_id} ({SITE_NAMES.get(site_id, '?')}): {len(group)} {kinds}")

        # `type` on RelatedMedia is raw: for readable titles it's the site's type classifier
        # (what Title.country maps on ranobelib.me), for anime the format (TV, OVA, ...).
        print("\nanime adaptations (media.type is the format here):")
        for relation in relations:
            media = relation.media
            if relation.type.id == adaptation and media.kind == "anime":
                print(f"  {media.type.label if media.type else '?'}: {media.rus_name}")

        # Novels on ranobelib.me itself: open them with RanobeLib. The relation type tells
        # how each relates to *this* title (the sequel, the prequel, a spin-off, ...).
        print("\nrelated novels on ranobelib.me:")
        for relation in relations:
            media = relation.media
            if media.site_id != RanobeLib.site.id:
                continue
            async with RanobeLib(media.slug_url, cache_dir=cache_dir) as related:
                info = await related.get_info()
            print(f"  {relation.type.label}: {info.rus_name} — {info.chapter_count} chapters")

        # The type is read from the related title's side. Open the sequel and look back: from
        # there, this novel is the "Предыстория" (prequel), not the "Продолжение".
        sequel_media = next(r.media for r in relations if r.type.id == sequel)
        async with RanobeLib(sequel_media.slug_url, cache_dir=cache_dir) as lib:
            back = [r for r in await lib.get_relations() if r.media.slug_url == NOVEL_SLUG]
        for relation in back:
            print(f"\nfrom {sequel_media.slug_url}: this novel is the {relation.type.label!r}")


if __name__ == "__main__":
    asyncio.run(main())

# Expected output (real run against the live site on 2026-11-03; relations are edited by the
# site, so the list and the chapter counts can change over time):
#
# 17 relation types; sequel=4, spin-off=6
#
# 19 related titles:
#   site 3 (ranobelib.me): 6 ['manga']
#   site 2 (slashlib.me): 3 ['manga']
#   site 5 (anilib.me): 10 ['anime']
#
# anime adaptations (media.type is the format here):
#   TV Сериал: Старшая школа DxD
#   OVA: Старшая школа DxD OVA
#   Спешл: Старшая школа DxD: Спецвыпуски
#   TV Сериал: Старшая школа DxD New
#   OVA: Старшая школа DxD New OVA
#   TV Сериал: Старшая школа DxD: Рождение
#   OVA: Старшая школа DxD: Рождение — Эпизод 13
#   Спешл: Старшая школа DxD: Рождение — Спецвыпуски
#   Неизвестный: Старшая школа DxD: Герой — Эпизод 0
#   TV Сериал: Старшая школа DxD: Герой
#
# related novels on ranobelib.me:
#   Продолжение: Истинная Старшая Школа D×D — 72 chapters
#   Предыстория: Старшая Школа D×D: Начало (Новелла) — 5 chapters
#   Альтернативная история: Старшая Школа D×D EX (Новелла) — 8 chapters
#   Развёрнутая история: Старшая школа D×D DX — 110 chapters
#   Спин-офф: Падший Бог-Пёс —SLASHDØG— (Новелла) — 45 chapters
#   Спин-офф: Старшая школа D×D: Младшие — 10 chapters
#
# from 22513--shin-high-school-dxd: this novel is the 'Предыстория'

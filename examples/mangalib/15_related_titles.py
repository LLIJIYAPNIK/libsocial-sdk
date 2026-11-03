"""Related titles: sequels, colored versions, novel spin-offs and anime with get_relations().

MangaLib.get_relations() lists what a title's page shows under related titles. Each Relation
has a type (a Label: "Продолжение", "Цветная версия", "Адаптация", ...; the full list is
Catalog.list_relation_types()) and the related title as RelatedMedia.

Relations cross the whole lib.social network, so RelatedMedia isn't mangalib's Title:

- site_id: the site the related title lives on. Only site_id == MangaLib.site.id (1) opens
  with MangaLib (pass media.slug_url). A novel (site 3) opens with ranobelib.RanobeLib — see
  examples/core/07_related_titles.py, which does just that — and there is no SDK package for
  anime (anilib.me, site 5).
- kind: "manga" for any readable title (novels included — the API's naming) or "anime".
- type: raw. For readable titles it's their site's type classifier, what Title.country maps
  ("Манга", "Манхва", ... on mangalib.me; "Япония", ... on ranobelib.me); for anime the format.
"""

import asyncio
import tempfile

from mangalib import Catalog, Label, MangaLib, RelatedMedia, Relation

MANGA = "https://mangalib.me/ru/manga/7965--chainsaw-man"


def describe(media: RelatedMedia) -> str:
    kind = media.type.label if media.type is not None else "?"
    return f"{media.kind}/{kind} on site {media.site_id}: {media.rus_name}"


async def main() -> None:
    # A throwaway cache, so the "Expected output" doesn't depend on an earlier run.
    with tempfile.TemporaryDirectory() as cache_dir:
        # The same vocabulary on every site: Catalog doesn't filter relation types by site.
        async with Catalog(cache_dir=cache_dir) as catalog:
            types: list[Label] = await catalog.list_relation_types()
        ids = {t.label: t.id for t in types}
        print(f"{len(types)} relation types, e.g. {[t.label for t in types[1:5]]}")

        async with MangaLib(MANGA, cache_dir=cache_dir) as lib:
            # In the page's order. Cached on disk like get_info(); refresh=True re-fetches.
            relations: list[Relation] = await lib.get_relations()

        print(f"\n{len(relations)} titles related to Chainsaw Man:")
        for relation in relations:
            print(f"  {relation.type.label}: {describe(relation.media)}")

        # Pick by id, not by label — then open what's on mangalib.me with MangaLib.
        wanted = {ids["Продолжение"], ids["Цветная версия"]}
        print("\nopened with MangaLib:")
        for relation in relations:
            media = relation.media
            if relation.type.id in wanted and media.site_id == MangaLib.site.id:
                async with MangaLib(media.slug_url, cache_dir=cache_dir) as related:
                    info = await related.get_info()
                country = info.country.name if info.country else "?"
                print(f"  {info.slug_url}: {info.chapter_count} chapters ({country})")

        # Everything else needs another package (or none exists).
        print("\nnot on mangalib.me:")
        for relation in relations:
            if relation.media.site_id != MangaLib.site.id:
                print(f"  site {relation.media.site_id}: {relation.media.slug_url}")


if __name__ == "__main__":
    asyncio.run(main())

# Expected output (real run against the live site on 2026-11-03; relations are edited by the
# site, so the list and the chapter counts can change over time):
#
# 17 relation types, e.g. ['Адаптация', 'Источник', 'Предыстория', 'Продолжение']
#
# 5 titles related to Chainsaw Man:
#   Продолжение: manga/Манга on site 1: Человек-бензопила 2
#   Адаптация: anime/TV Сериал on site 5: Человек-бензопила
#   Цветная версия: manga/Манга on site 1: Человек-бензопила (Официальная цветная версия)
#   Спин-офф: manga/Япония on site 3: Человек-бензопила: Истории о напарниках (Новелла)
#   Адаптация: anime/Фильм on site 5: Человек-бензопила: Резе
#
# opened with MangaLib:
#   55901--chainsaw-man-2: 139 chapters (Манга)
#   54714--chaisawman-full-color: 105 chapters (Манга)
#
# not on mangalib.me:
#   site 5: 17984--chainsaw-man-anime
#   site 3: 94226--chainsaw-man-buddy-stories
#   site 5: 23126--chainsaw-man-movie-reze-hen-anime

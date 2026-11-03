"""Related titles: adaptations, source, sequels, spin-offs — across the whole network.

TitleClient.get_relations() lists what a title page shows as related titles. Each Relation has
a type (a Label: "Адаптация", "Источник", "Продолжение", ...) and the related title as
RelatedMedia. Relations cross sites: a novel on ranobelib.me links to its manga on mangalib.me
and its anime on anilib.me. So RelatedMedia is not a site's Title model. It carries:

- site_id: which site the related title lives on. Open it with that site's client, passing
  media.slug_url. There is no SDK package for anime (anilib.me, site 5), and some site 2
  titles can't be opened without logging in.
- kind: "manga" (the API's name for every readable title, novels included) or "anime".
- type: the raw API field. For readable titles it's the type classifier of the title's own
  site, what Title.country maps (Japan, English, ... on ranobelib; Manga, Comic, ... on
  mangalib). For anime it's the format (TV series, OVA, ...).

Relation types are read from the related title's side: on the novel, the manga is an
"Адаптация"; on that manga, the novel is its "Источник". Catalog.list_relation_types() lists
every type, so code can pick relations by id rather than by the Russian label.

Needs both ranobelib-python-sdk and mangalib-python-sdk installed, like 06.
"""

import asyncio
import tempfile

import mangalib
import ranobelib
from libsocial import Label, RelatedMedia, Relation

NOVEL = "https://ranobelib.me/ru/book/14841--beginning-after-the-end-novel"
ADAPTATION = 1  # Relation type id, from list_relation_types() below.


def describe(relation: Relation) -> str:
    media: RelatedMedia = relation.media
    origin_or_format = media.type.label if media.type is not None else "?"
    return (
        f"{relation.type.label}: {media.kind} on site {media.site_id} "
        f"({origin_or_format}) {media.slug_url}"
    )


async def main() -> None:
    with tempfile.TemporaryDirectory() as cache_dir:
        # The relation type vocabulary is the same on every site: no filtering by site_ids.
        async with ranobelib.Catalog(cache_dir=cache_dir) as catalog:
            types: list[Label] = await catalog.list_relation_types()
        print(f"{len(types)} relation types:", ", ".join(f"{t.id} {t.label}" for t in types))

        async with ranobelib.RanobeLib(NOVEL, cache_dir=cache_dir) as novel:
            relations = await novel.get_relations()  # Cached like get_info(); refresh=True.
        print(f"\n{len(relations)} titles related to the novel, in the page's order:")
        for relation in relations:
            print("  ", describe(relation))

        # Who can open what: each site package fetches titles on its own site only.
        sites = {
            ranobelib.RanobeLib.site.id: "ranobelib",
            mangalib.MangaLib.site.id: "mangalib",
        }
        for relation in relations:
            package = sites.get(relation.media.site_id, "no SDK package")
            print(f"   {relation.media.slug_url}: {package}")

        # Open the manga adaptation with mangalib, and look at the relation from its side.
        manga = next(
            r.media
            for r in relations
            if r.type.id == ADAPTATION and r.media.site_id == mangalib.MangaLib.site.id
        )
        async with mangalib.MangaLib(manga.slug_url, cache_dir=cache_dir) as comic:
            info = await comic.get_info()
            back = await comic.get_relations()
        print(f"\nmangalib {info.slug_url}: {info.chapter_count} chapters")
        for relation in back:
            if relation.media.site_id == ranobelib.RanobeLib.site.id:
                print("   from the manga's side:", describe(relation))


if __name__ == "__main__":
    asyncio.run(main())

# Expected output (real run against the live sites on 2026-11-03; relations are edited by the
# sites, so the list can change over time. On Windows without the GTK runtime, importing
# ranobelib first prints WeasyPrint's warning that it couldn't load its libraries, as in 06):
#
# 17 relation types: 0 Нет, 1 Адаптация, 2 Источник, 3 Предыстория, 4 Продолжение, 5
#   Альтернативная история, 6 Спин-офф, 7 Кроссовер, 8 Цветная версия, 9 Перезапуск, 10 Другое,
#   11 Обобщение, 12 Одна вселенная, 15 Альтернативная история, 16 Развёрнутая история, 13
#   Изначальная история, 14 Общий персонаж
#
# 4 titles related to the novel, in the page's order:
#    Адаптация: manga on site 1 (Комикс) 6478--the-beginning-after-the-end
#    Адаптация: anime on site 5 (TV Сериал)
#   24430--saikyou-no-ousama-nidome-no-jinsei-wa-nani-wo-suru-anime
#    Спин-офф: manga on site 3 (Английский)
#   107378--the-beginning-after-the-end-amongst-the-fallen-novel
#    Другое: manga on site 1 (Комикс) 183849--jasmine-wind-borne
#    6478--the-beginning-after-the-end: mangalib
#    24430--saikyou-no-ousama-nidome-no-jinsei-wa-nani-wo-suru-anime: no SDK package
#    107378--the-beginning-after-the-end-amongst-the-fallen-novel: ranobelib
#    183849--jasmine-wind-borne: mangalib
#
# mangalib 6478--the-beginning-after-the-end: 229 chapters
#    from the manga's side: Источник: manga on site 3 (Английский)
#   14841--beginning-after-the-end-novel
#    from the manga's side: Другое: manga on site 3 (Английский)
#   107378--the-beginning-after-the-end-amongst-the-fallen-novel

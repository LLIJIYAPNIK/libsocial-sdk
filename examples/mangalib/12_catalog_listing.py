"""Browse and search the mangalib.me catalog with Catalog.

Catalog is a separate entry point from MangaLib: listing the whole site isn't tied to one
title, so it takes no URL. It's the same class as ranobelib's Catalog (both come from
libsocial-core), pointed at mangalib.me.

- `list_titles()` returns a `CatalogPage`: `items` (list[Title]), `page`, `has_next_page`.
  Each item is the same `Title` model as MangaLib.get_info(), but the listing endpoint sends
  fewer fields: no genres/tags/summary/chapter_count. For those, open the title in MangaLib.
- Filter lookups: `list_genres()` (`Genre`), `list_countries()` (`Country`) and
  `list_statuses()` (`Label`, the same model as `Title.status`). The API serves each of them
  for the whole lib.social network at once; Catalog keeps only mangalib.me's entries.
- Filters: `query`, `genres` and `tags` (a title must have all of them), `statuses` and
  `countries` (a title has one of each, so it matches any of them), `min_chapters` /
  `max_chapters` (inclusive), `sort`, `page` / `per_page` (10-60).
- Every page and lookup is cached on disk, keyed by its parameters; `refresh=True` re-fetches.
"""

import asyncio
import tempfile
import time

from mangalib import Catalog, CatalogPage, Country, Genre, Label, MangaLib, Title


def describe(title: Title) -> str:
    kind = title.country.name if title.country else "?"
    return f"{title.slug_url}: {title.name} ({kind}, {title.status.label})"


async def main() -> None:
    # A fresh cache directory, so the caching part at the end really starts empty. Leave
    # cache_dir out to use .mangalib_cache in the current directory, shared with MangaLib.
    with tempfile.TemporaryDirectory() as cache_dir:
        async with Catalog(cache_dir=cache_dir) as catalog:
            # No filters: the whole catalog, most recently updated first (sort's default,
            # "last_chapter_at"). There's no total count, only has_next_page.
            # The page is a mangalib.CatalogPage, its items mangalib.Title (with base_names).
            # list_titles() is annotated with the core's CatalogPage[Title], so that's what a
            # type checker sees; the fields are the same.
            page = await catalog.list_titles(per_page=10)
            print(type(page).__module__, isinstance(page, CatalogPage))
            print(f"page {page.page}: {len(page.items)} titles, has_next_page={page.has_next_page}")
            for title in page.items[:3]:
                print(" ", describe(title))

            # Free-text search over name/rus_name/eng_name.
            found = await catalog.list_titles(query="chainsaw man", per_page=10)
            print("\nsearch 'chainsaw man':")
            for title in found.items[:5]:
                print(" ", describe(title))

            # --- Filter lookups -------------------------------------------------------------

            # 49 genres. The network-wide list also has genres only other sites use (88
            # "Детское" exists only on site 5); those are filtered out. `adult` marks the
            # 18+ ones.
            genres: list[Genre] = await catalog.list_genres()
            print(f"\n{len(genres)} genres, adult: {[g.name for g in genres if g.adult]}")
            by_name = {genre.name: genre for genre in genres}

            # "Countries" on mangalib.me are title types. The API calls this field `type`
            # everywhere (Title's `type`, the `types[]` filter, `fields[]=types`); the SDK
            # named it Country after ranobelib.me, where it's Japan/Korea/China. On
            # mangalib.me it's the format: manga, manhwa, manhua, ... — and the ids differ
            # (ranobelib's are 10-15), so ids from one site's Catalog mean nothing on the
            # other's.
            countries: list[Country] = await catalog.list_countries()
            print("countries (types):", [(c.id, c.name) for c in countries])
            kinds = {country.name: country for country in countries}

            statuses: list[Label] = await catalog.list_statuses()
            print("statuses:", [(s.id, s.label) for s in statuses])
            status = {label.label: label for label in statuses}

            # --- Filters --------------------------------------------------------------------

            # genres: AND. Adding an id no title has empties the result instead of leaving it
            # unchanged — that's how the AND was checked. Unknown ids aren't an error.
            action = by_name["Боевик"]
            sports = by_name["Спорт"]
            both = await catalog.list_titles(genres=[action.id, sports.id], per_page=10)
            print(f"\n{action.name} AND {sports.name}:")
            for title in both.items[:3]:
                print(" ", describe(title))
            nothing = await catalog.list_titles(genres=[action.id, 999999], per_page=10)
            print(f"{action.name} AND an unknown genre: {len(nothing.items)} titles")

            # statuses and countries: OR. sort="name" mixes the matches, so both show up.
            manhwa, manhua = kinds["Манхва"], kinds["Маньхуа"]
            either = await catalog.list_titles(
                countries=[manhwa.id, manhua.id], per_page=60, sort="name"
            )
            print(f"\n{manhwa.name} OR {manhua.name}:")
            for kind in (manhwa, manhua):
                for title in [t for t in either.items if t.country == kind][:2]:
                    print(" ", describe(title))

            finished = await catalog.list_titles(
                statuses=[status["Завершён"].id, status["Приостановлен"].id],
                countries=[kinds["Манга"].id],
                per_page=60,
                sort="name",
            )
            print("\nfinished OR paused manga:")
            print(" ", sorted({t.status.label for t in finished.items}))

            # Chapter count, both bounds inclusive; the items don't carry it, so sort by it.
            longest = await catalog.list_titles(min_chapters=1000, sort="chap_count", per_page=10)
            print("\n1000+ chapters, most first:")
            for title in longest.items[:3]:
                print(" ", describe(title))
            oneshots = await catalog.list_titles(max_chapters=1, sort="views", per_page=10)
            print("at most 1 chapter, most viewed first:")
            for title in oneshots.items[:3]:
                print(" ", describe(title))

            # Wrong bounds fail before any request.
            for kwargs in (
                {"per_page": 9},
                {"per_page": 61},
                {"min_chapters": 5, "max_chapters": 1},
            ):
                try:
                    await catalog.list_titles(**kwargs)  # type: ignore[arg-type]
                except ValueError as exc:
                    print("ValueError:", exc)

            # --- Pagination -----------------------------------------------------------------

            # Walk pages until has_next_page is False (capped, in case the search is broad).
            print("\nevery page of 'chainsaw':")
            page_number, total = 1, 0
            while page_number <= 5:
                current = await catalog.list_titles(query="chainsaw", page=page_number, per_page=10)
                total += len(current.items)
                print(f"  page {current.page}: {len(current.items)} titles")
                if not current.has_next_page:
                    break
                page_number += 1
            print(f"  {total} titles in all")

            # --- From a catalog item to MangaLib --------------------------------------------

            # slug_url is all MangaLib needs. get_info() fills in what the listing left out,
            # tags included — and tag ids for the `tags` filter come from there: there's no
            # list_tags().
            chainsaw = next(t for t in found.items if t.slug_url == "7965--chainsaw-man")
            print("\nlisting item: chapter_count", chainsaw.chapter_count, "tags", chainsaw.tags)
            async with MangaLib(chainsaw.slug_url, cache_dir=cache_dir) as lib:
                info = await lib.get_info()
            print(
                f"get_info(): {info.chapter_count} chapters, genres {[g.name for g in info.genres]}"
            )
            print("tags:", [(tag.id, tag.name) for tag in info.tags[:4]])

            # tags: AND, like genres. Chainsaw Man has both of its first two tags.
            first_two = [tag.id for tag in info.tags[:2]]
            tagged = await catalog.list_titles(tags=first_two, per_page=60, sort="views")
            names = " AND ".join(tag.name for tag in info.tags[:2])
            print(
                f"{names}: {len(tagged.items)} titles on page 1, Chainsaw Man among them:",
                any(t.id == info.id for t in tagged.items),
            )

            # --- Caching --------------------------------------------------------------------

            # The same parameters again come from disk; refresh=True asks the API again (and
            # updates the cached copy).
            for refresh in (False, True):
                start = time.perf_counter()
                again = await catalog.list_titles(
                    query="chainsaw man", per_page=10, refresh=refresh
                )
                elapsed = time.perf_counter() - start
                source = "API" if refresh else "cache"
                print(
                    f"\nrefresh={refresh}: {len(again.items)} titles from the {source}, "
                    f"{elapsed * 1000:.0f} ms",
                    end="",
                )
            print()


asyncio.run(main())

# Expected output (real run against the live site on 2026-10-25; titles are added and
# updated constantly, so the listings drift over time — that's the site changing, not a bug;
# the timings vary from run to run):
#
# mangalib.models True
# page 1: 10 titles, has_next_page=True
#   248157--witch-ribu: WITCHRIV (Манга, Онгоинг)
#   235297--konya-coin-laundry-de-aimashou: Kon’ya Coin Laundry de Aimashou (Манга, Онгоинг)
#   274200--hoegwijawa-maeng-in-seongnyeo: hoegwijawa maeng-in seongnyeo (Манхва, Онгоинг)
#
# search 'chainsaw man':
#   55901--chainsaw-man-2: Chainsaw Man 2 (Манга, Завершён)
#   251901--chainsaw-man-fan-one-shot-reze-and-yuki-story: Chainsaw man: fan one-shot Reze and Yuki
#   story (Комикс, Завершён)
#   54714--chaisawman-full-color: Chainsaw Man - Digital Colored Comics (Манга, Приостановлен)
#   65356--chainsaw-man-the-story-of-himeno-aki-and-tobacco: Chainsaw Man dj - The Story of Himeno,
#   Aki and Tobacco (Манга, Завершён)
#   210063--dragon-ball-amp-chainsaw-man-x-sponge-bob: Dragon Ball & Chainsaw Man X Sponge Bob
#   (Манга, Завершён)
#
# 49 genres, adult: ['Гендерная интрига', 'Эротика']
# countries (types): [(1, 'Манга'), (4, 'OEL-манга'), (5, 'Манхва'), (6, 'Маньхуа'), (8, 'Руманга'),
#   (9, 'Комикс')]
# statuses: [(1, 'Онгоинг'), (2, 'Завершён'), (3, 'Анонс'), (4, 'Приостановлен'), (5, 'Выпуск
#   прекращён')]
#
# Боевик AND Спорт:
#   8380--over-rev: Over Rev! (Манга, Завершён)
#   246480--eondeobogseo: eondeobogseo (Манхва, Онгоинг)
#   89791--baki-gaiden-retsu-kaioh-isekai-tensei-shitemo-ikko-kamawan: Baki Gaiden - Retsu Kaioh
#   Isekai Tensei Shitemo Ikkou Kamawan! (Манга, Онгоинг)
# Боевик AND an unknown genre: 0 titles
#
# Манхва OR Маньхуа:
#   247091--gamgmdanghan-namjurl-dowajwssderni-jipchacnami-doeassspnida: Я помогала главному герою-
#   заключенному, но он стал одержимым (Манхва, Онгоинг)
#   155697--uebge-unen-namza: Уеbgе unеn nаmzа (Манхва, Онгоинг)
#   276220--dingji-rou-dun-huigui-yikao-wan-bei-gong-su-wushuang: ★Dǐngjí ròu dùn ★huíguī ~yīkào wàn
#   bèi gōng sù wúshuāng (Маньхуа, Онгоинг)
#   11765--shuang-xiu-ai-xuan-yixian: “Shuang xiu” - ai xuan yixian (Маньхуа, Завершён)
#
# finished OR paused manga:
#   ['Завершён', 'Приостановлен']
#
# 1000+ chapters, most first:
#   106362--peanuts: Peanuts (Комикс, Завершён)
#   48556--dark-side-of-the-horse: Dark Side of the Horse (Комикс, Онгоинг)
#   1356--hajime-no-ippo: Hajime no Ippo (Манга, Приостановлен)
# at most 1 chapter, most viewed first:
#   86572--look-back: Look back (Манга, Завершён)
#   122925--goodbye-eri: Goodbye Eri (Манга, Завершён)
#   17652--igrok-kotoryy-vernulsya-spustya-10-000-let: man nyeon mane gwihwanhan peulleieo (Манхва,
#   Завершён)
# ValueError: per_page must be between 10 and 60, got 9.
# ValueError: per_page must be between 10 and 60, got 61.
# ValueError: min_chapters (5) must not be greater than max_chapters (1).
#
# every page of 'chainsaw':
#   page 1: 10 titles
#   page 2: 5 titles
#   15 titles in all
#
# listing item: chapter_count None tags []
# get_info(): 107 chapters, genres ['Боевик', 'Комедия', 'Сверхъестественное', 'Сёнэн', 'Трагедия',
#   'Ужасы', 'Фэнтези']
# tags: [(82, 'Монстры'), (155, 'Зомби'), (175, 'Антигерой'), (247, 'Дружба')]
# Монстры AND Зомби: 60 titles on page 1, Chainsaw Man among them: True
#
# refresh=False: 9 titles from the cache, 10 ms
# refresh=True: 9 titles from the API, 186 ms

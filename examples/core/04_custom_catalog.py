"""A catalog for a site without a package: slashlib.me, on libsocial.Catalog.

The listing and its filters are all in the core; a site's Catalog only says which site
(`site`), what a page is (`page_model`: CatalogPage[ItsTitle], which also decides the model of
the items) and optionally where it caches (`default_cache_dir`).

The genre, type and status lookups come from one endpoint for the whole network, every entry
tagged with the sites it's for; Catalog keeps only its site's. So the same call on two sites'
catalogs gives different lists, and an id from one is meaningless on the other.

Pages and lookups are cached on disk like a TitleClient's responses; `cache_stats()` /
`clear_cache()` measure and empty that cache, returning `CacheStats(entries, bytes)`.
"""

import asyncio
import tempfile
from pathlib import Path

from libsocial import (
    ApiClient,
    CacheStats,
    Catalog,
    CatalogPage,
    Country,
    Genre,
    Label,
    Site,
    cache_stats,
    clear_cache,
)
from libsocial.models import Title

SLASHLIB = Site(id=2, origin="https://slashlib.me")
MANGALIB = Site(id=1, origin="https://mangalib.me")


class SlashCatalog(Catalog[Title]):
    site = SLASHLIB
    page_model = CatalogPage[Title]
    default_cache_dir = Path(".slashlib_cache")


class MangaCatalog(Catalog[Title]):
    # The same few lines are all mangalib's own Catalog adds, besides its models.
    site = MANGALIB
    page_model = CatalogPage[Title]


async def main() -> None:
    with tempfile.TemporaryDirectory() as cache_dir:
        async with (
            SlashCatalog(cache_dir=cache_dir) as catalog,
            MangaCatalog(cache_dir=cache_dir) as manga,
        ):
            genres: list[Genre] = await catalog.list_genres()
            countries: list[Country] = await catalog.list_countries()
            statuses: list[Label] = await catalog.list_statuses()

            # What the endpoint itself sends, through the raw client.
            async with ApiClient(SLASHLIB) as client:
                network = await client.list_genres()
                network_types = await client.list_countries()
            print(
                f"genres: {len(network)} in the network, {len(genres)} for slashlib, "
                f"{len(await manga.list_genres())} for mangalib"
            )
            only_here = {g.name for g in genres} - {g.name for g in await manga.list_genres()}
            print(f"{len(only_here)} genres are on slashlib but not on mangalib")
            print(
                f"types: {len(network_types)} in the network; slashlib's:",
                [c.name for c in countries],
            )
            print("statuses:", [s.label for s in statuses])

            # list_titles() as on any site; ids come from the lookups above.
            manhwa = next(c for c in countries if c.name == "Манхва")
            completed = next(s for s in statuses if s.label == "Завершён")
            comedy = next(g for g in genres if g.name == "Комедия")
            page = await catalog.list_titles(
                countries=[manhwa.id],
                statuses=[completed.id],
                genres=[comedy.id],
                sort="views",
                per_page=10,
            )
            print(f"\ncompleted comedy manhwa, most viewed (page {page.page}):")
            # age_restriction is on every listing item; this skips the 18+ ones.
            for title in [t for t in page.items if t.age_restriction.label != "18+"][:3]:
                print(f"  {title.slug_url} ({title.age_restriction.label})")

        stats: CacheStats = cache_stats(cache_dir)
        print("\ncache:", stats)
        print("older than an hour:", clear_cache(cache_dir, older_than=3600))
        print("all:", clear_cache(cache_dir), "->", cache_stats(cache_dir))


if __name__ == "__main__":
    asyncio.run(main())

# Expected output (real run against the live API on 2026-10-25; the lookups and the listing
# change as the sites add genres and titles):
#
# genres: 58 in the network, 56 for slashlib, 49 for mangalib
# 7 genres are on slashlib but not on mangalib
# types: 20 in the network; slashlib's: ['Манга', 'OEL-манга', 'Манхва', 'Маньхуа', 'Руманга',
#   'Комикс']
# statuses: ['Онгоинг', 'Завершён', 'Анонс', 'Приостановлен', 'Выпуск прекращён']
#
# completed comedy manhwa, most viewed (page 1):
#   33138--sinyeolo-sal-anamgi (6+)
#   8893--naui-manyeo (16+)
#   158655--du-malileul-wihan-tteul (16+)
#
# cache: CacheStats(entries=4, bytes=49279)
# older than an hour: CacheStats(entries=0, bytes=0)
# all: CacheStats(entries=4, bytes=49279) -> CacheStats(entries=0, bytes=0)

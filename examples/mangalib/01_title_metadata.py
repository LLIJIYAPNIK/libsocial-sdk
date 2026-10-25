"""Fetch a manga's metadata with MangaLib.get_info().

`pip install mangalib-python-sdk`. mangalib.me runs on the same API as ranobelib.me, so
`MangaLib` has the same methods as `RanobeLib` and `get_info()` returns the same kind of
`Title`: one request to the title endpoint, no chapter list, no pages. What differs is the
site, and with it the meaning of some fields — `country` above all (see below).
"""

import asyncio

from mangalib import MangaLib


async def main() -> None:
    # MangaLib is an async context manager: it owns the HTTP client and closes it on exit.
    # The only required argument is the title, as its page URL...
    url = "https://mangalib.me/ru/manga/262329--kidou-senshi-gundam-battle-operation-code-fairy"
    async with MangaLib(url) as lib:
        # ...which the SDK reduces to the `{id}--{slug}` the API addresses titles by.
        print(lib.slug_url)
        info = await lib.get_info()

        # `name` is the original (romanized) title, `rus_name`/`eng_name` translations of it;
        # `other_names` whatever else the site lists. All exactly as the API sends them.
        print(info.name, "|", info.rus_name, "|", info.eng_name)

        # status and age_restriction are Label(id, label): the label is the site's own text.
        print(info.status.label, info.age_restriction.label, info.release_date)

        # `country` is the field ranobelib.me uses for a title's country of origin. On
        # mangalib.me the same field holds the *type* of the work — манга, OEL-манга,
        # манхва, маньхуа, руманга, комикс; the model keeps one name for both sites (see
        # docs/api-notes.md, "MangaLib").
        print(info.country.name if info.country else None)

        # Genres and tags are separate lists of (id, name, adult); the ids are what
        # Catalog.list_titles(genres=[...], tags=[...]) filters by.
        print([genre.name for genre in info.genres[:4]], [tag.name for tag in info.tags[:3]])

        # People: authors (story), artists (drawing) — often the same person for manga —
        # and the translation teams credited on the title.
        print([p.name for p in info.authors], [p.name for p in info.artists])
        print([team.name for team in info.teams])

        # The chapter count as the site reports it, and when the newest chapter appeared
        # (UTC). Catalog listings don't carry either, only get_info() does.
        print(info.chapter_count, info.last_chapter_at)

        # Cover URLs in several sizes (thumbnail / md / default), on the cover CDN.
        print(info.cover.thumbnail)

    # A bare `{id}--{slug}` works as well as the full URL.
    async with MangaLib("212879--return-of-the-runebound-professor-webtoon") as lib:
        info = await lib.get_info()
        print(info.name)
        # mangalib.me doesn't add a format marker to names itself (ranobelib.me always adds
        # "(Новелла)"), but some names were typed with one — "(webtoon)", "(Manhwa)",
        # "[Вебтун]", ... `base_names` lists every name without it, deduplicated: handy for
        # looking the title up elsewhere by name. Tails that tell versions apart, like
        # "(манга-версия)", are kept.
        print(info.base_names)


if __name__ == "__main__":
    asyncio.run(main())

# Expected output (real run against the live site; the long lines are wrapped here):
#
# 262329--kidou-senshi-gundam-battle-operation-code-fairy
# Kidou Senshi Gundam: Battle Operation Code Fairy | Мобильный Воин Гандам: Боевая операция
#   Код Фея | Mobile Suit Gundam: Battle Operation Code Fairy
# Завершён 12+ 2021
# Манга
# ['Боевик', 'Драма', 'Меха', 'Научная фантастика'] ['Гяру', 'Военные', 'Бои на мечах']
# ['Takagi Shuuei'] ['Takagi Shuuei']
# ['Ave_Jalter']
# 12 2026-07-24 14:00:02+00:00
# https://cover.imglib.info/uploads/cover/kidou-senshi-gundam-battle-operation-code-fairy/
#   cover/1ae00dfc-f617-4192-940e-990b109a5fde_thumb.jpg
# Return of the Runebound Professor (webtoon)
# ['Возвращение Профессора Рун', 'Return of the Runebound Professor']

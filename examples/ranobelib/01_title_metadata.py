"""Fetch title metadata with RanobeLib.get_info().

get_info() is the cheapest call in the SDK: one request to the title metadata endpoint,
returning a Title model (name, status, genres, authors, etc.) without touching the chapter
list or any chapter content at all.
"""

import asyncio

from ranobelib import RanobeLib


async def main() -> None:
    # RanobeLib is an async context manager: it owns the underlying httpx.AsyncClient and
    # closes it on exit, so always use `async with` rather than instantiating it bare.
    # The only required argument is the title's URL (any ranobelib.me title page works).
    async with RanobeLib("https://ranobelib.me/ru/book/6712--high-school-dxd-novel") as lib:
        info = await lib.get_info()

        # `name` is the original (usually Japanese/romanized) title, `rus_name` is the
        # Russian translation of the title itself — both come straight from the API,
        # neither is derived from the other.
        print(info.name)
        print(info.rus_name)

        # `status` is an enum-like model; `.label` is its human-readable Russian text as
        # ranobelib.me shows it ("Завершён", "Онгоинг", ...).
        print(info.status.label)

        # Total chapter count as reported by the site itself, not computed by the SDK.
        print(info.chapter_count)

        # When the most recent chapter was published, as a timezone-aware (UTC) datetime —
        # the same value the catalog's sort="last_chapter_at" orders by. Only get_info()
        # fills this in: Catalog.list_titles() items leave it None, because the catalog
        # listing endpoint doesn't return it (see docs/api-notes.md, "Last chapter date").
        print(info.last_chapter_at)

        # `genres` is a list of Genre models; slicing keeps the printed output short.
        print([genre.name for genre in info.genres[:5]])

        # ranobelib.me appends a format marker to titles' names — "(Новелла)", "(Novel)",
        # "(LN)", ... `base_names` gives every name (rus_name, eng_name, name, other_names,
        # in that order) without it, deduplicated — e.g. to search another catalog (anime,
        # manga) by name, where the marker would only get in the way. The fields above stay
        # as the API sent them.
        print(info.base_names)


asyncio.run(main())

# Expected output (real run against the live site):
#
# Haisukuru Di Di (Novel)
# Старшая школа D×D (Новелла)
# Завершён
# 308
# 2026-07-09 13:29:40+00:00
# ['Боевик', 'Боевые искусства', 'Вампиры', 'Гарем', 'Драма']
# ['Старшая школа D×D', 'High School D×D', 'Haisukuru Di Di', 'Демоны старшей школы', 'ไฮสคูล D×D',
#  'ハイスクールD×D', '高校龙中龙 D×D', '하이스쿨 D×D']

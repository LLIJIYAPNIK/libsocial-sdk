"""List/search the ranobelib.me catalog with Catalog.list_titles() and its filter lookups.

Catalog is a separate entry point from RanobeLib: browsing/searching the whole site isn't
scoped to any one title, so it doesn't belong on the class that's built around a title's URL.
It reuses the same Title model as RanobeLib.get_info() for each list item, just with some
fields (genres, summary, chapter_count, ...) left at their defaults, since the catalog
listing endpoint doesn't send them.
"""

import asyncio

from ranobelib import Catalog


async def main() -> None:
    # Catalog is also an async context manager, same reasoning as RanobeLib: it owns an
    # httpx.AsyncClient and closes it on exit. No title URL is needed to construct it.
    async with Catalog() as catalog:
        # Free-text search matches against name/rus_name/eng_name. Results come back as a
        # CatalogPage: `.items` (list[Title]) plus `.has_next_page` to know whether to ask
        # for more without needing a separate "how many total results" call.
        page = await catalog.list_titles(query="dxd")
        print(f"page {page.page}, has_next_page={page.has_next_page}")
        for title in page.items[:5]:
            print(f"  {title.id}: {title.name} ({title.status.label})")

        # `list_genres()` is the id -> name lookup for the `genres` filter below: it fetches
        # every genre ranobelib.me actually uses (the underlying API endpoint covers the
        # whole lib.social network at once, tagged by site — Catalog filters that down to
        # ranobelib for you, see docs/api-notes.md), cached on disk like list_titles().
        genres = await catalog.list_genres()
        print(f"{len(genres)} genres available, e.g.: {[genre.name for genre in genres[:5]]}")
        action_genre = next(genre for genre in genres if genre.name == "Боевик")

        # `genres` filter narrows results; `genres` is a list of ids because a
        # title can be filtered by more than one at once (it must have *all* of them, not
        # just any one — see docs/api-notes.md). Ids come from list_genres() above, or from
        # the site's own filter UI.
        action_page = await catalog.list_titles(genres=[action_genre.id], per_page=10)
        print(f"\n5 '{action_genre.name}' titles:")
        for title in action_page.items[:5]:
            print(f"  {title.id}: {title.name}")

        # `list_statuses()` is the id -> label lookup for the `statuses` filter, same pattern
        # as `list_genres()` above. It returns the same `Label` model as `Title.status`, so
        # a title's status compares equal to the matching entry here.
        statuses = await catalog.list_statuses()
        print(f"\n{len(statuses)} statuses available: {[status.label for status in statuses]}")
        ongoing = next(status for status in statuses if status.label == "Онгоинг")
        completed = next(status for status in statuses if status.label == "Завершён")

        # `statuses` is a list too, but OR (not AND like `genres`): a title has exactly one
        # status, so "ongoing or completed" is the only reading that can match anything.
        status_page = await catalog.list_titles(
            statuses=[ongoing.id, completed.id], per_page=60, sort="name"
        )
        print(f"\n5 {ongoing.label} or {completed.label} titles (mixed):")
        mixed = [
            *[title for title in status_page.items if title.status == ongoing][:3],
            *[title for title in status_page.items if title.status == completed][:2],
        ]
        for title in mixed:
            print(f"  {title.id}: {title.name} ({title.status.label})")

        # `min_chapters`/`max_chapters` bound the chapter count, both inclusive (the same
        # number as Title.chapter_count) — e.g. a «от 1000 глав» filter is min_chapters=1000.
        # Catalog items themselves don't carry that count (only get_info() does), so the
        # result is sorted by it here to make the order meaningful: longest titles first.
        long_page = await catalog.list_titles(min_chapters=1000, sort="chap_count", per_page=10)
        print("\n5 titles with 1000+ chapters (most chapters first):")
        for title in long_page.items[:5]:
            print(f"  {title.id}: {title.name}")

        # `list_countries()` is the id -> name lookup for the `countries` filter below, same
        # pattern as `list_genres()` above (network-wide constants endpoint, filtered down to
        # ranobelib.me by Catalog). Despite the name, this covers more than literal countries
        # for ranobelib.me specifically — three real countries (Japan/Korea/China) plus three
        # non-national origin categories the site classifies the same way (original English,
        # original/non-translated, fanfiction) — see docs/api-notes.md.
        countries = await catalog.list_countries()
        print(f"\n{len(countries)} countries available: {[country.name for country in countries]}")
        korea = next(country for country in countries if country.name == "Корея")
        japan = next(country for country in countries if country.name == "Япония")

        # `countries` takes a list of ids, same shape as `genres`/`tags`, but with OR (not
        # AND) semantics — a title only ever has one country of origin, so it matches if that
        # country is *any* of the given ids, not all of them (requiring all would never match
        # past the first id). Every returned Title's `.country` reflects it (also populated on
        # RanobeLib.get_info() results, since it's the same model field). A single id still
        # works as a one-element list, e.g. `countries=[korea.id]`.
        korean_page = await catalog.list_titles(countries=[korea.id], per_page=10)
        print(f"\n5 titles from {korea.name}:")
        for title in korean_page.items[:5]:
            print(f"  {title.id}: {title.name}")

        jp_or_kr_page = await catalog.list_titles(
            countries=[japan.id, korea.id], per_page=10, sort="name"
        )
        print(f"\n5 titles from {japan.name} or {korea.name} (mixed):")
        for title in jp_or_kr_page.items[:5]:
            origin = title.country.name if title.country else "?"
            print(f"  {title.id}: {title.name} ({origin})")

        # `tags` filters the same way `genres` does (AND semantics — a title must have
        # *all* given tag ids, confirmed against the live API even though tags are more
        # numerous/specific than genres, see docs/api-notes.md), but there's no
        # `list_countries()`/`list_genres()`-style `list_tags()` lookup: unlike genres/
        # countries, this SDK's own tag ids/names only ever come from a Title already
        # fetched elsewhere (e.g. `title.tags` from `RanobeLib.get_info()`, or from a
        # previous catalog result's `.tags` — though catalog listing items don't send
        # `tags`, same as `genres`). 218 = "Боги" (Gods), found that way in a real title.
        tag_page = await catalog.list_titles(tags=[218], per_page=10)
        print(f"\n{len(tag_page.items)} 'Боги' titles on page 1:")
        for title in tag_page.items[:5]:
            print(f"  {title.id}: {title.name}")

        # `sort` picks the ordering — despite the keyword name, this is sent to the API as
        # `sort_by`; a real `sort` parameter exists on the wire but the API silently ignores
        # it (see docs/api-notes.md). Default is "last_chapter_at" (most recently updated).
        newest_page = await catalog.list_titles(sort="created_at", per_page=10)
        print(f"\n5 newest titles: {[title.name for title in newest_page.items[:5]]}")


asyncio.run(main())

# Expected output (real run against the live site; new titles are added constantly and the
# genre list can change too, so the exact ids/names here will drift over time — that's the
# site changing, not a bug):
#
#
#
# page 1, has_next_page=True
#   261856: DxD : A Nameless Star (Онгоинг)
#   272504: DxD: Хранитель великой оружейной (Онгоинг)
#   65799: DXD: Isekai Driver's Multiverse Retirement (Novel) (Завершён)
#   256087: DxD: Gambling With Fate (Онгоинг)
#   257880: DXD : Draconic Rebellion (Онгоинг)
# 54 genres available, e.g.: ['Арт', 'Безумие', 'Боевик', 'Боевые искусства', 'Вампиры']
#
# 5 'Боевик' titles:
#   206818: oneulman saneun gisa
#   97937: Wǒ néng fùzhì tiānfù
#   184704: My Longevity Simulation (Novel)
#   273576: Zhe Ge Sha Shou Shi Zhui Xu
#   132390: I will Heal you with the Academy Convenience Store (Novel)
#
# 5 statuses available: ['Онгоинг', 'Завершён', 'Анонс', 'Приостановлен', 'Выпуск
# прекращён']
#
# 5 Онгоинг or Завершён titles (mixed):
#   16498: 잔여 포인트 999999999999P (Novel) (Онгоинг)
#   84055: 생존의 기회 (Novel) (Онгоинг)
#   33503: 死于伟贤 (Novel) (Онгоинг)
#   45925: 人類或不朽的龍皇 (Novel) (Завершён)
#   227524: √4: Uchi no Juunin wa Minna Ijou desu (Завершён)
#
# 5 titles with 1000+ chapters (most chapters first):
#   206937: Dūshì jípǐn yī shén
#   16784: Di Ba
#   7058: Xiu Luo Wu Shen
#   38871: Qiángdà de xiǎoshān nóng (Novel)
#   18612: Àoshì dān shén
#
# 6 countries available: ['Япония', 'Корея', 'Китай', 'Английский', 'Авторский', 'Фанфик']
#
# 5 titles from Корея:
#   187014: apokallibseu syelteo gwanlija (Novel)
#   206818: oneulman saneun gisa
#   271255: Seongnyeoege jibchagbadneun dolpal-i singwan-i doeeossda
#   273571: muhyeob geim-e chiteumodeuleul jeog-yonghaessda
#   263880: I Became Daddy Long Legs in a Romance Fantasy
#
# 5 titles from Япония or Корея (mixed):
#   16498: 잔여 포인트 999999999999P (Novel) (Корея)
#   214726: ■■ eul wihan segyeneun eobsda (Корея)
#   227524: √4: Uchi no Juunin wa Minna Ijou desu (Япония)
#   55978: Я получил читерные способности в другом мире и стал экстраординарным в реальном~
#   повышение уровня изменило мою жизнь~ (Novel) (Япония)
#   231169: Я не ищу связей на одну ночь (Новелла) (Корея)
#
# 10 'Боги' titles on page 1:
#   55754: Embers Ad Infinitum (Novel)
#   262215: The Years of Apocalypse - A Time Loop Progression Fantasy
#   275322: Quán Zhí Jiàn Xiū
#   272014: Исчисление судеб
#   203235: Counterattack System appeared when I'm already At The Mahayana Realm
#
# 5 newest titles: ['chin-aehaneun naui eonniege', 'cheonjaelanyo, jadongsanyang-indeyo',
# 'gom inhyeong-i bulmyeonjeung agdang-eul kkumnalalo bonaem', 'Игры мафиози',
# 'Imsinsikyeotdeoni Hwangnyeoyeotda']

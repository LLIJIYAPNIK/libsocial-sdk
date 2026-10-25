"""The raw API client: libsocial.ApiClient, JSON in and out, no models, no cache.

RanobeLib, MangaLib and Catalog all go through ApiClient. Use it directly when you need
something the models don't carry (a field nobody modeled yet, the whole response as-is) or
want to see what the API really answers. It already does the request plumbing: Site-Id and
browser-like headers, at most 5 requests in flight, a 0.2 s gap between request starts
(shared with every other client in the process, see 05_pacing_and_console.py), retries of
429/5xx with backoff, and the SDK's exceptions for 404/403/429.

- `get_title(slug_url, fields=[...])`: the title; `fields` asks for extras on top of the
  default response.
- `get_chapters(slug_url)`: the whole chapter list, one request.
- `get_chapter(slug_url, number=..., volume=..., branch_id=...)`: one chapter with content.
- `list_titles(...)`: one catalog page. Every filter is a required keyword here (None for
  "no filter"); Catalog adds the defaults, validation and caching.
- `list_genres()` / `list_countries()` / `list_statuses()`: the network-wide lookups, each
  entry tagged with the `site_ids` it belongs to. Catalog filters them to its site.
"""

import asyncio

from libsocial import ApiClient, Site, TitleNotFoundError
from libsocial.models import Title

RANOBELIB = Site(id=3, origin="https://ranobelib.me")
MANGALIB = Site(id=1, origin="https://mangalib.me")
DXD = "6712--high-school-dxd-novel"


async def main() -> None:
    # Keyword settings that RanobeLib/MangaLib don't expose; the defaults are shown.
    async with ApiClient(RANOBELIB, timeout=15.0, max_concurrency=5, max_retries=3) as client:
        # rating and views aren't on the Title model: the raw response has them.
        raw = await client.get_title(DXD, fields=["rate_avg", "views"])
        print(raw["name"], "| rating", raw["rating"]["average"], "| views", raw["views"]["total"])
        # Anything raw can still become a model: Title ignores what it doesn't know.
        title = Title.model_validate(raw)
        print(
            type(title).__name__, title.status.label, title.country.name if title.country else None
        )

        chapters = await client.get_chapters(DXD)
        first = chapters[0]
        print(f"{len(chapters)} chapters; first: volume {first['volume']} number {first['number']}")
        print(
            "its branches:",
            [(b["branch_id"], [t["name"] for t in b["teams"]]) for b in first["branches"]],
        )

        chapter = await client.get_chapter(
            DXD,
            number=first["number"],
            volume=first["volume"],
            branch_id=first["branches"][0]["branch_id"],
        )
        # A novel chapter's content is HTML or a ProseMirror document, as the site stored it.
        content = chapter["content"]
        kind = "ProseMirror" if isinstance(content, dict) else "HTML"
        print("chapter keys:", sorted(chapter)[:8], "...; content:", kind)

        page = await client.list_titles(
            page=1,
            per_page=10,
            query="dxd",
            genres=None,
            tags=None,
            statuses=None,
            countries=None,
            min_chapters=None,
            max_chapters=None,
            sort="views",
        )
        print("listing:", sorted(page), "has_next_page", page["meta"]["has_next_page"])
        print("  ", [item["slug_url"] for item in page["data"][:3]])

        # The lookups cover every site; each entry says which ones it's for.
        genres = await client.list_genres()
        here = [genre for genre in genres if RANOBELIB.id in genre["site_ids"]]
        print(f"genres: {len(genres)} in the network, {len(here)} for site {RANOBELIB.id}")
        types = await client.list_countries()
        print("types for site 3:", [t["label"] for t in types if RANOBELIB.id in t["site_ids"]])
        statuses = await client.list_statuses()
        print("statuses:", [(s["label"], s["site_ids"]) for s in statuses[:2]], "...")

    # The site id scopes title lookups: a ranobelib.me title asked for as mangalib.me is a
    # 404, indistinguishable from a title that doesn't exist.
    async with ApiClient(MANGALIB) as client:
        try:
            await client.get_title(DXD)
        except TitleNotFoundError as exc:
            print(f"as site {MANGALIB.id}: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    asyncio.run(main())

# Expected output (real run against the live API on 2026-10-25; the rating, views and listing
# change over time):
#
# Haisukuru Di Di (Novel) | rating 9.2 | views 260345
# Title Завершён Япония
# 308 chapters; first: volume 1 number 0
# its branches: [(None, ['Неизвестный'])]
# chapter keys: ['attachments', 'branch_id', 'bundle', 'bundle_id', 'content', 'created_at',
#   'expired_at', 'expired_type'] ...; content: HTML
# listing: ['data', 'links', 'meta'] has_next_page True
#    ['91443--new-hero-in-dxd', '42088--reborn-in-dxd-world-with-a-fate-system',
#   '107777--godly-crafter-in-dxd']
# genres: 58 in the network, 54 for site 3
# types for site 3: ['Япония', 'Корея', 'Китай', 'Английский', 'Авторский', 'Фанфик']
# statuses: [('Онгоинг', [0, 1, 2, 3, 4, 5]), ('Завершён', [0, 1, 2, 3, 4, 5])] ...
# as site 1: TitleNotFoundError: Title not found: '6712--high-school-dxd-novel'

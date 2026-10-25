# ranobelib

`ranobelib-python-sdk` (`import ranobelib`).


Async Python SDK for [ranobelib.me](https://ranobelib.me): fetch title metadata, download
chapters and volumes, and export to epub, fb2, txt, or pdf.

The SDK talks to the undocumented but open JSON API behind the site (`api.cdnlibs.org`,
part of the lib.social network) instead of scraping HTML — see [API notes](api-notes.md)
for what's been learned about it along the way. The part shared by every lib.social site
(API client, request pacing, cache, titles, chapters, catalog) comes from `libsocial-core`,
installed with it.

## Installation

```bash
uv add ranobelib-python-sdk
```

or

```bash
pip install ranobelib-python-sdk
```

Requires Python 3.11+. `fmt="pdf"` on [`RanobeLib.export()`][ranobelib.RanobeLib.export]
additionally needs [WeasyPrint's native dependencies](https://doc.courtbouillon.org/weasyprint/stable/first_steps.html#installation)
(Pango/cairo, via a GTK3 runtime) installed on the system — `pip install`/`uv add` alone
doesn't guarantee that on every platform. Without them, `export(fmt="pdf")` raises the same
"unknown format" error the other three formats don't.

## Quickstart

```python
from ranobelib import RanobeLib

async with RanobeLib("https://ranobelib.me/ru/book/6712--high-school-dxd-novel") as lib:
    info = await lib.get_info()
    toc = await lib.get_table_of_contents()

    chapter = await lib.get_chapter(volume=6, number="51.6")
    volume = await lib.get_volume(volume=6)

    chapters = await lib.get_chapters([(6, "51.6"), (6, "52")])
    volumes = await lib.get_volumes([1, 2, 3])

    translations = await lib.get_translations(volume=6, number="51.6")
    chapter = await lib.get_chapter(volume=6, number="51.6", branch_id=...)

    await lib.export(chapters, fmt="epub", path="output.epub")
```

`number` is a string exactly as the API returns it, and may contain a decimal for
sub-chapters (`"51.6"`) — there's no separate parameter for the fractional part.

### Selecting a translation

When a chapter has more than one team's translation, `get_chapter()` (and anything built on
it — `get_chapters()`, `get_volume()`, `get_volumes()`) raises
[`MultipleTranslationsError`][ranobelib.MultipleTranslationsError] instead of guessing which
one you want:

```python
from ranobelib import MultipleTranslationsError

try:
    chapter = await lib.get_chapter(volume=6, number="51.6")
except MultipleTranslationsError as exc:
    for branch in exc.branches:
        print(branch.branch_id, [team.name for team in branch.teams])
    chapter = await lib.get_chapter(volume=6, number="51.6", branch_id=exc.branches[0].branch_id)
```

### Caching

Raw API responses (title metadata, chapter list, chapter content) are cached to disk by
default, so re-exporting to a different format or downloading newly added chapters doesn't
re-fetch data already on hand:

```python
async with RanobeLib(url, cache_dir=".cache", cache_ttl=3600) as lib:
    toc = await lib.get_table_of_contents()  # First call: hits the API.
    toc = await lib.get_table_of_contents()  # Second call: served from disk.
    toc = await lib.get_table_of_contents(refresh=True)  # Bypasses the cache.
```

To see how much space the cache takes, or to empty it (all of it, or only entries older
than a given age), use `cache_stats()` / `clear_cache()` rather than deleting its files
yourself — the on-disk layout is an SDK internal:

```python
from ranobelib import cache_stats, clear_cache

print(cache_stats(".cache"))  # CacheStats(entries=..., bytes=...)
clear_cache(".cache", older_than=86400)  # Drop entries older than a day.
```

## Examples

[`examples/ranobelib/`](https://github.com/LLIJIYAPNIK/libsocial-sdk/tree/main/examples/ranobelib)
has a complete, commented script for every feature: metadata, chapters and volumes,
translations, whole-title download, caching, export to all four formats and to your own,
sizes, console output, the catalog, footnotes, images, paragraphs and error handling.

## Documentation

- [API reference](ranobelib-reference.md) — generated from the source's own docstrings.
- [API notes](api-notes.md) — a running log of what's been learned about ranobelib's
  undocumented API and the design decisions that followed from it (translation selection,
  rate limiting, why each exporter is built the way it is, and more).
- The project's [CLAUDE.md](https://github.com/LLIJIYAPNIK/libsocial-sdk/blob/main/CLAUDE.md)
  documents the full architecture, public API contract, and roadmap.

## License

MIT — see [LICENSE](https://github.com/LLIJIYAPNIK/libsocial-sdk/blob/main/LICENSE).

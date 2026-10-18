# mangalib-python-sdk

[![PyPI](https://img.shields.io/pypi/v/mangalib-python-sdk)](https://pypi.org/project/mangalib-python-sdk/)
[![License: MIT](https://img.shields.io/github/license/LLIJIYAPNIK/libsocial-sdk)](../../LICENSE)
[![Python versions](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-blue)](pyproject.toml)
[![CI](https://github.com/LLIJIYAPNIK/libsocial-sdk/actions/workflows/ci.yml/badge.svg)](https://github.com/LLIJIYAPNIK/libsocial-sdk/actions/workflows/ci.yml)

Async Python SDK for [mangalib.me](https://mangalib.me): title metadata, table of contents,
translations, catalog search, chapter pages as images, and export to CBZ or PDF.

Like [`ranobelib-python-sdk`](https://pypi.org/project/ranobelib-python-sdk/), it talks to
the undocumented but open JSON API behind the site (`api.cdnlibs.org`, shared by the whole
lib.social network) instead of scraping HTML. The shared part (API client, request pacing,
cache, titles, chapters, catalog) comes from `libsocial-core`, installed with it, so a
process using both SDKs paces its requests to the API together.

> **Status:** early. There is no login, so paid and early-access chapters can't be read:
> fetching one raises `AuthRequiredError`, and a whole-title download leaves them out.

## Installation

```bash
uv add mangalib-python-sdk
```

or

```bash
pip install mangalib-python-sdk
```

PDF export needs the `pdf` extra (img2pdf): `uv add "mangalib-python-sdk[pdf]"` /
`pip install "mangalib-python-sdk[pdf]"`. Without it, `"pdf"` just isn't one of the export
formats. Requires Python 3.11+.

## Quickstart

```python
from mangalib import Catalog, MangaLib

async with MangaLib("https://mangalib.me/ru/manga/7965--chainsaw-man") as lib:
    info = await lib.get_info()
    toc = await lib.get_table_of_contents()

    # Chapter 1 has two translations: pick one (see get_translations()).
    translations = await lib.get_translations(volume=1, number="1")
    chapter = await lib.get_chapter(volume=1, number="1", branch_id=translations[0].branch_id)

    for page in chapter.pages:
        print(page.number, page.width, page.height)
    images = await lib.download_pages(chapter)  # list[bytes], in reading order

    # One chapter, several, a volume, or the whole title, into one file.
    await lib.export([chapter], fmt="cbz", path="chainsaw-man-1.cbz")
    volumes = await lib.download_title(translation_index=0, on_chapter=print)
    await lib.export(volumes, fmt="pdf", path="chainsaw-man.pdf", on_chapter=print)

    size = await lib.estimate_title_size()  # bytes of page images, from a sample

async with Catalog() as catalog:
    page = await catalog.list_titles(query="chainsaw")
```

- `get_chapter()` / `get_chapters()` / `get_volume()` / `get_volumes()` /
  `download_title()` return chapters with `pages` (`Page`: position, size, path on an image
  server).
- `ChapterBranch.is_open` (from `get_table_of_contents()` / `get_translations()`) says
  whether a translation can be read without an account.
- `download_page()` / `download_pages()` fall back from one image server to the next; see
  `list_image_servers()` and the API notes for why `compress` is tried first. Requests to
  an image host are paced across the process and retried on 429/5xx; `concurrency=` sets
  how many pages are fetched at once.
- `export()` writes `"cbz"` (pages in order + `ComicInfo.xml`) or `"pdf"` (a page per image,
  an outline entry per chapter); `mangalib.exporters.EXPORTERS` lists what's available.
- `chapter_size()` / `volume_size()` give the exact size of the page images, from `HEAD`
  requests; `estimate_title_size()` extrapolates from a sample of chapters.

## Documentation

Full API reference: **<https://LLIJIYAPNIK.github.io/libsocial-sdk/>**. What the API
returns for MangaLib, and what was checked: the "MangaLib" section of
[`docs/api-notes.md`](../../docs/api-notes.md). [`CHANGELOG.md`](CHANGELOG.md) lists what
changed in each release.

## License

MIT — see [LICENSE](../../LICENSE).

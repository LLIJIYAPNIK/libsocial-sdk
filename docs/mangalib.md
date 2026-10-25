# mangalib

`mangalib-python-sdk` (`import mangalib`): titles, chapters, translations, the catalog and
chapter pages of [mangalib.me](https://mangalib.me), with export to CBZ or PDF.

## Installation

```bash
uv add mangalib-python-sdk          # or: pip install mangalib-python-sdk
uv add "mangalib-python-sdk[pdf]"   # with PDF export (img2pdf)
```

Without the `pdf` extra, `"pdf"` just isn't one of the export formats
([`EXPORTERS`](mangalib-reference.md#exporters)).

## Quickstart

```python
from mangalib import Catalog, MangaLib

async with MangaLib("https://mangalib.me/ru/manga/7965--chainsaw-man") as lib:
    info = await lib.get_info()
    toc = await lib.get_table_of_contents()

    # Chapter 1 has two translations: pick one.
    translations = await lib.get_translations(volume=1, number="1")
    chapter = await lib.get_chapter(volume=1, number="1", branch_id=translations[0].branch_id)

    images = await lib.download_pages(chapter)  # list[bytes], in reading order
    await lib.export([chapter], fmt="cbz", path="chainsaw-man-1.cbz")

    size = await lib.estimate_title_size()  # bytes of page images, from a sample
    volumes = await lib.download_title(translation_index=0, on_chapter=print)
    await lib.export(volumes, fmt="pdf", path="chainsaw-man.pdf", on_chapter=print)

async with Catalog() as catalog:
    page = await catalog.list_titles(query="chainsaw")
```

## Chapters are pages

A fetched chapter has [`pages`][mangalib.Chapter] instead of text: each
[`Page`][mangalib.Page] is a position, a size and a path on an image server. The servers
come from [`list_image_servers()`][mangalib.MangaLib.list_image_servers], and not all of them
let a script in. [`download_page()`][mangalib.MangaLib.download_page] starts from
`compress` and falls back to the next one. It paces its requests per image host across the
process and retries a 429/5xx before moving on.

[`chapter_size()`][mangalib.MangaLib.chapter_size] and
[`volume_size()`][mangalib.MangaLib.volume_size] give the exact size of the images from
`HEAD` requests, without downloading them.
[`estimate_title_size()`][mangalib.MangaLib.estimate_title_size] extrapolates from a
sample of chapters.

## Paid and early-access chapters

There's no login. [`ChapterBranch.is_open`][mangalib.ChapterBranch.is_open] says whether a
translation can be read without an account. Fetching a closed chapter raises
[`AuthRequiredError`][mangalib.AuthRequiredError]. A whole-title download or estimate
leaves closed chapters out.

## More

- [Examples](https://github.com/LLIJIYAPNIK/libsocial-sdk/tree/main/examples/mangalib): a
  complete, commented script for every feature, from metadata to export, the catalog,
  caching and error handling.
- [API reference](mangalib-reference.md).
- [API notes](api-notes.md#mangalib-mangalib-python-sdk-issue-90-checked-2026-10-18): what
  the API returns for mangalib.me, and how it was checked.

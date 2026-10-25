# ranobelib-python-sdk

[![PyPI](https://img.shields.io/pypi/v/ranobelib-python-sdk)](https://pypi.org/project/ranobelib-python-sdk/)
[![License: MIT](https://img.shields.io/github/license/LLIJIYAPNIK/libsocial-sdk)](../../LICENSE)
[![Python versions](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-blue)](pyproject.toml)
[![CI](https://github.com/LLIJIYAPNIK/libsocial-sdk/actions/workflows/ci.yml/badge.svg)](https://github.com/LLIJIYAPNIK/libsocial-sdk/actions/workflows/ci.yml)
[![Coverage Status](https://coveralls.io/repos/github/LLIJIYAPNIK/ranobelib-python-sdk/badge.svg?branch=main)](https://coveralls.io/github/LLIJIYAPNIK/ranobelib-python-sdk?branch=main)
[![Docs](https://github.com/LLIJIYAPNIK/libsocial-sdk/actions/workflows/docs.yml/badge.svg)](https://github.com/LLIJIYAPNIK/libsocial-sdk/actions/workflows/docs.yml)

Async Python SDK for [ranobelib.me](https://ranobelib.me): fetch title metadata, download
chapters and volumes, and export to epub, fb2, txt, or pdf.

The SDK talks to the undocumented but open JSON API behind the site (`api.cdnlibs.org`,
part of the lib.social network) instead of scraping HTML. The part shared by every
lib.social site (API client, request pacing, cache, titles, chapters, catalog) comes from
`libsocial-core`, installed with it.

> **Status:** all the calls in the quickstart below are implemented — metadata, table of
> contents, single/bulk chapter and volume downloads, whole-title bulk download, translation
> selection, and export to
> `"txt"`, `"fb2"`, `"epub"`, or `"pdf"` (cover + in-chapter illustrations embedded in
> epub/pdf). Raw API responses are cached to disk, and the underlying client bounds
> concurrency, paces requests, and retries 429/5xx with backoff. `fmt="pdf"` needs
> WeasyPrint's native dependencies (Pango/cairo/GTK3) installed on the system — `pip
> install`/`uv add` alone doesn't guarantee that on every platform; without them,
> `export(fmt="pdf")` raises the same "unknown format" error the other three formats don't.
> Authorization (private/18+/paid content) is out of scope — see `CLAUDE.md` for the full
> architecture and design decisions behind all of this.

## Installation

```bash
uv add ranobelib-python-sdk
```

or

```bash
pip install ranobelib-python-sdk
```

Requires Python 3.11+.

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

    all_volumes = await lib.download_title(translation_index=0, chapter_delay=0.5)

    await lib.export(chapters, fmt="epub", path="output.epub")
```

This is the full current public API — everything above is implemented and works today.

## Examples

Complete, runnable scripts for every feature above — title metadata, table of contents,
single/bulk chapter and volume downloads, translation selection, whole-title bulk download,
disk caching, export to all four formats, and error handling — live in
**[`examples/ranobelib/`](../../examples/ranobelib/)**, one heavily commented file per feature. Start there for
copy-pasteable code.

## Documentation

Full API reference and guides: **<https://LLIJIYAPNIK.github.io/libsocial-sdk/>**
(built with `mkdocs-material` + `mkdocstrings`, deployed on push to `main`). `CLAUDE.md`
documents the full architecture, public API contract, and the reasoning behind the SDK's
design decisions. [`CHANGELOG.md`](CHANGELOG.md) lists what changed in each release.

## License

MIT — see [LICENSE](../../LICENSE).

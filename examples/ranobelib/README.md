# ranobelib examples

Examples for [`ranobelib-python-sdk`](../../packages/ranobelib/) (`import ranobelib`). For
mangalib.me see [`../mangalib/`](../mangalib/).

Every script in this directory is a complete, self-contained program — save/copy it as-is
and run `python examples/ranobelib/<file>.py`. Each one was actually executed against the live
ranobelib.me site to produce the "Expected output" comment at the bottom of the file; only
chapter HTML content is truncated (`[:200]`/`[:300]`) for readability, everything else is
the real output verbatim. Titles/URLs may change or get removed on the site over time, so an
old "Expected output" block can drift from what you see when you re-run a script — that's
the site changing, not a bug in the SDK.

Scripts are heavily commented on purpose: each one is meant to be read top to bottom as a
mini-tutorial for the feature it demonstrates, not just copy-pasted.

| File | Feature |
|---|---|
| [`01_title_metadata.py`](01_title_metadata.py) | `get_info()` — title metadata |
| [`02_table_of_contents.py`](02_table_of_contents.py) | `get_table_of_contents()` — volumes/chapters without content |
| [`03_single_chapter.py`](03_single_chapter.py) | `get_chapter()` — one chapter's content |
| [`04_multiple_chapters.py`](04_multiple_chapters.py) | `get_chapters()` — several chapters at once |
| [`05_single_volume.py`](05_single_volume.py) | `get_volume()` — a whole volume |
| [`06_multiple_volumes.py`](06_multiple_volumes.py) | `get_volumes()` — several volumes at once |
| [`07_translation_selection.py`](07_translation_selection.py) | `get_translations()` + `branch_id` — picking a translation |
| [`08_download_title.py`](08_download_title.py) | `download_title()` — whole-title bulk download |
| [`09_disk_caching.py`](09_disk_caching.py) | disk cache + `refresh=True`, `cache_stats()` / `clear_cache()` |
| [`10_export_formats.py`](10_export_formats.py) | `export()` to txt/fb2/epub/pdf |
| [`11_error_handling.py`](11_error_handling.py) | `TitleNotFoundError` / `ChapterNotFoundError` / `AccessBlockedError` |
| [`12_catalog_listing.py`](12_catalog_listing.py) | `Catalog.list_titles()` — browsing/searching the catalog |
| [`13_chapter_footnotes.py`](13_chapter_footnotes.py) | `Chapter.footnotes` — translator footnotes, separate from the text |
| [`14_chapter_images.py`](14_chapter_images.py) | `chapter_image_urls()` / `rewrite_image_urls()` — listing and rewriting a chapter's image URLs |
| [`15_chapter_paragraphs.py`](15_chapter_paragraphs.py) | `chapter_paragraphs()` — a chapter's top-level blocks as plain text, indexed like the DOM |
| [`16_sizing.py`](16_sizing.py) | `estimate_title_size()` before downloading, `chapter_size()` / `volume_size()` after |
| [`17_console_output.py`](17_console_output.py) | `verbosity` — progress bars and a cache/API log in the console |
| [`18_custom_exporter.py`](18_custom_exporter.py) | your own export format: `Exporter`, `register()`, `EXPORTERS` |
| [`19_bulk_errors.py`](19_bulk_errors.py) | `VolumeNotFoundError`, `MultipleTitleTranslationsError` / `AmbiguousChapter`, `except RanobeLibError` |

See the [full API reference](https://LLIJIYAPNIK.github.io/libsocial-sdk/ranobelib-reference/)
for every public class/method. Two exceptions aren't demonstrated, since a short script can't
reproduce them reliably: `AuthRequiredError` (needs a paid or early-access chapter) and
`RateLimitError` (needs sustained rate limiting). Their attributes are in the reference; 11_error_handling.py explains how
`AuthRequiredError` differs from `AccessBlockedError`.

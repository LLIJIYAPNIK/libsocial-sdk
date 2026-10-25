# mangalib examples

Examples for [`mangalib-python-sdk`](../../packages/mangalib/) (`import mangalib`). For
ranobelib.me see [`../ranobelib/`](../ranobelib/).

Every script in this directory is a complete, self-contained program — save/copy it as-is
and run `python examples/mangalib/<file>.py`. Each one was actually executed against the
live mangalib.me site to produce the "Expected output" comment at the bottom of the file.
Titles/chapters may change or get removed on the site over time, so an old "Expected output"
block can drift from what you see when you re-run a script — that's the site changing, not a
bug in the SDK.

`MangaLib` has the same title/chapter/translation methods as `RanobeLib`; what differs is the
chapter itself (a list of page images instead of text), closed chapters, and the export
formats. The scripts below show the mangalib side of each feature, so they don't assume
you've read the ranobelib ones.

| File | Feature |
|---|---|
| `01_title_metadata.py` | `get_info()` — title metadata, `Title.base_names` *(planned)* |
| `02_table_of_contents.py` | `get_table_of_contents()` — volumes/chapters without pages *(planned)* |
| `03_single_chapter.py` | `get_chapter()` — one chapter's pages *(planned)* |
| `04_multiple_chapters.py` | `get_chapters()` — several chapters at once *(planned)* |
| `05_volumes.py` | `get_volume()` / `get_volumes()` *(planned)* |
| `06_translations.py` | `get_translations()`, `branch_id`, closed chapters *(planned)* |
| `07_download_title.py` | `download_title()` — whole-title bulk download *(planned)* |
| [`08_page_images.py`](08_page_images.py) | a chapter's pages, image servers, closed chapters |
| [`09_export_formats.py`](09_export_formats.py) | `export()` to CBZ/PDF, `chapter_size()` / `estimate_title_size()` |
| `10_sizing.py` | `chapter_size()` / `volume_size()` / `estimate_title_size()` *(planned)* |
| `11_custom_exporter.py` | your own export format via `mangalib.exporters.register()` *(planned)* |
| `12_catalog_listing.py` | `Catalog.list_titles()` — browsing/searching the catalog *(planned)* |
| `13_disk_caching.py` | disk cache + `refresh=True`, `cache_stats()` / `clear_cache()` *(planned)* |
| `14_error_handling.py` | `MangaLibError` and its subclasses *(planned)* |

See the [full API reference](https://LLIJIYAPNIK.github.io/libsocial-sdk/mangalib-reference/)
for every public class/method.

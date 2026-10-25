# Examples

Runnable, heavily commented scripts for each package in this repository, one directory per
package:

| Directory | Package | Import | Scripts |
|---|---|---|---|
| [`ranobelib/`](ranobelib/) | [`ranobelib-python-sdk`](../packages/ranobelib/) — ranobelib.me, text novels | `import ranobelib` | 19 |
| [`mangalib/`](mangalib/) | [`mangalib-python-sdk`](../packages/mangalib/) — mangalib.me, manga page images | `import mangalib` | 14 |
| [`core/`](core/) | [`libsocial-core`](../packages/core/) — the shared core both are built on | `import libsocial` | 6 |

Every script is a complete, self-contained program: run it as-is with
`python examples/<package>/<file>.py`. Each one was actually executed against the live site
to produce the "Expected output" comment at the bottom of the file; the sites' data changes,
so an old "Expected output" can drift from what you see. Scripts are meant to be read top to
bottom as a mini-tutorial for one feature, not just copy-pasted. Each directory's README
lists its scripts.

## Where to start

- **Novels from ranobelib.me:** [`ranobelib/01_title_metadata.py`](ranobelib/01_title_metadata.py),
  then the chapter and volume scripts (03–08) and [`ranobelib/10_export_formats.py`](ranobelib/10_export_formats.py).
- **Manga from mangalib.me:** [`mangalib/01_title_metadata.py`](mangalib/01_title_metadata.py),
  then chapters and volumes (03–05), [`mangalib/08_page_images.py`](mangalib/08_page_images.py)
  and [`mangalib/09_export_formats.py`](mangalib/09_export_formats.py).
- **Browsing a site's catalog:** `12_catalog_listing.py` in either directory.
- **Another lib.social site, or the raw API:** [`core/`](core/), starting from
  [`core/02_raw_api_client.py`](core/02_raw_api_client.py) and
  [`core/03_custom_site_client.py`](core/03_custom_site_client.py).
- **Both site packages in one program:** [`core/06_both_sites.py`](core/06_both_sites.py).

## Kept in step with the API

CI doesn't run the scripts (they need the live sites), but checks on every pull request that
each one type-checks with `mypy --strict`, imports without running (`main()` is behind
`if __name__ == "__main__":`), and that every name in the packages' `__all__` (and their
`exporters`) appears in its package's examples — see `.github/scripts/test_examples.py`.

# libsocial-core examples

Examples for [`libsocial-core`](../../packages/core/) (`import libsocial`), the shared core
that [`ranobelib`](../ranobelib/) and [`mangalib`](../mangalib/) are built on. You need it
directly only to build a package for another lib.social site or to work with the raw API;
for ranobelib.me and mangalib.me use their own packages.

Every script in this directory is a complete, self-contained program: run it as-is with
`python examples/core/<file>.py`. Each one was actually executed against the live API to
produce the "Expected output" comment at the bottom of the file; the sites' data changes over
time, so an old "Expected output" can drift from what you see.

The site without a package of its own used in 03 and 04 is slashlib.me (site id 2). 06 needs
both `ranobelib-python-sdk` and `mangalib-python-sdk` installed.

| File | Feature |
|---|---|
| [`01_urls_and_sites.py`](01_urls_and_sites.py) | `parse_slug_url()`, `Site`, `browser_headers_for()` / `browser_headers()` — no requests |
| [`02_raw_api_client.py`](02_raw_api_client.py) | `ApiClient` directly: raw JSON for a title, chapters, a chapter, a listing, the network-wide lookups; fields the models don't have; `TitleNotFoundError` on the wrong site id |
| [`03_custom_site_client.py`](03_custom_site_client.py) | a client for slashlib.me on `TitleClient`: its own `Chapter` / `Volume[...]` models, `info_fields`, `default_cache_dir`, `_create_client()`, a `_plan_chapters()` that prefers a team; `PlannedChapter`, `ChapterBranch`, `MultipleTranslationsError`, `MultipleTitleTranslationsError` / `AmbiguousChapter` |
| [`04_custom_catalog.py`](04_custom_catalog.py) | a `Catalog` for slashlib.me: `CatalogPage`, lookups (`Genre`, `Country`, `Label`) filtered by site versus the whole network; `cache_stats()` / `CacheStats` / `clear_cache()` |
| [`05_pacing_and_console.py`](05_pacing_and_console.py) | `shared_pacer()` and `Pacer`: two clients for two sites sharing one request rate, measured; `Reporter` and `Verbosity` for progress and logs in the SDK's style |
| [`06_both_sites.py`](06_both_sites.py) | ranobelib and mangalib together: one franchise in both catalogs, the shared models (`Title`, `Person`, `Cover`, `Tag`, `Team`, `ChapterUser`), one exception hierarchy under `LibSocialError` |

Every name in `libsocial.__all__` appears in at least one of these scripts. `RateLimitError`,
`AccessBlockedError`, `AuthRequiredError` and `DownloadTitleInterruptedError` appear in 06
only as part of the shared hierarchy; they're raised and handled in the site packages'
examples ([`mangalib/14_error_handling.py`](../mangalib/14_error_handling.py),
[`mangalib/07_download_title.py`](../mangalib/07_download_title.py),
[`ranobelib/11_error_handling.py`](../ranobelib/11_error_handling.py)).

See the [full API reference](https://LLIJIYAPNIK.github.io/libsocial-sdk/core-reference/)
for every public class/method.

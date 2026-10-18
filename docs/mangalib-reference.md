# mangalib API reference

`mangalib-python-sdk` (`import mangalib`): the SDK for [mangalib.me](https://mangalib.me), on
the same `libsocial-core` as `ranobelib`. Chapters are page images rather than text. What
the API returns for MangaLib is in [API notes](api-notes.md#mangalib-mangalib-python-sdk-issue-90-checked-2026-10-18).

## Entry point

::: mangalib.MangaLib

::: mangalib.Catalog

## Models

::: mangalib.CatalogPage

::: mangalib.Title

::: mangalib.Chapter

::: mangalib.Page

::: mangalib.ChapterBranch
    options:
      # Its base, libsocial.ChapterBranch, is documented on two pages (the core's and, as a
      # re-export, ranobelib's), which leaves the link to it ambiguous. It extends that model
      # with restricted_view/is_open.
      show_bases: false

::: mangalib.RestrictedView

::: mangalib.ImageServer

::: mangalib.Volume

## Page images

::: mangalib.page_url

::: mangalib.images.DEFAULT_SERVER_ORDER

::: mangalib.images.DEFAULT_IMAGE_CONCURRENCY

::: mangalib.images.DEFAULT_IMAGE_REQUEST_DELAY

## Exporters

Not re-exported from the top-level `mangalib` package — import from `mangalib.exporters`.
A new format is a new module in `mangalib/exporters/` implementing `Exporter`, decorated
with `@register`. `"pdf"` is registered only when the `pdf` extra (img2pdf) is installed.

::: mangalib.exporters.Exporter

::: mangalib.exporters.register

::: mangalib.exporters.EXPORTERS
    options:
      show_root_heading: false
      show_root_toc_entry: false

::: mangalib.exporters.cbz.CbzExporter

::: mangalib.exporters.pdf.PdfExporter

## Exceptions

`MangaLibError` is the base class of every error the SDK raises, the same class as
`ranobelib.RanobeLibError`; the others are shared with `ranobelib` too, except
`PageDownloadError`.

::: mangalib.PageDownloadError

::: mangalib.AuthRequiredError

::: mangalib.ChapterNotFoundError

::: mangalib.VolumeNotFoundError

::: mangalib.MultipleTranslationsError

::: mangalib.MultipleTitleTranslationsError

::: mangalib.DownloadTitleInterruptedError

## Cache maintenance

::: mangalib.cache_stats

::: mangalib.clear_cache

::: mangalib.CacheStats

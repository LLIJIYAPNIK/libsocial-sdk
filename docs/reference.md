# API reference

## Entry point

::: ranobelib.RanobeLib

::: ranobelib.Catalog

## Models

::: ranobelib.CatalogPage

::: ranobelib.Title

::: ranobelib.Chapter

::: ranobelib.Footnote

::: ranobelib.Volume

::: ranobelib.ChapterBranch

::: ranobelib.Genre

::: ranobelib.Country

::: ranobelib.Label

## Exceptions

::: ranobelib.RanobeLibError

::: ranobelib.TitleNotFoundError

::: ranobelib.ChapterNotFoundError

::: ranobelib.VolumeNotFoundError

::: ranobelib.MultipleTranslationsError

::: ranobelib.AuthRequiredError

::: ranobelib.AccessBlockedError

::: ranobelib.RateLimitError

::: ranobelib.DownloadTitleInterruptedError

## Sizing

::: ranobelib.chapter_size

::: ranobelib.volume_size

## Chapter content

::: ranobelib.chapter_image_urls

::: ranobelib.rewrite_image_urls

::: ranobelib.chapter_paragraphs

## Exporters

Not re-exported from the top-level `ranobelib` package — import from `ranobelib.exporters`.
Adding a new export format is a new module in `ranobelib/exporters/` implementing
`Exporter` and decorated with `@register`; no changes needed elsewhere.

::: ranobelib.exporters.Exporter

::: ranobelib.exporters.register

::: ranobelib.exporters.EXPORTERS
    options:
      show_root_heading: false
      show_root_toc_entry: false

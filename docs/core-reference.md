# libsocial-core API reference

`import libsocial`. Most users get these through `ranobelib` or `mangalib`, which re-export
the models and exceptions — see [libsocial-core](core.md).

## Building blocks

::: libsocial.Site

::: libsocial.TitleClient

::: libsocial.Catalog

::: libsocial.ApiClient

::: libsocial.Pacer

::: libsocial.shared_pacer

::: libsocial.PlannedChapter

## Models

::: libsocial.Title

::: libsocial.Chapter

::: libsocial.ChapterBranch

::: libsocial.Volume

::: libsocial.CatalogPage

## Exceptions

::: libsocial.LibSocialError

::: libsocial.TitleNotFoundError

::: libsocial.ChapterNotFoundError

::: libsocial.VolumeNotFoundError

::: libsocial.MultipleTranslationsError

::: libsocial.MultipleTitleTranslationsError

::: libsocial.AuthRequiredError

::: libsocial.AccessBlockedError

::: libsocial.RateLimitError

::: libsocial.DownloadTitleInterruptedError

## Cache maintenance

::: libsocial.cache_stats

::: libsocial.clear_cache

::: libsocial.CacheStats

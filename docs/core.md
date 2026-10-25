# libsocial-core

`libsocial-core` (`import libsocial`): the part of the SDKs every lib.social site shares.
It's installed with `ranobelib-python-sdk` and `mangalib-python-sdk`, and is meant to be used
through them. You need it directly only to build a package for another site.

What it has:

- [`ApiClient`][libsocial.ApiClient]: the `api.cdnlibs.org` client, scoped to a site by a
  [`Site`][libsocial.Site] (id and origin). It bounds concurrency, retries 429/5xx with
  backoff, and paces requests through a [`Pacer`][libsocial.Pacer] shared by every client
  in the process that talks to the same host ([`shared_pacer()`][libsocial.shared_pacer]).
- [`TitleClient`][libsocial.TitleClient]: one title's metadata, table of contents,
  translations, chapter fetching and whole-title download, with a disk cache. A site package
  subclasses it, setting the site and its own models as class attributes.
- [`Catalog`][libsocial.Catalog]: catalog listing and search, and the genre, type and
  status lists, filtered to the site.
- The shared models (`Title`, `Chapter`, `ChapterBranch`, `Volume`, ...) and exceptions,
  all derived from [`LibSocialError`][libsocial.LibSocialError].

```python
from libsocial import Site, TitleClient
from libsocial.models import Chapter, Title, Volume


class MyChapter(Chapter):
    content: str | None = None


class MyVolume(Volume[MyChapter]):
    pass


class MySite(TitleClient[Title, MyChapter, MyVolume]):
    site = Site(id=3, origin="https://ranobelib.me")
    title_model = Title
    chapter_model = MyChapter
    volume_model = MyVolume


async with MySite("https://ranobelib.me/ru/book/6712--high-school-dxd-novel") as client:
    info = await client.get_info()
```

A site package adds what depends on its chapters: text and export for ranobelib, page images
and export for mangalib. It can override `_create_client()` (its own `ApiClient` subclass)
and `_plan_chapters()` (which chapters a whole-title operation takes, as mangalib does to
leave out closed ones).

[`examples/core/`](https://github.com/LLIJIYAPNIK/libsocial-sdk/tree/main/examples/core) has
the snippet above grown into a working client for slashlib.me (a site with no package of its
own) with both overrides, plus scripts for the raw `ApiClient`, a site's `Catalog`, shared
pacing and console output, and ranobelib and mangalib used together.

See the [API reference](core-reference.md).

# libsocial-core

The site-independent core shared by the async Python SDKs for the lib.social sites
(ranobelib.me, mangalib.me, ...). They all sit on one backend, `api.cdnlibs.org`, and differ
mainly in the `Site-Id` they send and in what a chapter contains.

This package is the shared part:

- `ApiClient`: the `api.cdnlibs.org` client, scoped to a site by a `Site` (id + origin).
  Bounded concurrency, retries with backoff on 429/5xx, and request pacing shared by every
  client in the process that talks to the same host.
- `TitleClient`: one title's metadata, table of contents, translations (branches), chapter
  fetching and whole-title download, with a disk cache.
- `Catalog`: catalog listing/search and the genre/country/status lists, filtered to the site.
- Models (`Title`, `Chapter`, `ChapterBranch`, `Volume`, ...) and exceptions.

It's meant to be used through a site package, which sets the site and its chapter model —
most likely [`ranobelib-python-sdk`](https://pypi.org/project/ranobelib-python-sdk/), not
directly.

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

Working, commented scripts — the raw API client, a client and a catalog for a site without a
package of its own, shared pacing, both site packages together — are in
[`examples/core/`](https://github.com/LLIJIYAPNIK/libsocial-sdk/tree/main/examples/core).

Repository, documentation and the site packages:
<https://github.com/LLIJIYAPNIK/libsocial-sdk>.

MIT licensed.

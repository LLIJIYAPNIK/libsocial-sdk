# libsocial-sdk

Async Python SDKs for the lib.social sites. ranobelib.me and mangalib.me run on one
backend, the undocumented but open JSON API at `api.cdnlibs.org`, and these packages talk to
it instead of scraping HTML. What's been learned about that API along the way is in the
[API notes](api-notes.md).

| Package | Install | For |
|---|---|---|
| [ranobelib](ranobelib.md) | `pip install ranobelib-python-sdk` | [ranobelib.me](https://ranobelib.me): novels — chapter text, footnotes, illustrations, export to epub/fb2/txt/pdf |
| [mangalib](mangalib.md) | `pip install mangalib-python-sdk` | [mangalib.me](https://mangalib.me): manga — chapter pages as images, export to CBZ/PDF |
| [libsocial-core](core.md) | installed with either | The shared part: API client, request pacing, disk cache, titles, chapters, translations, catalog |

The two site packages have the same shape: a title client (`RanobeLib` / `MangaLib`) built
from a title's URL, and a `Catalog` for listing and searching the site. Both are async-only
(`httpx`) and need Python 3.11+.

```python
from mangalib import MangaLib
from ranobelib import RanobeLib

async with RanobeLib("https://ranobelib.me/ru/book/6712--high-school-dxd-novel") as novel:
    info = await novel.get_info()

async with MangaLib("https://mangalib.me/ru/manga/7965--chainsaw-man") as manga:
    chapter = await manga.get_chapter(volume=1, number="1", branch_id=4667)
```

Used together in one process, they pace their requests to `api.cdnlibs.org` together rather
than each at its full rate, and `except LibSocialError` (alias `RanobeLibError` /
`MangaLibError`) catches errors from either.

Each package is versioned and released on its own — see its changelog in the
[repository](https://github.com/LLIJIYAPNIK/libsocial-sdk). Runnable examples:
[`examples/`](https://github.com/LLIJIYAPNIK/libsocial-sdk/tree/main/examples).

## License

MIT — see [LICENSE](https://github.com/LLIJIYAPNIK/libsocial-sdk/blob/main/LICENSE).

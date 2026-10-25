# Examples

Runnable, heavily commented scripts for each package in this repository, one directory per
package:

| Directory | Package | Import |
|---|---|---|
| [`ranobelib/`](ranobelib/) | [`ranobelib-python-sdk`](../packages/ranobelib/) — ranobelib.me, text novels | `import ranobelib` |
| [`mangalib/`](mangalib/) | [`mangalib-python-sdk`](../packages/mangalib/) — mangalib.me, manga page images | `import mangalib` |
| [`core/`](core/) | [`libsocial-core`](../packages/core/) — the shared core both are built on | `import libsocial` |

Every script is a complete, self-contained program: run it as-is with
`python examples/<package>/<file>.py`. Each one was actually executed against the live site
to produce the "Expected output" comment at the bottom of the file. Scripts are meant to be
read top to bottom as a mini-tutorial for one feature, not just copy-pasted. Each
directory's README lists its scripts.

Start with [`ranobelib/`](ranobelib/) or [`mangalib/`](mangalib/), depending on the site
you need; [`core/`](core/) is for building a package for another lib.social site or working
with the raw API.

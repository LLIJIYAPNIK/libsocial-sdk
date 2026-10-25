# libsocial-sdk

[![ranobelib-python-sdk](https://img.shields.io/pypi/v/ranobelib-python-sdk?label=ranobelib-python-sdk)](https://pypi.org/project/ranobelib-python-sdk/)
[![mangalib-python-sdk](https://img.shields.io/pypi/v/mangalib-python-sdk?label=mangalib-python-sdk)](https://pypi.org/project/mangalib-python-sdk/)
[![libsocial-core](https://img.shields.io/pypi/v/libsocial-core?label=libsocial-core)](https://pypi.org/project/libsocial-core/)
[![License: MIT](https://img.shields.io/github/license/LLIJIYAPNIK/libsocial-sdk)](LICENSE)
[![CI](https://github.com/LLIJIYAPNIK/libsocial-sdk/actions/workflows/ci.yml/badge.svg)](https://github.com/LLIJIYAPNIK/libsocial-sdk/actions/workflows/ci.yml)
[![Coverage Status](https://coveralls.io/repos/github/LLIJIYAPNIK/ranobelib-python-sdk/badge.svg?branch=main)](https://coveralls.io/github/LLIJIYAPNIK/ranobelib-python-sdk?branch=main)
[![Docs](https://github.com/LLIJIYAPNIK/libsocial-sdk/actions/workflows/docs.yml/badge.svg)](https://github.com/LLIJIYAPNIK/libsocial-sdk/actions/workflows/docs.yml)

Async Python SDKs for the lib.social sites, built on their open JSON API
(`api.cdnlibs.org`). This repository is a [uv workspace](https://docs.astral.sh/uv/concepts/projects/workspaces/);
each package under `packages/` is published to PyPI on its own.

| Package | PyPI | Description |
|---|---|---|
| [`packages/ranobelib`](packages/ranobelib/) | [`ranobelib-python-sdk`](https://pypi.org/project/ranobelib-python-sdk/) | [ranobelib.me](https://ranobelib.me): title metadata, chapter/volume downloads, export to epub/fb2/txt/pdf |
| [`packages/mangalib`](packages/mangalib/) | [`mangalib-python-sdk`](https://pypi.org/project/mangalib-python-sdk/) | [mangalib.me](https://mangalib.me): title metadata, chapters, translations, catalog, page images, export to CBZ/PDF |
| [`packages/core`](packages/core/) | [`libsocial-core`](https://pypi.org/project/libsocial-core/) | The site-independent core: api.cdnlibs.org client, shared pacing, cache, titles, chapters, catalog |

Installation, quickstart and changelog: [`packages/ranobelib/README.md`](packages/ranobelib/README.md),
[`packages/mangalib/README.md`](packages/mangalib/README.md), [`packages/core/README.md`](packages/core/README.md).
This repository was called `ranobelib-python-sdk` until the mangalib package joined it; the
old GitHub URLs redirect here, and the package names on PyPI haven't changed.
Runnable examples, one directory per package: [`examples/`](examples/). Full documentation:
**<https://LLIJIYAPNIK.github.io/libsocial-sdk/>**.

## Development

```bash
uv sync                                         # all packages + dev tools, one shared uv.lock
uv run ruff check . && uv run ruff format --check .
uv run mypy packages/core/src packages/ranobelib/src packages/mangalib/src
uv run pytest --cov                             # every package's tests
uv build --package libsocial-core
uv build --package ranobelib-python-sdk
uv build --package mangalib-python-sdk
```

## Releasing

Each package is released on its own, by publishing a GitHub Release from `main` tagged
`<package>-vX.Y.Z` — `core-vX.Y.Z` (`libsocial-core`), `ranobelib-vX.Y.Z`
(`ranobelib-python-sdk`; its releases before the monorepo are the plain `vX.Y.Z` tags),
`mangalib-vX.Y.Z`:

1. Bump `version` in the package's `pyproject.toml` through a PR, as usual.
2. `gh release create ranobelib-v0.14.0 --target main --generate-notes`

`release.yml` checks the tag's version against `pyproject.toml`, builds that package and
publishes it to PyPI; `changelog.yml` adds the release's section to that package's
`CHANGELOG.md`. If a package needs a new core, release the core first: CI tests every
package against the newest `libsocial-core` actually on PyPI.

## License

MIT — see [LICENSE](LICENSE).

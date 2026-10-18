# ranobelib-python-sdk

[![PyPI](https://img.shields.io/pypi/v/ranobelib-python-sdk)](https://pypi.org/project/ranobelib-python-sdk/)
[![License: MIT](https://img.shields.io/github/license/LLIJIYAPNIK/ranobelib-python-sdk)](LICENSE)
[![CI](https://github.com/LLIJIYAPNIK/ranobelib-python-sdk/actions/workflows/ci.yml/badge.svg)](https://github.com/LLIJIYAPNIK/ranobelib-python-sdk/actions/workflows/ci.yml)
[![Coverage Status](https://coveralls.io/repos/github/LLIJIYAPNIK/ranobelib-python-sdk/badge.svg?branch=main)](https://coveralls.io/github/LLIJIYAPNIK/ranobelib-python-sdk?branch=main)
[![Docs](https://github.com/LLIJIYAPNIK/ranobelib-python-sdk/actions/workflows/docs.yml/badge.svg)](https://github.com/LLIJIYAPNIK/ranobelib-python-sdk/actions/workflows/docs.yml)

Async Python SDKs for the lib.social sites, built on their open JSON API
(`api.cdnlibs.org`). This repository is a [uv workspace](https://docs.astral.sh/uv/concepts/projects/workspaces/);
each package under `packages/` is published to PyPI on its own.

| Package | PyPI | Description |
|---|---|---|
| [`packages/ranobelib`](packages/ranobelib/) | [`ranobelib-python-sdk`](https://pypi.org/project/ranobelib-python-sdk/) | [ranobelib.me](https://ranobelib.me): title metadata, chapter/volume downloads, export to epub/fb2/txt/pdf |
| [`packages/mangalib`](packages/mangalib/) | `mangalib-python-sdk` (not published yet) | [mangalib.me](https://mangalib.me): title metadata, chapters, translations, catalog, page images |
| [`packages/core`](packages/core/) | `libsocial-core` (not published yet) | The site-independent core: api.cdnlibs.org client, shared pacing, cache, titles, chapters, catalog |

Installation, quickstart and changelog: [`packages/ranobelib/README.md`](packages/ranobelib/README.md),
[`packages/mangalib/README.md`](packages/mangalib/README.md).
Runnable examples: [`examples/`](examples/). Full documentation:
**<https://LLIJIYAPNIK.github.io/ranobelib-python-sdk/>**.

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

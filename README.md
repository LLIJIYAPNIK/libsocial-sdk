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

Installation, quickstart and changelog: [`packages/ranobelib/README.md`](packages/ranobelib/README.md).
Runnable examples: [`examples/`](examples/). Full documentation:
**<https://LLIJIYAPNIK.github.io/ranobelib-python-sdk/>**.

## Development

```bash
uv sync                                         # all packages + dev tools, one shared uv.lock
uv run ruff check . && uv run ruff format --check .
uv run mypy packages/ranobelib/src
uv run pytest --cov
uv build --package ranobelib-python-sdk
```

## License

MIT — see [LICENSE](LICENSE).

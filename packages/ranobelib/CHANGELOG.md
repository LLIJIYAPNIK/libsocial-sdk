# Changelog

All notable changes to this package are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the
package follows [Semantic Versioning](https://semver.org/). Entries are generated from
[Conventional Commits](https://www.conventionalcommits.org/) messages by `cliff.toml` +
`.github/workflows/changelog.yml`, which adds each release's section here and pushes it to
`main` whenever a GitHub Release of this package is published — don't hand-edit released
sections, fix the underlying commit message/PR title instead.

## [0.14.1](https://github.com/LLIJIYAPNIK/libsocial-sdk/compare/ranobelib-v0.14.0..ranobelib-v0.14.1) - 2026-10-25

## [0.14.0](https://github.com/LLIJIYAPNIK/libsocial-sdk/compare/v0.13.0..ranobelib-v0.14.0) - 2026-10-18

### Added

- Build ranobelib on libsocial-core

### Changed

- Release each package by its own prefixed tag

## [0.13.0] - 2026-10-18

### Added

- Add public chapter_image_urls() and rewrite_image_urls() helpers
- Add public chapter_paragraphs() helper
- Add public cache_stats() and clear_cache() for disk cache maintenance
- Add Title.base_names, the title's names without the format suffix

## [0.12.0] - 2026-10-04

### Added

- Add Catalog.list_statuses() and filter list_titles() by several statuses
- Expose Title.last_chapter_at from get_info()
- Filter Catalog.list_titles() by chapter count

## [0.11.0] - 2026-09-30

### Added

- Send browser-like headers to the API
- Send browser-like headers when downloading illustrations
- Raise AccessBlockedError for the edge protection's HTML 403
- Forward headers= through RanobeLib and Catalog

## [0.10.0] - 2026-09-29

### Added

- Expose translator footnotes as Chapter.footnotes
- Keep footnotes in exports and size estimates

### Fixed

- Keep paragraph boundaries of dropped block-level tags

## [0.9.0] - 2026-08-14

### Added

- Support filtering by multiple countries in Catalog.list_titles()

## [0.8.0] - 2026-08-12

### Added

- Add country/region of origin to Title and Catalog.list_titles()
- Add tags filter parameter to Catalog.list_titles()

## [0.7.0] - 2026-08-10

### Added

- Add Catalog.list_genres()

## [0.6.1] - 2026-08-09

### Fixed

- Retry past rate limiting in download_title() and preserve partial progress

## [0.6.0] - 2026-08-08

### Added

- Add ApiClient.list_titles for catalog browsing
- Add Catalog entry point for listing/searching titles

## [0.5.0] - 2026-08-07

### Added

- Add on_chapter progress callback to download_title()

## [0.4.1] - 2026-08-06

### Fixed

- Cancel superseded docs deploy runs instead of queueing them
- Sanitize HTML-string chapter content, not just prosemirror

## [0.4.0] - 2026-08-06

### Added

- Add chapter/volume size estimation and RanobeLib.estimate_title_size()
- Add interactive console output via verbosity parameter

### Fixed

- Stop dropping releases with only ci: commits from CHANGELOG.md

## [0.3.0] - 2026-08-06

### Changed

- Generate CHANGELOG.md from Conventional Commits via git-cliff

## [0.2.0] - 2026-08-06

### Added

- Add RanobeLib.download_title() for whole-title bulk downloads

## [0.1.0] - 2026-08-05

### Added

- Add exception hierarchy
- Add title URL/slug parsing
- Add async API client for title metadata
- Add Title model with prosemirror summary parsing
- Add RanobeLib facade with get_info
- Add Chapter and Volume models
- Add get_chapters to the API client
- Add get_table_of_contents to RanobeLib
- Add ChapterNotFoundError
- Normalize chapter content to HTML on Chapter.content
- Add ApiClient.get_chapter
- Add RanobeLib.get_chapter
- Add VolumeNotFoundError
- Add RanobeLib.get_volume
- Add RanobeLib.get_chapters
- Add RanobeLib.get_volumes
- Add MultipleTranslationsError
- Add branch_id translation selection to RanobeLib
- Add DiskCache
- Cache raw API responses in RanobeLib
- Add concurrency limiting and retry with backoff to ApiClient
- Add Exporter protocol and format registry
- Add TxtExporter
- Add RanobeLib.export
- Add Fb2Exporter
- Add EpubExporter
- Add PdfExporter
- Set up the mkdocs-material documentation site

### Changed

- Add GitHub Actions workflow
- Add docs build check to ci.yml and a deploy workflow
- Upload coverage to Coveralls from the test job
- Add release.yml to publish to PyPI via Trusted Publishing

### Fixed

- Pin setup-uv to an existing tag
- Make Exporter.export async

[0.13.0]: https://github.com/LLIJIYAPNIK/ranobelib-python-sdk/compare/v0.12.0..v0.13.0
[0.12.0]: https://github.com/LLIJIYAPNIK/ranobelib-python-sdk/compare/v0.11.0..v0.12.0
[0.11.0]: https://github.com/LLIJIYAPNIK/ranobelib-python-sdk/compare/v0.10.0..v0.11.0
[0.10.0]: https://github.com/LLIJIYAPNIK/ranobelib-python-sdk/compare/v0.9.0..v0.10.0
[0.9.0]: https://github.com/LLIJIYAPNIK/ranobelib-python-sdk/compare/v0.8.0..v0.9.0
[0.8.0]: https://github.com/LLIJIYAPNIK/ranobelib-python-sdk/compare/v0.7.0..v0.8.0
[0.7.0]: https://github.com/LLIJIYAPNIK/ranobelib-python-sdk/compare/v0.6.1..v0.7.0
[0.6.1]: https://github.com/LLIJIYAPNIK/ranobelib-python-sdk/compare/v0.6.0..v0.6.1
[0.6.0]: https://github.com/LLIJIYAPNIK/ranobelib-python-sdk/compare/v0.5.0..v0.6.0
[0.5.0]: https://github.com/LLIJIYAPNIK/ranobelib-python-sdk/compare/v0.4.1..v0.5.0
[0.4.1]: https://github.com/LLIJIYAPNIK/ranobelib-python-sdk/compare/v0.4.0..v0.4.1
[0.4.0]: https://github.com/LLIJIYAPNIK/ranobelib-python-sdk/compare/v0.3.0..v0.4.0
[0.3.0]: https://github.com/LLIJIYAPNIK/ranobelib-python-sdk/compare/v0.2.0..v0.3.0
[0.2.0]: https://github.com/LLIJIYAPNIK/ranobelib-python-sdk/compare/v0.1.0..v0.2.0
[0.1.0]: https://github.com/LLIJIYAPNIK/ranobelib-python-sdk/tree/v0.1.0


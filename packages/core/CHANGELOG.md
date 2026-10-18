# Changelog

All notable changes to this package are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the
package follows [Semantic Versioning](https://semver.org/). Entries are generated from
[Conventional Commits](https://www.conventionalcommits.org/) messages by `cliff.toml` +
`.github/workflows/changelog.yml`, which adds each release's section here and pushes it to
`main` whenever a GitHub Release of this package is published — don't hand-edit released
sections, fix the underlying commit message/PR title instead.

## [1.0.1](https://github.com/LLIJIYAPNIK/libsocial-sdk/compare/core-v1.0.0..core-v1.0.1) - 2026-10-18

## [1.0.0](https://github.com/LLIJIYAPNIK/ranobelib-python-sdk/tree/core-v1.0.0) - 2026-10-18

### Added

- Add the libsocial-core package with the site-independent core
- Add extension points site packages need on libsocial-core

### Changed

- Release each package by its own prefixed tag

### Fixed

- Scope libsocial-core cache keys to the site

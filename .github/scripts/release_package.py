"""Which package a release tag publishes, for release.yml and changelog.yml.

Each package is released by its own tag, ``<prefix>-vX.Y.Z`` (``core-v1.0.0``,
``ranobelib-v0.14.0``, ``mangalib-v1.0.0``), published as a GitHub Release from ``main``.
This is the one place that maps a tag prefix to a package; a workflow calls it and reads
the result from ``$GITHUB_OUTPUT``-style ``key=value`` lines on stdout.

Usage::

    python .github/scripts/release_package.py <tag> [--no-version-check]

Exits non-zero, with a GitHub ``::error::`` annotation, when the tag's prefix is unknown, the
tag isn't ``<prefix>-vX.Y.Z``, the package's directory is missing, or (unless
``--no-version-check``) the tag's version differs from ``[project].version`` in the
package's ``pyproject.toml``.
"""

from __future__ import annotations

import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

PACKAGES = {
    "core": "packages/core",
    "ranobelib": "packages/ranobelib",
    "mangalib": "packages/mangalib",
}
"""Tag prefix -> package directory, relative to the repository root."""

LEGACY_TAG_PREFIXES = {"ranobelib": "v"}
"""Tags from before per-package releases: ``vX.Y.Z`` is ranobelib's history. Not accepted
for new releases, only recognized as the previous version when writing a changelog."""

_TAG = re.compile(r"^(?P<prefix>[a-z][a-z0-9]*)-v(?P<version>\d+\.\d+\.\d+)$")
_VERSION = r"[0-9]+\.[0-9]+\.[0-9]+"


class ReleaseError(Exception):
    """The tag can't be released as given."""


@dataclass(frozen=True)
class Release:
    """What a release tag publishes."""

    tag: str
    prefix: str
    version: str
    directory: str
    name: str
    tag_pattern: str

    def outputs(self) -> str:
        """``key=value`` lines for ``$GITHUB_OUTPUT``."""
        return "\n".join(
            [
                f"tag={self.tag}",
                f"prefix={self.prefix}",
                f"version={self.version}",
                f"directory={self.directory}",
                f"name={self.name}",
                f"tag_pattern={self.tag_pattern}",
            ]
        )


def tag_pattern(prefix: str) -> str:
    """Regex matching every release tag of the package, legacy ones included."""
    legacy = LEGACY_TAG_PREFIXES.get(prefix)
    if legacy is None:
        return f"^{prefix}-v{_VERSION}$"
    return f"^({prefix}-v|{legacy}){_VERSION}$"


def resolve(tag: str, *, check_version: bool = True, root: Path = REPO_ROOT) -> Release:
    """Map a release tag to its package, checking it can be released.

    Raises:
        ReleaseError: If the tag doesn't name a known package and version, the package
            directory is missing, or the version doesn't match its ``pyproject.toml``.
    """
    match = _TAG.match(tag)
    if match is None:
        raise ReleaseError(
            f"Tag {tag!r} isn't <package>-vX.Y.Z. Known packages: {', '.join(PACKAGES)}."
        )
    prefix, version = match["prefix"], match["version"]
    directory = PACKAGES.get(prefix)
    if directory is None:
        raise ReleaseError(
            f"Unknown package prefix {prefix!r} in tag {tag!r}. "
            f"Known packages: {', '.join(PACKAGES)}."
        )
    pyproject = root / directory / "pyproject.toml"
    if not pyproject.is_file():
        raise ReleaseError(f"Tag {tag!r} names {directory}, which has no pyproject.toml.")

    project = tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]
    if check_version and project["version"] != version:
        raise ReleaseError(
            f"Tag {tag!r} says version {version}, but {directory}/pyproject.toml has "
            f"{project['version']}. Bump the version on main first, or fix the tag."
        )
    return Release(
        tag=tag,
        prefix=prefix,
        version=version,
        directory=directory,
        name=project["name"],
        tag_pattern=tag_pattern(prefix),
    )


def main(argv: list[str], *, root: Path = REPO_ROOT) -> int:
    args = [arg for arg in argv if arg != "--no-version-check"]
    if len(args) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        release = resolve(args[0], check_version="--no-version-check" not in argv, root=root)
    except ReleaseError as exc:
        print(f"::error::{exc}")
        return 1
    print(release.outputs())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

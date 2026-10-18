"""Tests for release_package.py: which tags release what, and which are refused."""

import re
import tomllib
from pathlib import Path

import pytest
from release_package import PACKAGES, ReleaseError, main, resolve, tag_pattern

REPO_ROOT = Path(__file__).resolve().parents[2]


def _version(directory: str) -> str:
    text = (REPO_ROOT / directory / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version = "([^"]+)"', text, re.MULTILINE)
    assert match is not None
    return match[1]


@pytest.mark.parametrize(
    ("prefix", "name"),
    [("core", "libsocial-core"), ("ranobelib", "ranobelib-python-sdk")],
)
def test_resolves_the_real_packages_at_their_current_version(prefix: str, name: str) -> None:
    version = _version(PACKAGES[prefix])

    release = resolve(f"{prefix}-v{version}")

    assert release.name == name
    assert release.version == version
    assert release.directory == PACKAGES[prefix]


def _fake_repo(tmp_path: Path, version: str = "1.2.3") -> Path:
    package = tmp_path / "packages" / "core"
    package.mkdir(parents=True)
    (package / "pyproject.toml").write_text(
        f'[project]\nname = "libsocial-core"\nversion = "{version}"\n', encoding="utf-8"
    )
    return tmp_path


@pytest.mark.parametrize(
    "tag",
    [
        "v0.14.0",  # The legacy scheme: no longer releasable.
        "ranobelib-0.14.0",  # No "v".
        "core-v1.0",  # Not X.Y.Z.
        "core-v1.0.0-rc1",
        "Core-v1.0.0",
        "",
    ],
)
def test_refuses_malformed_tags(tag: str) -> None:
    with pytest.raises(ReleaseError, match="isn't <package>-vX.Y.Z"):
        resolve(tag)


def test_refuses_an_unknown_prefix() -> None:
    with pytest.raises(ReleaseError, match="Unknown package prefix 'manga'"):
        resolve("manga-v1.0.0")


def test_refuses_a_known_package_whose_directory_is_missing(tmp_path: Path) -> None:
    with pytest.raises(ReleaseError, match="has no pyproject.toml"):
        resolve("mangalib-v1.0.0", root=_fake_repo(tmp_path))


def test_refuses_a_version_that_differs_from_pyproject(tmp_path: Path) -> None:
    root = _fake_repo(tmp_path, version="1.2.3")

    with pytest.raises(ReleaseError, match="says version 1.2.4, but packages/core"):
        resolve("core-v1.2.4", root=root)
    assert resolve("core-v1.2.4", root=root, check_version=False).version == "1.2.4"


def test_tag_patterns_match_only_the_packages_own_tags() -> None:
    core = re.compile(tag_pattern("core"))
    ranobelib = re.compile(tag_pattern("ranobelib"))

    assert core.match("core-v1.0.0")
    assert not core.match("ranobelib-v1.0.0")
    assert not core.match("v1.0.0")
    # ranobelib's history is the legacy vX.Y.Z tags, then ranobelib-vX.Y.Z.
    assert ranobelib.match("ranobelib-v0.14.0")
    assert ranobelib.match("v0.13.0")
    assert not ranobelib.match("core-v1.0.0")
    assert not ranobelib.match("mangalib-v1.0.0")


@pytest.mark.parametrize(
    "directory",
    [directory for directory in PACKAGES.values() if (REPO_ROOT / directory).is_dir()],
)
def test_each_changelog_starts_with_the_cliff_header(directory: str) -> None:
    # changelog.yml's git-cliff --prepend recognizes the file's header only when it matches
    # cliff.toml's byte for byte; otherwise the next release duplicates it.
    def lf(path: Path) -> str:
        return path.read_bytes().decode("utf-8").replace("\r\n", "\n")

    header = tomllib.loads(lf(REPO_ROOT / "cliff.toml"))["changelog"]["header"]

    assert lf(REPO_ROOT / directory / "CHANGELOG.md").startswith(header)


def test_main_prints_github_outputs(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _fake_repo(tmp_path)

    assert main(["core-v1.2.3"], root=root) == 0
    out = capsys.readouterr().out
    assert "name=libsocial-core\n" in out
    assert "directory=packages/core\n" in out
    assert "tag_pattern=^core-v[0-9]+\\.[0-9]+\\.[0-9]+$" in out

    assert main(["core-v9.9.9"], root=root) == 1
    assert capsys.readouterr().out.startswith("::error::")
    assert main(["core-v9.9.9", "--no-version-check"], root=root) == 0
    assert main([], root=root) == 2

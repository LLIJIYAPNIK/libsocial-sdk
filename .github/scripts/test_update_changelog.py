"""Tests for update_changelog.py, on throwaway git repositories with a bare "origin".

Needs git-cliff: ``$GIT_CLIFF`` (as in changelog.yml), or ``git-cliff`` on PATH.
"""

import os
import shlex
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest
from release_package import ReleaseError
from update_changelog import main, update_changelog

REPO_ROOT = Path(__file__).resolve().parents[2]
GIT_CLIFF = shlex.split(os.environ.get("GIT_CLIFF", "git-cliff"))

pytestmark = pytest.mark.skipif(
    shutil.which(GIT_CLIFF[0]) is None, reason="git-cliff isn't available (set $GIT_CLIFF)"
)


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.strip()


def _clone(origin: Path, path: Path) -> None:
    # The script commits with the repository's own identity (changelog.yml sets one).
    git(origin.parent, "clone", str(origin), str(path))
    git(path, "config", "user.name", "Test")
    git(path, "config", "user.email", "test@example.com")


def _header() -> str:
    config = (REPO_ROOT / "cliff.toml").read_bytes().decode("utf-8").replace("\r\n", "\n")
    header: str = tomllib.loads(config)["changelog"]["header"]
    return header


def _write(repo: Path, path: str, text: str) -> None:
    file = repo / path
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_bytes(text.encode("utf-8"))


def _commit(repo: Path, message: str, path: str) -> None:
    _write(repo, path, message)
    git(repo, "add", "-A")
    git(repo, "commit", "-m", message)


LEGACY = "## [0.13.0] - 2026-10-18\n\n### Added\n\n- Legacy entry\n\n[0.13.0]: https://x/v0.13.0\n"


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A clone of a bare origin: ranobelib's legacy v0.13.0, then one change per package."""
    monkeypatch.setenv("GITHUB_REPO", "owner/repo")
    origin = tmp_path / "origin.git"
    work = tmp_path / "work"
    git(tmp_path, "init", "--bare", "-b", "main", str(origin))
    _clone(origin, work)
    git(work, "checkout", "-b", "main")

    shutil.copy(REPO_ROOT / "cliff.toml", work / "cliff.toml")
    for prefix, name in (("core", "libsocial-core"), ("ranobelib", "ranobelib-python-sdk")):
        _write(work, f"packages/{prefix}/pyproject.toml",
               f'[project]\nname = "{name}"\nversion = "0.0.0"\n')  # fmt: skip
    _write(work, "packages/core/CHANGELOG.md", _header())
    _write(work, "packages/ranobelib/CHANGELOG.md", _header() + LEGACY)
    git(work, "add", "-A")
    git(work, "commit", "-m", "chore: set up")
    git(work, "tag", "v0.13.0")

    _commit(work, "feat: core thing", "packages/core/thing.py")
    _commit(work, "feat: ranobelib thing", "packages/ranobelib/thing.py")
    _commit(work, "ci: shared thing", ".github/thing.yml")
    git(work, "tag", "core-v1.0.0")
    git(work, "tag", "ranobelib-v0.14.0")
    git(work, "push", "origin", "main", "--tags")
    return work


def _on_origin(repo: Path, path: str) -> str:
    git(repo, "fetch", "origin", "main")
    return git(repo, "show", f"origin/main:{path}") + "\n"


def test_a_release_adds_only_its_packages_section(repo: Path) -> None:
    assert update_changelog("core-v1.0.0", repo=repo, git_cliff=GIT_CLIFF) == "pushed"

    core = _on_origin(repo, "packages/core/CHANGELOG.md")
    tagged_on = git(repo, "log", "-1", "--format=%cs", "core-v1.0.0")
    assert core.count("# Changelog") == 1
    # The tagged commit ("ci: shared thing") is outside packages/core, yet the section is
    # the release's, dated like it.
    assert f"## [1.0.0](https://github.com/owner/repo/tree/core-v1.0.0) - {tagged_on}" in core
    assert "- Core thing" in core
    assert "Ranobelib thing" not in core
    assert "Shared thing" not in core  # Outside packages/core.
    assert _on_origin(repo, "packages/ranobelib/CHANGELOG.md") == _header() + LEGACY


def test_running_again_for_the_same_tag_changes_nothing(repo: Path) -> None:
    update_changelog("core-v1.0.0", repo=repo, git_cliff=GIT_CLIFF)
    head = git(repo, "rev-parse", "origin/main")

    assert update_changelog("core-v1.0.0", repo=repo, git_cliff=GIT_CLIFF) == "already there"
    git(repo, "fetch", "origin", "main")
    assert git(repo, "rev-parse", "origin/main") == head


def test_ranobelib_compares_its_first_prefixed_release_with_the_legacy_tag(repo: Path) -> None:
    update_changelog("ranobelib-v0.14.0", repo=repo, git_cliff=GIT_CLIFF)

    text = _on_origin(repo, "packages/ranobelib/CHANGELOG.md")
    section = "## [0.14.0](https://github.com/owner/repo/compare/v0.13.0..ranobelib-v0.14.0)"
    assert text.startswith(_header() + section)
    assert "- Ranobelib thing" in text
    assert "Core thing" not in text
    assert text.endswith(LEGACY)  # History untouched.


def test_each_release_gets_its_own_section_even_when_run_after_a_newer_one(
    repo: Path,
) -> None:
    _commit(repo, "feat: newer ranobelib thing", "packages/ranobelib/newer.py")
    git(repo, "tag", "ranobelib-v0.14.1")
    git(repo, "push", "origin", "main", "--tags")

    # The older release's run finishing last must still write the older release.
    update_changelog("ranobelib-v0.14.1", repo=repo, git_cliff=GIT_CLIFF)
    update_changelog("ranobelib-v0.14.0", repo=repo, git_cliff=GIT_CLIFF)

    text = _on_origin(repo, "packages/ranobelib/CHANGELOG.md")
    newer = text.split("## [0.14.1]")[1].split("## [")[0]
    older = text.split("## [0.14.0]")[1].split("## [")[0]
    assert "compare/ranobelib-v0.14.0..ranobelib-v0.14.1" in newer
    assert "- Newer ranobelib thing" in newer
    assert "- Ranobelib thing" in older
    assert "Newer" not in older


def test_a_push_rejected_because_main_moved_is_retried_on_top_of_it(
    repo: Path, tmp_path: Path
) -> None:
    other = tmp_path / "other"
    _clone(tmp_path / "origin.git", other)
    attempts: list[int] = []

    def someone_else_pushes_first(attempt: int) -> None:
        attempts.append(attempt)
        if attempt == 1:  # E.g. another package's changelog run, a moment earlier.
            _commit(other, "docs: concurrent change", "packages/core/CHANGELOG.md")
            git(other, "push", "origin", "HEAD:main")

    outcome = update_changelog(
        "ranobelib-v0.14.0",
        repo=repo,
        git_cliff=GIT_CLIFF,
        retry_delay=0,
        before_push=someone_else_pushes_first,
    )

    assert outcome == "pushed"
    assert attempts == [1, 2]
    log = git(repo, "log", "--format=%s", "origin/main", "-2")
    assert log.splitlines() == [
        "docs: update packages/ranobelib/CHANGELOG.md for ranobelib-v0.14.0",
        "docs: concurrent change",
    ]


def test_gives_up_when_main_keeps_moving(repo: Path, tmp_path: Path) -> None:
    other = tmp_path / "other"
    _clone(tmp_path / "origin.git", other)

    def someone_else_always_pushes_first(attempt: int) -> None:
        _commit(other, f"docs: concurrent change {attempt}", f"other-{attempt}.txt")
        git(other, "push", "origin", "HEAD:main")

    with pytest.raises(ReleaseError, match="main kept moving"):
        update_changelog(
            "core-v1.0.0",
            repo=repo,
            git_cliff=GIT_CLIFF,
            attempts=2,
            retry_delay=0,
            before_push=someone_else_always_pushes_first,
        )


def test_refuses_an_unknown_tag(repo: Path) -> None:
    with pytest.raises(ReleaseError):
        update_changelog("v1.0.0", repo=repo, git_cliff=GIT_CLIFF)


def test_main(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(repo)
    monkeypatch.setenv("GIT_CLIFF", shlex.join(GIT_CLIFF))

    assert main(["core-v1.0.0"]) == 0
    assert "core-v1.0.0: pushed" in capsys.readouterr().out
    assert main(["mangalib-v1.0.0"]) == 1
    assert capsys.readouterr().out.startswith("::error::")
    assert main([]) == 2

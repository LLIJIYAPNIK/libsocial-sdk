"""Checks on examples/: every public name has an example, and every example still imports.

Neither test touches the network. The examples themselves run against the live sites and
aren't run here; what these catch is an example falling behind the API — a public name
added without an example, or one renamed or removed while an example still uses it. Name
and signature changes inside an example's calls are mypy's job (CI's `examples` job).
"""

from __future__ import annotations

import importlib
import importlib.util
import re
import sys
from pathlib import Path

import pytest

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"

# Package -> its examples directory, and the modules whose __all__ it has to cover.
PACKAGES = {
    "core": ["libsocial"],
    "ranobelib": ["ranobelib", "ranobelib.exporters"],
    "mangalib": ["mangalib", "mangalib.exporters"],
}

# Public names with no example of their own, and why. Keep this short: a new public name
# normally gets an example and a line in its examples README instead.
NOT_IN_EXAMPLES: dict[str, str] = {}


def public_names(module_name: str) -> list[str]:
    module = importlib.import_module(module_name)
    names: list[str] = module.__all__
    return names


def example_sources(directory: str) -> str:
    return "\n".join(
        path.read_text(encoding="utf-8") for path in sorted((EXAMPLES / directory).glob("*.py"))
    )


@pytest.mark.parametrize("directory", sorted(PACKAGES))
def test_every_public_name_appears_in_the_package_examples(directory: str) -> None:
    source = example_sources(directory)
    missing = [
        f"{module}.{name}"
        for module in PACKAGES[directory]
        for name in public_names(module)
        if f"{module}.{name}" not in NOT_IN_EXAMPLES
        and not re.search(rf"\b{re.escape(name)}\b", source)
    ]
    assert not missing, f"no example in examples/{directory}/ uses: {missing}"


def test_exemptions_are_still_public_and_still_missing() -> None:
    # A stale exemption would hide the next real gap under the same name.
    for qualified in NOT_IN_EXAMPLES:
        module, name = qualified.rsplit(".", 1)
        directory = next(d for d, modules in PACKAGES.items() if module in modules)
        assert name in public_names(module), f"{qualified} is no longer public"
        assert not re.search(rf"\b{re.escape(name)}\b", example_sources(directory)), (
            f"{qualified} now has an example; drop it from NOT_IN_EXAMPLES"
        )


EXAMPLE_FILES = sorted(EXAMPLES.glob("*/*.py"))


@pytest.mark.parametrize("path", EXAMPLE_FILES, ids=lambda path: f"{path.parent.name}/{path.name}")
def test_example_imports_without_running(path: Path) -> None:
    # Importing runs everything but the `if __name__ == "__main__":` block, so a renamed or
    # removed import, or a module-level use of the API (a subclass, a constant), fails here.
    name = f"example_{path.parent.name}_{path.stem}"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # dataclasses and pydantic look the module up by name
    try:
        spec.loader.exec_module(module)
    finally:
        del sys.modules[name]
    assert callable(getattr(module, "main", None)), "an example defines main()"
    source = path.read_text(encoding="utf-8")
    assert '\nif __name__ == "__main__":\n' in source, "main() runs only under the __main__ guard"


def test_every_package_has_examples() -> None:
    assert sorted(path.name for path in EXAMPLES.iterdir() if path.is_dir()) == sorted(PACKAGES)
    assert all(list((EXAMPLES / directory).glob("*.py")) for directory in PACKAGES)

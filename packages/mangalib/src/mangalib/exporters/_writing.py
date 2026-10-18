"""Writing an export file atomically (not public API)."""

from __future__ import annotations

import contextlib
import os
import tempfile
from collections.abc import Iterator
from pathlib import Path


@contextlib.contextmanager
def atomic_output(path: Path) -> Iterator[Path]:
    """A temporary file next to ``path`` that replaces it only if the block succeeds.

    An export downloads every page as it goes, so it can fail halfway (a page no server
    serves, a closed chapter); without this, that would leave a truncated file behind, or
    clobber a good one from an earlier run.
    """
    descriptor, name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".part")
    os.close(descriptor)
    temporary = Path(name)
    try:
        yield temporary
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)

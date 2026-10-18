"""Console output for RanobeLib: progress bars and full-mode operation logging.

Behind ``RanobeLib``'s ``verbosity`` parameter (``False`` by default, ``"progress_only"``,
or ``"full"`` — see CLAUDE.md's roadmap entry for why these three, and why this prints
directly via ``rich`` rather than going through ``logging``). ``Reporter`` is the single
object that knows which of the three modes is active; every call site (``sdk.py``, the
exporters) just calls ``log()``/``progress()`` unconditionally and lets ``Reporter`` decide
whether that produces any output.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Literal

from rich.console import Console
from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn, TimeElapsedColumn

Verbosity = Literal["full", "progress_only"] | Literal[False]
"""``False``: silent. ``"progress_only"``: progress bars only. ``"full"``: progress bars
plus a line logged for every title/chapters-list/chapter-content fetch (cache hit or API)."""


class Reporter:
    """Console output gated by a ``Verbosity`` level, backed by a single ``rich.Console``."""

    def __init__(self, verbosity: Verbosity, *, console: Console | None = None) -> None:
        """Initialize the reporter.

        Args:
            verbosity: The active output level.
            console: Custom ``rich.console.Console`` to print through, e.g. one writing to
                an in-memory stream for tests. Defaults to a new ``Console()`` (stdout) —
                only constructed at all when ``verbosity`` isn't ``False``, so a silent
                ``RanobeLib`` never touches the terminal.
        """
        self._verbosity = verbosity
        if not verbosity:
            self._console = None
        else:
            self._console = console if console is not None else Console()

    def log(self, message: str) -> None:
        """Print ``message``, only when verbosity is ``"full"``.

        ``markup=False``: messages embed literal ``[cache]``/``[api]`` prefixes (see
        ``sdk.py``'s choke points), which rich's default markup parsing would otherwise try
        to interpret as style tags.
        """
        if self._verbosity == "full" and self._console is not None:
            self._console.log(message, markup=False)

    @contextmanager
    def progress(self, description: str, total: int) -> Iterator[Callable[[], None]]:
        """A progress bar shown for ``"progress_only"``/``"full"``, a no-op otherwise.

        Yields a zero-argument callable: call it once per completed step.
        """
        if not self._verbosity or total == 0:
            yield lambda: None
            return

        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            console=self._console,
        ) as progress:
            task_id = progress.add_task(description, total=total)
            yield lambda: progress.advance(task_id)

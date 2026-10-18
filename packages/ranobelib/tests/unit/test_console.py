"""Unit tests for ranobelib.console.Reporter."""

import io

from rich.console import Console

from ranobelib.console import Reporter, Verbosity


def _reporter_with_buffer(verbosity: Verbosity) -> tuple[Reporter, io.StringIO]:
    buffer = io.StringIO()
    console = Console(file=buffer, force_terminal=False, width=80)
    return Reporter(verbosity, console=console), buffer


def test_reporter_false_never_constructs_a_console() -> None:
    reporter = Reporter(False)

    assert reporter._console is None


def test_reporter_log_is_silent_when_verbosity_is_false() -> None:
    reporter, buffer = _reporter_with_buffer(False)

    reporter.log("should not appear")

    assert buffer.getvalue() == ""


def test_reporter_log_is_silent_in_progress_only_mode() -> None:
    reporter, buffer = _reporter_with_buffer("progress_only")

    reporter.log("should not appear")

    assert buffer.getvalue() == ""


def test_reporter_log_prints_in_full_mode() -> None:
    reporter, buffer = _reporter_with_buffer("full")

    reporter.log("fetching chapter 1/2")

    assert "fetching chapter 1/2" in buffer.getvalue()


def test_reporter_progress_is_noop_when_verbosity_is_false() -> None:
    reporter, buffer = _reporter_with_buffer(False)

    with reporter.progress("Downloading", 3) as advance:
        advance()
        advance()
        advance()

    assert buffer.getvalue() == ""


def test_reporter_progress_is_noop_for_zero_total() -> None:
    reporter, buffer = _reporter_with_buffer("full")

    with reporter.progress("Downloading", 0) as advance:
        advance()  # must not raise even though there's nothing to advance

    assert buffer.getvalue() == ""


def test_reporter_progress_only_mode_renders_a_bar() -> None:
    reporter, buffer = _reporter_with_buffer("progress_only")

    with reporter.progress("Downloading title", 2) as advance:
        advance()
        advance()

    output = buffer.getvalue()
    assert "Downloading title" in output


def test_reporter_full_mode_renders_a_bar_too() -> None:
    reporter, buffer = _reporter_with_buffer("full")

    with reporter.progress("Exporting to epub", 1) as advance:
        advance()

    assert "Exporting to epub" in buffer.getvalue()

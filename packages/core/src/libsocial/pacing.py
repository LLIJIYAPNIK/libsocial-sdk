"""Request pacing shared by every client in the process that talks to the same host."""

from __future__ import annotations

import threading
import time
from collections.abc import Awaitable, Callable


class Pacer:
    """Spaces out request starts: each one at least its delay after the previous one.

    Every ``ApiClient`` talking to the same host shares one ``Pacer`` by default (see
    ``shared_pacer()``), so two clients for different sites in one process — say ranobelib
    and mangalib, both on api.cdnlibs.org — pace against each other instead of each sending
    at its own full rate and doubling the load on the API between them.

    Works by reservation: a caller takes the next free start slot under a plain
    ``threading.Lock``, held only for that bookkeeping and never across an ``await``, then
    sleeps until the slot outside of it. So a single ``Pacer`` is safe to share across event
    loops and threads, which an ``asyncio.Lock`` (bound to the loop that first used it) is
    not.
    """

    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        """Initialize the pacer.

        Args:
            clock: Monotonic time source, in seconds. Overridable for tests.
        """
        self._clock = clock
        self._lock = threading.Lock()
        self._next_at: float | None = None

    async def wait(self, delay: float, *, sleep: Callable[[float], Awaitable[None]]) -> None:
        """Wait for this request's start slot, and reserve ``delay`` seconds after it.

        Args:
            delay: Minimum time, in seconds, before the next request (from any client
                sharing this pacer) may start after this one. Each caller passes its own,
                so clients with different delays can share a pacer.
            sleep: Sleep function to wait with — the calling client's, so tests that
                inject a fake one don't actually wait.
        """
        with self._lock:
            now = self._clock()
            start = now if self._next_at is None else max(now, self._next_at)
            self._next_at = start + delay
        if start > now:
            await sleep(start - now)


_shared: dict[str, Pacer] = {}
_shared_lock = threading.Lock()


def shared_pacer(host: str) -> Pacer:
    """The process-wide ``Pacer`` for ``host``, created on first use.

    Args:
        host: The API host, e.g. ``"api.cdnlibs.org"`` — matched case-insensitively.
    """
    key = host.lower()
    with _shared_lock:
        pacer = _shared.get(key)
        if pacer is None:
            pacer = _shared[key] = Pacer()
        return pacer

"""Unit tests for libsocial.pacing: Pacer and the process-wide pacer per host."""

import asyncio
import threading
from collections.abc import Awaitable, Callable

import pytest

from libsocial.pacing import Pacer, shared_pacer


class _FakeClock:
    """A clock that only moves when a (fake) sleep or the test moves it."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def _sleep_on(clock: _FakeClock, delays: list[float]) -> Callable[[float], Awaitable[None]]:
    async def sleep(delay: float) -> None:
        delays.append(delay)
        clock.now += delay

    return sleep


async def test_first_request_starts_immediately() -> None:
    clock, delays = _FakeClock(), list[float]()
    pacer = Pacer(clock=clock)

    await pacer.wait(0.2, sleep=_sleep_on(clock, delays))

    assert delays == []


async def test_back_to_back_requests_are_spaced_by_the_delay() -> None:
    clock, delays = _FakeClock(), list[float]()
    pacer = Pacer(clock=clock)
    sleep = _sleep_on(clock, delays)

    for _ in range(3):
        await pacer.wait(0.2, sleep=sleep)

    assert delays == [pytest.approx(0.2), pytest.approx(0.2)]


async def test_time_already_passed_counts_towards_the_delay() -> None:
    clock, delays = _FakeClock(), list[float]()
    pacer = Pacer(clock=clock)
    sleep = _sleep_on(clock, delays)

    await pacer.wait(0.2, sleep=sleep)
    clock.now = 0.15
    await pacer.wait(0.2, sleep=sleep)
    clock.now = 10.0
    await pacer.wait(0.2, sleep=sleep)

    assert delays == [pytest.approx(0.05)]


async def test_concurrent_waiters_get_consecutive_slots() -> None:
    # Requests from clients sharing one pacer, fired at the same moment: the second is pushed
    # back by the first's delay, the third by both — together they go at one client's rate.
    clock, delays = _FakeClock(), list[float]()
    pacer = Pacer(clock=clock)

    async def no_advance_sleep(delay: float) -> None:
        delays.append(delay)

    await asyncio.gather(*(pacer.wait(0.2, sleep=no_advance_sleep) for _ in range(3)))

    assert sorted(delays) == [pytest.approx(0.2), pytest.approx(0.4)]


async def test_each_caller_reserves_its_own_delay() -> None:
    clock, delays = _FakeClock(), list[float]()
    pacer = Pacer(clock=clock)

    async def no_advance_sleep(delay: float) -> None:
        delays.append(delay)

    await pacer.wait(1.0, sleep=no_advance_sleep)
    await pacer.wait(0.1, sleep=no_advance_sleep)  # Waits out the first caller's 1.0s...
    await pacer.wait(0.1, sleep=no_advance_sleep)  # ...then only its own 0.1s on top.

    assert delays == [pytest.approx(1.0), pytest.approx(1.1)]


def test_shared_pacer_is_one_per_host() -> None:
    assert shared_pacer("api.cdnlibs.org") is shared_pacer("API.cdnlibs.org")
    assert shared_pacer("api.cdnlibs.org") is not shared_pacer("cover.cdnlibs.org")


def test_shared_pacer_is_usable_from_several_event_loops() -> None:
    # An asyncio.Lock would be bound to the first loop that used it; the shared pacer must
    # keep working for a client created in another asyncio.run() or another thread.
    pacer = shared_pacer("loops.example")
    errors: list[BaseException] = []

    async def no_sleep(delay: float) -> None:
        return None

    def run() -> None:
        try:
            asyncio.run(pacer.wait(0.0, sleep=no_sleep))
        except BaseException as exc:  # pragma: no cover - only on failure
            errors.append(exc)

    run()
    thread = threading.Thread(target=run)
    thread.start()
    thread.join()

    assert errors == []

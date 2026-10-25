"""Request pacing shared across clients, and console output in the SDK's style.

Every ApiClient leaves at least 0.2 s between the starts of two requests. The `Pacer` doing
that is per host, not per client: `shared_pacer("api.cdnlibs.org")` is one object for the whole
process, and every client on that host uses it unless given its own `pacer=`. So RanobeLib and
MangaLib running side by side (both api.cdnlibs.org) share one request rate instead of
doubling it. A Pacer reserves start slots under a thread lock, so it also works across event
loops and threads. Use one for your own requests too, e.g. to a cover or image host.

`Reporter` is what the clients' `verbosity=` drives: `log()` prints only at "full",
`progress()` shows a rich progress bar at "progress_only" and "full", and at False (the
`Verbosity` default) neither prints anything. A site package's own operations use it to look
like the core's.
"""

import asyncio
import time

import httpx

from libsocial import ApiClient, Pacer, Reporter, Site, Verbosity, shared_pacer

RANOBELIB = Site(id=3, origin="https://ranobelib.me")
MANGALIB = Site(id=1, origin="https://mangalib.me")


class Recording(httpx.AsyncHTTPTransport):
    """A transport that notes when each request actually starts."""

    def __init__(self, starts: list[float]) -> None:
        super().__init__()
        self.starts = starts

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.starts.append(time.monotonic())
        return await super().handle_async_request(request)


async def burst(shared: bool) -> list[float]:
    """Five requests from each of two clients (two sites), all at once."""
    starts: list[float] = []

    def client(site: Site) -> ApiClient:
        pacer = None if shared else Pacer()  # None: the host's shared_pacer()
        return ApiClient(site, transport=Recording(starts), pacer=pacer)

    async with client(RANOBELIB) as ranobe, client(MANGALIB) as manga:
        await asyncio.gather(*(c.list_statuses() for c in (ranobe, manga) for _ in range(5)))
    starts.sort()
    return [later - earlier for earlier, later in zip(starts, starts[1:], strict=False)]


async def main() -> None:
    print("one pacer per host:", shared_pacer("api.cdnlibs.org") is shared_pacer("API.cdnlibs.org"))
    # Shared: one start every ~0.2 s across both clients. A Pacer each: two 0.2 s streams
    # interleave, so requests start twice as often against the same API.
    for shared in (True, False):
        gaps = await burst(shared)
        label = "shared pacer" if shared else "a Pacer each"
        print(f"{label}: {len(gaps) + 1} requests, gaps {min(gaps):.2f}-{max(gaps):.2f}s")

    # Your own pacing: each wait() reserves the next slot, `delay` after the previous one.
    pacer = Pacer()
    start = time.monotonic()
    for _ in range(3):
        await pacer.wait(0.5, sleep=asyncio.sleep)
        print(f"  slot at {time.monotonic() - start:.1f}s")

    # A Reporter like the clients' own. With verbosity=False nothing below would print.
    verbosity: Verbosity = "full"
    reporter = Reporter(verbosity)
    titles = ["6712--high-school-dxd-novel", "7965--chainsaw-man", "3319--overlord"]
    with reporter.progress("Processing titles", len(titles)) as advance:
        for slug_url in titles:
            reporter.log(f"[my-app] {slug_url}")
            await asyncio.sleep(0.1)
            advance()
    Reporter(False).log("never printed")


asyncio.run(main())

# Expected output (real run on 2026-10-25; the gaps vary by a few hundredths of a second with
# network latency. rich timestamps the log lines and adds where they came from on the right):
#
# one pacer per host: True
# shared pacer: 10 requests, gaps 0.19-0.22s
# a Pacer each: 10 requests, gaps 0.00-0.22s
#   slot at 0.0s
#   slot at 0.5s
#   slot at 1.0s
# [16:59:55] [my-app] 6712--high-school-dxd-novel                                   console.py:52
#            [my-app] 7965--chainsaw-man                                            console.py:52
#            [my-app] 3319--overlord                                                console.py:52
# Processing titles ---------------------------------------- 3/3 0:00:00

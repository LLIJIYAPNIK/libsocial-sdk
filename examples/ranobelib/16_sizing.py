"""How big is a title before you download it, and how big is what you already have?

The API has no content-length or image-size field anywhere, so the SDK gives two kinds of
answer, at two different costs:

1. `RanobeLib.estimate_title_size()` — *before* download_title(). Knowing the exact size
   would mean fetching every chapter, which costs as much as the download itself. Instead it
   fetches the (cheap, cached) chapter list, downloads only `sample_size` chapters spread
   evenly across the title (not just the first ones — early and late chapters often differ
   in length), and multiplies their average size by the chapter count. A sample, not a
   measurement: good enough to decide "is this worth downloading", nothing more.
2. `chapter_size(chapter)` / `volume_size(volume)` — for content you've *already* fetched.
   No requests at all: the text is measured exactly (UTF-8 bytes of the content plus
   footnotes).

Images are the approximate part of both. They aren't downloaded to be weighed (that is the
traffic this is meant to avoid), so each `<img>` in a chapter counts as `average_image_size`
bytes — 150 KB by default (`ranobelib.sizing.DEFAULT_AVERAGE_IMAGE_SIZE`), a guess, not a
measurement. Pass your own if you know better for a given title.

Either way it's the size of the source text + images, not of a specific exported file: epub's
zip compression or pdf's layout overhead aren't modeled, so the number is the same whatever
`fmt` you export to later.
"""

import asyncio

from ranobelib import RanobeLib, chapter_size, volume_size


def human(size: int) -> str:
    if size < 1_000_000:
        return f"{size / 1_000:.1f} KB"
    return f"{size / 1_000_000:.2f} MB"


async def main() -> None:
    # 47 chapters, illustrated — small enough to also fetch in full below, so the estimate can
    # be checked against the exact total.
    async with RanobeLib("https://ranobelib.me/ru/book/91443--new-hero-in-dxd") as lib:
        # sample_size=5 is the default; more samples cost more requests and narrow the error.
        # For a title with several translations per chapter, branch_id / translation_index
        # pick which one is measured (same meaning as in download_title()); chapters neither
        # resolves are just left out of the sample instead of raising, since the estimate
        # doesn't care which translation it measures.
        estimate = await lib.estimate_title_size(sample_size=5)
        print("estimate, 5 sampled chapters:", human(estimate))
        # Already-sampled chapters come from the disk cache, so this costs 10 more requests.
        estimate_15 = await lib.estimate_title_size(sample_size=15)
        print("estimate, 15 sampled chapters:", human(estimate_15))

        # Now the exact answer, by fetching everything. The sampled chapters are served from
        # the disk cache here too.
        toc = await lib.get_table_of_contents()
        volumes = await lib.get_volumes([int(volume.number) for volume in toc])

        # Exact text, assumed-average images: the same rule the estimate applied per sample.
        for volume in volumes:
            print(f"volume {volume.number}: {len(volume.chapters)} chapter(s),", end=" ")
            print(human(volume_size(volume)))
        exact = sum(volume_size(volume) for volume in volumes)
        print("exact total:", human(exact))
        print(f"estimates off by {estimate / exact - 1:+.0%} / {estimate_15 / exact - 1:+.0%}")

        # Why so far off: the text is small, the images are most of the weight, and they sit in
        # a handful of chapters. A chapter's text alone is its size with average_image_size=0.
        heaviest = max(volumes[-1].chapters, key=chapter_size)
        print(f"heaviest chapter {heaviest.volume}/{heaviest.number}:", end=" ")
        print(human(chapter_size(heaviest)), end=", ")
        print("text only", human(chapter_size(heaviest, average_image_size=0)))

        # Smaller illustrations than the default guess? Say so, and the total follows.
        exact_small = sum(volume_size(volume, average_image_size=50_000) for volume in volumes)
        print("exact total, 50 KB per image:", human(exact_small))


if __name__ == "__main__":
    asyncio.run(main())

# Expected output (real run against the live site):
#
# estimate, 5 sampled chapters: 5.78 MB
# estimate, 15 sampled chapters: 6.15 MB
# volume 0: 1 chapter(s), 0.9 KB
# volume 1: 46 chapter(s), 9.48 MB
# exact total: 9.48 MB
# estimates off by -39% / -35%
# heaviest chapter 1/25: 2.92 MB, text only 65.7 KB
# exact total, 50 KB per image: 4.48 MB

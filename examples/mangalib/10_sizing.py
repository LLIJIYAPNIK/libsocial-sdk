"""How much a manga download weighs, before downloading a single image.

The image servers answer a HEAD request with a page's exact size (Content-Length), so the
SDK can tell exactly how big a chapter is for one small request per page, with no image
traffic. That's why these are MangaLib methods (they make requests), unlike ranobelib's
plain chapter_size()/volume_size() functions, which only measure text already downloaded.

- `chapter_size(chapter)` / `volume_size(volume)`: exact, for fetched chapters (their page
  lists; get_chapter(), get_volume(), download_title(), ...). `server` / `concurrency` as in
  download_pages().
- `estimate_title_size()`: the whole title from a sample. The chapter list doesn't say how
  many pages a chapter has, so it fetches `sample_size` chapters spread across the title,
  sizes them exactly and extrapolates to every chapter download_title() would fetch —
  closed chapters excluded, translations chosen by `branch_id` / `translation_index` as in
  download_title(). Chapters neither resolves are left out of the sample instead of raising.
"""

import asyncio

from mangalib import MangaLib


def megabytes(size: int) -> str:
    return f"{size / 1_000_000:.1f} MB"


async def main() -> None:
    # A webtoon: six open chapters of tall strips, two translations each, six closed ones.
    async with MangaLib("https://mangalib.me/ru/manga/261420--husband-thief") as lib:
        chapter = await lib.get_chapter(volume=1, number="0", branch_id=26208)
        size = await lib.chapter_size(chapter)
        print(f"chapter 0: {len(chapter.pages)} pages, {megabytes(size)}")

        # Every chapter here has two translations: without a choice, no chapter can be
        # sampled, and the estimate is 0 rather than an error.
        print("estimate, no translation chosen:", await lib.estimate_title_size())

        # Six open chapters, so sample_size=6 measures all of them: the exact figure.
        estimate_2 = await lib.estimate_title_size(sample_size=2, branch_id=26208)
        estimate_6 = await lib.estimate_title_size(sample_size=6, branch_id=26208)
        by_index = await lib.estimate_title_size(sample_size=2, translation_index=0)
        print("estimate, 2 / 6 sampled chapters:", megabytes(estimate_2), megabytes(estimate_6))
        print("estimate, translation_index=0:", megabytes(by_index))

        # The exact figure: download_title() fetches the chapters' page lists (not the
        # images), then volume_size() asks about every page.
        volumes = await lib.download_title(branch_id=26208)
        exact = sum([await lib.volume_size(volume) for volume in volumes])
        pages = sum(len(chapter.pages) for volume in volumes for chapter in volume.chapters)
        print(f"exact: {megabytes(exact)} in {pages} pages")
        print(f"2-chapter estimate off by {estimate_2 / exact - 1:+.0%}")


if __name__ == "__main__":
    asyncio.run(main())

# Expected output (real run against the live site on 2026-10-25, while chapters 6-11 were in
# early access; as they open, the estimates and the exact figure grow):
#
# chapter 0: 4 pages, 5.0 MB
# estimate, no translation chosen: 0
# estimate, 2 / 6 sampled chapters: 33.1 MB 35.9 MB
# estimate, translation_index=0: 33.2 MB
# exact: 35.9 MB in 30 pages
# 2-chapter estimate off by -8%

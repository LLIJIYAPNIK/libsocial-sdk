"""Download a whole manga in one call with MangaLib.download_title().

download_title() fetches every chapter of the title — pages included — and returns them as
list[Volume], the same shape as get_table_of_contents(), ready for export() (see
09_export_formats.py). Compared with looping over get_volumes() yourself:

- Translations are settled for the whole title up front. Chapters with several translations
  need `branch_id` (use that translation wherever it exists) or `translation_index` (take
  the N-th translation of each chapter's own list). Without either, it raises
  `MultipleTitleTranslationsError` listing *every* ambiguous chapter (`AmbiguousChapter`),
  before downloading anything.
- Closed chapters (paid, early access — see 06_translations.py) are skipped, since they
  can't be fetched without an account. Only open translations count, for the choice above
  too. So the result can have fewer chapters than the table of contents.
- If a chapter fails partway (rate limiting that outlasts the retries, or any other SDK
  error), the chapters already fetched aren't lost: `DownloadTitleInterruptedError` carries
  them (`.volumes`, `.completed` / `.total`). They're also in the disk cache, so calling
  download_title() again picks up where it stopped instead of starting over.

Knobs for a long title: `chapter_delay` (an extra pause after each chapter, on top of the
client's own request pacing), `max_rate_limit_retries` (extra retries for a chapter that
keeps coming back rate-limited; 0 turns them off), `on_chapter(completed, total)` (progress
for a program, e.g. a web backend) and `verbosity` (progress bars and a log for a person at
a terminal).
"""

import asyncio

from mangalib import (
    AmbiguousChapter,
    DownloadTitleInterruptedError,
    MangaLib,
    MultipleTitleTranslationsError,
)

URL = "https://mangalib.me/ru/manga/261420--husband-thief"


def report(completed: int, total: int) -> None:
    print(f"on_chapter: {completed}/{total}")


async def main() -> None:
    async with MangaLib(URL) as lib:
        toc = await lib.get_table_of_contents()
        print("chapters in the table of contents:", sum(len(v.chapters) for v in toc))

        # Chapters 0-5 have two open translations each, so this stops before downloading.
        try:
            await lib.download_title()
        except MultipleTitleTranslationsError as exc:
            ambiguous: list[AmbiguousChapter] = exc.chapters
            for item in ambiguous:
                options = [(b.branch_id, b.teams[0].name) for b in item.branches]
                print(f"chapter {item.volume}/{item.number}:", options)

    # branch_id: one translation for every chapter that has it. verbosity="full" logs each
    # fetch and every closed chapter skipped, plus a progress bar.
    async with MangaLib(URL, verbosity="full") as lib:
        try:
            volumes = await lib.download_title(
                branch_id=26208,
                chapter_delay=0.5,
                max_rate_limit_retries=3,
                on_chapter=report,
            )
        except DownloadTitleInterruptedError as exc:
            # Not reached in this run. On a long title: keep exc.volumes (what was fetched,
            # grouped like a full result), or wait and call download_title() again — the
            # cache makes the second call resume. The original error is exc.__cause__.
            print(f"stopped after {exc.completed}/{exc.total}: {exc.__cause__}")
            return

    for volume in volumes:
        for chapter in volume.chapters:
            teams = [team.name for team in chapter.teams]
            print(chapter.volume, chapter.number, teams, len(chapter.pages), "pages")

    # translation_index=0 instead: the first translation in *each chapter's own* list. The
    # order differs between chapters, so the teams come out mixed.
    async with MangaLib(URL) as lib:
        volumes = await lib.download_title(translation_index=0)
        print([chapter.teams[0].name for chapter in volumes[0].chapters])


if __name__ == "__main__":
    asyncio.run(main())

# Expected output (real run against the live site on 2026-10-25, starting with an empty
# cache). A second run logs "[cache]" instead of "[api]". Chapters 6-11 were in early access
# then; as they open, download_title() picks them up too. rich timestamps the log lines and
# draws the bar across the terminal's width.
#
# chapters in the table of contents: 12
# chapter 1/0: [(26207, 'Lexiopia'), (26208, 'Bam Byeol')]
# chapter 1/1: [(26208, 'Bam Byeol'), (26207, 'Lexiopia')]
# chapter 1/2: [(26208, 'Bam Byeol'), (26207, 'Lexiopia')]
# chapter 1/3: [(26208, 'Bam Byeol'), (26207, 'Lexiopia')]
# chapter 1/4: [(26208, 'Bam Byeol'), (26207, 'Lexiopia')]
# chapter 1/5: [(26207, 'Lexiopia'), (26208, 'Bam Byeol')]
# [13:19:34] [cache] chapter list for 261420--husband-thief                       console.py:52
#            [skip] chapter 1/6: closed (paid or early access)                    console.py:52
#            [skip] chapter 1/7: closed (paid or early access)                    console.py:52
#            [skip] chapter 1/8: closed (paid or early access)                    console.py:52
#            [skip] chapter 1/9: closed (paid or early access)                    console.py:52
#            [skip] chapter 1/10: closed (paid or early access)                   console.py:52
#            [skip] chapter 1/11: closed (paid or early access)                   console.py:52
#            [api] fetching chapter 1/0                                           console.py:52
# on_chapter: 1/6
# [13:19:35] [api] fetching chapter 1/1                                           console.py:52
# on_chapter: 2/6
# [13:19:36] [api] fetching chapter 1/2                                           console.py:52
# on_chapter: 3/6
#            [api] fetching chapter 1/3                                           console.py:52
# on_chapter: 4/6
# [13:19:37] [api] fetching chapter 1/4                                           console.py:52
# on_chapter: 5/6
# [13:19:38] [api] fetching chapter 1/5                                           console.py:52
# on_chapter: 6/6
# Downloading 261420--husband-thief ---------------------------------------- 6/6 0:00:03
# 1 0 ['Bam Byeol'] 4 pages
# 1 1 ['Bam Byeol'] 6 pages
# 1 2 ['Bam Byeol'] 5 pages
# 1 3 ['Bam Byeol'] 6 pages
# 1 4 ['Bam Byeol'] 4 pages
# 1 5 ['Bam Byeol'] 5 pages
# ['Lexiopia', 'Bam Byeol', 'Bam Byeol', 'Bam Byeol', 'Bam Byeol', 'Lexiopia']

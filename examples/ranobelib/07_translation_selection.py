"""Handle titles with more than one translation team.

Some chapters have competing translations from different teams ("branches" in the API).
get_chapter() deliberately refuses to guess which one you want: if a chapter has more than
one branch and you don't pass `branch_id`, it raises MultipleTranslationsError rather than
silently picking one — the API's own default when branch_id is omitted was found to be
unpredictable (not simply "first branch"), so the SDK doesn't try to replicate it. See the
"Translation selection" section of docs/api-notes.md for how this was verified.
"""

import asyncio

from ranobelib import MultipleTranslationsError, RanobeLib


async def main() -> None:
    # Chapters 0-2 of this title each have two competing translations (also used title-wide
    # in 08_download_title.py).
    slug = "113306--bungou-stray-dogs-gaiden-ayatsuji-yukito-vs-kyogoku-natsuhiko"
    async with RanobeLib(f"https://ranobelib.me/ru/book/{slug}") as lib:
        # get_translations() lists the available branches for one chapter without
        # downloading any chapter content — use it to show the user their options.
        branches = await lib.get_translations(volume=1, number="0")
        for branch in branches:
            print(branch.branch_id, [team.name for team in branch.teams])

        # Calling get_chapter() without branch_id on an ambiguous chapter raises instead of
        # guessing. exc.branches carries the same branch list get_translations() returned,
        # so you can catch-and-resolve without a separate lookup.
        try:
            await lib.get_chapter(volume=1, number="0")
        except MultipleTranslationsError as exc:
            print("ambiguous, pick one:", [b.branch_id for b in exc.branches])

        # Passing branch_id (a stable id for one specific "translation line", not tied to a
        # team's own id — see docs/api-notes.md) resolves the ambiguity explicitly.
        chapter = await lib.get_chapter(volume=1, number="0", branch_id=branches[0].branch_id)
        print((chapter.content or "")[:60])


if __name__ == "__main__":
    asyncio.run(main())

# Expected output (real run against the live site on 2026-10-25):
#
# 12954 ['K&F']
# 12955 ['ChelkaDostaTrans']
# ambiguous, pick one: [12954, 12955]
# <p><strong>«Все беспорядки последнего времени — это моих рук

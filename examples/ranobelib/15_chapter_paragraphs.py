"""Get a chapter's paragraphs as plain text, indexed like the DOM, via chapter_paragraphs().

`Chapter.content` is a flat sequence of block elements (`<p>`, `<hr />`, `<img>`). A web
reader that renders it as HTML sees one element child per block, and may key things by that
position — e.g. reader comments left on "paragraph 12". chapter_paragraphs() returns each
block's text at the same index, so a server can show the paragraph a comment refers to
without parsing the chapter HTML itself.
"""

import asyncio

from ranobelib import RanobeLib, chapter_paragraphs


async def main() -> None:
    async with RanobeLib("https://ranobelib.me/ru/book/6712--high-school-dxd-novel") as lib:
        chapter = await lib.get_chapter(volume=9, number="76")

        paragraphs = chapter_paragraphs(chapter)
        print(len(paragraphs), "top-level blocks")

        # Entry i is the i-th element child of the rendered content — the same number a
        # browser gives it via `content.children[i]`. Text is plain: tags stripped, entities
        # decoded, whitespace collapsed.
        for index in range(3):
            print(index, paragraphs[index][:80])

        # Blocks with no text (an `<hr />` scene break, an image-only paragraph) are kept as
        # "" rather than skipped, so the indexes never shift.
        print("empty blocks:", sum(1 for text in paragraphs if not text))

        # Translator footnotes live in Chapter.footnotes, not in content, so they aren't
        # entries here (see 13_chapter_footnotes.py).


asyncio.run(main())

# Expected output (real run against the live site):
#
# 1113 top-level blocks
# 0 — Хорошо! Продолжай!
# 1 — Да!
# 2 Это было раннее утро второго дня школьной поездки. Небо лишь начинало светлеть.
# empty blocks: 0

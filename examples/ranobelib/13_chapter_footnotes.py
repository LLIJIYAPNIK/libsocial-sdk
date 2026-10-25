"""Read a chapter's translator footnotes separately from its text via Chapter.footnotes.

Translators on ranobelib.me add footnotes (term explanations, translation notes) as ordinary
paragraphs starting with "↑", usually after the chapter's last real paragraph — the API has
no structured footnote field of its own. The SDK recognizes those paragraphs and moves them
out of `Chapter.content` into `Chapter.footnotes`, so `content` is only the story text and
the notes can be shown on their own (a collapsible block, a list after the chapter, ...).
"""

import asyncio

from ranobelib import RanobeLib


async def main() -> None:
    async with RanobeLib("https://ranobelib.me/ru/book/6712--high-school-dxd-novel") as lib:
        chapter = await lib.get_chapter(volume=9, number="76")

        # The footnote paragraphs are gone from `content`: its last paragraph is the story's
        # last line, not a translator note.
        print(chapter.content[-120:])
        print()

        # Each footnote's `content` is sanitized inline HTML (same tags as Chapter.content,
        # e.g. <strong>/<em>), with the leading "↑" already stripped and no wrapping <p>.
        #
        # There's no marker linking a footnote to the exact spot in the text it explains:
        # translators mark the spot with a bare "*" at most, which the text also uses for
        # other things (scene breaks, censored words) — so the footnotes' order, which is the
        # order they appear in the source, is the only link there is.
        for index, footnote in enumerate(chapter.footnotes, start=1):
            print(f"{index}. {footnote.content}")

        # export() keeps them too: every format lists them in a "Notes" block after the
        # chapter's text (see 10_export_formats.py).


asyncio.run(main())

# Expected output (real run against the live site):
#
# ерименте в замке Нидзё.</p><p>Президент, похоже, наша школьная поездка подошла к совершенно
# неожиданной кульминации.</p>
#
# 1. Подразумевается район на западных окраинах Киото. Гора, давшая району название, находится
# позади него. Дословно означает «Грозовая гора».
# 2. Храм Тендай буддизма, расположенный в западной части Киото.
# 3. Буддистский храм, построенный в горах, известен своими осенними видами.
# 4. Мост, пересекающий Луну.
# 5. Традиционный костюм ханьцев Китая. В наши дни ханьфу надевается только во время торжественных
# церемоний или в исторических телесериалах и фильмах. Однако, в Китае и за границей есть
# культурные общества, которые посвящают свои силы возрождению ханьфу. Это явление называется
# «ханьфу фусин»
# 6. Замок Нидзё — укреплённая резиденция сёгунов рода Токугава, располагающаяся в Киото.

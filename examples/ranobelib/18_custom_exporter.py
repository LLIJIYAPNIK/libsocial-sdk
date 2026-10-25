"""Add your own export format: implement `Exporter`, `@register` it, export(fmt=...) it.

export() looks the format up in `ranobelib.exporters.EXPORTERS`, a dict of registered
exporter classes keyed by their `format`. Registering a class there is all it takes for
`lib.export(chapters, fmt="...")` to accept a new format — no SDK code changes, the same way
the built-in txt/fb2/epub/pdf exporters are wired up.

An exporter is any class matching the `ranobelib.exporters.Exporter` protocol:

- a `format: ClassVar[str]` — the key export(fmt=...) selects it by;
- an `async def export(self, title, chapters, output_path, *, on_chapter=None, headers=None)`
  that writes the file and returns its path. `on_chapter()` should be called once per
  chapter — it drives the progress bar when the client has `verbosity` on (see
  17_console_output.py). `headers` are the client's extra HTTP headers, for exporters that
  download things (epub/pdf fetch illustrations); one that makes no requests ignores them.

It's instantiated with no arguments, once per export() call.

The example writes JSON — the chapters' paragraphs as plain text plus their footnotes — the
kind of thing you'd feed to a search index or a translation tool rather than an e-reader.
"""

import asyncio
import json
import tempfile
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, ClassVar

from ranobelib import Chapter, Footnote, RanobeLib, Title, chapter_paragraphs
from ranobelib.exporters import EXPORTERS, Exporter, register


def footnote_record(footnote: Footnote) -> str:
    # Footnotes are inline HTML (<strong>/<em> and the like), kept as-is here.
    return footnote.content


# @register adds the class to EXPORTERS under its `format`, at import time.
@register
class JsonExporter:
    format: ClassVar[str] = "json"

    async def export(
        self,
        title: Title,
        chapters: list[Chapter],
        output_path: Path,
        *,
        on_chapter: Callable[[], None] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Path:
        records: list[dict[str, Any]] = []
        for chapter in chapters:
            records.append(
                {
                    "volume": chapter.volume,
                    "number": chapter.number,
                    "name": chapter.name,
                    # One entry per top-level block of the content; images and scene breaks
                    # are "" (see 15_chapter_paragraphs.py), dropped here.
                    "paragraphs": [text for text in chapter_paragraphs(chapter) if text],
                    "footnotes": [footnote_record(footnote) for footnote in chapter.footnotes],
                }
            )
            if on_chapter is not None:
                on_chapter()
        document = {"title": title.rus_name or title.name, "chapters": records}
        output_path.write_text(json.dumps(document, ensure_ascii=False, indent=2), "utf-8")
        return output_path


async def main() -> None:
    # Registered next to the built-in formats ("pdf" only where WeasyPrint's native libraries
    # are installed). Exporter is a runtime-checkable Protocol: matching it is about having
    # `format` and `export`, not about inheriting from anything.
    print(sorted(EXPORTERS))
    print(isinstance(JsonExporter(), Exporter))

    async with RanobeLib("https://ranobelib.me/ru/book/6712--high-school-dxd-novel") as lib:
        chapters = await lib.get_chapters([(9, "76")])
        with tempfile.TemporaryDirectory() as directory:
            path = await lib.export(chapters, fmt="json", path=Path(directory) / "dxd.json")
            document = json.loads(path.read_text("utf-8"))

    chapter = document["chapters"][0]
    print(document["title"], "/", chapter["volume"], chapter["number"], chapter["name"])
    print(len(chapter["paragraphs"]), "paragraphs, first:", chapter["paragraphs"][0][:60])
    print(len(chapter["footnotes"]), "footnotes, first:", chapter["footnotes"][0][:60])


asyncio.run(main())

# Expected output (real run against the live site, on a machine without WeasyPrint's native
# libraries — with them, "pdf" is in the list too):
#
# ['epub', 'fb2', 'json', 'txt']
# True
# Старшая школа D×D (Новелла) / 9 76 Жизнь 3: Группа Героев прибыла
# 1113 paragraphs, first: — Хорошо! Продолжай!
# 6 footnotes, first: Подразумевается район на западных окраинах Киото. Гора, давш

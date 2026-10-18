# CLAUDE.md

Инструкции для Claude Code при работе над репозиторием **ranobelib-python-sdk**.

## О проекте

Python SDK для сайта ranobelib.me: получение метаданных тайтла, скачивание глав/томов и
экспорт в epub/fb2/txt/pdf. SDK дёргает недокументированный, но открытый JSON API сети
lib.social (`api.cdnlibs.org`), а не парсит HTML.

Пакет публикуется как `ranobelib-python-sdk` (репозиторий и PyPI-имя), импортируется как
`ranobelib`.

Код, докстринги, комментарии, README и публичная документация — **на английском**
(стандарт для OSS-пакета на PyPI). Issue/PR-описания и коммуникация с пользователем внутри
таск-трекера могут быть на русском, если пользователь сам пишет по-русски.

## Ключевые технические решения (зафиксированы, не пересматривать без явного запроса)

| Область | Решение |
|---|---|
| HTTP-клиент | `httpx.AsyncClient`, только async, без sync-обёртки |
| Модели данных | pydantic v2 |
| Менеджер пакетов | `uv` (никаких pip/poetry/pipenv в проекте) |
| Минимальная версия Python | 3.11 |
| Авторизация | не реализуется в MVP (только открытый контент) |
| CLI | не делаем, только библиотека |
| PDF | WeasyPrint (HTML/CSS → PDF, общий HTML-шаблон с epub/fb2) |
| Иллюстрации | обложка тайтла + картинки внутри глав встраиваются в epub и pdf; в fb2/txt — без иллюстраций (fb2 технически поддерживает картинки, но в MVP не подключаем, чтобы не усложнять — если понадобится, отдельный PR) |
| Тесты API | VCR-кассеты: `pytest-recording` + `vcrpy` |
| Покрытие тестами | 95%+, проверяется в CI (`--cov-fail-under=95`) |
| Линт/форматирование | `ruff` (lint + format) |
| Типизация | `mypy --strict` (или разумно близко к strict) |
| Документация | `mkdocs-material` + `mkdocstrings`, деплой на GitHub Pages |
| Лицензия | MIT |
| Git workflow | атомарные коммиты по фиче, один PR на фичу, merge — вручную пользователем |
| Консольный вывод | `rich`; параметр `verbosity` в конструкторе `RanobeLib`: `False` (дефолт, тихо) / `"progress_only"` (progress bar'ы для `download_title()`/`export()`) / `"full"` (то же плюс построчный лог каждого обращения к title/chapters-list/chapter-контенту, включая кэш-хит/промах) — прямой `print`/`rich.console.Console`, не `logging` (см. roadmap-шаг 23) |

## Публичный API (контракт SDK)

Главная точка входа — класс `RanobeLib`, инициализируется ссылкой на тайтл:

```python
from ranobelib import RanobeLib

async with RanobeLib(
    "https://ranobelib.me/ru/book/6712--high-school-dxd-novel",
    verbosity="progress_only",       # False (default) / "progress_only" / "full"
    headers=None,                    # доп. HTTP-заголовки поверх браузерных дефолтов (шаг 32)
) as lib:
    info = await lib.get_info()                       # метаданные тайтла
    toc = await lib.get_table_of_contents()            # тома/главы/названия, без контента

    chapter = await lib.get_chapter(volume=6, number="51.6")
    volume = await lib.get_volume(volume=6)

    chapters = await lib.get_chapters([(6, "51.6"), (6, "52")])
    volumes = await lib.get_volumes([1, 2, 3])

    translations = await lib.get_translations(volume=6, number="51.6")
    chapter = await lib.get_chapter(volume=6, number="51.6", branch_id=...)

    all_volumes = await lib.download_title(translation_index=0, chapter_delay=0.5)

    await lib.export(chapters, fmt="epub", path="output.epub")

    from ranobelib import chapter_size, volume_size

    approx_title_bytes = await lib.estimate_title_size()   # sampled, before committing to download_title()
    exact_chapter_bytes = chapter_size(chapter)              # exact, content already fetched above
    exact_volume_bytes = volume_size(volume)                 # exact, content already fetched above
```

Каталог (листинг/поиск по всему сайту, не по одному тайтлу) — отдельная точка входа,
`Catalog`, не метод `RanobeLib` (см. пункт 8 и roadmap-шаг 24):

```python
from ranobelib import Catalog

async with Catalog() as catalog:
    page = await catalog.list_titles(query="dxd", genres=[34], statuses=[1], sort="rate_avg")
    for title in page.items:                # list[Title] — та же модель, что get_info()
        print(title.name)
    if page.has_next_page:
        next_page = await catalog.list_titles(page=page.page + 1, query="dxd")
```

Требования из ТЗ и как они ложатся на методы:

1. Скачивание отдельной главы (том + номер главы, включая дробные вида `"51.6"`) → `get_chapter`
2. Скачивание тома → `get_volume`
3. Скачивание нескольких глав → `get_chapters`
4. Скачивание нескольких томов → `get_volumes`
5. Вывод данных о тайтле (тома, главы, названия, контент) → `get_info`, `get_table_of_contents`,
   объекты `Chapter`/`Volume` с полем `.content`
6. Экспорт в epub/fb2/txt/pdf → `export()` с реестром экспортёров
6a. Определить размер главы/тома до экспорта, и приблизительный размер тайтла целиком до
    полной закачки → `sizing.chapter_size()`/`sizing.volume_size()` (точный, для уже
    скачанного контента) и `RanobeLib.estimate_title_size()` (оценка по выборке, до вызова
    `download_title()`) — см. roadmap-шаг 22.
6b. Интерактивный консольный вывод (progress bar'ы + лог работы SDK) → параметр `verbosity`
    конструктора `RanobeLib` — см. roadmap-шаг 23.
7. Выбор перевода при наличии → `get_translations()` + параметр `branch_id` (не `team_id` —
   исправлено при реализации, см. ниже и `docs/api-notes.md`) во всех методах скачивания;
   если не указан и переводов несколько — либо явная ошибка `MultipleTranslationsError` с
   перечислением вариантов, либо детерминированный дефолт (первая команда по `branches`) —
   решить и задокументировать в первом PR, где это появится, не молчать об этом выборе.
   Решено (см. `docs/api-notes.md`, раздел "Translation selection"): `get_chapter()` кидает
   `MultipleTranslationsError`, если у главы больше одной ветки перевода и `branch_id` не
   передан — детерминированный дефолт не реализован, т.к. собственный дефолт API (когда
   `branch_id` не передан) непредсказуем и не документирован (эмпирически — не
   "первая ветка в списке"). `get_chapters()`/`get_volume()`/`get_volumes()` наследуют ту же
   проверку (кидают ту же ошибку, если внутри есть неоднозначная глава), но пока не дают
   выбрать `branch_id` поглавно при массовой загрузке — это оставлено как возможное будущее
   расширение, если понадобится.
8. Листинг/поиск по каталогу (не по одному тайтлу — заголовки issue #38: "catalog listing
   isn't naturally title-scoped") → отдельный класс `Catalog` (не метод `RanobeLib`),
   `Catalog.list_titles(page=..., query=..., genres=..., statuses=..., sort=...)` — см.
   roadmap-шаг 24.

`number` уже приходит от API строкой, при необходимости содержащей дробную часть
(`"51.6"`) — отдельного параметра для дробной части в SDK нет, `number: str` передаётся
как есть. Изначально предполагался отдельный параметр `number_secondary` для дробной
части (чтобы не склеивать строку самим), но ручная проверка (см. ниже) показала, что
поле `number_secondary` в API — не дробная часть, а дублирует `volume`; контракт
поправлен, когда это обнаружилось при реализации `get_table_of_contents`.

## Что уже известно про API (проверено вручную)

Базовый URL: `https://api.cdnlibs.org/api`. Запросы идут без авторизации, 200 OK, но
перед API (и перед `cover.cdnlibs.org`) стоит DDoS-Guard: с 2026-09-30 он отвечает
HTML-403 (не JSON-403 самого API) на любой запрос без непустого `Referer` — значение не
проверяется (проходит даже `Referer: x`), `Origin`/`User-Agent` сами по себе ни на что не
влияют. SDK шлёт `Origin`/`Referer`/`User-Agent` браузера (`ranobelib/_http.py`'s
`BROWSER_HEADERS`) и в `ApiClient`, и в image-клиентах epub/pdf; `headers=` на
`RanobeLib`/`Catalog`/`ApiClient` позволяет их перекрыть (шаг 32). Такой HTML-403 SDK
отличает от JSON-403 API по `Content-Type` и кидает `AccessBlockedError`, а не
`AuthRequiredError`. Подробности и таблица проверенных комбинаций — в `docs/api-notes.md`,
раздел "WAF 403".

`api.cdnlibs.org` общий для всей сети lib.social (mangalib, ranobelib, hentailib, ...).
Эндпоинты тайтла и списка глав (`/api/manga/{slug_url}`, `/api/manga/{slug_url}/chapters`)
требуют заголовок `Site-Id: 3` — без него (или с неверным значением) запрос по
существующему тайтлу возвращает 404 с тем же телом, что и реально несуществующий тайтл,
т.е. отличить эти случаи по ответу нельзя. У эндпоинта поиска/списка (`GET /api/manga`)
другой механизм — query-параметр `site_id[]=3`, а не заголовок. Также на ошибочных статусах
API отдаёт HTML-страницу сайта вместо JSON, если не передан заголовок
`Accept: application/json`; на успешных ответах отдаёт JSON в любом случае. Подробности и
проверенный список `fields[]` для метаданных тайтла — в `docs/api-notes.md`.

Список глав тайтла:

```
GET /api/manga/{slug}/chapters
```

Ответ: `{"data": [...]}`, каждый элемент:

```json
{
  "id": 187667,
  "index": 68,
  "item_number": 68,
  "volume": "5",
  "number": "51",
  "number_secondary": "5",
  "name": "Послесловие",
  "branches_count": 1,
  "branches": [
    {
      "id": 187667,
      "branch_id": null,
      "created_at": "2018-03-20T14:09:28.000000Z",
      "teams": [],
      "user": {"username": "DUB1401", "id": 4790}
    }
  ],
  "bundle_id": null
}
```

`number_secondary` — строка; **проверено на 667 главах трёх разных тайтлов (0
расхождений): значение всегда равно `volume`**, это не дробная часть номера главы, как
предполагалось изначально по одному примеру. Дробная часть номера главы (`"6.5"`,
`"81.5"`, `"0.1"`) приходит непосредственно внутри строки `number` — отдельного поля для
неё нет. Подробности и данные проверки — в `docs/api-notes.md`. Весь список, включая
дробные главы, отдаётся одним запросом — никакого перебора `.1`, `.2` и т.д. быть не
должно, это заменяет то, что обсуждалось в начале.

`branches` — переводы разных команд одной главы; при `branches_count > 1` есть выбор
перевода (пункт 7 из ТЗ), выбирается по `branch_id` (не по `teams`/`Team.id` — `branch_id`
стабилен для конкретной "линии перевода" и остаётся единственным способом адресовать ветку
без привязанной команды; подробности в `docs/api-notes.md`).

Метаданные тайтла:

```
GET /api/manga/{slug}?fields[]=background&fields[]=eng_name&fields[]=otherNames&fields[]=summary&fields[]=releaseDate&fields[]=genres&fields[]=tags&fields[]=teams&fields[]=authors&fields[]=artists&fields[]=chap_count&fields[]=status_id&...
```

Список доступных `fields[]` не полностью каталогизирован — при реализации `get_info()`
свериться через devtools/network, какие поля реально нужны для наших моделей, и не тащить
лишнее.

### Что НЕ проверено и требует исследования перед реализацией (не гадать, не хардкодить наугад)

- Как дробный `number` (`"6.5"`) влияет на URL чтения (`/read/v{volume}/c{number}` без
  точки vs всегда с точкой) — не проверено, `number_secondary` тут ни при чём (см. выше).
- Домен и структура CDN для картинок обложки/аватаров (`cover.cdnlibs.org`) — для картинок
  *внутри глав* уже проверено, см. `docs/api-notes.md`: это сам `ranobelib.me`, отдельного
  CDN нет.
- Поведение при 403/пейволле (платные/ранние главы, 18+ без токена) — коды ответа, тело
  ошибки. 404 на несуществующую главу проверено (см. `docs/api-notes.md`), 403 — ещё нет.
- Есть ли пагинация у `/chapters` для очень больших тайтлов (у проверенного тайтла 308 глав
  пришли одним ответом, но не факт, что так всегда).

Каждый такой пункт закрывается коротким ручным исследованием (аналогично тому, как
уже сделано для списка глав) **до** написания продакшен-кода соответствующей фичи, и
результат фиксируется в PR (описание + при необходимости обновление этого файла).

## Структура репозитория

```
ranobelib-python-sdk/
├── src/
│   └── ranobelib/
│       ├── __init__.py          # публичный экспорт (RanobeLib, модели, исключения)
│       ├── _http.py             # общие для всех HTTP-клиентов браузерные заголовки
│       ├── client.py            # низкоуровневый HTTP-клиент к api.cdnlibs.org
│       ├── sdk.py                # класс RanobeLib — публичный фасад
│       ├── models.py             # pydantic-модели (Title, Chapter, Volume, Team, Branch, ...)
│       ├── exceptions.py
│       ├── cache.py              # дисковый кэш сырых ответов API
│       ├── numbering.py          # сортировка/сравнение номеров глав, парсинг URL тайтла
│       ├── catalog.py            # класс Catalog — листинг/поиск по каталогу (не по тайтлу)
│       ├── images.py             # chapter_image_urls()/rewrite_image_urls() — см. шаг 37
│       ├── paragraphs.py         # chapter_paragraphs() — см. шаг 38
│       └── exporters/
│           ├── __init__.py       # Protocol Exporter + реестр форматов
│           ├── txt.py
│           ├── fb2.py
│           ├── epub.py
│           └── pdf.py            # WeasyPrint, переиспользует HTML-шаблон из epub
├── tests/
│   ├── cassettes/                 # VCR-кассеты (записанные реальные ответы API)
│   ├── unit/
│   └── integration/                # тесты поверх кассет (используют реальные записанные данные)
├── docs/
│   ├── index.md
│   └── api-notes.md               # сюда складывать находки про недокументированный API
├── examples/
│   ├── README.md                  # индекс: файл → фича, со ссылками
│   ├── 01_title_metadata.py
│   ├── 02_table_of_contents.py
│   ├── 03_single_chapter.py
│   ├── 04_multiple_chapters.py
│   ├── 05_single_volume.py
│   ├── 06_multiple_volumes.py
│   ├── 07_translation_selection.py
│   ├── 08_download_title.py
│   ├── 09_disk_caching.py
│   ├── 10_export_formats.py
│   ├── 11_error_handling.py       # рабочие, подробно закомментированные скрипты — см. шаг 19
│   ├── 12_catalog_listing.py      # Catalog.list_titles() — см. шаг 24
│   ├── 13_chapter_footnotes.py    # Chapter.footnotes — см. шаг 30
│   ├── 14_chapter_images.py       # chapter_image_urls()/rewrite_image_urls() — см. шаг 37
│   └── 15_chapter_paragraphs.py   # chapter_paragraphs() — см. шаг 38
├── .github/workflows/
│   ├── ci.yml                     # появляется вместе с первым функциональным PR
│   ├── docs.yml
│   ├── release.yml                # публикация на PyPI по событию GitHub Release
│   └── changelog.yml              # регенерирует CHANGELOG.md по тому же событию
├── cliff.toml                     # конфиг git-cliff для CHANGELOG.md
├── pyproject.toml
├── README.md
├── CHANGELOG.md
├── LICENSE
└── CLAUDE.md
```

## Кэширование

Сырые JSON-ответы (метаданные тайтла, список глав, контент конкретной главы) кэшируются на
диск (`.ranobelib_cache/` в текущей директории по умолчанию, путь настраивается параметром
конструктора `RanobeLib(..., cache_dir=...)`). Цель — повторный экспорт в другой формат или
докачка новых глав не должны заново дёргать API за уже полученными данными. TTL и
принудительный `refresh=True` — предусмотреть, но не переусложнять в первой версии кэша.

Реализовано (`cache.py`): `DiskCache` — по файлу на ключ (имя — хэш ключа), значение плюс
время записи в JSON; `ttl` (секунды, `None` = бессрочно) передаётся конструктору `RanobeLib`
как `cache_ttl`. Кэш подключён в `sdk.py`, а не в `client.py` — "поверх уже готового
клиента" буквально, `ApiClient` не тронут. `refresh=True` есть на `get_info()`,
`get_table_of_contents()`, `get_chapter()` (три "листовых" операции, у каждой свой кэш-
неймспейс: метаданные тайтла, список глав, контент главы) — не переусложняя, на
`get_chapters()`/`get_volume()`/`get_volumes()` `refresh` пока не проброшен (они и так
получают кэш списка глав и кэш контента главы бесплатно через общие приватные методы);
добавить поглавный `refresh` для массовой загрузки — возможное будущее расширение, если
понадобится.

Обслуживание кэша (шаг 39): `cache_stats(cache_dir)` / `clear_cache(cache_dir, older_than=...)`
→ `CacheStats(entries, bytes)` — единственный публичный способ измерить/очистить кэш;
раскладка на диске остаётся внутренней деталью SDK.

## Rate limiting и ошибки

- Ограничение конкурентности: семафор на конфигурируемое число одновременных запросов
  (дефолт — разумное консервативное значение, например 5), плюс небольшая задержка между
  запросами по умолчанию.
- Retry с exponential backoff на 429 и 5xx (например через `tenacity` или ручную реализацию
  — на усмотрение реализующего PR, задокументировать выбор).
- Кастомные исключения в `exceptions.py`: `RanobeLibError` (база), `TitleNotFoundError`,
  `ChapterNotFoundError`, `VolumeNotFoundError`, `MultipleTranslationsError`,
  `AuthRequiredError` (для 403/платного контента — понятная ошибка вместо падения), `RateLimitError`,
  `AccessBlockedError` (HTML-403 от DDoS-Guard перед API — не авторизация; отличается от
  JSON-403 API по `Content-Type` ответа, не по тексту заглушки, и не ретраится — см.
  `docs/api-notes.md`, раздел "WAF 403").

Реализовано (`client.py`): выбрана ручная реализация, не `tenacity` — вся логика (семафор +
пейсинг + backoff) укладывается в ~20 строк, `tenacity` добавил бы зависимость ради обёртки,
которую пришлось бы дополнительно приспосабливать под "уважать `Retry-After`, если он есть,
иначе экспоненциально" и под инъекцию `sleep`/`clock` для тестов без реального ожидания —
см. `docs/api-notes.md` (раздел "Rate limiting и retry"). `ApiClient` — единственное место с
этими настройками (`max_concurrency=5`, `request_delay=0.2s`, `max_retries=3`,
`retry_base_delay=1.0s`, экспоненциально ×2 за попытку, `Retry-After` уважается при 429);
`RanobeLib` их не пробрасывает — та же логика, что уже принята для `timeout`/`base_url`
(`ApiClient`-only, не публичный контракт SDK). Единственное исключение — `headers` (см.
roadmap-шаг 32): пробрасывается через `RanobeLib`/`Catalog`, т.к. решает не "как" SDK
общается с API, а "пустит ли" DDoS-Guard его вообще.

## Экспорт

Общий интерфейс в `exporters/__init__.py`:

```python
class Exporter(Protocol):
    format: ClassVar[str]

    async def export(
        self,
        title: Title,
        chapters: list[Chapter],
        output_path: Path,
        *,
        on_chapter: Callable[[], None] | None = None,   # шаг 23
        headers: Mapping[str, str] | None = None,       # шаг 32
    ) -> Path: ...

EXPORTERS: dict[str, type[Exporter]] = {}

def register(exporter: type[Exporter]) -> type[Exporter]: ...
```

`export()` изначально задумывался синхронным (см. историю этого файла) — исправлено при
реализации epub (шаг 14): встраивание обложки/иллюстраций требует скачивания картинок, а
SDK async-only без sync-обёртки (см. таблицу решений выше), так что синхронный метод не
мог бы сделать сетевой запрос сам. `txt`/`fb2` не делают I/O и просто ничего не `await`-ят
в теле — исправление их не задевает.

Новый формат — новый файл в `exporters/`, декоратор `@register`, без правок ядра.
`txt` — самый простой формат, имеет смысл делать первым: так интерфейс `Exporter`
проверяется на практике до того, как в epub/pdf добавится сложность с картинками/вёрсткой.

Реализовано: `@register` регистрирует класс в `EXPORTERS` по его `format`, но чтобы декоратор
вообще выполнился, модуль нужно импортировать — `exporters/__init__.py` в конце делает это
сам через `pkgutil.iter_modules` по всем файлам пакета, так что "без правок ядра" верно
буквально: новый экспортёр не требует правки ни `sdk.py`, ни даже `exporters/__init__.py`.
`RanobeLib.export(chapters, *, fmt, path)` подбирает класс по `fmt` из `EXPORTERS` (`ValueError`
с перечислением доступных форматов, если ключа нет — до похода в сеть), сам подтягивает
`Title` через `get_info()` (кэшируется как обычно) и `await`-ит `Exporter.export()`.
`TxtExporter` конвертирует HTML главы (см. `Chapter.content`) в текст через
`html.parser.HTMLParser` (стдлиб, не `lxml`/`beautifulsoup` — экспортёру txt хватает
`p`/`br`/`hr`, картинки просто отбрасываются per правило "без иллюстраций в txt/fb2"),
не регуляркой — HTML-string-формат ответа API пробрасывает разметку сайта как есть,
включая варианты тегов (`b`/`i` вместо `strong`/`em`, см. `docs/api-notes.md`) и HTML-
сущности, которые тупая регулярка обработала бы неверно.

`Fb2Exporter` (`fb2.py`) генерирует XML через стдлиб `xml.etree.ElementTree`, не `lxml` —
`lxml` тянет за собой libxml2 как системную зависимость ради генерации, с которой стдлиб
справляется (сериализация с namespace через `ET.register_namespace`, `ET.indent` для
читаемого вывода); `lxml` при этом всё равно добавлен как dev-зависимость — валидировать
структуру сгенерированного fb2 в тестах через него, как и написано в разделе "Тестирование"
ниже. HTML главы парсится тем же подходом, что и в `TxtExporter` (свой `HTMLParser`,
`b`/`i` маппятся туда же, куда `strong`/`em`), но строит дерево элементов вместо плоского
текста, чтобы сохранить `<strong>`/`<emphasis>`; `<br />` даёт новый `<p>` (fb2 не допускает
перенос строки внутри `<p>`), `<hr />` — `<empty-line/>`, картинки отбрасываются.
`<title-info><genre>` — обязательный элемент по спецификации fb2, но надёжного маппинга
свободных жанров ranobelib на фиксированный словарь fb2 нет; вместо гадания используется
всегда валидный дефолт `prose_contemporary` — реальный жанр не теряется (он есть в
`Title.genres`), просто fb2-специфичный тег жанра не пытается его отразить.

`EpubExporter` (`epub.py`), в отличие от fb2, использует `ebooklib` как рантайм-зависимость,
а не только для тестов — epub не плоский XML-документ, а zip-контейнер с манифестом,
spine и NCX/nav TOC, ручная сборка которого руками через `zipfile`/`ElementTree` дала бы
много шансов на тонкие структурные баги; `ebooklib` (уже присутствовавший как dev-
зависимость для валидации fb2, см. выше) уже умеет писать этот контейнер корректно, так
что здесь дополнительная зависимость оправдана иначе, чем для fb2. `EpubHtml.content`
принимает HTML-фрагмент как есть — `ebooklib` сам оборачивает его в валидный XHTML-документ
через `lxml.html` (нестрогий парсер), так что контент главы не требует построения строгого
XHTML-дерева, как в fb2; единственная нужная трансформация — переписать `<img src="...">`
с абсолютных URL на локальные пути встроенных ресурсов (`_ImageSrcRewriter`, тот же подход
через `HTMLParser`, что и в txt/fb2, по той же причине). Обложка (`Title.cover.default` →
`.md` → `.thumbnail`, первое непустое) и картинки внутри глав скачиваются через отдельный
`httpx.AsyncClient` (не `ApiClient` — это другие хосты: `cover.cdnlibs.org`/`ranobelib.me`
аплоады, не `api.cdnlibs.org`, без `Site-Id` и с неизвестными лимитами), но полноценный
`ApiClient`-стиль ретраев/backoff здесь не переиспользуется — встраивание иллюстраций
best-effort: неудачная загрузка (любая ошибка HTTP) просто пропускает картинку, а не валит
весь экспорт; при этом семафор на конкурентность (`_IMAGE_CONCURRENCY = 5`, то же
консервативное значение, что и `ApiClient.max_concurrency`) всё же есть, чтобы не заливать
CDN неограниченным числом параллельных запросов. `<img>`, для которого загрузка не удалась,
из финального контента полностью убирается (не оставляется висящей внешней ссылкой) — см.
докстринг `_ImageSrcRewriter`. Этот механизм (скачивание + `<img src>` → embedded-ресурс)
вынесен в `exporters/_illustrations.py` (не публичный API, как `_shared.py`) при добавлении
`pdf`-экспортёра, т.к. обоим нужен один и тот же пайплайн — отличается только последний шаг
(локальный путь в zip для epub vs `data:`-URI для pdf, см. ниже).

`PdfExporter` (`pdf.py`, WeasyPrint) — единственные два экспортёра, у которых `export()`
реально делает сетевые запросы (epub и pdf), отсюда и исправление сигнатуры
`Exporter.export()` на `async` (см. выше). "Переиспользование HTML-шаблона" из роадмапа —
это переиспользование `exporters/_illustrations.py` (скачивание, `extract_image_urls`,
`rewrite_image_srcs`) и того же способа рендерить заголовок+тело главы, а не буквально
общий HTML-документ с epub: контент-документ epub встраивается ebooklib-ом в его собственный
XHTML-шаблон, а pdf собирает один цельный HTML-документ с CSS для WeasyPrint сам (обложка +
титульный лист + главы с `break-before: page` между ними). Картинки — не отдельные файлы (в
pdf нет контейнера, как в epub), а `data:` URI прямо в HTML, тем же переиспользуемым
`rewrite_image_srcs` (значение в мэппинге — не путь, а сама data-URI строка, функции всё
равно, что подставлять). `HTML(...).write_pdf(...)` синхронный (у WeasyPrint нет async API)
и может быть небыстрым на большой книге — обёрнут в `asyncio.to_thread`, чтобы не блокировать
event loop; сетевых запросов сам рендеринг не делает (все картинки уже скачаны заранее через
`httpx.AsyncClient`), так что это не нарушает "только async" для сетевого I/O.

**Важно**: WeasyPrint требует нативные библиотеки (Pango/cairo/gobject через GTK3-рантайм) не
только на этапе установки, а на этапе `import` — `pip`/`uv add` отрабатывает чисто на любой
платформе, но сам `import weasyprint` может упасть `OSError` без GTK3 (например, на Windows
без отдельно поставленного GTK3-рантайма). Подробности и как это обрабатывается (graceful
degradation: `pdf.py` сам ловит ImportError/OSError вокруг своего импорта и просто не
регистрирует `PdfExporter`, а не роняет весь `import ranobelib`) — в `docs/api-notes.md`,
раздел "PDF export". CI (`ci.yml`) ставит нужные apt-пакеты перед тестами, чтобы
pdf-специфичные тесты реально исполнялись там, а не только скипались.

## Документация

- Докстринги в Google-стиле для всех публичных классов/методов.
- `mkdocs.yml` + `mkdocstrings[python]` для автогенерации API-референса из докстрингов.
- `docs/api-notes.md` — живой документ с находками о недокументированном API ranobelib
  (эндпоинты, форматы полей, edge-кейсы) — обновлять по ходу реализации, не только в момент
  первого исследования.
- README.md: назначение проекта, установка (`uv add ranobelib-python-sdk` / `pip install`),
  quickstart-пример (аналогичный блоку из раздела "Публичный API" выше), ссылка на полную
  документацию.

Реализовано: `docs/index.md` — почти то же содержимое, что в README (по сути дублирует quickstart
и статус, это нормально: README — витрина на GitHub, `docs/index.md` — landing страница
сайта, аудитории разные, некоторое дублирование ожидаемо и не в тягость поддерживать, т.к.
оба меняются вместе с публичным API). `docs/reference.md` — mkdocstrings-директивы (`:::
ranobelib.Класс`) на все имена из `ranobelib.__all__` плюс `ranobelib.exporters.Exporter`/
`register`/`EXPORTERS` (публичная точка расширения, но не ре-экспортируется из
`ranobelib/__init__.py`, так что явно оговорено в тексте страницы, откуда импортировать).
`docs/api-notes.md` уже существовал с самого начала проекта — просто добавлен в `nav`
`mkdocs.yml`, без изменений по содержанию ради этого шага.

**Важно**: GitHub Pages нужно один раз включить вручную в настройках репозитория
(Settings → Pages → Source: "GitHub Actions") — `docs.yml` его не включает сам, только
деплоит после того, как включено.

**Исправлено** (после инцидента 2026-08-06): `docs.yml`'s `deploy`-джоб зависал на шаге
`actions/deploy-pages` — лог крутил "Getting Pages deployment status... Current status:
deployment_queued" вплоть до собственного 10-минутного таймаута экшна, который сам себя
отменял (`Timeout reached, aborting!`). Причина — не зависимость и не сам SDK: несколько
пушей в `main` подряд (слияние нескольких PR за короткое время) создавали по одному запуску
`docs.yml` на пуш, а старая конфигурация `concurrency: { group: pages, cancel-in-progress:
false }` (значение по умолчанию из официального GitHub-шаблона) не отменяла более старые,
ещё стоящие в очереди запуски — они просто копились и один за другим доходили до таймаута,
пока актуальный (последний) деплой ждал своей очереди за ними. Исправление —
`cancel-in-progress: true`: новый пуш сразу отменяет ещё не начавший реально аплоадиться
(состояние "queued") более старый запуск вместо того, чтобы ждать его таймаута — актуален
всегда только деплой последнего коммита в `main`, более ранние не имеют смысла держать в
очереди. Плюс `timeout-minutes` на обеих джобах (`build`: 10, `deploy`: 12) как
подстраховка поверх собственного таймаута `actions/deploy-pages`, чтобы зависший запуск не
мог висеть в UI Actions дольше нескольких минут сверх этого таймаута, даже если его
внутренняя логика когда-нибудь даст сбой.

## Git workflow

- Одна фича — одна ветка — один PR. Не смешивать несколько фич в одном PR.
- Именование веток: `feature/<короткое-описание>` (например `feature/chapters-listing`,
  `feature/epub-exporter`).
- Коммиты атомарные и осмысленные, конвенция — Conventional Commits
  (`feat:`, `fix:`, `test:`, `docs:`, `chore:`, `refactor:`). Один коммит = одно логическое
  изменение, не "накопил и залил одним махом".
- **Никогда не мержить и не пушить в `main` напрямую.** PR открывается и оставляется на
  ревью — пользователь мержит вручную. Единственное исключение — `changelog.yml` (см. шаг
  21): полностью детерминированный, не требующий ревью пуш `CHANGELOG.md` от лица
  `github-actions[bot]` сразу после публикации GitHub Release, тем же способом, что и
  `docs.yml`/`release.yml` уже действуют без PR на события `push`/`release` (не решение
  человека или Claude Code, а действие CI на его собственное скоуп-ограниченное дело —
  регенерация одного файла из тегов/коммитов, без права трогать что-либо ещё).
- Если следующая фича логически зависит от ещё не смерженного PR — либо явно спросить
  пользователя, с какой ветки продолжать, либо ответвиться от ветки предыдущей фичи и
  явно указать это в описании нового PR (потребуется ребейз после мержа зависимости).
- Перед открытием PR: локально прогнать `uv run ruff check .`, `uv run ruff format --check .`,
  `uv run mypy src`, `uv run pytest --cov`. Не открывать PR с падающими проверками.
- Каждый PR с новой фичей включает: код, тесты (держащие общее покрытие ≥95%), обновление
  докстрингов/документации, при необходимости — обновление `docs/api-notes.md`.

## CI (GitHub Actions)

CI появляется вместе с **первым PR, содержащим реальную функциональность** (первый клиент +
`get_info`), не раньше — на голом скелете проекта (структура папок, `pyproject.toml`, линт-конфиги)
CI не нужен.

`.github/workflows/ci.yml`, триггеры — `pull_request` и `push` в `main`:

- job `lint`: `uv run ruff check .`, `uv run ruff format --check .`
- job `typecheck`: `uv run mypy src`
- job `test`: матрица по Python 3.11 / 3.12 / 3.13, `uv run pytest --cov=ranobelib --cov-report=xml --cov-fail-under=95`.
  Загрузка покрытия в Coveralls — только с одной ноги матрицы (`3.12`, `if:` в шаге), не со
  всех трёх: покрытие одно и то же на всех версиях Python, а Coveralls считает каждую
  загрузку отдельным build — три загрузки одних и тех же данных только шум. Инструмент —
  пакет `coveralls` (PyPI, dev-зависимость), не `coverallsapp/github-action`: читает
  `.coverage` (родной формат coverage.py) напрямую через API coverage.py, а не через
  промежуточный файл конкретного формата (lcov и т.п.), и сам определяет GitHub Actions
  через `GITHUB_ACTIONS`/`COVERALLS_REPO_TOKEN` без доп. настройки — токен уже создан на
  coveralls.io и лежит в секретах репозитория под тем же именем.
- job `build`: `uv build`, проверка, что пакет собирается
- job `docs`: `uv run --group docs mkdocs build --strict` — не деплоит, только проверяет, что
  сайт вообще собирается (`--strict` роняет билд на битых mkdocstrings-ссылках вроде `:::
  ranobelib.ЧтоТоПереименованное`), чтобы сломанный `docs/reference.md` не всплывал только
  постфактум в `docs.yml` после мержа в `main`.

`.github/workflows/docs.yml`: отдельный workflow (не блокирует PR, только `push` в `main` +
`workflow_dispatch`), деплоит через официальный Pages-flow (`actions/upload-pages-artifact` +
`actions/deploy-pages`, не `mkdocs gh-deploy`/ветка `gh-pages`) — Pages нужно один раз
включить в настройках репозитория (Source = GitHub Actions), дальше деплоится сам на каждый
push в `main`. Тема — `mkdocs-material`, `mkdocstrings[python]` в отдельной dependency group
`docs` (не `dev` — не нужна для lint/typecheck/test/build, `uv run --group docs mkdocs ...`).

`.github/workflows/release.yml`: триггер — публикация GitHub Release (`on: release: types:
[published]`), не `push` тега напрямую — публикация релиза через GitHub UI/`gh release
create` даёт явный, осознанный момент "да, публикуем именно сейчас", в отличие от пуша тега,
который легко сделать случайно. `uv publish` (не `pypa/gh-action-pypi-publish` — проект и так
uv-first везде, лишний action не нужен) через Trusted Publishing (`--trusted-publishing
automatic`, OIDC) — токен PyPI не хранится в секретах репозитория вообще. Job запускается в
GitHub environment `pypi` (`environment: {name: pypi, url: ...}`), это должно совпадать с
именем environment, указанным при регистрации trusted publisher на pypi.org (или там же
оставить environment пустым, если сузить до конкретного environment не нужно). Requires
`permissions: id-token: write` — без него OIDC-обмен с PyPI не пройдёт.

**Важно**: Trusted Publishing нужно один раз настроить на стороне PyPI (pending trusted
publisher — можно зарегистрировать даже до первого релиза, привязывается к
owner/repo/workflow-file/environment) — это может сделать только владелец аккаунта PyPI,
`release.yml` сам ничего не включает, только публикует после того, как настроено (та же
модель, что и с GitHub Pages выше).

Кэшировать `uv` (`astral-sh/setup-uv` с `enable-cache: true`) для скорости.

## Тестирование

- `pytest` + `pytest-asyncio` (`asyncio_mode = "auto"` в конфиге).
- `pytest-recording` + `vcrpy` для тестов, которые бьют по `RanobeLib`/клиенту: кассеты в
  `tests/cassettes/<test_name>.yaml`, `record_mode="once"` (перезаписываются только вручную,
  через `--record-mode=rewrite`, если API поменялось).
- Модульные тесты без сети — для `numbering.py` (сортировка/сравнение дробных `number`,
  парсинг URL тайтла из разных форматов ссылок), моделей (валидация pydantic на кривом
  JSON), исключений (маппинг статус-кодов → нужный exception), экспортёров (генерируемый
  epub/fb2 — проверять структуру через `ebooklib`/`lxml`, а не только "файл создался").
- Обязательно покрыть error-paths: 404 на несуществующую главу/том, 403 без авторизации,
  429 с ретраями, `MultipleTranslationsError` при нескольких командах без выбора.
- Порог покрытия — 95%, настроен в `pyproject.toml` (`[tool.coverage.report] fail_under = 95`)
  и продублирован флагом в CI. Закрывать метрику честными тестами поведения, а не
  `# pragma: no cover` на всём подряд.

## Порядок реализации фич (предлагаемая последовательность PR)

Ориентир для Claude Code — не жёсткий протокол, но не перескакивать вперёд через
незакрытые зависимости без необходимости:

1. **Scaffolding** — `uv init`, `pyproject.toml`, `ruff`/`mypy` конфиги, структура папок,
   `LICENSE` (MIT), заготовка README. Без функционала, без CI.
2. **HTTP-клиент + метаданные тайтла** (`get_info`) + базовые исключения + модели `Title`.
   Первый функциональный PR → добавляется `ci.yml`.
3. **Список глав и нумерация** (`get_table_of_contents`, `numbering.py`: сортировка
   дробных номеров глав, разбор URL тайтла).
4. **Исследование + реализация контента главы** (сначала ручное исследование эндпоинта,
   фиксация в `docs/api-notes.md`, потом код + модель `Chapter.content`).
5. **`get_chapter`** — скачивание одной главы.
6. **`get_volume`** — скачивание тома.
7. **`get_chapters`** — несколько глав.
8. **`get_volumes`** — несколько томов.
9. **Выбор перевода** — `get_translations`, параметр `team_id`, `MultipleTranslationsError`.
10. **Дисковый кэш** (`cache.py`) поверх уже готового клиента.
11. **Rate limiting + retry** в клиенте.
12. **Exporter-интерфейс + `txt`-экспортёр** (проверка интерфейса на простом формате).
13. **`fb2`-экспортёр**.
14. **`epub`-экспортёр** (+ обложка и иллюстрации).
15. **`pdf`-экспортёр** (WeasyPrint, переиспользование HTML-шаблона).
16. **Документация** — `mkdocs`, `docs.yml`, дописать README до полноценного quickstart.
17. **Бейджи в README** — license, версии Python, CI (агрегированный статус `ci.yml`:
    lint/typecheck/test/build), coverage (Coveralls, токен уже подключён на
    coveralls.io), docs (статус `docs.yml`). Требует загрузки покрытия в Coveralls из
    `ci.yml` (сейчас `--cov-report=xml` только пишет файл локально в раннере, никуда не
    отправляется) — задокументировать выбор инструмента для загрузки здесь же, когда
    реализовано.
18. **Публикация на PyPI** — `.github/workflows/release.yml`, `uv publish` через PyPI
    Trusted Publishing (OIDC, без хранения токена в секретах репозитория), триггер —
    публикация GitHub Release. Имя пакета (`ranobelib-python-sdk`) на момент написания
    свободно (проверено через `https://pypi.org/pypi/ranobelib-python-sdk/json` → 404).
    Требует одноразовой настройки на стороне PyPI (pending trusted publisher — регистрируется
    ещё до первого релиза, привязан к конкретным repo/workflow/environment), которую может
    сделать только владелец аккаунта PyPI — Claude Code не может выполнить фактическую первую
    публикацию сам, только подготовить workflow и объяснить, что нужно сделать вручную.
    Бейдж PyPI (версия с pypi.org) в README до первого успешного релиза будет показывать
    "not found" — это ожидаемо, как и с CI/docs бейджами до первого прогона.
19. **Рабочие примеры по каждой фиче — в `examples/`, не в README** — по одному
    самодостаточному Python-файлу на фичу верхнего уровня (`get_info`, `get_table_of_contents`,
    `get_chapter(s)`, `get_volume(s)`, выбор перевода, `download_title`, кэш, `export()` во
    все 4 формата, обработка исключений), с префиксом `NN_` для порядка чтения
    (`examples/01_title_metadata.py`, ...). Каждый файл — полностью рабочий скрипт (`import`ы,
    `async def main()`, `asyncio.run(main())`, не голый `async with`) и **подробно
    закомментирован**: не просто что делает вызов (это видно по имени метода), а зачем этот
    параметр/паттерн нужен, какие есть нюансы — комментарии рассчитаны на то, что файл читают
    как мини-туториал по фиче, а не только копируют. Ожидаемый вывод — комментарным блоком в
    конце файла (`# Expected output (real run against the live site): ...`), не
    отдельным markdown-блоком, как раньше в README. Примеры не придумываются — каждый
    прогоняется по-настоящему против живого API перед тем, как попасть в `examples/` (тот же
    принцип, что и с ручным исследованием API в `docs/api-notes.md`: не гадать, проверять).
    `examples/README.md` — краткий индекс (таблица файл → фича) со ссылками на каждый скрипт.
    Основной `README.md` примеры не содержит вообще — только раздел "Examples" с одной-двумя
    фразами и ссылкой на `examples/` (решение изменено уже после первой реализации: раньше
    примеры были прямо в README, вынесены в отдельную директорию, когда список фич вырос
    настолько, что README стал слишком длинным для витрины на GitHub — сами скрипты и их
    подробные комментарии там были бы избыточны). `mkdocs`-документация (шаг 16) по-прежнему
    источник полного API-референса, `examples/` её не заменяет и не дублирует — это
    copy-paste-ориентированные сценарии, а не референс по каждому классу/методу.
20. **Скачивание всего тайтла целиком** — новый метод `download_title()` (публичный API,
    контракт из раздела "Публичный API" выше дополняется этим методом; описанный там пример
    quickstart-а не переписывается ради него — метод дополняет набор `get_*`, а не заменяет
    ни один из них). Требования:
    - Один вызов, без ручного перебора томов/глав пользователем — метод сам получает список
      глав (`_get_chapters()`, как и `get_volume(s)`/`get_chapters()`) и скачивает контент
      каждой главы, возвращая `list[Volume]` (тот же тип, что `get_table_of_contents()`, но
      с заполненным `Chapter.content`), сгруппированный через уже существующий
      `_group_into_volumes()`.
    - Дополнительный, поверх уже имеющегося в `ApiClient` пейсинга/backoff (см. раздел "Rate
      limiting и ошибки" выше — тот пейсинг никуда не девается и продолжает применяться к
      каждому запросу), параметр `chapter_delay: float = 0.0` — дополнительная пауза после
      каждой скачанной главы. `ApiClient`-настройки (`request_delay` и т.д.) остаются
      client-only и не пробрасываются через `RanobeLib` (решение, зафиксированное для
      `timeout`/`base_url` в разделе "Rate limiting и ошибки" выше) — `chapter_delay` не
      нарушает это: это отдельная, специфичная для *bulk*-сценария пауза на уровне
      `RanobeLib`, а не проброс клиентских настроек.
    - Перевод при неоднозначности (`branches_count > 1`) — не гадать и не падать на первой же
      неоднозначной главе: сначала проверяются **все** главы тайтла, и только затем (если
      есть нерешённые) кидается одна ошибка `MultipleTitleTranslationsError` (новое
      исключение в `exceptions.py`, `chapters: list[AmbiguousChapter]`) — со списком *всех*
      неоднозначных глав сразу (не только первой попавшейся) и их `branch_id`-опций, чтобы
      пользователь не чинил ошибку по одной главе за раз через повторные запуски. Это
      закрывает пункт "per-chapter override for the bulk methods... future enhancement", про
      который `docs/api-notes.md` (раздел "Translation selection") явно писал, что он не
      реализован — теперь реализован, но только для `download_title()`, не для
      `get_chapters()`/`get_volume()`/`get_volumes()` (у них по-прежнему нет per-chapter
      выбора, см. тот же раздел `docs/api-notes.md`, актуализировать его в этом PR).
    - Два options резолва неоднозначности, оба опциональные и взаимоисключающие
      (`ValueError`, если переданы вместе):
      - `branch_id: int | None` — использовать этот `branch_id` для каждой неоднозначной
        главы, где он есть среди её `branches` (та же семантика, что уже есть у
        `get_chapter(..., branch_id=...)`, просто применённая ко всему тайтлу сразу;
        осмысленно благодаря тому, что `branch_id` — стабильный id "линии перевода", см.
        `docs/api-notes.md`).
      - `translation_index: int | None` — взять перевод по позиции в `branches` каждой
        неоднозначной главы (`0` — первый и т.д.), т.к. одна и та же команда не обязательно
        имеет одинаковый `branch_id` на разных главах тайтла (если она вообще есть на всех),
        а позиция — универсальный запасной вариант "бери первый (или N-й)" из требований.
      - Если для какой-то главы ни `branch_id`, ни валидный `translation_index` не резолвятся
        (`branch_id` не найден среди её `branches`, либо `translation_index` вне диапазона) —
        эта глава тоже попадает в список `MultipleTitleTranslationsError.chapters`, а не
        падает отдельной непонятной ошибкой (`IndexError` и т.п.).
      - Без обоих параметров — поведение по умолчанию: `MultipleTitleTranslationsError` при
        первой же неоднозначной главе тайтла (после полной проверки всех глав, как описано
        выше) — тот же принцип "не гадать самому", что уже принят для `get_chapter()`.
    - `docs/api-notes.md` (раздел "Translation selection") обновить, убрав формулировку про
      "future enhancement, если понадобится" — заменить на факт, что реализовано в
      `download_title()`.
    - **Добавлено позже (issue #35):** `on_chapter: Callable[[int, int], None] | None = None`
      — вызывается как `on_chapter(completed, total)` после каждой скачанной главы, поверх
      уже существующего `advance()` из `self._reporter.progress()` (см. шаг 23 ниже), не
      вместо него — `verbosity` печатает в терминал *этого* процесса, что бесполезно
      вызывающему, который сам не терминал (например, веб-бэкенд, гоняющий
      `download_title()` в фоновой задаче и обязанный сообщать прогресс браузеру через
      собственный polling/SSE-эндпоинт — ровно кейс из issue). Сигнатура — `(completed,
      total)`, а не `Callable[[], None]`, как у `Exporter.export()`'s `on_chapter` (шаг 23):
      там `total` вызывающему уже известен (`len(chapters)`, тот же список он и передал), а
      здесь общее число глав становится известно только после резолва неоднозначности
      перевода внутри `download_title()`, так что отдавать его вместе с каждым тиком дешевле
      для вызывающего, чем заставлять его самому дергать `get_table_of_contents()` только
      ради счётчика.
    - **Добавлено позже (issue #41):** длинные тайтлы (сотни-тысячи глав) на устойчивой
      последовательной загрузке упирались в собственный rate limit API раньше, чем
      заканчивалась глава — фиксированный ретрай-бюджет `ApiClient` (`max_retries=3`,
      `retry_base_delay=1.0s`, ~7s итого) расчитан на одиночный запрос, а не на bulk-операцию,
      уже работающую какое-то время; после его исчерпания `RateLimitError` пробрасывался прямо
      из `download_title()`, теряя все уже скачанные главы (они жили только в локальном списке
      метода). Исправлено двумя частями, обе на уровне `sdk.py` (не `ApiClient` — это
      специфичная для bulk-сценария надстройка, а не изменение общей ретрай-политики, которой
      пользуются все остальные методы):
      1. `_fetch_chapter_riding_out_rate_limits()` — дополнительный, более грубый слой ретрая
         поверх `_fetch_chapter()`, только внутри `download_title()`: на `RateLimitError`,
         пережившем собственные ретраи `ApiClient`, ждёт (уважая `Retry-After`, если он есть,
         иначе экспоненциальный backoff с потолком) и пробует снова, до нового параметра
         `max_rate_limit_retries` (дефолт `DEFAULT_RATE_LIMIT_RETRIES=6`; `0` отключает этот
         слой целиком).
      2. Если глава всё равно не скачивается (исчерпан `max_rate_limit_retries`, либо любая
         другая `RanobeLibError` посреди загрузки) — уже скачанные главы больше не
         теряются: `download_title()` кидает новое исключение `DownloadTitleInterruptedError`
         (`slug_url`, `volumes` — то, что уже скачано, сгруппировано так же, как при успехе,
         `completed`, `total`, исходная ошибка — как `__cause__`), вместо того чтобы дать
         исходной ошибке пробросить наружу и стереть прогресс. Тот же паттерн, что
         `ranobelib-companion` уже делал снаружи SDK как workaround (ловить `RateLimitError`,
         подождать, вызвать `download_title()` заново, положиться на дисковый кэш) — issue
         просил перенести это внутрь SDK, чтобы получить бесплатно для любого вызывающего, а
         не только для этого одного workaround'а.
      Не распространено на `get_chapters()`/`get_volume()`/`get_volumes()`/
      `estimate_title_size()` в этом фиксе — репродукция и сам issue именно про
      `download_title()` (единственный bulk-метод, чей смысл — пройти *все* главы длинного
      тайтла одним вызовом, поэтому именно он реально доходит до таких количеств запросов
      подряд; остальные bulk-методы получают явный, заданный вызывающим список
      глав/томов и по той же причине редко подходят к таким числам на практике). Тот же
      механизм для них — возможное будущее расширение, если понадобится, не реализовано
      здесь наугад. Подробности и разбор чисел (`5.0s`/`60.0s`/`6` — оценка, не измерено
      против реального окна rate limit'а API) — в `docs/api-notes.md`.
21. **`CHANGELOG.md` с автогенерацией через GitHub Actions.** Формат — [Keep a
    Changelog](https://keepachangelog.com/) + [Conventional
    Commits](https://www.conventionalcommits.org/) как источник записей (проект и так им
    следует, см. "Git workflow" выше — переиспользуется, а не вводится новая конвенция).
    - Инструмент — [`git-cliff`](https://git-cliff.org/) (Rust-бинарь, конфиг `cliff.toml` в
      корне репозитория), не `conventional-changelog`/`standard-version` (Node-экосистема,
      проект и так uv-first везде, лишний рантайм ради этого не нужен — та же логика выбора,
      что уже применена к `coveralls` в `ci.yml` и ручной retry-реализации в `client.py`, см.
      выше). Секция `[git.commit_parsers]` в `cliff.toml` мапит `feat:`/`fix:`/`perf:` в
      группы `Added`/`Fixed`/`Performance` changelog-а, `ci:` — в `Changed`, и **пропускает**
      `test:`/`chore:`/`style:`/`refactor:`/`docs:` — этот проект коммитит атомарно на
      каждый подшаг фичи (см. "Git workflow"), так что "сырой" лог коммитов на порядок шумнее
      итогового changelog-а; отбор по типу коммита — единственный способ получить
      пользователь-ориентированный список без ручной курации на каждый релиз. `ci:` — не
      implementation detail, как остальные пропущенные типы, а зачастую сам пользователь-
      видимый результат релиза (новая автоматизация, новая release-инфраструктура) —
      изначально был в списке пропускаемых, но это привело к тому, что `v0.3.0` (только
      `docs:`/`ci:`/`chore:`-коммиты, добавившие `examples/` и саму эту автогенерацию
      changelog-а) отрендерился с нулём записей и полностью выпал из файла; см. также
      "Уже вышедшие версии" ниже.
    - `cliff.toml`: `body`/`header`/`footer` — Tera-шаблоны; версии оформлены как markdown
      reference-ссылки (`## [X.Y.Z] - дата`), футер генерирует под них
      `[X.Y.Z]: .../compare/vPREV..vX.Y.Z` (или `.../tree/vX.Y.Z` для самой первой версии) —
      стандартный паттерн Keep a Changelog, ссылки берутся из `remote.github.owner`/`repo`.
      Одного `git remote origin` для их резолва оказалось недостаточно (проверено локальным
      прогоном `git-cliff` без переменной — вместо владельца/имени репозитория подставлялась
      пустая строка); `.github/workflows/changelog.yml` поэтому явно прокидывает
      `GITHUB_REPO: ${{ github.repository }}` в env шага `git-cliff-action` — это же нужно
      делать при ручном локальном прогоне `git-cliff` (см. "Уже вышедшие версии" ниже).
      `tag_pattern` ограничен `^v[0-9]+\.[0-9]+\.[0-9]+$`, чтобы будущие нерелизные теги
      (если появятся) не попадали в историю версий.
    - `.github/workflows/changelog.yml`: триггер — `release: types: [published]`, тот же
      триггер, что уже есть у `release.yml` (шаг 18) — оба воркфлоу реагируют на один и тот
      же осознанный момент "релиз опубликован", каждый занимается своим (публикация в PyPI /
      обновление changelog-а), не связаны друг с другом напрямую. Шаги: `actions/checkout`
      с `ref: main` (не `github.ref` — для `release: published` это detached tag-ref, пушить
      обратно с него нельзя) и `fetch-depth: 0` + `fetch-tags: true` (`git-cliff` должен
      видеть всю историю и все теги, не последний коммит); генерация через
      `orhun/git-cliff-action@v4` (сам скачивает нужный `git-cliff`, не нужно ставить бинарь
      вручную) в `CHANGELOG.md`; коммит и `git push origin HEAD:main` от имени
      `github-actions[bot]`, только если файл реально изменился (`git diff --cached --quiet`
      перед коммитом — идемпотентность: повторный прогон на тот же тег не создаёт пустых
      коммитов). Требует `permissions: contents: write` на уровне воркфлоу (по умолчанию
      `GITHUB_TOKEN` может быть read-only в зависимости от настроек репозитория) — см. также
      новое исключение в разделе "Git workflow" выше про этот единственный случай прямого
      пуша в `main` без PR.
    - Уже вышедшие версии (`v0.1.0`, `v0.2.0`, теги и GitHub Releases существуют на момент
      написания этого пункта) — `CHANGELOG.md` при первом добавлении в репозиторий сразу
      прогнан через `git-cliff` по существующей истории коммитов и тегов (не написан руками
      "по памяти" — тот же принцип "не гадать, проверять", что и везде в этом файле), так что
      уже в этом PR файл покрывает обе версии, а не только будущие релизы.
22. **Оценка размера скачивания** — новый модуль `sizing.py` + метод
    `RanobeLib.estimate_title_size()`. Мотивация: у API нет ни поля длины контента, ни
    размера картинок нигде в ответах (ни в `/chapters`, ни в самой главе — см.
    `docs/api-notes.md`), так что точный размер принципиально нельзя узнать, не скачав
    контент; при этом это как раз тот SDK, для которого "сколько это займёт места" —
    вопрос по существу (скачивание+экспорт ранобэ), а не общая утилита.

    Два разных сценария, с разной ценой запросов — оба зафиксированы явно, не гадать:

    - **Глава/том, контент уже скачан** (`get_chapter()`/`get_volume()`/`get_volumes()`/
      `download_title()` уже вернули объект с `.content`) — точный размер бесплатен, без
      дополнительных запросов: `sizing.chapter_size(chapter)` — точные байты
      `len(content.encode("utf-8"))` плюс `image_count * average_image_size` (число `<img>`
      в контенте, через уже существующий `exporters._illustrations.extract_image_urls` —
      не считать теги регуляркой второй раз); `sizing.volume_size(volume)` — сумма по
      главам тома. Обе — обычные функции, не методы моделей: `models.py` остаётся чисто
      данными (тот же принцип, что уже применён к `numbering.py` — логика поверх моделей
      живёт рядом, не в них), и это также избегает обратной зависимости `models.py` →
      `exporters._illustrations` (та зависит от `models.py` для `Cover`, не наоборот).
    - **Тайтл целиком, до вызова `download_title()`** — точный размер стоит столько же,
      сколько сам `download_title()` (нужно скачать контент каждой главы), что убивает саму
      цель "узнать заранее, стоит ли качать". `RanobeLib.estimate_title_size()` вместо этого
      берёт список глав (дёшево, кэшируется), сэмплирует до `sample_size` (по умолчанию 5)
      глав, распределённых равномерно по всему тайтлу (не только первые — ранние и поздние
      главы бывают разной длины), скачивает контент только этой выборки (через тот же
      `_fetch_chapter()`/дисковый кэш, что и в остальном SDK — если после оценки вызвать
      `download_title()`, сэмплированные главы не скачиваются повторно), считает среднее
      `chapter_size()` по выборке и умножает на общее число глав тайтла. Разрешение перевода
      — те же `branch_id`/`translation_index`, что у `download_title()` (переиспользует
      `_resolve_bulk_branch_id`), но с другим поведением на нерешённой неоднозначности:
      неразрешимая глава просто пропускается как кандидат для выборки, вместо того чтобы
      кидать `MultipleTitleTranslationsError`, как делает `download_title()` — оценке
      размера не важно, *какой именно* перевод измерен, только что это осмысленный текст
      главы этого тайтла; кидать ошибку ради оценки было бы противоречием самой идее
      "быстро прикинуть, не разбираясь".
    - `average_image_size` (дефолт `sizing.DEFAULT_AVERAGE_IMAGE_SIZE = 150_000` байт) —
      константа-допущение, не измеряется сетевым запросом: реальный вес каждой картинки
      можно узнать только скачав её, а это ровно тот сетевой трафик, которого вся фича
      пытается избежать (тот же компромисс, что и у epub/pdf-иллюстраций в разделе
      "Экспорт" — там скачивание оправдано, потому что картинки всё равно нужно скачать для
      встраивания; здесь это лишняя работа только ради более точной оценки). Параметр
      переопределяем на каждом вызове (`chapter_size()`/`volume_size()`/
      `estimate_title_size()`), если у вызывающего есть более точное предположение для
      конкретного тайтла.
    - Результат — оценка объёма исходного текста+картинок (в байтах), не байт-в-байт
      предсказание веса конкретного экспортированного файла: сжатие zip-контейнера epub,
      разметка/CSS-оверхед pdf, verbosity XML в fb2 — всё это не моделируется, оценка одна
      и та же независимо от `fmt`, который в `export()` передадут потом. Этого достаточно
      для решения "стоит ли качать вообще", не для точного планирования места на диске.
    - `chapter_size`/`volume_size` ре-экспортированы из `ranobelib/__init__.py` (в отличие
      от `exporters.Exporter`/`register`/`EXPORTERS` — те не ре-экспортируются, т.к. это
      точка расширения для написания новых экспортёров, а не то, чем пользуется обычный
      вызывающий каждый день; `chapter_size`/`volume_size` — наоборот, обычный дневной
      юзкейс наравне с `get_chapter`/`get_volume`).
23. **Интерактивный консольный вывод** — новый модуль `console.py` (класс `Reporter`) +
    параметр `verbosity: Literal["full", "progress_only"] | Literal[False] = False`
    конструктора `RanobeLib`. Три уровня, зафиксированы буквально по формулировке задачи:
    `False` (дефолт — полностью тихо, никакого поведения не меняет по сравнению с уже
    существующим SDK), `"progress_only"` (progress bar'ы при `download_title()`/`export()`),
    `"full"` (то же плюс построчный лог работы SDK, чтобы пользователь видел, что
    происходит).

    - **Библиотека — `rich`** (новая runtime-зависимость). Даёт progress bar и
      форматированный консольный лог одним и тем же `rich.console.Console` без написания
      своего терминального рендеринга; `tqdm` закрыл бы только progress bar, для `"full"`
      всё равно пришлось бы городить отдельный print/форматирование. Ручная `\r`-based
      реализация (без новой зависимости, в духе решений по retry/HTML-парсингу) была
      рассмотрена и отклонена — здесь эффект как раз в качестве консольного вывода
      (визуальный progress bar, а не текстовый лог строк), а не в логике, которую стоит
      писать самим.
    - **Прямой `print`/`rich.console.Console`, не stdlib `logging`.** Обычная библиотека
      обязана использовать `logging` и не решать за потребителя, печатать что-то в консоль
      или нет — но здесь `verbosity` сам параметр конструктора, буквально решающий именно
      это; раз пользователь явно попросил консольный вывод как часть публичного контракта,
      обвязывать это ещё и через `logging.basicConfig`, который потребителю пришлось бы
      настраивать отдельно, было бы избыточной косвенностью ради гибкости, которую тут
      никто не просил (пользователь UI-приложения на SDK, которому не нужен вывод в его
      собственную консоль, просто не передаёт `verbosity` — дефолт `False` ничего не печатает).
    - **`"full"`-логирование заведено через три приватных choke point в `sdk.py`**
      (`_get_title()`/`_get_chapters()`/`_fetch_chapter()` — уже единственные места, где
      идёт обращение к дисковому кэшу и `ApiClient`), а не в каждый публичный метод
      отдельно: `get_info()`, `get_table_of_contents()`, `get_chapter()`, `get_chapters()`,
      `get_translations()`, `get_volume()`, `get_volumes()`, `download_title()`,
      `estimate_title_size()` — все в конечном счёте вызывают один из этих трёх методов,
      так что каждый из них уже "покрыт выводом" бесплатно, без правки самих
      публичных методов. Строка лога называет ресурс и источник — кэш или API
      (`"[cache] chapter 6/51.6"` / `"[api] chapter 6/51.6"`), т.к. "что происходит"
      включает и то, ушёл ли реально запрос в сеть, не только какая операция вызвана.
      Retry/backoff *внутри* `ApiClient` в это логирование не включены — `verbosity` живёт
      на уровне `RanobeLib`, а `ApiClient` уже задокументирован как единственное место со
      своими собственными, не пробрасываемыми через `RanobeLib` настройками (см. "Rate
      limiting и ошибки" выше); тащить `Reporter` внутрь `ApiClient` ради этого значило бы
      нарушить то разделение ради второстепенной части задачи.
    - **Progress bar для `download_title()`** — оборачивает уже существующий цикл по
      `planned` (по одному тику на скачанную главу), плюс отдельный (меньший) бар в
      `estimate_title_size()` вокруг цикла по выборке, той же формы ради единообразия.
    - **Progress bar для `export()`** — протокол `Exporter.export()` получает новый
      опциональный параметр `on_chapter: Callable[[], None] | None = None`, вызываемый
      каждым из четырёх экспортёров (`txt`/`fb2`/`epub`/`pdf`) один раз на обработанную
      главу; `RanobeLib.export()` передаёт колбэк, который двигает прогресс-бар на
      `len(chapters)` шагов. **Известное ограничение, не скрывается**: для `epub`/`pdf`
      самая медленная часть — скачивание иллюстраций (`download_images()`) — происходит
      *до* цикла по главам, который дёргает `on_chapter`, так что бар какое-то время не
      двигается, пока идёт скачивание, а затем быстро долистывает до конца на CPU-only
      этапе сборки документа. Инструментировать сам `download_images()` отдельным
      прогрессом — возможное будущее расширение, не сделано в этом PR, чтобы не городить
      два разных прогресс-бара с разными total на один вызов `export()`.
    - Тесты новых `on_chapter`-колбэков и `Reporter` — через `rich.console.Console(file=...)`
      с перехватом вывода в `io.StringIO` (не мокать `rich` целиком) и через прямой подсчёт
      вызовов колбэка, не через парсинг реального терминального вывода.
24. **Каталог: листинг/поиск по всему сайту** (issue #38, запрошено компаньон-проектом
    `ranobelib-companion`, которому для страницы каталога нужен способ листинга/поиска без
    парсинга HTML). Новый модуль `catalog.py`, класс `Catalog`:
    - **Отдельная точка входа, не метод `RanobeLib`.** `RanobeLib` конструируется по ссылке
      на конкретный тайтл (`parse_slug_url`) — листинг каталога в принципе не привязан ни к
      какому тайтлу, так что ему некуда деться в этот класс без добавления
      опционального/фиктивного URL, чего сам issue тоже явно избегает в предложенной сигнатуре
      (`async with Catalog(...) as catalog`). `Catalog` — независимый async context manager
      с собственными `ApiClient`/`DiskCache` (тот же паттерн, что `RanobeLib`, просто без
      привязки к `slug_url`).
    - `Catalog.list_titles(*, page=1, per_page=30, query=None, genres=None, status=None,
      sort="last_chapter_at", refresh=False) -> CatalogPage` (`CatalogPage` — новая модель в
      `models.py`: `items: list[Title]`, `page: int`, `has_next_page: bool`).
      `page`/`per_page` валидируются на стороне SDK до похода в сеть (`ValueError`, тот же
      принцип, что уже применён к `sample_size` в `estimate_title_size()`): `page >= 1`,
      `10 <= per_page <= 60` — оба диапазона взяты из реального поведения API (см.
      `docs/api-notes.md`, раздел "Catalog listing/search"), не выдуманы.
    - **`sort="last_chapter_at"` — не `"updated_at"`, как было в исходном предложении issue.**
      Ручная проверка (см. `docs/api-notes.md`) показала, что `updated_at` не входит в реальный
      набор допустимых значений API (422), а сам параметр запроса, который что-то делает,
      называется `sort_by`, не `sort` (`sort` тихо принимается и ни на что не влияет — той же
      природы находка, что и `number_secondary`/`team_id` ранее в этом файле). SDK использует
      `sort_by` внутри, но называет публичный параметр `sort` (как и предлагал issue) —
      расхождение имён параметр/аргумент задокументировано в докстринге `list_titles()` и в
      `docs/api-notes.md`, чтобы не потерялось.
    - **`Title` переиспользуется как есть для элементов списка**, как явно просил issue —
      отдельная модель "элемент каталога" не заведена: сырой элемент `GET /api/manga`
      проходит через `Title.model_validate()` без ошибок (все обязательные поля модели
      присутствуют в ответе), поля, которых этот эндпоинт не отдаёт (`genres`, `summary`,
      `chapter_count`, ...), остаются на дефолтах модели (`None`/`[]`), как для любого другого
      частично заполненного `Title`.
    - **Дисковое кэширование — переиспользован существующий `DiskCache`** (issue явно
      предполагает `cache_dir`/`cache_ttl` в конструкторе `Catalog`, той же формы, что у
      `RanobeLib`), ключ кэша строится из всех параметров фильтрации/сортировки/страницы —
      кэшируется именно результат конкретного запроса листинга, не весь каталог. Это не
      противоречит пункту issue "no bulk prefetch or caching strategy" — тот пункт про отказ
      от отдельной фичи "предзагрузить и закэшировать каталог целиком", а не про отказ от уже
      существующего в проекте паттерна "кэшировать сырой ответ на диск по ключу запроса"
      (`cache.py`), которым `RanobeLib` и так пользуется для всех своих `_get_*`.
    - **Фильтры — `genres`/`status`, оба через `int`-идентификаторы, без встроенного словаря
      имён в `list_titles()` самом.** `GET /api/genres` и `GET /api/manga/genres` отвечают 403
      без авторизации (см. `docs/api-notes.md`), так что `list_titles()` не пытается
      валидировать/маппить `genres`/`status` id на человекочитаемые имена сам — тот же принцип
      "не гадать", что и у `average_image_size`/`branch_id` в других фичах. Рабочий способ
      получить id → имя для жанров всё же нашёлся отдельно — см. шаг 25 (`list_genres()`).
      `genres` — список id, работает как AND (нужны все перечисленные жанры одновременно, не
      любой из них) — эмпирически подтверждено, не задокументировано официально.
    - **Не реализовано, задокументировано как сознательный пропуск, не как забытое:**
      постраничная стабильность `sort="random"` (API поддерживает её через параметр
      `random_order`, `Catalog` его не пробрасывает — вне рамок задачи issue, см.
      `docs/api-notes.md`), направление сортировки (`sort_type`, найден при исследовании, но
      issue его не просил — если понадобится, отдельное расширение), `verbosity` (не входит в
      предложенную issue сигнатуру конструктора `Catalog`, и разовый запрос листинга не
      получает пользы от progress-bar'ов так, как их получает `download_title()`/`export()`).
    - `Catalog`/`CatalogPage` ре-экспортированы из `ranobelib/__init__.py` — обычный дневной
      юзкейс наравне с `RanobeLib`, не точка расширения, которую нужно прятать (см. решение
      по `chapter_size`/`volume_size` в шаге 22 для того же рассуждения от противного).
    - `examples/12_catalog_listing.py` добавлен по тому же принципу, что и остальные примеры
      (шаг 19) — реально прогнан против живого API.
25. **`Catalog.list_genres()`** (issue #44, тот же запрос от `ranobelib-companion`, что и шаг
    24 — компаньону нужен список жанров с именами для чекбоксов фильтра на странице
    каталога, а хардкодить таблицу id → имя на веб-слое запрещено теми же соображениями, что
    уже описаны для `genres`/`status` выше — эта логика про ranobelib.me принадлежит SDK).
    - Шаг 24 (и `docs/api-notes.md`) на момент написания фиксировал "нет публичного способа
      получить список жанров" — проверены были только `GET /api/genres` и
      `GET /api/manga/genres` (оба 403). Дальнейшее исследование (см. `docs/api-notes.md`,
      раздел "Genre filter") нашло рабочий, не требующий авторизации эндпоинт:
      `GET /api/constants?fields[]=genres` — 200, отдаёт полный список жанров сети lib.social
      (не только ranobelib). Формулировка "нет публичного способа" в `list_titles()`'s
      докстринге исправлена этим PR — теперь способ есть, просто через `list_genres()`, не
      через сам `list_titles()`.
    - `async def list_genres(self, *, refresh: bool = False) -> list[Genre]` на `Catalog` —
      сигнатура и возвращаемый тип ровно как предложено в issue (`Genre` уже существует,
      использовался только в `Title.genres`, отдельная "жанр каталога"-модель не заводится,
      тот же принцип, что уже применён к `Title` в шаге 24 для элементов листинга).
    - **Фильтрация по `site_ids` — обязательна, не опциональна.** `GET /api/constants` не
      скоупится по сайту никаким параметром запроса (`Site-Id`-заголовок ни на что не влияет
      — проверено явно, см. `docs/api-notes.md`), в отличие от `GET /api/manga` (шаг 24) —
      ответ отдаёт жанры сразу для всей сети lib.social, каждый со своим полем `site_ids`.
      54 из 55 жанров включают ranobelib (id сайта `3`) в `site_ids`; жанр `88` ("Детское")
      — только `site_ids: [5]`. `Catalog.list_genres()` фильтрует по `site_ids`, содержащим
      `3`, перед возвратом (`catalog.py`'s `_build_genres()`, переиспользует
      `client.RANOBELIB_SITE_ID`) — без этого шага вызывающий получил бы опции фильтра,
      которые в принципе не могут совпасть ни с одним тайтлом ranobelib через
      `list_titles(genres=...)`.
    - **Кэширование — тот же `DiskCache`, что и у `list_titles()`**, отдельный
      неймспейс-ключ (`"catalog:genres"`, без параметров — эндпоинт их не принимает), с тем же
      `refresh=True` escape hatch, что и у `list_titles()` — открытые в issue вопросы решены
      этим же ответом ("кэшировать как остальное" и "да, `refresh`").
    - `Genre` ре-экспортирован из `ranobelib/__init__.py` (раньше не был — использовался
      только опосредованно через `Title.genres`) — тот же принцип, что и у
      `chapter_size`/`volume_size` в шаге 22: обычный дневной юзкейс (аннотировать
      возвращаемое значение `list_genres()`), не точка расширения, которую нужно прятать.
26. **Страна/регион происхождения тайтла** (issue #48, тот же запрос от
    `ranobelib-companion`, что и шаги 24-25 — на странице каталога после жанров следующий
    планируемый фильтр в сайдбаре "Filters" — страна происхождения, и по тем же соображениям
    компаньону нельзя хардкодить таблицу id → имя страны на веб-слое).
    - Issue предлагал модель `Country(id, name)` и параметры по образу `genres`/`status`
      (`fields[]=countries`/`GET /api/countries`-подобный эндпоинт, по аналогии с
      `list_genres()`) — оба предположения не подтвердились при проверке (см.
      `docs/api-notes.md`, раздел "Country/origin filter"): `GET /api/constants
      ?fields[]=countries` — рабочий эндпоинт, но отдаёт не страны происхождения тайтлов, а
      несвязанный список (3 записи с `phone_code`/`emoji_unicode`, похоже на
      телефонные коды для какого-то из user-flow сайта). Реальное понятие "страна
      происхождения" уже присутствует в каждом ответе `GET /api/manga/{slug}` и
      `GET /api/manga` по умолчанию (без доп. `fields[]`) под полем `type` — до этого PR
      висело в `docs/api-notes.md` как "extra field, `Title` не моделирует" (было верно на
      момент шага 24, стало неполным, как только выяснилось назначение поля). Фильтр
      каталога — `types[]=<id>` (OR-семантика, не AND, как у `genres[]` — ожидаемо, у
      тайтла только один `type`), список id → label — `GET /api/constants?fields[]=types`,
      та же не заскоупленная по сайту форма, что и у `fields[]=genres`, с тем же
      постфильтром по `site_ids`, содержащим `3`.
    - Из полного списка `types` на ranobelib.me приходится 6 значений: `10` "Япония", `11`
      "Корея", `12` "Китай" — буквально страны, как и предполагал issue — плюс `13`
      "Английский", `14` "Авторский", `15` "Фанфик" — не страны, но тот же классификатор
      происхождения на уровне самого сайта. Решено: не пытаться сузить до "настоящих" трёх
      стран (это было бы домысливанием на уровне SDK, которого сам API не делает) — `Country`
      отдаёт все 6 как есть, с оговоркой в докстринге модели и в `docs/api-notes.md`.
    - Публичная форма API оставлена ровно такой, как предложил issue (`Country(id, name)`,
      `Title.country: Country | None`, `Catalog.list_titles(country=...)`,
      `Catalog.list_countries()`) — совпадает с реальным юзкейсом (фильтр в сайдбаре), только
      внутренняя реализация (имя wire-параметра `types[]`, эндпоинт `fields[]=types`, не
      "чистое" понятие страны) исправлена под то, что действительно возвращает API — тот же
      принцип, что и у `sort`/`sort_by`, `number_secondary`, `team_id` ранее в этом файле.
      `name` в `Country` замаплен на `label` из сырого ответа (`Field(alias="label")`,
      `populate_by_name=True` — тот же паттерн, что и у `Title`'s `otherNames`/`releaseDate`)
      — в отличие от `Genre`/`Tag`, где сырое поле уже называется `name` без маппинга.
    - `Title.country` — тоже через alias (`Field(alias="type")` на `country`), т.к. сырой
      ключ в ответе `/api/manga/...` — `type`, не `country`.
    - Кэширование `list_countries()` — тот же `DiskCache`, отдельный неймспейс-ключ
      (`"catalog:countries"`), тот же `refresh=True`, что и у `list_genres()`;
      `list_titles()`'s кэш-ключ дополнен параметром `country`, как и `genres`/`status`.
    - `Country` ре-экспортирован из `ranobelib/__init__.py`, тот же принцип, что и у `Genre`
      в шаге 25 (обычный дневной юзкейс — аннотировать `list_countries()`/`Title.country`, не
      точка расширения).
27. **Фильтр каталога по тегам** (issue #50, снова `ranobelib-companion` — на странице
    тайтла каждый тег из `Title.tags` должен вести на каталог, отфильтрованный по этому
    тегу, тем же паттерном, что уже работает для жанровых бэйджей через `genres=[...]`).
    - Issue явно не был уверен в двух вещах и просил не гадать: поддерживает ли API фильтр
      по тегу вообще, и если да — AND или OR семантика (тегов обычно больше и они более
      специфичны, чем жанры, так что OR казался issue правдоподобным дефолтом, даже ценой
      несогласованности с `genres`). Проверено напрямую: `tags[]=<id>` — рабочий фильтр
      (подтверждено: тайтл `129971`, попавший в результаты `tags[]=218`, при прямом запросе
      `fields[]=tags` действительно имеет тег `218` "Боги" среди своих тегов). Семантика —
      **AND, как и у `genres[]`, не OR** (та же методика проверки, что и для `genres` —
      комбинация реального id тега с несуществующим, `tags[]=218&tags[]=999999`, даёт **0**
      результатов, не то же ненулевое количество, что и `tags[]=218` один — при OR реальный
      id всё равно дал бы совпадения). Неизвестные id тегов не валидируются (200, пустой
      результат, не 422) — как и `genres[]`, в отличие от `status[]`/`types[]`.
    - `Catalog.list_titles(tags: list[int] | None = None)` — форма ровно как в issue
      (список id, как у `genres`), тот же принцип "не валидировать перед отправкой", что и у
      `genres` (см. `docs/api-notes.md`).
    - **`Catalog.list_tags()` не добавлен** — в отличие от шагов 25/26 (`list_genres()`,
      `list_countries()`), этому issue не нужен независимый от конкретного тайтла список
      id → имя: компаньон уже получает и id, и имя каждого тега из `Title.tags` (тег на
      странице тайтла уже отрендерен с этими данными, ссылка просто добавляет
      `?tags=<id>` к уже известному значению) — заводить отдельный листинг ради юзкейса,
      которому он не нужен, было бы преждевременным расширением API. `GET /api/constants
      ?fields[]=tags` при этом похоже существует (найден, но не исследован, ещё в шаге 25 —
      см. `docs/api-notes.md`) и остаётся кандидатом для будущего `list_tags()`, если
      появится юзкейс, которому он действительно нужен.
    - `Tag` **не** ре-экспортирован из `ranobelib/__init__.py` в этом PR — в отличие от
      `Genre`/`Country`, ни один новый публичный метод не возвращает `list[Tag]` напрямую
      (только `list_titles(tags=[...])` принимает голые `int`), так что нет нового
      юзкейса, требующего аннотировать этот тип на вызывающей стороне (тот же принцип, что
      уже применён к `chapter_size`/`Genre`/`Country` — экспортировать только когда
      появляется юзкейс, а не превентивно).
    - Кэш-ключ `list_titles()` дополнен параметром `tags`, тем же способом, что и `genres`.
28. **Фильтр каталога по автору/художнику/переводческой команде — issue #51, НЕ
    реализовано.** Issue предлагал `author_id`/`artist_id`/`team_id` (по образу `status` —
    единичное значение, не список) и сам явно отметил открытый вопрос: поддерживает ли API
    такой фильтр вообще (та же оговорка, что issue #50 сделал для тегов — там не
    подтвердилась, теги оказались рабочим фильтром). Здесь — подтвердилась: после
    исчерпывающей проверки (см. `docs/api-notes.md`, раздел "Author/artist/team filter") —
    ~25 правдоподобных имён query-параметров на `GET /api/manga` (snake_case/camelCase,
    единственное/множественное число, включая Laravel-стиль `filter[author_id]=...`),
    отдельные под-эндпоинты вида `/api/people/{id}/manga`/`/api/teams/{id}/manga` (404),
    `fields[]` на `/api/people/{id}` (ничего не добавляет, даже на заведомо неверное
    значение — непохоже, что там вообще подключён `fields[]`), и свободный текстовый поиск
    `q=<имя автора>` (0 результатов даже для реального автора с ровно одним тайтлом) — ни
    один способ не сузил выдачу. **Решение: параметры не добавлены.** Фильтр, который
    выглядит рабочим, но молча ничего не фильтрует (API не отклоняет неизвестные
    query-параметры, а просто их игнорирует — так что нет способа заставить SDK честно
    ошибиться на "неподдерживаемом" фильтре) хуже отсутствия фильтра — тот же принцип, что
    и решение не гадать `average_image_size`/`branch_id`-дефолты в других местах этого
    файла, применённое к целому issue целиком, а не к одному параметру внутри уже решённой
    фичи. Issue закрыт с комментарием, объясняющим находку, а не смержен как фича.
29. **Фильтр каталога по нескольким странам сразу — issue #55.** Шаг 26 (`country: int |
    None`) зафиксировал единичное значение, обосновав это тем, что у тайтла ровно одна
    страна происхождения — это утверждение о том, чем тайтл *обладает*, не о том, что нужно
    *фильтру*: companion-приложению для мультиселект-чекбоксов (вместо radio-кнопок) в
    сайдбаре "Filters" нужно "Япония ИЛИ Корея", тем же списком id, что уже есть у
    `genres`/`tags`, но с OR-, не AND-семантикой (тайтл может совпасть только с одной из
    выбранных стран, а не обязан иметь их все). OR-семантика повторного `types[]` уже была
    подтверждена при исследовании шага 26 (`types[]=10&types[]=11` → результаты с обоими
    типами) — issue #55 лишь переоткрыл этот вопрос как открытый до отдельной проверки;
    перепроверено ещё раз с большей выборкой (`limit=60`) — см. `docs/api-notes.md`, раздел
    "Widened to accept multiple countries". `country: int | None` заменён целиком на
    `countries: list[int] | None` (не оставлен рядом как отдельный параметр — issue оставлял
    это на усмотрение реализации, но проект не держит неиспользуемые параллельные параметры
    ради обратной совместимости, см. общие принципы CLAUDE.md); `None`/пустой список — не
    применять фильтр по стране вообще, как и у `genres`/`tags`. Кэш-ключ `list_titles()`
    обновлён (`countries` вместо `country`), `examples/12_catalog_listing.py` дополнен
    примером фильтра по двум странам сразу (реально прогнан против живого API, как и
    остальные примеры).

30. **Сноски переводчика отдельным полем `Chapter.footnotes`** (issue #58, снова
    `ranobelib-companion` — его читалка группирует сноски в сворачиваемый блок "Сноски" и до
    этого PR распознавала их сама по тексту, как временный workaround).
    - Issue сам оставлял открытыми два вопроса — размечает ли API сноски как-то структурно, и
      есть ли явная связь "маркер в тексте → сноска". Проверено (см. `docs/api-notes.md`,
      раздел "Translator footnotes"): **нет и нет.** Ни в HTML-строке, ни в prosemirror нет
      ни отдельного узла/марки, ни `<sup>`/якорей/классов — сноска это просто текст,
      набранный переводчиком, минимум в трёх разных формах даже внутри одного тайтла
      (`↑`-абзацы/`<ol><li>&uarr;…`, `слово*1` + `1*текст`, "Заметки переводчика" + `[1] …`).
    - Распознаётся **только `↑`-форма**: `p`/`li` (HTML) или `paragraph` (prosemirror), чей
      первый непустой текст начинается с `↑` — в выборке `↑` ни разу не встретилась вне начала
      сноски, т.е. признак однозначен. `[1]`/`1*`/заголовок "Заметки" — обычный текст тоже,
      ошибочное срабатывание молча удалило бы текст главы из `content`, так что они не
      распознаются (тот же принцип "не гадать", что и у `average_image_size`/`branch_id`).
      Возможное будущее расширение, если понадобится.
    - Модель `Footnote(content: str)` — **без поля `marker`**, предложенного issue: заполнить
      его нечем — место ссылки в тексте помечается максимум голой `*` без номера, а `*` в тех
      же текстах ещё и разделитель сцен `***`, `*действие*` и цензура цифр. Порядок в
      `Chapter.footnotes` (порядок в исходнике) — единственная связь, которая есть; модель,
      а не голый `str`, чтобы поле можно было добавить позже без ломки API.
    - Сноски **убираются из `content`** (не дублируются), как и просил issue. Чтобы экспорт
      при этом их не терял, все четыре экспортёра рендерят тело главы через
      `exporters/_shared.py`'s `chapter_body_html()` — `content` + блок "Notes" (после `<hr />`)
      со сносками по порядку; `sizing.chapter_size()` тоже учитывает их байты/картинки.
    - `<li>` санитайзер по-прежнему выкидывает (текст оставляет) — распознаётся только
      li-сноска; общая проблема потери границ блоков у выброшенных тегов — отдельный issue #59,
      не решается здесь (решено позже, см. шаг 31).
    - Round-trip `Chapter.model_validate(chapter.model_dump())` сохраняет сноски (валидатор не
      перезаписывает уже переданный `footnotes` пустой повторной экстракцией).
    - `Footnote` ре-экспортирован из `ranobelib/__init__.py` — тот же принцип, что у
      `Genre`/`Country`: нужен вызывающему для аннотации `Chapter.footnotes`.
31. **Выброшенные блочные теги сохраняют границу абзаца** (issue #59, найдено компаньоном
    вместе с #58 — его workaround для `<ol>`-сносок, PR 242 в `ranobelib-companion`).
    - Санитайзер выкидывал любой тег вне словаря `p`/`img`/`strong`/`em`/`br`/`hr`, оставляя
      текст — для inline-обёрток (`a`, `span`) это правильно, а для блочных (`li`, `h3`, ...)
      текст оказывался голым вне `<p>` и слипался с соседями. Реально встречается (см.
      `docs/api-notes.md`): `h3` — заголовки разделов, `ol`/`li` — сноски (их уже забирал #58,
      но только как частный случай).
    - Исправление ровно как предложил issue: текст выброшенного блока оборачивается в `<p>` —
      тот же словарь, что уже выдаёт prosemirror-путь, публичный API не меняется. Список
      блочных тегов — стандартный HTML (`_DROPPED_BLOCK_TAGS`), а не только увиденные `h3`/
      `ol`/`li`: санитайзер существует ровно для непредсказуемой разметки, и "не угадывать"
      здесь значит не оставлять известный класс тегов с известным багом.
    - Вложенность: по одному `<p>` на каждый inline-участок между дочерними блоками (не
      `<p>` внутри `<p>`), блок внутри открытого `<p>` сначала закрывает его (как в HTML),
      `<hr />` внутри выброшенного блока — между абзацами, а не внутри. Заголовок становится
      обычным `<p>` — отдельный тег заголовка в словаре потребовал бы правок всех экспортёров,
      вне рамок issue.
    - Распознавание сносок (#58) перенесено с уровня "`p`/`li`" на уровень абзаца: любой
      абзац (явный `p` или собранный из текста выброшенного блока), начинающийся с `↑`.
    - Проверено на 263 реальных HTML-главах: меняются ровно 10 (с `h3`/`ol`), видимый текст
      и сноски до/после совпадают, голого текста вне `<p>` не осталось ни в одной.

32. **Проброс `headers=` через `RanobeLib`/`Catalog`** (после блока DDoS-Guard 2026-09-30 —
    см. "Что уже известно про API" выше и `docs/api-notes.md`, раздел "WAF 403").
    - До этого шага `headers=` был только у `ApiClient` (как и остальные его настройки, см.
      "Rate limiting и ошибки"), а фасады создавали `ApiClient()` без аргументов — пользователь
      SDK не мог сам подстроиться под смену правил DDoS-Guard, и подсказка
      `AccessBlockedError` отсылала к внутреннему классу. Теперь `RanobeLib(..., headers=...)`
      и `Catalog(headers=...)` передают их в `ApiClient`; семантика та же — мерж поверх
      `BROWSER_HEADERS` + `Site-Id`/`Accept`, ключ перекрывает дефолт без учёта регистра.
    - **Осознанное исключение из правила "настройки `ApiClient` не пробрасываются"**, только
      для `headers`: `timeout`/`base_url`/ретраи настраивают, *как* SDK общается с API, и у
      них рабочие дефолты; заголовки решают, *пустит ли* edge вообще — без проброса смена
      правил на стороне сайта ломает всех пользователей до следующего релиза. Остальные
      настройки `ApiClient` по-прежнему не пробрасываются.
    - Обложки качаются с `cover.cdnlibs.org` за тем же edge'ем, поэтому `RanobeLib.export()`
      передаёт те же `headers` экспортёру: протокол `Exporter.export()` получил необязательный
      `headers: Mapping[str, str] | None = None` (тем же способом, что `on_chapter` в шаге 23);
      epub/pdf мержат его поверх `BROWSER_HEADERS` (`_http.browser_headers()`), txt/fb2
      принимают и игнорируют. Сторонний экспортёр, написанный под старую сигнатуру, нужно
      дополнить этим параметром — `RanobeLib.export()` передаёт его всегда (как и
      `on_chapter`), без проверки сигнатуры экспортёра через `inspect`.

33. **Дата последней главы `Title.last_chapter_at`** (issue #67, снова `ranobelib-companion`
    — карточки каталога показывают «N гл. · обновлён <дата>»).
    - Проверено (см. `docs/api-notes.md`, раздел "Last chapter date"): у
      `GET /api/manga/{slug}` есть `fields[]=last_item_at` — совпадает до секунды с самым
      поздним `branches[].created_at` по всему списку глав (два тайтла) и с порядком
      `sort_by=last_chapter_at` в каталоге. `get_info()` его запрашивает, модель отдаёт как
      `Title.last_chapter_at: datetime | None` (`Field(alias="last_item_at")`, тот же
      паттерн, что `country`/`type`).
    - **Главную просьбу issue — поле на элементах `Catalog.list_titles()` — API не
      позволяет.** `GET /api/manga`, в отличие от эндпоинта тайтла, валидирует `fields[]`
      (422 на неизвестное значение); ни `last_item_at`, ни ~40 других кандидатов не прошли, а
      принятые (`metadata`, `created_at`, ...) даты последней главы не несут. Сам сайт в
      карточках каталога дату тоже не показывает. На элементах каталога поле остаётся `None`
      — задокументировано в докстринге поля и в `docs/api-notes.md`.
    - Сознательно **не сделано** (решение пользователя): дозапрос `last_item_at` для каждого
      элемента листинга (скрытый N+1, ~30 запросов на страницу, упор в rate limit) и обёртка
      над `GET /api/latest-updates` (там есть и `last_item_at`, и
      `metadata.latest_items.count` для бейджа «+N глав» из nice-to-have issue, но эндпоинт
      не фильтруется — это лента обновлений, не каталог). Оба — возможные будущие
      расширения, если появится юзкейс.
    - Добавление `last_item_at` в `_INFO_FIELDS` меняет кэш-ключ `get_info()` (в нём
      отсортированный список полей), так что старые записи дискового кэша просто не
      попадают — без ручной инвалидации.

34. **Список статусов и фильтр по нескольким статусам** (issue #68, снова
    `ranobelib-companion` — группа «Статус» с мультиселект-чипами в мобильных фильтрах
    каталога; номер 34, т.к. 33 занят `Title.last_chapter_at` из issue #67).
    - Проверено (см. `docs/api-notes.md`, раздел "Status list and multiple statuses"):
      `GET /api/constants?fields[]=status` — та же не заскоупленная по сайту форма с
      `site_ids`, что и `fields[]=genres`/`types`; 5 статусов, все для ranobelib (`1`
      "Онгоинг", `2` "Завершён", `3` "Анонс", `4` "Приостановлен", `5` "Выпуск прекращён"),
      лейблы совпадают с `Title.status`. Повторный `status[]` — **OR**, как `types[]`
      (`[1, 2]` → и онгоинги, и завершённые).
    - `Catalog.list_statuses(*, refresh=False) -> list[Label]` — та же модель, что
      `Title.status`, как и предлагал issue (отдельная модель "статус каталога" не
      заводится, тот же принцип, что `Genre` в шаге 25); фильтр по `site_ids`, содержащим
      `3`, тот же, что у `list_genres()`/`list_countries()` (сейчас ничего не отсекает, но
      эндпоинт не заскоуплен по сайту). Кэш — `DiskCache`, ключ `"catalog:statuses"`.
    - `status: int | None` заменён на `statuses: list[int] | None` целиком, без
      deprecated-алиаса, который предлагал issue — то же решение, что и `country` →
      `countries` в шаге 29 (проект не держит параллельные параметры ради обратной
      совместимости). Ломающее изменение публичного API — отметить в описании релиза.
    - `Label` ре-экспортирован из `ranobelib/__init__.py` и добавлен в `docs/reference.md` —
      тот же принцип, что у `Genre`/`Country`: нужен вызывающему для аннотации
      возвращаемого значения `list_statuses()`.

35. **Фильтр каталога по числу глав** (issue #69, снова `ranobelib-companion` — группа
    «Количество глав»: «от 100» / «от 500» / «от 1000» в мобильных фильтрах каталога).
    - Имена параметров не угаданы, а взяты из схемы фильтров каталога в JS-бандле самого
      сайта: `chap_count_min`/`chap_count_max`. Проверено на живом API (см.
      `docs/api-notes.md`, раздел "Chapter-count filter"): обе границы **включительные** и
      считают `items_count.uploaded` — то же число, что `Title.chapter_count`. Отрицательные и
      нецелые значения — 422.
    - `Catalog.list_titles(min_chapters=..., max_chapters=...)` — обе границы, как предлагал
      issue (верхняя "если API поддерживает" — поддерживает). `None` — без границы; обе
      участвуют в кэш-ключе.
    - **`min > max` API молча меняет местами**, а не отклоняет. SDK на это недокументированное
      поведение не полагается: `ValueError` до похода в сеть на `min > max` и на
      отрицательные значения — тот же принцип, что у `page`/`per_page` в шаге 24.

36. **`chapter_count`/`last_chapter_at` на элементах каталога — issue #74, НЕ реализовано,
    т.к. API этого не позволяет** (снова `ranobelib-companion`, карточки «N гл. · обновлён
    <дата>»). Шаг 33 уже показал, что `last_item_at` в листинге не получить. Issue #74
    попросил проверить ещё два места: запрос собственного каталога сайта и batch-эндпоинт.
    Проверено (см. `docs/api-notes.md`, подраздел "Chapter count on listing items"). Каталог
    сайта по JS-бандлу шлёт `GET /manga` только с `fields: ["rate", "rate_avg",
    "userBookmark"]`. Число глав сайт показывает лишь во всплывающей карточке, которая
    запрашивает каждый тайтл отдельно. `fields[]` с `chap_count`/`items_count` и ~15 похожих
    вариантов дают 422. Пакетного запроса нет: `ids[]`/`id[]`/`slugs[]` листинг
    игнорирует, а `latest-updates` не фильтруется. Изменена только документация
    (докстринг `Title.chapter_count` и `docs/api-notes.md`), поведение SDK то же. Отдельный
    `get_info()` на каждую карточку (N+1) issue отверг сам.

37. **Публичные хелперы для картинок главы** (issue #76, снова `ranobelib-companion` —
    офлайн-чтение в PWA: картинки глав нужно отдать через свой same-origin прокси и знать
    заранее, что кэшировать; cross-origin ответы service worker полезно сохранить не может).
    - Новый модуль `images.py`: `chapter_image_urls(chapter) -> list[str]` — все `<img src>`
      из `content`, затем из `footnotes`, в порядке документа, без повторов (первое
      вхождение); `rewrite_image_urls(chapter, replace) -> Chapter` — копия
      (`model_copy`, без повторной валидации — валидатор `Chapter` заново извлекал бы сноски)
      с каждым `src` в `content`/`footnotes`, пропущенным через `replace`, значение
      экранируется как атрибут. Оба кидают `ValueError` на `content is None`, как
      `chapter_size()`. Сигнатуры — ровно как в issue.
    - Парсинг не дублируется: приватный `_ImageSrcRewriter` в `exporters/_illustrations.py`
      обобщён с маппинга на функцию (`replace_image_srcs()`; `None` из функции — выбросить
      `<img>`), `rewrite_image_srcs()` для epub/pdf стал тонкой обёрткой над ним с прежним
      поведением. Перечисление — тот же `extract_image_urls()`, что у `chapter_size()`.
    - `replace` вызывается на каждый `<img>` (без кэширования по URL — дёшево и
      предсказуемо); `<img>` без `src` остаётся как есть, функция для него не вызывается.
    - Оба ре-экспортированы из `ranobelib/__init__.py` — тот же принцип, что
      `chapter_size`/`volume_size` (шаг 22): обычный юзкейс поверх скачанной главы.

38. **`chapter_paragraphs(chapter)` — текст блоков верхнего уровня, с DOM-индексами**
    (issue #77, снова `ranobelib-companion`: комментарии читалки привязаны к индексу абзаца
    — позиции среди `content.children` в браузере, и модерации в админке нужно показать
    текст этого абзаца).
    - Новый модуль `paragraphs.py`. Главное в контракте — индекс: запись *i* = *i*-й
      элемент верхнего уровня `Chapter.content`. Поэтому запись даёт **каждый** элемент
      верхнего уровня, включая `<hr />` и `<img>` (`""`, а не пропуск — иначе индексы
      поплывут относительно DOM). Голый текст вне элементов на верхнем уровне записью не
      считается (в DOM это текстовый узел, не элемент), как и просил issue.
    - Текст: сущности декодированы, пробелы схлопнуты, `<br />` внутри блока — разделитель
      слов. Сноски не входят — их и так нет в `content` (шаг 30).
    - Отдельный `HTMLParser`, считающий глубину, а не переиспользование
      санитайзера из `models.py`: `content` уже санитайзен, нужен лишь подсчёт элементов
      верхнего уровня. Контракт сверен с независимым парсером (`lxml.html`, дочерние
      элементы фрагмента + `text_content()`) на всех 80 главах из кассет — 0 расхождений.
    - `ValueError` на `content is None`, как у `chapter_size()`; ре-экспортирован из
      `ranobelib/__init__.py` по тому же принципу, что хелперы шага 37.

39. **Обслуживание дискового кэша: `cache_stats()` / `clear_cache()`** (issue #78, снова
    `ranobelib-companion` — экран «Система» в админке: размер `cache_dir` и кнопка «Очистить
    кеш SDK»; удалять файлы кэша самому компаньону запрещено — это хардкод внутреннего
    формата SDK на веб-слое).
    - Публичная форма — функции модуля `cache.py` (первый вариант из issue), ре-экспортированы
      из `ranobelib/__init__.py` вместе с `CacheStats` (frozen dataclass `entries`/`bytes`).
      Реализация — методы `DiskCache.stats()`/`DiskCache.clear()` (там же, где `_path_for`,
      т.е. знание о раскладке в одном месте), функции — тонкие обёртки; `DiskCache` по-прежнему
      не публичный, так что это не две параллельные публичные формы.
      `cache_dir` по умолчанию — `DEFAULT_CACHE_DIR`, тот же, что у `RanobeLib`/`Catalog`.
    - **Трогаются только файлы, которые пишет сам кэш**: обычный файл (не каталог/симлинк) с
      именем `<64 строчных hex>.json` (`_ENTRY_NAME`, ровно форма `_path_for`); остальное в
      каталоге, и сам каталог, не учитывается и не удаляется. Содержимое для отбора не
      читается — иначе `cache_stats()` читал бы весь кэш целиком.
    - Отсутствующий каталог (и путь, указывающий на файл) — пустой кэш, `CacheStats(0, 0)`.
    - Конкурентная безопасность: файл, исчезнувший между листингом и `stat`/`unlink`, и файл,
      который не удалить (на Windows — открыт другим процессом), молча пропускаются и не
      засчитываются; `get()` на удаляемый файл уже был промахом, `set()` после удаления просто
      пересоздаёт запись.
    - `older_than` (опция из issue) — та же проверка возраста, что у `ttl` в `get()` (удаляется
      строго старше `now - older_than`), читает `cached_at` из файла. Битая запись (не JSON,
      нет/нечисловой `cached_at`) при `older_than` тоже удаляется — `get()` её всё равно никогда
      не отдаст. Отрицательный `older_than` — `ValueError`.

40. **`Title.base_names` — названия без суффикса формата** (issue #79, снова
    `ranobelib-companion`: поиск аниме-адаптаций на AniLiberty по названию промахивается из-за
    «(Новелла)»/«(Novel)»; срезать суффикс на веб-слое — парсинг названий ranobelib, место
    ему в SDK).
    - `@property` на `Title` (не `computed_field`, чтобы не менять `model_dump()` и формат
      кэша): `rus_name`, `eng_name`, `name`, `other_names` по порядку, без суффикса, без
      пустых и дублей (первое вхождение). Исходные поля не меняются.
    - Список суффиксов не угадан, а собран с живого каталога: обход всех 24 658 тайтлов
      (`GET /api/manga`, 411 страниц) и подсчёт всех хвостов в скобках, плюс выборка
      `other_names` через `get_info()` (150 тайтлов). Цифры и разбор — `docs/api-notes.md`,
      раздел "Title names without the format suffix".
    - Правило — закрытый список слов формата (`novel`/`новелла` с вариантами `light`/`web`/
      `лайт`/`веб`/`вэб`, `ln`/`wn`/`лн`, `ranobe`/`ранобэ`, `web serial`, `quest`/`квест`)
      в `(...)`/`[...]` в самом конце строки, без учёта регистра; повторяется, пока
      срезается (бывают стопки `(LN) (Novel)`). Разделитель `,`/`:`/`/` перед суффиксом
      уходит вместе с ним, `-`/`–` — нет (обычно закрывает подзаголовок `-...-`).
    - Остальные хвосты в скобках сохраняются: год, `(18+)`, `(Фанфик)`, `(Oneshot)`,
      `(перезапуск)`, `[LitRPG]`, `[MTL]`, `(Печатная версия)`, франшизы — они отличают
      один тайтл от другого (фанфик с «(Фанфик)» не должен совпасть с аниме оригинала).
      Нормализация для сравнения (регистр, пунктуация, `×` → `x`) — не здесь, как и
      просил issue.

Каждый пункт — отдельная ветка/PR по правилам из раздела Git workflow.

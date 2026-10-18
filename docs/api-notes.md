# Notes on the undocumented ranobelib API

Living document of findings about the `api.cdnlibs.org` API, gathered by manual inspection
(browser devtools / network tab) before implementing the corresponding SDK feature. Update
this file as new endpoints or edge cases are investigated — see `CLAUDE.md` for the current
list of open questions.

## Confirmed

- Base URL: `https://api.cdnlibs.org/api`, no authorization required for public content —
  but a non-empty `Referer` is (see "WAF 403" below).
- `GET /api/manga/{slug}/chapters` returns the full chapter list (including fractional
  chapters) in a single response, keyed under `"data"`. No pagination observed so far on a
  308-chapter title.
- `GET /api/manga/{slug}?fields[]=...` returns title metadata; the full set of useful
  `fields[]` values has not been catalogued yet.

### Site scoping: `Site-Id` header

`api.cdnlibs.org` is shared across the whole lib.social network (mangalib, ranobelib,
hentailib, ...). Title-detail and chapter-list endpoints (`GET /api/manga/{slug_url}`,
`GET /api/manga/{slug_url}/chapters`) need a `Site-Id: 3` request header to scope the lookup
to ranobelib.me — `3` is the value found in `<html data-id="3">` on ranobelib.me pages.
Without this header (or with the wrong site id), a request for a real, existing title
returns **404** with the same generic body as an actually-missing title:

```json
{"data": {"toast": {"type": "silent", "message": "Not Found"}}}
```

i.e. a bare 404 from this API does not distinguish "wrong site" from "title doesn't exist" —
the SDK always sends the correct header, so in practice this collapses to `TitleNotFoundError`.

The `GET /api/manga` search/list endpoint uses a *different* mechanism: a `site_id[]=3` query
parameter instead of the header (e.g. `GET /api/manga?q=foo&site_id[]=3`).

### `Accept: application/json` is required for JSON error bodies

On error status codes (404 confirmed), the API serves an HTML SPA shell (the site's own
404 page) unless the request sends `Accept: application/json` — with that header it serves
the JSON error body shown above instead. Successful (2xx) responses are JSON either way. The
SDK client sends `Accept: application/json` on every request to avoid parsing HTML by
accident.

### WAF 403: a non-empty `Referer` is required (checked 2026-09-30)

`api.cdnlibs.org` and `cover.cdnlibs.org` sit behind DDoS-Guard (`Server: ddos-guard` on
every response). By 2026-09-30 its edge started rejecting the SDK's requests — which until
then sent only `Site-Id`/`Accept` and httpx's default `User-Agent: python-httpx/0.28.1` —
with a **403 HTML page**, on every endpoint, before the request reaches the API:

```
403 - Forbidden . That's an error.
Client does not have access rights to the content so server is rejecting to give proper
response. That's all we know.
```

This is not the API's own 403: that one is JSON (`{"message": "User is not logged in."}`,
see "Catalog listing/search" below) with `Content-Type: application/json`. The edge's 403 is
`Content-Type: text/html; charset=utf-8`, regardless of `Accept`.

Checked against the live API on 2026-09-30, same IP, on `GET /api/manga/{slug}` (`Site-Id:
3`), `GET /api/manga?site_id[]=3&q=dxd` and `GET /api/constants?fields[]=genres`:

| Headers on top of `Site-Id` + `Accept` | Result (all three endpoints) |
|---|---|
| none (the SDK's old behavior) | 403 HTML |
| `Origin: https://ranobelib.me` + `Referer: https://ranobelib.me/` | 200 JSON |
| iPhone Safari `User-Agent` only | 403 HTML |
| all three | 200 JSON |
| `Origin: https://ranobelib.me` only | 403 HTML |
| `Referer: https://ranobelib.me/` only | 200 JSON |
| `Referer: https://ranobelib.me` (no trailing `/`) only | 200 JSON |
| `Origin: https://example.com` only | 403 HTML |

Follow-up the same day (while reproducing `AccessBlockedError` for
`examples/11_error_handling.py`), `GET /api/manga/{slug}` only:

| Headers on top of `Site-Id` + `Accept` | Result |
|---|---|
| `Referer: https://example.com/` only | 200 JSON |
| `Referer: https://mangalib.me/` only | 200 JSON |
| `Referer: x` only | 200 JSON |
| `Origin: https://ranobelib.me` + `Referer: https://example.com/` + UA | 200 JSON |
| `Referer:` (empty value) only | 403 HTML |

So the filter only checks that a **non-empty `Referer` is present** — its value isn't
checked against ranobelib.me, or even for being a URL (the first round of checks above only
ever tried ranobelib.me values, so it wrongly read as "a ranobelib.me `Referer`";
corrected by the follow-up). `Origin` doesn't count, and `User-Agent` alone neither causes
nor fixes the block (no TLS/HTTP2 fingerprinting needed, at least as of this date). With all three headers,
`/chapters` and `/chapter` also return 200, and a missing chapter still returns the API's own
JSON 404, so error mapping is unaffected.

Images: a title cover on `cover.cdnlibs.org` returned the same 403 without headers and 200
with them (same rule: `Referer: x` and `Referer: https://example.com/` got 200 too) — which silently dropped covers from epub/pdf exports, since illustration
downloads are best-effort. An in-chapter image on `ranobelib.me/uploads/...` returned 200
either way (also behind `ddos-guard`, just not filtered by `Referer` at the time).

What the SDK sends as a result (`ranobelib/_http.py`'s `BROWSER_HEADERS`): `Origin`,
`Referer` (`https://ranobelib.me/`, trailing slash, as the browser sends it) and an iPhone
Safari `User-Agent`, taken from a real browser session on the site. Only *some* `Referer`
is needed today, but the site's own value is sent, alongside the other two, so the request
as a whole matches the site's own traffic rather than half-imitating it — a real browser
never sends a site `Referer` with a `python-httpx` UA, and a stricter future rule is likelier
to check for ranobelib.me than to reject it. They go on every `ApiClient` request and on
the epub/pdf exporters' image clients (the latter without `Site-Id`/`Accept`, which are
API-specific).

`headers=` on `RanobeLib`, `Catalog` (and the underlying `ApiClient`) merges extra headers
over these (a given key replaces the default, case-insensitively), so a caller can send what
the edge expects if its rules change again, without waiting for an SDK release.
`RanobeLib.export()` passes the same `headers` on to the exporter
(`Exporter.export(..., headers=...)`), so epub/pdf illustration downloads — cover.cdnlibs.org
sits behind the same edge — use them too. This is the one `ApiClient` setting the facades
forward: the others (`timeout`, `base_url`, retry/pacing, see "Rate limiting и retry") tune
*how* the SDK talks to the API and have working defaults, while headers decide *whether*
the edge lets the SDK talk to it at all — without a way to change them from the facades,
a rule change on the site's side would leave every SDK user stuck until the next release.

#### `AccessBlockedError` vs `AuthRequiredError`

`ApiClient` used to turn *any* 403 into `AuthRequiredError` ("Authorization required") — a
misleading hint when it's the edge, not the API, refusing the request. The two are now told
apart by the response's `Content-Type`: `application/json` (the API's own 403, e.g. `{"message":
"User is not logged in."}`) → `AuthRequiredError` as before; anything else, including a
missing `Content-Type` (the edge's HTML page) → `AccessBlockedError`. `Content-Type` rather
than the page's text ("That's an error."), since the wording of an edge's error page is the
likeliest thing about it to change, while "the API answers in JSON" is the API's contract
(see "`Accept: application/json` is required for JSON error bodies" above: with that header
sent, even the API's own error pages are JSON).

`AccessBlockedError` isn't retried (403 isn't in `ApiClient`'s retryable statuses, and
`download_title()`'s extra retry layer only rides out `RateLimitError`) — resending the same
request with the same headers gets the same answer. Inside `download_title()` it's still a
`RanobeLibError`, so it's wrapped in `DownloadTitleInterruptedError` with the chapters
already fetched, like any other mid-download failure.

Reproducible on demand — unlike `AuthRequiredError`, which needs a paywalled title — by
sending an empty `Referer`: `RanobeLib(..., headers={"Referer": ""})` (that's what
`examples/11_error_handling.py` does, against the live API).

### `get_info()` — verified `fields[]` list

Confirmed against a real title (`91443--new-hero-in-dxd`) with
`Site-Id: 3` + `Accept: application/json`:

```
GET /api/manga/{slug_url}?fields[]=background&fields[]=eng_name&fields[]=otherNames
    &fields[]=summary&fields[]=releaseDate&fields[]=genres&fields[]=tags&fields[]=teams
    &fields[]=authors&fields[]=artists&fields[]=chap_count&fields[]=last_item_at
```

Notes on individual fields, since the mapping from requested `fields[]` name to response key
is not always 1:1:

- `chap_count` does **not** add a `chap_count` key — it surfaces `items_count: {"uploaded":
  int, "total": int}` instead. `uploaded` is the actual number of published chapters; this is
  what the SDK's `Title.chapter_count` is populated from.
- `last_item_at` adds a `last_item_at` ISO timestamp — when the most recent chapter was
  published; the SDK's `Title.last_chapter_at`. See "Last chapter date" below for how it was
  verified and why the catalog listing can't provide it.
- `status_id` (not currently requested by the SDK) surfaces `scanlateStatus: {"id", "label"}`
  — the *translation* status (e.g. "Заброшен" / abandoned by the team), distinct from the
  title's own `status` field (e.g. "Онгоинг" / ongoing), which is present by default without
  requesting any extra fields.
- `summary` is prosemirror-doc JSON (`{"type": "doc", "content": [...]}`). The SDK flattens
  it to plain text by concatenating `text` leaves paragraph by paragraph — deliberately
  simpler than the chapter-content renderer below, since a title summary doesn't need
  bold/italic/images preserved the way chapter content does.
- Fields present without being requested: `id`, `name`, `rus_name`, `eng_name`, `model`,
  `slug`, `slug_url`, `cover`, `ageRestriction`, `site`, `type`, `is_licensed`,
  `content_marking`, `status`, `releaseDateString`.

### Last chapter date: `last_item_at` (issue #67, checked 2026-10-04)

Issue #67 asked for the date of a title's most recent chapter on `Title`, mainly for
`Catalog.list_titles()` items (catalog cards showing "обновлён <дата>").

- **Title endpoint — available.** `GET /api/manga/{slug_url}?fields[]=last_item_at` adds
  `last_item_at` (ISO timestamp, UTC). Not present by default. Checked that it's really the
  latest chapter's date: on `6712--high-school-dxd-novel` (308 chapters) and
  `91443--new-hero-in-dxd` (47 chapters) it equals the newest `branches[].created_at` across
  the title's whole `/chapters` list, to the second. It's also the value the catalog's
  `sort_by=last_chapter_at` orders by: the first six results of that sort, looked up one by
  one, came back in strictly descending `last_item_at` order. Requested by `get_info()`,
  surfaced as `Title.last_chapter_at`.
- **Catalog listing (`GET /api/manga`) — not available.** Unlike the title endpoint, the
  listing *validates* `fields[]`: an unknown value is a 422 (`"Выбранное значение для fields.0
  ошибочно."`, no list of allowed values). Rejected: `last_item_at`, `last_chapter_at`,
  `lastChapterAt`, `last_chapter`, `lastItemAt`, `last_item`, `updated_at`, `chap_count`,
  `items_count`, `chapters`, `latest_chapter`, `new_chapters`, `views`, and ~30 other
  guesses. Accepted, and none of them carry the date: `metadata` (only shiki/anilist sync
  timestamps, even with `sort_by=last_chapter_at`), `created_at` (the *title's* creation
  date), `releaseDate`, `moderated`, `rate`/`rate_avg`, `userBookmark`. The site's own
  catalog cards don't show a date either — its JS bundle only reads `last_item_at` in the
  home page's "latest updates" block.
- **`GET /api/latest-updates` — available, but not a catalog.** Items carry `last_item_at`,
  `items_count`, and `metadata.latest_items: {"count": N, "items": [...]}` — the site renders
  `count - 1` as "+ ещё N глав" (the "+N" badge the issue's nice-to-have asked about). It
  paginates (`page=2` gives different items) but ignores `genres[]`, `q`, `limit`,
  `per_page`, so it can't stand in for `list_titles()`. Not wrapped by the SDK.

So `Title.last_chapter_at` is filled in by `RanobeLib.get_info()` only, and stays `None` on
`Catalog.list_titles()` items. Fetching it per item (one title request per catalog row, ~30
per page) was considered and left out: a hidden N+1 on a listing call, with the rate limit
that comes with it, is a caller-visible cost the SDK shouldn't take on implicitly.

#### Chapter count on listing items: also not available (issue #74, checked 2026-10-04)

Issue #74 asked for `chapter_count` alongside `last_chapter_at` on `Catalog.list_titles()`
items, and named two places the probe above hadn't looked: whatever ranobelib.me's own
catalog page sends, and a batch endpoint. Both checked, and the answer is **no**: the listing
can't return either value.

- **The site's catalog request.** Read from the site's JS bundle (the store that loads the
  catalog grid): it calls `GET /manga` with the filter params plus exactly
  `fields: ["rate", "rate_avg", "userBookmark"]`, and nothing else. The site's catalog cards
  don't show a chapter count or a date. Where the site does show a chapter count for a
  catalog entry, in the hover popup, it fetches the title on its own
  (`GET /manga/{slug}` with `fields: ["genres", "tags", "releaseDate", "summary",
  "status_id", "chap_count"]`), one request per hovered card. So the site itself does
  per-title requests, on demand.
- **`fields[]` on the listing, re-probed.** `chap_count` (the name that gives `items_count` on
  the title endpoint), `items_count`, `itemsCount`, `chapters_count`, `chaptersCount`,
  `count_chapters`, `chap_count_uploaded`, `items_count_uploaded`, `uploaded`, `items`,
  `latest_items`, `last_items`, `stats`, `counters`, `info`, `status_id`, `type`, `format`
  all return 422. The accepted ones haven't changed (`metadata`, `moderated`, `created_at`,
  `releaseDate`, `rate`, `rate_avg`, `userBookmark`). None of them has a chapter count.
- **Batch lookup.** `GET /api/manga` ignores `ids[]`, `id[]`, and `slugs[]`: it returns the
  normal unfiltered page, so it can't be used to fetch "these 30 titles" in one request.
  `GET /api/latest-updates` does have `items_count` and `last_item_at` on every item, but it
  can't be filtered (see above). It's the home page's update feed, not something that covers
  an arbitrary catalog page.

`chapter_count` and `last_chapter_at` stay `None` on `Catalog.list_titles()` items. The only
way to get them for a catalog page is one `get_info()` per title, which is the N+1 that issue
#74 itself rules out.

### Title names without the format suffix (issue #79, checked 2026-10-18)

ranobelib.me appends a publication-format marker to titles' names: `Старшая школа D×D
(Новелла)`, `Haisukuru Di Di (Novel)`. `Title.base_names` removes it. To build the list of
markers from real data, I walked the whole catalog (`GET /api/manga`, `sort_by=created_at`,
411 pages, 24,658 titles) and counted every bracketed tail of `rus_name`, `eng_name` and
`name`:

- `(Новелла)` ends 11,648 `rus_name`s and `(Novel)` ends 10,870 `name`s. Those two are
  what the site appends itself.
- Next come `(LN)` (358 over the three fields), `(WN)` (149), then a long tail of spellings
  people typed by hand: `(Light Novel)`, `(Web Novel)`, `(webnovel)`, `(web-novel)`,
  `(Lite-Novel)`, `(Novella)`, `(Novell)`, `(Webnovela)`, `(новела)`, `(Лайт-новелла)`,
  `(Лайт Новелла)`, `(Веб-Новелла)`, `( веб - новелла)`, `(Вэб Новелла)`, `(ЛН)`, `(Ranobe)`,
  `(Ранобэ)`, `(web serial)`, `[quest]`, `[квест]`, `[ln]`, `[wn]`. Case and inner spaces
  vary.
- Markers can stack: `(LN) (Novel)`, `(WN) (Новелла)`, `(новелла) (Novel)`, `(Вэб Новелла)
  (WN)`. A separator is sometimes left in front of one (`Цитрусовый маг, (Новелла)`,
  `...Shuren: (Novel)`, `... / (Novel)`). A few names are only the marker (` (Новелла)`).
- Every other tail is part of telling one title from another, so it's kept: `(Oneshot)`,
  `(перезапуск)`/`(Remake)`, `(Фанфик)`/`(фф)`, `(18+)`, years (`(2013)`), `(Прототип)`,
  `(Печатная версия)`, `[LitRPG]`, `[MTL]`, franchise names (`(Star Wars)`, `(Гарри Поттер)`),
  `(#1)`/`(#2)`. Tails that mention a format word but aren't a bare marker are kept too:
  `(Gothic novel)`, `(Novel test)`, `(не Новелла)`, `[A Tower Climb Web Serial]`.

The rule is a closed list of format words inside `(...)` or `[...]` at the very end of the
name, repeated until none is left, together with any `,`/`:`/`/` and whitespace before it.
A `-`/`–` before the marker stays, because it usually closes a subtitle (`Devil May Cry 5
-Before the Nightmare- (Novel)`). Over the full catalog this changes 24,321 names, and no
bare format marker is left at the end of any of them.

`other_names` isn't in the listing. A random sample of 150 titles through `get_info()` (91
of them have `other_names`) had no bracketed tail in any of them: those are translations
and original-language names. The same rule is applied to them anyway, as the issue asks.

Normalizing names for comparison (case, punctuation, `×` → `x`) isn't done here. That
belongs to whatever matches two catalogs against each other.

### Title URL / slug format

A title URL like `https://ranobelib.me/ru/book/91443--new-hero-in-dxd` (locale prefix is
optional — `/book/91443--new-hero-in-dxd` also resolves) has the API's `slug_url`
(`{numeric_id}--{slug}`) as its last path segment. The SDK extracts this segment and uses it
directly as the path parameter for `/api/manga/{slug_url}` — no separate slug/id lookup step
needed.

### `number_secondary` is not a chapter-number fraction — it mirrors `volume`

CLAUDE.md's original notes guessed `number_secondary` was the fractional part of a chapter
number (e.g. `number_secondary: "5"` on a `number: "51"` chapter, read as chapter `"51.5"`).
Verified against three different titles totaling 667 chapters (`6712--high-school-dxd-novel`,
308 chapters, 25 volumes; `147836--o-moem-pererozdenii-v-bessmertnogo`, 84 chapters, 8
volumes, including fractional chapter numbers `"6.5"`/`"81.5"`; `11407--solo-leveling`, 275
chapters including 20 multi-team-branch chapters): **`number_secondary` equals `volume` in
every single case, zero exceptions.** The exact example the original guess was based on
(`volume: "5", number: "51", number_secondary: "5"`) fits this pattern too — it wasn't a
coincidental fraction, `number_secondary` was just echoing the volume.

The actual fractional part of a chapter number, when present, is already embedded directly
in the `number` field as a string (`"6.5"`, `"81.5"`, `"0.1"`) — there is no separate field
for it. This means the SDK's `get_chapter`/`get_chapters`/`get_translations` take `number:
str` as-is from the API instead of a separate `number_secondary` parameter; see CLAUDE.md's
"Публичный API" section for the corrected signatures (this was originally documented
differently, based on the wrong guess above, before `get_table_of_contents` was
implemented).

### Chapter content: endpoint, and two different content formats

```
GET /api/manga/{slug_url}/chapter?number={number}&volume={volume}&branch_id={branch_id}
```

`number`/`volume` match `CLAUDE.md`'s guessed pattern exactly (first try). `branch_id` is
optional; confirmed working against a title with two translation teams (`11407--solo-leveling`,
chapter `volume=1, number=0`, `branch_id=2251` vs `branch_id=635` returned that branch's own
`teams`). **Without `branch_id`, the API did not pick `branches[0]` from the chapter-list
response** — it returned the *older* of the two branches (created 2019 vs 2020). Default
branch selection is not simply "first in the list"; needs its own investigation before
implementing team selection / `MultipleTranslationsError` (roadmap step 9). 404 on an
unknown `number`/`volume` combination returns the same generic body as title-not-found.

The single-chapter response shape differs from a chapter's entry in the `/chapters` list:
no `index`/`item_number`/`branches_count`/`branches` — instead a singular `branch_id` and a
flat `teams` array (the teams for *that* branch specifically, can be empty even when the
chapter has a team in the list endpoint's `branches[].teams`). Extra fields not modeled:
`moderated`, `likes_count`, `is_liked`, `is_viewed`, `expired_type`, `expired_at`,
`publish_at`, `translation_quality_rating`, `bundle`, `manga_id`, `created_at`.

**Content is not always prosemirror-doc JSON**, despite CLAUDE.md's original suspicion
(reasonable at the time, based on `ranobelib-loader`'s upload format and `Title.summary`
being prosemirror). Sampled all 308 chapters of `6712--high-school-dxd-novel`'s `content`
field (some requests hit 429 partway through — sample is 273 successfully fetched chapters,
still large enough to be conclusive):

- **235 chapters (~86%): `content` is an HTML string**, e.g.
  `<p data-paragraph-index="1">text</p><p data-paragraph-index="2">text</p>`. Tags observed
  across samples from two titles: `p`, `img`, `em`, `strong`, `b`, `i` (inconsistent between
  `<em>/<strong>` and `<b>/<i>` for the same semantic meaning — presumably different editor
  versions over the site's history; both pairs occur, never mixed within one chapter in the
  samples checked). `data-paragraph-index` looks like a pure editor artifact, safe to ignore.
  Image `<img>` tags carry an already-absolute `src`, e.g.
  `<img loading="lazy" src="https://ranobelib.me/uploads/ranobe/{slug}/chapters/{chapter_id}/{filename}" />`.
- **38 chapters (~14%): `content` is prosemirror-doc JSON** (`{"type": "doc", "content":
  [...]}`), matching `Title.summary`'s format. Node types observed: `paragraph` (can have no
  `content` key at all for a blank line; can carry `attrs: {"textAlign": "center"}` — not
  currently reproduced in the SDK's HTML output, a known gap), `image` (block-level, sibling
  to paragraphs, not nested inside one), `hardBreak`, `horizontalRule`. Mark types on `text`
  nodes: `bold`, `italic`. No headings/lists/blockquotes observed in the sample.
- The `content` format is a **per-chapter** property, not per-title or per-team — seen both
  formats within the same title.

**Image resolution for the prosemirror format**: an `image` node doesn't carry a URL
directly, only an opaque id: `{"type": "image", "attrs": {"images": [{"image":
"9bb930b8-...-f717bf"}]}}`. The response's top-level `attachments` array resolves it — find
the entry whose `name` equals that id, then prepend `https://ranobelib.me` to its `url`
(relative, e.g. `/uploads/ranobe/{slug}/chapters/{chapter_id}/{filename}.{extension}`) to
get the same absolute URL shape the HTML-string format embeds directly. `attachments` is
empty (`[]`) for chapters with no images, present alongside either content format.

The SDK normalizes both formats into a single HTML fragment on `Chapter.content` — prosemirror
format: rendered with the restricted tag vocabulary (`<p>`, `<img loading="lazy" src="...">`,
`<strong>`, `<em>`, `<br />`, `<hr />`); string format: **sanitized down to that same
vocabulary**, not passed through as-is — the site's own markup isn't SDK-generated and can
carry tags/attributes outside it (`data-paragraph-index`, `b`/`i` instead of `strong`/`em`, or
worse, see the tag survey above). `b`/`i` are folded into `strong`/`em`; every other
unrecognized tag is dropped (its text kept, except inside `script`/`style`, which drop their
text too); every attribute is dropped except `img`'s `src`, and only when it resolves to an
`http(s)` URL.

**Dropped block-level tags keep their paragraph boundary (issue #59).** Dropping a tag but
keeping its text is fine for inline wrappers (`a`, `span`), but for a block wrapper it used
to remove the only boundary its text had: the text landed as bare text outside any `<p>`,
running into its neighbors. Block tags observed in the cached HTML-string chapters of
`6712--high-school-dxd-novel` (263 chapters): `h3` (13 section headings, e.g.
`<h3>Император</h3>`, in 5 chapters) and `ol`/`li` (footnote lists, 5 chapters) — no `div`,
`blockquote`, tables or other lists. The sanitizer handles the standard HTML block tags
anyway (`li`, `div`, `h1`–`h6`, `blockquote`, `section`, table cells, ... — see
`_DROPPED_BLOCK_TAGS`), since it exists to cope with markup it can't predict: a dropped
block's inline content is wrapped in `<p>`, one `<p>` per run of inline content between
nested blocks (`<div>a<p>b</p>c</div>` → `<p>a</p><p>b</p><p>c</p>`), whitespace-only runs
(the `\r\n\t` between `<li>`s) are dropped, and opening any block inside an open `<p>` closes
that `<p>` first, as HTML does. So `Chapter.content` is a flat sequence of `<p>`/`<hr />`/
`<img>` for block-structured input, same as the prosemirror path produces. A heading comes
out as a plain `<p>` (no heading tag in the vocabulary — adding one would be a separate
change to every exporter). Re-checked on the same 263 chapters: 10 change (exactly the
`h3`/`ol` ones), their visible text and footnotes are identical before/after, and none has
text left outside a `<p>`. So exporters only ever handle one shape *and* `Chapter.content` is safe to
render as raw HTML regardless of which format the API used for a given chapter — see
`_sanitize_content_html`/`_ContentSanitizer` in `models.py`.

### Translator footnotes (issue #58)

**The API has no structured footnotes.** Checked both content formats: 313 cached chapter
responses (308 of `6712--high-school-dxd-novel`, 5 of another title; 263 HTML-string, 50
prosemirror) plus ~45 live chapters from 12 recently updated titles (all prosemirror). The
prosemirror node types seen were only `doc`/`paragraph`/`text`/`hardBreak`/`heading`/`image`/
`horizontalRule`, marks only `bold`/`italic` — no footnote node, mark or attribute. The
HTML-string chapters carry no `<sup>`, `id`/`href` anchors or classes either. A footnote is
just translator-typed text, in (at least) these shapes, all seen within the one DxD title:

1. **`↑`-prefixed blocks** — `<p>↑&nbsp;text</p>` one per footnote, or an
   `<ol><li>&uarr;&nbsp;text</li>…</ol>` list (older chapters). All 10 chapters of the
   cached sample that contain a `↑` use it this way: 42 `↑` in total, every one at the start
   of a block, none anywhere else in the text. In all 10 the footnotes are a contiguous run
   at the very end of the chapter.
2. **Numbered asterisks** — `word*1` in the text, a trailing `<p>1*text</p>` per note.
3. **A "Заметки переводчика" heading paragraph** followed by `<p>[1] text</p>` items, with
   `word [1]` in the text.

**What the SDK detects: only shape 1.** A paragraph — `p`, or one made from a dropped
block's text such as `li` (HTML-string, see above), or `paragraph` (prosemirror) — whose
first non-blank text starts with `↑` is moved out of `Chapter.content`
into `Chapter.footnotes` (`Footnote.content`: sanitized inline HTML, arrow and following
whitespace stripped, no wrapping `<p>`). `↑` is distinctive enough to be unambiguous in the
sample; shapes 2 and 3 aren't — `[1]`, `1*` and a "notes" heading are ordinary text too, and
guessing wrong would silently delete story text from `content`. They stay in `content` as
before; recognizing them is a possible future extension if it turns out to matter.

**No marker/back-reference.** The issue's proposed `Footnote.marker` isn't there because the
data has nothing to fill it with: in shape 1 the reference point in the text is a bare,
unnumbered `*` after a word (count matches the footnote count in the chapters checked), but
the same text also uses `*` for `***` scene breaks, `*action*` emphasis and censored digits
(`32****8517`) — 416 paragraphs with a `*` right after a non-space character across the
cached chapters, vs 42 footnotes. The order of `Chapter.footnotes` (source order) is the only link available.

Exporters list a chapter's footnotes after its text under a "Notes" heading
(`exporters/_shared.py`'s `chapter_body_html`), so moving them out of `content` doesn't drop
them from exported files; `sizing.chapter_size()` counts them too.

### No bulk "volume content" endpoint

Checked for a shortcut before implementing `get_volume()` (fetch a whole volume's chapters
in fewer requests than one-per-chapter): `GET /api/manga/{slug}/volume?volume=1`,
`GET /api/manga/{slug}/volumes` both 404. `GET /api/manga/{slug}/chapter?volume=1` (omitting
`number`) returns **422** with `{"data": {"number": ["Поле number обязательно для
заполнения."]}}` — `number` is a required parameter, confirming there's no way to fetch a
volume's chapters in one call. `get_volume()` fetches the chapter list once (to find which
numbers belong to the requested volume), then fetches each of those chapters individually,
same as calling `get_chapter()` in a loop. Sequential, not concurrent — no rate-limit/retry
handling exists yet (roadmap step 11), so no concurrency control to bound it either.

### Translation selection: `branch_id`, not `team_id`, and no reliable default

Researched before implementing `get_translations()`/`MultipleTranslationsError`/`branch_id`
(roadmap step 9), against `11407--solo-leveling`, which has 20 chapters with two competing
translations (out of 275 total). Example: `volume=1, number=0` has two `branches` entries
in the `/chapters` list response:

```json
{"id": 933688, "branch_id": 2251, "created_at": "2020-10-02...", "teams": [{"id": 13375, "name": "BerkuD13", ...}], "user": {"username": "Birdzz", "id": 1171713}}
{"id": 269251, "branch_id": 635,  "created_at": "2019-04-11...", "teams": [], "user": {"username": "ItsEND", "id": 24545}}
```

Two things this confirms, both contradicting CLAUDE.md's original guess (the public API
sketch used a `team_id` parameter, assumed equal to a `Team.id`):

- **The selector the `/chapter` endpoint actually accepts is `branch_id`, not a team id.**
  `branch_id` (`2251`/`635` above) is a stable id for a *translation line*, distinct from
  both the branch entry's own `id` (a per-chapter-revision id, different on every chapter)
  and `Team.id` (`13375` for BerkuD13). It doesn't always correspond to a team at all — the
  second branch above has `"teams": []` (an uploader with no team credit), so a `team_id`
  parameter couldn't even address it. The SDK's public API is corrected to use `branch_id`
  throughout (`get_chapter(..., branch_id=...)`), same kind of correction as
  `number_secondary` earlier in this file.
- **The API's own default (`branch_id` omitted) is not "the first branch listed."**
  Confirmed by requesting `volume=1, number=0` three ways:

  | `branch_id` param | response `branch_id` | response `teams` |
  |---|---|---|
  | *(omitted)* | `635` | `[]` |
  | `2251` | `2251` | `[{"name": "BerkuD13", ...}]` |
  | `635` | `635` | `[]` |

  Omitting `branch_id` returned `635` (branches[1], the *older* upload, 2019 vs 2020) — not
  `branches[0]` (`2251`). The single-chapter response also carries no `branches`/
  `branches_count` field to detect ambiguity after the fact (see the chapter-content section
  above for its full shape) — the only way to know a chapter has more than one translation
  is to check the `/chapters` list first.

**Design decision** (CLAUDE.md's ТЗ explicitly leaves this choice to be made and documented
here): since the API's own default isn't documented and the one example checked doesn't fit
any obvious rule ("first in list", "newest", "has a credited team" all fail here), the SDK
does not attempt to replicate or guess it. `get_chapter()` (and, since they build on it,
`get_chapters()`/`get_volume()`/`get_volumes()`) raises `MultipleTranslationsError` when a
chapter has more than one branch and `branch_id` wasn't given, instead of silently returning
whichever one the API happens to default to. Callers use `get_translations()` to list the
options and pick one explicitly.

Cost of this: `get_chapter()` without an explicit `branch_id` now fetches the full
`/chapters` list first (to check for ambiguity) before fetching the chapter itself — one
extra request it didn't need before this feature, only when `branch_id` isn't already known.
`get_chapters()`/`get_volume()`/`get_volumes()` already fetched that list for other reasons,
so they get the ambiguity check for free. This cost is expected to shrink once the disk
cache (roadmap step 10) makes repeated `/chapters` fetches for the same title free.

`get_volume()`/`get_volumes()`/`get_chapters()` do not expose a way to pick a specific
`branch_id` per chapter when fetching in bulk (their signatures don't have room for a
per-chapter override) — they only raise if any chapter they touch turns out to be ambiguous.
`get_chapter(..., branch_id=...)` already covers the single-chapter case the public API's
quickstart shows it for.

Title-wide bulk download (`download_title()`, roadmap step 20) needed a real answer to this
rather than "future enhancement" — it can hit many ambiguous chapters across a whole title,
and stopping at the first one (like `get_volume()` does) would mean fixing one, rerunning,
hitting the next, rerunning again. It resolves this two ways instead, both optional and
mutually exclusive: `branch_id` (same `branch_id` applied wherever a chapter has it —
meaningful because `branch_id` is a stable translation-line id, not a per-chapter revision
id, see above) or `translation_index` (position in each ambiguous chapter's `branches` list —
a fallback for when the same team doesn't share one `branch_id` across every chapter, or
doesn't appear on every chapter at all). Without either, or when the given one doesn't
resolve every ambiguous chapter, it raises `MultipleTitleTranslationsError` listing *all*
unresolved chapters at once (checked up front, not one failure at a time) — same "don't
guess" principle as `MultipleTranslationsError`, just batched for the bulk case.

### Rate limiting и retry: ручная реализация вместо `tenacity`

Роадмап (шаг 11) явно оставлял выбор между `tenacity` и ручной реализацией на усмотрение
PR, с требованием задокументировать решение — вот оно.

**Выбор: ручная реализация**, без новой зависимости. Причины:

- Вся нужная логика — семафор на конкурентность, пейсинг между стартами запросов и
  экспоненциальный backoff с уважением `Retry-After` — укладывается в три небольших метода
  `ApiClient._get`/`_pace`/`_backoff_delay` (~30 строк). `tenacity` избавила бы от написания
  цикла retry, но для остального (семафор, пейсинг, разбор `Retry-After`) всё равно нужен
  свой код — выигрыш от зависимости небольшой.
- Тестируемость без реального ожидания: `sleep`/`clock` — параметры конструктора
  `ApiClient` (по умолчанию `asyncio.sleep`/`time.monotonic`), тесты подменяют их на
  fake/recording-реализации и проверяют backoff/пейсинг мгновенно и детерминированно
  (`tests/unit/test_client.py`), без монки патчинга `asyncio.sleep` глобально (что сломало
  бы не связанные с этим тесты, использующие реальный `asyncio.sleep` для координации).
- Ни одна из существующих кассет VCR не воспроизводит 429/5xx подряд, так что интеграционным
  тестам retry не нужен — юнит-тесты полностью покрывают эту логику через `httpx.MockTransport`.

**Реализация** (`ApiClient`, все параметры — только на уровне клиента, не пробрасываются
через `RanobeLib`, аналогично `timeout`/`base_url`; единственное исключение среди настроек
`ApiClient` — `headers`, см. раздел "WAF 403" выше):

- `max_concurrency=5` — `asyncio.Semaphore`, оборачивает сам HTTP-запрос (не время
  ожидания backoff между попытками — семафор освобождается на время сна между ретраями,
  чтобы долгий backoff одного запроса не блокировал слот для других).
- `request_delay=0.2s` (`DEFAULT_REQUEST_DELAY` в `client.py`, дефолт можно переопределить
  через `None`-сентинел в конструкторе) — минимальный интервал между стартами запросов,
  даже при `max_concurrency > 1`; применяется на каждую попытку, включая ретраи.
- `max_retries=3`, `retry_base_delay=1.0s`, экспонента ×2 за попытку (1s → 2s → 4s). На 429
  сначала проверяется `Retry-After` (секунды); если заголовок есть и парсится — используется
  он вместо экспоненты; если отсутствует или не парсится — обычный экспоненциальный backoff.
- После исчерпания ретраев `_raise_for_status` работает как раньше (немедленно на первом
  вызове до этой фичи): `RateLimitError`/`RanobeLibError` на итоговый ответ.

Тестовый набор целиком глушит `request_delay` (через `ranobelib.client.DEFAULT_REQUEST_DELAY`,
monkeypatch в `tests/conftest.py`) — `RanobeLib` не даёт способа передать `request_delay`
per-instance, а без этого тесты вроде `get_volume()` на реальном тайтле с полусотней глав
реально ждали бы ~10 секунд ради поведения, которое `test_client.py` и так проверяет точно
и без ожидания через инъекцию fake `sleep`/`clock`.

#### Пейсинг общий на хост, а не на клиент (`libsocial-core`, issue #87)

`api.cdnlibs.org` один на всю сеть lib.social. Считает ли он rate limit отдельно по сайтам, не
проверялось, и оснований так считать нет. Поэтому в ядре (`packages/core`, `libsocial.pacing`) пейсинг вынесен из
`ApiClient` в `Pacer`, и по умолчанию все `ApiClient` процесса, которые ходят на один хост,
делят один `Pacer` (`shared_pacer(host)`). Два клиента для разных сайтов в одном процессе
(ranobelib и mangalib) вместе шлют запросы не чаще одного клиента, а не вдвое чаще.
Семафор `max_concurrency` и ретраи остаются у каждого клиента свои: общим сделан только
интервал между стартами запросов, о котором и шла речь в issue.

- Слоты резервируются, а не ждутся под замком: вызывающий под `threading.Lock` (без `await`
  внутри) берёт следующий свободный момент старта и сдвигает его на свой `request_delay`,
  потом спит уже вне замка. Поэтому один `Pacer` можно делить между event loop'ами и потоками
  (`asyncio.Lock` привязывается к loop'у, который первым его использовал, и в другом
  `asyncio.run()` падает). Каждый вызывающий резервирует свою задержку, так что клиенты с
  разным `request_delay` могут делить один пейсер.
- `ApiClient(pacer=...)`: свой `Pacer` (например, с fake-часами в тестах) или отдельный,
  чтобы не делить общий. Параметр `clock` переехал из `ApiClient` в `Pacer`, потому что
  часы нужны только пейсингу.
- Проверено вживую (2026-10-18): `Catalog` ядра для site 3 и site 1 в одном процессе получают
  один и тот же объект `Pacer`, и оба листинга отвечают нормально.

С шага 3 монорепозитория (#88) `ranobelib` работает на ядре: `ranobelib.client.ApiClient` —
наследник `libsocial.ApiClient` с зашитым сайтом, так что общий пейсер по умолчанию теперь
и у `RanobeLib`/`Catalog`. Параметр `clock=` у `ranobelib.client.ApiClient` остался:
переданный, он даёт клиенту собственный `Pacer` на этих часах вместо общего.

#### `download_title()` outliving `ApiClient`'s per-request retry budget (issue #41)

Reported against a real 3932-chapter title (`17435--fan-ren-xiu-xian-chuan`): sustained
sequential fetching by `download_title()` reliably trips the API's own 429 around chapter
~217, well before `ApiClient`'s retry budget was ever meant to cover — `max_retries=3`/
`retry_base_delay=1.0s` (~1s/2s/4s, ~7s total) is tuned for one request tolerating a
transient blip, not a download that's already been running for tens of seconds to minutes.
Once that budget is exhausted, the `RateLimitError` used to propagate straight out of
`download_title()`, discarding every chapter fetched so far — they only ever lived in a
local list, never returned to the caller on failure.

**Fix, two parts, both in `sdk.py` (not `ApiClient` — this is a bulk-operation-specific
concern layered on top, not a change to the per-request retry policy every other method
also relies on):**

1. `RanobeLib._fetch_chapter_riding_out_rate_limits()` wraps `_fetch_chapter()` for
   `download_title()`'s loop: on a `RateLimitError` that already survived `ApiClient`'s own
   retries, wait and try again — honoring `Retry-After` if the API sent one, otherwise capped
   exponential backoff (`_RATE_LIMIT_RETRY_BASE_DELAY=5.0s`, doubling, capped at
   `_RATE_LIMIT_RETRY_MAX_DELAY=60.0s`) — up to a new `max_rate_limit_retries` parameter on
   `download_title()` (default `DEFAULT_RATE_LIMIT_RETRIES=6`; `0` disables this extra layer
   entirely). These numbers are a judgment call, not measured against the live API's actual
   rate-limit window (undocumented, see the rest of this file's running theme) — generous
   enough to ride out a temporary throttling window without an unbounded/indefinite retry
   loop that could hang forever on a title the API has decided to block outright.
2. If a chapter fetch still fails after that (rate limiting past the ceiling above, or any
   other `RanobeLibError` — e.g. a chapter unexpectedly requiring auth mid-download), the
   chapters already fetched are no longer thrown away: `download_title()` catches it and
   raises `DownloadTitleInterruptedError` instead, carrying `.volumes` (what was already
   downloaded, grouped exactly like a successful return), `.completed`, `.total`, and the
   original error as `__cause__`. A caller can keep the partial result, or just call
   `download_title()` again — the disk cache (see "Кэширование" in CLAUDE.md) means
   already-fetched chapters aren't re-requested, so a retry resumes rather than restarts.
   This is the same pattern `ranobelib-companion` was already doing *outside* the SDK as a
   workaround (catch `RateLimitError`, back off, call `download_title()` again, rely on the
   cache) — issue #41 asked for it to move inside the SDK so every caller gets it for free,
   not just that one.

Not extended to `get_chapters()`/`get_volume()`/`get_volumes()`/`estimate_title_size()` in
this fix — the reported failure and this issue's reproduction are specifically about
`download_title()` (the one bulk method whose whole point is walking *every* chapter of a
long title sequentially in one call, so it's the one that actually reaches the chapter
counts where this bites); the other bulk methods take an explicit, caller-provided list of
chapters/volumes to fetch, which for the same underlying reason (this is a "how many
requests can this one call make in a row" problem) rarely gets anywhere near that many in
practice. Same retry-layer/partial-progress mechanism if one of them turns out to need it —
left as a follow-up, not guessed at speculatively here.

Unit-tested in `tests/unit/test_sdk.py` (`test_download_title_*rate_limit*`,
`test_download_title_raises_interrupted_error_with_partial_progress`) via the same
`monkeypatch(lib, "_fetch_chapter", ...)` pattern `estimate_title_size()`'s tests already
use, not VCR — same reasoning as `ApiClient`'s own retry tests above: no existing cassette
reproduces sustained 429s, and a fake `_fetch_chapter` exercises the retry/give-up logic
exactly without needing one.

### PDF export: WeasyPrint needs native libraries at *import* time, not just install time

Discovered while implementing the pdf exporter (roadmap step 15), on this repo's Windows
dev environment: `uv add weasyprint` installs cleanly (pure wheel, no build step) on any
platform, but `import weasyprint` itself raises `OSError: cannot load library
'libgobject-2.0-0'` unless the GTK3 runtime (Pango/cairo/gobject, which WeasyPrint uses for
text shaping) is present on the system. This is different from every other dependency this
project has added — `pip install` succeeding doesn't mean the package actually works.

**Consequence for `import ranobelib`:** `exporters/__init__.py` eagerly auto-imports every
module in the package (see "Экспорт" in CLAUDE.md) to run each exporter's `@register`. If
`pdf.py` did a plain top-level `import weasyprint`, that OSError would propagate straight
through the auto-import loop and crash `import ranobelib` itself on any system without
GTK3 — not just "pdf export doesn't work", the whole SDK would be unusable.

**Fix**: `pdf.py` wraps its own `import weasyprint` in `try/except (ImportError, OSError)`;
on failure it sets `weasyprint = None` and skips defining `PdfExporter` entirely (the
`@register` line lives inside `if weasyprint is not None:`). `import ranobelib` then always
succeeds, `EXPORTERS` just doesn't have a `"pdf"` key, and `RanobeLib.export(fmt="pdf")` on
such a system raises the same `ValueError: Unknown export format 'pdf'. Available: ...` it
would for any other unregistered format — no new exception type needed, and the message
already tells the caller what *is* available.

**Testing implication**: `tests/unit/test_pdf_exporter.py`'s WeasyPrint-dependent tests
(`pytest.mark.skipif(weasyprint is None, ...)`) skip rather than fail on machines without
the native deps — this repo's Windows dev environment among them. `ci.yml`'s `test` job
installs `libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf2.0-0 libcairo2` via `apt-get`
before running pytest so they actually execute there instead of silently always skipping.
No VCR-backed integration test for `fmt="pdf"` exists (unlike txt/fb2/epub) for the same
root cause: recording its cassette needs a real WeasyPrint run to make the real HTTP calls
worth capturing, which isn't possible in this dev environment, and CI runs with
`--record-mode=none` so it can't record one either — see tests/integration/test_export.py's
module docstring. The unit tests (mock transport, no cassette needed) cover the same
download-then-render pipeline instead.

### Catalog listing/search: `GET /api/manga`

Researched for issue #38 (companion web UI needs catalog browsing without scraping HTML) —
the existing "Site scoping" section above already noted this endpoint uses a `site_id[]=3`
query parameter rather than the `Site-Id` header, and that's confirmed still true; everything
else below is new. Checked with real `curl` requests against the live API (no test title
needed — this endpoint lists/searches across the whole site).

**Pagination — `page`/`limit`, not `page`/`per_page`:**

```
GET /api/manga?site_id[]=3&page=1&limit=30
```

- `limit` controls page size, but only within **`10..60` inclusive** — `9` or `61` both
  return **422** (`"Поле limit должно быть между 10 и 60."`). Omitting `limit` defaults to
  `60`, not some smaller number.
- `page` must be `>= 1` — `0`/negative both 422 (`"Поле page должно быть не менее 1."`).
- Response shape: `{"data": [...], "links": {...}, "meta": {...}}` — unlike every other
  endpoint in this SDK, the top-level object isn't just `{"data": ...}`, callers need `meta`
  too.
- `meta.has_next_page` (bool) is exactly the "indicate whether more results exist" signal the
  issue asked for — no need to compute it from a total count, and in fact **there is no total
  count anywhere in the response** (no `meta.total`/`meta.last_page`). A page past the end
  returns **200** with `"data": []` and `has_next_page: false`, not 404.
- `meta.seed` is present on every response but turned out to be informational/unrelated to
  requesting a specific page reliably — see "`sort_by=random`" below for the parameter that
  actually matters for that.

**Search — `q`:**

`q=<text>` does a free-text search (matches on `name`/`rus_name`/`eng_name`, empirically).
No separate "search" endpoint — same `GET /api/manga` as browsing, `q` is just another filter.

**Genre filter — `genres[]`, AND semantics:**

`genres[]=<id>` (repeatable) filters to titles having *all* given genre ids, not any of them
— confirmed by combining a real genre id with a nonexistent one (`genres[]=34&genres[]=999999`
→ 0 results, not the same non-zero count as `genres[]=34` alone; an OR filter would still have
matched on the real id). Unknown genre ids don't error (no whitelist validation) — they just
never match anything, so the SDK doesn't need to fetch/validate against a genre catalog at
all, which is convenient because there isn't a public way to do that (see below).

There's no way to list genre ids/names via `GET /api/genres` or `GET /api/manga/genres` —
both respond **403 `{"message": "User is not logged in."}`**, a different error shape than
every other 403 this SDK has seen (`AuthRequiredError`'s shape assumes the `/manga/...`
family's JSON body). A working, unauthenticated endpoint was found (issue #44):

```
GET /api/constants?fields[]=genres
```

`Accept: application/json` still required (same as everywhere else — no `Site-Id`
requirement here though, see below), no auth needed, 200 with
`{"data": {"genres": [...]}}`. Each element:

```json
{
  "id": 34,
  "name": "Боевик",
  "alt_name": [],
  "dsc": "",
  "adult": false,
  "alert": false,
  "site_ids": [1, 2, 3, 4, 5],
  "blocked_for_country": [],
  "allowed_for_country": [],
  "allowed_for_domain": [],
  "anilist_id": null,
  "shiki_id": null,
  "mal_id": null,
  "is_media_spoiler": null,
  "is_general_spoiler": null
}
```

55 genres total as of this writing. `id`/`name`/`adult` map directly onto the existing
`Genre` model (`Title.genres`'s element type, reused per the issue's ask — no separate
"catalog genre" model). **`site_ids` isn't site-scoped by any request parameter** — a
`Site-Id: 3` header (or omitting it) makes no difference to which genres come back, unlike
every other endpoint that header matters for; the response always contains genres for the
whole lib.social network at once, and callers must filter by `site_ids` themselves.
54 of the 55 genres include `3` (ranobelib.me) in `site_ids`; the one exception is id `88`
("Детское"), tagged `site_ids: [5]` only. `Catalog.list_genres()` filters to `site_ids`
containing `3` before returning, so a ranobelib-scoped caller never sees a genre that
couldn't possibly match any ranobelib title — see `catalog.py`'s `_build_genres()`.

`GET /api/constants` also exposes other `fields[]` values unrelated to this issue (found
while probing, not otherwise used by this SDK): `tags`, `status`, `types`,
`imageServers` — each 403-free the same way `genres` is. Not investigated further; noted
here in case a future feature needs one of them (same "don't guess, check first" principle
as this whole section). (`types` was picked up later for issue #48, see "Country/origin
filter" below, and `status` for issue #68, see "Status filter" below; `tags` still isn't used for anything beyond the filter parameter itself, see
next.)

**Tag filter — `tags[]`, AND semantics, same as genres (issue #50):**

Issue #50 (companion app wants each tag badge on a title page to link to the catalog
pre-filtered to that tag, same as genre badges already do with `genres=[...]`) asked
whether the API supports filtering by tag id at all, and if so whether the match is AND or
OR — tags being more numerous/specific than genres made OR seem plausible as the more
useful default even at the cost of inconsistency with `genres`. Checked directly:

- `tags[]=<id>` is a real, working filter — confirmed by checking that a title present in
  `tags[]=218` results (id `129971`, "Immortal Drunkard") actually has tag id `218`
  ("Боги") in its own `fields[]=tags` response.
- It's **AND, not OR — same semantics as `genres[]`, contradicting the issue's OR guess**.
  Same test methodology as the genre AND confirmation above: combining a real tag id with a
  nonexistent one (`tags[]=218&tags[]=999999`) returns **0 results**, not the same non-zero
  count as `tags[]=218` alone — an OR filter would still have matched on the real id.
- Unknown tag ids don't error (`tags[]=999999` alone → 200, `"data": []`, not a 422) — no
  server-side whitelist, same as `genres[]` and unlike `status[]`/`types[]`. This SDK
  doesn't validate `tags` against a tag catalog before sending, same reasoning as `genres`.
- Not investigated as part of this issue (out of scope — the issue only asked for the
  filter, not a listing endpoint): whether `GET /api/constants?fields[]=tags` (noted as
  present but unexplored above) would support a future `Catalog.list_tags()` the way
  `fields[]=genres`/`fields[]=types` do for genres/countries. Unlike those two, this issue's
  actual use case (companion linking a tag badge already rendered from `Title.tags`) never
  needs a tag id → name lookup independent of a specific title, so no `list_tags()` was
  added here.

**Author/artist/team filter — not supported by the API at all (issue #51, not implemented):**

Issue #51 proposed `author_id`/`artist_id`/`team_id` single-value filters on `list_titles()`
(`Person.id`/`Person.id`/`Team.id` from `Title.authors`/`Title.artists`/`Title.teams`), the
same shape as `status`, and explicitly flagged as an open question whether the API supports
this at all — same caveat issue #50 raised for tags, which turned out to be unfounded there
(tags *are* filterable). For author/artist/team, extensive checking against the live API
found no supported mechanism whatsoever:

- Brute-forced ~25 plausible `GET /api/manga` query parameter names against a real title's
  known author id (`57847`, "kingCH") and team id (`23286`, "Stixs TEAM") — snake_case and
  camelCase singular/plural variants (`author_id`, `authors[]`, `author_ids[]`, `people[]`,
  `people_ids[]`, `artist_id`, `artists_id[]`, `team_id`, `teams[]`, `translator_id`,
  `translators[]`, `user_id`, `creator_id`, `publisher_id`, `franchise_id`, `authorId`,
  `teamId`, `author_slug`, `team_slug`, ...), plus a Laravel-style bracket-filter guess
  (`filter[author_id]=...`, checked with `curl -g` to rule out shell/URL-globbing false
  positives). Every single one returned **the exact same result set as no filter at all** —
  silently ignored, not a 422 (this API generally doesn't reject unknown query parameters,
  so silence here isn't as strong a signal as `genres[]`/`tags[]`'s AND-semantics tests, but
  combined with the points below it's conclusive enough not to guess further).
- No dedicated "titles by this person/team" sub-endpoint exists either:
  `GET /api/people/{slug_url}/manga`, `.../titles`, `GET /api/teams/{slug_url}/manga`,
  `.../titles` are all **404**.
- `GET /api/people/{slug_url}` (a real, working, unauthenticated endpoint — returns id,
  name, avatar, `titles_count_details` per site id, subscriber stats) doesn't expose an
  actual title list through any `fields[]` value tried (`manga`, `titles`, `works`,
  `franchise`) — response shape is identical regardless, and even a clearly-bogus
  `fields[]` value doesn't error the way it does on `/api/manga/{slug}` (`{"fields.0":
  [...]}`), suggesting `fields[]` isn't wired up for this endpoint at all, not just missing
  these particular values.
- Checked whether the free-text `q` search (documented above as matching
  name/rus_name/eng_name) incidentally matches author name as a fallback: `q=kingCH`
  (the exact name of a real credited author) returns **0 results**, even though that
  author has exactly one real title on ranobelib.me. So there's no id-based *or*
  name-based way to search/filter the catalog by author/artist/team through this API.

**Conclusion: not implemented.** Adding `author_id`/`artist_id`/`team_id` parameters that
silently do nothing (since nothing on the wire would ever narrow results) would be worse
than not having them — a filter that looks like it works but doesn't is actively misleading,
unlike e.g. `genres`/`tags`/`country`, which are all confirmed-working real filters. If the
API adds this capability later, or a working parameter name surfaces from a source other
than guessing (e.g. observing the real ranobelib.me frontend's own network requests), this
can be revisited then — not before.

**Status filter — `status[]`, not `status`:**

`status=1` (scalar) is **422** (`"Поле status должно быть массивом."` — must be an array),
confirming the real param is `status[]=1`. Values are `Title.status.id`s — confirmed by
requesting `status[]=1` and checking every returned item's `status.id == 1`. Observed ids in
the wild: `1` ("В процессе"/ongoing), `2` ("Завершён"/completed), `4`, `5` (labels not fully
sampled). Same as genres, an unrecognized id (`status[]=99`) is **422** here though (`"The
selected status.0 is invalid."`) — unlike `genres[]`, this one *is* validated against a
whitelist server-side.

**Status list and multiple statuses — `fields[]=status`, OR semantics (issue #68, checked
2026-10-04):**

Issue #68 (companion app's mobile catalog filters: a «Статус» group of multi-select chips)
asked for an id → label list, like `list_genres()`/`list_countries()`, and for filtering by
several statuses at once.

- The whitelist above is `GET /api/constants?fields[]=status`: same network-wide,
  `site_ids`-tagged shape as `fields[]=genres`/`fields[]=types` (a `Site-Id` header changes
  nothing about the response). As of this writing, 5 entries, all tagged for ranobelib.me:
  `1` "Онгоинг", `2` "Завершён", `3` "Анонс", `4` "Приостановлен", `5` "Выпуск прекращён"
  (`4`/`5` are tagged `site_ids: [0, 1, 2, 3, 4]`, i.e. not for site 5, `1`-`3` for all
  sites). The labels match `Title.status.label` for the same ids (each `status[]=<id>` alone
  returned only titles with that `status.id`/`label`), and `6`/`99` are the 422 above, so
  the list is the full set. `Catalog.list_statuses()` filters by `site_ids` containing `3`
  anyway, same as the other two lists — today that drops nothing, but the endpoint isn't
  site-scoped, so it could.
- Repeated `status[]` is **OR**, like `types[]`: `status[]=1&status[]=2` (`limit=60`,
  `sort_by=name`) returns both ongoing and completed titles (46 + 14), `status[]=2&status[]=4`
  both completed and paused. Expected, since a title has exactly one status.
- `Catalog.list_titles()`'s `status: int | None` was replaced outright with
  `statuses: list[int] | None` — not kept as a deprecated alias, same call as `country` →
  `countries` in issue #55 below. `None` or an empty list omits `status[]` entirely.

**Chapter-count filter — `chap_count_min`/`chap_count_max` (issue #69, checked
2026-10-04):**

Issue #69 (companion app's mobile catalog filters: «Количество глав» — «от 100» / «от 500» /
«от 1000») asked for a minimum chapter count, plus a maximum if the API has one. The parameter
names weren't guessed: the site's own JS bundle declares its catalog filter schema with
`chap_count_min`/`chap_count_max` (next to `year_min`/`year_max`, `rating_min`/`rating_max`,
...). Checked against the live API — the listing items don't carry a chapter count, so each
result's count was looked up through `GET /api/manga/{slug_url}?fields[]=chap_count`:

- Both bounds are **inclusive** and count `items_count.uploaded` — the same number as
  `Title.chapter_count`. `chap_count_min=1000&sort_by=chap_count&sort_type=asc` starts at
  titles with exactly 1000 chapters; `chap_count_max=100&sort_by=chap_count` (desc) starts at
  exactly 100; `chap_count_min=308&chap_count_max=308` includes `6712--high-school-dxd-novel`
  (308 chapters). `chap_count_min=100&chap_count_max=500` ascending starts at 100.
- Validated server-side: a negative value is 422 (`"... должно быть не менее 0."`), a
  non-integer (`abc`, `1.5`) is 422 (`"... должно быть целым числом."`). `0` is accepted,
  and `chap_count_max=0` returns titles with no chapters yet.
- **`min > max` is silently swapped**, not rejected: `chap_count_min=500&chap_count_max=100`
  gives the same 100..500 range (ascending starts at 100, descending at 500). The SDK
  doesn't rely on that undocumented behavior: `Catalog.list_titles(min_chapters=...,
  max_chapters=...)` raises `ValueError` for `min > max` and for negative values before any
  request, same as it already does for `page`/`per_page`.
- A bound above every title (`chap_count_min=99999999`) is 200 with an empty page.

**Country/origin filter — `types[]`, not `country`/`countries[]` (issue #48):**

Issue #48 (companion app's catalog filter sidebar needs a country-of-origin filter, same
motivation as the genre filter in #44) proposed guessing at `country`/`countries[]`
parameters and a `fields[]=countries` constants endpoint, mirroring `genres`. Checked
directly, both guesses turned out wrong:

- `GET /api/constants?fields[]=countries` is a real, working, unauthenticated endpoint —
  but it returns something unrelated to title origin: as of this writing, 3 entries
  (Беларусь/Казахстан/Россия), each with a `phone_code` and `emoji_unicode` and no
  `site_ids` field at all. This looks like a phone-country-code list for some account/
  registration flow elsewhere on the site, not a title metadata concept — the SDK does not
  use this endpoint.
- The actual "country a title comes from" concept already exists in every title response,
  just under a different name: the `type` field (present by default on both
  `GET /api/manga/{slug}` and `GET /api/manga` catalog listing items, no extra `fields[]`
  needed — confirmed via a real title, `91443--new-hero-in-dxd`: `"type": {"id": 15,
  "label": "Фанфик"}`, matching `tests/unit/test_models.py`'s `RAW_TITLE` fixture, which
  already carried this field unused before this issue). Before this issue, `type` was
  listed among "extra fields this endpoint sends that `Title` doesn't model" (see below) —
  that was accurate at the time (nothing consumed it) but incomplete once its actual
  meaning was understood.
- The catalog listing filter for it is `types[]=<id>` (repeatable; confirmed OR semantics
  by combining `types[]=10&types[]=11` → results with either type, unlike `genres[]`'s AND
  — expected, since a title only ever has one `type`, so OR is the only semantics that make
  sense). `type_id[]`/`type[]` were tried as alternate names and silently do nothing (same
  "accepted but ignored" pattern as bare `sort`); unrecognized ids **422**
  (`"The selected types.0 is invalid."`) — validated server-side, like `status[]`.
- The listing endpoint for id → label is `GET /api/constants?fields[]=types` (same
  network-wide, `site_ids`-tagged shape as `fields[]=genres`, see above — not site-scoped by
  request parameter, filter by `site_ids` containing `3` client-side). As of this writing,
  6 entries are tagged for ranobelib.me (`site_ids: [3]`): `10` "Япония" (Japan), `11`
  "Корея" (Korea), `12` "Китай" (China), `13` "Английский" (originally English-language),
  `14` "Авторский" (original/non-translated web novel), `15` "Фанфик" (fanfiction). The
  other ~14 entries in the full response are tagged for other lib.social sites (manga/manhwa/
  manhua-type entries for site 1/2/4, anime episode-format entries for site 5) and excluded
  the same way `Catalog.list_genres()` excludes non-ranobelib genres.
- Given three of the six ranobelib values aren't literal countries, the SDK's `Country`
  model (`id`/`name`, `name` mapped from the API's `label` key) surfaces all six as-is
  rather than trying to filter down to "real" countries only — see `Country`'s docstring.
  This is the same kind of naming mismatch as `sort`/`sort_by` and `number_secondary`/team
  selection elsewhere in this file: the issue's proposed public shape (`Country`,
  `Title.country`, `list_titles(country=...)`, `Catalog.list_countries()`) is kept because
  it matches the real use case, but everything under the hood — wire parameter names,
  constants endpoint, and the fact that this isn't a *pure* country concept — was corrected
  against what the API actually does, not what the issue guessed.

**Widened to accept multiple countries — `countries: list[int]`, OR semantics (issue #55):**

`list_titles(country=...)` originally only accepted a single id (previous paragraph),
matching "a title only has one country" — but that's a fact about what a title *has*, not
about what a filter UI needs to *select*, and issue #55 (companion app's catalog filters
moving country from radio buttons to checkboxes) asked for the same list-of-ids shape
`genres`/`tags` already have. The OR semantics of repeated `types[]` were already confirmed
during #48's investigation (bullet above: `types[]=10&types[]=11` → results with either
type) but the public API only ever sent one value. Re-confirmed directly for this issue with
a larger sample (`types[]=10&types[]=11&limit=60&sort_by=name`): the 60 results include both
type `10` and type `11` titles, not just one — real OR, not "last one wins" or silently
ignored like a bare `sort`. `Catalog.list_titles()`'s `country: int | None` parameter was
replaced outright with `countries: list[int] | None` (not kept alongside it — the issue left
this open, but the project doesn't keep unused parallel parameters, see CLAUDE.md); `None` or
an empty list omits `types[]` entirely, same as `genres`/`tags` already do for their own
list parameters.

**Sort — the real parameter is `sort_by`, not `sort` (`sort` is silently accepted and does
nothing):**

CLAUDE.md's original proposed shape (from the issue) guessed a `sort: str = "updated_at"`
parameter. Checked directly: `sort=<anything>` (including garbage values) returns 200 with
**no change in ordering whatsoever** compared to omitting it entirely — it isn't validated,
isn't applied, just ignored. The parameter that actually controls ordering is **`sort_by`**,
which *is* validated (unknown values → 422, no enumeration of allowed ones in the error body,
so the set below was found by brute-forcing likely candidates, not read from a schema):

| `sort_by` value | Result |
|---|---|
| `name` | 200, changes order |
| `created_at` | 200, changes order |
| `views` | 200, changes order |
| `chap_count` | 200, changes order |
| `last_chapter_at` | 200, changes order |
| `rate_avg` | 200, changes order (confirmed by rating) |
| `random` | 200, genuinely randomizes (different order every call, no shared seed by default) |
| `updated_at`, `rating`, `alphabet`, `id`, `popularity`, ... | 422 invalid |

This list isn't necessarily exhaustive — only what was tried. Also confirmed a companion
**`sort_type`** parameter (`"desc"`/`"asc"`, default `desc`) that reverses ordering for
whichever `sort_by` is active; `order`/`dir` were tried as alternate names for this and don't
do anything (silently ignored, same as bare `sort`).

Given `updated_at` doesn't exist, the SDK's default is **`last_chapter_at`** instead — the
closest real equivalent to "recently updated" (a title's last-chapter timestamp, which is
what actually changes when a title gets a new chapter). Same kind of correction as
`number_secondary`/`team_id` earlier in this file: the issue's proposed shape was a starting
guess, not verified API behavior.

`sort_by=random` pagination note (not implemented, documented as a known gap): passing back
the `random_order` float from a previous response's `meta.random_order` as a `random_order`
query param on the next request keeps the random order stable across pages (confirmed:
`page=1` and `page=2` with the same `random_order` value returned no overlapping ids).
Without it, consecutive `sort_by=random` pages are independently randomized and can repeat or
skip items. `Catalog.list_titles()` doesn't expose `sort_by="random"` pagination stability
(no `random_order` parameter) — out of scope for this issue's ask (plain listing/search, not
a "browse randomly without duplicates" feature); a caller can still pass `sort="random"` and
get a valid, just not stably-paginated, response.

**Catalog list items validate directly against the existing `Title` model:** a raw item from
`GET /api/manga`'s `data` array has every field `Title` requires (`id`, `name`, `slug`,
`slug_url`, `cover`, `ageRestriction`, `status`) and nothing that conflicts with it — confirmed
by running `Title.model_validate()` on a real captured item. Fields `Title` defines with
defaults but that this endpoint doesn't send (`genres`, `tags`, `authors`, `artists`, `teams`,
`summary`, `release_date`, `chapter_count`, `last_chapter_at` — see "Last chapter date"
above, ...) just come back empty/`None`, same as any other optional field — no separate "catalog list item" model needed, matching the issue's explicit
ask to reuse `Title`. Extra fields this endpoint sends that `Title` doesn't model (`rating`,
`content_marking`, `site`, `releaseDateString`) are ignored by pydantic, same as everywhere
else in the SDK. `type` used to be in this list too, until issue #48 (see "Country/origin
filter" above) — it's now `Title.country`.

## MangaLib (`mangalib-python-sdk`, issue #90, checked 2026-10-18)

mangalib.me sits on the same backend as ranobelib.me. Everything below was checked against
the live API with `Site-Id: 1` and `Origin`/`Referer: https://mangalib.me` before the models
were written. The starting point was the SDK's own code and the open-source
[keiyoushi `lib-multisrc/libgroup`](https://github.com/keiyoushi/extensions-source/tree/main/lib-multisrc/libgroup)
client, and the live API corrected it in a few places (image servers, closed chapters).

### Same as ranobelib

- `GET /manga/{slug}` with the same `fields[]` (`get_info()` uses ranobelib's list
  unchanged), `GET /manga/{slug}/chapters`, `GET /manga/{slug}/chapter`, `GET /manga` with
  `site_id[]=1`, `GET /constants`. A title of the other site answers 404 with the wrong
  `Site-Id`, as described under "Site scoping".
- The chapter list has the same shape, `branches[]` included. `number` holds the fraction
  (344 of 11,523 chapters of 41 titles, e.g. `"6.5"`), and `number_secondary` equals
  `volume` on all 20,596 chapters of 114 other titles (latest-updated and most-viewed), as
  on ranobelib.
- `Title.country` is the site's title type. For site 1 `/constants?fields[]=types` gives
  `Манга`, `OEL-манга`, `Манхва`, `Маньхуа`, `Руманга`, `Комикс`. `fields[]=status` has the
  same five statuses as ranobelib. `fields[]=genres` lists 49 genres for site 1.
- **No reliable default branch.** On 12 chapters of four titles with competing translations
  (`7965--chainsaw-man`, `3321--dorohedoro`, `105--fullmetal_alchemist`,
  `18009--jujutsu-kaisen-0-...`), the branch the API picks without `branch_id` was the first
  in the chapter list's `branches` in only 5 of them. Per title the pick was the same
  `branch_id` each time, but that `branch_id` was the lowest of the title's ids in three
  titles and the highest in the fourth. So `MangaLib` raises `MultipleTranslationsError` like
  ranobelib does ("Translation selection").
- Many of the most-viewed titles (`247--shingeki-no-kyojin`, `3601--unordinary_`, Solo
  Leveling, ...) return an empty chapter list: licensed titles keep their page but not their
  chapters. That's an empty table of contents, not an error.

### Chapter pages

A fetched chapter has `pages` instead of `content`:

```json
{"id": 4577438, "image": "00.png_res.jpg", "slug": 1, "external": 0, "chunks": 1,
 "chapter_id": 223269, "created_at": "...", "updated_at": "...", "height": 2048,
 "width": 1425, "url": "//manga/chainsaw-man/chapters/1-1/00.png_res.jpg", "ratio": "0.6958"}
```

- `slug` is the page's 1-based position, and `pages` comes in that order: `1..N` without
  gaps on all 108 chapters (one per title, 1,497 pages) checked for it. `Page.number` is
  this `slug`.
- `url` started with `//` on all of those pages and on 510 more (41 chapters of 41 other
  titles). It's relative to an image server. Neither the chapter nor the page says which server, because every server serves
  every page under the same path.
- `external` was `0` on every one of the 510 pages. `chunks` ranged from 0 to 5. On tall webtoon strips (690×38200)
  the server still sends the whole image for the page URL, so `chunks` doesn't change how a
  page is downloaded and isn't modelled. Non-ASCII file names occur (`1화_Dfpp.png`) and
  download fine.
- `width`/`height` matched the downloaded image's dimensions.

### Image servers: `GET /constants?fields[]=imageServers`

Not site-scoped by any parameter. Entries carry `site_ids` like the genre list:

| `id` | site 1 (and 3) `url` | serves |
|---|---|---|
| `main` | `https://img2.imglib.info` | HTML 403 from DDoS-Guard on every attempt |
| `secondary` | `https://img2.imglib.info` | same host as `main` |
| `compress` | `https://img3.cdnlibs.org` | the full-size page (1425×2048 for the example above) |
| `download` | `https://img3.cdnlibs.org` | same host as `compress` |
| `crop` | `https://crops.mangalib.me` | a 310×450 preview; `400 Invalid path` on some pages |

Sites 2 and 4 have their own hosts (`img2.hentaicdn.org`, ...), and site 2's `crop` has an
empty `url`. `MangaLib.list_image_servers()` keeps the entries for site 1 that have a URL.

`img2.imglib.info` was checked with no headers, with only `Referer`, with only a browser
`User-Agent`, with `Accept: image/*`, with `Sec-Fetch-*`, with `Accept-Language`, and with
all of them together, using fresh clients and a cookie-keeping client. Every request got
DDoS-Guard's HTML 403, except a single 200 on the first request of one client, after which
that client got 403s too. That host wants a browser that runs DDoS-Guard's JavaScript check.
`img3.cdnlibs.org` and `crops.mangalib.me` served every combination, including no headers at all.

Two more things about `compress`:

- It sends JPEG (`Content-Type: image/jpeg`, JPEG bytes) even for `.png` file names, so a
  file name's extension doesn't tell the format.
- `server.url + page.url` gives a double slash (`https://img3.cdnlibs.org//manga/...`). The
  single-slash form returns the same bytes on every server, and `mangalib.page_url()` uses it.

So `MangaLib.download_page()` tries the servers in the order `compress`, `download`, `main`,
`secondary` (`images.DEFAULT_SERVER_ORDER`), skips any server whose URL was already tried,
and moves on after a non-2xx status or a non-image `Content-Type` (a 429, a 5xx or a network
error only after retries, see "Export, page sizes and the image host's rate limit" below).
`server=` puts a server first; `crop` is only used when asked for. Image requests send
`browser_headers_for("https://mangalib.me")` plus `Accept: image/*`, with the same
`headers=` overrides as the API client. They don't send `Site-Id`.

### Paid and early-access chapters: `restricted_view`

Scanned on the chapter lists of 114 titles (the 60 latest-updated and 60 most-viewed, less
duplicates and five with no chapters; 20,880 branches):

- A restricted branch in the chapter list carries `restricted_view: {"is_open": false,
  "expired_at": ..., "price": null}`: 1,868 branches. `expired_at` is when early access
  ends (89 of them), and `null` for a chapter that stays paid (1,779). The list never had
  `is_open: true`. A chapter that had been in early access and has since opened
  (`226780--...`'s 1/73) has no `restricted_view` in the list, though fetching it returns
  one with `is_open: true`.
- Branches also carry `expired_type`: `0` on 17,972, `2` on exactly the 1,779 permanently
  paid ones, `1` on 1,129, which are the 89 in early access plus chapters whose early
  access ended long ago. So it doesn't say whether a chapter is readable now, and isn't
  modelled.
- Fetching a closed chapter without an account is **200, not 403**. The response has
  `restricted_view: {"is_open": false, "price": 18, "expired_at": ...,
  "can_open_with_content_key": false}` and no `pages` key at all. With or without
  `branch_id` the answer is the same. A chapter whose early access has ended has
  `restricted_view.is_open: true` and its `pages`.

The SDK has no login. `ChapterBranch.restricted_view`/`is_open` come from the chapter list.
On the chapter fetch, `mangalib.client.ApiClient.get_chapter()` raises `AuthRequiredError` when
`restricted_view.is_open` is `false`. The check runs there and not on the parsed model, so that
the refusal never reaches the disk cache. A cached refusal would keep failing after the
chapter opens at `expired_at`. The chapter list isn't used to refuse early: a cached list
can be older than the chapter's opening.

`get_chapters()`/`get_volume()`/`get_volumes()` hit the same error on a closed chapter:
they're given explicit chapters, and silently leaving one out would hand back less than
was asked for. The whole-title operations, `download_title()` and `estimate_title_size()`,
work over open translations only instead (issue #91). They'd otherwise end at the first
closed chapter, usually one of the newest, with `DownloadTitleInterruptedError`. A chapter
whose translations are all closed is skipped (logged with `verbosity="full"`). A closed
translation next to open ones is dropped from the choice, so `translation_index` counts
open translations and `MultipleTitleTranslationsError` lists only those. When one
translation is left open out of several, it's requested by its `branch_id`, because without
one the API picks its own default, which can be the closed one. On
`226780--online-game-...` this downloads 132 of the 134 chapters, leaving out the two in
early access.

### Export, page sizes and the image host's rate limit (issue #91, checked 2026-10-18)

- **`HEAD` gives a page's exact size.** `img3.cdnlibs.org` answers `HEAD` with
  `Content-Length` equal to the downloaded body (checked page by page), with
  `Cache-Control: max-age=4320000`. `MangaLib.chapter_size()`/`volume_size()` sum these
  without downloading any image. `estimate_title_size()` samples chapters the same way:
  the chapter list has no page counts, so both the page count and the page weight come from
  the sample. For chapter 1/1 of `7965--chainsaw-man` (55 pages) the sum was 17,943,292
  bytes, and the PDF export of it 17,974,132.
- **The image host rate-limits, through DDoS-Guard.** 300 full-size GETs (63 MB) went
  through with five at a time, 0.2 s between request starts, without a 429. So did 300 GETs
  with twenty at a time and no delay, which ran at ~15 requests/s because of bandwidth.
  Dense `HEAD` bursts got 429s: 5 of 256 requests at ~57 requests/s, and 751 of 927 with
  thirty at a time (the first after 2.6 s). The 429 is DDoS-Guard's HTML page, with no
  `Retry-After`. A request a minute or two later went through again. `GET`s at 0.1 s
  pacing right after those bursts got a few 429s too, so the limit looks like requests per
  time window, not request rate alone.
- **A 429 on `HEAD` breaks the connection.** DDoS-Guard sends its HTML body even in answer
  to `HEAD`, so the next response on that keep-alive connection fails to parse
  (`httpx.RemoteProtocolError: illegal status line`, with the leftover HTML in it).
- So page requests go through the process-wide `libsocial.shared_pacer()` of the image's
  own host (not api.cdnlibs.org's) with `images.DEFAULT_IMAGE_REQUEST_DELAY = 0.2`, five at
  a time by default (`concurrency=`). A 429, a 5xx or any `httpx.TransportError` (the broken
  connection above included) is retried on the same server up to 3 times, after 1, 2 and
  4 s. A refusal (another 4xx, or a 2xx that isn't an image) isn't retried. After either,
  the next server is tried.
- **PDF via img2pdf** (the `pdf` extra). JPEGs are embedded as-is: the page image in the
  PDF is byte-identical to the download. It also took PNG with alpha (adding a soft mask)
  and WebP. A 690×38200 webtoon strip, beyond the PDF page-size limit (14,400 pt), came out
  as one page of 69×3820 with `/UserUnit 10`, not split. That keeps one PDF page per
  image, as the issue asks. The PDF is built in memory, so for a whole long title CBZ is the
  lighter format.
- **A fetched chapter's `name` belongs to its translation.** It can be missing where the
  chapter list has one (1/1 of `7965--chainsaw-man`, `branch_id` 4667: `null` vs.
  `"Пёс и бензопила"`), and two translations can name a chapter differently (3/20:
  `"За выпивкой"` in the list, `"Выпивка"` in the fetched one). Export uses the fetched
  chapter's name, so a translation's file isn't labelled with another translation's title.
  Many chapters have an empty `""` name. A chapter without a name is labelled
  `Том N Глава M`.

### Title names without a format marker (checked 2026-10-18)

`Title.base_names` has the same job as ranobelib's (issue #79): names to look a title up
by elsewhere, without a publication-format marker. The marker list was built the same way,
by walking the whole catalog (`GET /api/manga`, `site_id[]=1`, `sort_by=created_at`, 691
pages, 41,419 titles) and counting every bracketed tail of `rus_name`, `eng_name` and
`name`.

- **mangalib.me appends no marker of its own.** Only 2,061 names over the three fields of
  41,419 titles end with a bracketed tail at all, and most of those tell titles apart: `(Doujinshi)` (88),
  `(Colored)`, `(перезапуск)`, `(додзинси)`, `(Цветная версия)`, `(Oneshot)`,
  `(Serialization)`, `(Genshin Impact)`, years, `(Vol 1)`, `(Remake)`, `(Артбук)`, authors.
- Bare format markers were typed by hand on 49 names: `(webtoon)`/`[Webtoon]`/`(WEBTOON)`
  (the most common, mostly on romanized Korean `name`s), `(вебтун)`/`[Вебтун]`, `(manhwa)`,
  `(manga)`/`(Манга)`, `(Manhua)`, `(comic)`/`(comics)`/`(Комикс)`/`(комикс)`,
  `(comic book)`, `(Webcomic)`. Two have no space before it (`...gibun-eun?(webtoon)`,
  `Donghwa(webtoon)`).
- Tails that mention a format but say more are kept, because they tell versions of a work
  apart: `Вакфу: Великая Волна (манга-версия)` and `(вебтун-версия)` are two titles,
  likewise `(Color Webtoon)`/`(цветная вебтун версия)` vs. the original, and
  `(Fan Comics)`, `(Digital Colored Comics)`, `(Graphic Novel)`, `(Sonic The Comic)`,
  `(мини-комиксы)`, `(Пролог к новелле)`. A bare `(novel)`/`(новелла)` was left too: on a
  manga site it marks the one title that isn't manga (1 case).

The rule is ranobelib's (bracketed marker at the very end, repeated, with `,`/`:`/`/` before
it) with the list above. Over the full catalog it changes exactly those 49 names.
`other_names` of a random 150 titles through `get_info()` (113 have some) had one bracketed
tail, an author's name (`Love Planet (KISARAGI Sono)`), and no marker.

## Open questions

See the "Что НЕ проверено" section of `CLAUDE.md` for the current list: how a fractional
`number` affects the reading URL, illustration CDN structure for the `p`/`img`-only cases
(confirmed to be `ranobelib.me` itself, not a separate CDN — see above, so this is largely
resolved, but worth re-confirming CDN domain doesn't vary by title/region), paywall/403
behavior, `/chapters` pagination for very large titles, and reproducing `textAlign`/
heading/list formatting from the prosemirror format if it turns out to matter for exports.
Default branch/team selection is now resolved — see "Translation selection" above.

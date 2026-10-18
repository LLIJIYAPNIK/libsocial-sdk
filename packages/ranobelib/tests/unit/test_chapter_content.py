"""Unit tests for chapter content normalization (ranobelib.models.Chapter.content)."""

from typing import Any

from ranobelib.models import Chapter

BASE_CHAPTER: dict[str, Any] = {
    "id": 1,
    "volume": "1",
    "number": "1",
    "name": "Chapter 1",
}


def test_chapter_content_string_strips_editor_attributes() -> None:
    # data-paragraph-index is a pure editor artifact (see docs/api-notes.md) and isn't in
    # the restricted tag/attribute vocabulary the sanitizer allows through.
    raw = {**BASE_CHAPTER, "content": '<p data-paragraph-index="1">Hello.</p>'}

    chapter = Chapter.model_validate(raw)

    assert chapter.content == "<p>Hello.</p>"


def test_chapter_content_string_keeps_allowed_tags() -> None:
    raw = {
        **BASE_CHAPTER,
        "content": (
            "<p>a<strong>b</strong><em>c</em>d</p><hr /><p>e<br />f"
            '<img loading="lazy" src="https://ranobelib.me/uploads/x.jpg" /></p>'
        ),
    }

    chapter = Chapter.model_validate(raw)

    assert chapter.content == (
        "<p>a<strong>b</strong><em>c</em>d</p><hr /><p>e<br />f"
        '<img loading="lazy" src="https://ranobelib.me/uploads/x.jpg" /></p>'
    )


def test_chapter_content_string_maps_b_and_i_to_strong_and_em() -> None:
    # Observed as interchangeable with strong/em across samples, see docs/api-notes.md.
    raw = {**BASE_CHAPTER, "content": "<p><b>bold</b> <i>italic</i></p>"}

    chapter = Chapter.model_validate(raw)

    assert chapter.content == "<p><strong>bold</strong> <em>italic</em></p>"


def test_chapter_content_string_drops_disallowed_tags_keeps_text() -> None:
    raw = {**BASE_CHAPTER, "content": '<p>before <a href="https://evil.example">link</a> after</p>'}

    chapter = Chapter.model_validate(raw)

    assert chapter.content == "<p>before link after</p>"


def test_chapter_content_string_drops_script_tag_and_its_text() -> None:
    raw = {**BASE_CHAPTER, "content": "<p>safe</p><script>alert(document.cookie)</script>"}

    chapter = Chapter.model_validate(raw)

    assert chapter.content == "<p>safe</p>"


def test_chapter_content_string_strips_event_handler_attributes() -> None:
    raw = {**BASE_CHAPTER, "content": '<p onclick="alert(1)">text</p>'}

    chapter = Chapter.model_validate(raw)

    assert chapter.content == "<p>text</p>"


def test_chapter_content_string_drops_img_with_unsafe_scheme() -> None:
    raw = {**BASE_CHAPTER, "content": '<p><img src="javascript:alert(1)" /></p>'}

    chapter = Chapter.model_validate(raw)

    assert chapter.content == "<p></p>"


def test_chapter_content_string_escapes_text() -> None:
    raw = {**BASE_CHAPTER, "content": "<p>&lt;not a real tag&gt; &amp; &quot;quoted&quot;</p>"}

    chapter = Chapter.model_validate(raw)

    assert chapter.content == "<p>&lt;not a real tag&gt; &amp; &quot;quoted&quot;</p>"


def test_chapter_content_defaults_to_none() -> None:
    chapter = Chapter.model_validate(BASE_CHAPTER)

    assert chapter.content is None


def test_chapter_content_prosemirror_paragraphs() -> None:
    raw = {
        **BASE_CHAPTER,
        "content": {
            "type": "doc",
            "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": "First."}]},
                {"type": "paragraph", "content": [{"type": "text", "text": "Second."}]},
            ],
        },
    }

    chapter = Chapter.model_validate(raw)

    assert chapter.content == "<p>First.</p><p>Second.</p>"


def test_chapter_content_prosemirror_empty_paragraph() -> None:
    raw = {
        **BASE_CHAPTER,
        "content": {"type": "doc", "content": [{"type": "paragraph"}]},
    }

    chapter = Chapter.model_validate(raw)

    assert chapter.content == "<p></p>"


def test_chapter_content_prosemirror_bold_and_italic_marks() -> None:
    raw = {
        **BASE_CHAPTER,
        "content": {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "text", "text": "bold", "marks": [{"type": "bold"}]},
                        {"type": "text", "text": " and "},
                        {"type": "text", "text": "italic", "marks": [{"type": "italic"}]},
                    ],
                }
            ],
        },
    }

    chapter = Chapter.model_validate(raw)

    assert chapter.content == "<p><strong>bold</strong> and <em>italic</em></p>"


def test_chapter_content_prosemirror_escapes_text() -> None:
    raw = {
        **BASE_CHAPTER,
        "content": {
            "type": "doc",
            "content": [{"type": "paragraph", "content": [{"type": "text", "text": "<script>&"}]}],
        },
    }

    chapter = Chapter.model_validate(raw)

    assert chapter.content == "<p>&lt;script&gt;&amp;</p>"


def test_chapter_content_prosemirror_hard_break_and_horizontal_rule() -> None:
    raw = {
        **BASE_CHAPTER,
        "content": {
            "type": "doc",
            "content": [
                {"type": "paragraph", "content": [{"type": "hardBreak"}]},
                {"type": "horizontalRule"},
            ],
        },
    }

    chapter = Chapter.model_validate(raw)

    assert chapter.content == "<p><br /></p><hr />"


def test_chapter_content_prosemirror_image_resolved_via_attachments() -> None:
    raw = {
        **BASE_CHAPTER,
        "content": {
            "type": "doc",
            "content": [
                {"type": "image", "attrs": {"images": [{"image": "abc-123"}]}},
            ],
        },
        "attachments": [
            {
                "name": "abc-123",
                "filename": "abc-123.jpg",
                "url": "/uploads/ranobe/example/chapters/1/abc-123.jpg",
            }
        ],
    }

    chapter = Chapter.model_validate(raw)

    assert chapter.content == (
        '<img loading="lazy" '
        'src="https://ranobelib.me/uploads/ranobe/example/chapters/1/abc-123.jpg" />'
    )


def test_chapter_content_prosemirror_image_unresolvable_omitted() -> None:
    raw = {
        **BASE_CHAPTER,
        "content": {
            "type": "doc",
            "content": [{"type": "image", "attrs": {"images": [{"image": "missing"}]}}],
        },
        "attachments": [],
    }

    chapter = Chapter.model_validate(raw)

    assert chapter.content == ""


def test_chapter_content_prosemirror_unknown_block_node_recurses_into_children() -> None:
    # Forward-compat: an unrecognized block wrapper (e.g. a node type not yet seen in the
    # wild, see docs/api-notes.md) should still surface its text rather than dropping it.
    raw = {
        **BASE_CHAPTER,
        "content": {
            "type": "doc",
            "content": [
                {
                    "type": "blockquote",
                    "content": [
                        {"type": "paragraph", "content": [{"type": "text", "text": "Quoted."}]}
                    ],
                }
            ],
        },
    }

    chapter = Chapter.model_validate(raw)

    assert chapter.content == "<p>Quoted.</p>"


def test_chapter_content_prosemirror_unknown_inline_node_recurses_into_children() -> None:
    raw = {
        **BASE_CHAPTER,
        "content": {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "link", "content": [{"type": "text", "text": "link"}]}],
                }
            ],
        },
    }

    chapter = Chapter.model_validate(raw)

    assert chapter.content == "<p>link</p>"


def test_chapter_content_prosemirror_no_attachments_key() -> None:
    raw = {
        **BASE_CHAPTER,
        "content": {"type": "doc", "content": [{"type": "image", "attrs": {"images": []}}]},
    }

    chapter = Chapter.model_validate(raw)

    assert chapter.content == ""


def _footnote_contents(chapter: Chapter) -> list[str]:
    return [footnote.content for footnote in chapter.footnotes]


def test_chapter_footnotes_default_to_empty() -> None:
    assert Chapter.model_validate(BASE_CHAPTER).footnotes == []
    assert Chapter.model_validate({**BASE_CHAPTER, "content": "<p>Text.</p>"}).footnotes == []


def test_chapter_footnotes_string_paragraphs_moved_out_of_content() -> None:
    # Shape observed in real HTML-string chapters (see docs/api-notes.md): one <p> per
    # footnote, arrow + non-breaking space, after the chapter's last real paragraph.
    raw = {
        **BASE_CHAPTER,
        "content": (
            '<p data-paragraph-index="1">Story*.</p>'
            '<p data-paragraph-index="2">↑ Бумажный веер.</p>'
            '<p data-paragraph-index="3">↑ Second note.</p>'
        ),
    }

    chapter = Chapter.model_validate(raw)

    assert chapter.content == "<p>Story*.</p>"
    assert _footnote_contents(chapter) == ["Бумажный веер.", "Second note."]


def test_chapter_footnotes_string_ordered_list_items() -> None:
    # The other real HTML-string shape: an <ol> of <li>, with the arrow as an entity.
    raw = {
        **BASE_CHAPTER,
        "content": (
            "<p>Story.</p>\r\n\r\n<ol>\r\n\t<li>&uarr;&nbsp;Первая.</li>\r\n"
            "\t<li>&uarr;&nbsp;Вторая.</li>\r\n</ol>"
        ),
    }

    chapter = Chapter.model_validate(raw)

    assert "↑" not in (chapter.content or "")
    assert "Первая" not in (chapter.content or "")
    assert (chapter.content or "").startswith("<p>Story.</p>")
    assert _footnote_contents(chapter) == ["Первая.", "Вторая."]


def test_chapter_footnotes_string_keeps_sanitized_inline_markup() -> None:
    raw = {
        **BASE_CHAPTER,
        "content": '<p><b>↑ Term</b> — <i class="x">meaning</i><script>bad()</script></p>',
    }

    chapter = Chapter.model_validate(raw)

    assert chapter.content == ""
    assert _footnote_contents(chapter) == ["<strong>Term</strong> — <em>meaning</em>"]


def test_chapter_footnotes_string_arrow_not_at_start_is_regular_text() -> None:
    raw = {**BASE_CHAPTER, "content": "<p>Prices went ↑ today.</p><li>Item ↑</li>"}

    chapter = Chapter.model_validate(raw)

    assert chapter.content == "<p>Prices went ↑ today.</p><p>Item ↑</p>"
    assert chapter.footnotes == []


def test_chapter_footnotes_string_empty_footnote_dropped() -> None:
    raw = {**BASE_CHAPTER, "content": "<p>Text.</p><p>↑ </p>"}

    chapter = Chapter.model_validate(raw)

    assert chapter.content == "<p>Text.</p>"
    assert chapter.footnotes == []


def test_chapter_content_string_list_items_become_paragraphs() -> None:
    # Issue #59: a dropped block tag used to leave its text inline, running adjacent
    # blocks together into one unparagraphed line.
    raw = {**BASE_CHAPTER, "content": "<ul>\r\n\t<li>One</li>\r\n\t<li>Two</li>\r\n</ul>"}

    chapter = Chapter.model_validate(raw)

    assert chapter.content == "<p>One</p><p>Two</p>"


def test_chapter_footnotes_string_paragraph_inside_list_item() -> None:
    raw = {**BASE_CHAPTER, "content": "<ol><li><p>↑ Nested.</p></li></ol>"}

    chapter = Chapter.model_validate(raw)

    assert chapter.content == ""
    assert _footnote_contents(chapter) == ["Nested."]


def test_chapter_content_string_implicitly_closes_unclosed_paragraphs() -> None:
    raw = {**BASE_CHAPTER, "content": "<p>One<p>↑ Note<p>Two"}

    chapter = Chapter.model_validate(raw)

    assert chapter.content == "<p>One</p><p>Two</p>"
    assert _footnote_contents(chapter) == ["Note"]


def test_chapter_content_string_closes_blocks_left_open_inside_closed_one() -> None:
    raw = {**BASE_CHAPTER, "content": "<li><p>Text</li><p>After</p>"}

    chapter = Chapter.model_validate(raw)

    assert chapter.content == "<p>Text</p><p>After</p>"


def test_chapter_content_string_drops_stray_block_end_tags() -> None:
    raw = {**BASE_CHAPTER, "content": "</p>Text</li><p/>"}

    chapter = Chapter.model_validate(raw)

    assert chapter.content == "Text<p></p>"


def _prosemirror_paragraph(*children: dict[str, Any]) -> dict[str, Any]:
    return {"type": "paragraph", "content": list(children)}


def test_chapter_footnotes_prosemirror_paragraphs_moved_out_of_content() -> None:
    raw = {
        **BASE_CHAPTER,
        "content": {
            "type": "doc",
            "content": [
                _prosemirror_paragraph({"type": "text", "text": "Story."}),
                _prosemirror_paragraph(
                    {"type": "text", "text": "↑ "},
                    {"type": "text", "text": "Term", "marks": [{"type": "bold"}]},
                    {"type": "text", "text": " — meaning <x>"},
                ),
                _prosemirror_paragraph({"type": "text", "text": "↑"}),
            ],
        },
    }

    chapter = Chapter.model_validate(raw)

    assert chapter.content == "<p>Story.</p>"
    assert _footnote_contents(chapter) == ["<strong>Term</strong> — meaning &lt;x&gt;"]


def test_chapter_footnotes_prosemirror_skips_non_text_nodes_before_arrow() -> None:
    raw = {
        **BASE_CHAPTER,
        "content": {
            "type": "doc",
            "content": [
                _prosemirror_paragraph(
                    {"type": "hardBreak"},
                    {"type": "text", "text": "  "},
                    {"type": "text", "text": "↑ Note."},
                ),
                _prosemirror_paragraph({"type": "hardBreak"}),
                _prosemirror_paragraph({"type": "text", "text": "Up ↑"}),
            ],
        },
    }

    chapter = Chapter.model_validate(raw)

    assert chapter.content == "<p><br /></p><p>Up ↑</p>"
    assert _footnote_contents(chapter) == ["<br />  Note."]


def test_chapter_footnotes_prosemirror_inside_unknown_block_node() -> None:
    raw = {
        **BASE_CHAPTER,
        "content": {
            "type": "doc",
            "content": [
                {
                    "type": "blockquote",
                    "content": [_prosemirror_paragraph({"type": "text", "text": "↑ Deep."})],
                }
            ],
        },
    }

    chapter = Chapter.model_validate(raw)

    assert chapter.content == ""
    assert _footnote_contents(chapter) == ["Deep."]


def test_chapter_footnotes_survive_dump_and_revalidate() -> None:
    chapter = Chapter.model_validate({**BASE_CHAPTER, "content": "<p>Text.</p><p>↑ Note.</p>"})

    assert Chapter.model_validate(chapter.model_dump()) == chapter


def test_chapter_content_string_heading_becomes_paragraph() -> None:
    # Real shape (see docs/api-notes.md): <h3> section headings between paragraphs.
    raw = {
        **BASE_CHAPTER,
        "content": "<p>Before.</p>\r\n\r\n<h3>Император</h3>\r\n\r\n<p>After.</p>",
    }

    chapter = Chapter.model_validate(raw)

    assert chapter.content == "<p>Before.</p>\r\n\r\n<p>Император</p>\r\n\r\n<p>After.</p>"


def test_chapter_content_string_dropped_block_keeps_inline_markup() -> None:
    raw = {**BASE_CHAPTER, "content": '<div class="x"> <b>Bold</b> and <a href="#">link</a> </div>'}

    chapter = Chapter.model_validate(raw)

    assert chapter.content == "<p><strong>Bold</strong> and link</p>"


def test_chapter_content_string_dropped_block_splits_text_around_nested_blocks() -> None:
    raw = {
        **BASE_CHAPTER,
        "content": "<div>Intro<p>Inner</p>Middle<blockquote>Quote</blockquote>Outro</div>",
    }

    chapter = Chapter.model_validate(raw)

    assert chapter.content == "<p>Intro</p><p>Inner</p><p>Middle</p><p>Quote</p><p>Outro</p>"


def test_chapter_content_string_block_inside_paragraph_closes_it() -> None:
    raw = {**BASE_CHAPTER, "content": "<p>Text<div>Block</div>tail</p>"}

    chapter = Chapter.model_validate(raw)

    assert chapter.content == "<p>Text</p><p>Block</p>tail"


def test_chapter_content_string_table_cells_become_paragraphs() -> None:
    raw = {
        **BASE_CHAPTER,
        "content": "<table><tr><td>A</td><td>B</td></tr><tr><td></td></tr></table>",
    }

    chapter = Chapter.model_validate(raw)

    assert chapter.content == "<p>A</p><p>B</p>"


def test_chapter_content_string_hr_inside_dropped_block_separates_paragraphs() -> None:
    raw = {**BASE_CHAPTER, "content": "<div>One<hr>Two</div><p>a<hr/>b</p>"}

    chapter = Chapter.model_validate(raw)

    assert chapter.content == "<p>One</p><hr /><p>Two</p><p>a<hr />b</p>"


def test_chapter_content_string_unclosed_list_items_close_each_other() -> None:
    raw = {**BASE_CHAPTER, "content": "<ol><li>One<li>Two</ol>"}

    chapter = Chapter.model_validate(raw)

    assert chapter.content == "<p>One</p><p>Two</p>"


def test_chapter_footnotes_string_detected_per_paragraph_in_dropped_block() -> None:
    raw = {
        **BASE_CHAPTER,
        "content": ("<div>Story.<p>More.</p>↑ Note.</div><div><span>↑</span> Other.</div>"),
    }

    chapter = Chapter.model_validate(raw)

    assert chapter.content == "<p>Story.</p><p>More.</p>"
    assert _footnote_contents(chapter) == ["Note.", "Other."]

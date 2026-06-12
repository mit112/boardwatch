import html

from boardwatch.core.html_text import html_to_text


def test_paragraph_boundaries_become_separators() -> None:
    out = html_to_text("<p>First paragraph.</p><p>Second paragraph.</p>")
    assert out == "First paragraph.\nSecond paragraph."


def test_list_item_boundaries_become_separators() -> None:
    out = html_to_text("<ul><li>Python</li><li>Go</li><li>SQL</li></ul>")
    assert out.splitlines() == ["Python", "Go", "SQL"]


def test_nested_inline_tags_merge_into_contiguous_text() -> None:
    out = html_to_text("<p>We use <b>Go</b> and <em>Python</em> daily.</p>")
    assert out == "We use Go and Python daily."


def test_entities_unescaped() -> None:
    assert html_to_text("<p>Tools &amp; Infrastructure</p>") == "Tools & Infrastructure"
    assert html_to_text("<p>5 &gt; 3</p>") == "5 > 3"


def test_greenhouse_escaped_content_pipeline() -> None:
    # Greenhouse returns the content field as HTML-ESCAPED HTML; the provider
    # (Task 6) unescapes once before calling html_to_text. Pinned with a
    # captured-shape sample (structure from a real recording, text sanitized).
    escaped = (
        "&lt;p&gt;Engineering &amp;amp; Design&lt;/p&gt;"
        "&lt;ul&gt;&lt;li&gt;Build APIs&lt;/li&gt;&lt;li&gt;Ship weekly&lt;/li&gt;&lt;/ul&gt;"
    )
    out = html_to_text(html.unescape(escaped))
    assert out.splitlines() == ["Engineering & Design", "Build APIs", "Ship weekly"]


def test_script_and_style_dropped() -> None:
    out = html_to_text("<p>Visible</p><script>var x = 1;</script><style>p{}</style>")
    assert out == "Visible"


def test_empty_and_whitespace_only_input() -> None:
    assert html_to_text("") == ""
    assert html_to_text("   \n\t ") == ""


def test_intra_line_whitespace_collapsed() -> None:
    out = html_to_text("<p>Senior   Software\n Engineer</p>")
    assert out == "Senior Software Engineer"

from __future__ import annotations

import pytest

from boardwatch.tailor.model import Bullet, Entry, Resume, SkillGroup
from boardwatch.tailor.render import parse_bullets
from boardwatch.tailor.render.latex import escape, unescape


def test_escape_latex_specials():
    assert escape("40% & $5 #1 a_b {x} ~ ^ c\\d") == r"40\% \& \$5 \#1 a\_b \{x\} \textasciitilde{} \textasciicircum{} c\textbackslash{}d"


def test_escape_collapses_whitespace():
    assert escape("a   b\n c") == "a b c"


def test_escape_unescape_roundtrip():
    # includes backslash/tilde/caret to exercise unescape's longest-first ordering (re-review 2 minor)
    for s in ["Cut p99 latency 40%", "C/C++ & .NET", "a_b {x} $y$ #z", "path\\to ~file ^2"]:
        assert unescape(escape(s)) == " ".join(s.split())


def test_parse_bullets_brace_depth_and_unescape():
    src = (
        r"\resumeItem{Improved startup by 40\% via caching}" "\n"
        r"\resumeItem{Nested \emph{group} stays balanced}" "\n"
        r"\section{Skills}"
    )
    assert parse_bullets(src) == [
        "Improved startup by 40% via caching",
        "Nested \\emph{group} stays balanced",
    ]


def test_parse_bullets_handles_escaped_literal_braces():
    # re-review 2 M2: the fixture MUST carry a LONE/unbalanced brace. The earlier draft used a
    # BALANCED `{ … }` pair, so deleting the load-bearing `if c == "\\": pos += 2` skip still
    # extracted correctly — the test could not fail for its own claim. With ONE `{` and no matching
    # `}`, removing the skip makes depth never return to 0 at the wrapper's close, so the extraction
    # over-runs into `\resumeItemListEnd` and the assertion goes red.
    from boardwatch.tailor.render.latex import escape
    body = escape("Config uses { only and 100% coverage")  # lone '{' -> escape() -> \{
    src = f"\\resumeItem{{{body}}}\n\\resumeItemListEnd"
    assert parse_bullets(src) == ["Config uses { only and 100% coverage"]


def _r() -> Resume:
    return Resume(
        header=["Mit Sheth", "houston · m@example.com"],
        education=["MS — NEU — 2025"],
        skill_groups=[SkillGroup(label="Languages", items=["Python", "C/C++"])],
        entries=[
            Entry(entry_id="e1", heading="ignored", kind="experience",
                  title="SWE Co-Op", dates="Jul 2024 – Feb 2025",
                  subtitle="NIO, Northeastern", location="Boston, MA",
                  bullets=[Bullet(bullet_id="b1", text="Cut startup time 40%")]),
            Entry(entry_id="e2", heading="ignored", kind="project",
                  title="Knowledge Forge", dates="Sep 2023 – Dec 2023",
                  subtitle="Python, Django",
                  bullets=[Bullet(bullet_id="b2", text="Built REST APIs on AWS")]),
        ],
    )


def test_emit_is_deterministic():
    from boardwatch.tailor.render.latex import LatexRenderer

    r = _r()
    assert LatexRenderer().emit(r) == LatexRenderer().emit(r)


def test_emit_section_order_and_macros():
    from boardwatch.tailor.render.latex import LatexRenderer

    src = LatexRenderer().emit(_r())
    assert src.index(r"\section{Skills}") < src.index(r"\section{Experience}") < src.index(r"\section{Projects}")
    assert r"\textbf{Languages}: Python, C/C++\\" in src
    assert r"\resumeSubheading" in src and "{SWE Co-Op}{Jul 2024 -- Feb 2025}" in src
    assert r"{NIO, Northeastern}{Boston, MA}" in src
    assert r"\resumeProjectHeading" in src and r"{\textbf{Knowledge Forge} $|$ \emph{Python, Django}}{Sep 2023 -- Dec 2023}" in src


def _project_resume(**entry_overrides) -> Resume:
    base = dict(
        entry_id="p1", heading="ignored", kind="project", title="Hookrail",
        subtitle="Go, PostgreSQL, Redis", dates="June 2026 -- Present",
        bullets=[Bullet(bullet_id="b1", text="Built a webhook service")],
    )
    base.update(entry_overrides)
    return Resume(
        header=["N", "e@example.com"], education=["ed"],
        skill_groups=[SkillGroup(label="L", items=["Python"])],
        entries=[Entry(**base)],
    )


def test_emit_project_heading_includes_href_when_link_present():
    from boardwatch.tailor.render.latex import LatexRenderer

    src = LatexRenderer().emit(
        _project_resume(link_url="https://github.com/mit112/hookrail", link_label="GitHub")
    )
    # URL passes through byte-intact (never escape()d); label is escaped display text; the
    # full heading composes name | tech | link, in that order.
    assert (
        r"{\textbf{Hookrail} $|$ \emph{Go, PostgreSQL, Redis} $|$ "
        r"\href{https://github.com/mit112/hookrail}{\underline{GitHub}}}{June 2026 -- Present}"
    ) in src


def test_emit_project_heading_no_link_composes_name_and_tech_only():
    from boardwatch.tailor.render.latex import LatexRenderer

    # No link fields set: exactly name | tech, no \href and no trailing ' $|$ ' — the full macro
    # call is asserted, which encodes both.
    src = LatexRenderer().emit(_project_resume())
    assert (
        r"\resumeProjectHeading{\textbf{Hookrail} $|$ \emph{Go, PostgreSQL, Redis}}"
        r"{June 2026 -- Present}"
    ) in src


def test_emit_project_heading_link_without_subtitle_has_no_empty_emph():
    from boardwatch.tailor.render.latex import LatexRenderer

    src = LatexRenderer().emit(
        _project_resume(
            title="StreakSync", subtitle=None, dates="2025",
            link_url="https://apps.apple.com/us/app/x/id6755203446", link_label="App Store",
        )
    )
    assert (
        r"{\textbf{StreakSync} $|$ "
        r"\href{https://apps.apple.com/us/app/x/id6755203446}{\underline{App Store}}}{2025}"
    ) in src
    assert r"\emph{}" not in src  # empty tech segment is dropped, not rendered blank


def test_emit_project_heading_escapes_link_label_but_not_url():
    from boardwatch.tailor.render.latex import LatexRenderer

    # The label is display text and must be LaTeX-escaped (unlike "GitHub", `R&D` actually
    # exercises escape()); the URL is emitted verbatim, so its bytes survive intact.
    src = LatexRenderer().emit(
        _project_resume(link_url="https://example.test/r-and-d", link_label="R&D Repo")
    )
    assert r"\href{https://example.test/r-and-d}{\underline{R\&D Repo}}" in src
    assert "R&D Repo" not in src  # the raw, unescaped ampersand never reaches the source


def test_emit_project_heading_url_without_label_emits_no_link_segment():
    from boardwatch.tailor.render.latex import LatexRenderer

    # A directly-constructed Entry can carry link_url without link_label (the declaration forbids
    # it, but the renderer must not emit an empty `\underline{}` and ship an invisible link): the
    # whole link segment is dropped.
    src = LatexRenderer().emit(
        _project_resume(link_url="https://example.test/x", link_label=None)
    )
    assert "https://example.test/x" not in src  # the project's own link_url is never emitted
    assert r"\underline{}" not in src  # and no empty-anchor link is produced


def test_emit_link_in_first_bullet_moves_the_link_from_the_heading_onto_the_first_bullet():
    from boardwatch.tailor.render.latex import LatexRenderer

    src = LatexRenderer().emit(
        _project_resume(
            link_url="https://example.test/r-and-d",
            link_label="R&D Repo",
            link_in_first_bullet=True,
            bullets=[
                Bullet(bullet_id="b1", text="Released 511 datasets."),
                Bullet(bullet_id="b2", text="Wrote the ingestion path"),
            ],
        )
    )
    # The heading composes name | tech ONLY — the link is no longer in it, and there is no
    # trailing ' $|$ ' where it used to sit.
    assert (
        r"\resumeProjectHeading{\textbf{Hookrail} $|$ \emph{Go, PostgreSQL, Redis}}"
        r"{June 2026 -- Present}"
    ) in src
    # Instead the link is appended to the FIRST bullet: one space, URL verbatim, label escaped.
    assert (
        r"\resumeItem{Released 511 datasets. "
        r"\href{https://example.test/r-and-d}{\underline{R\&D Repo}}}"
    ) in src
    # Only the first bullet gets it; the raw, unescaped label never reaches the source.
    assert r"\resumeItem{Wrote the ingestion path}" in src
    assert "R&D Repo" not in src


def test_emit_link_in_first_bullet_off_keeps_the_link_in_the_heading():
    from boardwatch.tailor.render.latex import LatexRenderer

    # Regression: default off ⇒ byte-for-byte the heading-link behaviour, and nothing on the bullet.
    src = LatexRenderer().emit(
        _project_resume(link_url="https://github.com/x/hookrail", link_label="GitHub")
    )
    assert (
        r"\href{https://github.com/x/hookrail}{\underline{GitHub}}}{June 2026 -- Present}"
    ) in src
    assert r"\resumeItem{Built a webhook service}" in src  # bullet unchanged, no appended link


def test_emit_escapes_bullets_and_firewall_roundtrips():
    from boardwatch.tailor.render.latex import LatexRenderer

    src = LatexRenderer().emit(_r())
    assert r"\resumeItem{Cut startup time 40\%}" in src
    assert parse_bullets(src) == ["Cut startup time 40%", "Built REST APIs on AWS"]


def test_emit_fills_sections_marker_only():
    from boardwatch.tailor.render.latex import LatexRenderer

    src = LatexRenderer().emit(_r())
    assert "%%SECTIONS_START%%" in src and "%%SECTIONS_END%%" in src  # markers preserved
    # title/summary left empty in Increment 1
    assert "Backend Software Engineer" not in src


def test_emit_heading_only_entry_does_not_crash():
    from boardwatch.tailor.render.latex import LatexRenderer

    # Blocker-2 regression: default kind="experience", title=None -> must fall back, not escape(None)
    r = Resume(header=["N", "e@example.com"], education=["ed"],
               skill_groups=[SkillGroup(label="L", items=["Python"])],
               entries=[Entry(entry_id="e1", heading="Engineer — Acme — 2020",
                              bullets=[Bullet(bullet_id="b1", text="Did a thing")])])
    src = LatexRenderer().emit(r)
    assert r"\resumeSubheading{Engineer -- Acme -- 2020}{}{}{}" in src  # one-line fallback


def test_emit_zero_bullet_entry_omits_its_item_list():
    """An entry with no bullets must render its subheading but NO \\resumeItemListStart/End pair.
    An itemize with zero \\item is a LaTeX compile error ("missing \\item"), so a bulletless entry
    inside a non-empty section — e.g. a projected project whose contribution facts are not yet
    effective — would otherwise crash the PDF. The section-level guard did not cover the per-entry
    case."""
    from boardwatch.tailor.render.latex import LatexRenderer

    r = Resume(
        header=["N", "e@example.com"],
        education=["ed"],
        skill_groups=[SkillGroup(label="L", items=["Python"])],
        entries=[
            Entry(entry_id="e1", heading="Acme", kind="experience", title="SWE", dates="2020",
                  bullets=[Bullet(bullet_id="b1", text="Did a thing")]),
            Entry(entry_id="e2", heading="SideCo", kind="experience", title="Proj", dates="2021",
                  bullets=[]),
        ],
    )
    src = LatexRenderer().emit(r)
    # The exact empty-itemize pattern that makes tectonic fail with "missing \\item".
    assert "\\resumeItemListStart\n\n\\resumeItemListEnd" not in src
    # The bulleted entry still opens its list; the bulletless one still shows its subheading.
    assert r"\resumeItem{Did a thing}" in src
    assert "{Proj}{2021}" in src


def test_emit_omits_skills_section_when_there_are_no_skill_groups():
    """A résumé with no skill groups omits the Skills section, mirroring the empty-section guard
    the experience/project/extracurricular emitters already apply. A field whose résumé carries no
    skills list (a multi-tenancy case) must not leave a stray empty "Skills" header."""
    from boardwatch.tailor.render.latex import LatexRenderer

    src = LatexRenderer().emit(_r().model_copy(update={"skill_groups": []}))
    assert r"\section{Skills}" not in src
    # present when there are groups
    assert r"\section{Skills}" in LatexRenderer().emit(_r())


def test_emit_extracurricular_section_when_present():
    from boardwatch.tailor.render.latex import LatexRenderer

    r = _r().model_copy(update={"extracurricular": ["Led the winning hackathon team (2022)."]})
    src = LatexRenderer().emit(r)
    assert r"\section{Extracurricular}" in src and "hackathon team" in src
    # absent when empty
    assert r"\section{Extracurricular}" not in LatexRenderer().emit(_r())


def test_emit_reworded_comment_is_inert(tmp_path):
    from boardwatch.tailor.render.latex import LatexRenderer

    src = LatexRenderer().emit(_r(), reworded=frozenset({"b1"}))
    assert "% reworded (Tier B)" in src
    assert parse_bullets(src) == ["Cut startup time 40%", "Built REST APIs on AWS"]  # comment inert


def test_resolve_template_prefers_config_dir(tmp_path):
    from boardwatch.tailor.render.latex import resolve_template

    (tmp_path / "resume_template.tex").write_text(
        "%%SECTIONS_START%%\n%%SECTIONS_END%%\nMY CUSTOM TEMPLATE\n")
    assert "MY CUSTOM TEMPLATE" in resolve_template(tmp_path)
    # bundled default when absent
    assert "%%SECTIONS_START%%" in resolve_template(tmp_path / "nonexistent")


def test_validate_template_rejects_leftover_artifact(tmp_path):
    from boardwatch.tailor.render.latex import TemplateArtifactError, resolve_template

    (tmp_path / "resume_template.tex").write_text(
        "%%SECTIONS_START%%\n%%SECTIONS_END%%\n<placeholder>\n")
    with pytest.raises(TemplateArtifactError):
        resolve_template(tmp_path)


def test_validate_template_rejects_leftover_todo_word(tmp_path):
    from boardwatch.tailor.render.latex import TemplateArtifactError, resolve_template

    (tmp_path / "resume_template.tex").write_text(
        "%%SECTIONS_START%%\n%%SECTIONS_END%%\n% TODO fill in real content\n")
    with pytest.raises(TemplateArtifactError):
        resolve_template(tmp_path)


def test_validate_template_rejects_unrecognized_marker(tmp_path):
    from boardwatch.tailor.render.latex import TemplateArtifactError, resolve_template

    (tmp_path / "resume_template.tex").write_text(
        "%%SECTIONS_START%%\n%%SECTIONS_END%%\n%%BOGUS_START%%\n%%BOGUS_END%%\n")
    with pytest.raises(TemplateArtifactError):
        resolve_template(tmp_path)


def test_validate_template_rejects_missing_sections_markers(tmp_path):
    from boardwatch.tailor.render.latex import TemplateArtifactError, resolve_template

    (tmp_path / "resume_template.tex").write_text("NO MARKERS HERE AT ALL\n")
    with pytest.raises(TemplateArtifactError):
        resolve_template(tmp_path)


def test_emit_renders_escaped_title_when_template_has_the_pair():
    from boardwatch.tailor.render.latex import LatexRenderer

    r = _r().model_copy(update={"title": "iOS & Backend Engineer"})
    src = LatexRenderer().emit(r)  # bundled template carries the TITLE pair
    assert r"iOS \& Backend Engineer" in src  # escaped title present
    # no stray marker survives, regardless of whether a title was injected
    assert "%%TITLE_START%%" not in src and "%%TITLE_END%%" not in src


def test_emit_title_none_renders_no_title_line_and_no_stray_marker():
    from boardwatch.tailor.render.latex import LatexRenderer

    src = LatexRenderer().emit(_r())  # _r() has title=None
    assert "%%TITLE_START%%" not in src and "%%TITLE_END%%" not in src
    # sections markers still survive untouched
    assert "%%SECTIONS_START%%" in src and "%%SECTIONS_END%%" in src


def test_emit_degrades_when_template_lacks_the_title_pair(tmp_path):
    from boardwatch.tailor.render.latex import LatexRenderer

    (tmp_path / "resume_template.tex").write_text(
        "HEADER ONLY\n%%SECTIONS_START%%\n%%SECTIONS_END%%\n"
    )
    r = _r().model_copy(update={"title": "iOS Engineer"})
    src = LatexRenderer(config_dir=tmp_path).emit(r)  # no crash even though title is set
    assert "iOS Engineer" not in src  # nowhere to put it; degrade silently
    assert "%%TITLE" not in src


def test_to_pdf_writes_tex_and_deletes_stale_pdf(tmp_path):
    from boardwatch.tailor.render.latex import LatexRenderer
    from boardwatch.tailor.render.outcome import CompileOutcome, CompileReason

    out_dir = tmp_path / "out"
    out_dir.mkdir()
    stale_pdf = out_dir / "acme.pdf"
    stale_pdf.write_text("stale")

    captured: dict[str, object] = {}

    def fake_runner(tex_path, pdf_path):
        captured["tex_path"] = tex_path
        captured["pdf_path"] = pdf_path
        captured["pdf_existed"] = pdf_path.exists()
        return CompileOutcome(reason=CompileReason.OK, pdf_path=pdf_path, page_count=1, log="")

    outcome = LatexRenderer().to_pdf("SOURCE", out_dir, "acme", fake_runner)

    assert outcome.reason is CompileReason.OK
    assert (out_dir / "acme.tex").read_text() == "SOURCE"
    assert captured["tex_path"] == out_dir / "acme.tex"
    assert captured["pdf_path"] == out_dir / "acme.pdf"
    assert captured["pdf_existed"] is False  # stale pdf deleted before the runner ran

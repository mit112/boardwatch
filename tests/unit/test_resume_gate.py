from __future__ import annotations

from pathlib import Path

import pytest

from boardwatch.reports.resume_gate import (
    BULLET_MAX_LENGTH,
    TEMPLATE_ARTIFACT_TOKENS,
    GateReason,
    LayoutViolation,
    ResumeValidationError,
    contains_template_artifact,
    evaluate_compile,
    validate_layout,
    validate_slots,
)
from boardwatch.tailor.model import Bullet, Entry, Resume, SkillGroup
from boardwatch.tailor.plan import MAX_BULLETS_PER_ENTRY
from boardwatch.tailor.render.latex import LatexRenderer, escape
from boardwatch.tailor.render.outcome import CompileOutcome, CompileReason


def _ok(pages: int = 1) -> CompileOutcome:
    return CompileOutcome(CompileReason.OK, Path("/x/r.pdf"), pages, "log")


def test_ok_within_limit_is_shippable() -> None:
    r = evaluate_compile(_ok(1), max_pages=1)
    assert r.reason is GateReason.OK and r.shippable and r.page_count == 1


def test_fewer_pages_than_limit_is_shippable() -> None:
    assert evaluate_compile(_ok(1), max_pages=2).shippable


def test_over_limit_is_page_limit_exceeded() -> None:
    r = evaluate_compile(_ok(2), max_pages=1)
    assert r.reason is GateReason.PAGE_LIMIT_EXCEEDED and not r.shippable


def test_binary_missing_passes_through() -> None:
    r = evaluate_compile(CompileOutcome(CompileReason.BINARY_MISSING, None, None, ""), max_pages=1)
    assert r.reason is GateReason.BINARY_MISSING and not r.shippable


def test_compile_failed_passes_through() -> None:
    r = evaluate_compile(CompileOutcome(CompileReason.COMPILE_FAILED, None, None, "boom"), max_pages=1)
    assert r.reason is GateReason.COMPILE_FAILED and not r.shippable and r.log == "boom"


def test_compile_outcome_invariant_ok_requires_pdf_and_pages() -> None:
    with pytest.raises(ValueError):
        CompileOutcome(CompileReason.OK, None, 1, "")
    with pytest.raises(ValueError):
        CompileOutcome(CompileReason.OK, Path("/x.pdf"), None, "")
    with pytest.raises(ValueError):
        CompileOutcome(CompileReason.COMPILE_FAILED, Path("/x.pdf"), 1, "")


def _resume(bullets: list[str] | None = None, *, header: list[str] | None = None,
            entries: list[Entry] | None = None) -> Resume:
    ents = entries if entries is not None else [
        Entry(entry_id="e1", heading="Co", bullets=[Bullet(bullet_id="b1", text=t) for t in (bullets or ["did x"])])
    ]
    return Resume(header=header if header is not None else ["Jane"], education=[],
                  skill_groups=[SkillGroup(label="L", items=["Python"])], entries=ents)


def test_validate_slots_passes_a_full_resume() -> None:
    validate_slots(_resume())  # no raise


def test_validate_slots_rejects_empty_header() -> None:
    with pytest.raises(ResumeValidationError):
        validate_slots(_resume(header=[]))


def test_validate_slots_rejects_no_entries() -> None:
    with pytest.raises(ResumeValidationError):
        validate_slots(_resume(entries=[]))


def test_validate_slots_rejects_entry_with_no_bullets() -> None:
    with pytest.raises(ResumeValidationError):
        validate_slots(_resume(entries=[Entry(entry_id="e1", heading="Co", bullets=[])]))


def test_validate_slots_rejects_blank_bullet() -> None:
    with pytest.raises(ResumeValidationError):
        validate_slots(_resume(entries=[Entry(entry_id="e1", heading="Co", bullets=[Bullet(bullet_id="b1", text=" ")])]))


# --- P4 item 5a: validate_layout --------------------------------------------------------

_CLEAN_BULLET_TEXT = "Built a Python service handling 2M requests a day on Kubernetes"


def _clean_bullet(bullet_id: str = "b1", text: str = _CLEAN_BULLET_TEXT) -> Bullet:
    return Bullet(bullet_id=bullet_id, text=text)


def _layout_resume(
    *,
    entries: list[Entry] | None = None,
    header: list[str] | None = None,
    education: list[str] | None = None,
    skill_groups: list[SkillGroup] | None = None,
) -> Resume:
    ents = entries if entries is not None else [
        Entry(entry_id="e1", heading="Senior Engineer — Acme", bullets=[_clean_bullet()])
    ]
    return Resume(
        header=header if header is not None else ["Ada Lovelace", "ada@example.com"],
        education=education if education is not None else ["BSc Mathematics"],
        skill_groups=skill_groups
        if skill_groups is not None
        else [SkillGroup(label="Languages", items=["Python"])],
        entries=ents,
    )


def test_validate_layout_passes_a_clean_resume() -> None:
    r = _layout_resume()
    validate_layout(r, LatexRenderer().emit(r))  # no raise


def test_validate_layout_asserts_resumeitem_roundtrip() -> None:
    r = _layout_resume()  # existing factory (has entries+bullets)
    src = LatexRenderer().emit(r)
    validate_layout(r, src)  # no raise
    tampered = src.replace(escape(r.entries[0].bullets[0].text), "SOMETHING ELSE")
    with pytest.raises(LayoutViolation) as ei:
        validate_layout(r, tampered)
    assert ei.value.reason is GateReason.ESCAPING_MISMATCH


def test_validate_layout_rejects_bullet_too_long() -> None:
    text = "a" * (BULLET_MAX_LENGTH + 1)
    r = _layout_resume(
        entries=[Entry(entry_id="e1", heading="H", bullets=[_clean_bullet(text=text)])]
    )
    with pytest.raises(LayoutViolation) as exc_info:
        validate_layout(r, LatexRenderer().emit(r))
    assert exc_info.value.reason is GateReason.BULLET_TOO_LONG


def test_validate_layout_bullet_max_length_boundary_is_clean() -> None:
    text = "a" * BULLET_MAX_LENGTH
    r = _layout_resume(
        entries=[Entry(entry_id="e1", heading="H", bullets=[_clean_bullet(text=text)])]
    )
    validate_layout(r, LatexRenderer().emit(r))  # no raise


@pytest.mark.parametrize(
    "text",
    [
        "Cut p99 latency 40%",
        "Shipped v2 to 10M users",
        "Led migration to Kubernetes",
    ],
)
def test_validate_layout_accepts_legitimate_short_bullets(text: str) -> None:
    # There is no length FLOOR (coordinator review, footgun fix): a concise, real bullet
    # must never trip the gate — unlike the ceiling, a short bullet renders fine and this
    # gate also runs on the untailored MASTER, so a floor would risk dropping every lead.
    r = _layout_resume(
        entries=[Entry(entry_id="e1", heading="H", bullets=[_clean_bullet(text=text)])]
    )
    validate_layout(r, LatexRenderer().emit(r))  # no raise


def test_validate_layout_rejects_too_many_bullets() -> None:
    bullets = [
        _clean_bullet(bullet_id=f"b{i}") for i in range(MAX_BULLETS_PER_ENTRY + 1)
    ]
    r = _layout_resume(entries=[Entry(entry_id="e1", heading="H", bullets=bullets)])
    with pytest.raises(LayoutViolation) as exc_info:
        validate_layout(r, LatexRenderer().emit(r))
    assert exc_info.value.reason is GateReason.TOO_MANY_BULLETS


def test_validate_layout_bullet_ceiling_boundary_is_clean() -> None:
    bullets = [_clean_bullet(bullet_id=f"b{i}") for i in range(MAX_BULLETS_PER_ENTRY)]
    r = _layout_resume(entries=[Entry(entry_id="e1", heading="H", bullets=bullets)])
    validate_layout(r, LatexRenderer().emit(r))  # no raise


def test_validate_layout_rejects_escaping_mismatch_on_unescaped_bullet() -> None:
    # "&" is a LaTeX special that escape() actually transforms (unlike a plain quote,
    # which LaTeX has no need to escape) — this is what makes the round-trip meaningful.
    text = "Shipped the R&D critical path fix for the checkout flow quickly"
    r = _layout_resume(
        entries=[Entry(entry_id="e1", heading="H", bullets=[_clean_bullet(text=text)])]
    )
    good_source = LatexRenderer().emit(r)
    # Simulate a future emit path that forgot to route this string through escape().
    bad_source = good_source.replace(escape(text), text)
    assert bad_source != good_source
    with pytest.raises(LayoutViolation) as exc_info:
        validate_layout(r, bad_source)
    assert exc_info.value.reason is GateReason.ESCAPING_MISMATCH


def test_validate_layout_accepts_a_correctly_escaped_ampersand() -> None:
    text = "Shipped the R&D critical path fix for the checkout flow quickly"
    r = _layout_resume(
        entries=[Entry(entry_id="e1", heading="H", bullets=[_clean_bullet(text=text)])]
    )
    validate_layout(r, LatexRenderer().emit(r))  # no raise


def test_validate_layout_rejects_template_artifact_in_bullet() -> None:
    text = "TODO rewrite this bullet with a real accomplishment and metric"
    r = _layout_resume(
        entries=[Entry(entry_id="e1", heading="H", bullets=[_clean_bullet(text=text)])]
    )
    with pytest.raises(LayoutViolation) as exc_info:
        validate_layout(r, LatexRenderer().emit(r))
    assert exc_info.value.reason is GateReason.TEMPLATE_ARTIFACT


def test_validate_layout_rejects_template_artifact_in_link_label() -> None:
    # A link_label renders as visible `\underline{}` text, so it is scanned like any other
    # heading field: a placeholder label must be refused, not shipped as a live clickable link.
    r = _layout_resume(
        entries=[
            Entry(
                entry_id="p1", heading="Proj", kind="project", title="Proj",
                subtitle="Go", dates="2026",
                link_url="https://example.test/p", link_label="TODO add the real link",
                bullets=[_clean_bullet()],
            )
        ]
    )
    with pytest.raises(LayoutViolation) as exc_info:
        validate_layout(r, LatexRenderer().emit(r))
    assert exc_info.value.reason is GateReason.TEMPLATE_ARTIFACT


def _link_in_first_bullet_resume() -> Resume:
    # F1 (link_in_first_bullet): a project entry that renders its declared link INSIDE the first
    # bullet's \resumeItem{...} instead of the heading. Two bullets so "only the first gets it"
    # is exercised; an "&" in the label makes the escape() round-trip meaningful.
    return _layout_resume(
        entries=[
            Entry(
                entry_id="p1", heading="Hookrail", kind="project", title="Hookrail",
                subtitle="Go, PostgreSQL", dates="2026",
                link_url="https://example.test/r-and-d", link_label="R&D Repo",
                link_in_first_bullet=True,
                bullets=[
                    _clean_bullet(bullet_id="b1", text="Released 511 datasets to production"),
                    _clean_bullet(bullet_id="b2", text="Wrote the ingestion path end to end"),
                ],
            )
        ]
    )


def test_validate_layout_passes_a_link_in_first_bullet_render() -> None:
    # The interaction bug: the renderer appends the link inside the first \resumeItem{...}, so a
    # firewall that expected the bare \resumeItem{<text>} raised ESCAPING_MISMATCH and silently
    # degraded the lead to the untailored master. This must PASS on the real render.
    r = _link_in_first_bullet_resume()
    validate_layout(r, LatexRenderer().emit(r))  # no raise


def test_validate_layout_link_in_first_bullet_still_catches_a_tampered_href() -> None:
    # The firewall must still bite: a first-bullet href pointing anywhere other than the declared
    # link (a fabricated/mismatched URL) fails ESCAPING_MISMATCH — the fix reconstructs the exact
    # expected substring, it does not merely loosen the check.
    r = _link_in_first_bullet_resume()
    src = LatexRenderer().emit(r)
    tampered = src.replace("https://example.test/r-and-d", "https://evil.test/phish")
    assert tampered != src
    with pytest.raises(LayoutViolation) as exc_info:
        validate_layout(r, tampered)
    assert exc_info.value.reason is GateReason.ESCAPING_MISMATCH


def test_validate_layout_link_in_first_bullet_still_catches_altered_first_bullet_text() -> None:
    # Altering the first bullet's TEXT (the part before the appended link) must also fail: the
    # escaped-text round-trip still holds inside the reconstructed substring.
    r = _link_in_first_bullet_resume()
    src = LatexRenderer().emit(r)
    tampered = src.replace(
        escape("Released 511 datasets to production"), "Released 999 datasets to production"
    )
    assert tampered != src
    with pytest.raises(LayoutViolation) as exc_info:
        validate_layout(r, tampered)
    assert exc_info.value.reason is GateReason.ESCAPING_MISMATCH


def test_contains_template_artifact_detects_double_brace() -> None:
    assert contains_template_artifact("Worked on {{company}} launch project") == "{{"


def test_contains_template_artifact_is_case_insensitive() -> None:
    assert contains_template_artifact("todo: fix this bullet") == "TODO"


def test_contains_template_artifact_returns_none_for_clean_text() -> None:
    assert contains_template_artifact(_CLEAN_BULLET_TEXT) is None


@pytest.mark.parametrize(
    "text",
    [
        "Built a Todo-list app with 50K downloads",
        "Shipped a TodoMVC-based tool for the release team",
    ],
)
def test_contains_template_artifact_does_not_flag_hyphenated_product_names(text: str) -> None:
    # Coordinator review, false positive: a plain substring match fired inside legitimate
    # product/framework names. A word-like token must only fire standalone.
    assert contains_template_artifact(text) is None


def test_contains_template_artifact_still_flags_standalone_todo() -> None:
    assert contains_template_artifact("standalone TODO here") == "TODO"


@pytest.mark.parametrize("token", TEMPLATE_ARTIFACT_TOKENS)
def test_contains_template_artifact_catches_every_catalog_token(token: str) -> None:
    assert contains_template_artifact(f"prefix {token} suffix") == token


def test_validate_slots_accepts_a_declared_bulletless_entry() -> None:
    """D-221's third state: an entry that DECLARES it has no bullets renders as role +
    organisation + dates only. `test_validate_slots_rejects_entry_with_no_bullets` above is the
    control — the identical entry without the declaration is still refused, so relaxing this arm
    did not turn an accidental omission into a silent one."""
    validate_slots(
        _resume(entries=[Entry(entry_id="e1", heading="Co", bullets=[], bulletless=True)])
    )

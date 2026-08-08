"""Keyword-coverage measurement (P4 item 6) — the pure half.

Coverage is a REPORT, never a veto: nothing here changes whether a lead is kept, dropped,
or degraded. The load-bearing claims (derived from the brief, not from the code):

  1. The denominator is the JD's *requirement* terms — the qualifications span when a header
     exists, the whole body otherwise, and the report says which.
  2. The numerator counts only skills the MASTER résumé genuinely has (its bullets +
     skill_groups items), never the tailored output. A requirement term that appears in a
     tailored bullet but not the master must read as MISSING — the anti-echo guarantee.
  3. `fraction` is `None`, never `0.0`, when the JD has zero recognized requirement terms.
"""

from __future__ import annotations

from pathlib import Path

from boardwatch.extract.taxonomy import Taxonomy, load_taxonomy
from boardwatch.tailor.coverage import (
    CoverageReport,
    coverage_report,
    requirement_terms,
    resume_fact_skills,
)
from boardwatch.tailor.model import Bullet, Entry, Resume, SkillGroup

BUNDLED = Path("does-not-exist")  # no override dir: load_taxonomy falls back to the bundled yaml


def _taxonomy() -> Taxonomy:
    return load_taxonomy(BUNDLED)


# -- requirement_terms: denominator source ------------------------------------------


def test_qualifications_span_is_the_denominator_when_a_header_exists() -> None:
    tax = _taxonomy()
    body = (
        "About the role. We move fast.\n"
        "Requirements:\n"
        "- Strong Python experience\n"
        "- Kubernetes in production\n"
        "Benefits:\n"
        "- Free lunch and a Rust mechanical keyboard\n"
    )
    terms, source = requirement_terms(body, tax)
    assert source == "qualifications"
    assert "Python" in terms
    assert "Kubernetes" in terms
    # Rust is under Benefits, OUTSIDE the qualifications span, so it is not a requirement term.
    assert "Rust" not in terms


def test_body_fallback_when_no_qualifications_header() -> None:
    tax = _taxonomy()
    body = "We build backend systems in Python and deploy them on Kubernetes."
    terms, source = requirement_terms(body, tax)
    assert source == "body"
    assert terms == frozenset({"Python", "Kubernetes"})


def test_empty_jd_yields_empty_terms_without_crashing() -> None:
    tax = _taxonomy()
    terms, source = requirement_terms("", tax)
    assert terms == frozenset()
    assert source == "body"


# -- resume_fact_skills: bullets AND skill_groups, never prose ----------------------


def test_resume_fact_skills_reads_bullets_and_skill_groups_only() -> None:
    tax = _taxonomy()
    master = Resume(
        # Header and education prose mention Django and React; neither is a real skill fact
        # and both must be ignored — only bullets and skill_groups count.
        header=["Jane Dev — Django wizard"],
        education=["BSc — React University — 2020"],
        skill_groups=[SkillGroup(label="Languages", items=["Python"])],
        entries=[
            Entry(
                entry_id="e1",
                heading="Engineer — Acme",
                bullets=[Bullet(bullet_id="b1", text="Ran Kubernetes clusters at scale")],
            )
        ],
    )
    skills = resume_fact_skills(master, tax)
    assert skills == frozenset({"Python", "Kubernetes"})


# -- coverage_report: the anti-echo guarantee (most important) ----------------------


def _master_with_python_only() -> Resume:
    return Resume(
        header=["Jane Dev"],
        education=["BSc — Example — 2020"],
        skill_groups=[SkillGroup(label="Languages", items=["Python"])],
        entries=[
            Entry(
                entry_id="e1",
                heading="Engineer — Acme",
                bullets=[Bullet(bullet_id="b1", text="Shipped a Python service")],
            )
        ],
    )


def _tailored_that_echoes_kubernetes() -> Resume:
    return Resume(
        header=["Jane Dev"],
        education=["BSc — Example — 2020"],
        skill_groups=[SkillGroup(label="Languages", items=["Python"])],
        entries=[
            Entry(
                entry_id="e1",
                heading="Engineer — Acme",
                # Kubernetes appears here but NOT in the master above.
                bullets=[Bullet(bullet_id="b1", text="Shipped a Python service on Kubernetes")],
            )
        ],
    )


def test_requirement_present_only_in_tailored_output_is_reported_missing() -> None:
    tax = _taxonomy()
    jd_terms = frozenset({"Python", "Kubernetes"})

    master_skills = resume_fact_skills(_master_with_python_only(), tax)
    report = coverage_report(jd_terms, master_skills, "qualifications")

    assert report.covered == ("Python",)
    assert report.missing == ("Kubernetes",)
    assert report.covered_count == 1
    assert report.total_count == 2
    assert report.fraction == 0.5

    # RED guard: computing coverage against the TAILORED résumé (the bug this test forbids)
    # would flip Kubernetes from missing to covered. Proving the two disagree is what makes the
    # anti-echo guarantee falsifiable rather than incidental.
    tailored_skills = resume_fact_skills(_tailored_that_echoes_kubernetes(), tax)
    wrong = coverage_report(jd_terms, tailored_skills, "qualifications")
    assert "Kubernetes" in wrong.covered
    assert "Kubernetes" in report.missing  # the correct, master-based report


# -- coverage_report: fraction is None, never 0.0, on an empty denominator ----------


def test_fraction_is_none_when_no_requirement_terms() -> None:
    report = coverage_report(frozenset(), frozenset({"Python"}), "body")
    assert report.total_count == 0
    # None, NOT 0.0: a 0.0 would falsely assert "covers none of many requirements".
    assert report.fraction is None


def test_fraction_is_zero_not_none_when_terms_exist_but_none_covered() -> None:
    report = coverage_report(frozenset({"Python"}), frozenset(), "body")
    assert report.total_count == 1
    assert report.fraction == 0.0
    assert isinstance(report, CoverageReport)

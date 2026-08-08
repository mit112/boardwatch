"""Keyword-coverage measurement for tailored résumés (P4 item 6).

A per-lead REPORT, never a veto: nothing in this module changes whether a lead is kept,
dropped, or degraded. It answers one question — of the requirement terms a JD asks for, how
many does the applicant's real résumé actually have — and it answers it honestly, which is
why four rules are load-bearing:

  * **Denominator = the JD's requirement terms.** Extracted from the qualifications span
    (`requirement_echo.qualifications_span`, already tuned to find that section); when the JD
    has no recognizable qualifications header the whole body is the fallback, and the report
    records which source it used so a reader is never guessing.
  * **Numerator counts only the MASTER résumé's real skills** — its bullets and skill_groups
    items, never the tailored output. This is the anti-echo guarantee: a requirement term that
    a tailored bullet happens to mention but the master does not genuinely carry must read as
    MISSING, not covered. Coverage measured against the tailored résumé would be a mirror.
  * **Re-spelling is the taxonomy's job.** `Taxonomy.extract` returns canonical skill names
    (its patterns already fold JS/JavaScript and the like onto one name), so coverage is a set
    intersection of canonical names — no second alias pass.
  * **`fraction` is `None`, never `0.0`, when the JD names zero recognized requirement terms.**
    A 0.0 would falsely assert "covers none of many requirements"; `None` says "nothing to
    measure against".
"""

from __future__ import annotations

from dataclasses import dataclass

from boardwatch.extract.taxonomy import Taxonomy
from boardwatch.tailor.model import Resume
from boardwatch.tailor.requirement_echo import qualifications_span


@dataclass(frozen=True)
class CoverageReport:
    covered: tuple[str, ...]  # sorted canonical skill names covered
    missing: tuple[str, ...]  # sorted requirement terms NOT covered
    denominator_source: str  # "qualifications" | "body"
    covered_count: int
    total_count: int
    fraction: float | None  # covered/total; None iff total_count == 0


def requirement_terms(jd_body_text: str, taxonomy: Taxonomy) -> tuple[frozenset[str], str]:
    """The JD's requirement terms as canonical skill names, and which source they came from.

    The qualifications span when a header exists, the whole body otherwise. An empty span (no
    header) is the fallback trigger, never an error; an empty body simply yields no terms.
    """
    span = qualifications_span(jd_body_text)
    if span:
        return frozenset(taxonomy.extract("\n".join(span))), "qualifications"
    return frozenset(taxonomy.extract(jd_body_text)), "body"


def resume_fact_skills(master: Resume, taxonomy: Taxonomy) -> frozenset[str]:
    """Canonical skills the MASTER résumé genuinely has: extracted from its bullets and
    skill_groups items only. Header/education prose is deliberately excluded — a name-drop in a
    summary line is not a demonstrated skill fact."""
    parts = [b.text for e in master.entries for b in e.bullets]
    parts += [item for group in master.skill_groups for item in group.items]
    return frozenset(taxonomy.extract("\n".join(parts)))


def coverage_report(
    jd_requirement_skills: frozenset[str],
    resume_skills: frozenset[str],
    denominator_source: str,
) -> CoverageReport:
    """Intersect the JD's canonical requirement terms with the résumé's canonical skills. Pure."""
    covered = tuple(sorted(jd_requirement_skills & resume_skills))
    missing = tuple(sorted(jd_requirement_skills - resume_skills))
    total_count = len(jd_requirement_skills)
    covered_count = len(covered)
    # None, never 0.0, over an empty denominator — a fraction of zero requirements is undefined.
    fraction = None if total_count == 0 else covered_count / total_count
    return CoverageReport(
        covered=covered,
        missing=missing,
        denominator_source=denominator_source,
        covered_count=covered_count,
        total_count=total_count,
        fraction=fraction,
    )


def coverage_to_dict(report: CoverageReport | None) -> dict[str, object] | None:
    """Serialize a report for an artifact/JSON payload. `None` in, `None` out — a measurement
    that failed or never ran is recorded as absent, never as a fabricated zero."""
    if report is None:
        return None
    return {
        "covered": list(report.covered),
        "missing": list(report.missing),
        "denominator_source": report.denominator_source,
        "covered_count": report.covered_count,
        "total_count": report.total_count,
        "fraction": report.fraction,
    }

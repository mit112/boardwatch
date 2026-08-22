"""The run-scoped morning artifact — PROGRAM.md §3.P3 **item 7**.

This is Mit's actionable daily surface: for each lead this run tailored, where to apply, where
the PDF landed, the honest verdict label, and the strongest piece of evidence behind it — the
thing `bw-daily`'s per-lead `apply.txt` did, unified with eligibility and rendered once per run
instead of once per folder.

**Deliberately sourced from the same population as the funnel (P0 item 1), never from
`digest`/`notify`.** Those two are cursor-scoped ("new since I last looked") — a different
population from "every lead this run tailored". Sourcing the morning artifact from them would
silently drop a re-tailored lead whose posting was not `new` this run, and the funnel's own
docstrings already warn against exactly this population confusion.

**Links to the funnel rather than restating it.** The funnel is the reconciliation artifact —
counts, drops, cross-checks. Repeating any of that here would create two numbers for one fact,
which drifts the moment either writer changes without the other. This module carries only what
the funnel deliberately does not: apply URL, verdict, evidence span, ranking rationale.

Every field renders honestly when the underlying fact is absent — a lead with no PDF, no URL, or
no resolvable evidence quote says so in the render rather than leaving a blank or crashing. A
blank reads as "nothing to see here"; this artifact exists so a missing fact is as visible as a
present one.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from boardwatch.reports.board_coverage import CoverageReport as BoardCoverageReport
from boardwatch.reports.board_coverage import (
    board_coverage_headline,
    board_coverage_to_dict,
)
from boardwatch.reports.run_funnel import WrittenArtifact
from boardwatch.tailor.coverage import CoverageReport, coverage_to_dict

# v2 adds the run-level `board_coverage` block (D-274) — how much of each watched board
# boardwatch can actually see. It is the one number in this file that is NOT about a lead,
# and it is here because this is the file the operator opens: a run that surfaced 40 good
# leads out of a corpus covering 82% of its boards is a different morning from the same 40
# leads out of 40%, and nothing unattended used to say which one had happened.
#
# This does NOT breach the module docstring's rule against restating the funnel. The rule
# exists to stop two WRITERS computing one fact and drifting; here the caller loads the
# report once and hands the same object to both artifacts, so there is one computation and
# one number. It is rendered as `## Discovery reach`, never as the bare word `coverage`,
# because every lead below already prints a `coverage:` line meaning resume keyword
# coverage — the two must not read as the same measurement.
ARTIFACT_VERSION = 2


@dataclass(frozen=True)
class MorningLead:
    """One tailored lead, ranked-order, with everything Mit needs to act on it this morning.

    `verdict_label` is `AuditView.presentation` (D-036) — the honest `eligible_cleared` /
    `eligible_mixed` / ... label, never the bare stored `verdict` — so "eligible" here never
    overclaims a row that fired but did not clear. `evidence_kind`/`evidence_text` are the
    strongest cleared requirement's quote, or (when none clears with a usable quote) the
    eligibility rationale; both are `None` together when nothing is available, which renders as
    an honest "no evidence recorded" rather than a fabricated span.
    """

    posting_id: int
    title: str
    company: str
    board: str
    score: float
    why: str
    verdict_label: str
    apply_url: str | None
    pdf_path: str | None
    evidence_kind: str | None
    evidence_text: str | None
    # P4 item 6: keyword coverage of the JD's requirement terms against Mit's real résumé. A
    # report, not a gate — `None` when it could not be measured, which renders honestly below.
    coverage: CoverageReport | None = None


@dataclass(frozen=True)
class MorningArtifact:
    run_id: int
    funnel_name: str
    leads: tuple[MorningLead, ...]
    # `None` means the coverage load FAILED, not that coverage is zero (D-274).
    board_coverage: BoardCoverageReport | None = None


def build_morning(
    *,
    run_id: int,
    funnel_name: str,
    leads: Sequence[MorningLead],
    board_coverage: BoardCoverageReport | None = None,
) -> MorningArtifact:
    """Assemble the artifact from already-built lead rows. Pure: no engine, no clock, no I/O.

    Ranked by score, descending — the read order for a list Mit works top to bottom. A tie
    keeps the caller's original relative order (`sorted` is stable).
    """
    ordered = tuple(sorted(leads, key=lambda lead: lead.score, reverse=True))
    return MorningArtifact(
        run_id=run_id,
        funnel_name=funnel_name,
        leads=ordered,
        board_coverage=board_coverage,
    )


def morning_to_dict(artifact: MorningArtifact) -> dict[str, object]:
    return {
        "artifact_version": ARTIFACT_VERSION,
        "run_id": artifact.run_id,
        "funnel": artifact.funnel_name,
        "board_coverage": board_coverage_to_dict(artifact.board_coverage),
        "leads": [
            {
                "posting_id": lead.posting_id,
                "title": lead.title,
                "company": lead.company,
                "board": lead.board,
                "score": lead.score,
                "why": lead.why,
                "verdict_label": lead.verdict_label,
                "apply_url": lead.apply_url,
                "pdf_path": lead.pdf_path,
                "evidence_kind": lead.evidence_kind,
                "evidence_text": lead.evidence_text,
                "coverage": coverage_to_dict(lead.coverage),
            }
            for lead in artifact.leads
        ],
    }


def _fmt_url(url: str | None) -> str:
    return url if url else "no URL on record"


def _fmt_pdf(pdf_path: str | None) -> str:
    return pdf_path if pdf_path else "no PDF (see funnel for why)"


def _fmt_evidence(kind: str | None, text: str | None) -> str:
    if not text:
        return "no evidence recorded"
    if kind == "quote":
        return f'"{text}"'
    return f"rationale: {text}"


def _fmt_coverage(coverage: CoverageReport | None) -> str:
    """`covers N/M requirement terms (source)`, or an honest absence. When the JD names zero
    recognized requirements (`fraction is None`) we say so rather than printing `0/0`."""
    if coverage is None:
        return "not measured"
    if coverage.fraction is None:
        return f"no recognized requirements in JD {coverage.denominator_source}"
    line = (
        f"covers {coverage.covered_count}/{coverage.total_count} requirement terms "
        f"({coverage.denominator_source})"
    )
    if coverage.missing:
        line += f"\n- **missing:** {', '.join(coverage.missing)}"
    return line


def morning_to_markdown(artifact: MorningArtifact) -> str:
    lines = [
        f"# boardwatch run {artifact.run_id} — morning",
        "",
        f"Full accounting (counts, drops, cross-checks): see `{artifact.funnel_name}`.",
        "",
        f"{len(artifact.leads)} lead(s) tailored this run, ranked by score.",
        "",
        "## Discovery reach",
        "",
    ]
    # Rendered BEFORE the zero-lead return: a morning with no leads is precisely when the
    # operator needs to know whether discovery collapsed or the market was merely quiet.
    # Titled "Discovery reach", never "coverage" — each lead below prints its own
    # `coverage:` line meaning something entirely different.
    lines += board_coverage_headline(artifact.board_coverage)
    lines += [f"Per-board detail: `{artifact.funnel_name}`.", ""]
    if not artifact.leads:
        lines.append("none.")
        return "\n".join(lines) + "\n"

    for rank, lead in enumerate(artifact.leads, start=1):
        lines += [
            f"## {rank}. {lead.company} — {lead.title}",
            "",
            f"- **board:** {lead.board}",
            f"- **score:** {lead.score:.3f}",
            f"- **verdict:** {lead.verdict_label}",
            f"- **apply:** {_fmt_url(lead.apply_url)}",
            f"- **résumé PDF:** {_fmt_pdf(lead.pdf_path)}",
            f"- **evidence:** {_fmt_evidence(lead.evidence_kind, lead.evidence_text)}",
            f"- **coverage:** {_fmt_coverage(lead.coverage)}",
            f"- **why ranked here:** {lead.why}",
            "",
        ]
    return "\n".join(lines) + "\n"


def write_morning(artifact: MorningArtifact, out_dir: Path) -> WrittenArtifact:
    """Write both halves under `out_dir`, named by run, beside the funnel.

    Written OUTSIDE the git tree, for the same reason as the funnel (D-024 / R7): a per-run
    artifact can never carry a sha256-pinned SHIPPED_DATA entry.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"morning-{artifact.run_id}.json"
    markdown_path = out_dir / f"morning-{artifact.run_id}.md"
    json_path.write_text(json.dumps(morning_to_dict(artifact), indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(morning_to_markdown(artifact), encoding="utf-8")
    return WrittenArtifact(json_path=json_path, markdown_path=markdown_path)


__all__ = [
    "ARTIFACT_VERSION",
    "MorningArtifact",
    "MorningLead",
    "build_morning",
    "morning_to_dict",
    "morning_to_markdown",
    "write_morning",
]

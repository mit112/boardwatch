"""The run-scoped morning artifact (P3 item 7) — the pure half.

Mirrors `tests/unit/test_run_funnel.py`'s split: fabricated `MorningLead` rows in, `md`/`json`
out, no engine and no store. What matters here is that every column the design promises
(apply URL, PDF path, verdict label, evidence span, ranking why) actually renders, and that a
lead missing any one of those facts renders HONESTLY — a named absence, never a blank and never
a crash.
"""

from __future__ import annotations

import json
from pathlib import Path

from boardwatch.reports.board_coverage import BoardCoverage
from boardwatch.reports.board_coverage import build_report as build_board_report
from boardwatch.reports.morning import (
    ARTIFACT_VERSION,
    MorningLead,
    build_morning,
    morning_to_dict,
    morning_to_markdown,
    write_morning,
)


def lead(
    posting_id: int = 7,
    *,
    score: float = 0.5,
    apply_url: str | None = "https://example.test/apply",
    pdf_path: str | None = "/out/2026-08-07/acme-7/resume.pdf",
    evidence_kind: str | None = "quote",
    evidence_text: str | None = "3+ years of Python",
    verdict_label: str = "eligible_cleared",
) -> MorningLead:
    return MorningLead(
        posting_id=posting_id,
        title="Backend Engineer",
        company="Acme",
        board="greenhouse:acme",
        score=score,
        why="skills match: Python, Go",
        verdict_label=verdict_label,
        apply_url=apply_url,
        pdf_path=pdf_path,
        evidence_kind=evidence_kind,
        evidence_text=evidence_text,
    )


def test_build_morning_ranks_by_score_descending() -> None:
    low = lead(posting_id=1, score=0.2)
    high = lead(posting_id=2, score=0.9)
    mid = lead(posting_id=3, score=0.5)

    artifact = build_morning(run_id=42, funnel_name="funnel-42.md", leads=[low, high, mid])

    assert [lead.posting_id for lead in artifact.leads] == [2, 3, 1]


def test_dict_carries_every_promised_column() -> None:
    artifact = build_morning(run_id=42, funnel_name="funnel-42.md", leads=[lead()])
    payload = morning_to_dict(artifact)

    assert payload["run_id"] == 42
    assert payload["funnel"] == "funnel-42.md"
    (row,) = payload["leads"]
    for key in (
        "posting_id",
        "title",
        "company",
        "board",
        "score",
        "why",
        "verdict_label",
        "apply_url",
        "pdf_path",
        "evidence_kind",
        "evidence_text",
    ):
        assert key in row, f"missing column: {key}"
    assert row["apply_url"] == "https://example.test/apply"
    assert row["verdict_label"] == "eligible_cleared"
    assert row["evidence_text"] == "3+ years of Python"


def test_markdown_links_the_funnel_rather_than_restating_it() -> None:
    artifact = build_morning(run_id=42, funnel_name="funnel-42.md", leads=[lead()])
    rendered = morning_to_markdown(artifact)

    assert "funnel-42.md" in rendered
    # The accounting words that belong to the FUNNEL, not this artifact.
    assert "reconcil" not in rendered.lower()


def test_markdown_carries_apply_url_verdict_pdf_and_evidence() -> None:
    artifact = build_morning(run_id=42, funnel_name="funnel-42.md", leads=[lead()])
    rendered = morning_to_markdown(artifact)

    assert "https://example.test/apply" in rendered
    assert "eligible_cleared" in rendered
    assert "/out/2026-08-07/acme-7/resume.pdf" in rendered
    assert "3+ years of Python" in rendered
    assert "skills match: Python, Go" in rendered


def test_a_lead_missing_url_pdf_and_evidence_renders_honestly_not_a_blank() -> None:
    """No URL / no PDF / no evidence must say so, not crash, not print an empty cell."""
    bare = lead(
        posting_id=9,
        apply_url=None,
        pdf_path=None,
        evidence_kind=None,
        evidence_text=None,
        verdict_label="uncertain",
    )
    artifact = build_morning(run_id=1, funnel_name="funnel-1.md", leads=[bare])

    rendered = morning_to_markdown(artifact)
    payload = morning_to_dict(artifact)

    assert payload["leads"][0]["apply_url"] is None
    assert payload["leads"][0]["pdf_path"] is None
    assert payload["leads"][0]["evidence_text"] is None
    assert "no URL on record" in rendered
    assert "no PDF" in rendered
    assert "no evidence recorded" in rendered
    # Never a bare colon-then-nothing — every honest fallback names the absence.
    assert "**apply:** \n" not in rendered
    assert "**résumé PDF:** \n" not in rendered


def test_no_leads_renders_none_not_an_empty_table() -> None:
    artifact = build_morning(run_id=5, funnel_name="funnel-5.md", leads=[])
    rendered = morning_to_markdown(artifact)
    assert "none." in rendered


def test_write_morning_names_both_halves_by_run_id(tmp_path: Path) -> None:
    artifact = build_morning(run_id=13, funnel_name="funnel-13.md", leads=[lead()])
    written = write_morning(artifact, tmp_path)

    assert written.json_path == tmp_path / "morning-13.json"
    assert written.markdown_path == tmp_path / "morning-13.md"
    assert written.json_path.exists()
    assert written.markdown_path.exists()
    assert json.loads(written.json_path.read_text())["run_id"] == 13


# --------------------------------------------------------------------------------------
# Discovery reach (D-274) — the one block in this file that is not about a lead
# --------------------------------------------------------------------------------------


def _reach(held: int = 500, stated: int = 1000) -> object:
    return build_board_report(
        [
            BoardCoverage(
                company_id=1,
                name="Acme",
                provider="greenhouse",
                bucket="measured",
                held=held,
                board_reported_total=stated,
                board_enumerated=stated,
                detail_deferred=0,
                shortfall=stated - held,
                ratio=held / stated,
            )
        ]
    )


def test_the_artifact_version_is_bumped_for_the_discovery_reach_block() -> None:
    """v1 had no version-history test at all, so nothing would have caught a silent bump. v2
    adds the run-level `board_coverage` block — a new top-level section, not an additive key
    inside one."""
    assert ARTIFACT_VERSION == 2
    artifact = build_morning(run_id=1, funnel_name="funnel-1.md", leads=[lead()])
    assert morning_to_dict(artifact)["artifact_version"] == 2


def test_discovery_reach_renders_for_the_operator() -> None:
    artifact = build_morning(
        run_id=1, funnel_name="funnel-1.md", leads=[lead()], board_coverage=_reach()
    )

    rendered = morning_to_markdown(artifact)

    assert "## Discovery reach" in rendered
    assert "50.0%" in rendered
    # Points at the funnel for the 135-row table rather than restating it here.
    assert "Per-board detail: `funnel-1.md`" in rendered


def test_discovery_reach_is_never_titled_coverage() -> None:
    """Every lead below already prints a `coverage:` line meaning resume KEYWORD coverage. A
    second, unrelated measurement under the same word in the same document is the collision
    the design flagged, made worse: in JSON they are two keys, but on the page a human reads
    one word twice."""
    artifact = build_morning(
        run_id=1, funnel_name="funnel-1.md", leads=[lead()], board_coverage=_reach()
    )

    rendered = morning_to_markdown(artifact)

    assert "## Discovery reach" in rendered
    assert "## Coverage" not in rendered
    assert "## coverage" not in rendered
    # The per-lead keyword line is untouched and still means what it always did.
    assert "- **coverage:**" in rendered


def test_a_zero_lead_morning_still_reports_discovery_reach() -> None:
    """THE case this block exists for. A morning with no leads is exactly when the operator
    needs to know whether discovery collapsed or the market was merely quiet — and the
    zero-lead path used to return before anything else could render."""
    artifact = build_morning(
        run_id=1, funnel_name="funnel-1.md", leads=[], board_coverage=_reach()
    )

    rendered = morning_to_markdown(artifact)

    assert "## Discovery reach" in rendered
    assert "50.0%" in rendered
    assert "none." in rendered


def test_discovery_reach_says_not_measured_rather_than_vanishing() -> None:
    artifact = build_morning(run_id=1, funnel_name="funnel-1.md", leads=[lead()])

    rendered = morning_to_markdown(artifact)

    assert "## Discovery reach" in rendered
    assert "not measured this run" in rendered
    assert morning_to_dict(artifact)["board_coverage"] is None

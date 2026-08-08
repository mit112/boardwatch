"""Pure reconciliation core (P0 item 5).

These tests fabricate inputs: the pure builder cannot catch a wrong JOIN (that is the
query task's job), only a wrong COMPARISON. Each test perturbs exactly one input and
asserts the specific typed DiscrepancyKind AND that `ok` flips to False.
"""

from __future__ import annotations

from boardwatch.reports.reconcile import (
    ArtifactCounts,
    DbCounts,
    DiscrepancyKind,
    FileCheck,
    reconcile,
    reconcile_to_dict,
    reconcile_to_markdown,
)


def _artifact(**kw: object) -> ArtifactCounts:
    base = dict(tailored_rows=2, tailored_with_pdf=2, lead_count=2, status="ok")
    base.update(kw)
    return ArtifactCounts(**base)  # type: ignore[arg-type]


def _db(**kw: object) -> DbCounts:
    base = dict(tailored_rows=2, tailored_with_pdf=2, distinct_lead_postings=2, run_status="ok")
    base.update(kw)
    return DbCounts(**base)  # type: ignore[arg-type]


def _typ(kind: str = "resume_tailored", *, typ_exists: bool = True,
         pdf_expected: bool = True, pdf_exists: bool = True) -> FileCheck:
    return FileCheck(
        kind=kind, typ_uri="/leads/a.tex", typ_exists=typ_exists,
        pdf_expected=pdf_expected, pdf_uri="/leads/a.pdf", pdf_exists=pdf_exists,
    )


def _kinds(report) -> set[DiscrepancyKind]:
    return {d.kind for d in report.discrepancies}


def test_fully_agreeing_inputs_reconcile() -> None:
    report = reconcile(run_id=7, artifact=_artifact(), db=_db(), files=[_typ(), _typ()])
    assert report.ok
    assert report.discrepancies == ()


def test_tailored_row_count_mismatch() -> None:
    report = reconcile(run_id=7, artifact=_artifact(tailored_rows=3), db=_db(), files=[])
    assert not report.ok
    assert _kinds(report) == {DiscrepancyKind.TAILORED_COUNT_MISMATCH}


def test_pdf_count_mismatch() -> None:
    report = reconcile(run_id=7, artifact=_artifact(tailored_with_pdf=1), db=_db(), files=[])
    assert not report.ok
    assert _kinds(report) == {DiscrepancyKind.PDF_COUNT_MISMATCH}


def test_lead_count_mismatch() -> None:
    report = reconcile(run_id=7, artifact=_artifact(lead_count=5), db=_db(), files=[])
    assert not report.ok
    assert _kinds(report) == {DiscrepancyKind.LEAD_COUNT_MISMATCH}


def test_status_mismatch() -> None:
    report = reconcile(run_id=7, artifact=_artifact(status="ok"), db=_db(run_status="failed"),
                       files=[])
    assert not report.ok
    assert _kinds(report) == {DiscrepancyKind.STATUS_MISMATCH}


def test_status_check_skipped_for_v2_artifact_without_manifest() -> None:
    # A v2 artifact carries no manifest, so status is None and must not be compared.
    report = reconcile(run_id=7, artifact=_artifact(status=None), db=_db(run_status="failed"),
                       files=[])
    assert report.ok


def test_missing_typ_file() -> None:
    report = reconcile(run_id=7, artifact=_artifact(), db=_db(),
                       files=[_typ(typ_exists=False)])
    assert not report.ok
    assert _kinds(report) == {DiscrepancyKind.MISSING_TYP_FILE}
    assert report.discrepancies[0].path == "/leads/a.tex"


def test_missing_pdf_file_when_expected() -> None:
    report = reconcile(run_id=7, artifact=_artifact(), db=_db(),
                       files=[_typ(pdf_expected=True, pdf_exists=False)])
    assert not report.ok
    assert _kinds(report) == {DiscrepancyKind.MISSING_PDF_FILE}


def test_llm_row_never_asserts_a_pdf() -> None:
    # resume_tailored_llm carries no pdf_uri, so pdf_expected is False; a missing PDF is fine,
    # a missing .tex is not.
    report = reconcile(run_id=7, artifact=_artifact(), db=_db(),
                       files=[_typ("resume_tailored_llm", pdf_expected=False, pdf_exists=False)])
    assert report.ok


def test_llm_row_missing_typ_is_flagged() -> None:
    report = reconcile(run_id=7, artifact=_artifact(), db=_db(),
                       files=[_typ("resume_tailored_llm", typ_exists=False, pdf_expected=False)])
    assert _kinds(report) == {DiscrepancyKind.MISSING_TYP_FILE}


def test_dict_and_markdown_render_over_multiple_reports() -> None:
    good = reconcile(run_id=1, artifact=_artifact(), db=_db(), files=[])
    bad = reconcile(run_id=2, artifact=_artifact(tailored_rows=9), db=_db(), files=[])
    payload = reconcile_to_dict([good, bad])
    assert payload["ok"] is False
    assert payload["runs_checked"] == 2
    md = reconcile_to_markdown([good, bad])
    assert "run 1" in md and "run 2" in md
    assert "tailored_count_mismatch" in md

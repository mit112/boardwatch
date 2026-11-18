"""T294: companion status documents are validated and served, and a bad one reads as failed."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from boardwatch.delivery.companions import SCHEMA, read_companions


def _doc(**over: Any) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "schema": SCHEMA,
        "name": "reviewer",
        "updated_at": "2026-11-17T10:14:00-06:00",
        "state": "failed",
        "summary": "reviewer batch done 10:14, store write failed: scan lock held",
        "counts": {"closed": 18, "skipped": 62},
        "items": [{"label": "Acme SWE", "reason": "sign-in wall", "needs_owner": True}],
    }
    doc.update(over)
    return doc


def _write(data_dir: Path, stem: str, body: object) -> None:
    folder = data_dir / "companions"
    folder.mkdir(parents=True, exist_ok=True)
    text = body if isinstance(body, str) else json.dumps(body)
    (folder / f"{stem}.json").write_text(text, encoding="utf-8")


def test_no_companions_directory_is_an_empty_list(tmp_path: Path) -> None:
    assert read_companions(tmp_path) == []


def test_a_valid_document_is_served_unchanged(tmp_path: Path) -> None:
    _write(tmp_path, "reviewer", _doc())
    assert read_companions(tmp_path) == [_doc()]


@pytest.mark.parametrize(
    "body",
    [
        "{not json",
        "[]",
        _doc(schema="boardwatch.companion/2"),
        _doc(name="someone-else"),
        _doc(updated_at="yesterday"),
        _doc(updated_at="2026-11-17T10:14:00"),
        _doc(state="fine"),
        _doc(summary=""),
        _doc(counts={"closed": "18"}),
        _doc(counts={"closed": True}),
        _doc(counts={"nested": {"a": 1}}),
        _doc(items={"label": "x"}),
        _doc(items=[{"reason": "no label"}]),
        _doc(items=[{"label": "x", "answer": "secret"}]),
        _doc(items=[{"label": "x", "needs_owner": "yes"}]),
    ],
)
def test_an_unreadable_document_reads_as_failed_never_absent(tmp_path: Path, body: object) -> None:
    _write(tmp_path, "reviewer", body)
    (got,) = read_companions(tmp_path)
    assert got["name"] == "reviewer"
    assert got["state"] == "failed"
    assert got["summary"].startswith("unreadable status: ")


def test_documents_are_sorted_by_name_and_one_bad_file_does_not_hide_the_rest(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "zeta", _doc(name="zeta", state="ok"))
    _write(tmp_path, "alpha", "garbage")
    assert [(c["name"], c["state"]) for c in read_companions(tmp_path)] == [
        ("alpha", "failed"),
        ("zeta", "ok"),
    ]


def test_history_rows_are_served_and_bounded(tmp_path: Path) -> None:
    rows = [{"label": f"2026-11-{d:02d}", "counts": {"asked": d}} for d in range(1, 15)]
    _write(tmp_path, "reviewer", _doc(history=rows))
    assert read_companions(tmp_path)[0]["history"] == rows

    for bad in (
        [{"label": "x", "counts": {"a": "1"}}],
        [{"counts": {"a": 1}}],
        [{"label": "x", "counts": {}, "extra": 1}],
        [{"label": str(d), "counts": {}} for d in range(32)],
    ):
        _write(tmp_path, "reviewer", _doc(history=bad))
        assert read_companions(tmp_path)[0]["state"] == "failed", bad

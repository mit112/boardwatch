"""`profile-bundle extract`: the deterministic candidate lane (Gate B, Slice B, design §6.5).

`import` enumerates a source into the ledger and stops; every record it adds is `review_required`.
`extract` is the step that reads those records through the seeded `policy/extraction-mappings.yaml`
and lands candidates, moving the easy buckets to `imported` and leaving the rest a *quarantine with
a drain* — `imports/extraction-report.yaml` carries one closed reason for every record that stays
`review_required`, and none for any other (§6.3a).

Three properties this file is answerable for, because each is a way the drain stops meaning anything
with no test going red:

- **The easy buckets land.** `header/1` (the professional name) and the skill items produce
  candidates, so their records read `imported` in the ledger.
- **The three documents never disagree.** `extract` writes candidates, the ledger, and the report
  together; `validate_extraction_report` reconciles the last two and must find nothing.
- **Re-extraction is authoritative, not additive.** Identity includes the value, so a naive merge
  would keep a superseded candidate; a re-extract of an unchanged source moves no byte (§6.6).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

import pytest
from typer.testing import CliRunner

from boardwatch.cli.app import app
from boardwatch.profile_bundle.models.imports import ExtractionReport, SourceLedger
from boardwatch.profile_bundle.paths import BUNDLE_DIR_NAME, draft_root
from boardwatch.profile_bundle.validation.imports import validate_extraction_report
from boardwatch.profile_bundle.yaml_loader import load_yaml_bytes
from tests.profile_bundle.conftest import materialise, quoted_yaml

SOURCES = PurePosixPath("policy/sources.yaml")
LEDGER = PurePosixPath("imports/source-ledger.yaml")
CANDIDATES = PurePosixPath("imports/candidates.yaml")
REPORT = PurePosixPath("imports/extraction-report.yaml")

RESUME_SOURCE_ID = "source.synthetic-resume"

#: The same minimal résumé the import CLI test uses: seven records — two header, one education, two
#: skill items, one entry metadata, one bullet. Extraction lands five of them (`header/1`, the two
#: skills, the metadata's two facts, the bullet) and leaves two `review_required`: `header/2` (the
#: email — the catalog has no contact predicate, `no_predicate_exists`) and `education/1` (prose the
#: deterministic lane defers, `free_text_deferred`).
RESUME_DOCUMENT: dict[str, Any] = {
    "header": ["Ada Lovelace", "ada@example.com"],
    "education": ["Example University, BSc"],
    "skill_groups": [{"label": "Languages", "items": ["Python", "Rust"]}],
    "entries": [
        {
            "entry_id": "entry-analytical-engine",
            "heading": "Example Labs",
            "kind": "experience",
            "title": "Engineer",
            "bullets": [{"bullet_id": "bullet-1", "text": "Built a synthetic thing."}],
        }
    ],
}
#: header/1 (name) + two skills + one bullet + one metadata record (which yields two candidates but
#: is one imported record) = five imported; the email and the education line stay review_required.
EXPECTED_IMPORTED = 5
EXPECTED_REVIEW_REQUIRED = 2


@dataclass(frozen=True)
class Env:
    data_dir: Path
    config_dir: Path

    @property
    def bundle_root(self) -> Path:
        return self.config_dir / BUNDLE_DIR_NAME

    @property
    def draft(self) -> Path:
        return draft_root(self.bundle_root, "baseline")

    def ledger(self) -> SourceLedger:
        raw = (self.draft / "imports" / "source-ledger.yaml").read_bytes()
        return SourceLedger.model_validate(load_yaml_bytes(raw, logical_path=LEDGER))

    def report(self) -> ExtractionReport:
        raw = (self.draft / "imports" / "extraction-report.yaml").read_bytes()
        return ExtractionReport.model_validate(load_yaml_bytes(raw, logical_path=REPORT))

    def candidates_raw(self) -> dict[str, Any]:
        raw = (self.draft / "imports" / "candidates.yaml").read_bytes()
        loaded = load_yaml_bytes(raw, logical_path=CANDIDATES)
        assert isinstance(loaded, dict)
        return loaded

    def resume_rows(self) -> list[Any]:
        return [row for row in self.ledger().records if row.source_id == RESUME_SOURCE_ID]

    def resume_record_ids(self) -> set[str]:
        return {row.source_record_id for row in self.resume_rows()}


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Env:
    """The comprehensive example as `drafts/baseline`, with a résumé source declared in policy.

    The example ships no `boardwatch_resume` source, so the kind Gate B needs is declared here —
    the owner-approval step the command deliberately does not perform for you. Built through the
    same fixtures the import CLI test uses so the two exercise one draft shape.
    """
    config_dir = tmp_path / "cfg"
    config_dir.mkdir(parents=True)
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(config_dir))
    root = config_dir / BUNDLE_DIR_NAME
    root.mkdir()
    (root / "drafts").mkdir()
    bundle = materialise(root)

    declared = load_yaml_bytes(
        (bundle.draft / "policy" / "sources.yaml").read_bytes(), logical_path=SOURCES
    )
    assert isinstance(declared, dict)
    declared["sources"].append(
        {
            "source_id": RESUME_SOURCE_ID,
            "source_kind": "boardwatch_resume",
            "portable_locator": "resume.yaml",
        }
    )
    (bundle.draft / "policy" / "sources.yaml").write_bytes(
        quoted_yaml(declared, logical_path=SOURCES)
    )
    return Env(data_dir=tmp_path / "data", config_dir=config_dir)


@pytest.fixture
def resume_file(tmp_path: Path) -> Path:
    path = tmp_path / "resume.yaml"
    path.write_bytes(quoted_yaml(RESUME_DOCUMENT, logical_path=PurePosixPath("resume.yaml")))
    return path


def run(env: Env, args: list[str]):  # type: ignore[no-untyped-def]
    return CliRunner().invoke(app, ["--data-dir", str(env.data_dir), "profile-bundle", *args])


def import_resume(env: Env, resume_file: Path):  # type: ignore[no-untyped-def]
    return run(
        env,
        ["import", "--draft", "baseline", "--source", RESUME_SOURCE_ID, "--from", str(resume_file)],
    )


def extract_resume(env: Env, resume_file: Path, *, extra: list[str] | None = None):  # type: ignore[no-untyped-def]
    return run(
        env,
        [
            "extract",
            "--draft",
            "baseline",
            "--source",
            RESUME_SOURCE_ID,
            "--from",
            str(resume_file),
            *(extra or []),
        ],
    )


def import_then_extract(env: Env, resume_file: Path, *, extra: list[str] | None = None):  # type: ignore[no-untyped-def]
    assert import_resume(env, resume_file).exit_code == 0
    return extract_resume(env, resume_file, extra=extra)


def test_extract_lands_candidates_for_the_easy_buckets(env: Env, resume_file: Path) -> None:
    """The one thing that did not exist: enumerated records becoming typed candidates.

    Exit 0 — the two records that stay `review_required` are a *completeness* finding, which the
    revalidation every authoring command ends with does not run, exactly as `import` reports its
    undispositioned records through its result rather than its exit code.
    """
    result = import_then_extract(env, resume_file, extra=["--json"])
    assert result.exit_code == 0, result.output

    body = json.loads(result.output)["result"]
    assert body["changed"] is True
    assert body["counts_by_disposition"] == {
        "imported": EXPECTED_IMPORTED,
        "excluded": 0,
        "review_required": EXPECTED_REVIEW_REQUIRED,
    }

    by_locator = {row.normalized_locator: row for row in env.resume_rows()}
    # The easy buckets: the professional name and every skill item carry candidates.
    assert by_locator["header/1"].disposition.value == "imported"
    assert by_locator["header/1"].candidate_ids
    for locator in ("skill-groups/Languages/1", "skill-groups/Languages/2"):
        assert by_locator[locator].disposition.value == "imported", locator
        assert by_locator[locator].candidate_ids


def test_the_report_explains_every_review_required_record_and_no_other(
    env: Env, resume_file: Path
) -> None:
    """§6.3a: exactly one closed reason per `review_required` record, and none for any other.

    Asserted from the ledger and the report on disk — the drain's durable carrier — not from the
    command's return value, so the report is checked as the document a promoted revision would hold.
    """
    assert import_then_extract(env, resume_file).exit_code == 0

    ledger = env.ledger()
    report = env.report()
    review_required = {
        row.source_record_id
        for row in ledger.records
        if row.source_id == RESUME_SOURCE_ID and row.disposition.value == "review_required"
    }
    dispositioned = {
        row.source_record_id
        for row in ledger.records
        if row.source_id == RESUME_SOURCE_ID and row.disposition.value != "review_required"
    }
    explained = report.by_record

    assert len(review_required) == EXPECTED_REVIEW_REQUIRED
    # Every review_required record has exactly one reason; the model already refuses a duplicate.
    assert review_required <= set(explained)
    # No imported or excluded record carries a reason.
    assert dispositioned.isdisjoint(set(explained))

    by_locator = {row.normalized_locator: row.source_record_id for row in ledger.records}
    assert explained[by_locator["header/2"]].reason.value == "no_predicate_exists"
    assert explained[by_locator["education/1"]].reason.value == "free_text_deferred"


def test_the_three_documents_never_disagree(env: Env, resume_file: Path) -> None:
    """`extract` writes candidates, the ledger and the report together, so they cannot contradict.

    `validate_extraction_report` is the reconciliation §6.3a demands between the ledger and the
    report; run over what `extract` wrote for its source, it must find nothing. Scoped to the résumé
    source deliberately: extract is authoritative *per source* (§6.6), and the comprehensive example
    ships an un-extracted source with a `review_required` record of its own — the whole-bundle
    reconciliation is a Gate-B property that holds only once every source has been extracted, not a
    property of extracting one. Counted through a different path than the one that produced it: the
    command's own result is not consulted here at all.
    """
    assert import_then_extract(env, resume_file).exit_code == 0

    resume_ledger, resume_report = _resume_scoped(env)
    assert validate_extraction_report(resume_ledger, resume_report) == ()

    # And the candidate side of the agreement: every imported record names candidates, every
    # review_required one names none.
    for row in env.resume_rows():
        if row.disposition.value == "imported":
            assert row.candidate_ids, row.normalized_locator
        elif row.disposition.value == "review_required":
            assert not row.candidate_ids, row.normalized_locator


def test_re_running_extract_is_authoritative_not_additive(env: Env, resume_file: Path) -> None:
    """§6.6: a re-extract replaces this source's candidates in place; it never accumulates them.

    Identity includes the canonicalized value, so a merge-based re-extract would be safe only when
    nothing changed and would silently retain a superseded candidate when something did. The
    documents are the Gate B denominator; an unchanged re-extract must move no byte, and the
    candidate set for the source must be exactly the same IDs.
    """
    assert import_then_extract(env, resume_file).exit_code == 0
    before = {
        path: (env.draft / "imports" / path).read_bytes()
        for path in ("candidates.yaml", "source-ledger.yaml", "extraction-report.yaml")
    }
    first_ids = _resume_candidate_ids(env)

    result = extract_resume(env, resume_file, extra=["--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["result"]["changed"] is False
    for path, raw in before.items():
        assert (env.draft / "imports" / path).read_bytes() == raw, path
    assert _resume_candidate_ids(env) == first_ids


def test_extract_leaves_every_other_sources_candidates_untouched(
    env: Env, resume_file: Path
) -> None:
    """Authoritative *per source*: the example's own candidates are a diff nobody should have to read.

    The comprehensive example ships candidates for its own sources; extracting the résumé source
    must carry every one of them over byte-for-byte, replacing only the résumé source's block.
    """
    before = {
        candidate["candidate_id"]: candidate
        for candidate in env.candidates_raw()["candidates"]
    }
    assert before, "the example fixture is expected to ship candidates of its own"

    assert import_then_extract(env, resume_file).exit_code == 0

    after = {
        candidate["candidate_id"]: candidate
        for candidate in env.candidates_raw()["candidates"]
    }
    for candidate_id, candidate in before.items():
        assert after.get(candidate_id) == candidate, candidate_id


def test_extract_refuses_an_undeclared_source_the_import_way(env: Env, resume_file: Path) -> None:
    """The multi-write command shares `import`'s refusal convention: exit 1, empty result, one code.

    A source the policy catalog does not declare is refused before anything is enumerated or
    written — the same `broken_reference` at the same exit tier `import` produces, so an automated
    caller reads one contract across both commands.
    """
    result = run(
        env,
        [
            "extract",
            "--draft",
            "baseline",
            "--source",
            "source.never-approved",
            "--from",
            str(resume_file),
            "--json",
        ],
    )
    assert result.exit_code == 1, result.output
    body = json.loads(result.output)
    assert body["result"] == {}
    assert [item["code"] for item in body["diagnostics"]] == ["broken_reference"]


def _resume_scoped(env: Env) -> tuple[SourceLedger, ExtractionReport]:
    """The ledger and report filtered to the résumé source alone, so the per-source reconciliation
    is exercised without the example's un-extracted sources standing in for a defect in `extract`."""
    full = env.ledger()
    resume_ledger = SourceLedger.model_validate(
        {
            "ledger_version": full.ledger_version,
            "sources": [
                source.model_dump(mode="json")
                for source in full.sources
                if source.source_id == RESUME_SOURCE_ID
            ],
            "records": [
                row.model_dump(mode="json")
                for row in full.records
                if row.source_id == RESUME_SOURCE_ID
            ],
        }
    )
    resume_ids = {row.source_record_id for row in resume_ledger.records}
    report = env.report()
    resume_report = ExtractionReport.model_validate(
        {
            "report_version": report.report_version,
            "entries": [
                entry.model_dump(mode="json")
                for entry in report.entries
                if entry.source_record_id in resume_ids
            ],
        }
    )
    return resume_ledger, resume_report


def _resume_candidate_ids(env: Env) -> set[str]:
    resume_records = env.resume_record_ids()
    return {
        candidate["candidate_id"]
        for candidate in env.candidates_raw()["candidates"]
        if candidate["source_record_id"] in resume_records
    }

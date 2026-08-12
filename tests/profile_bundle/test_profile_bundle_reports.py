"""The one validation report, and the two renderings the commands emit (design §19, §20, §21).

Three properties matter more than the report's contents:

- **One model, two renderings.** Human text and JSON are both derived from the same
  `ValidationReport`. A human-only field would be a fact no script can act on, and a JSON-only
  field would be one no operator ever reads.
- **Deterministic bytes.** Sorted keys, compact separators, one trailing newline. The same report
  must produce the same bytes on every machine, or a diff of two runs is unreadable.
- **Closed shape.** The keys are pinned exactly. A diagnostic carries record IDs and byte ranges,
  never captured evidence bytes or contact values, and a closed schema is what stops a future field
  from quietly carrying one into a report an operator pastes into a bug tracker.

**Both renderings are exercised through the command, not through a library renderer.** `reports.py`
once carried `report_json` and `report_text`, and the command layer rendered the same report a
second time into its own envelope; the two forms had already diverged on wording and on shape while
thirty tests here held the one no operator could reach. D-115: a check that cannot fire is deleted,
so the renderers went and their properties moved onto the surface that emits them. What stays a
unit test is what is still a pure function of the model — the counts and the §21 outcome — because
those are computed by `validation/run.py` on every run.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pytest
from typer.testing import CliRunner

from boardwatch.cli.app import app
from boardwatch.profile_bundle.canonical import candidate_content_digest
from boardwatch.profile_bundle.errors import Diagnostic, IssueCode, diagnostic, outcome_with
from boardwatch.profile_bundle.reports import (
    REPORT_SCHEMA,
    ValidationCounts,
    ValidationReport,
    count_diagnostics,
    outcome_for_report,
)
from tests.profile_bundle.conftest import (
    SyntheticBundle,
    parse_documents,
    stored_blob_reader,
)

DIGEST = "sha256:" + "a" * 64
CANDIDATE = "sha256:" + "b" * 64


def error(message: str = "an error", **kwargs: object) -> Diagnostic:
    return diagnostic(IssueCode.BROKEN_REFERENCE, message, **kwargs)  # type: ignore[arg-type]


def blocker(message: str = "a blocker") -> Diagnostic:
    return diagnostic(IssueCode.UNRESOLVED_CONFLICT, message, record_id="conflict.example")


def warning(message: str = "a warning") -> Diagnostic:
    return diagnostic(IssueCode.BROKEN_REFERENCE, message, tier="warning")


def information(message: str = "some information") -> Diagnostic:
    return diagnostic(IssueCode.ORPHANED_ARTEFACT, message)


def report(*diagnostics: Diagnostic, as_of: date | None = None) -> ValidationReport:
    return ValidationReport(
        schema_version=1,
        bundle_digest=DIGEST,
        candidate_digest=CANDIDATE,
        as_of=as_of,
        diagnostics=tuple(diagnostics),
        counts=count_diagnostics(diagnostics),
    )


@dataclass(frozen=True)
class Env:
    data_dir: Path


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Env:
    config_dir = tmp_path / "cfg"
    config_dir.mkdir(parents=True)
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(config_dir))
    return Env(data_dir=tmp_path / "data")


def validate(env: Env, bundle: SyntheticBundle, *extra: str):  # type: ignore[no-untyped-def]
    """One `profile-bundle validate --draft` run, exactly as an operator would make it."""
    return CliRunner().invoke(
        app,
        [
            "--data-dir", str(env.data_dir), "profile-bundle", "validate",
            "--bundle", str(bundle.root), "--draft", bundle.draft_name, *extra,
        ],
    )


def loaded(text: str) -> dict[str, object]:
    payload = json.loads(text)
    assert isinstance(payload, dict)
    return payload


def result_of(text: str) -> dict[str, object]:
    body = loaded(text)["result"]
    assert isinstance(body, dict)
    return body


# --------------------------------------------------------------------------------------
# Counts
# --------------------------------------------------------------------------------------


def test_counts_are_totalled_per_tier() -> None:
    counts = count_diagnostics([error(), error("second"), blocker(), warning(), information()])
    assert counts == ValidationCounts(error=2, blocker=1, warning=1, information=1)


def test_counts_over_no_diagnostics_are_all_zero() -> None:
    assert count_diagnostics([]) == ValidationCounts(0, 0, 0, 0)


def test_total_is_the_sum_of_every_tier() -> None:
    counts = count_diagnostics([error(), blocker(), warning(), information()])
    assert counts.total == 4


# --------------------------------------------------------------------------------------
# Outcome and exit code (§21)
# --------------------------------------------------------------------------------------


def test_a_report_with_no_findings_is_clean_and_exits_zero() -> None:
    outcome = outcome_for_report(report())
    assert (outcome.category, outcome.exit_code) == ("clean", 0)


def test_an_error_is_findings_and_exits_one() -> None:
    outcome = outcome_for_report(report(error()))
    assert (outcome.category, outcome.exit_code) == ("findings", 1)


def test_a_blocker_alone_is_findings_and_exits_one() -> None:
    """§20.5 keeps blockers separate from errors, but both mean the operator has work to do."""
    outcome = outcome_for_report(report(blocker()))
    assert (outcome.category, outcome.exit_code) == ("findings", 1)


@pytest.mark.parametrize("noise", [warning(), information()])
def test_warnings_and_information_never_change_the_exit_code(noise: Diagnostic) -> None:
    outcome = outcome_for_report(report(noise))
    assert (outcome.category, outcome.exit_code) == ("clean", 0)


@pytest.mark.parametrize(
    "code",
    [IssueCode.IO_ERROR, IssueCode.UNSUPPORTED_SCHEMA_VERSION, IssueCode.INTERNAL_ERROR],
)
def test_a_check_that_could_not_complete_exits_three_not_one(code: IssueCode) -> None:
    """A check that did not run is not a check that passed, and it is not a finding either: §21
    gives it its own exit code so a script cannot read "could not read the bundle" as "one error"."""
    outcome = outcome_for_report(report(diagnostic(code, "could not complete")))
    assert (outcome.category, outcome.exit_code) == ("could_not_complete", 3)


def test_could_not_complete_outranks_an_ordinary_error_in_the_same_report() -> None:
    outcome = outcome_for_report(report(error(), diagnostic(IssueCode.IO_ERROR, "unreadable")))
    assert (outcome.category, outcome.exit_code) == ("could_not_complete", 3)


def test_diagnostic_order_does_not_depend_on_the_order_they_were_found() -> None:
    """The ordering both renderings read, pinned where it is decided rather than downstream.

    `ValidationReport.ordered` and `errors.outcome_with` sort by `Diagnostic.sort_key`, so two runs
    that accumulated the same findings in different orders emit identical bytes. Driving this from
    a bundle would need two validations that disagree on traversal order and agree on everything
    else, which no input produces.
    """
    found = [blocker(), error("aaa"), warning()]
    assert report(*found).ordered == report(*reversed(found)).ordered
    assert outcome_with(None, found).diagnostics == outcome_with(None, list(reversed(found))).diagnostics


# --------------------------------------------------------------------------------------
# The machine rendering, as a command emits it
# --------------------------------------------------------------------------------------


def test_json_carries_exactly_the_declared_result_keys(
    env: Env, synthetic_bundle: SyntheticBundle
) -> None:
    """A closed shape, asserted by equality rather than by containment. A new field cannot appear
    without this failing, which is the point: a report must never grow a payload that carries
    captured evidence or a contact value into something an operator pastes elsewhere."""
    assert set(result_of(validate(env, synthetic_bundle, "--json").output)) == {
        "bundle_digest",
        "candidate_digest",
        "counts",
        "schema_version",
    }


def test_json_carries_exactly_the_declared_diagnostic_keys(
    env: Env, synthetic_bundle: SyntheticBundle
) -> None:
    synthetic_bundle.write("skills/inventory.yaml", "skills: [ this is not\n")
    entries = loaded(validate(env, synthetic_bundle, "--json").output)["diagnostics"]
    assert isinstance(entries, list) and entries
    assert set(entries[0]) == {"code", "details", "message", "path", "record_id", "tier"}


def test_json_uses_sorted_keys_compact_separators_and_one_trailing_newline(
    env: Env, synthetic_bundle: SyntheticBundle
) -> None:
    text = validate(env, synthetic_bundle, "--json").output
    assert text.endswith("}\n")
    assert not text.endswith("}\n\n")
    assert ", " not in text and '": ' not in text, "separators are not compact"
    body = text.rstrip("\n")
    assert body == json.dumps(
        json.loads(body), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


def test_json_is_byte_identical_across_runs(env: Env, synthetic_bundle: SyntheticBundle) -> None:
    assert (
        validate(env, synthetic_bundle, "--json").output
        == validate(env, synthetic_bundle, "--json").output
    )


def test_json_carries_the_report_schema_version(
    env: Env, synthetic_bundle: SyntheticBundle
) -> None:
    assert loaded(validate(env, synthetic_bundle, "--json").output)["report_schema"] == (
        REPORT_SCHEMA
    )


def test_json_carries_the_counts_per_tier(env: Env, synthetic_bundle: SyntheticBundle) -> None:
    counts = result_of(validate(env, synthetic_bundle, "--json").output)["counts"]
    assert isinstance(counts, dict)
    assert set(counts) == {"blocker", "error", "information", "warning"}


def test_json_preserves_non_ascii_rather_than_escaping_it(
    env: Env, synthetic_bundle: SyntheticBundle
) -> None:
    """The bundle is Unicode-first and NFC-normalised throughout; escaping here would make a
    diagnostic about a non-ASCII record unreadable in the one place an operator reads it.

    The accented text has to come from the bundle rather than from a hand-built diagnostic, so it
    is written into a document the loader refuses: the parse failure quotes the key it stopped on.
    """
    synthetic_bundle.write("skills/inventory.yaml", 'café: "Zürich"\n')
    output = validate(env, synthetic_bundle, "--json").output
    assert "café" in output or "Zürich" in output, output
    assert "\\u00e9" not in output and "\\u00fc" not in output


def test_a_digest_no_run_computed_is_rendered_as_null(
    env: Env, synthetic_bundle: SyntheticBundle
) -> None:
    """A bundle whose manifest will not parse has no schema version and no digest, and reporting
    `0` or `""` for either would be a measurement that was never taken (D-012)."""
    synthetic_bundle.write("manifest.yaml", "state: [ not a manifest\n")
    result = result_of(validate(env, synthetic_bundle, "--json").output)
    assert result["bundle_digest"] is None
    assert result["candidate_digest"] is None
    assert result["schema_version"] is None


def test_validate_presents_the_candidate_digest_it_recomputed(
    env: Env, synthetic_bundle: SyntheticBundle
) -> None:
    """§19 step 7: `validate` presents the candidate digest, and step 8 has the owner approve
    *that exact digest*. It is the one field binding the two commands, so an agent that reads it
    from `validate` and hands it to the owner must be reading the digest `approve` will bind.

    Computed here through the in-memory blob reader rather than the filesystem one the command
    uses, so agreement is not two calls into the same path. Both renderings, because an agent reads
    the JSON and the owner reads the text, and they have to be looking at the same digest.
    """
    expected = candidate_content_digest(
        parse_documents(synthetic_bundle.draft), stored_blob_reader(synthetic_bundle.root), None
    )
    assert result_of(validate(env, synthetic_bundle, "--json").output)["candidate_digest"] == (
        expected
    )
    assert expected in validate(env, synthetic_bundle).output


# --------------------------------------------------------------------------------------
# The human rendering, as a command emits it
# --------------------------------------------------------------------------------------


def test_text_shows_every_diagnostic_the_json_carries(
    env: Env, synthetic_bundle: SyntheticBundle
) -> None:
    """A finding a script can see and an operator cannot is how a real problem gets ignored."""
    synthetic_bundle.write("skills/inventory.yaml", "skills: [ this is not\n")
    machine = loaded(validate(env, synthetic_bundle, "--json").output)["diagnostics"]
    human = validate(env, synthetic_bundle).output
    assert isinstance(machine, list) and machine
    for finding in machine:
        assert isinstance(finding, dict)
        assert finding["message"] in human
        assert finding["code"] in human


def test_text_states_the_outcome_and_the_counts(
    env: Env, synthetic_bundle: SyntheticBundle
) -> None:
    synthetic_bundle.write("skills/inventory.yaml", "skills: [ this is not\n")
    output = validate(env, synthetic_bundle).output
    assert "findings" in output
    counts = result_of(validate(env, synthetic_bundle, "--json").output)["counts"]
    assert isinstance(counts, dict)
    for tier, count in counts.items():
        assert f"{count} {tier}" in output, output


def test_text_says_a_clean_report_is_clean_rather_than_printing_nothing(
    env: Env, synthetic_bundle: SyntheticBundle
) -> None:
    """Silence and success look identical, which is exactly the confusion this program keeps
    paying for. A clean run says so."""
    result = validate(env, synthetic_bundle)
    assert result.exit_code == 0, result.output
    assert "clean" in result.output


def test_text_states_the_as_of_date_when_completeness_was_requested(
    env: Env, synthetic_bundle: SyntheticBundle
) -> None:
    output = validate(env, synthetic_bundle, "--completeness", "--as-of", "2026-08-11").output
    assert "2026-08-11" in output


def test_text_is_deterministic(env: Env, synthetic_bundle: SyntheticBundle) -> None:
    synthetic_bundle.write("skills/inventory.yaml", "skills: [ this is not\n")
    assert validate(env, synthetic_bundle).output == validate(env, synthetic_bundle).output

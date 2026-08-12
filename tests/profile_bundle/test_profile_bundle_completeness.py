"""T13 completeness validation (design §20.5), and the clauses it deliberately does not check.

§20.5's "required profile fields" read like four checks, and three of them are not checks at all:
the model layer already refuses the input. D-115 says a check that cannot fire is deleted rather
than shipped, so those three have no issue code and no branch here — and each one instead has a test
below naming the layer that *does* hold the guarantee. A never-firing check reads as coverage, and
the spec row it covers would look green while nothing ran.

The time-dependent clauses are the opposite problem. `as_of` is an argument, never a clock read, so
the same bytes produce the same structural verdict forever (§20 opening) and only completeness moves
with the date. The tests therefore pin one fixture at two dates and assert exactly what changes.
"""

from __future__ import annotations

import os
import shutil
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any

import pytest

from boardwatch.profile_bundle.errors import IssueCode, tier_of
from boardwatch.profile_bundle.models.entities import STATUS_CATALOGS
from boardwatch.profile_bundle.models.facts import (
    VALUE_DATE_KINDS,
    FactRecord,
    FactValueKind,
)
from boardwatch.profile_bundle.models.metrics import MetricRecord
from boardwatch.profile_bundle.models.policy import ExpirySpec
from boardwatch.profile_bundle.paths import revision_root
from boardwatch.profile_bundle.validation import BundleParseError, build_context, load_documents
from boardwatch.profile_bundle.validation.completeness import (
    _declared_expiry,
    ancestry_completeness,
    validate_completeness,
)
from boardwatch.profile_bundle.validation.digest import validate_digest
from boardwatch.profile_bundle.validation.structural import validate_structural
from boardwatch.profile_bundle.yaml_loader import load_yaml_bytes
from tests.profile_bundle.conftest import (
    PromotedRevisionTree,
    SyntheticBundle,
    blob_reader,
    quoted_yaml,
)

# --------------------------------------------------------------------------------------
# The three clocks every time-dependent test uses
#
# Derived from what the packaged example actually authors, and pinned by
# `test_the_expiry_dates_the_packaged_example_pins_are_the_ones_these_tests_assume` so a fixture
# that drifts fails as a fixture rather than quietly changing what these tests measure.
# --------------------------------------------------------------------------------------

#: Before the one expiring credential (`expires_at: 2026-07-01`) lapses.
BEFORE_EXPIRY = date(2026, 6, 30)
#: After it lapsed, but inside both 90-day review intervals (`reviewed_at: 2026-08-10`).
AFTER_EXPIRY = date(2026, 8, 11)
#: After 2026-08-10 + 90 days = 2026-11-08, so both review intervals have elapsed too.
AFTER_REVIEW_INTERVAL = date(2027, 1, 1)


# --------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------


def edit(bundle: SyntheticBundle, relative: str, mutate: Any) -> None:
    """Rewrite one document of the draft through the loader the production reader uses."""
    path = bundle.document(relative)
    data = load_yaml_bytes(path.read_bytes(), logical_path=PurePosixPath(relative))
    mutate(data)
    path.write_bytes(quoted_yaml(data, logical_path=PurePosixPath(relative)))


def parse_codes(root: Path) -> list[str]:
    """The codes a tree produces when it will not become models at all."""
    try:
        load_documents(root, mode="draft")
    except BundleParseError as exc:
        return sorted(finding.code for finding in exc.diagnostics)
    return []


# --------------------------------------------------------------------------------------
# The three §20.5 clauses that are model contracts, not completeness checks
# --------------------------------------------------------------------------------------


def test_the_issue_catalog_carries_no_code_that_cannot_fire() -> None:
    """D-115, applied to the completeness group.

    `metric_review_missing` cannot fire because `review_interval_days` is a `PredicateSpec` column
    and a metric has no predicate, while `MetricRecord.reviewed_at` is a required `date`; there is
    neither an interval to be past nor a review to be absent. `missing_person_entity` and
    `entity_status_undeclared` cannot fire because the document models make both unrepresentable.
    Each of the three tests below names where the guarantee actually lands.
    """
    absent = {"METRIC_REVIEW_MISSING", "MISSING_PERSON_ENTITY", "ENTITY_STATUS_UNDECLARED"}
    assert absent & {code.name for code in IssueCode} == set()


def test_a_metric_carries_a_required_review_date_and_no_review_interval() -> None:
    """Where metric freshness lands: on the model, as a required `date`.

    A metric's freshness is its `reviewed_at` alone. `review_interval_days` belongs to a predicate's
    `ExpirySpec`, and a metric has no predicate row, so "this metric is past its review interval" is
    not a condition the schema can express.
    """
    assert "reviewed_at" in MetricRecord.model_fields
    assert MetricRecord.model_fields["reviewed_at"].is_required()
    assert "review_interval_days" not in MetricRecord.model_fields
    assert "review_interval_days" in ExpirySpec.model_fields


def test_a_metric_without_a_review_date_fails_to_parse(synthetic_bundle: SyntheticBundle) -> None:
    """The same guarantee, exercised through the real loader rather than through introspection."""

    def drop_review(data: Any) -> None:
        del data["metrics"][0]["reviewed_at"]

    edit(synthetic_bundle, "metrics/records.yaml", drop_review)
    assert IssueCode.MODEL_VALIDATION_ERROR in parse_codes(synthetic_bundle.draft)


def test_a_tree_without_an_identity_document_reports_a_missing_required_file(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """Where "one person entity" lands, half one: the file is declared by the grammar."""
    synthetic_bundle.document("facts/identity.yaml").unlink()
    ctx = build_context(synthetic_bundle.draft, mode="draft", blobs=blob_reader())
    assert IssueCode.MISSING_REQUIRED_FILE in sorted(f.code for f in validate_structural(ctx))


def test_an_identity_document_without_a_person_fails_to_parse(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """Where "one person entity" lands, half two: `IdentityDocument.person` is one required field.

    There is no way to author zero people or two, so a completeness check counting them would be a
    branch whose false arm is unreachable.
    """

    def drop_person(data: Any) -> None:
        del data["person"]

    edit(synthetic_bundle, "facts/identity.yaml", drop_person)
    assert IssueCode.MODEL_VALIDATION_ERROR in parse_codes(synthetic_bundle.draft)


def test_every_entity_kind_that_has_a_status_declares_it_as_a_required_field() -> None:
    """Where "explicit education/employment/project status" lands: the entity models.

    `person` is deliberately absent from `STATUS_CATALOGS` — §9 declares no status catalog for it —
    so "every kind except person" is the exact shape the schema already enforces.
    """
    assert {"education", "employment", "project"} <= set(STATUS_CATALOGS)
    assert "person" not in STATUS_CATALOGS


def test_an_entity_without_a_status_fails_to_parse(synthetic_bundle: SyntheticBundle) -> None:
    def drop_status(data: Any) -> None:
        del data["entities"][0]["status"]

    edit(synthetic_bundle, "facts/education.yaml", drop_status)
    assert IssueCode.MODEL_VALIDATION_ERROR in parse_codes(synthetic_bundle.draft)


# --------------------------------------------------------------------------------------
# The codes completeness does report
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [
        "missing_contact_channel",
        "missing_review_state",
        "stale_fact",
        "expired_review",
        "fact_value_expired",
        "unresolved_conflict",
        "unverifiable_ancestor",
    ],
)
def test_every_completeness_finding_is_a_blocker(value: str) -> None:
    """§20.5: a completeness finding never makes the revision invalid.

    The tier is what decides whether `validate` exits 1 on a bundle that is merely incomplete, so it
    is asserted per code rather than trusted to a default. Parametrised over the wire values rather
    than the enum members so a code this slice adds is a failing assertion instead of a collection
    error — a collection error proves nothing about the layer.
    """
    assert tier_of(IssueCode(value)) == "blocker"


def test_the_completeness_summary_is_information_only() -> None:
    """Counts must not move the exit code. §20.5 lists them as `information`, and a run whose only
    finding is a count is a clean run."""
    assert tier_of(IssueCode("completeness_counts")) == "information"


def test_a_value_expiry_and_a_review_expiry_are_different_codes() -> None:
    """One code, one condition.

    Renewing an expired credential and re-reviewing a fact whose interval elapsed are different
    operator actions, so folding both into `expired_review` would leave a script reading the JSON
    unable to tell them apart. `stale_fact` is a third thing again: the DECLARED
    `VerificationState.STALE`, never a computed date comparison.
    """
    codes = {IssueCode("fact_value_expired"), IssueCode.EXPIRED_REVIEW, IssueCode.STALE_FACT}
    assert len(codes) == 3


def test_the_expiry_dates_the_packaged_example_pins_are_the_ones_these_tests_assume() -> None:
    """A fixture that drifts from the dates the tests reason about would pass while measuring
    something else, so the two facts that carry a non-null `expires_at` are pinned here."""
    from tests.profile_bundle.conftest import example_source_root

    root = example_source_root()
    certification = load_yaml_bytes(
        (root / "facts" / "certifications.yaml").read_bytes(),
        logical_path=PurePosixPath("facts/certifications.yaml"),
    )
    expiring = [f for f in certification["facts"] if f["expires_at"] is not None]
    assert [(f["fact_id"], f["expires_at"]) for f in expiring] == [
        ("fact.example-credential.expiry.001", "2026-07-01")
    ]
    assert BEFORE_EXPIRY < date.fromisoformat(expiring[0]["expires_at"]) < AFTER_EXPIRY


# --------------------------------------------------------------------------------------
# The packaged example, at three clocks
# --------------------------------------------------------------------------------------


def completeness_codes(bundle: SyntheticBundle, as_of: date) -> list[str]:
    ctx = build_context(
        bundle.draft, mode="draft", blobs=blob_reader(), bundle_root=bundle.root
    )
    return sorted(f.code for f in validate_completeness(ctx, as_of=as_of))


def test_the_example_reports_only_the_blockers_it_actually_carries(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """The example is deliberately not finding-free: it carries one unresolved conflict, one stale
    fact, and one lapsed credential, because a fixture with nothing wrong cannot show that the
    layer reports anything at all.

    Asserting the exact multiset rather than membership is what makes this a regression test: a
    check that started double-reporting one record under two codes would still pass a `in` test.
    """
    assert completeness_codes(synthetic_bundle, AFTER_EXPIRY) == [
        "completeness_counts",
        "fact_value_expired",
        "stale_fact",
        "unresolved_conflict",
    ]


def test_a_lapsed_credential_is_a_blocker_only_after_it_lapses(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """§22 criterion 24: a fixture with a past expiry stays structurally valid and produces one
    completeness blocker. Run before the date and the blocker is simply absent."""
    before = completeness_codes(synthetic_bundle, BEFORE_EXPIRY)
    after = completeness_codes(synthetic_bundle, AFTER_EXPIRY)
    assert "fact_value_expired" not in before
    assert after.count("fact_value_expired") == 1


def test_a_review_interval_lapses_independently_of_a_value_expiry(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """The example's two `application.*` predicates are the only rows with a review interval (90
    days) and both facts were reviewed on 2026-08-10, so the interval and the credential's value
    date lapse at different times. Two codes, two clocks, one fixture."""
    assert completeness_codes(synthetic_bundle, AFTER_EXPIRY).count("expired_review") == 0
    assert completeness_codes(synthetic_bundle, AFTER_REVIEW_INTERVAL).count("expired_review") == 2


def test_only_the_time_dependent_codes_move_between_two_clocks(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """The design's central purity claim, stated as a difference rather than as an absolute.

    Everything a bundle says about itself is fixed; only expiry and review move with `--as-of`. If a
    third code ever appeared in this difference, some check would have started reading the date.
    """
    early = set(completeness_codes(synthetic_bundle, BEFORE_EXPIRY))
    late = set(completeness_codes(synthetic_bundle, AFTER_REVIEW_INTERVAL))
    assert late - early == {"expired_review", "fact_value_expired"}
    assert early - late == set()


def test_the_non_completeness_layers_are_identical_under_two_clocks(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """§20: "wall-clock time cannot turn the same bytes from valid to invalid".

    Completeness takes the only date in the package, so the way to falsify this is to run every
    other layer twice and compare. `profile_bundle` reads no clock at all, which is what makes the
    comparison meaningful instead of tautological.
    """
    ctx = build_context(
        synthetic_bundle.draft, mode="draft", blobs=blob_reader(), bundle_root=synthetic_bundle.root
    )
    structural = validate_structural(ctx)
    assert structural == validate_structural(ctx)
    assert set(completeness_codes(synthetic_bundle, BEFORE_EXPIRY)) & {
        f.code for f in structural
    } == set()


def test_the_package_reads_no_clock() -> None:
    """The property the two-clock tests rest on, asserted directly against the source.

    A single `date.today()` anywhere under `profile_bundle/` would make some verdict depend on when
    it ran, and the comparison tests above would keep passing because both of their runs happen at
    the same wall-clock moment.
    """
    from boardwatch import profile_bundle

    package = Path(profile_bundle.__file__).parent
    offenders = [
        source.relative_to(package).as_posix()
        for source in sorted(package.rglob("*.py"))
        for text in [source.read_text(encoding="utf-8")]
        if "date.today(" in text or "datetime.now(" in text or "utcnow(" in text
    ]
    assert offenders == []


# --------------------------------------------------------------------------------------
# Each blocker, made to fire on purpose
# --------------------------------------------------------------------------------------


def test_a_projected_surface_with_no_contact_channel_is_a_blocker(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """§20.5: "at least one contact channel for a requested surface".

    A requested surface is one the bundle actually projects to. The example's only public-surface
    contact is the profile URL, so narrowing it leaves public facts with no way to reach the person.
    """

    def narrow(data: Any) -> None:
        for contact in data["contacts"]:
            contact["allowed_surfaces"] = [
                s for s in contact["allowed_surfaces"] if s != "public"
            ]

    edit(synthetic_bundle, "facts/identity.yaml", narrow)
    found = completeness_codes(synthetic_bundle, AFTER_EXPIRY)
    assert found.count("missing_contact_channel") == 1


def test_a_surface_no_record_projects_to_needs_no_contact_channel(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """The other half. Without it, the check above could be passing because it demands a contact for
    every surface in the enum, which would make a résumé-only profile permanently incomplete."""
    ctx = build_context(synthetic_bundle.draft, mode="draft", blobs=blob_reader())
    surfaces = {
        s for c in ctx.index.contacts for s in c.allowed_surfaces
    }
    assert "public" in {str(s) for s in surfaces}
    assert "missing_contact_channel" not in completeness_codes(synthetic_bundle, AFTER_EXPIRY)


def test_an_imported_fact_left_unresolved_is_a_blocker(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """§20.5: "a declared review state for every imported fact".

    `verification_state` is a required field, so the only non-vacuous reading is that an imported
    fact may not still be sitting at `unresolved` — nobody has decided about it yet.
    """

    def unresolve(data: Any) -> None:
        for fact in data["facts"]:
            if fact["import_lineage"] is not None:
                fact["verification_state"] = "unresolved"

    edit(synthetic_bundle, "facts/projects/project.packet-pantry.yaml", unresolve)
    assert completeness_codes(synthetic_bundle, AFTER_EXPIRY).count("missing_review_state") == 1


def test_an_unresolved_fact_that_was_not_imported_is_not_a_review_state_finding(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """The example already ships two unresolved facts — the conflict's candidates. Neither was
    imported, and reporting them here would make every open conflict look like an import problem."""
    assert "missing_review_state" not in completeness_codes(synthetic_bundle, AFTER_EXPIRY)


def test_an_unresolved_conflict_names_the_candidates_it_blocks(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """Reported once per group, not once per candidate: the group is the record an owner rules on,
    and the blocked facts are the consequence, so they travel as detail."""
    ctx = build_context(synthetic_bundle.draft, mode="draft", blobs=blob_reader())
    found = [
        f for f in validate_completeness(ctx, as_of=AFTER_EXPIRY) if f.code == "unresolved_conflict"
    ]
    assert [f.record_id for f in found] == ["conflict.packet-pantry.end-date"]
    assert found[0].details["blocked_record_ids"] == [
        "fact.packet-pantry.end-date.001",
        "fact.packet-pantry.end-date.002",
    ]


def test_a_resolved_conflict_blocks_nothing(synthetic_bundle: SyntheticBundle) -> None:
    """The example carries one resolved group as well as one unresolved one. If both were reported
    the count above would be 2, and "resolved" would mean nothing."""
    ctx = build_context(synthetic_bundle.draft, mode="draft", blobs=blob_reader())
    assert "conflict.packet-pantry.start-date" not in {
        f.record_id for f in validate_completeness(ctx, as_of=AFTER_EXPIRY)
    }


def test_a_stale_fact_is_reported_for_its_declared_state_not_for_a_date(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """`stale_fact` is the DECLARED `VerificationState.STALE` and nothing else.

    The example's stale fact also carries `expires_at: 2026-01-01`, which is in the past at every
    clock these tests use. It is reported exactly once — under `stale_fact` — because expiry is
    evaluated only over effective facts, and a stale fact is already locally blocked (§21).
    """
    ctx = build_context(synthetic_bundle.draft, mode="draft", blobs=blob_reader())
    for as_of in (BEFORE_EXPIRY, AFTER_EXPIRY, AFTER_REVIEW_INTERVAL):
        found = [
            f for f in validate_completeness(ctx, as_of=as_of) if f.code == "stale_fact"
        ]
        assert [f.record_id for f in found] == ["fact.packet-pantry.legacy-language.001"]
        assert "fact.packet-pantry.legacy-language.001" not in {
            f.record_id
            for f in validate_completeness(ctx, as_of=as_of)
            if f.code == "fact_value_expired"
        }


def test_a_lapsed_credential_names_the_fact_and_the_date_it_was_measured_against(
    synthetic_bundle: SyntheticBundle,
) -> None:
    ctx = build_context(synthetic_bundle.draft, mode="draft", blobs=blob_reader())
    found = [
        f for f in validate_completeness(ctx, as_of=AFTER_EXPIRY) if f.code == "fact_value_expired"
    ]
    assert [f.record_id for f in found] == ["fact.example-credential.expiry.001"]
    assert found[0].details == {
        "expired_on": "2026-07-01",
        "declared_by": "both",
        "as_of": AFTER_EXPIRY.isoformat(),
        "predicate": "certification.expiry",
    }


def expiry_findings(bundle: SyntheticBundle, as_of: date) -> list[Any]:
    ctx = build_context(bundle.draft, mode="draft", blobs=blob_reader())
    return [f for f in validate_completeness(ctx, as_of=as_of) if f.code == "fact_value_expired"]


def set_credential_expires_at(bundle: SyntheticBundle, value: str | None) -> None:
    def mutate(data: Any) -> None:
        for fact in data["facts"]:
            if fact["fact_id"] == "fact.example-credential.expiry.001":
                fact["expires_at"] = value

    edit(bundle, "facts/certifications.yaml", mutate)


def test_a_credential_is_blocked_by_its_own_value_date_with_no_expires_at(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """§10.4's row is "block active use after **value date**", and for `certification.expiry` the
    fact's VALUE *is* that date.

    Keying only on the `expires_at` column meant a credential that lapsed years ago, whose author
    left `expires_at: null`, stayed `verified` and effective at every `as_of` — keeping `resume`,
    `public` and `application` in its `allowed_surfaces` and counting toward `surface_coverage`. A
    résumé built from the bundle would have asserted it. The packaged example sets both dates
    identically, which is exactly why no existing test could tell them apart, so this one removes the
    column and leaves only the value.
    """
    set_credential_expires_at(synthetic_bundle, None)
    found = expiry_findings(synthetic_bundle, AFTER_EXPIRY)
    assert [f.record_id for f in found] == ["fact.example-credential.expiry.001"]
    assert found[0].details["expired_on"] == "2026-07-01"
    assert found[0].details["declared_by"] == "value"
    assert expiry_findings(synthetic_bundle, BEFORE_EXPIRY) == []


def test_the_earlier_of_a_credentials_two_declared_dates_governs(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """`expires_at` and a date value under this predicate declare the same thing.

    Taking the later of the two would let an author revive a lapsed credential by writing a column
    date after the one the credential itself carries, so the earlier governs and the finding names
    which declaration produced it — typed in `details`, not spelled out in the message.
    """
    set_credential_expires_at(synthetic_bundle, "2030-01-01")
    found = expiry_findings(synthetic_bundle, AFTER_EXPIRY)
    assert [(f.details["expired_on"], f.details["declared_by"]) for f in found] == [
        ("2026-07-01", "value")
    ]


def test_a_fact_whose_predicate_never_expires_is_not_reported_for_its_expiry_date(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """Expiry is the predicate's contract, not the fact's opinion.

    `technology.used` declares `behaviour: never`, so a `expires_at` authored on one of its facts
    states when the author expects to revisit it — not a date after which the value is unusable.
    Reading the fact's date alone would block a live skill on an author's note.
    """

    def add_past_expiry(data: Any) -> None:
        for fact in data["facts"]:
            if fact["fact_id"] == "fact.packet-pantry.language.001":
                fact["expires_at"] = "2020-01-01"

    edit(synthetic_bundle, "facts/projects/project.packet-pantry.yaml", add_past_expiry)
    ctx = build_context(synthetic_bundle.draft, mode="draft", blobs=blob_reader())
    assert "fact.packet-pantry.language.001" not in {
        f.record_id
        for f in validate_completeness(ctx, as_of=AFTER_EXPIRY)
        if f.code == "fact_value_expired"
    }


def test_a_catalog_pairing_a_value_date_expiry_with_a_dateless_type_fails_the_whole_bundle(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """Where the model's refusal lands for a real bundle, rather than for a hand-built row.

    `policy/predicates.yaml` is read through the same document loader as every other file, so the
    pairing is reported as a `model_validation_error` and the run never reaches a verdict at all.
    That is the whole point of refusing it at authoring time: the alternative was a bundle that
    validated clean while one predicate's expiry could never fire.
    """

    def mutate(data: Any) -> None:
        for spec in data["predicates"]:
            if spec["predicate_id"] == "certification.expiry":
                spec["legal_value_types"] = ["year_month"]

    edit(synthetic_bundle, "policy/predicates.yaml", mutate)
    assert parse_codes(synthetic_bundle.draft) == ["model_validation_error"]


#: One authored value per kind in the closed union, so the parametrization below covers all ten and
#: a new kind fails here with a `KeyError` instead of silently not being measured.
VALUE_BY_KIND: dict[str, Any] = {
    "string": {"type": "string", "value": "Example Cloud Practitioner"},
    "integer": {"type": "integer", "value": 3},
    "decimal": {"type": "decimal", "value": "1.5"},
    "boolean": {"type": "boolean", "value": True},
    "date": {"type": "date", "value": "2020-01-01"},
    "year_month": {"type": "year_month", "value": "2020-01"},
    "date_range": {"type": "date_range", "start": "2020-01-01", "end": "2020-02-01"},
    "url": {"type": "url", "value": "https://example.test/credential"},
    "string_list": {"type": "string_list", "values": ["example"]},
    "skill_ref": {"type": "skill_ref", "skill_id": "skill.example-language"},
}


@pytest.mark.parametrize("kind", sorted(FactValueKind, key=str))
def test_the_expiry_check_reads_a_value_date_from_exactly_the_kinds_the_catalog_admits(
    synthetic_bundle: SyntheticBundle, kind: FactValueKind
) -> None:
    """One set, two readers, and the test that stops them becoming two contracts.

    `PredicateSpec` refuses `block_active_use_after_value_date` on any value type outside
    `VALUE_DATE_KINDS`, and this function reads a value date from exactly those kinds. Either side
    moving alone reopens the hole the pair exists to close: a catalog row whose facts carry a
    `year_month` or a `date_range` and `expires_at: null` was never blocked at any `as_of`, with no
    finding and no code. So the agreement is asserted over every member of the closed union rather
    than asserted in a comment.
    """
    ctx = build_context(synthetic_bundle.draft, mode="draft", blobs=blob_reader())
    credential = next(
        f for f in ctx.index.facts if f.fact_id == "fact.example-credential.expiry.001"
    )
    fact = FactRecord.model_validate(
        {
            **credential.model_dump(mode="json"),
            "value": VALUE_BY_KIND[kind.value],
            "expires_at": None,
        }
    )
    assert (_declared_expiry(fact) is not None) == (kind in VALUE_DATE_KINDS)


def test_a_review_interval_is_not_past_on_the_day_it_falls_due(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """2026-08-10 plus 90 days is 2026-11-08. "Past its review interval" means strictly after that,
    so the boundary day is clean and the next one is not — otherwise every interval would be one day
    shorter than the catalog says."""
    assert completeness_codes(synthetic_bundle, date(2026, 11, 8)).count("expired_review") == 0
    assert completeness_codes(synthetic_bundle, date(2026, 11, 9)).count("expired_review") == 2


def test_a_non_effective_fact_is_not_reported_for_a_lapsed_review(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """Review expiry, like cardinality and exclusivity, is evaluated only over effective facts.

    A rejected or superseded record is already locally blocked; reporting that its review also
    lapsed would give an operator a second finding about a record they have already retired.
    """

    def retire(data: Any) -> None:
        for fact in data["facts"]:
            fact["verification_state"] = "rejected"

    edit(synthetic_bundle, "application/gated-facts.yaml", retire)
    assert completeness_codes(synthetic_bundle, AFTER_REVIEW_INTERVAL).count("expired_review") == 0


# --------------------------------------------------------------------------------------
# The information summary
# --------------------------------------------------------------------------------------


def test_the_summary_is_one_information_row_carrying_every_count_the_design_names(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """§20.5 lists what completeness output includes. One row rather than one per topic, because
    every row would carry the same code and a consumer could not tell them apart."""
    ctx = build_context(synthetic_bundle.draft, mode="draft", blobs=blob_reader())
    summaries = [
        f for f in validate_completeness(ctx, as_of=AFTER_EXPIRY) if f.code == "completeness_counts"
    ]
    assert len(summaries) == 1
    details = summaries[0].details
    assert summaries[0].tier == "information"
    assert set(details) == {
        "conflicts",
        "entity_status_distribution",
        "evidence",
        "exclusions_by_reason",
        "facts_by_state",
        "metric_review",
        "records",
        "source_ledger",
        "surface_coverage",
    }


def test_the_summary_reports_the_source_ledger_totals_the_import_documents_state(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """Counted through a different path than the one that produced them: the expected numbers come
    from the ledger document, not from the summary's own arithmetic."""
    ctx = build_context(synthetic_bundle.draft, mode="draft", blobs=blob_reader())
    ledger = ctx.index.source_ledger
    assert ledger is not None
    summary = next(
        f for f in validate_completeness(ctx, as_of=AFTER_EXPIRY) if f.code == "completeness_counts"
    )
    totals = summary.details["source_ledger"]
    assert isinstance(totals, dict)
    assert totals["denominator"] == len(ledger.records)


def test_the_summary_carries_no_contact_value_or_capture_text(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """A diagnostic is pasted into bug reports. Counts are safe; the strings they were counted from
    are not, and the summary is the one finding that touches every record in the bundle."""
    ctx = build_context(synthetic_bundle.draft, mode="draft", blobs=blob_reader())
    summary = next(
        f for f in validate_completeness(ctx, as_of=AFTER_EXPIRY) if f.code == "completeness_counts"
    )
    rendered = repr(summary.details) + summary.message
    for secret in ("candidate@example.com", "+1 555 0100", "example.com/profile"):
        assert secret not in rendered


# --------------------------------------------------------------------------------------
# Ancestor traversal (§20.6's last clause, reported as completeness)
# --------------------------------------------------------------------------------------


def ancestry_codes(tree: PromotedRevisionTree, *, deep: bool = False) -> list[str]:
    ctx = build_context(
        tree.revision_dir, mode="revision", blobs=blob_reader(), bundle_root=tree.bundle_root
    )
    return sorted(f.code for f in ancestry_completeness(ctx, deep=deep))


def test_an_intact_chain_reports_nothing(chained_tree: PromotedRevisionTree) -> None:
    assert ancestry_codes(chained_tree) == []


def test_a_parentless_revision_has_no_ancestry_to_verify(
    promoted_tree: PromotedRevisionTree,
) -> None:
    assert ancestry_codes(promoted_tree) == []


def test_a_missing_ancestor_is_a_blocker_not_an_error(chained_tree: PromotedRevisionTree) -> None:
    """§21: "Missing or unreadable ancestor | unverifiable_ancestor completeness blocker; selected
    revision remains structurally valid"."""
    parent_digest = chained_tree.documents.manifest.parent_bundle_digest
    assert parent_digest is not None
    shutil.rmtree(revision_root(chained_tree.bundle_root, parent_digest))
    ctx = build_context(
        chained_tree.revision_dir,
        mode="revision",
        blobs=blob_reader(),
        bundle_root=chained_tree.bundle_root,
    )
    found = ancestry_completeness(ctx)
    assert [f.code for f in found] == ["unverifiable_ancestor"]
    assert found[0].tier == "blocker"
    assert found[0].details["reason"] == "absent"
    # The digest layer raises no error about it either — it withholds the candidate comparison and
    # says so at the information tier, which is what keeps the exit code where §21 puts it.
    assert [(f.code, f.tier) for f in validate_digest(ctx)] == [
        ("candidate_digest_unverified", "information")
    ]


def test_an_unreadable_ancestor_manifest_is_a_blocker(
    chained_tree: PromotedRevisionTree,
) -> None:
    """Unreadable is a different fault from absent, and the reason is typed at the raise site rather
    than recovered from the message text."""
    parent_digest = chained_tree.documents.manifest.parent_bundle_digest
    assert parent_digest is not None
    (revision_root(chained_tree.bundle_root, parent_digest) / "manifest.yaml").write_text(
        "not: [a, valid, manifest]\n", encoding="utf-8"
    )
    ctx = build_context(
        chained_tree.revision_dir,
        mode="revision",
        blobs=blob_reader(),
        bundle_root=chained_tree.bundle_root,
    )
    found = ancestry_completeness(ctx)
    assert [(f.code, f.details["reason"]) for f in found] == [
        ("unverifiable_ancestor", "malformed")
    ]


def test_an_ancestor_that_renames_itself_is_a_blocker(
    chained_tree: PromotedRevisionTree,
) -> None:
    """The envelope check: an ancestor directory must hold the manifest whose digest names it.

    Cheap, and it does not deep-parse anything — §20.6 forbids repeating promotion's parent checks
    during ordinary validation, but reading the stored envelope is exactly what it prescribes.
    """
    parent_digest = chained_tree.documents.manifest.parent_bundle_digest
    assert parent_digest is not None
    parent_root = revision_root(chained_tree.bundle_root, parent_digest)
    path = parent_root / "manifest.yaml"
    data = load_yaml_bytes(path.read_bytes(), logical_path=PurePosixPath("manifest.yaml"))
    data["bundle_digest"] = "sha256:" + "a" * 64
    path.write_bytes(quoted_yaml(data, logical_path=PurePosixPath("manifest.yaml")))
    ctx = build_context(
        chained_tree.revision_dir,
        mode="revision",
        blobs=blob_reader(),
        bundle_root=chained_tree.bundle_root,
    )
    assert [f.details["reason"] for f in ancestry_completeness(ctx)] == [
        "declared_digest_mismatch"
    ]


def test_a_mutated_ancestor_is_only_caught_by_the_deep_audit(
    chained_tree: PromotedRevisionTree,
) -> None:
    """Both halves of the §20.6 contract in one test.

    Ordinary validation traverses ancestors through their stored envelopes and does NOT revalidate
    them, so an edited ancestor document is invisible — that is the design's choice, not an
    oversight. `deep=True` is the opt-in audit that recomputes the ancestor's digest from its bytes.
    """
    parent_digest = chained_tree.documents.manifest.parent_bundle_digest
    assert parent_digest is not None
    parent_root = revision_root(chained_tree.bundle_root, parent_digest)
    path = parent_root / "skills" / "inventory.yaml"
    data = load_yaml_bytes(path.read_bytes(), logical_path=PurePosixPath("skills/inventory.yaml"))
    data["skills"][0]["canonical_name"] = "Edited Ancestor"
    path.write_bytes(quoted_yaml(data, logical_path=PurePosixPath("skills/inventory.yaml")))

    assert ancestry_codes(chained_tree) == []
    ctx = build_context(
        chained_tree.revision_dir,
        mode="revision",
        blobs=blob_reader(),
        bundle_root=chained_tree.bundle_root,
    )
    assert [f.details["reason"] for f in ancestry_completeness(ctx, deep=True)] == [
        "content_digest_mismatch"
    ]


def test_a_self_referential_ancestor_terminates(promoted_tree: PromotedRevisionTree) -> None:
    """A revision's digest covers its parent digest, so a genuine cycle is not constructible — but a
    hand-forged directory is, and a traversal without a seen-set would hang instead of reporting."""
    forged = "sha256:" + "b" * 64
    forged_root = revision_root(promoted_tree.bundle_root, forged)
    shutil.copytree(promoted_tree.revision_dir, forged_root)
    path = forged_root / "manifest.yaml"
    data = load_yaml_bytes(path.read_bytes(), logical_path=PurePosixPath("manifest.yaml"))
    data.update({"bundle_digest": forged, "revision": 2, "parent_bundle_digest": forged})
    path.write_bytes(quoted_yaml(data, logical_path=PurePosixPath("manifest.yaml")))

    ctx = build_context(
        forged_root, mode="revision", blobs=blob_reader(), bundle_root=promoted_tree.bundle_root
    )
    assert [f.details["reason"] for f in ancestry_completeness(ctx)] == ["cycle"]


def test_ancestry_is_skipped_for_a_tree_handed_over_without_its_bundle_root(
    chained_tree: PromotedRevisionTree,
) -> None:
    """There is nowhere to look for an ancestor, and inventing a blocker about a directory nobody
    handed over would be a measurement never taken."""
    ctx = build_context(chained_tree.revision_dir, mode="revision", blobs=blob_reader())
    assert ancestry_completeness(ctx) == ()


def test_an_ancestor_from_a_newer_boardwatch_is_a_blocker(
    chained_tree: PromotedRevisionTree,
) -> None:
    """An ancestor this build cannot read is unverifiable, not invalid.

    §21 sends an unsupported schema version to exit 3 when it is the bundle being validated. An
    ANCESTOR is different: the selected revision is perfectly readable, and refusing to complete
    because a historical directory is too new would make one old revision poison every later one.
    """
    parent_digest = chained_tree.documents.manifest.parent_bundle_digest
    assert parent_digest is not None
    path = revision_root(chained_tree.bundle_root, parent_digest) / "manifest.yaml"
    data = load_yaml_bytes(path.read_bytes(), logical_path=PurePosixPath("manifest.yaml"))
    data["schema_version"] = 999
    path.write_bytes(quoted_yaml(data, logical_path=PurePosixPath("manifest.yaml")))
    ctx = build_context(
        chained_tree.revision_dir,
        mode="revision",
        blobs=blob_reader(),
        bundle_root=chained_tree.bundle_root,
    )
    assert [f.details["reason"] for f in ancestry_completeness(ctx)] == ["unsupported_schema"]


def test_an_ancestor_that_is_a_draft_is_a_blocker(chained_tree: PromotedRevisionTree) -> None:
    """Every ancestor was promoted. A draft manifest in a revisions/ directory is a tree that was
    copied in by hand, and its sentinel digests mean it can never be the parent it claims to be."""
    from tests.profile_bundle.conftest import example_source_root

    parent_digest = chained_tree.documents.manifest.parent_bundle_digest
    assert parent_digest is not None
    target = revision_root(chained_tree.bundle_root, parent_digest) / "manifest.yaml"
    target.write_bytes((example_source_root() / "manifest.yaml").read_bytes())
    ctx = build_context(
        chained_tree.revision_dir,
        mode="revision",
        blobs=blob_reader(),
        bundle_root=chained_tree.bundle_root,
    )
    assert [f.details["reason"] for f in ancestry_completeness(ctx)] == ["not_a_revision"]


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads a mode-000 file, so the guard cannot fire")
def test_an_ancestor_manifest_that_cannot_be_read_is_a_blocker(
    chained_tree: PromotedRevisionTree,
) -> None:
    """Present but unreadable is a different fault from absent: one is a restore from backup, the
    other is a permissions problem, and an operator who cannot tell them apart guesses."""
    parent_digest = chained_tree.documents.manifest.parent_bundle_digest
    assert parent_digest is not None
    path = revision_root(chained_tree.bundle_root, parent_digest) / "manifest.yaml"
    path.chmod(0o000)
    try:
        ctx = build_context(
            chained_tree.revision_dir,
            mode="revision",
            blobs=blob_reader(),
            bundle_root=chained_tree.bundle_root,
        )
        found = ancestry_completeness(ctx)
        assert [f.details["reason"] for f in found] == ["unreadable"]
        # Both renderings emit `message` verbatim, and `reports.py` states that a diagnostic never
        # carries a value like this. `str(OSError)` appends the absolute path it failed on, so the
        # reason has to be taken from the exception without it.
        assert str(chained_tree.bundle_root) not in found[0].message
    finally:
        path.chmod(0o644)


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads a mode-000 file, so the guard cannot fire")
def test_a_deep_audit_of_an_unreadable_ancestor_document_carries_no_filesystem_path(
    chained_tree: PromotedRevisionTree,
) -> None:
    """The same leak as the test above, one layer up, where fixing the manifest read did not reach.

    The deep audit loads the ancestor's DOCUMENTS, and that read raises a `BundleIoError` built from
    `str(OSError)` — which appends the absolute path it failed on. Interpolating the exception whole
    put a `$HOME` path into an `unverifiable_ancestor` message, which both renderings emit verbatim.
    Only `deep=True` reaches this route, so the shallow test above could not see it.
    """
    parent_digest = chained_tree.documents.manifest.parent_bundle_digest
    assert parent_digest is not None
    path = revision_root(chained_tree.bundle_root, parent_digest) / "facts" / "identity.yaml"

    def audited() -> tuple[Any, ...]:
        ctx = build_context(
            chained_tree.revision_dir,
            mode="revision",
            blobs=blob_reader(),
            bundle_root=chained_tree.bundle_root,
        )
        return ancestry_completeness(ctx, deep=True)

    # The negative control for a test about a leak: the same audit over the same chain with nothing
    # chmodded reports nothing at all, so the finding below is the permission and not the audit.
    assert audited() == ()
    path.chmod(0o000)
    try:
        found = audited()
        assert len(found) == 1
        assert str(chained_tree.bundle_root) not in found[0].message
        assert (found[0].code, found[0].details["reason"]) == (
            "unverifiable_ancestor",
            "unreadable",
        )
    finally:
        path.chmod(0o644)

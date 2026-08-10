"""Referential validation: every reference resolves, to the right kind, and the graph holds.

The negative cases edit the comprehensive example through the same round-trip the structural tests
use. Two properties get more attention than the rest because they are the ones a plausible-looking
implementation gets wrong:

- **Resolution and kind are separate findings.** A test asserts a reference to a real record of the
  wrong kind reports `wrong_reference_kind`, not `broken_reference`.
- **Evidence symmetry is compared over all three relationship sets.** A contextual-only attachment is
  legitimate, and a check that demanded `supports` would force every one of them to overstate itself.
"""

from __future__ import annotations

from typing import Any

import pytest

from boardwatch.profile_bundle.errors import IssueCode
from boardwatch.profile_bundle.validation import (
    build_context,
    records_blocked_by_unresolved_conflicts,
    validate_referential,
)
from boardwatch.profile_bundle.yaml_loader import load_yaml_bytes
from tests.profile_bundle.conftest import SyntheticBundle, blob_reader
from tests.profile_bundle.test_profile_bundle_structural_validation import edit_document

ABSENT_FACT = "fact.does-not-exist.001"
ABSENT_EVIDENCE = "evidence.does-not-exist.001"


def referential_findings(bundle: SyntheticBundle) -> tuple[Any, ...]:
    ctx = build_context(
        bundle.draft, mode="draft", blobs=blob_reader(), bundle_root=bundle.root
    )
    return validate_referential(ctx)


def read(bundle: SyntheticBundle, relative: str) -> Any:
    return load_yaml_bytes(bundle.document(relative).read_bytes(), logical_path=relative)


def only(findings: tuple[Any, ...], code: IssueCode) -> Any:
    matching = [finding for finding in findings if finding.code == code]
    assert len(matching) == 1, f"expected exactly one {code}, got {[f.code for f in findings]}"
    return matching[0]


# --------------------------------------------------------------------------------------
# The clean case
# --------------------------------------------------------------------------------------


def test_the_comprehensive_example_has_no_referential_findings(
    synthetic_bundle: SyntheticBundle,
) -> None:
    assert referential_findings(synthetic_bundle) == ()


def test_the_example_actually_exercises_the_graph_it_is_checking(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """A clean result over an empty graph would prove nothing.

    Asserts the example carries at least one of each edge the layer checks, so
    `test_the_comprehensive_example_has_no_referential_findings` above is a real result.
    """
    ctx = build_context(synthetic_bundle.draft, mode="draft")
    assert any(fact.evidence_ids for fact in ctx.index.facts), "no fact cites evidence"
    assert any(fact.supersedes_fact_ids for fact in ctx.index.facts), "no supersession edge"
    assert ctx.index.conflicts, "no conflict group"
    assert ctx.index.rulings, "no ruling"
    assert ctx.index.relations, "no relation"
    assert ctx.index.claims and any(c.required_fact_ids for c in ctx.index.claims)
    assert ctx.index.metrics and any(m.evidence_ids for m in ctx.index.metrics)
    assert ctx.index.skills and any(s.supporting_fact_ids for s in ctx.index.skills)
    assert ctx.index.candidates and ctx.index.ledger_records and ctx.index.exclusions


# --------------------------------------------------------------------------------------
# Resolution versus kind
# --------------------------------------------------------------------------------------


def test_a_fact_citing_absent_evidence_is_a_broken_reference(
    synthetic_bundle: SyntheticBundle,
) -> None:
    def repoint(data: Any) -> None:
        data["facts"][0]["evidence_ids"] = [ABSENT_EVIDENCE]

    edit_document(synthetic_bundle, "facts/education.yaml", repoint)
    finding = only(referential_findings(synthetic_bundle), IssueCode.BROKEN_REFERENCE)
    assert finding.details["target"] == ABSENT_EVIDENCE
    assert finding.details["field"] == "evidence_ids"
    assert finding.path == "facts/education.yaml"


def test_a_reference_to_a_real_record_of_the_wrong_kind_is_a_kind_finding(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """The distinction that matters: naming a real record of the wrong kind is not a missing ID.

    Exercised through `evidence.supports_record_ids`, which is one of the few reference fields typed
    as a bare `RecordId`. Most reference fields are typed to a single kind (`required_metric_ids` is
    a `MetricId`), so the model's pattern refuses the wrong kind before this layer ever sees it —
    which is why the reachable case had to be chosen deliberately rather than assumed.
    """
    ctx = build_context(synthetic_bundle.draft, mode="draft")
    an_entity = sorted(ctx.index.entities)[0]
    # A class with no "must support at least one X" contract of its own, so the edit exercises the
    # reference check rather than tripping the evidence class model first.
    unconstrained = next(
        record.evidence_id
        for record in ctx.index.evidence
        if str(record.evidence_class) in ("public_record", "private_document")
    )

    def add_an_entity(data: Any) -> None:
        for record in data["evidence"]:
            if record["evidence_id"] == unconstrained:
                record["supports_record_ids"] = [
                    *record["supports_record_ids"],
                    an_entity,
                ]

    edit_document(synthetic_bundle, "evidence/records.yaml", add_an_entity)
    findings = referential_findings(synthetic_bundle)
    kind_findings = [f for f in findings if f.code == IssueCode.WRONG_REFERENCE_KIND]
    assert [f.details["target"] for f in kind_findings] == [an_entity]
    assert [f.details["found_kind"] for f in kind_findings] == [an_entity.split(".")[0]]
    assert not [f for f in findings if f.code == IssueCode.BROKEN_REFERENCE]
    # And not ALSO an asymmetry: one edit, one cause, one finding.
    assert not [f for f in findings if f.code == IssueCode.EVIDENCE_LINK_ASYMMETRY]


def test_typed_reference_fields_refuse_the_wrong_kind_before_this_layer(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """Recorded so the coverage above is not mistaken for a gap.

    A claim's `required_metric_ids` is a `MetricId`, so pointing it at a real fact is refused at
    parse time, not reported as a referential finding. The guarantee is stronger, not weaker — but it
    lands in a different place, and a reader comparing this file against §20.2 should see why.
    """
    facts = read(synthetic_bundle, "facts/education.yaml")

    def repoint(data: Any) -> None:
        data["claims"][0]["required_metric_ids"] = [facts["facts"][0]["fact_id"]]

    edit_document(synthetic_bundle, "claims/bullet-candidates.yaml", repoint)
    with pytest.raises(Exception, match="could not be parsed"):
        referential_findings(synthetic_bundle)


def test_an_approval_for_an_absent_record_is_reported(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """§13 binds an approval to a record and a digest. An approval whose target is not in the
    revision authorizes nothing, so it must not read as authority."""
    stamp = {
        "approval_stamp_id": "approval-stamp.synthetic.001",
        "candidate_content_digest": "sha256:" + "0" * 64,
        "approved_at": "2026-08-10T12:00:00Z",
        "approved_via": "controlling_terminal",
        "entries": [
            {
                "approval_id": "approval.dangling.001",
                "action": "confirm_fact",
                "target_record_id": ABSENT_FACT,
                "target_content_digest": "sha256:" + "1" * 64,
                "resulting_state": "owner_confirmed",
            }
        ],
    }
    edit_document(
        synthetic_bundle,
        "history/approvals.yaml",
        lambda data: data.__setitem__("approvals", [stamp]),
    )
    finding = only(referential_findings(synthetic_bundle), IssueCode.BROKEN_REFERENCE)
    assert finding.record_id == "approval.dangling.001"
    assert finding.details["target"] == ABSENT_FACT


def test_a_change_naming_a_removed_record_is_a_warning_not_an_error(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """A deliberate asymmetry with the approval case above.

    §17 makes the change ledger append-only history, so an entry describing the revision that
    *removed* a record permanently names an ID the tree no longer defines. Erroring would make a
    correct history unrepresentable; silence would hide a typo. It is a warning, and a warning must
    not change the exit code.
    """
    change = {
        "change_id": "change.synthetic.001",
        "revision": 1,
        "parent_bundle_digest": None,
        "actor": "owner",
        "authorized_by": "owner",
        "summary": "Removed a fact that no longer applies.",
        "changed_record_ids": [ABSENT_FACT],
        "created_at": "2026-08-10T12:00:00Z",
    }
    edit_document(
        synthetic_bundle,
        "history/changes.yaml",
        lambda data: data.__setitem__("changes", [change]),
    )
    findings = referential_findings(synthetic_bundle)
    finding = only(findings, IssueCode.BROKEN_REFERENCE)
    assert finding.tier == "warning"
    assert finding.record_id == "change.synthetic.001"
    assert not [f for f in findings if f.tier in ("error", "blocker")]


# --------------------------------------------------------------------------------------
# Bidirectional evidence links
# --------------------------------------------------------------------------------------


def test_a_fact_citing_evidence_that_does_not_name_it_back_is_an_asymmetry(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """One direction alone would let a fact cite evidence about something else entirely."""
    education = read(synthetic_bundle, "facts/education.yaml")
    fact_id = education["facts"][0]["fact_id"]

    def unlink(data: Any) -> None:
        for record in data["evidence"]:
            for relationship in (
                "supports_record_ids",
                "contradicts_record_ids",
                "contextualizes_record_ids",
            ):
                record[relationship] = [
                    target for target in record[relationship] if target != fact_id
                ]

    edit_document(synthetic_bundle, "evidence/records.yaml", unlink)
    findings = [
        f
        for f in referential_findings(synthetic_bundle)
        if f.code == IssueCode.EVIDENCE_LINK_ASYMMETRY
    ]
    assert findings, "removing the reverse link must be reported"
    assert all(f.details["direction"] == "record_to_evidence" for f in findings)
    assert all(f.record_id == fact_id for f in findings)


def test_evidence_naming_a_fact_that_does_not_cite_it_is_an_asymmetry(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """The other direction, checked independently: the index builds the record side and the layer
    reads the evidence side, so neither can be derived from the other."""
    education = read(synthetic_bundle, "facts/education.yaml")
    fact_id = education["facts"][0]["fact_id"]

    def drop_citations(data: Any) -> None:
        for fact in data["facts"]:
            if fact["fact_id"] == fact_id:
                fact["evidence_ids"] = []

    edit_document(synthetic_bundle, "facts/education.yaml", drop_citations)
    findings = [
        f
        for f in referential_findings(synthetic_bundle)
        if f.code == IssueCode.EVIDENCE_LINK_ASYMMETRY
    ]
    assert findings
    assert all(f.details["direction"] == "evidence_to_record" for f in findings)
    assert all(f.details["supported_record_id"] == fact_id for f in findings)


def test_a_contextual_only_attachment_is_symmetric(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """§12 makes the relationship a closed choice of three, and says in the same breath that a
    contextual source cannot satisfy a verification requirement.

    So `contextualizes` is a legitimate reverse link, and demanding `supports` here would force every
    contextual attachment to overstate itself. Asserted against the example's own secondary-summary
    evidence, so the case is shown to exist rather than constructed.
    """
    ctx = build_context(synthetic_bundle.draft, mode="draft")
    contextual = [
        record
        for record in ctx.index.evidence
        if record.contextualizes_record_ids and not record.supports_record_ids
    ]
    assert contextual, "the example must carry a contextual-only evidence record"
    cited_by = {
        target for record in contextual for target in record.contextualizes_record_ids
    }
    assert any(
        set(fact.evidence_ids) & {r.evidence_id for r in contextual}
        for fact in ctx.index.facts
        if fact.fact_id in cited_by
    ), "the contextual evidence must be cited by the fact it contextualizes"
    assert not [
        f for f in validate_referential(ctx) if f.code == IssueCode.EVIDENCE_LINK_ASYMMETRY
    ]


# --------------------------------------------------------------------------------------
# Supersession
# --------------------------------------------------------------------------------------


def test_a_supersession_cycle_is_reported(synthetic_bundle: SyntheticBundle) -> None:
    """A cycle makes "the current value" undefined: every fact in it is superseded, so the predicate
    silently loses its answer while every record still validates."""
    education = read(synthetic_bundle, "facts/education.yaml")
    first = education["facts"][0]["fact_id"]
    second = education["facts"][1]["fact_id"]

    def make_cycle(data: Any) -> None:
        for fact in data["facts"]:
            if fact["fact_id"] == first:
                fact["supersedes_fact_ids"] = [second]
            elif fact["fact_id"] == second:
                fact["supersedes_fact_ids"] = [first]

    edit_document(synthetic_bundle, "facts/education.yaml", make_cycle)
    finding = only(referential_findings(synthetic_bundle), IssueCode.SUPERSESSION_CYCLE)
    assert set(finding.details["cycle"]) == {first, second}


def test_a_fact_superseding_itself_is_refused_before_this_layer(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """The one-step cycle is a model-level refusal (`_no_self_supersession`), so it never reaches the
    graph walk. Recorded here so the two checks are not mistaken for one."""
    education = read(synthetic_bundle, "facts/education.yaml")
    fact_id = education["facts"][0]["fact_id"]

    def self_supersede(data: Any) -> None:
        data["facts"][0]["supersedes_fact_ids"] = [fact_id]

    edit_document(synthetic_bundle, "facts/education.yaml", self_supersede)
    with pytest.raises(Exception) as raised:
        referential_findings(synthetic_bundle)
    assert "could not be parsed" in str(raised.value)


# --------------------------------------------------------------------------------------
# Conflicts and rulings
# --------------------------------------------------------------------------------------


def test_a_candidate_about_another_predicate_is_reported(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """A conflict group is "competing answers to one question". A candidate about a different
    predicate is not a competing answer, and a ruling picking it would settle nothing."""
    ctx = build_context(synthetic_bundle.draft, mode="draft")
    conflict = ctx.index.conflicts[0]
    victim = conflict.candidate_fact_ids[0]
    fact = ctx.index.fact(victim)
    assert fact is not None
    owning = ctx.index.paths[victim].as_posix()

    def change_predicate(data: Any) -> None:
        for entry in data["facts"]:
            if entry["fact_id"] == victim:
                entry["predicate"] = "predicate.employment.title"

    edit_document(synthetic_bundle, owning, change_predicate)
    findings = referential_findings(synthetic_bundle)
    mismatches = [f for f in findings if f.code == IssueCode.CONFLICT_CANDIDATE_MISMATCH]
    assert [f.record_id for f in mismatches] == [victim]


def test_a_fact_naming_a_group_that_does_not_list_it_is_reported(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """Checked from the fact's side as well as the group's, because either side alone can be wrong.

    A fact that thinks it is disputed while the group does not list it would be blocked by nothing.
    """
    ctx = build_context(synthetic_bundle.draft, mode="draft")
    conflict = ctx.index.conflicts[0]
    outsider = next(
        fact
        for fact in ctx.index.facts
        if fact.conflict_group_id is None
        and ctx.index.paths[fact.fact_id].as_posix().startswith("facts/")
    )
    owning = ctx.index.paths[outsider.fact_id].as_posix()

    def join_the_group(data: Any) -> None:
        for entry in data["facts"]:
            if entry["fact_id"] == outsider.fact_id:
                entry["conflict_group_id"] = conflict.conflict_id

    edit_document(synthetic_bundle, owning, join_the_group)
    findings = referential_findings(synthetic_bundle)
    mismatches = [f for f in findings if f.code == IssueCode.CONFLICT_CANDIDATE_MISMATCH]
    assert [f.record_id for f in mismatches] == [outsider.fact_id]


def test_an_active_ruling_belonging_to_another_conflict_is_reported(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """Only the assembled tree can see this: the ID is a well-formed `RulingId`, and the ruling it
    names is real — it just rules on a different group."""
    ctx = build_context(synthetic_bundle.draft, mode="draft")
    resolved = next(c for c in ctx.index.conflicts if c.active_ruling_id is not None)
    other = next(c for c in ctx.index.conflicts if c.conflict_id != resolved.conflict_id)
    existing = ctx.index.rulings[0]
    foreign_id = "ruling.synthetic.foreign.001"

    def add_a_ruling_on_the_other_group(data: Any) -> None:
        data["rulings"] = [
            *data["rulings"],
            {
                "ruling_id": foreign_id,
                "conflict_id": other.conflict_id,
                "decision": "keep_unresolved",
                "selected_fact_id": None,
                "rejected_fact_ids": [],
                "rationale": "Left undecided pending a record that distinguishes the two dates.",
                "owner_evidence_id": existing.owner_evidence_id,
                "decided_at": "2026-08-10",
            },
        ]

    def repoint(data: Any) -> None:
        for conflict in data["conflicts"]:
            if conflict["conflict_id"] == resolved.conflict_id:
                conflict["active_ruling_id"] = foreign_id

    edit_document(synthetic_bundle, "conflicts/rulings.yaml", add_a_ruling_on_the_other_group)
    edit_document(synthetic_bundle, "conflicts/groups.yaml", repoint)
    findings = referential_findings(synthetic_bundle)
    mismatches = [f for f in findings if f.code == IssueCode.ACTIVE_RULING_MISMATCH]
    assert [f.record_id for f in mismatches] == [resolved.conflict_id]
    assert mismatches[0].details["ruling_id"] == foreign_id


def test_a_resolved_group_with_no_active_ruling_is_refused_before_this_layer(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """`ConflictRecord._resolved_groups_name_their_ruling` owns this, so the referential layer
    deliberately does not re-check it. Pinned here so removing the model validator fails a test."""

    def unset(data: Any) -> None:
        for conflict in data["conflicts"]:
            if conflict["state"] == "resolved":
                conflict["active_ruling_id"] = None

    edit_document(synthetic_bundle, "conflicts/groups.yaml", unset)
    with pytest.raises(Exception, match="could not be parsed"):
        referential_findings(synthetic_bundle)


def test_a_ruling_deciding_a_fact_outside_its_group_is_reported(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """A ruling may only decide between the facts its own group disputes; otherwise one owner
    decision silently settles a question it never considered."""
    education = read(synthetic_bundle, "facts/education.yaml")
    outsider = education["facts"][0]["fact_id"]

    def reject_an_outsider(data: Any) -> None:
        data["rulings"][0]["rejected_fact_ids"] = [outsider]

    edit_document(synthetic_bundle, "conflicts/rulings.yaml", reject_an_outsider)
    findings = referential_findings(synthetic_bundle)
    mismatches = [f for f in findings if f.code == IssueCode.ACTIVE_RULING_MISMATCH]
    assert mismatches and all(f.details["target"] == outsider for f in mismatches)


# --------------------------------------------------------------------------------------
# Relation catalog typing
# --------------------------------------------------------------------------------------


def test_an_uncatalogued_relation_type_is_reported(
    synthetic_bundle: SyntheticBundle,
) -> None:
    def retype(data: Any) -> None:
        data["relations"][0]["relation_type"] = "not-in-the-catalog"

    edit_document(synthetic_bundle, "relations/records.yaml", retype)
    finding = only(referential_findings(synthetic_bundle), IssueCode.RELATION_KIND_MISMATCH)
    assert finding.details["relation_type"] == "not-in-the-catalog"


def test_a_relation_endpoint_of_an_illegal_entity_kind_is_reported(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """The catalog row names which entity kinds each endpoint may be. Without this a typed relation
    could be authored between any two entities and still validate."""
    ctx = build_context(synthetic_bundle.draft, mode="draft")
    catalog = ctx.index.relation_catalog
    assert catalog is not None
    relation = ctx.index.relations[0]
    spec = catalog.by_type[relation.relation_type]
    illegal = next(
        entity_id
        for entity_id in ctx.index.entities
        if entity_id.split(".")[0] not in {str(kind) for kind in spec.legal_source_kinds}
    )

    def repoint(data: Any) -> None:
        for entry in data["relations"]:
            if entry["relation_id"] == relation.relation_id:
                entry["source_id"] = illegal

    edit_document(synthetic_bundle, "relations/records.yaml", repoint)
    findings = referential_findings(synthetic_bundle)
    mismatches = [f for f in findings if f.code == IssueCode.RELATION_KIND_MISMATCH]
    assert mismatches and mismatches[0].details["field"] == "source_id"


def test_nothing_is_checked_when_the_relation_catalog_is_absent(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """A missing catalog is a structural finding. Inventing a permissive default here would let a
    typed relation be authored against anything with no diagnostic anywhere."""
    synthetic_bundle.document("policy/relations.yaml").unlink()
    findings = referential_findings(synthetic_bundle)
    assert not [f for f in findings if f.code == IssueCode.RELATION_KIND_MISMATCH]


# --------------------------------------------------------------------------------------
# Import ledger cross-references
# --------------------------------------------------------------------------------------


def test_a_candidate_naming_an_absent_source_record_is_reported(
    synthetic_bundle: SyntheticBundle,
) -> None:
    def repoint(data: Any) -> None:
        data["candidates"][0]["source_record_id"] = "source-record." + "a" * 64

    edit_document(synthetic_bundle, "imports/candidates.yaml", repoint)
    findings = [f for f in referential_findings(synthetic_bundle) if f.path]
    broken = [
        f
        for f in findings
        if f.code == IssueCode.BROKEN_REFERENCE and f.path == "imports/candidates.yaml"
    ]
    assert len(broken) == 1
    assert broken[0].details["field"] == "source_record_id"


def test_an_exclusion_for_an_absent_source_record_is_reported(
    synthetic_bundle: SyntheticBundle,
) -> None:
    def repoint(data: Any) -> None:
        data["exclusions"][0]["source_record_id"] = "source-record." + "b" * 64

    edit_document(synthetic_bundle, "imports/exclusions.yaml", repoint)
    broken = [
        f
        for f in referential_findings(synthetic_bundle)
        if f.code == IssueCode.BROKEN_REFERENCE and f.path == "imports/exclusions.yaml"
    ]
    assert len(broken) == 1


# --------------------------------------------------------------------------------------
# Unresolved-conflict locality
# --------------------------------------------------------------------------------------


def test_an_unresolved_conflict_blocks_only_its_own_candidates(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """The locality property, stated as a test because getting it wrong is silent and expensive.

    One disputed job title must not suppress the whole employment. The blocked set is exactly the
    candidates of unresolved groups — nothing about the subject, nothing about the file.
    """
    ctx = build_context(synthetic_bundle.draft, mode="draft")
    unresolved = ctx.index.unresolved_conflict_ids
    assert unresolved, "the example must carry an unresolved group"

    blocked = records_blocked_by_unresolved_conflicts(ctx.index)
    expected = {
        fact_id
        for conflict in ctx.index.conflicts
        if conflict.conflict_id in unresolved
        for fact_id in conflict.candidate_fact_ids
    }
    assert blocked == expected

    # And the locality claim itself: a fact about the same subject, outside the group, is not blocked.
    disputed = next(c for c in ctx.index.conflicts if c.conflict_id in unresolved)
    siblings = [
        fact
        for fact in ctx.index.facts
        if fact.subject_id == disputed.subject_id
        and fact.fact_id not in disputed.candidate_fact_ids
    ]
    assert siblings, "the example must carry an undisputed fact about the disputed subject"
    assert not {fact.fact_id for fact in siblings} & blocked


def test_a_resolved_group_blocks_nothing_and_a_reopened_one_blocks(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """`reopened` counts as unresolved: new evidence unsettled a previous ruling, so its candidates
    are undecided again. Treating it as settled would keep using the superseded answer."""
    ctx = build_context(synthetic_bundle.draft, mode="draft")
    resolved = [c for c in ctx.index.conflicts if str(c.state) == "resolved"]
    assert resolved, "the example must carry a resolved group"
    blocked = records_blocked_by_unresolved_conflicts(ctx.index)
    for conflict in resolved:
        assert not set(conflict.candidate_fact_ids) & blocked

    def reopen(data: Any) -> None:
        for conflict in data["conflicts"]:
            if conflict["state"] == "resolved":
                conflict["state"] = "reopened"

    edit_document(synthetic_bundle, "conflicts/groups.yaml", reopen)
    reopened_ctx = build_context(synthetic_bundle.draft, mode="draft")
    reopened_blocked = records_blocked_by_unresolved_conflicts(reopened_ctx.index)
    assert set(resolved[0].candidate_fact_ids) <= reopened_blocked

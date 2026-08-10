"""Layer 2: every reference resolves, to a record of the required kind, and the graph is consistent.

Two things here are easy to get subtly wrong, so they are spelled out.

**Resolving and kind-checking are separate findings.** A reference to an absent ID is
`broken_reference`; a reference that resolves to the wrong kind of record is `wrong_reference_kind`.
Collapsing them would let a typo that happens to name a real record of another kind report as a
missing ID, and the operator would look for the wrong bug.

**Bidirectional evidence links are compared in both directions independently.** §12 makes the fact
cite its evidence and the evidence name what it supports. The index builds one side from the records
and this layer reads the other side from the evidence, so an asymmetry cannot be hidden by a helper
that derives one from the other.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping, Sequence
from typing import Final

from boardwatch.profile_bundle.errors import Diagnostic, IssueCode, diagnostic
from boardwatch.profile_bundle.index import BundleIndex
from boardwatch.profile_bundle.models.base import (
    ENTITY_PREFIXES,
    EntityKind,
    entity_kind_of,
    prefix_of,
)
from boardwatch.profile_bundle.validation.context import ValidationContext

_ENTITY_KINDS: Final[frozenset[str]] = frozenset(ENTITY_PREFIXES)


def validate_referential(ctx: ValidationContext) -> tuple[Diagnostic, ...]:
    """Every referential finding in the tree, unsorted."""
    return tuple(
        finding
        for check in (
            _fact_references,
            _contact_and_relation_references,
            _skill_references,
            _metric_references,
            _evidence_references,
            _conflict_references,
            _ruling_references,
            _claim_references,
            _change_and_approval_references,
            _evidence_links_are_symmetric,
            _supersession_graph_is_acyclic,
            _conflict_candidates_agree_with_their_group,
            _active_rulings_belong_to_their_conflict,
            _relation_endpoints_match_the_catalog,
            _import_references,
        )
        for finding in check(ctx)
    )


# --------------------------------------------------------------------------------------
# The one reference check every field goes through
# --------------------------------------------------------------------------------------


def _resolve(
    index: BundleIndex,
    *,
    referrer: str,
    field: str,
    target: str,
    expected: Iterable[str],
    path: str | None,
) -> Diagnostic | None:
    """`None` when `target` resolves to a record whose prefix is in `expected`.

    `expected` is a set of ID prefixes rather than a set of model classes, because that is what the
    reference field's own type alias constrains: comparing the same thing in both places is what
    makes a mismatch here mean the authored data is wrong rather than the model.
    """
    allowed = frozenset(expected)
    record = index.get(target)
    if record is None:
        return diagnostic(
            IssueCode.BROKEN_REFERENCE,
            f"{referrer}.{field} names {target}, which no document defines",
            path=path,
            record_id=referrer,
            field=field,
            target=target,
        )
    found = prefix_of(target)
    if found in allowed or (allowed == _ENTITY_KINDS and found in _ENTITY_KINDS):
        return None
    return diagnostic(
        IssueCode.WRONG_REFERENCE_KIND,
        f"{referrer}.{field} names {target}, a {found} record; expected "
        f"{', '.join(sorted(allowed))}",
        path=path,
        record_id=referrer,
        field=field,
        target=target,
        found_kind=found,
    )


def _each(
    ctx: ValidationContext,
    *,
    referrer: str,
    field: str,
    targets: Sequence[str],
    expected: Iterable[str],
) -> Iterator[Diagnostic]:
    allowed = frozenset(expected)
    path = ctx.index.path_of(referrer)
    for target in targets:
        found = _resolve(
            ctx.index,
            referrer=referrer,
            field=field,
            target=target,
            expected=allowed,
            path=path,
        )
        if found is not None:
            yield found


def _one(
    ctx: ValidationContext,
    *,
    referrer: str,
    field: str,
    target: str | None,
    expected: Iterable[str],
) -> Iterator[Diagnostic]:
    if target is None:
        return
    yield from _each(ctx, referrer=referrer, field=field, targets=(target,), expected=expected)


# --------------------------------------------------------------------------------------
# Per-record-kind reference checks
# --------------------------------------------------------------------------------------


def _fact_references(ctx: ValidationContext) -> Iterator[Diagnostic]:
    for fact in ctx.index.facts:
        yield from _one(
            ctx,
            referrer=fact.fact_id,
            field="subject_id",
            target=fact.subject_id,
            expected=_ENTITY_KINDS,
        )
        yield from _each(
            ctx,
            referrer=fact.fact_id,
            field="evidence_ids",
            targets=fact.evidence_ids,
            expected=("evidence",),
        )
        yield from _one(
            ctx,
            referrer=fact.fact_id,
            field="conflict_group_id",
            target=fact.conflict_group_id,
            expected=("conflict",),
        )
        yield from _each(
            ctx,
            referrer=fact.fact_id,
            field="supersedes_fact_ids",
            targets=fact.supersedes_fact_ids,
            expected=("fact",),
        )
        if fact.value.type == "skill_ref":
            yield from _one(
                ctx,
                referrer=fact.fact_id,
                field="value.skill_id",
                target=fact.value.skill_id,
                expected=("skill",),
            )


def _contact_and_relation_references(ctx: ValidationContext) -> Iterator[Diagnostic]:
    for contact in ctx.index.contacts:
        yield from _one(
            ctx,
            referrer=contact.contact_id,
            field="person_id",
            target=contact.person_id,
            expected=("person",),
        )
    for relation in ctx.index.relations:
        yield from _one(
            ctx,
            referrer=relation.relation_id,
            field="source_id",
            target=relation.source_id,
            expected=_ENTITY_KINDS,
        )
        yield from _one(
            ctx,
            referrer=relation.relation_id,
            field="target_id",
            target=relation.target_id,
            expected=_ENTITY_KINDS,
        )


def _skill_references(ctx: ValidationContext) -> Iterator[Diagnostic]:
    for skill in ctx.index.skills:
        yield from _each(
            ctx,
            referrer=skill.skill_id,
            field="supporting_fact_ids",
            targets=skill.supporting_fact_ids,
            expected=("fact",),
        )


def _metric_references(ctx: ValidationContext) -> Iterator[Diagnostic]:
    for metric in ctx.index.metrics:
        yield from _one(
            ctx,
            referrer=metric.metric_id,
            field="subject_id",
            target=metric.subject_id,
            expected=_ENTITY_KINDS,
        )
        yield from _each(
            ctx,
            referrer=metric.metric_id,
            field="evidence_ids",
            targets=metric.evidence_ids,
            expected=("evidence",),
        )


#: Record kinds evidence may point at. §12 lets evidence support a fact, a metric, a skill, or a
#: claim; pointing at an entity or a ledger row would make "supports" meaningless.
_EVIDENCE_TARGET_KINDS: Final[tuple[str, ...]] = ("fact", "metric", "skill", "claim")


def _evidence_references(ctx: ValidationContext) -> Iterator[Diagnostic]:
    for record in ctx.index.evidence:
        evidence_id = record.evidence_id
        for field in ("supports_record_ids", "contradicts_record_ids", "contextualizes_record_ids"):
            yield from _each(
                ctx,
                referrer=evidence_id,
                field=field,
                targets=getattr(record, field),
                expected=_EVIDENCE_TARGET_KINDS,
            )


def _conflict_references(ctx: ValidationContext) -> Iterator[Diagnostic]:
    for conflict in ctx.index.conflicts:
        yield from _one(
            ctx,
            referrer=conflict.conflict_id,
            field="subject_id",
            target=conflict.subject_id,
            expected=_ENTITY_KINDS,
        )
        yield from _each(
            ctx,
            referrer=conflict.conflict_id,
            field="candidate_fact_ids",
            targets=conflict.candidate_fact_ids,
            expected=("fact",),
        )
        yield from _one(
            ctx,
            referrer=conflict.conflict_id,
            field="active_ruling_id",
            target=conflict.active_ruling_id,
            expected=("ruling",),
        )


def _ruling_references(ctx: ValidationContext) -> Iterator[Diagnostic]:
    for ruling in ctx.index.rulings:
        yield from _one(
            ctx,
            referrer=ruling.ruling_id,
            field="conflict_id",
            target=ruling.conflict_id,
            expected=("conflict",),
        )
        yield from _one(
            ctx,
            referrer=ruling.ruling_id,
            field="selected_fact_id",
            target=ruling.selected_fact_id,
            expected=("fact",),
        )
        yield from _each(
            ctx,
            referrer=ruling.ruling_id,
            field="rejected_fact_ids",
            targets=ruling.rejected_fact_ids,
            expected=("fact",),
        )
        yield from _one(
            ctx,
            referrer=ruling.ruling_id,
            field="owner_evidence_id",
            target=ruling.owner_evidence_id,
            expected=("evidence",),
        )


def _claim_references(ctx: ValidationContext) -> Iterator[Diagnostic]:
    for claim in ctx.index.claims:
        yield from _one(
            ctx,
            referrer=claim.claim_id,
            field="subject_id",
            target=claim.subject_id,
            expected=_ENTITY_KINDS,
        )
        yield from _each(
            ctx,
            referrer=claim.claim_id,
            field="required_fact_ids",
            targets=claim.required_fact_ids,
            expected=("fact",),
        )
        yield from _each(
            ctx,
            referrer=claim.claim_id,
            field="required_metric_ids",
            targets=claim.required_metric_ids,
            expected=("metric",),
        )
        yield from _each(
            ctx,
            referrer=claim.claim_id,
            field="metric_mentions",
            targets=tuple(mention.metric_id for mention in claim.metric_mentions),
            expected=("metric",),
        )


def _change_and_approval_references(ctx: ValidationContext) -> Iterator[Diagnostic]:
    """Change and approval references.

    An approval entry's target MUST resolve: §13 binds the approval to a record and a content
    digest, and an approval for a record that is not here authorizes nothing.

    A change record's `changed_record_ids` is treated as a WARNING when it does not resolve, and
    that is a deliberate asymmetry. §17 makes the ledger append-only history, so an entry describing
    the revision that *removed* a record permanently names an ID the tree no longer defines.
    Erroring would make a correct history unrepresentable; staying silent would hide a typo. A
    warning says it without making the bundle invalid.
    """
    for change in ctx.index.changes:
        path = ctx.index.path_of(change.change_id)
        for target in change.changed_record_ids:
            if ctx.index.get(target) is not None:
                continue
            yield diagnostic(
                IssueCode.BROKEN_REFERENCE,
                f"{change.change_id}.changed_record_ids names {target}, which this revision does "
                "not define; expected if that change removed it",
                path=path,
                record_id=change.change_id,
                tier="warning",
                field="changed_record_ids",
                target=target,
            )

    for approval_id, entry in sorted(ctx.index.approval_entries.items()):
        if ctx.index.get(entry.target_record_id) is not None:
            continue
        yield diagnostic(
            IssueCode.BROKEN_REFERENCE,
            f"approval {approval_id} approves {entry.target_record_id}, which this revision does "
            "not define; an approval for an absent record authorizes nothing",
            path="history/approvals.yaml",
            record_id=approval_id,
            field="target_record_id",
            target=entry.target_record_id,
        )


def _import_references(ctx: ValidationContext) -> Iterator[Diagnostic]:
    """Ledger cross-references. The counting and idempotence rules belong to the import layer.

    Only resolution is checked here: a candidate naming a source record that is not in the ledger,
    or a ledger record naming a candidate that is not in the package, is a broken graph regardless
    of whether the denominators add up.
    """
    ledger_ids = {record.source_record_id for record in ctx.index.ledger_records}
    candidate_ids = {candidate.candidate_id for candidate in ctx.index.candidates}

    for record in ctx.index.ledger_records:
        for candidate_id in record.candidate_ids:
            if candidate_id in candidate_ids:
                continue
            yield diagnostic(
                IssueCode.BROKEN_REFERENCE,
                f"{record.source_record_id}.candidate_ids names {candidate_id}, which "
                "imports/candidates.yaml does not define",
                path="imports/source-ledger.yaml",
                record_id=record.source_record_id,
                field="candidate_ids",
                target=candidate_id,
            )
    for candidate in ctx.index.candidates:
        if candidate.source_record_id in ledger_ids:
            continue
        yield diagnostic(
            IssueCode.BROKEN_REFERENCE,
            f"{candidate.candidate_id}.source_record_id names {candidate.source_record_id}, "
            "which imports/source-ledger.yaml does not define",
            path="imports/candidates.yaml",
            record_id=candidate.candidate_id,
            field="source_record_id",
            target=candidate.source_record_id,
        )
    for exclusion in ctx.index.exclusions:
        if exclusion.source_record_id in ledger_ids:
            continue
        yield diagnostic(
            IssueCode.BROKEN_REFERENCE,
            f"imports/exclusions.yaml excludes {exclusion.source_record_id}, which "
            "imports/source-ledger.yaml does not define",
            path="imports/exclusions.yaml",
            record_id=exclusion.source_record_id,
            field="source_record_id",
            target=exclusion.source_record_id,
        )


# --------------------------------------------------------------------------------------
# Graph consistency
# --------------------------------------------------------------------------------------


def _evidence_links_are_symmetric(ctx: ValidationContext) -> Iterator[Diagnostic]:
    """`fact.evidence_ids` and the evidence's own link sets must agree exactly (§12).

    The comparison is against the UNION of `supports`, `contradicts`, and `contextualizes`, not
    against `supports` alone. §12 makes the relationship a closed choice of three, and a secondary
    summary that only *contextualizes* a fact is a legitimate attachment — the design says in the
    same breath that "a contextual source cannot satisfy a verification requirement", which is a
    semantic question about whether the fact is verified, not a referential one about whether the
    two records point at each other. Requiring `supports` here would have forced every contextual
    attachment to overstate itself.

    Read from the evidence side; the index built the record side. One direction alone would let a
    fact cite evidence that names something else entirely.
    """
    linked: dict[str, set[str]] = {}
    relationship: dict[tuple[str, str], str] = {}
    for record in ctx.index.evidence:
        evidence_id = record.evidence_id
        for name, targets in (
            ("supports", record.supports_record_ids),
            ("contradicts", record.contradicts_record_ids),
            ("contextualizes", record.contextualizes_record_ids),
        ):
            for target in targets:
                linked.setdefault(target, set()).add(evidence_id)
                relationship[(evidence_id, target)] = name

    for record_id, cited in sorted(ctx.index.evidence_links.items()):
        naming = linked.get(record_id, set())
        for evidence_id in sorted(set(cited) - naming):
            if ctx.index.get(evidence_id) is None:
                continue  # already reported as a broken reference
            yield diagnostic(
                IssueCode.EVIDENCE_LINK_ASYMMETRY,
                f"{record_id} cites {evidence_id}, which names it in none of supports, "
                "contradicts, or contextualizes",
                path=ctx.index.path_of(record_id),
                record_id=record_id,
                evidence_id=evidence_id,
                direction="record_to_evidence",
            )
        for evidence_id in sorted(naming - set(cited)):
            yield diagnostic(
                IssueCode.EVIDENCE_LINK_ASYMMETRY,
                f"{evidence_id} {relationship[(evidence_id, record_id)]} {record_id}, which does "
                "not cite it",
                path="evidence/records.yaml",
                record_id=evidence_id,
                supported_record_id=record_id,
                relationship=relationship[(evidence_id, record_id)],
                direction="evidence_to_record",
            )

    # Only facts and metrics carry `evidence_ids`, so only they can cite back. Evidence naming a
    # skill or a claim is a legitimate one-way link (§12), and evidence naming any other kind is a
    # WRONG kind — reported as one, not doubly reported as an asymmetry about the same edit.
    for record_id, naming in sorted(linked.items()):
        if record_id in ctx.index.evidence_links:
            continue
        if prefix_of(record_id) not in ("fact", "metric"):
            continue
        if ctx.index.get(record_id) is None:
            continue  # already reported as a broken reference
        for evidence_id in sorted(naming):
            yield diagnostic(
                IssueCode.EVIDENCE_LINK_ASYMMETRY,
                f"{evidence_id} {relationship[(evidence_id, record_id)]} {record_id}, which cites "
                "no evidence",
                path="evidence/records.yaml",
                record_id=evidence_id,
                supported_record_id=record_id,
                relationship=relationship[(evidence_id, record_id)],
                direction="evidence_to_record",
            )


def _supersession_graph_is_acyclic(ctx: ValidationContext) -> Iterator[Diagnostic]:
    """No fact may supersede itself transitively.

    A cycle makes "the current value" undefined: every fact in it is superseded, so a reader looking
    for the surviving value finds none, and the predicate silently loses its answer.
    """
    edges: Mapping[str, tuple[str, ...]] = {
        fact.fact_id: fact.supersedes_fact_ids for fact in ctx.index.facts
    }
    #: 0 = unvisited, 1 = on the current path, 2 = finished.
    state: dict[str, int] = {}
    reported: set[str] = set()

    def walk(node: str, trail: tuple[str, ...]) -> Iterator[Diagnostic]:
        state[node] = 1
        for target in edges.get(node, ()):
            if target not in edges:
                continue  # a dangling edge is a broken reference, reported elsewhere
            if state.get(target, 0) == 1:
                cycle = trail[trail.index(target) :] if target in trail else (target,)
                key = min(cycle)
                if key not in reported:
                    reported.add(key)
                    yield diagnostic(
                        IssueCode.SUPERSESSION_CYCLE,
                        "supersession cycle: " + " -> ".join((*cycle, target)),
                        path=ctx.index.path_of(target),
                        record_id=key,
                        cycle=list(cycle),
                    )
                continue
            if state.get(target, 0) == 0:
                yield from walk(target, (*trail, target))
        state[node] = 2

    for fact_id in sorted(edges):
        if state.get(fact_id, 0) == 0:
            yield from walk(fact_id, (fact_id,))


def _conflict_candidates_agree_with_their_group(ctx: ValidationContext) -> Iterator[Diagnostic]:
    """Every candidate fact must share the group's subject and predicate, and point back at it.

    §13's group is "competing answers to one question". A candidate about another predicate is not a
    competing answer, and a ruling picking it would resolve a question nobody asked.
    """
    for conflict in ctx.index.conflicts:
        for fact_id in conflict.candidate_fact_ids:
            fact = ctx.index.fact(fact_id)
            if fact is None:
                continue  # broken reference, reported elsewhere
            if fact.subject_id != conflict.subject_id or fact.predicate != conflict.predicate:
                yield diagnostic(
                    IssueCode.CONFLICT_CANDIDATE_MISMATCH,
                    f"{fact_id} is a candidate of {conflict.conflict_id} but describes "
                    f"{fact.subject_id}/{fact.predicate}, not "
                    f"{conflict.subject_id}/{conflict.predicate}",
                    path=ctx.index.path_of(fact_id),
                    record_id=fact_id,
                    conflict_id=conflict.conflict_id,
                )
            if fact.conflict_group_id != conflict.conflict_id:
                yield diagnostic(
                    IssueCode.CONFLICT_CANDIDATE_MISMATCH,
                    f"{fact_id} is a candidate of {conflict.conflict_id} but its "
                    f"conflict_group_id is {fact.conflict_group_id!r}",
                    path=ctx.index.path_of(fact_id),
                    record_id=fact_id,
                    conflict_id=conflict.conflict_id,
                )
        # And the reverse: a fact naming a group that does not list it.
    for fact in ctx.index.facts:
        if fact.conflict_group_id is None:
            continue
        group = ctx.index.conflict(fact.conflict_group_id)
        if group is None or fact.fact_id in group.candidate_fact_ids:
            continue
        yield diagnostic(
            IssueCode.CONFLICT_CANDIDATE_MISMATCH,
            f"{fact.fact_id} names conflict {fact.conflict_group_id}, which does not list it as a "
            "candidate",
            path=ctx.index.path_of(fact.fact_id),
            record_id=fact.fact_id,
            conflict_id=fact.conflict_group_id,
        )


def _active_rulings_belong_to_their_conflict(ctx: ValidationContext) -> Iterator[Diagnostic]:
    """An active ruling must be a ruling ON that conflict, and may only decide that group's facts.

    Two neighbouring conditions are deliberately NOT re-checked here, because a model validator
    already refuses them at parse time and a second copy would drift from the first:

    - a resolved group with no active ruling (`ConflictRecord._resolved_groups_name_their_ruling`);
    - a decision whose selection does not match it (`RulingRecord._selection_matches_the_decision`).

    What only the assembled tree can see is whether the ruling and the group agree about each other,
    which is what stays.
    """
    rulings = {ruling.ruling_id: ruling for ruling in ctx.index.rulings}
    for conflict in ctx.index.conflicts:
        active = conflict.active_ruling_id
        if active is None:
            continue
        ruling = rulings.get(active)
        if ruling is not None and ruling.conflict_id != conflict.conflict_id:
            yield diagnostic(
                IssueCode.ACTIVE_RULING_MISMATCH,
                f"{conflict.conflict_id} names active ruling {active}, which rules on "
                f"{ruling.conflict_id}",
                path="conflicts/groups.yaml",
                record_id=conflict.conflict_id,
                ruling_id=active,
            )

    # A ruling may only decide between the facts its own group is disputing. Ruling on a fact from
    # another group would let one owner decision silently settle a question it never considered.
    for ruling in ctx.index.rulings:
        ruled_group = ctx.index.conflict(ruling.conflict_id)
        if ruled_group is None:
            continue  # broken reference, reported elsewhere
        decided = (
            *((ruling.selected_fact_id,) if ruling.selected_fact_id is not None else ()),
            *ruling.rejected_fact_ids,
        )
        for fact_id in decided:
            if fact_id in ruled_group.candidate_fact_ids:
                continue
            yield diagnostic(
                IssueCode.ACTIVE_RULING_MISMATCH,
                f"{ruling.ruling_id} rules on {fact_id}, which is not a candidate of "
                f"{ruled_group.conflict_id}",
                path="conflicts/rulings.yaml",
                record_id=ruling.ruling_id,
                conflict_id=ruled_group.conflict_id,
                target=fact_id,
            )


def _relation_endpoints_match_the_catalog(ctx: ValidationContext) -> Iterator[Diagnostic]:
    """A relation's endpoints must be entity kinds its catalog row permits (§9).

    Without the catalog present nothing is checked here — the missing file is the finding, and
    inventing a permissive default would let a typed relation be authored against any two entities.
    """
    catalog = ctx.index.relation_catalog
    if catalog is None:
        return
    by_type = catalog.by_type
    for relation in ctx.index.relations:
        spec = by_type.get(relation.relation_type)
        if spec is None:
            yield diagnostic(
                IssueCode.RELATION_KIND_MISMATCH,
                f"{relation.relation_id} uses relation type {relation.relation_type!r}, which "
                "policy/relations.yaml does not define",
                path="relations/records.yaml",
                record_id=relation.relation_id,
                relation_type=relation.relation_type,
            )
            continue
        for field, endpoint, legal in (
            ("source_id", relation.source_id, spec.legal_source_kinds),
            ("target_id", relation.target_id, spec.legal_target_kinds),
        ):
            kind = _entity_kind_or_none(endpoint)
            if kind is None or kind in legal:
                continue
            yield diagnostic(
                IssueCode.RELATION_KIND_MISMATCH,
                f"{relation.relation_id}.{field} is a {kind} entity; {relation.relation_type} "
                f"permits {', '.join(sorted(str(k) for k in legal))}",
                path="relations/records.yaml",
                record_id=relation.relation_id,
                field=field,
                relation_type=relation.relation_type,
                found_kind=str(kind),
            )


def _entity_kind_or_none(entity_id: str) -> EntityKind | None:
    """`None` for an ID that names no entity kind — that is a reference finding, not a kind one."""
    try:
        return entity_kind_of(entity_id)
    except ValueError:
        return None


def records_blocked_by_unresolved_conflicts(index: BundleIndex) -> frozenset[str]:
    """Fact IDs blocked because their group is not resolved.

    Exposed here because the locality property is the point: this returns ONLY the candidates of
    unresolved groups, so an unrelated fact about the same subject stays usable. A conflict that
    blocked its whole subject would make one disputed job title suppress a whole employment.
    """
    unresolved = index.unresolved_conflict_ids
    return frozenset(
        fact_id
        for conflict in index.conflicts
        if conflict.conflict_id in unresolved
        for fact_id in conflict.candidate_fact_ids
    )

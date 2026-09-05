"""Grouping, then roll-up, then the ledger write.

ENGINE_VERSION is DERIVED, not maintained (D-P2-22). Deterministic runs dedupe on
(input_id, engine_version), so an unbumped semantic change returns the old verdict forever,
and a manual bump discipline is unenforceable by construction. The digest is over ast.dump
rather than raw bytes so comments and formatting do not re-key the corpus, and
include_attributes=False keeps line numbers out of it.

The roll-up reproduces .agent/p2-catalog/proto.py::evaluate (the reviewed prototype and the
ORACLE this module was reconciled against) stage for stage: a per-detection abstain when the
detection carries an `abstained` escape, then stage 1 exclusive-group conflict, then refinement
group disagreement, then stage 1b split-threshold abstain, then the stage 2 policy roll-up. The
prototype's abstain and stage 1b were both absent from the frozen task-7 brief; where brief and
prototype disagreed, the prototype won (the brief's own Step rule), verified case by case against
proto.evaluate.
"""

from __future__ import annotations

import ast
import hashlib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from sqlalchemy import Connection, select

from boardwatch.eligibility.catalog import FamilySpec, RulesCatalog
from boardwatch.eligibility.detect import Detection, detect, jd_locator
from boardwatch.eligibility.facts import Facts, Policy
from boardwatch.eligibility.hashing import InputIdentity, verify_identity
from boardwatch.eligibility.resolve import MET, UNKNOWN, UNMET, resolve
from boardwatch.store.eligibility import RequirementItem, SupportItem, record_evaluation
from boardwatch.store.tables import eligibility_evaluations, eligibility_inputs

ENGINE_SEMANTIC = 1
ENGINE_KIND = "deterministic"


def digested_modules() -> tuple[str, ...]:
    """Every module whose edit can change a verdict or its evidence.

    A FUNCTION, not a module constant: R9 has no allowlist and a non-empty string tuple at a
    declaration position in a scoped module is a violation. Function bodies are invisible to
    the gate's `_declarations` walk by design, so this is the sanctioned shape rather than a
    dodge.

    Filenames rather than imported module objects, so the digest reads source from disk and
    fails loudly on a missing file instead of silently covering less than it claims.

    `catalog.py` IS covered, and that is load-bearing: `catalog.version` hashes the parsed
    YAML document, not the loader. Dropping `re.IGNORECASE` from `_pattern`'s `re.compile`,
    or ceasing to compile `suppressed_by`, changes every verdict in the corpus while
    `rules_hash`, `profile_hash`, `input_fingerprint` and a detect/resolve/engine-only digest
    all stay byte-identical. The deterministic anti-join would then return the old verdict
    forever, which is the exact failure D-P2-22 exists to prevent.
    """
    return ("catalog.py", "detect.py", "resolve.py", "engine.py")


def source_of(filename: str) -> str:
    path = Path(__file__).with_name(filename)
    if not path.is_file():
        raise FileNotFoundError(
            f"{filename} is part of ENGINE_VERSION but is not readable, so the version "
            "would silently cover less than it claims"
        )
    return path.read_text(encoding="utf-8")


def canonical_dump(node: ast.AST | list[object] | object) -> str:
    """Serialise an AST to a string that is stable across Python versions.

    `ast.dump` is NOT usable here, because its output is interpreter-dependent and the digest
    built from it keys the eligibility ledger. Python 3.13 changed `ast.dump` to omit fields
    holding their default, so 3.12 writes `args=[], keywords=[], type_params=[]` where 3.13
    writes nothing; and `type_params` did not exist before 3.12. Over the four digested
    modules that produced three different digests for byte-identical source — `6f9feb84bfee`
    on 3.11, `a1d0be72a338` on 3.12, `7e88ed2b193d` on 3.13 — so every posting's verdict
    re-keyed on a Python upgrade, and the three CI interpreters each computed a different
    engine version.

    Walking `_fields` directly makes those defaults irrelevant. Empty lists are skipped, which
    is what absorbs a grammar field added by a later version but unused by this code
    (`type_params` is the live example). `None` is KEPT rather than skipped, so `Constant(None)`
    — the literal `None` — stays distinguishable from a node with an absent optional.

    Comments and formatting stay invisible, which is the property D-P2-22 wanted from `ast.dump`
    in the first place: parsing discards them, so only a semantic edit re-keys the corpus.
    """
    if isinstance(node, ast.AST):
        fields = []
        for name in node._fields:
            value = getattr(node, name, None)
            if isinstance(value, list) and not value:
                continue
            fields.append(f"{name}={canonical_dump(value)}")
        return f"{type(node).__name__}({','.join(fields)})"
    if isinstance(node, list):
        return "[" + ",".join(canonical_dump(item) for item in node) + "]"
    return repr(node)


def digest_of_sources(sources: list[str]) -> str:
    """SHA-256 over the canonical AST dumps, length-prefixed.

    Raises SyntaxError on unparseable source rather than skipping it: a version computed
    over a subset is a stale-verdict machine. Length prefixes rather than a separator join,
    so no two different module lists can produce the same byte stream.
    """
    running = hashlib.sha256()
    for source in sources:
        encoded = canonical_dump(ast.parse(source)).encode("utf-8")
        running.update(str(len(encoded)).encode("utf-8"))
        running.update(b":")
        running.update(encoded)
    return running.hexdigest()


@lru_cache(maxsize=1)
def engine_version() -> str:
    return (
        f"{ENGINE_SEMANTIC}+"
        f"{digest_of_sources([source_of(m) for m in digested_modules()])[:12]}"
    )


@dataclass(frozen=True)
class EvaluationResult:
    verdict: str
    requirements: tuple[RequirementItem, ...]


@dataclass(frozen=True)
class _Staged:
    """One detection carried through the grouping stages with its live disposition."""

    detection: Detection
    disposition: str
    rationale: str
    support: tuple[SupportItem, ...]


def field_applicability(family: FamilySpec, career_field: str | None, catalog: RulesCatalog) -> str:
    """How a family relates to the profile's career field.

    "active"  — not a field-tier family, or the field is in scope: evaluate normally.
    "skip"    — field-tier, career_field is a VALID field this family does not apply to: the
                family is genuinely irrelevant (verdict-equivalent to the user's own `ignore`).
    "abstain" — field-tier and career_field is MISSING or NOT a catalog value: unresolvable, so
                the keystone requires ABSTAIN, never a silent clear.
    """
    if family.tier != "field":
        return "active"
    if career_field in family.applies_to:
        return "active"
    if career_field in catalog.career_fields:
        return "skip"
    return "abstain"


def not_applicable_field_families(facts: Facts, catalog: RulesCatalog) -> frozenset[str]:
    """Field-tier families that a report must show as `not_applicable` rather than
    `never_fired` for THIS profile — i.e. those whose career_field applicability is `skip`."""
    return frozenset(
        family.id
        for family in catalog.families
        if field_applicability(family, facts.career_field, catalog) == "skip"
    )


def _no_evaluable_requirement(
    body_text: str, catalog: RulesCatalog, enabled: frozenset[str]
) -> bool:
    """True when the posting carried NO requirement any family could evaluate.

    Consulted only in the zero-row branch of the roll-up. `eligible` there would be a
    clear-BY-SILENCE — the "No flags != cleared" keystone violation: the body matched no
    pattern in any ENABLED family, so nothing was cleared and the evidence chain is empty.
    A family the profile's own policy (`ignore`) or field scope (`skip`) left OUT is a
    different case entirely — a requirement WAS present and the user deliberately opted out
    of it, which legitimately stays `eligible`. So the posting is un-evaluable (must abstain)
    only when no EXCLUDED family would have detected a requirement either. For a default or
    all-`blocker` profile nothing is excluded, so this short-circuits without re-detecting.
    """
    excluded = frozenset(family.id for family in catalog.families) - enabled
    if not excluded:
        return True
    return not detect(body_text, catalog, enabled_families=excluded)


def evaluate(
    body_text: str, facts: Facts, policy: Policy, catalog: RulesCatalog
) -> EvaluationResult:
    severity = catalog.materialised_policy(policy)
    applicability = {
        family_id: field_applicability(catalog.family(family_id), facts.career_field, catalog)
        for family_id in severity
    }
    enabled = frozenset(
        family_id
        for family_id, choice in severity.items()
        if choice != "ignore" and applicability[family_id] != "skip"
    )
    # Field-tier families whose career_field is missing/unresolvable stay enabled so they
    # DETECT, then every detection abstains (keystone) — never silently cleared.
    field_abstain = frozenset(fid for fid in enabled if applicability[fid] == "abstain")
    detections = detect(body_text, catalog, enabled_families=enabled)

    # ---- per detection: an abstain escape ELSEWHERE in the posting may waive it, so the row
    # is undecidable rather than resolved. Abstain rather than drop: dropping returns
    # `eligible` by silence, the worse direction (proto.evaluate, detect.abstained).
    staged: list[_Staged] = []
    for detection in detections:
        if detection.family in field_abstain:
            staged.append(
                _Staged(detection, UNKNOWN, "missing_profile_field:career_field", ())
            )
        elif detection.abstained is not None:
            staged.append(
                _Staged(
                    detection,
                    UNKNOWN,
                    f"the posting may waive this: {detection.abstained}",
                    (),
                )
            )
        else:
            resolution = resolve(
                detection, facts, catalog.effective_family(detection.family, policy)
            )
            staged.append(
                _Staged(
                    detection, resolution.disposition, resolution.rationale, resolution.support
                )
            )

    # ---- stage 1: grouping, per group, independently, with exact set semantics. A group
    # conflicts when two or more DISTINCT implies values of THAT group are present. Two
    # detections of the SAME implies value are corroboration, not conflict.
    present: dict[str, set[str]] = {}
    for item in staged:
        present.setdefault(item.detection.family, set()).add(item.detection.pattern.implies)
    # (family, implies) PAIRS, never bare implies strings. `implies` is only unique WITHIN a
    # family: the vocabulary is declared per family, so nothing stops a user-supplied
    # override from reusing a name across two of them, and a bare-string set would then let
    # a conflict inside family X silently rewrite every row in family Y to `unknown`. This
    # matches .agent/p2-catalog/proto.py, where the same fix landed as slice A item A5.
    conflicted: set[tuple[str, str]] = set()
    for family in catalog.families:
        seen = present.get(family.id, set())
        for group in family.exclusive_groups:
            overlap = seen & group
            if len(overlap) >= 2:
                # only THIS group's values in THIS family, never another group's or
                # another family's
                conflicted |= {(family.id, value) for value in overlap}
    staged = [
        _Staged(
            item.detection,
            UNKNOWN,
            "conflicting statements about this requirement appear in the posting",
            (),
        )
        if (item.detection.family, item.detection.pattern.implies) in conflicted
        else item
        for item in staged
    ]

    # ---- refinement groups: parallel requirements can co-occur. They abstain only when the
    # candidate clears one member while missing another; agreement is evidence for the roll-up.
    # Like stage 1b below, the disagreement is keyed on a SET of dispositions, never row order.
    # Named apart from stage 1b's `by_key` below rather than shared: stage 1b must recompute
    # AFTER this pass, because a row this pass rewrites to `unknown` is no longer a `met` or an
    # `unmet` for its split test. Sharing one snapshot would let a dissolved row keep voting.
    refinement_dispositions: dict[tuple[str, str], set[str]] = {}
    for item in staged:
        refinement_dispositions.setdefault(
            (item.detection.family, item.detection.pattern.implies), set()
        ).add(item.disposition)
    refinement_conflicted: set[tuple[str, str]] = set()
    for family in catalog.families:
        for group in family.refinement_groups:
            overlap = {
                value for value in group if (family.id, value) in refinement_dispositions
            }
            # TWO DISTINCT members or it is not a straddle. Without this, ONE member carrying
            # two disagreeing detections satisfies the met/unmet test below and is dissolved
            # here, which preempts stage 1b and mislabels it: "8+ years of experience required.
            # 3+ years of experience required." is two thresholds for ONE requirement, not two
            # parallel requirements, and its rows must carry stage 1b's rationale. The
            # disposition is `unknown` either way, so only the EVIDENCE CHAIN distinguishes
            # them — which is exactly what the keystone invariant makes load-bearing.
            if len(overlap) < 2:
                continue
            seen = {
                disposition
                for value in overlap
                for disposition in refinement_dispositions[(family.id, value)]
            }
            if MET in seen and UNMET in seen:
                refinement_conflicted |= {(family.id, value) for value in overlap}
    if refinement_conflicted:
        staged = [
            _Staged(
                item.detection,
                UNKNOWN,
                "the posting's parallel requirements straddle the candidate's profile",
                (),
            )
            if (item.detection.family, item.detection.pattern.implies) in refinement_conflicted
            else item
            for item in staged
        ]

    # ---- stage 1b: two rows for the SAME (family, implies) that DISAGREE cannot both be
    # right, and "any unmet wins" in the roll-up would silently pick the harsher threshold.
    # "Senior applicants need 8 years. Exceptional applicants may qualify with 3 years." told a
    # 4-year candidate `ineligible`. The cluster abstains instead: order-independent (keyed on
    # the SET of dispositions), and the safe direction. Rows that AGREE keep their disposition.
    by_key: dict[tuple[str, str], set[str]] = {}
    for item in staged:
        by_key.setdefault(
            (item.detection.family, item.detection.pattern.implies), set()
        ).add(item.disposition)
    split = {key for key, seen in by_key.items() if MET in seen and UNMET in seen}
    if split:
        staged = [
            _Staged(
                item.detection,
                UNKNOWN,
                "the posting states more than one threshold for this requirement",
                (),
            )
            if (item.detection.family, item.detection.pattern.implies) in split
            else item
            for item in staged
        ]

    requirements: list[RequirementItem] = []
    rows: list[tuple[str, str, str]] = []
    for item in staged:
        detection = item.detection
        # Substitute captured values BEFORE the row is written. The four eligibility tables
        # carry BEFORE UPDATE/DELETE RAISE(ABORT) triggers, so a row storing a literal
        # "{years}" is permanently uncorrectable: it can only ever be superseded.
        requirement_text = detection.pattern.requirement_text
        if detection.values:
            try:
                requirement_text = requirement_text.format(**detection.values)
            except (KeyError, IndexError):
                pass  # a catalog override may carry a placeholder its pattern never captures
        requirements.append(
            RequirementItem(
                requiredness=detection.pattern.requiredness,  # type: ignore[arg-type]
                requirement_text=requirement_text,
                jd_locator=jd_locator(detection),
                disposition=item.disposition,  # type: ignore[arg-type]
                rule_id=detection.pattern.rule_id,
                rationale=item.rationale,
                support=item.support,
            )
        )
        rows.append((detection.family, detection.pattern.requiredness, item.disposition))

    # ---- stage 2: roll-up over requirement ROWS, not over families. A family can produce
    # several detections at different requiredness levels, and collapsing a family to one
    # disposition loses that. These are order-INDEPENDENT any() tests, not a fold.
    def blocking(disposition: str) -> bool:
        return any(
            severity[family] == "blocker" and requiredness == "required" and found == disposition
            for family, requiredness, found in rows
        )

    if blocking(UNMET):
        verdict = "ineligible"
    elif blocking(UNKNOWN):
        verdict = "uncertain"
    elif not rows and _no_evaluable_requirement(body_text, catalog, enabled):
        # Zero requirement rows AND no family — enabled or user-excluded — could have found
        # a requirement in this body. `eligible` here is a clear by silence with an empty
        # evidence chain, which the keystone forbids ("No flags" != cleared). Abstain.
        verdict = "uncertain"
    else:
        verdict = "eligible"
    return EvaluationResult(verdict=verdict, requirements=tuple(requirements))


def write_evaluation(
    conn: Connection,
    *,
    posting_version_id: int,
    identity: InputIdentity,
    result: EvaluationResult,
    run_id: int | None = None,
) -> int:
    """Persist one deterministic evaluation, idempotently.

    verify_identity runs FIRST. The four tables carry BEFORE UPDATE/DELETE RAISE(ABORT)
    triggers, so a bad row can only ever be superseded, never corrected.

    `run_id` attributes the row to the pipeline run that judged it. It is optional here only
    because this is a store-level primitive; callers in `src/` always supply one, so a NULL
    reaching the column means the row predates run attribution.
    """
    verify_identity(identity, posting_version_id=posting_version_id)
    return record_evaluation(
        conn,
        posting_version_id=posting_version_id,
        profile_hash=identity.profile_hash,
        profile_snapshot=identity.profile_snapshot,
        rules_hash=identity.rules_hash,
        rules_snapshot=identity.rules_snapshot,
        input_fingerprint=identity.input_fingerprint,
        engine_kind=ENGINE_KIND,  # type: ignore[arg-type]
        engine_version=engine_version(),
        verdict=result.verdict,  # type: ignore[arg-type]
        score=None,  # D-P2-6: D17 forbids persisted scores
        requirements=result.requirements,
        run_id=run_id,
    )


def current_evaluations(
    conn: Connection,
    posting_version_ids: list[int],
    profile_hash: str,
    rules_hash: str,
) -> dict[int, tuple[int, str]]:
    """posting_version_id -> (evaluation id, verdict) for the CURRENT input identity.

    Scoped to the current engine version AND the caller's (profile_hash, rules_hash), so a
    corrected fact or policy selects the evaluation it produced rather than any leftover row
    at the same engine version. The (posting_version, profile_hash, rules_hash) triple is the
    unique input fingerprint, and (input, engine_version) is unique per deterministic run, so
    at most one row survives per posting version and the read needs no tie-break.

    get_evaluations returns EVERY evaluation ordered by id with no selector, so P2 adds its
    own rather than reusing it blindly (spec §4.7).
    """
    if not posting_version_ids:
        return {}
    stmt = (
        select(
            eligibility_inputs.c.posting_version_id,
            eligibility_evaluations.c.id,
            eligibility_evaluations.c.verdict,
        )
        .join(
            eligibility_inputs,
            eligibility_evaluations.c.input_id == eligibility_inputs.c.id,
        )
        .where(
            eligibility_inputs.c.posting_version_id.in_(posting_version_ids),
            eligibility_inputs.c.profile_hash == profile_hash,
            eligibility_inputs.c.rules_hash == rules_hash,
            eligibility_evaluations.c.engine_kind == ENGINE_KIND,
            eligibility_evaluations.c.engine_version == engine_version(),
        )
    )
    return {
        int(row.posting_version_id): (int(row.id), str(row.verdict))
        for row in conn.execute(stmt).all()
    }

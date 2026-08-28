"""ENGINE_VERSION is DERIVED, grouping is exact set semantics, and roll-up is a set of
order-independent any() tests over requirement ROWS."""

import ast
from pathlib import Path

import pytest
import yaml
from sqlalchemy import insert, select

from boardwatch.core.clock import utcnow
from boardwatch.eligibility.catalog import bundled_rules_text, load_rules
from boardwatch.eligibility.engine import (
    ENGINE_KIND,
    ENGINE_SEMANTIC,
    engine_version,
    evaluate,
    field_applicability,
    write_evaluation,
)
from boardwatch.eligibility.facts import Facts, Policy, WorkAuthFact
from boardwatch.eligibility.hashing import build_identity
from boardwatch.eligibility.resolve import declared_fields
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.eligibility import get_evaluations, get_requirements, get_support
from boardwatch.store.tables import (
    companies,
    eligibility_evaluations,
    eligibility_inputs,
    jobs,
    posting_versions,
    postings,
)

BLOCK_ALL = Policy(families={
    "work_auth": "blocker", "experience_years": "blocker",
    "clearance": "blocker", "degree": "blocker",
})


def _field_catalog(config_dir, *, assign):  # assign: {family_id: [career_field, ...]}
    """Bundled catalog with `assign`ed families reclassified to tier:field, drift-safe."""
    doc = yaml.safe_load(bundled_rules_text())
    doc["career_fields"] = ["software", "data", "design"]
    for fam in doc["families"]:
        if fam["id"] in assign:
            fam["tier"] = "field"
            fam["applies_to"] = assign[fam["id"]]
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "rules.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")
    return load_rules(config_dir)


# A fully-controlled single field-tier family whose pattern matches the string "bachelor".
_CONTROLLED = """
version: 1
negation_cues: ["not"]
career_fields: [software, data]
families:
  - id: degree
    label: Degree
    fact: highest_degree
    tier: field
    applies_to: [software]
    answer_type: choice
    default_policy: preference
    question: "Highest degree?"
    fields:
      - name: highest_degree
        type: choice
        choices: [none, bachelor]
        ranks: {none: 0, bachelor: 3}
    implies_vocabulary: [degree_required]
    exclusive_groups: []
    patterns:
      - id: bachelor_required
        requiredness: required
        implies: degree_required
        scope: sentence
        required_rank: 3
        requirement_text: "A bachelor's degree is required"
        pattern: "bachelor"
        abstain_by: ["unless otherwise noted"]
"""


def _controlled_catalog(config_dir):
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "rules.yaml").write_text(_CONTROLLED, encoding="utf-8")
    return load_rules(config_dir)


@pytest.fixture()
def catalog(tmp_path: Path):
    return load_rules(tmp_path / "no-override")


@pytest.fixture()
def db(tmp_path: Path):
    engine = get_engine(tmp_path / "data")
    ensure_schema(engine)
    return engine


@pytest.fixture()
def version_id(db) -> int:
    now = utcnow()
    with db.begin() as conn:
        cid = int(conn.execute(insert(companies).values(
            name="Acme", provider="greenhouse", slug="acme", source="user", watched=True,
        )).inserted_primary_key[0])
        jid = int(conn.execute(insert(jobs).values(created_at=now)).inserted_primary_key[0])
        pid = int(conn.execute(insert(postings).values(
            company_id=cid, job_id=jid, provider_posting_id="p-1", title="Eng",
            normalized_title="eng", first_seen_at=now, last_seen_at=now, status="open",
            consecutive_missing=0, content_hash="h1", body_text="Bachelor's degree required.",
        )).inserted_primary_key[0])
        return int(conn.execute(insert(posting_versions).values(
            posting_id=pid, content_hash="h1", body_text="Bachelor's degree required.",
            captured_at=now, run_id=None, capture_reason="new",
        )).inserted_primary_key[0])


# ---------------------------------------------------------------- derived version

def test_an_activity_row_elsewhere_does_not_dissolve_a_total_years_block(catalog) -> None:
    """The exclusive group is collected DOCUMENT-wide, not per sentence.

    `rules.yaml` describes the group as firing "if the total, range and scoped patterns ever
    overlap on the same text", but `evaluate` builds `present` from every detection in the body,
    so two rows in unrelated sentences are enough to conflict and rewrite BOTH to unknown. That
    is why `scoped_years_activity` carries its own `activity_years_minimum` value instead of
    reusing `scoped_years_minimum`.

    Taken from a Disney "Software Engineer I" posting where adding an activity pattern that shared
    the scoped value turned a correct `ineligible` into `uncertain` -- delivered. The floor here is
    set BEYOND the experience soft margin (5 vs a 1-year profile) on purpose: it isolates the
    exclusive-group behavior from the margin's own abstain, so a dissolved block can only be the
    group bug, not a small-shortfall surface.
    """
    body = (
        "A minimum of 5 years of relevant experience.\n"
        "A minimum of 5 year of developing cloud native applications, preferably in AWS.\n"
    )
    facts = Facts(total_years_experience=1)
    policy = Policy(families={"experience_years": "blocker"})
    result = evaluate(body, facts, policy, catalog)
    kinds = {(r.rule_id, r.disposition) for r in result.requirements}
    assert result.verdict == "ineligible", f"the total floor was dissolved: {kinds}"
    assert ("experience_years:total_years_minimum", "unmet") in kinds


def test_the_engine_version_is_stable_across_runs() -> None:
    assert engine_version() == engine_version()
    assert engine_version().startswith(f"{ENGINE_SEMANTIC}+")
    assert len(engine_version().split("+", 1)[1]) == 12


def test_the_version_changes_when_any_covered_module_changes() -> None:
    """Asserts the PROPERTY, not the constant. The previous form compared a tuple to a
    literal copy of itself, which passes against `digest_of_sources = lambda s: ""` and
    establishes nothing. This version fails if any module is dropped from the tuple."""
    from boardwatch.eligibility import engine

    base = [engine.source_of(m) for m in engine.digested_modules()]
    baseline = engine.digest_of_sources(base)
    for index in range(len(base)):
        mutated = list(base)
        mutated[index] = mutated[index] + "\n_AUDIT_PROBE = 1\n"
        assert engine.digest_of_sources(mutated) != baseline, engine.digested_modules()[index]
    assert "catalog.py" in engine.digested_modules()  # the loader can change every verdict


def test_a_comment_only_edit_does_not_change_the_digest(tmp_path: Path) -> None:
    """The digest is over a parsed AST, not raw bytes, or every comment edit re-evaluates
    the whole corpus."""
    from boardwatch.eligibility.engine import digest_of_sources

    original = Path("src/boardwatch/eligibility/detect.py").read_text(encoding="utf-8")
    commented = original + "\n# a trailing comment that changes nothing\n"
    assert digest_of_sources([original]) == digest_of_sources([commented])


def test_a_logic_edit_changes_the_digest() -> None:
    from boardwatch.eligibility.engine import digest_of_sources

    assert digest_of_sources(["x = 1"]) != digest_of_sources(["x = 2"])


def test_formatting_does_not_change_the_digest() -> None:
    from boardwatch.eligibility.engine import digest_of_sources

    assert digest_of_sources(["def f():\n    return 1\n"]) == digest_of_sources(
        ["def f():\n\n\n    return 1\n"]
    )


def test_the_digest_refuses_a_missing_module(tmp_path: Path) -> None:
    """A version that silently fails to cover a module is worse than a crash: it pins a
    stale verdict forever."""
    from boardwatch.eligibility.engine import source_of

    with pytest.raises(FileNotFoundError):
        source_of("no_such_module.py")


def test_the_canonical_dump_omits_empty_list_fields() -> None:
    """The mechanism that makes the digest interpreter-independent.

    `ast.dump` is version-dependent: 3.13 omits fields holding their default where 3.12 writes
    `args=[], keywords=[], type_params=[]`, and `type_params` did not exist before 3.12. Over
    the four digested modules that produced a DIFFERENT digest on each of 3.11 / 3.12 / 3.13
    for byte-identical source, so a Python upgrade silently re-keyed every posting's verdict.
    Skipping empty lists is what absorbs a grammar field a later version adds but this code
    does not use.
    """
    from boardwatch.eligibility.engine import canonical_dump

    dumped = canonical_dump(ast.parse("x = 1\n"))
    assert "=[]" not in dumped
    assert "type_params" not in dumped


def test_an_empty_grammar_field_does_not_change_the_dump() -> None:
    """Directly encodes the forward-compatibility claim: a node carrying an extra field that
    is an empty list must serialise identically to one without the field at all."""
    from boardwatch.eligibility.engine import canonical_dump

    node = ast.parse("def f():\n    return 1\n")
    without = canonical_dump(node)
    function = node.body[0]
    function._fields = (*function._fields, "_probe_future_field")
    function._probe_future_field = []  # type: ignore[attr-defined]
    assert canonical_dump(node) == without


def test_a_none_valued_field_is_kept_so_the_none_literal_stays_distinguishable() -> None:
    """`None` is NOT skipped alongside empty lists. `Constant(None)` is the literal `None`;
    dropping it would collapse `x = None` into a node with no fields."""
    from boardwatch.eligibility.engine import canonical_dump, digest_of_sources

    assert "value=None" in canonical_dump(ast.parse("x = None\n"))
    assert digest_of_sources(["x = None\n"]) != digest_of_sources(["x = 0\n"])


def test_unparseable_source_is_not_silently_skipped() -> None:
    from boardwatch.eligibility.engine import digest_of_sources

    with pytest.raises(SyntaxError):
        digest_of_sources(["def broken("])


# ---------------------------------------------------------------- grouping

def test_two_distinct_implies_in_one_group_rewrite_the_whole_group(catalog) -> None:
    body = "We do not offer visa sponsorship. Visa sponsorship is available for senior hires."
    facts = Facts(work_authorization=WorkAuthFact(status="needs_sponsorship", jurisdiction="us"))
    result = evaluate(body, facts, BLOCK_ALL, catalog)
    dispositions = {r.rule_id: r.disposition for r in result.requirements}
    assert dispositions["work_auth:no_sponsorship_offered"] == "unknown"
    assert dispositions["work_auth:sponsorship_available"] == "unknown"
    # every row stays recorded with its span, so the user sees the contradiction
    assert len(result.requirements) == 2
    assert all(r.jd_locator["span"][1] > r.jd_locator["span"][0] for r in result.requirements)


def test_two_detections_that_disagree_on_one_implies_abstain_the_whole_cluster(catalog) -> None:
    """Reconciled against .agent/p2-catalog/proto.py (07757bdf), the ORACLE: the brief's
    original form asserted [met, unmet]/ineligible, but proto's stage 1b abstains a cluster
    of the SAME (family, implies) whose rows DISAGREE (met and unmet both present), because
    "any unmet wins" in the roll-up would silently pick the harsher of two stated thresholds.
    "8+ years" met by nobody the "3+ years" row calls met is not a corroboration, it is a
    contradiction the posting itself states, so both rows go unknown and the verdict is
    uncertain. Order-independent: the split is keyed on the set of dispositions, not order.
    """
    body = "8+ years of experience required. 3+ years of experience required."
    result = evaluate(body, Facts(total_years_experience=5), BLOCK_ALL, catalog)
    dispositions = sorted(r.disposition for r in result.requirements)
    assert dispositions == ["unknown", "unknown"]
    assert result.verdict == "uncertain"


def test_two_detections_that_agree_are_corroboration_not_a_split(catalog) -> None:
    """The positive control for the split above: when two detections of the same implies
    AGREE, stage 1b must NOT fire. Both stay unmet, and the roll-up's `any unmet` binds,
    which is order-INDEPENDENT (corpus B21). A split that fired on agreement would turn a
    real `ineligible` into `uncertain`, the softer and wrong direction.
    """
    body = "5+ years of experience required. 8+ years of experience required."
    result = evaluate(body, Facts(total_years_experience=2), BLOCK_ALL, catalog)
    assert {r.disposition for r in result.requirements} == {"unmet"}
    assert result.verdict == "ineligible"


def test_a_degree_gated_disjunction_never_rejects_on_the_years_arm(catalog) -> None:
    """GATE-P5 REGRESSION LOCK (the SpaceX false positive). "A Bachelor's ... or N years of
    experience" clears on EITHER arm; a master's-plus-one-year candidate satisfies the
    degree path, so resolving the pure-years arm to `unmet` and returning INELIGIBLE deleted
    a real job — the unrecoverable direction the deterministic stage must never take. The
    years arm abstains, so the verdict is `uncertain`, not `ineligible`. The two-stage LLM
    gate is what turns such an abstain into a decision; the deterministic stage only refuses
    to reject.
    """
    body = "A Bachelor's degree in CS or 3+ years of professional experience is required."
    facts = Facts(total_years_experience=1, highest_degree="master")
    result = evaluate(body, facts, BLOCK_ALL, catalog)
    assert result.verdict != "ineligible"

    # positive control: a plain floor with no degree alternative still rejects below it
    plain = "8+ years of professional experience is required."
    assert evaluate(plain, facts, BLOCK_ALL, catalog).verdict == "ineligible"


def test_a_conflict_in_one_group_does_not_touch_another_group(catalog) -> None:
    """work_auth declares two independent groups, so each resolves separately."""
    body = (
        "We do not offer visa sponsorship. Visa sponsorship is available for senior hires. "
        "Applicants must be US citizens."
    )
    facts = Facts(work_authorization=WorkAuthFact(status="citizen", jurisdiction="us"))
    result = evaluate(body, facts, BLOCK_ALL, catalog)
    dispositions = {r.rule_id: r.disposition for r in result.requirements}
    assert dispositions["work_auth:no_sponsorship_offered"] == "unknown"
    assert dispositions["work_auth:us_citizen_required"] == "met"


def test_a_conflict_never_crosses_into_a_family_that_reuses_the_same_implies_name(
    catalog,
) -> None:
    """`conflicted` is keyed by (family, implies), not by implies alone.

    `implies_vocabulary` is declared PER FAMILY, so the same name in two families is two
    unrelated claims. The bundled catalog happens not to collide, which is exactly why the
    bare-string form went unnoticed; a user-supplied override reusing a name is enough to
    bleed. The collision is built here by renaming one degree pattern's implies onto a
    work_auth group member. Against a bare-string `conflicted` the last assertion fails:
    `degree:bachelor_required` comes back `unknown` because of a sponsorship contradiction
    that has nothing to do with it.
    """
    import dataclasses

    collision = "sponsorship_available"  # a member of a work_auth exclusive group
    shadowed = dataclasses.replace(
        catalog,
        families=tuple(
            family
            if family.id != "degree"
            else dataclasses.replace(
                family,
                patterns=tuple(
                    dataclasses.replace(pattern, implies=collision)
                    if pattern.id == "bachelor_required"
                    else pattern
                    for pattern in family.patterns
                ),
            )
            for family in catalog.families
        ),
    )
    body = (
        "We do not offer visa sponsorship. Visa sponsorship is available for senior hires. "
        "Bachelor's degree required."
    )
    facts = Facts(
        work_authorization=WorkAuthFact(status="needs_sponsorship", jurisdiction="us"),
        highest_degree="bachelor",
    )
    result = evaluate(body, facts, BLOCK_ALL, shadowed)
    dispositions = {r.rule_id: r.disposition for r in result.requirements}
    assert dispositions["work_auth:no_sponsorship_offered"] == "unknown"  # the real conflict
    assert dispositions["work_auth:sponsorship_available"] == "unknown"
    assert dispositions["degree:bachelor_required"] == "met"  # untouched by another family


def test_a_three_member_group_conflicts_on_any_two_distinct_values(catalog) -> None:
    body = "Applicants must be US citizens. Must be authorized to work in the United States."
    facts = Facts(work_authorization=WorkAuthFact(status="citizen", jurisdiction="us"))
    result = evaluate(body, facts, BLOCK_ALL, catalog)
    assert {r.disposition for r in result.requirements} == {"unknown"}


# ---------------------------------------------------------------- roll-up

def test_roll_up_precedence_unmet_beats_unknown(catalog) -> None:
    body = "Bachelor's degree required. An active TS/SCI clearance is required."
    facts = Facts(highest_degree="none")  # degree unmet, clearance unknown
    assert evaluate(body, facts, BLOCK_ALL, catalog).verdict == "ineligible"


def test_zero_rows_abstains_never_clears_by_silence(catalog) -> None:
    """A body that fires no family in any of the six reaches the roll-up with zero
    requirement rows. `eligible` there is a clear BY SILENCE with an empty evidence chain,
    which the keystone forbids ("No flags" != cleared), so the verdict abstains. The chain
    stays empty — zero rows is the honest record, not a fabricated per-family abstain."""
    result = evaluate("We build lovely software.", Facts(), BLOCK_ALL, catalog)
    assert result.verdict == "uncertain"
    assert result.requirements == ()


def test_a_preference_family_can_never_change_the_verdict(catalog) -> None:
    policy = Policy(families={"degree": "preference"})
    result = evaluate("Bachelor's degree required.", Facts(highest_degree="none"),
                      policy, catalog)
    assert result.verdict == "eligible"
    assert [r.disposition for r in result.requirements] == ["unmet"]  # recorded in full


def test_an_ignored_family_produces_no_rows_at_all(catalog) -> None:
    policy = Policy(families={"degree": "ignore"})
    result = evaluate("Bachelor's degree required.", Facts(highest_degree="none"),
                      policy, catalog)
    assert result.requirements == ()
    assert result.verdict == "eligible"


def test_preferred_and_bonus_rows_never_decide(catalog) -> None:
    result = evaluate("Bachelor's degree preferred.", Facts(highest_degree="none"),
                      BLOCK_ALL, catalog)
    assert [r.requiredness for r in result.requirements] == ["preferred"]
    assert result.verdict == "eligible"


def test_a_blocker_unknown_yields_uncertain(catalog) -> None:
    result = evaluate("Bachelor's degree required.", Facts(), BLOCK_ALL, catalog)
    assert result.verdict == "uncertain"


# ------------------------------------------------------ shipped-default severity (D-035)
#
# Every test above passes an explicit all-`blocker` fixture (`BLOCK_ALL`), which is exactly
# what the severity-layer review flagged as the gap: it proves the MECHANISM works but
# never exercises the SHIPPED DEFAULT a fresh, policy-less user actually gets. These use a
# bare `Policy()` — no overrides — because that is what `work_auth: blocker` in
# rules.yaml's `default_policy` actually ships to a new profile.

_NO_SPONSORSHIP_JD = (
    "We are hiring a backend engineer. We do not offer visa sponsorship for this role."
)


def test_shipped_default_makes_a_fresh_profile_ineligible_on_a_work_auth_hard_stop(
    catalog,
) -> None:
    """The multi-tenancy fix: a fresh user with NO policy overrides (`Policy()`) must get a
    decisive `ineligible` on a genuine work-auth hard stop, not the old 0-ineligible-ever
    behaviour every family shipped before D-035."""
    facts = Facts(
        work_authorization=WorkAuthFact(
            status="needs_sponsorship", jurisdiction="us", needs_sponsorship=True
        )
    )
    result = evaluate(_NO_SPONSORSHIP_JD, facts, Policy(), catalog)
    assert result.verdict == "ineligible"
    row = next(
        r for r in result.requirements if r.rule_id == "work_auth:no_sponsorship_offered"
    )
    assert row.disposition == "unmet"
    # the ineligible row carries a real JD span, never an empty/degenerate one
    start, end = row.jd_locator["span"]
    assert end > start >= 0
    assert _NO_SPONSORSHIP_JD[start:end]  # a genuine quoted substring, not a placeholder


def test_shipped_default_still_abstains_when_no_work_auth_fact_is_declared(catalog) -> None:
    """The keystone guard: the SAME hard-stop JD, under the SAME shipped-default `Policy()`,
    must never resolve to `ineligible` when the user has not declared work_authorization at
    all. A rule that cannot fire is a monitoring failure, not a conservatism feature, but it
    must also never silently delete the posting for a user who simply hasn't answered yet."""
    result = evaluate(_NO_SPONSORSHIP_JD, Facts(), Policy(), catalog)
    assert result.verdict == "uncertain"
    assert result.verdict != "ineligible"


def test_shipped_default_yields_different_correct_verdicts_by_profile(catalog) -> None:
    """Two profiles against the identical JD, both under the shipped-default `Policy()`:
    an F-1/OPT holder (`ead_or_similar` + `needs_sponsorship=True`, P2a's canonical case for
    a status that alone would abstain) is decided `ineligible`, while a US citizen who does
    not need sponsorship is decided `eligible` on the same restriction. Same posting, same
    policy, different facts, different — and correct — outcomes."""
    opt_facts = Facts(
        work_authorization=WorkAuthFact(
            status="ead_or_similar", jurisdiction="us", needs_sponsorship=True
        )
    )
    citizen_facts = Facts(
        work_authorization=WorkAuthFact(
            status="citizen", jurisdiction="us", needs_sponsorship=False
        )
    )
    opt_result = evaluate(_NO_SPONSORSHIP_JD, opt_facts, Policy(), catalog)
    citizen_result = evaluate(_NO_SPONSORSHIP_JD, citizen_facts, Policy(), catalog)
    assert opt_result.verdict == "ineligible"
    assert citizen_result.verdict == "eligible"


def test_score_is_always_written_null(catalog, db, version_id: int) -> None:
    """D17 rejects persisted scores; writing one smuggles a score cache into an audit
    ledger (D-P2-6)."""
    result = evaluate("Bachelor's degree required.", Facts(highest_degree="none"),
                      BLOCK_ALL, catalog)
    identity = build_identity(
        posting_version_id=version_id, facts=Facts(highest_degree="none"), policy=BLOCK_ALL,
        catalog=catalog, declared_fields=declared_fields(),
    )
    with db.begin() as conn:
        write_evaluation(conn, posting_version_id=version_id, identity=identity, result=result)
    with db.connect() as conn:
        assert conn.execute(select(eligibility_evaluations.c.score)).scalar_one() is None


# ---------------------------------------------------------------- ledger write

def _write(db, catalog, version_id: int, facts: Facts, policy: Policy, body: str) -> int:
    result = evaluate(body, facts, policy, catalog)
    identity = build_identity(
        posting_version_id=version_id, facts=facts, policy=policy, catalog=catalog,
        declared_fields=declared_fields(),
    )
    with db.begin() as conn:
        return write_evaluation(
            conn, posting_version_id=version_id, identity=identity, result=result
        )


def test_the_write_is_idempotent(catalog, db, version_id: int) -> None:
    body = "Bachelor's degree required."
    facts = Facts(highest_degree="none")
    first = _write(db, catalog, version_id, facts, BLOCK_ALL, body)
    second = _write(db, catalog, version_id, facts, BLOCK_ALL, body)
    assert first == second
    with db.connect() as conn:
        assert len(get_evaluations(conn, version_id)) == 1


def test_requirements_and_support_persist_with_locators(catalog, db, version_id: int) -> None:
    body = "Bachelor's degree required."
    facts = Facts(highest_degree="bachelor")
    eval_id = _write(db, catalog, version_id, facts, BLOCK_ALL, body)
    with db.connect() as conn:
        requirements = get_requirements(conn, eval_id)
        assert len(requirements) == 1
        row = requirements[0]
        assert row.rule_id == "degree:bachelor_required"
        assert row.disposition == "met"
        assert row.ordinal == 0
        assert row.jd_locator_json["field"] == "body_text"
        start, end = row.jd_locator_json["span"]
        assert body[start:end]
        support = get_support(conn, row.id)
        assert len(support) == 1
        assert support[0].support_kind == "declared_fact"


def test_ordinals_are_dense_from_zero_in_detection_order(catalog, db, version_id: int) -> None:
    """Asserts the ORDINALS, which the previous form never did: it compared the in-memory
    family list to a literal and passed against a store that stamped every row ordinal 0.

    The engine passes a PRE-SORTED list and store/eligibility.py assigns ordinals by
    `enumerate`, so the property splits in two: the emitted order is sorted by (family order
    in the catalog, span start), and the persisted ordinals are dense from zero in exactly
    that order. Both are asserted, so neither half can rot unnoticed.
    """
    body = (
        "Applicants must be US citizens. 5+ years of experience required. "
        "Active Secret clearance required. Bachelor's degree required."
    )
    facts = Facts()
    result = evaluate(body, facts, BLOCK_ALL, catalog)
    order_of = {family.id: index for index, family in enumerate(catalog.families)}
    keys = [
        (order_of[r.rule_id.split(":", 1)[0]], r.jd_locator["span"][0])
        for r in result.requirements
    ]
    assert len(keys) == 4
    assert keys == sorted(keys)
    assert [r.rule_id.split(":", 1)[0] for r in result.requirements] == [
        "work_auth", "experience_years", "clearance", "degree"
    ]
    eval_id = _write(db, catalog, version_id, facts, BLOCK_ALL, body)
    with db.connect() as conn:
        rows = get_requirements(conn, eval_id)
    assert [row.ordinal for row in rows] == [0, 1, 2, 3]
    assert [row.rule_id for row in rows] == [r.rule_id for r in result.requirements]


def test_the_persisted_snapshot_reproduces_its_own_hashes(catalog, db, version_id: int) -> None:
    from boardwatch.eligibility.hashing import digest

    facts = Facts(highest_degree="none")
    _write(db, catalog, version_id, facts, BLOCK_ALL, "Bachelor's degree required.")
    with db.connect() as conn:
        row = conn.execute(select(eligibility_inputs)).one()
    assert digest(row.profile_snapshot_json) == row.profile_hash
    assert digest(row.rules_snapshot_json) == row.rules_hash


def test_a_fingerprint_snapshot_mismatch_is_rejected(catalog, db, version_id: int) -> None:
    from boardwatch.eligibility.hashing import IdentityMismatchError, InputIdentity

    result = evaluate("Bachelor's degree required.", Facts(), BLOCK_ALL, catalog)
    identity = build_identity(
        posting_version_id=version_id, facts=Facts(), policy=BLOCK_ALL, catalog=catalog,
        declared_fields=declared_fields(),
    )
    tampered = InputIdentity(
        profile_hash=identity.profile_hash,
        profile_snapshot={"fields": {"highest_degree": "doctorate"}},
        rules_hash=identity.rules_hash, rules_snapshot=identity.rules_snapshot,
        input_fingerprint=identity.input_fingerprint,
    )
    with db.begin() as conn, pytest.raises(IdentityMismatchError):
        write_evaluation(
            conn, posting_version_id=version_id, identity=tampered, result=result
        )


def test_an_engine_version_bump_produces_a_second_evaluation(
    catalog, db, version_id: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D-P2-13. Rev 1's "evaluate where no evaluation exists" skipped a REQUIRED
    re-evaluation after a bump, because a v1 row already existed for that fingerprint."""
    from boardwatch.eligibility import engine as engine_module

    body = "Bachelor's degree required."
    facts = Facts(highest_degree="none")
    real = engine_version()  # captured BEFORE the patch, or the expected set collapses to one
    first = _write(db, catalog, version_id, facts, BLOCK_ALL, body)
    monkeypatch.setattr(engine_module, "engine_version", lambda: "999+deadbeefcafe")
    second = _write(db, catalog, version_id, facts, BLOCK_ALL, body)
    assert first != second
    with db.connect() as conn:
        rows = get_evaluations(conn, version_id)
    assert len(rows) == 2
    assert {r.engine_version for r in rows} == {real, "999+deadbeefcafe"}
    assert {r.engine_kind for r in rows} == {ENGINE_KIND}


def test_an_input_row_that_is_already_there_is_reused(catalog, db, version_id: int) -> None:
    """A row that has ALREADY landed is not a race, and this assertion CANNOT fail against
    the pre-SELECT code: the pre-SELECT finds the row and returns it, which is precisely how
    the previous version of this test passed against the unmodified `_get_or_create_input`.
    Kept, because reuse is still worth pinning. The actual race is the next test."""
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert

    from boardwatch.store.tables import eligibility_inputs as inputs_table

    identity = build_identity(
        posting_version_id=version_id, facts=Facts(), policy=BLOCK_ALL, catalog=catalog,
        declared_fields=declared_fields(),
    )
    with db.begin() as conn:
        conn.execute(sqlite_insert(inputs_table).values(
            posting_version_id=version_id, profile_hash=identity.profile_hash,
            profile_snapshot_json=identity.profile_snapshot, rules_hash=identity.rules_hash,
            rules_snapshot_json=identity.rules_snapshot,
            input_fingerprint=identity.input_fingerprint, created_at=utcnow(),
        ))
    result = evaluate("Bachelor's degree required.", Facts(), BLOCK_ALL, catalog)
    with db.begin() as conn:
        eval_id = write_evaluation(
            conn, posting_version_id=version_id, identity=identity, result=result
        )
    assert eval_id > 0
    with db.connect() as conn:
        assert len(conn.execute(select(inputs_table)).all()) == 1


def test_a_writer_that_loses_the_race_is_still_idempotent(catalog, db, version_id: int) -> None:
    """THE regression Step 4 exists to close, and it FAILS against the unmodified code.

    The failure window is between the pre-SELECT and the insert that follows it, so the
    racing writer has to land inside that window. `after_cursor_execute` fires on the FIRST
    statement this connection issues against eligibility_inputs, and what that statement IS
    decides everything:

      pre-SELECT-then-insert  the first statement is a SELECT, the second `top` run's row is
                              injected on another connection, and the following INSERT raises
                              IntegrityError. Both assertions below are unreachable.
      insert-then-reselect    the first statement is the INSERT itself, so there is no window
                              to inject into and the hook returns without doing anything.

    `first` is asserted directly as well as behaviourally, so a later reader cannot mistake
    the hook for decoration, and the failure names the cause instead of surfacing as a bare
    IntegrityError.
    """
    from sqlalchemy import event
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert

    from boardwatch.store.tables import eligibility_inputs as inputs_table

    identity = build_identity(
        posting_version_id=version_id, facts=Facts(), policy=BLOCK_ALL, catalog=catalog,
        declared_fields=declared_fields(),
    )
    result = evaluate("Bachelor's degree required.", Facts(), BLOCK_ALL, catalog)
    first: list[str] = []

    def inject(conn, cursor, statement, parameters, context, executemany) -> None:
        if first or "eligibility_inputs" not in statement:
            return
        first.append(statement)
        if not statement.lstrip().upper().startswith("SELECT"):
            return  # insert-then-reselect: this writer already won its own race
        with db.begin() as racer:  # a SECOND connection, exactly as a second `top` run
            racer.execute(sqlite_insert(inputs_table).values(
                posting_version_id=version_id, profile_hash=identity.profile_hash,
                profile_snapshot_json=identity.profile_snapshot,
                rules_hash=identity.rules_hash, rules_snapshot_json=identity.rules_snapshot,
                input_fingerprint=identity.input_fingerprint, created_at=utcnow(),
            ))

    event.listen(db, "after_cursor_execute", inject)
    try:
        with db.begin() as conn:
            eval_id = write_evaluation(
                conn, posting_version_id=version_id, identity=identity, result=result
            )
    finally:
        event.remove(db, "after_cursor_execute", inject)
    assert first, "no statement touched eligibility_inputs at all"
    assert first[0].lstrip().upper().startswith("INSERT"), first[0]
    assert eval_id > 0
    with db.connect() as conn:
        assert len(conn.execute(select(inputs_table)).all()) == 1


def test_current_evaluations_answers_only_for_the_running_engine_version(
    catalog, db, version_id: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The version filter is the anti-join D-P2-13 turns on: `get_evaluations` returns EVERY
    evaluation with no version selector, so a `current_evaluations` that lost its filter
    would hand a caller a verdict computed by a superseded engine and the re-evaluation would
    never happen. Fails against `current_evaluations -> {}` on the first assertion.
    """
    from boardwatch.eligibility import engine as engine_module

    body = "Bachelor's degree required."
    facts = Facts(highest_degree="none")
    eval_id = _write(db, catalog, version_id, facts, BLOCK_ALL, body)
    identity = build_identity(
        posting_version_id=version_id,
        facts=facts,
        policy=BLOCK_ALL,
        catalog=catalog,
        declared_fields=declared_fields(),
    )
    ph, rh = identity.profile_hash, identity.rules_hash
    with db.connect() as conn:
        assert engine_module.current_evaluations(conn, [version_id], ph, rh) == {
            version_id: (eval_id, "ineligible")
        }
        assert engine_module.current_evaluations(conn, [], ph, rh) == {}
        assert engine_module.current_evaluations(conn, [version_id + 1000], ph, rh) == {}
        # a different profile's identity must not be handed THIS profile's verdict: the
        # anti-join keys on (profile_hash, rules_hash), not on the engine version alone.
        assert engine_module.current_evaluations(conn, [version_id], "other", rh) == {}
        assert engine_module.current_evaluations(conn, [version_id], ph, "other") == {}
        # the row was written by the CURRENT version, so a bumped engine must not see it
        monkeypatch.setattr(engine_module, "engine_version", lambda: "999+deadbeefcafe")
        assert engine_module.current_evaluations(conn, [version_id], ph, rh) == {}


def test_the_derived_version_is_cached_and_the_cache_is_clearable() -> None:
    """`engine_version` is lru_cache'd, so the cache is part of the contract rather than an
    optimisation: nothing re-derives the version within a process, and any caller that edits
    or narrows a digested module in-process depends on `cache_clear` actually re-deriving.
    Neither half was executed anywhere.

    Assertion 1 fails if the result is not cached, assertion 2 if the cache cannot be
    cleared. `digested_modules` is restored and the cache cleared in a `finally` rather than
    by monkeypatch, because monkeypatch undoes its setattr at TEARDOWN, which is after the
    last assertion here and would leave the narrowed version cached for every later test.
    """
    from boardwatch.eligibility import engine as engine_module

    baseline = engine_module.engine_version()
    original = engine_module.digested_modules
    engine_module.digested_modules = lambda: ("engine.py",)  # narrower, so another digest
    try:
        assert engine_module.engine_version() == baseline  # still the cached value
        engine_module.engine_version.cache_clear()
        assert engine_module.engine_version() != baseline  # re-derived from the narrow list
    finally:
        engine_module.digested_modules = original
        engine_module.engine_version.cache_clear()
    assert engine_module.engine_version() == baseline


# ---------------------------------------------------------------- field-tier applicability

def test_field_applicability_four_cases(tmp_path) -> None:
    cat = _field_catalog(tmp_path, assign={"degree": ["software"]})
    degree = cat.family("degree")
    assert field_applicability(degree, "software", cat) == "active"
    assert field_applicability(degree, "data", cat) == "skip"          # valid other field
    assert field_applicability(degree, None, cat) == "abstain"         # missing
    assert field_applicability(degree, "bogus", cat) == "abstain"      # out-of-vocab
    # a non-field family is always active regardless of career_field
    assert field_applicability(cat.family("work_auth"), None, cat) == "active"


def test_three_field_active_routing(tmp_path) -> None:
    """Gate P2 evidence: >=3 career_fields each route their own family active, others skip."""
    cat = _field_catalog(
        tmp_path,
        assign={"degree": ["software"], "clearance": ["data"], "internship": ["design"]},
    )
    routes = {"software": "degree", "data": "clearance", "design": "internship"}
    for cf, active in routes.items():
        states = {fid: field_applicability(cat.family(fid), cf, cat)
                  for fid in ("degree", "clearance", "internship")}
        assert states[active] == "active"
        assert all(states[o] == "skip" for o in states if o != active)


def test_active_field_family_produces_rows(tmp_path) -> None:
    cat = _controlled_catalog(tmp_path)
    facts = Facts(career_field="software", highest_degree="none")
    result = evaluate("A bachelor's degree is required.", facts, Policy(), cat)
    assert any(r.rule_id == "degree:bachelor_required" for r in result.requirements)


def test_skip_field_family_produces_zero_rows(tmp_path) -> None:
    cat = _controlled_catalog(tmp_path)
    facts = Facts(career_field="data", highest_degree="none")  # valid, other field
    result = evaluate("A bachelor's degree is required.", facts, Policy(), cat)
    assert result.requirements == ()
    assert result.verdict == "eligible"


def test_missing_career_field_abstains_not_clears(tmp_path) -> None:
    cat = _controlled_catalog(tmp_path)
    facts = Facts(career_field=None, highest_degree="none")
    result = evaluate("A bachelor's degree is required.", facts, Policy(), cat)
    row = next(r for r in result.requirements if r.rule_id == "degree:bachelor_required")
    assert row.disposition == "unknown"
    assert row.rationale == "missing_profile_field:career_field"


def test_out_of_vocab_career_field_abstains_not_clears(tmp_path) -> None:
    cat = _controlled_catalog(tmp_path)
    facts = Facts(career_field="bogus", highest_degree="none")
    result = evaluate("A bachelor's degree is required.", facts, Policy(), cat)
    row = next(r for r in result.requirements if r.rule_id == "degree:bachelor_required")
    assert row.disposition == "unknown"
    assert row.rationale == "missing_profile_field:career_field"


def test_field_abstain_wins_a_genuine_collision_with_posting_waive(tmp_path) -> None:
    """A detection that ALSO carries a posting-waive escape (`detection.abstained` is set,
    from `_CONTROLLED`'s `abstain_by: ["unless otherwise noted"]` matching the JD) must still
    report the field-abstain rationale, not the posting-waive one.

    Both branches produce the SAME disposition (`unknown`), so a test that only checks
    disposition on a NON-colliding detection cannot tell the two branches apart, and a future
    reorder that checked `detection.abstained` first would silently flip only the rationale
    string. This constructs the actual collision — the same detection satisfies BOTH
    conditions at once — and pins that the field-abstain branch, which runs first in
    `evaluate`, is the one that wins.
    """
    cat = _controlled_catalog(tmp_path)
    body = "A bachelor's degree is required, unless otherwise noted."
    facts = Facts(career_field=None, highest_degree="none")  # missing -> field-abstain applies
    result = evaluate(body, facts, Policy(), cat)
    row = next(r for r in result.requirements if r.rule_id == "degree:bachelor_required")
    assert row.disposition == "unknown"
    assert row.rationale == "missing_profile_field:career_field"

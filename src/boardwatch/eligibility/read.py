"""Public read paths into the eligibility ledger (A6).

current_verdicts replaces the private _current_verdicts that used to live in
cli/top_cmd.py. Unlike that helper it is NOT open-only: the caller supplies the
posting version ids it cares about (obtained from current_posting_versions), so a
closed posting's current version is eligible for a verdict lookup, which is what an
export of closed tracked postings needs.
"""

from __future__ import annotations

from typing import NamedTuple

from sqlalchemy import Connection, func, select

from boardwatch.eligibility.engine import current_evaluations
from boardwatch.eligibility.final_gate import GATE_VERSION_PREFIX
from boardwatch.store.param_chunks import id_chunks
from boardwatch.store.tables import (
    eligibility_evaluations,
    eligibility_inputs,
    eligibility_requirements,
    posting_versions,
)


def current_evaluations_chunked(
    conn: Connection,
    posting_version_ids: list[int],
    profile_hash: str,
    rules_hash: str,
) -> dict[int, tuple[int, str]]:
    """`engine.current_evaluations`, safe for a list longer than SQLite's parameter cap.

    Use this, never the engine's function directly, wherever the id list is sized by the
    corpus. Every such caller passes the current version of every OPEN posting, and that list
    crossed `SQLITE_LIMIT_VARIABLE_NUMBER` (32766) on 2026-08-23 at 32,771 open postings: the
    funnel write hit it first and swallowed `too many SQL variables` into a printed warning,
    then the ranker hit it and took the run down. The corpus only grows, so it was permanent.

    It lives HERE rather than inside `engine.py` deliberately. `engine.py` is a digested
    module (`engine.digested_modules`), so batching the read in place would move
    `engine_version` — re-keying every verdict in the corpus and, through
    `pipeline.policy.run_policy_version`, every permanent ledger stamp, which owes a manual
    `ledger reopen --stale` that re-surfaces already-built leads. All of that for a change
    that cannot alter a single verdict.

    Chunk-then-merge is exact: the engine's read is a per-posting-version lookup with no
    aggregate, so the union over chunks is the un-chunked result.
    """
    out: dict[int, tuple[int, str]] = {}
    for chunk in id_chunks(posting_version_ids):
        out.update(current_evaluations(conn, chunk, profile_hash, rules_hash))
    return out


def _posting_by_version(conn: Connection, posting_version_ids: list[int]) -> dict[int, int]:
    """posting_version_id -> posting_id, chunked past the bound-parameter cap.

    Shared by both public reads below, which each need the same mapping to key their result
    by posting rather than by version.
    """
    out: dict[int, int] = {}
    for chunk in id_chunks(posting_version_ids):
        rows = conn.execute(
            select(posting_versions.c.id, posting_versions.c.posting_id).where(
                posting_versions.c.id.in_(chunk)
            )
        ).all()
        out.update({int(row.id): int(row.posting_id) for row in rows})
    return out


def current_verdicts(
    conn: Connection,
    posting_version_ids: list[int],
    profile_hash: str | None,
    rules_hash: str | None,
) -> dict[int, str | None]:
    """posting_id -> the CURRENT profile's verdict for its current version, or None.

    The caller controls the posting scope via posting_version_ids (the current
    versions from current_posting_versions), so this read is not restricted to open
    postings. Keyed on the identity the run already computed, so a corrected fact or
    policy is reflected the moment its re-evaluation lands, never a leftover verdict
    from an old profile. Returns {} when either hash is None, which is what the
    preflight reports for a store with no profile.
    """
    if profile_hash is None or rules_hash is None:
        return {}
    if not posting_version_ids:
        return {}
    evals = current_evaluations_chunked(conn, posting_version_ids, profile_hash, rules_hash)
    version_to_posting = _posting_by_version(conn, posting_version_ids)
    return {
        version_to_posting[vid]: (evals.get(vid) or (None, None))[1]
        for vid in posting_version_ids
        if vid in version_to_posting
    }


#: Rule-id prefixes whose ABSTAIN means a blocking rule could not be decided at all. Matched on the
#: `family:` prefix rather than by listing rule ids, so a new pattern in either family is covered
#: the day it ships — the opposite of a closed catalog, and correct here: this asks which FAMILY
#: the rule belongs to, and the families are the closed set.
HARD_FAMILIES = ("work_auth:", "clearance:")

#: The family whose bar the candidate may simply not clear. `unmet` counts alongside `unknown`:
#: both mean the requirement is not confirmed satisfied, which is the question the lane asks.
EXPERIENCE_FAMILY = "experience_years:"


class RequirementFlags(NamedTuple):
    """Three booleans summarising one posting's current requirement rows.

    A summary, not the rows: the lane decision needs to know only whether a requirement of each
    kind EXISTS, and carrying the rows would invite a second, differently filtered opinion
    downstream.

    The third flag does not ask a stronger version of the first two — it asks a DIFFERENT
    question, and that is why it is its own field rather than a widening of either. The two
    `*_unconfirmed` flags ask which kind of requirement the engine left unresolved, so both
    presuppose a row; `no_requirement_rows` asks whether the extractor produced a row at all.
    They are mutually exclusive by construction: all three come from the one query below, so a
    posting with no rows cannot carry an unconfirmed one.
    """

    #: A REQUIRED `experience_years` row resolved `unmet` or `unknown` — a bar not confirmed met.
    experience_unconfirmed: bool = False
    #: A REQUIRED `work_auth`/`clearance` row resolved `unknown` — a blocking rule that ABSTAINED.
    #: `unmet` is deliberately NOT folded in: an unmet hard rule makes the verdict `ineligible`,
    #: which has its own drain, and counting it here would relabel that lead's hold.
    eligibility_unconfirmed: bool = False
    #: The current evaluation produced NO requirement row: no family matched anything in the body,
    #: of any disposition and any requiredness. Neither filter the two flags above apply is applied
    #: here — a `met` row and a `preferred` row both mean the catalog read the JD and reached a
    #: disposition, which is the whole of the question — so a row of ANY shape clears it.
    no_requirement_rows: bool = False


#: The all-False summary, as ONE immutable value. Callers use it as the default for a posting with
#: no current evaluation, and as an argument default — which `RequirementFlags()` cannot be, since a
#: call in a default is flagged even when the type is immutable.
#:
#: All three fields are claims about an evaluation, so the all-False value asserts NONE of them:
#: not "this posting has requirement rows", but "nothing is known about its requirements". That is
#: exactly right for a posting with no current evaluation, which is the case it defaults for — and
#: it is why the lane routes that case on the `None` verdict arriving from the same read rather
#: than on `no_requirement_rows`, which would make an absence indistinguishable from a measured
#: False.
NO_REQUIREMENT_FLAGS = RequirementFlags()


def current_requirement_flags(
    conn: Connection,
    posting_version_ids: list[int],
    profile_hash: str | None,
    rules_hash: str | None,
) -> dict[int, RequirementFlags]:
    """posting_id -> what its CURRENT evaluation's requirement rows say about the delivery lane.

    Scoped exactly like `current_verdicts` — same identity, same version list, same read of
    `current_evaluations_chunked` — so a caller that takes both gets a verdict and a summary from
    the SAME evaluation. That is the whole point: the delivery lane reads them together, and a
    summary drawn from a different evaluation than the verdict beside it could hold a lead for a
    requirement the verdict had already resolved.

    A posting with no current evaluation is absent from the result, exactly as it is absent from
    `current_verdicts`; the caller's `.get(...)` default supplies the all-False summary, which is
    the old behaviour. That case is NOT `no_requirement_rows`: see `NO_REQUIREMENT_FLAGS`.
    """
    if profile_hash is None or rules_hash is None or not posting_version_ids:
        return {}
    evals = current_evaluations_chunked(conn, posting_version_ids, profile_hash, rules_hash)
    version_by_eval = {eval_id: vid for vid, (eval_id, _) in evals.items()}
    flags: dict[int, list[bool]] = {}
    # Evaluations that produced at least one row, so the zero-row set is the rest of the
    # evaluations THIS read already found. Derived from the same rows as the two flags rather
    # than from a second `NOT EXISTS` query, which would be a differently scoped opinion about
    # the same evaluation -- the drift this whole function exists to prevent.
    with_rows: set[int] = set()
    for chunk in id_chunks(list(version_by_eval)):
        rows = conn.execute(
            select(
                eligibility_requirements.c.evaluation_id,
                eligibility_requirements.c.rule_id,
                eligibility_requirements.c.disposition,
                eligibility_requirements.c.requiredness,
            ).where(eligibility_requirements.c.evaluation_id.in_(chunk))
        ).all()
        for row in rows:
            with_rows.add(int(row.evaluation_id))
            rule_id, disposition = row.rule_id, str(row.disposition)
            if not rule_id:
                continue
            # Both filters are applied HERE rather than in the where-clause, because the zero-row
            # question needs every row and these two questions need a subset of them. One read,
            # three answers: a narrowed query would have to be a second one, differently scoped.
            #
            # `engine.blocking` counts a row only when it is `required` AND its family is a
            # blocker, so a `preferred`/`bonus` row can never make a verdict `ineligible` or
            # `uncertain`. Holding a lead for one would be a hold on a requirement that cannot
            # block -- 2,790 rows on the live store, `clearance_preferred` the bulk of them.
            # Severity is the other half of that test and is NOT stored per row (it comes from
            # the caller's policy), so it is not filtered here; under a policy that demotes one
            # of these families the flag can still be set for a row that no longer blocks.
            # That is reachable only once an `eligible` verdict is subject to these gates,
            # which it is not today.
            if str(row.requiredness) != "required" or disposition not in ("unmet", "unknown"):
                continue
            experience = rule_id.startswith(EXPERIENCE_FAMILY)
            eligibility = disposition == "unknown" and rule_id.startswith(HARD_FAMILIES)
            # Only a row that sets a flag creates an entry. An unconfirmed row from ANY other
            # family -- `degree`, `internship`, `contract_not_fte` -- decides nothing here;
            # entering it would carry ~2k all-False summaries that read exactly like the absent
            # default while costing a dict entry each.
            if not (experience or eligibility):
                continue
            seen = flags.setdefault(int(row.evaluation_id), [False, False])
            seen[0] |= experience
            seen[1] |= eligibility
    version_to_posting = _posting_by_version(conn, posting_version_ids)
    out: dict[int, RequirementFlags] = {}
    for eval_id, (experience, eligibility) in flags.items():
        vid = version_by_eval[eval_id]
        posting_id = version_to_posting.get(vid)
        if posting_id is not None:
            out[posting_id] = RequirementFlags(experience, eligibility)
    # A zero-row evaluation sets no flag above, so it would otherwise be absent -- and absent
    # means "nothing is known about its requirements", which is the one thing that IS known here:
    # the catalog read the body and matched nothing. A posting whose rows are all decided stays
    # absent, because for that one the all-False default is the true summary.
    for eval_id, vid in version_by_eval.items():
        posting_id = version_to_posting.get(vid)
        if eval_id not in with_rows and posting_id is not None:
            out[posting_id] = RequirementFlags(no_requirement_rows=True)
    return out


def current_gate_verdicts(
    conn: Connection, posting_version_ids: list[int],
    profile_hash: str | None, rules_hash: str | None,
) -> dict[int, str | None]:
    """posting_id -> the LATEST final-gate verdict for its current version under this identity.

    Scoped to engine_kind='llm' AND engine_version LIKE 'final_gate:%' — so it never picks up the
    advisory extract_llm lane ('llm:%'), and the deterministic read (engine_kind='deterministic')
    never picks up either. The gate lane has no unique index; max(id) per posting_version means the
    most recent apply wins (a re-judge overrides), which is the intended semantics.
    """
    if profile_hash is None or rules_hash is None or not posting_version_ids:
        return {}
    # Chunked past SQLite's bound-parameter cap, which the open corpus crossed on 2026-08-23
    # (see current_evaluations_chunked). Sound here because the chunked column IS the group
    # key: every posting_version's rows fall in exactly one chunk, so max(id) per
    # posting_version is the same answer chunked or whole.
    verdict_by_version: dict[int, str] = {}
    for chunk in id_chunks(posting_version_ids):
        latest = (
            select(eligibility_inputs.c.posting_version_id,
                   func.max(eligibility_evaluations.c.id).label("eid"))
            .join(eligibility_inputs, eligibility_evaluations.c.input_id == eligibility_inputs.c.id)
            .where(
                eligibility_inputs.c.posting_version_id.in_(chunk),
                eligibility_inputs.c.profile_hash == profile_hash,
                eligibility_inputs.c.rules_hash == rules_hash,
                eligibility_evaluations.c.engine_kind == "llm",
                eligibility_evaluations.c.engine_version.like(f"{GATE_VERSION_PREFIX}%"),
            )
            .group_by(eligibility_inputs.c.posting_version_id)
            .subquery()
        )
        rows = conn.execute(
            select(eligibility_inputs.c.posting_version_id, eligibility_evaluations.c.verdict)
            .join(latest, eligibility_evaluations.c.id == latest.c.eid)
            .join(eligibility_inputs, eligibility_evaluations.c.input_id == eligibility_inputs.c.id)
        ).all()
        verdict_by_version.update(
            {int(r.posting_version_id): str(r.verdict) for r in rows}
        )
    v2p = _posting_by_version(conn, posting_version_ids)
    return {v2p[vid]: verdict
            for vid, verdict in verdict_by_version.items() if vid in v2p}

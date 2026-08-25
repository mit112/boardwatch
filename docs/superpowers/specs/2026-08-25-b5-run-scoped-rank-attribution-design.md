# B5 — run-scoped rank attribution (silent-empty-day guard) — design

**Date:** 2026-08-25
**Status:** approved-in-chat, awaiting spec review → writing-plans
**Owner call settled (this session):** Approach A (twins in the ranker); **no `artifact_version` bump**
(additive funnel fields only, holding the precedent set at version 6).

## Problem

The daily driver has a zero-output guard (`pipeline/runner.py::_zero_output_guard`) whose job is B5:
distinguish an **honest** empty day (the run correctly produced nothing) from a **silent** one (the run
reported success but lost a lead it should have delivered). The guard is **dormant** — it can never fire.

Root cause (D-282). The guard's trigger, `candidate_judged_this_run`, is **run-scoped** (postings whose
current eligibility verdict ∈ {eligible, uncertain} were attributed to *this* run via
`eligibility_evaluations.run_id`). But the clauses that let it say "…and there is no legitimate reason",
`ranked.hidden_handled` and `ranked.hidden_applied`, are **corpus-scoped** — measured over all 18k–33k open
postings (`hidden_handled` was 8 / 48 / 128 on runs 68/69/71; `hidden_hard_filter` alone is 18,472–18,932).
Those numbers are almost never zero, so the guard's `hidden_handled == 0 and hidden_applied == 0` condition
is almost never met and it stays silent. It cannot be repaired by admitting more corpus-scoped buckets:
they form an **exhaustive partition** of the corpus, so "can this run explain the empty day?" is always yes
by construction — a complete partition cannot evidence a silent failure.

## The fix (Approach A)

Count the ranker's **suppression** drops **restricted to the postings this run judged**, and rewrite the
guard to reason at run scope. Four drop sites get a run-scoped twin — exactly the outcomes that make an
empty day *honest* (the program already delivered/decided on the job, or the posting is gone):

| Suppression site | Corpus counter today | Where it lives | New run-scoped twin |
|---|---|---|---|
| Ledger disposition (built / skipped / seen-TTL) | `hidden_handled` | `cli/top_cmd.py` rank loop | `hidden_handled_this_run` |
| Submitted application | `hidden_applied` | `cli/top_cmd.py` rank loop | `hidden_applied_this_run` |
| Provable duplicate (`exact_quad`) | `hidden_duplicate` | `cli/top_cmd.py` rank loop | `hidden_duplicate_this_run` |
| Withheld as gone (liveness) | `dead_lead_ids` | `pipeline/runner.py` liveness stage | `dead_this_run` |

**Rejections are deliberately NOT twinned** — hard-filter, non-SWE, over-seniority, below-cutoff. A
filter or cap that ate the whole shortlist is precisely the silent empty day the guard exists to catch
(D-246: "A misconfigured `target_seniority_band` that ate the whole shortlist is exactly the silent empty
day this guard exists to catch"). So the guard *should* fire when this run judged eligible work and a
rejection/cap consumed all of it — that is intended, not a false alarm.

### Reconciliation identity (the D-282 "plus the reconciliation identity")

Let `J = candidate_judged_this_run`. Define

```
unexplained_this_run =
    J
    - hidden_handled_this_run
    - hidden_applied_this_run
    - hidden_duplicate_this_run
    - dead_this_run
```

Invariant, asserted at the guard: **`unexplained_this_run >= 0`**. Each twin is a subset of the this-run
judged set, and the four subsets are disjoint (a posting leaves the ranker at exactly one `continue`;
`dead` is a post-rank fate of a *surfaced* posting, disjoint from the three suppressions that `continue`
before surfacing). A negative value means a counting bug — raise, do not silently clamp. This is the
self-checking identity the drop-counting subsystem is built on (`considered == Σ drops`), narrowed to the
run-scoped subset the guard needs. It is **not** a full run-scoped mirror of all eight corpus buckets —
that would incur the 27-mirror-site tax the code warns about, for no B5 benefit.

### Guard rewrite

`_zero_output_guard` currently fires on `J > 0 and hidden_handled == 0 and dead_leads == 0 and
hidden_applied == 0` (corpus-scoped, hence dormant). Replace with:

```python
def _zero_output_guard(
    candidate_judged_this_run: int,
    handled_this_run: int = 0,
    applied_this_run: int = 0,
    duplicate_this_run: int = 0,
    dead_this_run: int = 0,
) -> str | None:
    unexplained = (
        candidate_judged_this_run
        - handled_this_run - applied_this_run - duplicate_this_run - dead_this_run
    )
    if unexplained < 0:
        raise ZeroOutputReconciliationError(...)  # typed, at the raise site; never clamp
    if unexplained > 0:
        return f"empty day not provably right: {unexplained} of {candidate_judged_this_run} candidate postings judged this run were neither delivered nor honestly suppressed"
    return None
```

The guard's outer reachability is unchanged (only reached when `renderable == 0` — no lead rendered).

## Plumbing "judged this run" into the ranker

`rank_open_postings` already runs `run_eligibility(..., run_id=run_id)` first, so this run's evaluations
are persisted before ranking. Add a sibling of the existing count query:

- `store/run_funnel_queries.py`: `posting_ids_judged_this_run(conn, *, profile_hash, rules_hash,
  engine_kind, engine_version, run_id) -> set[int]` — the id-returning form of
  `count_candidate_judged_this_run` (verdict ∈ {eligible, uncertain}, `run_id == run_id`). Factor the
  shared `WHERE` so the count and the id-set cannot drift.
- `cli/top_cmd.py::rank_open_postings`: fetch that set once (only when `run_id is not None`; empty set
  otherwise — `top`/gate callers pass no run and get zeros). At each of the three suppression `continue`
  branches (`hidden_duplicate`, `hidden_applied`, `hidden_handled`) increment the twin when
  `posting.posting_id in judged_this_run`. Add the three twin fields to `RankedResults`, defaulting 0.
- `pipeline/runner.py`: `dead_this_run = len(dead posting ids ∩ judged_this_run)`. The judged set is
  already computed at the guard call site (the block that builds `candidate_judged_this_run`); reuse the
  id-set query there so the runner and ranker agree on membership. Feed the four run-scoped values into
  the rewritten `_zero_output_guard`.

## Funnel artifact

The run-scoped fields surface in the funnel projection (`store/run_funnel_queries.py`,
`reports/run_funnel.py`) as additive keys **without** an `artifact_version` bump (owner call this session,
following D-285). They are guard-supporting diagnostics, not new members of the corpus reconciliation
identity, so they do **not** enter the `considered == Σ drops` sum and must not be added to it.

## Scope boundaries (documented, not built)

- **LLM/agent final gate.** `cli/top_cmd.py` can also hide a posting on a persisted `gate_verdicts`
  `ineligible` (the manual `eligibility gate request` lane), which `count_candidate_judged_this_run` does
  not count. The **automated daily driver does not invoke that gate** (`runner.py` has no gate call), so
  this hole is off the daily B5 path. If the operator has persisted manual gate `ineligible` verdicts, a
  posting hidden that way is a rejection, not a suppression — consistent with "rejections fire the guard."
  Not addressed here; noted so a later reader does not mistake it for an oversight.
- **`engine_version` unchanged.** No eligibility/catalog/detect/resolve/engine edit → no ledger drain.
- **Freeze-safe.** Ranker instrumentation + funnel diagnostics + the guard. No eligibility, profile, or
  résumé-gate change, so it does not break the Part 6 freeze and may merge before the frozen runs.

## Testing (discriminating)

Every guard test must be shown to **FAIL against the current corpus-scoped guard** before it counts
(a test that passes against the broken implementation is vacuous):

1. **Silent empty day fires (the bug):** this run judged N≥1 eligible postings; all are dropped by a
   *rejection* (e.g. below-cutoff or hard-filter) or silently lost; 0 leads. New guard **fires**; old
   guard does **not** (its `hidden_handled`/`hidden_applied` are non-zero corpus-wide). This is the
   regression the whole change exists to close.
2. **Ledger-drain honest day does not fire:** every this-run candidate is `handled_this_run` (or applied /
   duplicate / dead). `unexplained_this_run == 0` → no fire.
3. **Steady-state cache-hit day does not fire:** `J == 0` → `unexplained == 0` → no fire.
4. **Mixed day fires on the remainder:** J = 5, two handled-this-run, three below-cutoff, 0 leads →
   `unexplained == 3` → fire.
5. **Reconciliation invariant:** a constructed miscount making a twin exceed `J` raises the typed error
   rather than clamping (mutation-tested: deleting the `raise` fails this test).
6. **`posting_ids_judged_this_run` matches `count_candidate_judged_this_run`:** the id set's length equals
   the count on the same inputs (guards the shared-`WHERE` refactor against drift).

## Files touched

- `src/boardwatch/store/run_funnel_queries.py` — new id-set query + shared `WHERE`; funnel projection fields.
- `src/boardwatch/cli/top_cmd.py` — three `RankedResults` twin fields + increments in the three
  suppression branches; fetch the judged-this-run set.
- `src/boardwatch/pipeline/runner.py` — `dead_this_run`; rewritten `_zero_output_guard` + its call site.
- `src/boardwatch/reports/run_funnel.py` — surface the run-scoped fields (additive).
- Tests under `tests/` for the six cases above.
- Docstring corrections at the two D-282 sites (the guard is no longer dormant).

## Not in scope

Full run-scoped mirrors of the four rejection buckets; any `artifact_version` bump; touching the corpus
reconciliation identity; the LLM-gate hole; raising `DEFAULT_TOP_N`.

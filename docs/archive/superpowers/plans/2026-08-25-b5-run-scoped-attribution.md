# B5 Run-Scoped Rank Attribution — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Arm the dormant B5 zero-output guard by counting the ranker's four suppression drops restricted to the postings this run judged, so a silent empty day is distinguishable from an honest one.

**Architecture:** One run-scoped set of posting-ids (`eligible`/`uncertain` verdicts attributed to this run) drives three new ranker twin counters (handled/applied/duplicate) and, in the runner, a dead-intersection. The guard fires when `J − Σ(four suppressions) > 0` with 0 leads, and hard-errors if that goes negative. No new corpus drop bucket, no `artifact_version` bump, no `engine_version` change.

**Tech Stack:** Python 3.12, SQLAlchemy Core, pytest, mypy --strict, ruff.

**Spec:** `docs/superpowers/specs/2026-08-25-b5-run-scoped-rank-attribution-design.md`

## Global Constraints

- **`make check` is the only gate.** Narrow runs use `pytest <path> --no-cov -n 0`.
- **No `artifact_version` bump.** New funnel fields are additive (owner call this session, per D-285).
- **`engine_version` unchanged** — no eligibility/catalog/detect/resolve/engine edit → no ledger drain.
- **The new fields are diagnostics, NOT members of the `considered == Σ drops` reconciliation identity.** Never add them to that sum (they sit beside `uncertain_band`, which is also excluded).
- **Typed violation at the raise site:** the reconciliation miscount raises `ZeroOutputReconciliationError`, never a string-matched or clamped value.
- **Discriminating tests must be shown to FAIL against the old corpus-scoped logic before counting** (a test green against the broken guard is vacuous).
- **Semantic (confirmed by owner):** the four *suppressions* (handled / applied / duplicate / dead) make an empty day honest; *rejections* (hard-filter / non-SWE / over-seniority / below-cutoff) are meant to fire the guard.

---

### Task 1: Run-scoped judged-posting id set (store layer)

**Files:**
- Modify: `src/boardwatch/store/run_funnel_queries.py` (add `posting_ids_judged_this_run`; refactor `count_candidate_judged_this_run` at `:262` to delegate)
- Test: `tests/unit/test_run_funnel_queries.py`

**Interfaces:**
- Produces: `posting_ids_judged_this_run(conn, *, profile_hash: str, rules_hash: str, engine_kind: str, engine_version: str, run_id: int) -> set[int]`
- `count_candidate_judged_this_run(...) -> int` keeps its signature, now returns `len(posting_ids_judged_this_run(...))`.

- [ ] **Step 1: Write the failing test** — the id set equals the ids whose current-identity verdict is a candidate AND run-attributed, and its length equals the existing count.

```python
def test_posting_ids_judged_this_run_matches_count(engine_with_two_runs):
    # fixture: two open postings judged `eligible` by run 7, one `eligible` by run 6,
    # one `ineligible` by run 7. Identity (profile_hash/rules_hash/engine_kind/engine_version) shared.
    with engine_with_two_runs.connect() as conn:
        ids = posting_ids_judged_this_run(
            conn, profile_hash=PH, rules_hash=RH, engine_kind="deterministic",
            engine_version=EV, run_id=7,
        )
        count = count_candidate_judged_this_run(
            conn, profile_hash=PH, rules_hash=RH, engine_kind="deterministic",
            engine_version=EV, run_id=7,
        )
    assert ids == {POSTING_A, POSTING_B}          # run-7 candidates only
    assert POSTING_C not in ids                    # run-6 candidate excluded
    assert POSTING_INELIGIBLE not in ids           # non-candidate excluded
    assert len(ids) == count                        # count delegates to the set
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_run_funnel_queries.py::test_posting_ids_judged_this_run_matches_count --no-cov -n 0 -v`
Expected: FAIL — `posting_ids_judged_this_run` is not defined.

- [ ] **Step 3: Write minimal implementation**

```python
def posting_ids_judged_this_run(
    conn: Connection,
    *,
    profile_hash: str,
    rules_hash: str,
    engine_kind: str,
    engine_version: str,
    run_id: int,
) -> set[int]:
    """Open postings whose CURRENT-identity evaluation is a CANDIDATE verdict (`eligible` OR
    `uncertain`) AND was judged by THIS run — the id-returning form of
    `count_candidate_judged_this_run`. Shares `_current_identity_evaluations` so the count and the
    set cannot drift; the count now delegates here (P3 item 5 / B5)."""
    sub = _current_identity_evaluations(
        profile_hash=profile_hash,
        rules_hash=rules_hash,
        engine_kind=engine_kind,
        engine_version=engine_version,
    ).subquery()
    rows = conn.execute(
        select(sub.c.posting_id).where(
            sub.c.verdict.in_(("eligible", "uncertain")), sub.c.run_id == run_id
        )
    ).scalars().all()
    return set(rows)
```

Then replace the body of `count_candidate_judged_this_run` (keep its docstring/signature) with:

```python
    return len(
        posting_ids_judged_this_run(
            conn,
            profile_hash=profile_hash,
            rules_hash=rules_hash,
            engine_kind=engine_kind,
            engine_version=engine_version,
            run_id=run_id,
        )
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_run_funnel_queries.py --no-cov -n 0 -v`
Expected: PASS (including the pre-existing `count_candidate_judged_this_run` test at `:587`).

- [ ] **Step 5: Commit**

```bash
git add src/boardwatch/store/run_funnel_queries.py tests/unit/test_run_funnel_queries.py
git commit -m "feat(store): add posting_ids_judged_this_run; count delegates to it"
```

---

### Task 2: Ranker run-scoped twin counters

**Files:**
- Modify: `src/boardwatch/cli/top_cmd.py` (`RankedResults` fields; fetch judged set; increment twins in the three suppression `continue` branches at `hidden_duplicate`/`hidden_applied`/`hidden_handled`; populate return)
- Test: `tests/unit/test_top_accounting.py` (the rank counting/accounting module)
- Guard-check: `tests/unit/test_drop_bucket_mirror_sites.py` enforces the drop-bucket mirror sites. The new fields are **diagnostics, not drop buckets** — run this module and confirm it stays green (the twins must NOT appear in the `considered == Σ drops` enumeration). Update the enumeration only if it asserts an exhaustive field list.

**Interfaces:**
- Consumes: `posting_ids_judged_this_run` (Task 1).
- Produces: `RankedResults.judged_this_run_ids: frozenset[int]`, `.hidden_handled_this_run: int`, `.hidden_applied_this_run: int`, `.hidden_duplicate_this_run: int` (all default empty/0).

- [ ] **Step 1: Write the failing test** — a run judging two postings this run, one suppressed as `handled` and one as `duplicate`, plus a prior-run posting also suppressed as `handled`, yields run-scoped twins that count ONLY this-run postings.

```python
def test_rank_twins_count_only_this_run_suppressions(engine_seeded):
    # Seed: postings P1 (judged eligible by run 7, has a live `built` disposition),
    # P2 (judged eligible by run 7, exact_quad duplicate of a survivor),
    # P3 (judged eligible by run 6, has a live `built` disposition).
    ranked = rank_open_postings(engine_seeded, settings, run_id=7, record_surfaced=False)
    assert ranked.judged_this_run_ids == {P1, P2}
    assert ranked.hidden_handled_this_run == 1      # P1 only; P3 is prior-run
    assert ranked.hidden_duplicate_this_run == 1    # P2
    assert ranked.hidden_applied_this_run == 0
    # Corpus counters still see all of it:
    assert ranked.hidden_handled == 2               # P1 + P3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_top_accounting.py::test_rank_twins_count_only_this_run_suppressions --no-cov -n 0 -v`
Expected: FAIL — `RankedResults` has no `judged_this_run_ids` / `hidden_handled_this_run`.

- [ ] **Step 3: Write minimal implementation**

In `RankedResults` (after `hidden_applied`, before `suppressions`), add — with a comment that these are diagnostics OUTSIDE the `considered == Σ drops` identity, like `uncertain_band`:

```python
    # Run-scoped twins of the four SUPPRESSION drops, restricted to postings this run judged
    # (`eligible`/`uncertain`, run_id-attributed). Diagnostics for the B5 zero-output guard —
    # deliberately NOT part of the `considered == Σ drops` reconciliation identity above. `dead`
    # is the runner's liveness fate and lives there, not here.
    judged_this_run_ids: frozenset[int] = frozenset()
    hidden_handled_this_run: int = 0
    hidden_applied_this_run: int = 0
    hidden_duplicate_this_run: int = 0
```

In `rank_open_postings`, after `run_eligibility(...)` has persisted this run's verdicts and before the suppression loop, fetch the set (empty when there is no run):

```python
    judged_this_run: set[int] = (
        posting_ids_judged_this_run(
            conn,
            profile_hash=stats.profile_hash,
            rules_hash=stats.rules_hash,
            engine_kind=ENGINE_KIND,
            engine_version=engine_version(),
            run_id=run_id,
        )
        if run_id is not None
        else set()
    )
```

Reuse the `dedup_conn` block for this query (it is the connection open during suppression resolution), or open one alongside it — do not reuse the first `with engine.connect()` block, which is closed by the time scoring runs (see the existing comment at `top_cmd.py:397`). Initialise `hidden_*_this_run = 0` beside their corpus counterparts, and in the three suppression branches:

```python
        if suppression is not None and not include_duplicates:
            hidden_duplicate += 1
            if posting.posting_id in judged_this_run:
                hidden_duplicate_this_run += 1
            continue
        ...
        if applied_status is not None and not include_applied:
            hidden_applied += 1
            if posting.posting_id in judged_this_run:
                hidden_applied_this_run += 1
            continue
        ...
        if disposition is not None and not include_handled:
            hidden_handled += 1
            if posting.posting_id in judged_this_run:
                hidden_handled_this_run += 1
            continue
```

Add the four new values to the `return RankedResults(...)` mapping (`judged_this_run_ids=frozenset(judged_this_run)`, and the three counts). Import `ENGINE_KIND`, `engine_version`, `posting_ids_judged_this_run`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_top_accounting.py tests/unit/test_drop_bucket_mirror_sites.py --no-cov -n 0 -v`
Expected: PASS. The mirror-site module confirms the corpus `considered == Σ drops` identity is unchanged.

- [ ] **Step 5: Commit**

```bash
git add src/boardwatch/cli/top_cmd.py tests/unit/test_top_cmd.py
git commit -m "feat(rank): run-scoped twin counters for the four suppression drops"
```

---

### Task 3: Guard rewrite + runner wiring + reconciliation invariant

**Files:**
- Modify: `src/boardwatch/pipeline/runner.py` (`_zero_output_guard` at `:562`; new `ZeroOutputReconciliationError`; the guard call site at `:1246-1267`; docstring correction)
- Modify: `src/boardwatch/store/run_funnel_queries.py` (docstring correction at the D-282 site — the guard is no longer dormant)
- Test: `tests/pipeline/test_zero_output_guard.py` (new — guard unit cases) and `tests/pipeline/test_pipeline_run.py` (integration; the ledger-drain honest-day case already lives near `tests/pipeline/test_ledger_advances_the_queue.py`)

**Interfaces:**
- Consumes: `RankedResults.judged_this_run_ids`, `.hidden_handled_this_run`, `.hidden_applied_this_run`, `.hidden_duplicate_this_run` (Task 2); `summary.dead_lead_ids: list[int]` (posting-ids).
- Produces: `ZeroOutputReconciliationError(RuntimeError)`; `_zero_output_guard(candidate_judged_this_run: int, handled_this_run: int = 0, applied_this_run: int = 0, duplicate_this_run: int = 0, dead_this_run: int = 0) -> str | None`.

- [ ] **Step 1: Write the failing tests** — the mixed-day case is the discriminating one (it fires under the new logic but NOT under the old `all-suppressions-zero` logic), plus the honest and invariant cases.

```python
def test_guard_fires_on_mixed_day_with_some_handled():
    # J=5 judged this run; 2 honestly handled-this-run; 3 rejected/lost; 0 leads.
    # OLD guard: hidden_handled != 0 -> returns None (no fire) -> VACUOUS silence. NEW: fires.
    msg = _zero_output_guard(5, handled_this_run=2, applied_this_run=0,
                             duplicate_this_run=0, dead_this_run=0)
    assert msg is not None and "3 of 5" in msg

def test_guard_silent_when_all_this_run_candidates_suppressed():
    assert _zero_output_guard(4, handled_this_run=1, applied_this_run=1,
                             duplicate_this_run=1, dead_this_run=1) is None

def test_guard_silent_on_steady_state_cache_hit_day():
    assert _zero_output_guard(0) is None

def test_guard_raises_on_reconciliation_miscount():
    with pytest.raises(ZeroOutputReconciliationError):
        _zero_output_guard(2, handled_this_run=3)   # twin exceeds J -> counting bug
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/pipeline/test_zero_output_guard.py --no-cov -n 0 -v`
Expected: FAIL — `_zero_output_guard` still takes `(candidate_judged_this_run, hidden_handled, dead_leads, hidden_applied)` and `ZeroOutputReconciliationError` is undefined. Confirm `test_guard_fires_on_mixed_day_with_some_handled` in particular fails against the current body (it returns `None` for a non-zero `hidden_handled`). Import the guard with `from boardwatch.pipeline.runner import _zero_output_guard, ZeroOutputReconciliationError`.

- [ ] **Step 3: Write minimal implementation** — replace the guard body and add the error; rewrite the intro docstring (the guard is armed, corpus-scoped premise removed).

```python
class ZeroOutputReconciliationError(RuntimeError):
    """A run-scoped suppression twin exceeded the this-run candidate count — a counting bug in
    the ranker/liveness attribution, surfaced loudly rather than clamped (P3 item 5 / B5)."""


def _zero_output_guard(
    candidate_judged_this_run: int,
    handled_this_run: int = 0,
    applied_this_run: int = 0,
    duplicate_this_run: int = 0,
    dead_this_run: int = 0,
) -> str | None:
    """P3 item 5 (B5) — 0 leads is provably right IFF every candidate THIS run judged
    (`eligible`/`uncertain`) was either delivered or honestly SUPPRESSED (already built/skipped/
    seen, already applied, a provable duplicate, or gone). All four explainers are RUN-scoped
    (D-282): the corpus-scoped `hidden_*` buckets are an exhaustive partition and can explain any
    empty day, so a clause built from them can never fire. A rejection (hard-filter, non-SWE,
    over-seniority, below-cutoff) is NOT an explainer — a filter or cap that ate the whole
    shortlist is exactly the silent empty day this guard exists to catch (D-246)."""
    unexplained = (
        candidate_judged_this_run
        - handled_this_run
        - applied_this_run
        - duplicate_this_run
        - dead_this_run
    )
    if unexplained < 0:
        raise ZeroOutputReconciliationError(
            f"run-scoped suppression twins ({handled_this_run}+{applied_this_run}+"
            f"{duplicate_this_run}+{dead_this_run}) exceed candidates judged this run "
            f"({candidate_judged_this_run})"
        )
    if unexplained > 0:
        return (
            f"empty day not provably right: {unexplained} of {candidate_judged_this_run} "
            "candidate postings judged this run were neither delivered nor honestly suppressed"
        )
    return None
```

At the call site (`runner.py:1246-1267`), replace the `current_identity`/`count_candidate_judged_this_run` block with the RankedResults-sourced values (single source of truth — the ranker already required a profile, so `ranked` is always present here):

```python
        if summary.fatal is None and not summary.tailored:
            judged = ranked.judged_this_run_ids
            dead_this_run = len(set(summary.dead_lead_ids) & judged)
            summary.fatal = _zero_output_guard(
                len(judged),
                handled_this_run=ranked.hidden_handled_this_run,
                applied_this_run=ranked.hidden_applied_this_run,
                duplicate_this_run=ranked.hidden_duplicate_this_run,
                dead_this_run=dead_this_run,
            )
```

Remove the now-unused `count_candidate_judged_this_run` / `current_identity` imports from `runner.py` ONLY if no other runner site uses them (grep first — `current_identity` is used at `:1497`, so keep it; drop the `count_candidate_judged_this_run` import). Correct the D-282 premise docstring in `store/run_funnel_queries.py::count_candidate_judged_this_run` to note the guard is now armed via `posting_ids_judged_this_run`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/pipeline/test_zero_output_guard.py --no-cov -n 0 -v`
Expected: PASS.

- [ ] **Step 5: Write the integration test** — a full runner pass on a scratch store where this run judges ≥1 eligible posting that is then rejected (below-cutoff or hard-filter) with 0 leads must end `status != ok` with the empty-day fatal; and a ledger-drain pass (all this-run candidates handled) must end `status == ok`.

```python
def test_runner_fatal_on_silent_empty_day(scratch_engine_and_config):
    # Seed one open, eligible-this-run posting whose title is hard-filtered (foreign) so it is
    # rejected, not suppressed; run the pipeline; assert fatal names the empty day.
    summary = run_pipeline(...)
    assert summary.fatal is not None and "not provably right" in summary.fatal

def test_runner_ok_on_ledger_drain_day(scratch_engine_and_config):
    # Seed one open, eligible-this-run posting carrying a live `built` disposition.
    summary = run_pipeline(...)
    assert summary.fatal is None
```

Run: `pytest tests/pipeline/test_pipeline_run.py -k "silent_empty_day or ledger_drain" --no-cov -n 0 -v`
Expected: both PASS (the first FAILS if reverted to the corpus-scoped guard — verify by temporarily restoring the old body).

- [ ] **Step 6: Commit**

```bash
git add src/boardwatch/pipeline/runner.py src/boardwatch/store/run_funnel_queries.py tests/pipeline/test_zero_output_guard.py tests/pipeline/test_pipeline_run.py
git commit -m "feat(runner): arm the B5 zero-output guard on run-scoped attribution"
```

---

### Task 4: Surface run-scoped attribution in the funnel artifact

**Files:**
- Modify: `src/boardwatch/reports/run_funnel.py` (add a `run_scoped_attribution` object to the shortlist stage via `ShortlistCounts` / `build_run_funnel` at `:719`; additive, no version bump — do NOT touch the `reconciled` sum)
- Modify: `src/boardwatch/pipeline/runner.py` where `ShortlistCounts` is populated (thread the four values + `unexplained`)
- Test: `tests/unit/test_run_funnel.py` and `tests/pipeline/test_run_funnel_projection_stage.py`

**Interfaces:**
- Consumes: `ranked.*_this_run`, `ranked.judged_this_run_ids`, `dead_this_run` (Tasks 2–3).
- Produces: funnel shortlist stage key `run_scoped_attribution: {judged, handled, applied, duplicate, dead, unexplained}`.

- [ ] **Step 1: Write the failing test** — the funnel artifact carries the run-scoped object and the corpus reconciliation identity is unchanged. Match the module's existing assertion style (`build_run_funnel(...)` → the serialized dict); a run that judged 3, handled 1 this-run, 0 leads:

```python
def test_funnel_carries_run_scoped_attribution():
    funnel = build_run_funnel(...).to_dict()   # follow the module's existing serialization
    rsa = funnel["shortlist"]["run_scoped_attribution"]
    assert rsa == {"judged": 3, "handled": 1, "applied": 0,
                   "duplicate": 0, "dead": 0, "unexplained": 2}
    # The additive field is NOT in the corpus identity:
    assert funnel["shortlist"]["reconciled"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_run_funnel.py::test_funnel_carries_run_scoped_attribution --no-cov -n 0 -v`
Expected: FAIL — no `run_scoped_attribution` key.

- [ ] **Step 3: Write minimal implementation** — emit the nested object in the shortlist stage projection, computing `unexplained = judged - handled - applied - duplicate - dead`. Do NOT touch the `considered == Σ drops` sum or the `artifact_version` constant.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_run_funnel.py --no-cov -n 0 -v`
Expected: PASS, including the pre-existing funnel reconciliation-identity test.

- [ ] **Step 5: Commit**

```bash
git add src/boardwatch/reports/run_funnel.py src/boardwatch/pipeline/runner.py tests/unit/test_run_funnel.py
git commit -m "feat(funnel): surface run-scoped B5 attribution (additive, no version bump)"
```

---

### Task 5: Full gate + record

**Files:**
- Modify: `docs/program/STATE.md`, `docs/program/METRICS.md`, `docs/program/DECISIONS.md` (index + entry), then `make reindex`

- [ ] **Step 1:** Run the whole gate detached and capture the real exit code:

```bash
nohup sh -c 'export PATH=/opt/homebrew/bin:$PATH; make check > /tmp/b5-check-$$.log 2>&1; echo $? > /tmp/b5-check-$$.done' & disown
```
Gate on the sentinel file, not the launcher. Expected: exit 0.

- [ ] **Step 2:** Append a DECISIONS entry (next D-number) recording that B5 is now scoreable — run-scoped attribution across the four suppression sites + the reconciliation invariant, rejections fire by design (D-246), no `artifact_version`/`engine_version` change. Add its index row; run `make reindex`; confirm `make check`'s program-index gate is green.

- [ ] **Step 3:** Update `STATE.md` (B5 moves from UNSCOREABLE to instrumented; Part 6 certification unblocked for B5) and `METRICS.md`. Write these ONCE, at the end.

- [ ] **Step 4: Commit + open PR** from the worktree branch; do not merge to `main` directly.

```bash
git add docs/program/ && git commit -m "docs(program): record B5 run-scoped attribution (guard armed)"
```

---

## Self-Review

- **Spec coverage:** Task 1 = the id-set query; Task 2 = the four twins (three ranker + the dead intersection lands in Task 3); Task 3 = guard rewrite + invariant + runner wiring + docstring corrections; Task 4 = funnel surfacing; Task 5 = gate + records. LLM-gate boundary and freeze-safety are documented in the spec, no task needed. All spec sections covered.
- **Placeholder scan:** none — every code step carries real bodies; the only prose steps (Task 4 Step 3, Task 5) describe additive edits whose shape is fixed by the tests above them.
- **Type consistency:** `posting_ids_judged_this_run -> set[int]`; `judged_this_run_ids: frozenset[int]`; twins `int`; `_zero_output_guard(...) -> str | None`; `ZeroOutputReconciliationError(RuntimeError)`. `dead_this_run` computed from `set(summary.dead_lead_ids) & frozenset` — both posting-id typed. Consistent across tasks.

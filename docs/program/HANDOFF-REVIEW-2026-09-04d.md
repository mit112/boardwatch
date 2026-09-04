# Handoff for the reviewer of session 2026-09-04d

This session worked `TICKETS-2026-09-04.md` in the owner-ruled order. It is written for **a fresh
reviewer with no memory of the session** — what shipped, what the review that produced the tickets
got WRONG, where the risk actually sits, and what is measured versus assumed.

Read `REVIEW-2026-09-04.md` and `TICKETS-2026-09-04.md` first; this file only records what changed
about them.

---

## What shipped

| # | commit | what it closes |
|---|---|---|
| T1 | `db6807da` | the engine emits its own BEGIN, so a transaction's reads share one snapshot |
| T3 | `e88da1fd` | `(no\|not) (less\|fewer) than` is a comparative floor, not a negation |
| T5 | `b63b3ee9` | `run --queue-root`, and a refusal when only `BOARDWATCH_DATA_DIR` moves the store |
| T4 | `8c2b3ef2` | a bar stated in MONTHS is read and compared on the years axis |
| T2 | see STATE | the résumé renderer fails closed without the personal template |

Each landed in its own worktree with its own `make check`. **A green gate here means exit 2 with
exactly two failures** — `test_fail_closed_on_deeply_nested_json` and
`test_an_unreadable_drafts_directory_could_not_complete`, both environmental (unpinned Python
3.14.7, see STATE's blocker table). Any third failure is a real one.

---

## Three things the review and the tickets got WRONG. Check these first.

**1. Finding 3's stated symptom is not reproducible, and finding 6's direction is wrong.** The
review reports "You must have no less than 5 years of experience" → **`eligible`** against a
one-year profile. Reproduced through the corpus harness's own construction
(`Policy(families=<dict>)`, as `test_eligibility_corpus.py` does) it is **`uncertain` with ZERO
rows**. The defect is real — the bar is not detected at all — but the published verdict is not what
the code does, and `uncertain` versus `eligible` is the difference between "routes to the apply lane
undecided" and "asserted as qualifying".

I can show a mechanism that manufactures spurious `eligible` readings and is live in the same file
the review flags, though I cannot prove it is what happened here: `parse_policy(<the FAMILIES
dict>)` — rather than `{"families": {…}}` — fails validation and **silently returns an empty
`Policy`**. Through that constructor even the CONTROL ("at least 5 years", correctly detected and
`unmet`) reads `eligible`.

**And that is where finding 6's direction is wrong, which matters more than the probe.** The review
says a stray key in the stored JSON "silently abstains every rule on every posting". Measured, the
two halves fail in OPPOSITE directions:

| corrupt | result |
|---|---|
| `eligibility_facts_json` | `uncertain` — every rule abstains. The review is right here. |
| `eligibility_policy_json` | **0 policy families**, which is NOT "nothing blocks" — it is the catalog's DEFAULTS, where `work_auth` is the only `blocker` (D-035) and the other five families are `preference`. |

A `preference` family **can never yield `ineligible`**. So a corrupt policy row silently downgrades
the user's chosen `blocker` on `experience_years`, `degree`, `clearance`, `contract_not_fte`,
`internship` and `student_status`, and postings those families would have rejected read `eligible`.
**That is a clearing failure, not a conservative one.** `preflight.py:296` calls `parse_policy` on
the stored row on every path that produces a verdict, so this is production, not a test path.
**Reviewer: this makes T7 more serious than its "S / cheap+spec" sizing suggests.**

**2. T4's acceptance criterion is impossible as written.** The ticket asks for `"at least 18 months
of professional experience"` with 0 years → **`ineligible`**. 18 months is 1.5 years, which is
**inside `near_miss_years_ceiling: 3`**, so the row resolves `unknown` and the verdict is
`uncertain`. **A months bar under 36 months can only ever resolve `met` or `unknown` — never
`unmet`.** Corpus row `m1039` pins exactly this. In the whole live corpus only the value **48
months (4 occurrences)** can reach `ineligible`.

**3. T2's stated regression surface undercounts its blast radius by roughly 63 tests.** Seven
`tests/pipeline/` files each build their own config-dir fixture (`boardwatch init` + `tailor init`)
and never write `resume_template.tex` — every one of them silently depended on the fallback bug the
ticket kills. The subagent that did T2's first half found this and reported it rather than weakening
the guard to keep them green; a second pass repaired the fixtures. **Reviewer: confirm the repair
made each fixture represent a properly-configured user and did not soften the guard.**

---

## Where the risk is, ranked

**1. T4 moves live verdicts. It is the only ticket here that does.** Measured by A/B over **3,668
open postings pinned by id**, both arms, same ids:

| move | count |
|---|---:|
| `uncertain` → `eligible` | 26 |
| `uncertain` → `ineligible` | 1 |
| `ineligible` → `uncertain` | 1 |
| `eligible` → `uncertain` | 1 |
| postings gaining ≥1 row | 916 |

Rows written: **136 `met` / 7 `unknown`** on the total arm, **1,375 `unknown` / 2 `unmet`** on the
scoped arm. The scoped arm therefore abstains on 99.9% of what it touches. That was a deliberate
call, and the reviewer is entitled to disagree with it: the argument for keeping it is that without
the pattern the posting looks like it states **no bar at all**, which is false, and the one
`uncertain` → `ineligible` move is a real `"48 months of experience in: Java, Kotlin, Python"` bar on
an engineering role — the exact keystone violation the ticket names. The argument against is that
1,377 rows buy 2 decisions.

The single `eligible` → `uncertain` move is a genuine cost: posting 15392 states "Bachelor's … with
1+ years, or Masters/PhD with 3 months", and the scoped arm abstains rather than clearing it.

**2. T4's `implies` reuse puts months rows in the years refinement group, and that has teeth.** The
A/B — not analysis — found that "(i.e., 24-week JCAC course may count as 6 months of experience)"
made a spurious months row **dissolve a genuine "7 years of experience" rejection in the NEXT
sentence** on 10 postings, via the shared group. A unit-scoped `counts? as|toward` guard fixes it;
`m1043` is the control and **fails when the guard is removed** (verified by mutation). Reviewer:
this is the D-388 "a recall pattern can dissolve a decided sibling" class, and it will recur for any
future pattern that reuses an existing `implies`.

**3. T5 adds a refusal that could have broken the daily driver, and did not.** The guard fires when
`BOARDWATCH_DATA_DIR` is set, `--data-dir` was not passed, and `--queue-root` was not passed.
Verified before landing: the launchd plist sets `BOARDWATCH_HEARTBEAT_URL`, `BOARDWATCH_ALERT_URL`
and `PATH` and **does not set `BOARDWATCH_DATA_DIR`**; nothing in the shell profiles exports it
either. The guard is deliberately NOT extended to `--data-dir`, which can reconcile the real queue
just as easily — that is a visible argument rather than an invisible variable, and widening it was
not the ticket.

**4. T1 changes transaction behaviour for every write path in the program.** The gate is the
evidence (9,399 passing). The design decision worth reviewing: the `begin` listener emits
**DEFERRED** by default and IMMEDIATE only via `write_connection`, because emitting IMMEDIATE for
everything would serialise every read in the program against every write. There is a control test
for exactly that (`test_a_deferred_reader_does_not_lock_out_a_writer`) and it fails against the
over-eager version.

---

## What is measured, and what is only argued

**Measured (numbers reproducible from the store, read-only):**

- T3's blast radius: the comparative idiom appears in **58 of 61,927** open bodies, **0** of them a
  years bar (they are lifting weights, driving hours, a vision test in inches). An A/B over exactly
  those 58 moves **0 verdicts and 0 rows**. **T3 closes a class and changes nothing in the current
  corpus.** That is worth stating plainly because it is the honest price of the `rules_hash` re-key.
- T4's A/B, above.
- Every gate result, by exit-code sentinel rather than by the harness's notification (see the trap
  below).

**Argued, not measured:**

- That the scoped months arm's 1,375 abstains are worth keeping (see risk 1).
- That T2's fail-closed direction is right for a **fresh install**: nothing in the product currently
  WRITES `resume_template.tex`, so after this change a new user is refused until they author one.
  That is the correct direction and it is also a **new onboarding step nobody has ruled on**. Flagged
  in STATE rather than decided here.

---

## Traps this session hit, for the next one

1. **A background gate's task notification reports the WRAPPER's exit code.** T1's notification said
   "exit code 0" while the gate's own sentinel said 2. Read the `.exit` file, never the notification.
   (memory `a-background-waiters-exit-code-is-not-the-gates`)
2. **`tail` masks a checker's exit code.** `uv run python -m tools.generalization | tail -5` reported
   `exit=0` while printing an R14 violation. Redirect to a file, then echo `$?`.
3. **A stale `.pyc` served the OLD pin after `fixture_refresh --record`.** The checker quoted a hash
   that existed in no source file. Clear `__pycache__` and `touch` the module.
4. **A mutation that does not change behaviour proves nothing.** The first attempt at T1's
   over-eager-IMMEDIATE mutation edited a line the next branch immediately overwrote; the control
   test "passed" for one cycle for the wrong reason. Confirm the mutant actually behaves differently
   before reading a green test as evidence.
5. **The Bash cwd persists into a worktree.** A `git merge --ff-only` intended for `main` ran inside
   `bw-t3` and reported "Already up to date" — it had merged the branch into itself. Use `git -C`.
6. **Load hit 96 on a 10-core box** with two subagents plus one gate. No gate was corrupted this
   time (checked for `Error 143` / `cannot send` in every log), but the margin was thin.
7. **Adding a pattern moves a rule-count literal in a file you will not think to open.** Memory
   `rules-yaml-and-the-eligibility-corpus-are-content-pinned` names `test_run_funnel`; that file is
   `tests/unit/test_run_funnel.py`, and the sibling `tests/pipeline/test_run_funnel_artifact.py`
   also exists — searching only `tests/pipeline/` found the wrong one and the gate caught the miss
   on its first run. **After moving a shared count, `grep` the WHOLE tree for the OLD literal before
   gating**, rather than trusting a remembered file list. The full set for `experience_years` is
   nine sites: the pattern total, four suppressor-census entries, and five count literals across
   `test_abstain_report.py` (×2), `test_run_funnel_artifact.py` (×2), `test_eligibility_cmd.py`,
   plus `test_run_funnel.py`.

---

## Repo-vs-STATE disagreements found (the repo wins)

- **The launchd plist runs `run --project --top 40`, not `--top 100`.** STATE's "Owed, and
  specifically NOT done" block and memory `boardwatch-run-flags-differ-from-the-daily-driver` both
  say 100. Verified with `plutil -p`.

---

## Two things a reviewer should confirm rather than take on trust

**The ledger drain that `engine_version` normally owes.** The fingerprint moved
`1+bf844e01ebcb` → `1+d89b423701e5`, staling every permanent stamp, and T4 moves verdicts in the
LOOSENING direction — so D-319's test ("can a suppressed decision become less restrictive?") genuinely
applies rather than being waived by argument. It was answered by counting, not reasoning: the ledger
holds **40 rows, all `built`, all from run 2, none reopened, zero `skipped`**. Nothing is suppressed,
so nothing can be released and a drain could only re-deliver the same 40 leads. Re-run the count if
you doubt it: `job_dispositions` grouped by `disposition` and `reopened_at`, read-only.

**That the live config dir survives T2's new guard.** It does — `resolve_template()` was run against
the real `{config_dir}` through the shipped code path and returned a 4,101-character template whose
header carries the owner's actual name. Had it not, the 2026-09-05 04:00 tick would have refused
every lead by design, which is the correct behaviour and would still have been a silent outage to
anyone who had not checked.

---

## What was NOT done

Everything below T5 in `TICKETS-2026-09-04.md` — T6 through T25, and the three speed items SP1–SP3.
The tickets stand as written **except** where corrected above. Note that **T7 is now more
interesting than its "S / cheap+spec" size suggests**: the corrupt-JSON-fails-silent defect it names
is what contaminated D-467's own probe, so it is a defect that has already cost a measurement.

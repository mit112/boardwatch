# Tickets from astra review 03 (identity, liveness, the ledger, dedup, the on-disk queue)

Source: `.agent/astra/findings/03-identity-liveness-ledger-queue.md` (gitignored; the review of
checkout `5040bc4a`, written 2026-09-20). Consumed per STATE 2026-09-19b: all three falsifier
scripts were re-run by the orchestrating session (`03_identity_probes.py`,
`repro_queue_tamper.py`, `repro_partial_watched.py`, exit 0 — **every line reproduced byte for
byte**), and every cited `file:symbol` was opened by a read-only Opus verifier on the enterprise
seat (`.agent/astra/verify/03-report.md`, 84 turns, $4.67). **All seven findings are CONFIRMED
against the code.** Numbering continues the sequence (T113 was the last from review 02).

One PR per wave, `make check` per wave. **Every ticket's acceptance test must FAIL against the
current code before the fix is counted** — and for T114 and T116 the red was re-run INDEPENDENTLY
by the orchestrating session against unchanged `main`, not taken from the executor's report
(9 failed / 120 passed, and 8 failed / 2 passed).

## The finding that matters is NOT the one astra ranked first

Astra marked F1–F5 `wrong-now` and F6 `design-limit`. Measured read-only against the live store on
2026-09-20, **each with a null control**, the ranking inverts:

| finding | astra severity | live population 2026-09-20 |
|---|---|---|
| F1 job membership outlives its evidence | wrong-now | **0 diverged** of 383 multi-posting jobs (28 live dispositions, 2 applications) |
| F2 retired identity generations are read | wrong-now | **0** — the store holds only `p6.3` |
| F3 partial regroup releases a live source | wrong-now | **0** — 535 merge events, all whole-job |
| F4 queue actions stranded by a regroup | wrong-now | **0** — `app_state` holds 0 rows |
| F5 corrupt destination reads `unchanged` | wrong-now | **0** — 1,018 folders, 1,018 hashes and 901/901 PDF digests match |
| **F6 watched-but-unverifiable** | design-limit | **16,510 open postings** under 8 watched boards — 6.3% of the open corpus |

The defects are all real — the falsifiers prove that. But five of the six have no live instance, so
**their tests are the only evidence any fix works**, which is why every ticket below demands a
discriminating red and mutation evidence rather than a green suite.

Null controls that make those zeros real rather than broken probes: F1 — `exact_provider` differs
on all 383 while `exact_quad` agrees on all 383; F3 — the identical join on `to_job_id` returns
383 where `from_job_id` returns 0; F6 — staleness bands under the 8 boards track the all-open
control closely, so these are live rows still being listed, not stale junk.

## Re-key rule

**Nothing in review 03 touches the four digested engine modules or `rules.yaml`.** No ticket below
moves `engine_version`, `rules_hash`, `profile_hash` or `IDENTITY_ALGORITHM_VERSION`; none owes a
ledger drain; none restarts a confirm clock. What T119 moves is ROUTING, which the five-hash
manifest cannot see — the same gap T111 exists to close.

| # | ticket | finding | moves |
|---|---|---|---|
| **T114 SHIPPED** | lane-copy readers filter to the current identity generation | F2 | nothing — latent until the next version bump |
| **T115 SHIPPED** | a regroup may not release a source that still anchors postings, nor strand a queue action | F3 + F4 | regroup repair behaviour only |
| **T116 SHIPPED** | queue sync verifies the destination before reporting it unchanged | F5 | queue only; 0 live folders change |
| **T117 SHIPPED** | the run funnel names the boards no liveness owner can retire | F6 (visibility half) | reporting only |
| **T118 SHIPPED** | detect memberships whose recorded evidence no longer holds | F1 (detection half) | reporting only |
| **T119 SHIPPED** | a built lead whose posting was revised re-enters review | owner ruling | ROUTING |
| T120 | a `repaired` counter on `SyncReport` | T116 open q1 | reporting only |
| T121 | `_install` destroys unrecognised files on the ordinary `updated` path | T116 open q2 | queue write behaviour |
| T122 | `_status` answers "does anything enumerate this board?" with `companies.watched` | this session | rendered posting status |
| T123 | separate inventory completeness from detail-acquisition completeness | F6 (full) | liveness evidence; needs a typed snapshot contract |
| T124 | evidence-scoped job membership with invalidation and reconciliation | F1 (full) | membership schema; needs a migration |
| T125 | evidence-graded cross-job application links | F7 | **measurement first** — not yet a build ticket |
| T126 | `last complete scan age` as a second liveness cohort | T117 not-done | reporting only |
| T127 | `queue_detail` never passes `requirement_flags` | T119 open q1 | pre-existing; pane/list disagreement |
| T128 | three Windows portability bugs, red on `main` for at least two nights | this session's dispatch | test-only |

## What astra got wrong, and what it missed

Recorded so no later session re-derives it.

1. **F2's real cost.** `tests/unit/test_top_lane_copy.py:120` seeded `algorithm_version=1` — an
   int, into a `Text` column — so the lane-copy tests were exercising a RETIRED generation and
   passing only because the reader had no version predicate. **6 of the 11 go red when the
   predicate is added** (verified independently here; the seat verifier said "all 11" and was
   wrong). The other 5 assert the ABSENCE of suppression, which a dead reader also satisfies —
   vacuity from the other direction. `tests/unit/test_delivery_queue.py:2516` seeded the
   `_lane_copy` drain the same way; 2 of its 4 went red.
2. **A false invariant in shipped code.** `store/identity_queries.py:248-252`
   (`count_stale_identities`) justified reaping with "every reader **in this module** filters to
   `IDENTITY_ALGORITHM_VERSION` … Deleting them cannot change any verdict, any suppression, or any
   report." The three readers F2 names sit outside that module. The conclusion survived — deleting
   only removes suppression, the fail-open direction — but the stated reason was false. T114
   corrects the docstring to the property it actually relies on and says the check is a grep.
3. **F6 is fleet-wide.** All twelve providers demote a whole board to `partial` on one per-posting
   parse error. None returns `complete` despite detail failures (the safe direction).
4. **F7 misattributes D-504 twice.** D-504 is the seniority lever, not lane deferral. The decision
   astra meant is **D-506**; D-498 rule (b) has no decision number and is documented only in
   `cli/top_cmd.py:1074-1076`.
5. **A precedent astra did not cite.** `tests/unit/test_leakage_queries.py:152
   test_a_stale_algorithm_version_identity_is_not_counted_as_identified` already fixed this defect
   class on a different reader, and names a fourth deliberately-unfiltered reader
   (`_independent_reconstruction`) that must NOT be changed.
6. **Found here, and sharper than astra's own framing of F6.** `store/delivery_queries.py:343`
   (`_status`) asks "does anything enumerate this board?" and answers it with `companies.watched`,
   which means *configured for scans*, not *enumeration succeeds*. So the 16,510 render as
   verified-`open` while being exactly as unverifiable as the `not watched` class D-314/D-324
   already named. **T122. This is the argument T123 should be built on**, not "expand sweep
   selection".

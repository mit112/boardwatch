# PROGRAM STATE — read this first

**Last updated:** 2026-08-06 (session 1, program takeover)
**Updated by:** boardwatch (Claude)
**Repo state at write time:** branch `main`, clean, HEAD `cb78846`

> This is the single file a fresh session with zero memory reads to know where the program stands.
> If it disagrees with the repo, **the repo wins** — fix this file and note the correction in
> `DECISIONS.md`. Full plan: `PROGRAM.md`. Numbers: `METRICS.md`. Rationale: `DECISIONS.md`.

---

## Current phase

**P0 — Instrumentation. NOT STARTED, APPROVED TO BEGIN.**

Plan approved by Mit 2026-08-06 after independent review (verdict APPROVE WITH CHANGES; all twelve
required changes applied). **Nothing is blocked.** No source file has been modified yet — this session was
analysis, planning and program machinery only.

---

## What shipped this session

Analysis and program machinery only — **zero source changes**.

- Read all seven job-apps handover documents (2,609 lines) in `/Users/mitsheth/dev/Job apps/docs/boardwatch/`.
- Verified job-apps' claims about boardwatch against boardwatch's actual code. job-apps never read this
  repo and said so; four of its factual claims about boardwatch are wrong as a result. See `DECISIONS.md`
  D-002, D-004, D-005, D-006, D-007, D-009 and `PROGRAM.md` §5.
- Wrote `PROGRAM.md`, `STATE.md`, `DECISIONS.md`, `METRICS.md`, and the repo's first `CLAUDE.md`.

**Correction to boardwatch's own record:** the "37 applied folders" figure boardwatch used in
`.agent/plans/p12-parity-report.md` is wrong. job-apps' real figure is **388** `_applied/` folders (369
distinct, 380 with PDFs); 37 was one bucket of its current curated queue. boardwatch's "37 shipped vs 222
targets, and job-apps' applied count is also 37" argument is dead — both halves were coincidence on
job-apps' own numbers. That parity doc is retired by D-008; the file is gitignored working material and
has been left in place, unedited, as a record.

---

## Independent review — 2026-08-06

Reviewed by a fresh agent with no shared context, at Mit's instruction. **Verdict: APPROVE WITH CHANGES.**
Full record in D-013.

Five load-bearing factual claims were attacked: **D-004, D-007, D-009 VERIFIED** · **D-005, D-006
OVERSTATED** (both in boardwatch's own favour — the D-012 failure mode, caught). All twelve required
changes adopted, none contested.

### Worklist from the review

| # | Item | Phase | Status |
|---|---|---|---|
| 1 | Lane-scope D-005; add Tier-B token-provenance validator | P1 (3c) | **corrected in place** |
| 2 | Replace LaTeX `hbox`/`vbox` clause with Typst-native overflow check | P1 (3) | **corrected in place** |
| 3 | `typst` in Dockerfile + loud missing-binary preflight | P1 (3b) | **corrected in place** |
| 4 | `run_id` migration on `eligibility_evaluations` + `artifacts`; cache hit as an asserted stage | P0 | **corrected in place** |
| 5 | B1–B7 → phase → gate traceability table; give B4 an owner; fabrication counters in the funnel (`RewriteRow.drop_reason` already carries the data) | P0 | **closed** |
| 6 | Severity/policy layer into P2 deliverables and §3b's split table; specify which policy P5's labeled set is scored under | P2 / P5 | **closed** |
| 7 | Resolve the P1/P2 ordering inconsistency | P1/P2 | **closed — Mit ratified P1 first 2026-08-06; cost now stated explicitly in §2 rather than denied** |
| 8 | Make P4's blind-craft gate executable — job-apps produces no résumés under `STAGE1_ONLY=1` | P4 | **closed — corpus is job-apps' 392 existing `_applied/` folders** |
| 9 | Restore dropped handover items: sponsorship phrases, cohort completeness, persona registry, fixture-drift discipline, two-OS WAL | P3/P4/P5 | **closed** — persona registry is now P4 item 7; fixture drift is in `CLAUDE.md` |
| 10 | Augment the existing `FileLock` at `scan/coordinator.py:73` rather than replacing it | P3 | **closed** |
| 11 | Tier-B quota + meta-hash idempotence (~300 model calls/day unattended at 2/bullet) | P3 | **closed — P3 item 10** |
| 12 | Commit `docs/program/` and `CLAUDE.md` | — | **closed — committed 2026-08-06; standing permission to commit granted** |

**All twelve closed. The plan is final and approved to execute.**

---

## Next action

**Get approval, then start P0.** First P0 task once approved:

> Alembic migration adding nullable `run_id` to `eligibility_evaluations` and `artifacts`, then emit a
> per-run funnel artifact (`json` + `md`) with stage counts, **per-rule abstain rate**, cache hits as an
> asserted stage, and fabrication-gate counters.

Per-rule abstain is the highest-value single metric in the program: it is what makes a rule that cannot
fire visible as a high abstain rate instead of silently clearing every posting. The migration comes first
because without it three of the seven funnel stages cannot be attributed to a run at all (D-013).

---

## Phase status

| Phase | Status | Gate met? |
|---|---|---|
| P0 Instrumentation | not started | — |
| P1 Résumé artifact gate | not started | — |
| P2 Profile + keystone invariant | not started | — |
| P3 Unattended one command | not started | — |
| P4 Craft gate | not started | — |
| P5 Eligibility decides | not started | — |
| P6 Liveness + dedup | not started | — |
| 14-day acceptance run | not started | — |
| P7 Breadth | not started | — |

---

## Blocked items

| Item | Blocked on | Since |
|---|---|---|
| _(none)_ | | |

---

## Open questions

**None.** All four were answered by Mit on 2026-08-06 — see `PROGRAM.md` §7 and `DECISIONS.md` D-010/D-011.

Summary of the answers, because they carry program-wide weight:

1. **Reading the job-apps repo is authorized, standing.** It was revoked only for the self-assessment
   session so the plan would be honest. Accompanying standing instruction: **check and verify rather than
   assume** — a failed command is not a negative result, a recalled number is not a measured one.
2. **Two personas (SDE / iOS)** with different protected-fact sets, matching Mit's job-apps setup.
3. **`needs_sponsorship: true` for Mit**, declared knowingly and declared per user — never inferred.
4. **`~/boardwatch-applications/<date>/`** stays the daily output home.

Answers 2 and 3 both carry the same governing rule, now `PROGRAM.md` §3b and D-010: **publish the
generalized mechanism, keep Mit's instance local. This applies system wide.**

---

## Standing facts a fresh session should not re-derive

- **Live urgency.** `STAGE1_ONLY=1` is active in job-apps' launchd plist. Its 08:30 run stops after
  discovery. **Nothing is generating Mit's résumés daily right now.** P1 and P3 close a live gap.
- **The tailoring architecture is already correct.** Typed skeleton, plain-text-only model contract,
  Python-owns-markup, independent entailment judge — all present. Do not rebuild it. (`PROGRAM.md` §5.1.)
- **`typst` is installed** at `/opt/homebrew/bin/typst`. "No PDF" is a silent-degrade code path, not a
  missing binary.
- **`track` exists but has never been used** — `applications` and `application_events` are both 0 rows.
- **`jobs` and `postings` are both 19,448** — `job_id` is 1:1, grouping has never run, duplicate leakage
  is structurally unmeasurable until P6.
- **`make check` is the only real gate.** pytest + ruff + mypy green is not green; the generalization
  checker only runs under `make check`.
- **`.agent/` and `.superpowers/` are gitignored** working material. `CHANGELOG.md` is authoritative for
  what shipped.

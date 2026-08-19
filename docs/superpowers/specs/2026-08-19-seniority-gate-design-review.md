# Seniority gate — design self-review

**Date:** 2026-08-19
**Reviews:** two independent passes over `2026-08-19-seniority-gate-design.md` — one **code-reality**
lens (verify every `path:line` claim, find absences), one **doctrine** lens (keystone, multi-tenancy,
program gates). Findings below are consolidated and deduplicated; both reviewers independently
re-derived the measurements against the live store read-only.

**Verdict: the spec is NOT ready to build.** 4 BLOCKERs, 9 MAJORs. It is also not ready for owner
review until the BLOCKERs are resolved, because two of them change what gets built.

**What reproduced cleanly** (so the measurement work is sound): §3.1 baselines exactly
(26,997 / 5,438 `swe` / 10,388 `not_swe` / 11,171 `uncertain` / 6,380 survivors); §3.5 exactly
(30 postings / 24 distinct); §3.3's `Level N`, `L#`, `E#`, `IC#`, `SDE`+roman rows; alembic head
`runs_status_backfill_repair`; both leak titles' verdicts; §6.1's `exclude_titles` inventory.

---

## BLOCKERs

### B1. `reports/notify.py` is a second, independent filter chain — the spec wires only one

`select_new_matches` (`reports/notify.py:70-140`) reproduces the whole chain and already has its own
`include_non_swe` drain (`notify.py:117-128`). `companies.c.name.label("company_name")` is in its
select (`notify.py:92`), so the gate is placeable. As specced, **the notification path keeps pushing
Snap *Level 5* after `top` stops showing it.** The coordinator half lands here free (it lives in
`role_gate`); the seniority half does not.

`reports/stats.py:119` is a third independent `role_verdict` call — `stats` would report a different
population than the funnel.

### B2. No company-name → catalog-key normalization, and its absence fails silently

`top_cmd.py:202` selects `companies.c.name` — the **display** name. The `companies` table carries
both `name` and `slug` (`tables.py:46,48`) and in the live store they diverge:

```
Twilio | twilio                                        | greenhouse
Snap   | snapchat.wd1.myworkdayjobs.com/snapchat/snap  | workday
```

A lookup of `"Snap"` against key `snap` misses. The spec says nothing about casefolding, name-vs-slug,
or multi-word names (`Walmart Global Tech`, `Perplexity AI`). Severe because §4.1 rule 4 makes an
uncatalogued company `uncertain` → **pass-through**: a key-normalization bug makes the whole catalog
inert *and reports nothing* — precisely the "cannot say I don't know, so it says fine" fault §1.1
identifies.

### B3. The `uncertain` band is invisible everywhere — the keystone is NOT satisfied

§4.4 claims the reason is carried onto `why` *"exactly as `role_reason` is for a `not_swe`"*. That is
false about the cited code — `top_cmd.py:271` attaches `role_reason` **only** on `not_swe`, i.e. only
to drained rows. Following §4.4 literally inverts `_why_cell`'s documented invariant
(`top_cmd.py:495-504`): *"Every drain annotates; a normally-visible row is unannotated."*

Three surfaces are missing entirely:

- **The funnel never reports `uncertain`.** `ShortlistCounts` has no such field and §5 adds none.
  §3.1 correctly names the 11,171-posting (41%) fail-open hole as invisible to the funnel — then adds
  a second lane with the same property. CLAUDE.md: *"Abstain rates are reported per rule, every run."*
- **`show <id>` gets no band line**, though `show_cmd.py:150-155` is documented as *"the audit
  surface for the role gate."* A row hidden as `above_band` would have no lookup that explains it.
- **`RankedPosting` gains no `band`/`band_reason`**, and the JSON payload (`top_cmd.py:660-672`,
  which emits `"role"`) gains no `"band"`.

**Fix:** report `uncertain_band` (and `uncertain_role`) as *non-drop* counters through
`RankedResults` → `ShortlistCounts` → the shortlist stage's report block — **not** its `Drop` list,
so the identity still balances. Add `band`/`band_reason` to `RankedPosting` + JSON; annotate in
`_why_cell` for the **drained** row only; add a `Band:` line to `show`.

### B4. `fellow` is a measured false drop, on jobs Mit wants

§4.1 lists `fellow` as a universal senior word. It hits **16 postings** in the 6,380, including three
`role_verdict == swe` rows:

```
Scale AI | SWE Fellow - Human Frontier Collective (US / UK / Canada)
Scale AI | Machine Learning Fellow - Human Frontier Collective
```

A *fellowship* is an early-career program. §4.1 promises *"only a confident word or catalog hit can
drop"*; `fellow` is a homograph. **The word list was never measured the way §3.2 and §3.5 were** —
that is the actual defect. Measure every proposed universal word against the corpus before shipping.

---

## MAJORs

### M1. Multi-tenancy: the tier assignment is backwards and the catalog carries no tier

CLAUDE.md names **seniority** as *profile-dependent* and **title taxonomies** as *field-dependent*.
§4.2 labels `leveling.yaml` *"Universal field-data"* — a category the doctrine does not have — and
ships one flat `words:` map for every user in every field, with no `tier`/`applies_to`/`career_fields`
keys. `eligibility/rules.yaml` has all three precisely because this is what job-apps proved breaks
first when a second user appears.

`fellow`, `principal`, `associate`, `lead`, `director`, `staff` all invert by field: postdoc *Fellow*
is entry; law/consulting *Associate* is entry; *Nurse II* / *Police Officer II* are non-SWE roman
schemes.

**Fix:** universal tier = the numeric-token *mechanism* and the `above_band` comparison. Field tier =
the word→band map and the roman convention, keyed by `career_field`. Unresolvable field ⇒ `uncertain`.

### M2. The catalog is a company enumeration wearing a taxonomy label

§4.2 says register as `kind="taxonomy"` *"(not `company_enumeration` — R8 reserves that…)"*. R8's own
message (`inventory.py:295-306`) reads: *"A personal target list does not become acceptable by being
inventoried."* The `companies:` map is company names with per-company data, and §3.3 is explicit that
membership was chosen by measuring **Mit's** corpus (Snap because 21 hits, Twilio because 14). Every
other `kind="taxonomy"` entry justifies itself with *"Describes the world, not one user."* This one
cannot. **Choosing the label that dodges the check is the evasion `role_gate.py`'s own R9 note
refuses.**

**Fix:** split into a company-free `words`/`schemes` taxonomy plus a company→scheme mapping in the
registry. Do not relabel to pass the checker.

### M3. §5's zero-output-guard decision collides with §6.3's sequencing — and resets Gate P3

§5 correctly refuses to register `over_seniority` in `_zero_output_guard`. The consequence §6.3 never
connects: the guard (`runner.py:378-386`) fires when `eligible_judged_this_run > 0` and
`hidden_handled == dead_leads == hidden_applied == 0`. **The first morning the band filter empties
the shortlist, the guard fires, the run exits non-clean, and Gate P3's 7-consecutive-run count
restarts at 0.** STATE says it is 1 of 7 today.

### M4. Pruning `exclude_titles` is a 2.6× corpus expansion mid-window

Measured: ranker survivors go **6,380 → 16,542** when the seven seniority words are pruned per §6.1.
PROGRAM.md §1: *"Any change to eligibility, profile, or the résumé gate resets it \[the 14-day
clock]… Starting it early and mutating underneath it produces 14 days of uninterpretable data. This
is the single most important program-level scheduling fact."* §6.3 cites neither PROGRAM.md nor
Gate P6's live 7-day dedup window.

### M5. The drain consumes the queue it is draining

`--include-over-seniority` puts rows in `results.visible`; `rank_open_postings` defaults
`record_surfaced=True` and writes a `seen` disposition for every visible row (`top_cmd.py:397-398`).
So inspecting the quarantine suppresses those jobs for `seen_ttl_days` and injects noise into the P6
measurement. **A drain that consumes the queue is a re-entry path that closes behind you.** Pass
`record_surfaced=False` for drained rows; the same fix applies to `--include-non-swe`.

### M6. §3.6's 393 is real but wrong-attributed — and its own example is falsified

Reproduced as 392 / 48 companies. The conclusion does not survive the split:

- **218 of 392 (56%) are `role_verdict == "uncertain"`, not `swe`** — *Data Analyst II*, *Client
  Partner II*, *Learning Specialist II*. These are **role-gate leakage**, suppressed by accident
  because `II` happens to sit in `exclude_titles`.
- A universal roman rule drops them with a **false reason**: `above_band: mid`, when the truth is
  "not a software role." CLAUDE.md requires typed violations at the raise site.
- The spec's original closing sentence — *"a bare roman not adjacent to a role noun (Building
  Attendant II) is left to the role gate, which already handles it"* — is **measurably false**:
  `role_verdict("Building Attendant II") == ("uncertain", "no role signal in title")`. It passes.

**Honest framing:** this is an argument for closing the role gate's `uncertain` lane, not for a
roman-numeral seniority rule. *(The spec's §3.6 was already corrected once, from role-noun-adjacency
to bare matching, after prototyping showed adjacency admits 112 non-software postings. That
correction stands — but the attribution problem above is separate and still open.)*

### M7. Neither the gate nor its catalog enters any version hash

`engine_version()` digests only `("catalog.py","detect.py","resolve.py","engine.py")`
(`eligibility/engine.py:39-57`); `policy_version` = code + config + profile_row + profile_facts +
rules (`pipeline/policy.py:19-45`). **`leveling.yaml` and `seniority_gate.py` sit outside every hash
the program has.** §4.3's own justification for changing `profile_row_hash` — *"omitting it makes the
manifest claim two runs identical when the setting driving a drop bucket changed"* — applies verbatim
to the catalog. This is an internal inconsistency, not a judgement call.

Related: §4.2's "no cache hash needed" argument is correct about `rules_snapshot` but silently
falsifies `manifest.py:22-25`'s *"the one coverage gap that remains… stated so the manifest never
over-claims"*, which the spec neither closes nor amends.

### M8. §4.1 ("compiled once at import") and §4.2 ("config_dir override wins") cannot both hold

`role_gate` compiles at import because its data are module constants. `load_taxonomy` and
`load_rules` are **uncached** and re-read on every call precisely because an override may exist
(verified: neither carries `lru_cache`). The loop runs ~27k times per rank and `role_verdict` was
tuned to 0.30 s over 19,262 postings — a per-row catalog load is a measurable regression.

### M9. The mirror-site count is wrong again — ≥27, not 21

Every `path:line` in §5 items 1–16 verified correct, as did all five test sites and both
"deliberately NOT touched" sites. But:

- §5's list enumerates 15 items + item 12's four call sites = **19**, not the 21 claimed.
- The **3 doc sites** are asserted and never enumerated.
- Missing: `notify.py:128`, `stats.py:119`, `show_cmd.py:153`, `top_cmd.py:65-66`
  (`RankedPosting.role`/`role_reason`), `top_cmd.py:495-504` (`_why_cell`), `top_cmd.py:660-672`
  (JSON `"role"`), both `profile_row_hash` call sites (`pipeline/policy.py:31-38`,
  `pipeline/funnel_writer.py:193-200`), `profile_cmd.py::persist_profile` + `init_cmd.py:71`, and
  `tests/pipeline/test_applied_state_suppression.py:110-145` (a 6th test site).

**The spec's headline — "the count is 21, not 6" — repeats the exact failure mode it is correcting.**
The count is ≥27 and should be stated as a floor, not a total.

---

## MINORs

- **§3.2's denominator is mislabeled.** Measured: 135 postings, **125 distinct titles**, 128 distinct
  (title, company) pairs. "128 distinct titles" and "manual read of all 128" are the title×company
  count. The pattern is sound — 0 `swe` coordinator titles, only 3 tech-adjacent flips — but per
  CLAUDE.md *"a component's self-report is not verification"*: the precision claim is the author
  reading their own pattern's output. Also 3 of the 4 `_NOENG`-spared titles are UT Austin, not CMU.
- **§3.3's `T#` row is unreproducible and understates the point.** `\bT\d\b` → 0; `\bT\d+\b` → **24**
  (Target 23 store codes like *(T0654)*, eBay 1). Under §3.3's own framing this is the *largest*
  looks-like-a-level-and-isn't population in the corpus, and it is reported as 1.
- **§3.6 changes denominator silently** — 393 holds on role-gate survivors *without* `exclude_titles`;
  on §3.3's stated 6,380 population it is 4 postings / 3 companies.
- **R11 has no "count lock."** `check_init_prompts` (`defaults.py:405-434`) is a single tuple
  equality; `tests/generalization/test_defaults.py:354`'s length assertion is a non-vacuity guard.
  R11 *permits* a new init prompt behind a reviewed snapshot update. The conclusion (keep it out of
  `init`) may still be right; the stated reason overstates the rule.
- **§4.3's column shape departs from its own cited precedent.** `p1_resume_max_pages` uses
  `NOT NULL DEFAULT`; adopting that makes `None` unreachable and **dissolves** the null-vs-`"any"`
  hazard §4.3 then spends a paragraph patching.
- **`save_profile`'s new parameter breaks 25 call sites** (1 src, 24 tests) if required, following the
  `resume_max_pages` precedent. §7 doesn't budget for it. If defaulted, `persist_profile` must still
  pass it explicitly or `edit` silently resets the band.
- **The ledger crop is 11 rows.** `job_dispositions` holds 11, all `built`. §4.3 dramatizes an event
  it did not count, in a repo whose doctrine is to measure before asking.
- **No retroactive correction.** Run 61's Snap *Level 5* lead is `built` (permanent) so it won't
  re-surface, but its PDF is on disk and it is counted in METRICS.md for run 61. Worth one sentence.
- **§2 decision 4 oversells.** The coordinator deny closes **135 of the 11,171** fail-open postings —
  1.2%. Nothing in the spec changes the role gate's `uncertain` → pass direction. Say that plainly.
- **The shipped default reproduces the defect for every new user.** Keeping the band out of `init`
  means a fresh install ships with the seniority leak open, while `exclude_titles` — the mechanism it
  replaces — *is* gathered at `init`. If `init` can't ask, say what makes a new user aware.

---

## What this changes about the build

1. **B1/B2/B3/B4 must be resolved in the spec before `writing-plans`.** B1 and B3 change scope
   (three more call sites, a new non-drop counter lane); B2 changes the data model (slug vs name);
   B4 changes the shipped word list.
2. **M1/M2 are owner-facing.** They are doctrine questions — how the catalog is tiered, and whether a
   company map can ship outside the registry — not implementation details.
3. **M3/M4 are scheduling.** The config change resets Gate P3's streak and any live P6 window. That
   is Mit's call and it should be made before, not after, the code lands.
4. **M6 reframes the roman-numeral question** from "what band is `II`" to "why is the role gate's
   `uncertain` lane doing seniority's job", which may be the more valuable fix.

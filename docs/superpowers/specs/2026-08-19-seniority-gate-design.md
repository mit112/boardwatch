# Seniority gate — design

**Date:** 2026-08-19
**Status:** DRAFT — **do not build from this yet.** Self-review found **4 BLOCKERs and 9 MAJORs**;
see `2026-08-19-seniority-gate-design-review.md`. The measurements in §3 reproduce and stand; the
design in §4–§6 needs the BLOCKERs resolved first, two of which change scope. Not yet ready for
owner review either — B1–B4 change what gets built.
**Closes:** D-245 open question 4 ("How to close the two relevance leaks?")
**Records as:** D-246 when the spec lands

---

## 1. What is broken

Run 61 — the first clean unattended run (D-244) — shortlisted eight leads. Two of them were
off-target, and they leaked through two *different* holes:

| Lead | Why it leaked |
|---|---|
| Airbnb — *Disaster Response Coordinator* | `role_verdict()` returns `uncertain` ("no role signal in title"), and the ranker passes `uncertain` through fail-open. Only `not_swe` is dropped. |
| Snap — *Software Engineer, Specs, Level 5* | Seniority is gated **only** by `passes_hard_filters()`'s case-folded substring match against the profile's `exclude_titles`. Mit's list has the words (`Senior`, `Sr`, `Staff`, `Principal`, `Lead`, `Manager`, `Director`, `II`, `III`) but no numeric leveling, so `Level 5` passes. |

Neither hole is in `eligibility/rules.yaml`, and neither should be: role type and seniority are
**rank-time** concerns, and eligibility is blind to them by design. There is no role or seniority
family in the rules catalog (only `work_auth`, `experience_years`, `clearance`, `degree`,
`contract`, `internship`).

### 1.1 The deeper defect

`exclude_titles` is a case-folded **substring** veto. That single mechanism carries three faults at
once, all of them measured below against the live store (26,997 open postings, read-only snapshot):

1. **It over-matches.** `Sr` ⊂ `SRE`, `ISR`, `Israel`. `Lead` ⊂ `Leader`. `Director` ⊂ `Directory`.
2. **It encodes exactly one naming scheme.** Every sibling scheme (`Level 5`, `L5`, `E5`, `SDE III`)
   is invisible to it.
3. **It cannot abstain.** A substring either matches or does not; there is no third answer, so a
   token the mechanism does not understand is silently treated as "fine".

Fault 3 is the one that matters most here, and it is the keystone invariant restated in ranking
terms: *a gate that cannot say "I don't know" reports confidence it does not have.*

---

## 2. Decisions already made by the owner — not re-opened here

These were settled in the 2026-08-19 brainstorm. This spec builds on them; it does not argue them.

1. **Company-relative numeric levels resolve via a CATALOG, with flag-on-unknown.** Universal
   senior *words* drop outright. Numeric levels resolve only against a shipped, versioned catalog of
   **public** company schemes. A catalog **miss** produces `uncertain` → pass-through **flagged**,
   never a silent drop. *(Rejected: a blind numeric floor; and classify-but-never-drop.)*
2. **The target band is an explicit `target_seniority_band` profile field** (`entry|mid|senior|any`),
   **not** derived from `total_years_experience`. "Roles I want" ≠ "experience I have" — the
   distinction is load-bearing for career-switchers.
3. **The fix lives at RANK time** — a new `rank/seniority_gate.py` mirroring `rank/role_gate.py` —
   **not** in `eligibility/rules.yaml`.
4. **A companion fix ships alongside:** a guarded bare-`coordinator` deny in `role_gate`, so
   "… Coordinator" with no software signal flips `uncertain` → `not_swe`.

Decision 1 is **strongly vindicated by measurement** — see §4.2. A blind numeric floor would have
vetoed Cisco's *"Software Development Engineer – Routing Platforms & L2 - Routing, C, L"*, where
`L2` is OSI layer 2, and eBay's *"L2 Support Engineer"*, where `L2` is a support tier.

---

## 3. Measurements

Every number below was produced against a **read-only** snapshot of the live store
(`sqlite3 "file:…/boardwatch.db?immutable=1"`), 26,997 open postings, on 2026-08-19. `doctor` was
not used — it writes.

### 3.1 Baseline populations

| Population | Count |
|---|---|
| Open postings | 26,997 |
| `role_verdict` = `swe` | 5,438 |
| `role_verdict` = `not_swe` | 10,388 |
| `role_verdict` = `uncertain` (**passes through today**) | 11,171 |
| Survives `exclude_titles` + role gate — what a rank-time seniority gate actually sees | **6,380** |

The `uncertain` bucket is 41% of the corpus. That is the size of the fail-open hole the funnel's
"non-SWE dropped" count does not describe.

### 3.2 The coordinator deny — measured precision 128/128

Proposed pattern, appended to `_DENY_BUSINESS_SOFT` (the soft half, which is reached only when the
title carries **no** software signal and **no** rescue match):

```python
_NOENG + r"\bcoordinator\b"
```

`_NOENG` is the existing anchored guard `^(?!.*\b(?:engineer|engineering|developer|architect|
programmer|swe|sde|sdet)\b).*`, so the pattern is guarded twice over.

| Measure | Result |
|---|---|
| Titles flipping `uncertain` → `not_swe` | **135 postings / 128 distinct titles** |
| Of those, genuinely non-software (manual read of all 128) | **128 — precision 128/128** |
| Titles currently `swe` that contain `coordinator` | **0** — the deny cannot bury a software title |
| `coordinator` titles spared by the `_NOENG` guard | 4 |

The 4 spared are administrative roles at engineering schools (*"Administrative Coordinator - College
of Engineering - Electrical and Computer Engineering"*, CMU). They remain `uncertain` and pass —
the fail-open direction, which is correct: the guard errs toward showing a job, never toward
hiding one.

Representative flips: *Disaster Response Coordinator* (Airbnb — the D-245 leak), *Talent
Coordinator* (Palantir), *Workplace Coordinator* (Zillow), *People Ops Coordinator* (Perplexity),
*Global Mobility Coordinator* (Anthropic), *BIM Coordinator / BIM Designer* (OpenAI).

### 3.3 Numeric level tokens — the catalog is small because reality is small

Across the **6,380** titles that reach a rank-time seniority gate:

| Scheme | Postings | Companies | Verdict |
|---|---|---|---|
| `Level N` | 21 | **1** (Snap) | Real. The D-245 leak's family. |
| `L#` | 19 | 6 | **Mostly noise** — 14 Twilio (real levels); Cisco `L2 - Routing` = OSI layer 2; eBay `L2 Support Engineer` = support tier; Target `Facility Attendant L2`. |
| `E#` | 1 | 1 | Noise — Target *"Facility Attendant - E3"*. |
| `T#` | 1 | 1 | Noise — eBay *"Machine Learning Engineer (T25)"*. |
| `IC#` | **0** | 0 | Never appears in a title. |
| `SDE` + roman | **0** | 0 | Never appears in a title. |

**Google `L3–L7`, Meta `E3–E6`, and Amazon `SDE I–III` produce ZERO title hits.** Those companies do
not put the level in the posting title. This is the single most important sizing fact in this spec:

> The catalog's job is **not** to catch levels. It is to **refuse to guess** at tokens that look like
> levels and are not. Its live yield is ~35 postings; its live *protection* is Cisco's routing job.

The catalog still ships the dormant public schemes (Google, Meta, Amazon, Microsoft) because they are
correct, verifiable, universal facts and because a user at a different company mix will hit them.
They are documented as dormant so nobody later "fixes" them by loosening the company scoping.

### 3.4 Snap `Level N` — what the gate would actually do

28 Snap Level-N titles exist. With `target_seniority_band = entry` and Snap catalogued
(`3=entry, 4=mid, 5=senior, 6=staff_plus, 7=staff_plus`):

- **Retained** (`Level 3`, entry): *Software Engineer, Level 3*; *Software Engineer, iOS, Level 3* — 2.
- **Dropped as `above_band`** (`Level 4`/`Level 5`): ~18, including the D-245 leak *Software
  Engineer, Specs, Level 5* and every *Machine Learning Engineer … Level 4/5*.
- Already vetoed today by the words `Senior`/`Staff`/`Principal`: 7 (Level 5/6/7).

### 3.5 Collateral damage of the substring mechanism — 24 distinct titles

Titles where an `exclude_titles` entry fires as a **substring** but **no** entry fires at a word
boundary, and `role_verdict` says `swe`:

**30 postings / 24 distinct titles.** Split:

- **9 genuine `Sr` ⊂ `SRE` / `ISR` / `Israel` false vetoes** — real jobs Mit wants:
  *"Software Engineer - Cloud SRE"* (eBay), *"Software Development Engineer, SRE (US Federal)"*
  (Workday), *"Software Engineer/ SRE (Linux)"* (Visa), *"SRE/Dev Ops Engineer"* (CrowdStrike),
  *"Software Engineer - Figma Weave (Tel Aviv, **Isr**ael)"* (Figma).
- **14 Cisco/Intel/Broadcom `Lead` ⊂ `Leader` vetoes that are CORRECT by accident** — *"Software
  Engineering Technical Leader | C++, Routing protocols, BGP | 10 - 20 years"*. These **are** senior.
- 1 `Director` ⊂ `Directory`, already caught by `Staff`/`Senior`.

**This is a trap, and it drives a design requirement:** a naive `\blead\b` word-boundary fix would
**re-admit 14 genuinely-senior Cisco titles**. The gate's universal word list must therefore include
`leader` (and `technical leader`) as first-class senior tokens — the gate's vocabulary is *not* a
word-boundary copy of the user's `exclude_titles`.

### 3.6 The roman-numeral question — 393 postings ride on it

Bare roman numerals (`II`, `III`, `IV`) on role-gate survivors: **393 postings across 48 companies**
— CrowdStrike 50, Regeneron 35, Pinterest 33, Affirm 31, Instacart 23, Chewy 22.

`Engineer II` / `Engineer III` is a near-universal industry convention, not a company-private scheme.
If roman numerals were catalog-gated like `L5`, then at the 44 uncatalogued companies they would
resolve to `uncertain` → pass, and removing `II`/`III` from `exclude_titles` (§6.3) would admit
**~393 postings** that are dropped today. That is a regression, not a fix.

**Proposed refinement of decision 1** (owner confirmation requested, §8 Q1): treat a **bare** roman
numeral `II` / `III` / `IV`, matched at word boundaries anywhere in the title, as a **universal**
token — `II` = mid, `III`/`IV` = senior — while every **company-prefixed** scheme (`SDE III`, `L5`,
`E5`, `Level 5`, `IC5`, `T4`) stays catalog-gated.

This keeps the spirit of the ruling — *company-relative* levels need a catalog; *universal*
conventions do not — while not regressing 393 postings.

> **Corrected 2026-08-19, after prototyping (§3.7).** This section first proposed requiring the
> roman numeral to sit **adjacent to a role noun** (`Engineer II`). That is wrong, and the prototype
> caught it: role-noun adjacency admits **112 non-software postings** (*Animal Attendant II*,
> *Medical Account Specialist II*, 24 × *Medical Account Specialist II* at Regeneron). The reason is
> worth recording — `II`/`III` in `exclude_titles` were doing **double duty**: suppressing seniority
> *and* silently papering over the role gate's fail-open `uncertain` bucket. Removing them exposes
> everything the role gate was never confident about. Bare matching preserves today's behaviour.

### 3.7 Prototype run — the whole gate, measured end to end

A throwaway prototype of `parse_seniority` + `seniority_verdict` was run over the corpus at
`target_seniority_band = entry`, against the population that would reach the gate **after** the
`exclude_titles` prune of §6.1 (16,542 titles).

| Verdict | Count | Share |
|---|---|---|
| `in_band` | 6,410 | 38.75% |
| `above_band` | 10,124 | 61.20% |
| **`uncertain` (the abstain rate)** | **8** | **0.05%** |

**The abstain rate is the keystone number and it must be reported every run.** All 8 are correct
refusals-to-guess: Cisco's `L2 - Routing`, eBay's `L2 Support Engineer`, Target's
`Facility Attendant L2` / `- E3`, Cerebras' `Bring-up Engineer L2`, Coupang's `[L4]`, and Twilio
`Software Architect (L6)` — a level *outside* Twilio's catalogued range, which is a different
abstain reason from an uncatalogued company and must be reported as such.

**Independent corroboration.** Comparing today's shortlist to the gate's, on the bare-roman rule:

- **Today: 5,483 distinct survivors. With the gate: 5,445.**
- **Gained 23** — including all **9 SRE recoveries** of §3.5 (`Sr` ⊂ `SRE`/`ISR`/`Israel`). The
  remaining 14 are non-software noise the substring list was killing by accident; they are the
  role gate's problem, and the fail-open direction.
- **Lost 61 — every one correctly senior, and every one leaking TODAY.** 21 × *Distinguished
  Engineer* (Capital One, NVIDIA, Roblox, Marvell, Salesforce, Pinterest, Datadog), ~15 ×
  *Vice President* / *VP* software roles (Citi, BlackRock — *"Full Stack Engineer, Vice President"*),
  plus `IV` titles.

**`Distinguished` and `Vice President`/`VP` are in NO current `exclude_titles` entry.** This is an
unbudgeted win: 36+ senior postings that leak into the shortlist today are closed by the gate's
universal word list, entirely separate from the numeric-level work that motivated it.

Two independent measurements agree: §3.5 found 30 postings wrongly vetoed by substring, and the
survivor delta here is +23/−61 — the same population, counted a different way.

---

## 4. Design

### 4.1 New module — `src/boardwatch/rank/seniority_gate.py`

Mirrors `rank/role_gate.py` in shape and in discipline: ordered patterns built with `tuple([...])`
constructor calls, compiled once at import, and **every non-pass verdict carries the text that
decided it**. A gate you cannot audit is how a real job disappears.

```python
SeniorityBand   = Literal["entry", "mid", "senior", "staff_plus"]
TargetBand      = Literal["entry", "mid", "senior", "any"]
SeniorityVerdict = Literal["in_band", "above_band", "uncertain"]

def parse_seniority(title: str, company: str, catalog: LevelingCatalog
                    ) -> tuple[SeniorityBand | None, str]: ...

def seniority_verdict(title: str, company: str, target_band: TargetBand,
                      catalog: LevelingCatalog) -> tuple[SeniorityVerdict, str]: ...
```

**Resolution order** (first match wins, and the order is load-bearing exactly as in `role_gate`):

1. **Universal senior words**, matched `\bword\b` — `senior`, `sr\.?`, `staff`, `principal`,
   `distinguished`, `fellow`, `lead`, **`leader`**, `head of`, `manager`, `director`, `vp`,
   `vice president`. → the word's band.
2. **Universal role-noun + roman numeral** (§3.6) → `I`=entry, `II`=mid, `III`/`IV`=senior.
3. **Company numeric scheme**, only when `company` resolves in the catalog **and** the token's scheme
   is the one that company declares. → the catalog's band for that level.
4. **Numeric-looking token present, but the company is not catalogued, or declares a different
   scheme** → `uncertain`, carrying the matched text.
5. **No token at all** → `in_band`. Absence of signal is never a drop.

**Verdict:** bands order `entry < mid < senior < staff_plus`. `above_band` iff the parsed band is
**strictly greater** than the target. `target_band == "any"` ⇒ always `in_band`, and the gate reports
itself **inert** rather than staying silent.

**Fail direction, keystone-aligned:** only a confident word or catalog hit can drop. `uncertain`
passes and is flagged. An unset target passes and is reported.

### 4.2 New catalog — `src/boardwatch/rank/leveling.yaml`

Universal field-data: public, verifiable, identical for every user. Shape:

```yaml
leveling_version: 1
words:
  senior: senior
  sr: senior
  staff: staff_plus
  principal: staff_plus
  leader: senior
  # …
companies:
  snap:
    scheme: level_n          # "Level N"
    levels: {"3": entry, "4": mid, "5": senior, "6": staff_plus, "7": staff_plus}
  twilio:
    scheme: l_prefix         # "L2"
    levels: {"1": entry, "2": entry, "3": mid, "4": senior, "5": staff_plus}
  google:                    # DORMANT: 0 title hits measured 2026-08-19. Kept because it is
    scheme: l_prefix         # a correct public fact and a different user's corpus will hit it.
    levels: {"3": entry, "4": mid, "5": senior, "6": staff_plus, "7": staff_plus}
  # meta (E3-E6), amazon (SDE I-III), microsoft (59-65) — likewise dormant
```

**Loader** (`rank/leveling.py`), following the `eligibility/catalog.py` + `extract/taxonomy.py`
convention exactly:

- `files("boardwatch.rank") / "leveling.yaml"`, `yaml.safe_load`, with a
  `{config_dir}/leveling.yaml` override that wins.
- **Closed vocabulary, raise-not-bucket:** any band outside `entry|mid|senior|staff_plus`, any
  `scheme` outside the declared set, or any level key that is not a string ⇒ `LevelingError`. An
  out-of-catalog value is a failure, never a new bucket.
- **YAML 1.1 boolean defence** (the repo's hard-earned convention, `catalog.py:200-208`): every
  scalar is `isinstance(x, str)`-checked at load, because an unquoted `no`/`on`/`y` becomes a bool
  and then a plausible-looking token. Level keys are quoted strings.
- **`leveling_version` is VALIDATED against a module constant**, following
  `profile_bundle/predicate_catalog.py:79-91` — *not* the dead decorative `version:` key that
  `eligibility/rules.yaml` and `extract/taxonomy.yaml` carry and never read.
- **No cache hash needed.** `rank/heuristic.py`'s header states ranking persists nothing and
  "invalidation is a non-problem by construction". The catalog feeds ranking only, never an
  eligibility verdict, so it does **not** enter `rules_snapshot`. Putting it there would re-key every
  stored verdict for nothing.

**Generalization (R7/R9/R12) obligations — confirmed against `tools/generalization/`:**

- R7 **will** flag the new file. It needs an entry in `tools/generalization/allowlists.py`:
  `kind="taxonomy"` (**not** `company_enumeration` — R8 reserves that for `registry/companies.yaml`
  and allows exactly one), plus reason, provenance and a `pin="sha256:…"` re-pinned on every edit.
- `git add` it before running `make check`: the checker enumerates via `git ls-files`, so an
  untracked catalog is invisible to R7 and the gate passes falsely.
- R12 builds a real wheel and diffs members. Hatchling ships everything under the package root with
  no `package-data` entry, so `rank/leveling.yaml` is packaged automatically — **no pyproject change.**
- `seniority_gate.py` goes into `SCOPED_MODULES` and builds its tuples with `tuple([...])`, for the
  same reason `role_gate.py` does: moving title data to an unscoped module is the evasion R9 exists
  to catch. Note R9 also flags **dict keys**, so any word→band map in the module must be a
  constructor call or live in the YAML (it lives in the YAML).

### 4.3 New profile field — `target_seniority_band`

`entry | mid | senior | any`, default `any` (gate inert, backward-compatible, reported).

- **Column:** `Text`, nullable, `server_default="any"`. No DB `CHECK` — the house rule
  (`tables.py:227-229`) is that closed enums are enforced in Python at the write site, because
  retrofitting a CHECK to SQLite costs a full table rebuild.
- **Migration:** one additive `ALTER TABLE profile ADD COLUMN`, `down_revision =
  "runs_status_backfill_repair"` (verified current head), native `DROP COLUMN` on downgrade —
  modelled on `p1_resume_max_pages.py`.
- **Validation:** `SeniorityBand = Literal[...]` on `ProfileInput`, the house pattern
  (`settings.location_filter_mode`, `facts.PolicyChoice`).
- **`save_profile`** needs the field in **all three** of signature, `.values()` and the `set_` map.
  Omitting it from `set_` means `profile edit` silently never updates it — the exact defect the
  `save_eligibility` docstring warns about.
- **CLI:** prompt in `profile edit` and print in `profile show`. **Deliberately NOT in `init`** —
  following the `resume_max_pages` precedent, because a new `typer.prompt` in `init_cmd.py` trips
  R11's `EXPECTED_INIT_PROMPTS` snapshot plus its count lock, and R11's stated purpose is that every
  profile/filter prompt stays empty. A defaulted band in `init` is arguably the "one user's answer
  shipped to all" shape that rule exists to catch. `any` is the safe default; `edit` is where a user
  narrows it.

**Hashing — two hashes, and they behave differently. This was verified, not assumed:**

| Hash | Effect | Why |
|---|---|---|
| `eligibility/hashing.py::profile_hash` | **UNCHANGED** | It is built exclusively from `Facts` (`profile.eligibility_facts_json`), narrowed to fields declared by non-ignored rule families, plus `career_field`. It never reads `profile` table columns. Cached eligibility verdicts and cached LLM extractions stay valid — **no re-judging, no re-spend.** |
| `reports/manifest.py::profile_row_hash` | **MUST CHANGE** | It hashes the profile columns the ranker reads, and this field drives a funnel drop. Omitting it makes the manifest claim two runs identical when the setting driving a drop bucket changed. |

Consequence of the second, stated plainly: `policy_version` is a digest over `profile_row`, so
**every existing ledger disposition's stamp changes and reads as stale** on the first run after this
ships. That is documented, intended behaviour — a stamp mismatch never re-opens a disposition on its
own; `ledger show --stale` lists them and `ledger reopen` releases them. It is a one-time event and
it must be called out in the CHANGELOG.

**Null-vs-`"any"` hazard:** `hashing.canonical` deliberately distinguishes an explicit null from a
missing key. `None` and `"any"` mean the same thing behaviourally, so they must be **normalized to
`"any"` before hashing**, or one behaviour yields two `profile_row_hash` values and two
`policy_version` stamps.

### 4.4 Ranker wiring — `cli/top_cmd.py`

Beside the role gate, after `passes_hard_filters`, before scoring:

```python
role, role_reason = role_verdict(row.title)
if role == "not_swe" and not include_non_swe:
    hidden_non_swe += 1
    continue
band, band_reason = seniority_verdict(row.title, row.company_name, target_band, catalog)
if band == "above_band" and not include_over_seniority:
    hidden_over_seniority += 1
    continue
```

`uncertain` passes and its reason is carried onto the `RankedPosting.why` string, exactly as
`role_reason` is for a `not_swe`. Drain flag: `--include-over-seniority`.

---

## 5. The mirror-site count is 21, not 6

`top_cmd.py:83-107` documents *"a new drop bucket has SIX hand-maintained mirror sites"*, a number
two successive reviews already corrected upward. **It is wrong again.** A full trace of the existing
`hidden_non_swe` bucket finds **21 code sites + 5 test sites + 3 doc sites**. Updating that docstring
is itself one of the 21.

**Code:**

1. `top_cmd.py:83-85` — the reconciliation identity **prose** in `RankedResults`' docstring.
2. `top_cmd.py:96-107` — the "SIX mirror sites" paragraph. **Correct the count a third time.**
3. `top_cmd.py:112` — the `RankedResults` dataclass field.
4. `top_cmd.py:237` — counter initialisation.
5. `top_cmd.py:255-259` — the increment + `continue`.
6. `top_cmd.py:167` — `rank_open_postings` signature (`include_over_seniority`).
7. `top_cmd.py:399-415` — the `return RankedResults(...)` mapping.
8. `top_cmd.py:517-525` — `_print_hidden_notices` signature.
9. `top_cmd.py:544-549` — the drain notice.
10. `top_cmd.py:690` — **the empty-result early-return guard.** Not in the docstring's list of six,
    and it has already swallowed two buckets historically. A run whose postings were all dropped as
    over-seniority would otherwise print *"no open postings match your filters"* — an assertion that
    the corpus is empty.
11. `top_cmd.py:597-599` — the `--include-over-seniority` typer option.
12. `top_cmd.py:633, 654, 701, 725` — **four** separate call sites threading the flag.
13. `pipeline/runner.py:673-684` — `RankedResults` → `ShortlistCounts`.
14. `reports/run_funnel.py:216-235` — the `ShortlistCounts` field.
15. `reports/run_funnel.py:719-770` — the **shortlist** stage `Drop`.
16. `cli/run_cmd.py:24-43` — `_shortlist_line`, the operator's one-line summary.

**Deliberately NOT touched, and the reasoning is recorded so it is not "fixed" later:**

- **`pipeline/runner.py:342-390` `_zero_output_guard` — NO.** A bucket registers there only if it can
  *legitimately explain an empty day* — postings that were lead-worthy but suppressed by external or
  temporal state (already handled, already applied, gone). `over_seniority` is a **rejection**, not a
  suppression, exactly like `hidden_non_swe` and `hidden_hard_filter`, neither of which is registered.
  Registering it would **weaken** the guard: a run whose band filter ate everything would exit 0
  silently — the silent empty day in a new costume.
- **`run_funnel.py:910-930` the TAILOR stage `Drop` — NO.** That stage carries a drop only for
  buckets that remove postings *after* ranking (liveness). `over_seniority` drops *during* ranking,
  so adding it there would double-subtract and report a healthy run unbalanced.
- **`funnel_to_dict` / `funnel_to_markdown` — no change.** Both iterate `stage.drops` generically.

**Reconciliation.** The shortlist stage's identity is `considered == shortlisted + Σ Drop.count`,
`derived=False`, so it can genuinely fail. The ranker-side twin at `top_cmd.py:83-85` must gain the
new term. There is **no closed catalog of drop-reason strings** — `Drop.reason` is a bare `str` — so
nothing refuses a typo'd bucket name. That absence is why the checklist above is exhaustive rather
than trusted to a validator.

**Tests:**

17. `tests/unit/test_top_accounting.py:109-120` — `_accounted()` hand-summed identity.
18. `tests/unit/test_top_duplicates.py:105-120` and `:173-190` — two more independent hand sums.
19. `tests/unit/test_run_funnel.py:90-170` — the `funnel()` helper: the kwarg, **the default
    `considered=` balance**, and the `ShortlistCounts(...)` pass-through. Missing the middle one makes
    every unrelated funnel test fail as unbalanced.
20. `tests/unit/test_run_funnel.py:513-545` — the markdown drop-reason test; add the bucket with a
    **distinct non-zero** count (a zero makes the assertion blind).
21. `tests/pipeline/test_liveness_withholds_dead_leads.py:381-399` — the **only** guard on
    `_shortlist_line`. Nothing else catches a miss there.

---

## 6. Consequences the owner should see before this is built

### 6.1 The word half of the gate is inert until `exclude_titles` is edited

`passes_hard_filters` runs **before** the role gate and before the new seniority gate. Mit's
`exclude_titles` already strips `Senior`/`Sr`/`Staff`/`Principal`/`Lead`/`Manager`/`Director`/`II`/
`III` by substring. So on day one the new gate's **word** and **roman** rules will see almost nothing
— they have already been removed — and the gate's only live contribution is Snap `Level 4/5`
(~18 postings) and Twilio `L#`.

**The `Sr` ⊂ `SRE` fix (9 real jobs, §3.5) does not happen automatically.** It requires removing the
seniority words from `exclude_titles`, leaving only the genuinely role-based entries (*Field Service
Engineer*, *Mechanical Engineer*, *Hardware Engineer*, *Sales Engineer*, *Control Systems Engineer*,
*Service Technician*, *Field Engineer*).

That edit is `boardwatch profile edit` — **interactive, TTY-only, and Mit's to run.** It must happen
**after** the gate ships, or Mit gets one day of unfiltered senior titles.

### 6.2 With `target_seniority_band = entry`, `mid` drops

`above_band` is *strictly greater than* the target, so at `entry` a `Software Engineer II` is dropped.
This matches Mit's existing `exclude_titles` (which already excludes `II` and `III`) and matches
new-grad targeting. Stated explicitly because it is the kind of thing that is obvious now and
surprising in three months.

### 6.3 Sequencing

1. Ship the gate + catalog + profile field, default `any` ⇒ **behaviour is unchanged**, gate reports
   inert. Verify a clean run.
2. Mit sets `target_seniority_band = entry` via `profile edit`.
3. Mit prunes the seniority words from `exclude_titles` in the same `profile edit`.
4. First run after: expect the `policy_version` re-key (§4.3) and a one-time crop of stale ledger
   dispositions.

Steps 2–4 are one TTY session. Gate P3 is accruing clean runs, so this should land on a day Mit can
watch the 8 AM fire — a config change mid-accrual is worth doing deliberately.

---

## 7. Testing

- **Parser units:** `Sr` does not match `SRE`/`ISR`/`Israel`; `leader` parses as senior; role-noun
  roman numerals parse; a bare `II` not adjacent to a role noun does not.
- **Verdict units:** catalog hit → band; catalog **miss** → `uncertain` (Cisco `L2 - Routing` is the
  named regression test); no token → `in_band`; `target=any` → inert **and reported**.
- **Catalog units:** closed-enum violation raises; unquoted YAML-1.1 boolean raises;
  `leveling_version` mismatch raises.
- **Profile:** migration up/down; `server_default` on an existing row; `profile edit` round-trips the
  value (the `set_`-map defect); `profile_row_hash` tracks the field and the pinned parameter-set
  assertion in `tests/unit/test_profile_resume_max_pages.py:61` is updated; `profile_hash` is proven
  **unchanged**.
- **Coordinator deny:** measured against the live corpus per `role_gate`'s docstring discipline —
  128/128 precision, 0 `swe` titles affected, recorded in the module comment the way every other
  narrowing in that file is.
- **Behaviour test over run 61's real titles:** Snap *Level 5* drops once Snap is catalogued; Airbnb
  *Disaster Response Coordinator* → `not_swe`; the other **6 leads are retained** — including
  Affirm's *"Software Engineer I, Backend (Collections)"*, whose roman `I` must parse as **entry**,
  not be mistaken for a higher level.
- **`make check` green.** It is the only gate; run it in plain mode, never piped through `head`/`tail`.

---

## 8. Open questions for the owner

1. **Roman numerals: universal or catalog-gated?** §3.6. Catalog-gating them regresses ~393 postings
   at 44 uncatalogued companies. Recommendation: universal when adjacent to a role noun; company
   schemes stay catalogued. *This refines decision 1 rather than contradicting it — confirmation
   wanted, not a re-litigation.*
2. **Does `mid` drop at `target=entry`?** §6.2. Recommendation: yes, strictly-greater — it matches
   the current `exclude_titles` behaviour.
3. **Is the one-time `policy_version` re-key acceptable?** §4.3. It is unavoidable if the band is a
   ranking input, and it is the documented, recoverable path (`ledger reopen`).

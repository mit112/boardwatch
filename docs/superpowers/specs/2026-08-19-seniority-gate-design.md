# Seniority gate — design (revision 2)

**Date:** 2026-08-19
**Status:** revised after self-review — **ready for owner review**
**Closes:** D-245 open question 4 ("How to close the two relevance leaks?")
**Records as:** D-246 when the spec lands

**Revision 2 resolves all 4 BLOCKERs and 9 MAJORs** raised in
`2026-08-19-seniority-gate-design-review.md`. The review doc is kept as-is; where a finding changed
the design, the section says so. Two changes are structural: the catalog no longer contains company
names (§4.2), and the gate now reports its abstain rate (§4.5).

---

## 1. What is broken

Run 61 — the first clean unattended run (D-244) — shortlisted eight leads. Two were off-target, and
they leaked through two *different* holes:

| Lead | Why it leaked |
|---|---|
| Airbnb — *Disaster Response Coordinator* | `role_verdict()` returns `uncertain` ("no role signal in title"), and the ranker passes `uncertain` through fail-open. Only `not_swe` is dropped. |
| Snap — *Software Engineer, Specs, Level 5* | Seniority is gated **only** by `passes_hard_filters()`'s case-folded substring match against the profile's `exclude_titles`, which has the words but no numeric leveling. |

Neither hole is in `eligibility/rules.yaml`, and neither belongs there: role type and seniority are
**rank-time** concerns and eligibility is blind to them by design.

### 1.1 The deeper defect

`exclude_titles` is a case-folded **substring** veto carrying three faults at once:

1. **It over-matches.** `Sr` ⊂ `SRE`, `ISR`, `Israel`. `Lead` ⊂ `Leader`. `Director` ⊂ `Directory`.
2. **It encodes exactly one naming scheme.** `Level 5`, `L5`, `E5`, `SDE III` are invisible to it.
3. **It cannot abstain.** A substring matches or does not; there is no third answer, so a token the
   mechanism does not understand is silently treated as fine.

Fault 3 is the keystone invariant in ranking terms: *a gate that cannot say "I don't know" reports
confidence it does not have.*

### 1.2 Scope honesty (review MINOR)

The coordinator deny closes **135 of the 11,171** fail-open `uncertain` postings — **1.2%**. Nothing
here changes the role gate's `uncertain` → pass direction. This spec closes one instance of one leak
and makes the other measurable; it does not close the role gate's fail-open lane. §8 Q2 asks whether
that lane is the next piece of work — the measurements in §3.6 argue it is.

---

## 2. Owner decisions

Settled in the 2026-08-19 brainstorm and confirmed during this revision. Not re-argued here.

1. **Numeric levels resolve via a CATALOG with flag-on-unknown.** Universal senior *words* drop
   outright; numeric levels resolve only against a versioned catalog. A **miss** ⇒ `uncertain` ⇒
   pass-through **flagged**, never a silent drop.
2. **Target band is an explicit `target_seniority_band` profile field** (`entry|mid|senior|any`), not
   derived from `total_years_experience`.
3. **The fix lives at RANK time**, not in `eligibility/rules.yaml`.
4. **A guarded bare-`coordinator` deny** ships alongside in `role_gate`.
5. **Catalog tiering** (2026-08-19): the *mechanism* is universal; the *word→seniority meanings* are
   **field-tiered**, keyed to career field, defaulting to software. An unresolvable field abstains.
6. **The streak is not a constraint** (2026-08-19): the design still ships inert-by-default, because
   that is correct for every other user — but nothing is sequenced around protecting Gate P3.

### 2.1 One owner decision could not be built as chosen — and why

Decision: *"company→scheme mapping goes into the existing board registry."* **This is not
buildable**, and the reason is worth recording:

- `registry/companies.yaml` is a **37-entry seed catalog**; `CompanyEntry` is
  `ConfigDict(extra="forbid")` (`registry/validate.py:20`).
- The live `companies` table has **135 rows**. **Snap, Twilio and Google are not in the registry** —
  they are boards the operator added. Snap's `slug` is `snapchat.wd1.myworkdayjobs.com/snapchat/snap`.
- So adding Snap to the shipped registry to give it a leveling scheme is *precisely* the
  "personal target list" R8 refuses (`inventory.py:295-306`).

**Resolution, and it is better than either original option** (§4.2): ship the **schemes** as
company-free universal data, and put the **company→scheme binding in user config**, where a
per-user company list already legitimately lives. Shipped data then contains **zero company names**,
so R7/R8 are satisfied honestly rather than by relabelling.

---

## 3. Measurements

All numbers from a **read-only** snapshot of the live store (`sqlite3 "file:…?immutable=1"`), 26,997
open postings, 2026-08-19. `doctor` was not used — it writes. Every figure below reproduced under
independent re-derivation by a second reviewer except where noted as corrected.

### 3.1 Baseline populations

| Population | Count |
|---|---|
| Open postings | 26,997 |
| `role_verdict` = `swe` | 5,438 |
| `role_verdict` = `not_swe` | 10,388 |
| `role_verdict` = `uncertain` (**passes through today**) | 11,171 |
| Survives `exclude_titles` + role gate | 6,380 |
| Survives after the §6.1 `exclude_titles` prune | 16,542 |

The `uncertain` bucket is **41%** of the corpus — the size of the fail-open hole the funnel's
"non-SWE dropped" count does not describe. §4.5 makes the new gate's equivalent hole *reported*
rather than repeating that mistake.

### 3.2 The coordinator deny

Pattern appended to `_DENY_BUSINESS_SOFT` (reached only when the title has **no** software signal and
**no** rescue match), guarded twice over by the existing `_NOENG` anchor:

```python
_NOENG + r"\bcoordinator\b"
```

| Measure | Result |
|---|---|
| Titles flipping `uncertain` → `not_swe` | **135 postings / 125 distinct titles / 128 distinct (title, company)** |
| `swe`-classified titles containing `coordinator` | **0** — the deny cannot bury a software title |
| Spared by the `_NOENG` guard | 4 (three UT Austin, one CMU) |
| Tech-adjacent among the flips, on independent read | 3 (two Lucid physical-security/compliance, one UT Libraries data role) |

*Corrected from revision 1:* the headline "128 distinct titles" was the distinct **(title, company)**
count; distinct titles is **125**. Revision 1 also mis-attributed the spared titles to CMU.

Per CLAUDE.md — *"a component's self-report is not verification"* — the precision claim is the author
reading their own pattern's output. It was re-derived independently and the `0 swe` result is the
load-bearing half: the deny **cannot** hide a software job, whatever one thinks of the 3 edge cases.

### 3.3 Level grammars — self-describing vs ambiguous

This is the measurement that drove the §4.2 redesign. Over the whole corpus:

**Self-describing grammars** (the token names itself a level):

| Grammar | Postings | Companies | Every hit a real level? |
|---|---|---|---|
| `Level N` | 33 | 3 (Snap 29, Thomson Reuters 3, Disney 1) | **Yes** |
| `SDE` + roman/arabic, `Grade N`, `Band N` | **0** | 0 | — (never appear) |

**Ambiguous bare-letter grammars:**

| Grammar | Postings | Companies | What they actually are |
|---|---|---|---|
| `L#` | 45 | 11 | Mostly **not** levels — Cisco *"& L2 - Routing"* (OSI layer 2), eBay *"L2 Support Engineer"* (support tier), Target *"Facility Attendant L2"*, Inovalon 10 |
| `T#` | 2 | 2 | eBay *"(T25)"*, Marvell *"T4 - Hardware…"* |
| `E#` | 1 | 1 | Target *"Facility Attendant - E3"* |
| `IC#`, `P#`, `M#` | 0 | 0 | Never appear |

Two conclusions, and they are different:

1. **`Level N` is unambiguous as a grammar** — every hit really is a level. But its **band meaning is
   company-relative**: Snap `Level 5` is senior; Disney *"Creative Venue Technician Apprentice
   (Level 3)"* is a trade rung with no software meaning at all. Grammar and band must be separated.
2. **Bare-letter grammars are not levels and must never resolve.** A blind numeric floor would veto
   Cisco's routing job. This is decision 1 vindicated by data.

**Google `L3–L7`, Meta `E3–E6`, Amazon `SDE I–III` produce ZERO title hits.** Those companies do not
put levels in titles. Any catalog entry for them would be dormant decoration — a further argument
against shipping a company list at all.

*Corrected from revision 1:* the `T#` row said 1 posting; `\bT\s?-?\d{1,3}\b` gives 2, and a looser
`\bT\d+\b` gives 24 once Target store codes (*(T0654)*) are included. Revision 1's §3.3 also mixed
denominators — it reported some rows against the 6,380 population and some against the corpus.

### 3.4 Universal word list — every word measured (review BLOCKER B4)

Revision 1 proposed a word list that was never measured, unlike the other two rules. Measured against
the 16,542 population, hits and `swe`-classified drops:

| Word | Hits | `swe` | Ruling |
|---|---|---|---|
| `senior` | 3,508 | 1,588 | **ship** → senior |
| `staff` | 1,615 | 1,156 | **ship** → staff_plus |
| `manager` | 2,648 | 199 | **ship** → senior |
| `director` | 973 | 45 | **ship** → staff_plus |
| `lead` | 953 | 190 | **ship** → senior |
| `sr\.?` | 934 | 327 | **ship** → senior (word-boundary; kills `Sr`⊂`SRE`) |
| `principal` | 660 | 261 | **ship** → staff_plus |
| `leader` | 164 | 22 | **ship** → senior (see §3.5 — required, not optional) |
| `vp` | 43 | 4 | **ship** → staff_plus |
| `distinguished` | 24 | 5 | **ship** → staff_plus |
| `vice president` | 22 | 22 | **ship** → staff_plus |
| `head of`, `chief` | 0 | 0 | ship, **documented dormant** |
| **`fellow`** | 16 | **3** | **DROPPED — measured false drop** |
| `architect` | 619 | 39 | **dropped** — a role type, not a rung |
| `specialist` | 792 | 13 | **dropped** — not seniority |
| `associate` | 745 | 37 | **dropped** — field-inverting (law/finance entry); belongs to the field tier if anywhere |
| `expert`, `advanced`, `master` | 74 / 54 / 10 | 4 / 7 / 0 | **dropped** — company-specific level words, not universal |

**`fellow` was the BLOCKER.** It kills three `role_verdict == swe` early-career roles:

```
Scale AI | SWE Fellow - Human Frontier Collective (US / UK / Canada)
Scale AI | Machine Learning Fellow - Human Frontier Collective
```

A *fellowship* is an early-career program. §4.1 promises *"only a confident word or catalog hit can
drop"*; `fellow` is a homograph and is removed. `distinguished` still catches *"Fellow - Autonomy
(Distinguished Engineer)"*, which is the genuinely senior case.

### 3.5 Collateral damage of the substring mechanism

Titles where an `exclude_titles` entry fires as a **substring** but no entry fires at a word
boundary, and `role_verdict` says `swe`: **30 postings / 24 distinct titles.**

- **9 genuine `Sr` ⊂ `SRE`/`ISR`/`Israel` false vetoes** — *"Software Engineer - Cloud SRE"* (eBay),
  *"Software Development Engineer, SRE (US Federal)"* (Workday), *"Software Engineer/ SRE (Linux)"*
  (Visa), *"Software Engineer - Figma Weave (Tel Av**iv, Isr**ael)"* (Figma).
- **14 Cisco/Intel/Broadcom `Lead` ⊂ `Leader` vetoes that are correct by accident** — *"Software
  Engineering Technical Leader | C++, Routing protocols, BGP | 10 - 20 years"*.

**This is why `leader` is in the word list.** A naive `\blead\b` fix would re-admit 14 genuinely
senior titles. The gate's vocabulary is *not* a word-boundary copy of the user's `exclude_titles`.

### 3.6 Roman numerals — reframed (review MAJOR M6)

Bare roman `II`/`III`/`IV` on role-gate survivors: **392 postings / 48 companies** (CrowdStrike 50,
Regeneron 35, Pinterest 33, Affirm 31).

Revision 1 went back and forth here and both attempts were wrong:

- **Requiring a role noun** (`Engineer II`) admits **112 non-software postings** (*Animal Attendant
  II*, 24 × *Medical Account Specialist II*). Rejected.
- **Bare matching** preserves today's behaviour — but the review showed the *reason* is wrong:
  **218 of the 392 (56%) are `role_verdict == "uncertain"`, not `swe`** — *Data Analyst II*, *Client
  Partner II*, *Learning Specialist II*. Dropping them as `above_band: mid` writes a **false reason**
  into the funnel, which CLAUDE.md forbids (typed violations at the raise site).

Revision 1's own example is falsified: `role_verdict("Building Attendant II")` is
`("uncertain", "no role signal in title")` — it passes the role gate.

**Ruling for this spec:** ship bare roman `II`/`III`/`IV` in the **field tier** (software:
`II`=mid, `III`/`IV`=senior), because it preserves current behaviour and 174 of the 392 genuinely
are `swe` level markers. But record plainly that **the other 218 are role-gate leakage wearing a
seniority costume**, and that the real fix is §8 Q2 — closing the role gate's `uncertain` lane. The
seniority gate is not the right owner of that population and must not be credited with it.

### 3.7 Prototype — the whole gate, end to end

Prototype of `parse_seniority` + `seniority_verdict` at `target_seniority_band = entry` over the
16,542 population:

| Verdict | Count | Share |
|---|---|---|
| `in_band` | 6,410 | 38.75% |
| `above_band` | 10,124 | 61.20% |
| **`uncertain` (abstain rate)** | **8** | **0.05%** |

**Independent corroboration.** Today's shortlist vs the gate's, bare-roman rule:

- **Today 5,483 distinct survivors; with the gate 5,445.**
- **Gained 23** — including all **9 SRE recoveries**. The other 14 are non-software noise the
  substring list killed by accident; they are the role gate's problem, and the fail-open direction.
- **Lost 61 — every one correctly senior, and every one leaking TODAY.** 21 × *Distinguished
  Engineer* (Capital One, NVIDIA, Roblox, Marvell, Salesforce), ~15 × *Vice President* software roles
  (Citi, BlackRock), plus `IV` titles.

**`Distinguished` and `Vice President`/`VP` appear in no current `exclude_titles` entry.** This is an
unbudgeted win worth more than the numeric-level work that motivated the spec.

Two independent measurements agree: §3.5's 30 wrongly-vetoed postings and this +23/−61 delta are the
same population counted differently.

---

## 4. Design

### 4.1 New module — `src/boardwatch/rank/seniority_gate.py`

Mirrors `rank/role_gate.py`: ordered patterns built with `tuple([...])` constructor calls, and
**every non-pass verdict carries the text that decided it**.

```python
SeniorityBand    = Literal["entry", "mid", "senior", "staff_plus"]
TargetBand       = Literal["entry", "mid", "senior", "any"]
SeniorityVerdict = Literal["in_band", "above_band", "uncertain"]

def parse_seniority(title: str, scheme: LevelScheme | None, words: WordMap
                    ) -> tuple[SeniorityBand | None, str]: ...

def seniority_verdict(title: str, scheme: LevelScheme | None, target_band: TargetBand,
                      words: WordMap) -> tuple[SeniorityVerdict, str]: ...
```

Note the signature takes a **resolved scheme**, not a company string — company resolution happens
once per run in the caller (§4.3), which is what closes review BLOCKER B2.

**Resolution order** (first match wins; order is load-bearing as in `role_gate`):

1. **Field-tier senior words**, `\bword\b` → the word's band (§3.4 list).
2. **Field-tier roman numerals**, bare `II`/`III`/`IV` → mid/senior/senior (§3.6).
3. **Self-describing level grammar** (`Level N`) **with a bound scheme** → the scheme's band.
4. **Self-describing level grammar with NO bound scheme, or a level outside the scheme's range** →
   `uncertain`, carrying the matched text and *which* of the two reasons applies.
5. **Ambiguous bare-letter token** (`L5`, `E3`, `T4`) → **`uncertain`**, always. Never resolves,
   because §3.3 measured that these are usually not levels.
6. **No token** → `in_band`. Absence of signal is never a drop.

`target_band == "any"` ⇒ always `in_band`, and the gate reports itself **inert** rather than silent.

**Fail direction:** only a confident word or bound-scheme hit drops. Everything else passes flagged.

### 4.2 Catalog — `src/boardwatch/rank/leveling.yaml`, with NO company names

Structure, resolving review MAJORs M1 and M2 and owner decision 5:

```yaml
leveling_version: 1

# UNIVERSAL tier — the mechanism. Same for every user in every field.
grammars:
  level_n:   {kind: self_describing, pattern: "level_n"}   # "Level 5"
  l_prefix:  {kind: ambiguous}                              # "L5" — never resolves
  e_prefix:  {kind: ambiguous}
  ic_prefix: {kind: ambiguous}
  t_prefix:  {kind: ambiguous}

# UNIVERSAL tier — named, company-free level schemes a user may bind to a company.
schemes:
  ic_1_to_7:
    grammar: level_n
    levels: {"1": entry, "2": entry, "3": entry, "4": mid,
             "5": senior, "6": staff_plus, "7": staff_plus}
  ic_1_to_6:
    grammar: level_n
    levels: {"1": entry, "2": entry, "3": mid, "4": senior,
             "5": staff_plus, "6": staff_plus}

# FIELD tier — word and roman meanings, keyed by career field. Unresolvable field => abstain.
fields:
  software:
    words:
      senior: senior
      "sr": senior
      lead: senior
      leader: senior
      manager: senior
      staff: staff_plus
      principal: staff_plus
      distinguished: staff_plus
      director: staff_plus
      "vp": staff_plus
      "vice president": staff_plus
      "head of": staff_plus     # dormant: 0 hits measured 2026-08-19
      chief: staff_plus         # dormant: 0 hits measured 2026-08-19
    roman: {"II": mid, "III": senior, "IV": senior}
```

**Company→scheme binding is USER CONFIG**, at `{config_dir}/leveling-bindings.yaml`:

```yaml
bindings:
  - provider: workday
    slug: snapchat.wd1.myworkdayjobs.com/snapchat/snap
    scheme: ic_1_to_7
```

Keyed on **`(provider, slug)`** — the same pair `registry/validate.py:39` uses for identity and the
same pair the `companies` table stores. This is what closes B2: no display-name matching, no
casefolding guesswork, no multi-word-name problem. Default: **no bindings**, so every `Level N`
posting abstains and is flagged until the operator binds a scheme.

**Consequences, stated plainly:**

- Shipped data contains **zero company names** ⇒ R7 `kind="taxonomy"` is honest, R8 is untouched, and
  the design is multi-tenant by construction rather than by argument.
- **The Snap leak stays open until the operator adds one binding line.** That is correct: boardwatch
  has no shipped, verifiable fact about Snap's internal leveling, and §4.5 makes the abstention
  visible every run rather than silent.
- Google/Meta/Amazon need no entries at all — §3.3 measured zero title hits.

**Loader** (`rank/leveling.py`), following `eligibility/catalog.py` and `extract/taxonomy.py`:
`files("boardwatch.rank") / "leveling.yaml"` with a `{config_dir}` override; `yaml.safe_load`; closed
vocabularies that **raise** rather than bucket; `isinstance(x, str)` on every scalar (the YAML-1.1
boolean defence at `catalog.py:200-208` — `no`/`on`/`y` become bools); `leveling_version` **validated
against a module constant**, following `predicate_catalog.py:79-91` rather than the dead decorative
`version:` key in `rules.yaml`.

**Caching (review MAJOR M8).** Revision 1 claimed both "compiled once at import" and "config_dir
override wins", which cannot both hold — `load_taxonomy`/`load_rules` are uncached and re-read per
call. The loop runs ~27k times per rank and `role_verdict` is tuned to 0.30 s over 19,262 postings.
**Resolution:** load and compile the catalog **once per `rank_open_postings` call**, beside
`load_taxonomy(settings.config_dir)` (`top_cmd.py:186`), and pass the compiled object into the loop.
Nothing is compiled at import; nothing is loaded per row.

**Generalization obligations** (verified against `tools/generalization/`):

- R7 flags any new data file: add `src/boardwatch/rank/leveling.yaml` to `allowlists.py` with
  `kind="taxonomy"`, provenance, reason, and a `pin="sha256:…"` re-pinned on every edit.
- **`git add` before `make check`** — the checker enumerates via `git ls-files`, so an untracked
  catalog is invisible to R7 and the gate passes falsely.
- R12 builds a real wheel; hatchling ships everything under the package root, so **no pyproject
  change** is needed.
- `seniority_gate.py` joins `SCOPED_MODULES` and builds tuples with `tuple([...])`. R9 also flags
  **dict keys**, which is a further reason the word map lives in YAML, not the module.

### 4.3 Profile field — `target_seniority_band`

`entry | mid | senior | any`, default `any` (inert, backward-compatible, **reported**).

- **Column:** `Text`, **`NOT NULL DEFAULT 'any'`** — following `p1_resume_max_pages`'s actual shape.
  Revision 1 proposed nullable and then spent a paragraph patching a null-vs-`"any"` hash hazard;
  `NOT NULL` makes `None` unreachable and **dissolves** the hazard (review MINOR).
- **Migration:** one additive `ALTER TABLE profile ADD COLUMN`, `down_revision =
  "runs_status_backfill_repair"` (verified head), native `DROP COLUMN` on downgrade.
- **Validation:** `Literal[...]` on `ProfileInput`, the house pattern. No DB `CHECK` —
  `tables.py:227-229` rejects the retrofit.
- **`save_profile`:** the field must appear in **all three** of signature, `.values()` and the `set_`
  map. Omitting it from `set_` means `profile edit` silently never updates it. Give it a **default**
  so the 25 existing call sites (1 src, 24 tests) keep compiling — and then `persist_profile` must
  still pass it **explicitly**, or `edit` silently resets the band (review MINOR).
- **Plumbing (review MAJOR M3):** add the field to **`ProfileView`** and `profile_view_from_row`
  (`rank/heuristic.py:32-48`). That is the choice that makes B1 cheap, because `notify.py` consumes
  `ProfileView` too.
- **Company resolution:** `rank_open_postings` already selects `companies.c.name`; it must **also
  select `companies.c.provider` and `companies.c.slug`**, and resolve `(provider, slug)` → scheme
  once per run into a dict before the loop.
- **CLI:** prompt in `profile edit`, print in `profile show`. **Not in `init`**, following the
  `resume_max_pages` precedent. *Correction (review MINOR):* revision 1 said R11 has a "count lock";
  it does not — `check_init_prompts` is a single tuple equality, and the length assertion in
  `test_defaults.py:354` is a non-vacuity guard. R11 *permits* a new init prompt behind a reviewed
  snapshot update. Keeping it out of `init` is a judgement call, not a rule.
- **New-user awareness (review MINOR):** because `init` does not ask, `top` prints a one-line notice
  when `target_seniority_band` is `any` **and** the gate saw at least one seniority token — naming
  the setting and the command to change it. An inert gate that nobody knows exists is the same
  monitoring failure as an unreported abstain.

**Hashing — verified, and the two hashes behave differently:**

| Hash | Effect |
|---|---|
| `eligibility/hashing.py::profile_hash` | **UNCHANGED.** Built exclusively from `Facts`, narrowed to fields declared by non-ignored families, plus `career_field`. It reads no `profile` column. Cached eligibility verdicts and LLM extractions stay valid — no re-judging, no re-spend. |
| `reports/manifest.py::profile_row_hash` | **MUST CHANGE**, plus both call sites (`pipeline/policy.py:31-38`, `pipeline/funnel_writer.py:193-200`) and the pinned parameter-set assertion at `tests/unit/test_profile_resume_max_pages.py:61`. |

**Catalog version enters `policy_version` too (review MAJOR M7).** Revision 1 argued no hash was
needed because ranking persists nothing. That is right about `rules_snapshot` and wrong about the
manifest: `leveling.yaml` decides a **drop bucket** and is user-overridable, so omitting it makes the
manifest claim two runs identical when the thing driving the drop changed — §4.3's own argument for
`profile_row_hash`, applied consistently. Fold a digest of the **loaded** document (not the file, per
"hash what the consumer reads") into `policy_version`, and amend `manifest.py:22-25`'s *"the one
coverage gap that remains"* sentence, which this otherwise silently falsifies.

Consequence: `policy_version` changes once, so every existing ledger disposition reads stale. That is
documented, recoverable behaviour (`ledger show --stale`, `ledger reopen`). **It is 11 rows** — the
whole `job_dispositions` table, all `built` (review MINOR: revision 1 dramatized an uncounted event).

### 4.4 Ranker wiring — and the two other filter chains (review BLOCKER B1)

The gate must be wired in **three** places, not one. All three already call `role_verdict`:

| Site | Why |
|---|---|
| `cli/top_cmd.py:255-259` | the ranker |
| `reports/notify.py:117-128` | **independent chain with its own `include_non_swe`** — otherwise the notification path keeps pushing Snap *Level 5* after `top` stops showing it. `company_name` is already in its select (`notify.py:92`); it needs `provider`/`slug` added. |
| `reports/stats.py:119` | otherwise `stats` reports a different population than the funnel |

```python
role, role_reason = role_verdict(row.title)
if role == "not_swe" and not include_non_swe:
    hidden_non_swe += 1
    continue
band, band_reason = seniority_verdict(
    row.title, schemes.get((row.provider, row.slug)), target_band, words
)
if band == "uncertain":
    uncertain_band += 1                      # counted, NOT dropped (§4.5)
if band == "above_band" and not include_over_seniority:
    hidden_over_seniority += 1
    continue
```

### 4.5 Observability — the keystone (review BLOCKER B3)

Revision 1 claimed the `uncertain` reason rides on `RankedPosting.why` *"exactly as `role_reason`
does for a `not_swe`"*. **That was false about the cited code.** `top_cmd.py:271` attaches
`role_reason` **only** on `not_swe` — i.e. only to drained rows — so following revision 1 literally
would have inverted `_why_cell`'s documented invariant (`top_cmd.py:495-504`): *"Every drain
annotates; a normally-visible row is unannotated."*

Required, all four:

1. **`uncertain_band` is a counter on `RankedResults` → `ShortlistCounts` → the shortlist stage's
   report block — NOT its `Drop` list**, so the reconciliation identity still balances. This is the
   abstain rate CLAUDE.md requires reported every run.
2. **`RankedPosting` gains `band` and `band_reason`**, twinning the existing `role`/`role_reason`
   (`top_cmd.py:65-66`), and the JSON payload gains `"band"` beside `"role"` (`top_cmd.py:660-672`).
3. **`_why_cell` annotates the DRAINED row only** (`top_cmd.py:495-508`), preserving the invariant.
4. **`show <id>` gains a `Band:` line** beside the existing `Role:` line (`show_cmd.py:150-155`),
   which the code documents as *"the audit surface for the role gate"*. A row hidden as `above_band`
   must be explainable by lookup.

**While we are here:** `uncertain_role` should be reported by the same mechanism. §3.1's 41%
fail-open hole is invisible today, and adding a second unreported lane beside it is the defect this
spec exists to fix.

### 4.6 The drain must not consume the queue (review MAJOR M5)

`--include-over-seniority` puts rows in `results.visible`, and `rank_open_postings` defaults
`record_surfaced=True`, writing a `seen` disposition for every visible row (`top_cmd.py:397-398`).
So inspecting the quarantine would suppress those jobs for `seen_ttl_days` and pollute Gate P6's
dedup window. **A drain that consumes the queue is a re-entry path that closes behind you.**

Drained rows are excluded from `surfaced_job_ids`. **The same defect exists today for
`--include-non-swe`** and is fixed in the same change.

---

## 5. Mirror sites — **at least 27**, stated as a floor

`top_cmd.py:83-107` says *"a new drop bucket has SIX hand-maintained mirror sites"*, a number two
prior reviews already corrected upward. Revision 1 said 21 and **was itself wrong twice**: its list
enumerated 19, and it missed six sites outside `top_cmd.py`. The count is stated as a **floor**, and
correcting that docstring is one of the sites.

**Ranker — `cli/top_cmd.py`:** (1) the reconciliation-identity prose in `RankedResults`' docstring;
(2) the "SIX mirror sites" paragraph; (3) the dataclass field; (4) counter init; (5) the increment +
`continue`; (6) `rank_open_postings` signature; (7) the `return RankedResults(...)` mapping;
(8) `_print_hidden_notices` signature; (9) the drain notice; (10) **the empty-result early-return
guard at `:690`** — absent from the old list of six and it has already swallowed two buckets;
(11) the typer option; (12–15) **four** call sites threading the flag (`:633, 654, 701, 725`);
(16) `RankedPosting.role`/`role_reason` twin at `:65-66`; (17) `_why_cell` at `:495-508`;
(18) the JSON payload's `"role"` key at `:660-672`; (19) the select must add `provider`/`slug`.

**Beyond the ranker:** (20) `pipeline/runner.py:673-684` mapping into `ShortlistCounts`;
(21) `reports/run_funnel.py:216-235` the `ShortlistCounts` field; (22) `run_funnel.py:719-770` the
shortlist stage `Drop`; (23) `cli/run_cmd.py:24-43` `_shortlist_line`; (24) `reports/notify.py:128`;
(25) `reports/stats.py:119`; (26) `cli/show_cmd.py:153`; (27) `reports/manifest.py` +
**both** `profile_row_hash` call sites; (28) `cli/profile_cmd.py::persist_profile` and its caller
`init_cmd.py:71`.

**Docs (the three revision 1 asserted and never named):** `CHANGELOG.md`, `README.md:224` (which
documents `--include-non-swe`), and `docs/program/DECISIONS.md`.

**Deliberately NOT touched — reasoning recorded so it is not "fixed" later:**

- **`pipeline/runner.py:342-390` `_zero_output_guard` — NO.** Register only a bucket that can
  *legitimately explain an empty day* (suppressed by external/temporal state). `over_seniority` is a
  **rejection**, like `hidden_non_swe` and `hidden_hard_filter`, neither of which is registered.
  Registering it would **weaken** the guard. **Known consequence:** the first morning the band filter
  empties the shortlist, the guard fires and that run is not clean. Per owner decision 6 this is
  accepted, not designed around.
- **`run_funnel.py:910-930` tailor-stage `Drop` — NO.** That stage carries drops only for buckets
  removing postings *after* ranking. Adding it would double-subtract.
- `funnel_to_dict` / `funnel_to_markdown` iterate `stage.drops` generically — no change.

**Reconciliation.** Shortlist identity is `considered == shortlisted + Σ Drop.count`, `derived=False`,
so it can genuinely fail. `Drop.reason` is a bare `str` — **no closed catalog refuses a typo'd bucket
name**, which is why this list is exhaustive rather than trusted to a validator.

**Tests:** `test_top_accounting.py:109-120` (`_accounted`); `test_top_duplicates.py:105-120` and
`:173-190` (two more hand sums); `test_run_funnel.py:90-170` (the `funnel()` helper — kwarg,
`ShortlistCounts` pass-through, **and the default `considered=` balance**; missing the last makes
every unrelated funnel test fail); `test_run_funnel.py:513-545` (markdown drop reasons — use a
**distinct non-zero** count, a zero is blind); `test_liveness_withholds_dead_leads.py:381-399` (the
**only** guard on `_shortlist_line`); `test_applied_state_suppression.py:110-145` (the empty-result
early return — a 6th test site revision 1 missed).

---

## 6. Consequences

### 6.1 The word half is inert until `exclude_titles` is edited

`passes_hard_filters` runs **before** both gates, and `exclude_titles` already strips
`Senior`/`Sr`/`Staff`/`Principal`/`Lead`/`Manager`/`Director`/`II`/`III` by substring. On day one the
gate's word and roman rules see almost nothing.

**The 9 SRE recoveries do not happen automatically.** They require pruning the seniority words from
`exclude_titles`, leaving the role-based entries (*Field Service Engineer*, *Mechanical Engineer*,
*Hardware Engineer*, *Sales Engineer*, *Control Systems Engineer*, *Service Technician*, *Field
Engineer*). That is `boardwatch profile edit` — **interactive, TTY-only, the operator's to run.**

**It is a 6,380 → 16,542 corpus expansion** for ranking and the `seen` ledger. PROGRAM.md §1's reset
rule covers it. Per owner decision 6 the streak is not a constraint, but the expansion should be a
deliberate act, not a surprise.

### 6.2 At `target = entry`, `mid` drops

`above_band` is *strictly greater* than the target, so *Software Engineer II* drops at `entry`. This
matches both the current `exclude_titles` behaviour and new-grad targeting. Stated because it is
obvious now and surprising in three months.

### 6.3 No retroactive correction

Run 61's Snap *Level 5* lead is `built` (permanent), so it will not re-surface — but its PDF is on
disk in `~/boardwatch-applications/2026-08-19/` and it is already counted in METRICS.md for run 61.
Nothing retracts either, deliberately: the run happened and its record stands.

### 6.4 Sequencing

1. Ship gate + catalog + profile field, default `any` ⇒ **behaviour unchanged**, gate reports inert.
2. Operator sets `target_seniority_band`, prunes `exclude_titles`, and optionally binds a scheme for
   any company whose `Level N` postings are abstaining — all one TTY session.
3. Expect the one-time `policy_version` re-key (11 ledger rows) and, possibly, one non-clean run.

---

## 7. Testing

- **Parser:** `Sr` does not match `SRE`/`ISR`/`Israel`; `leader` parses as senior; `fellow` parses as
  **nothing**; bare roman parses; ambiguous `L5`/`E3`/`T4` **always** yield `uncertain`.
- **Scheme resolution:** `Level 5` with a bound scheme → senior; **unbound** → `uncertain` with the
  no-binding reason; level outside the scheme's range → `uncertain` with the *other* reason; binding
  is keyed on `(provider, slug)` and a display-name lookup is proven **not** to be used.
- **Catalog:** closed-enum violation raises; unquoted YAML-1.1 boolean raises; `leveling_version`
  mismatch raises; an unknown `career_field` **abstains** rather than defaulting to software.
- **Profile:** migration up/down; `NOT NULL DEFAULT` on an existing row; `profile edit` round-trips
  (the `set_`-map defect); `profile_row_hash` tracks the field and the pinned parameter-set assertion
  is updated; **`profile_hash` proven unchanged**.
- **Observability:** `uncertain_band` reaches the funnel report and is **not** in the `Drop` list;
  reconciliation still balances; `show` prints `Band:`; JSON carries `"band"`; `_why_cell` annotates
  a drained row and **not** a visible one.
- **Drain:** `--include-over-seniority` does **not** write `seen` — asserted through the store, not
  the return value.
- **All three chains:** a Snap `Level 5` posting is dropped by `top`, by `notify`, and by `stats`.
- **Coordinator deny:** measured against the live corpus per `role_gate`'s docstring discipline and
  recorded in the module comment as every other narrowing in that file is.
- **Behaviour test over run 61's real titles:** Snap *Level 5* drops **once a scheme is bound**;
  Airbnb *Disaster Response Coordinator* → `not_swe`; the other 6 leads retained, including Affirm's
  *"Software Engineer I, Backend (Collections)"* (roman `I` must not read as a higher level).
- **`make check` green** — the only gate; plain mode, never piped through `head`/`tail`.

---

## 8. Open questions

1. **Ship `head of` / `chief` despite 0 measured hits?** Recommendation: yes, marked dormant — they
   are unambiguous and cost nothing. (Contrast Google/Meta/Amazon scheme entries, which are dropped
   precisely because they are dormant *and* would put company names in shipped data.)
2. **Is the role gate's `uncertain` lane the next piece of work?** §3.6 found **218 of 392** roman
   titles are role-gate leakage, not seniority, and §1.2 notes the coordinator deny closes only 1.2%
   of the 11,171-posting fail-open bucket. This spec makes that lane *measurable* (§4.5's
   `uncertain_role`); closing it is a separate, larger design.

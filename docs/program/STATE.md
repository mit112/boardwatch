# PROGRAM STATE — read this first

> The one file a fresh session with zero memory reads to know where the program stands.
> **If it disagrees with the repo, the repo wins** — fix this file and record the correction in
> `DECISIONS.md`. Plan: `PROGRAM.md`. Numbers: `METRICS.md`. Shipped: `CHANGELOG.md`. **Do not re-derive
> `STANDING-FACTS.md`** (D-139). Both logs carry an index spanning themselves and a closed archive
> (D-108): read the index, then the one range — never the whole file.
>
> **States only what is true now**; no sha or commit count (D-017). **Rewrite it, never prepend.** Keep it
> near 170 lines: how something got here is narration, and narration belongs in `DECISIONS.md` /
> `METRICS.md`. Before cutting a sentence, check it exists somewhere else (D-149).

---

## Current standing

**The headline number: 0.** Zero job applications have ever been sent (`applications` has 0 rows) — the
machine produces leads, it never applies (out of scope). Against that: 3 published releases (none since
**0.3.0**), ~53k lines of source, **~6,900 tests**, 70 leaf CLI commands, 6 ATS providers, a **~1.0 GB**
store.

**P3'S STREAK IS RESET TO ZERO (D-276).** The 08:00 launchd trigger fired cleanly unattended on
**2026-08-20** (run 63, `runs` 1→2) and again on **2026-08-21 at 08:00:10** (run 66, `runs` 2→3, exit 0,
~26 min, funnel RECONCILES, 8 leads / 8 PDFs / 8 projected, 0 withheld as gone). **Gate P3 is 0 of 7
UNATTENDED — the streak RESET (D-276)** — it needs 7 consecutive clean scheduled runs, and only a SCHEDULED tick counts (a manual
`run --project` does not touch the counter). Run 66 was the first scheduled run to exercise the #114 `Lead`
fix and **all 8 of its leads were software roles** — run 65 had 5 of 8 as business/ops `Lead` titles.
**Run 67 (MANUAL, 2026-08-21, verified clean)** absorbed D-266's one-time full-corpus re-key so tomorrow's
tick does not pay it: exit 0, 42m41s, reconciles, 30,243 of 30,243 re-evaluated, 8 leads / 8 PDFs, **all 8
`us`** with none on fail-open.

**The next scheduled tick is 2026-08-23 08:00, and a clean one is 1 of 7.** Confirm it fired with
`launchctl print gui/$(id -u)/com.boardwatch.run | grep -E "runs|last exit"` — **`runs` must go 4 → 5 with
`last exit code = 0`**, and that counter is the ONLY authority (a manual `run --project` moves nothing).
Artifacts: `~/boardwatch-applications/<date>/funnel-<N>.*`, log `~/Library/Logs/boardwatch-run.log`; match on
the run NUMBER, never the date. Standing tripwire from the 16 decisions run 67 reopened (D-268): **all six
known leaks are blocked by the current gates** — five non-SWE `Lead` titles in the role gate, GE HealthCare
posting 31365 (`Buc` → `non_us`) in the hard filter — so any of the six appearing in a funnel's `leads` is a
real regression to investigate before anything else. The other ten are legitimate SWE roles that may
re-surface and consume the cap with repeats, which Mit accepted when reopening. A **missed-window alarm ships (D-260, #110):** a successful run pings `BOARDWATCH_HEARTBEAT_URL` (a
dead-man's-switch), so an external cron-monitor alerts when a scheduled run never happens — the one failure a
local check cannot see (the Mac off/asleep all day). Off until the operator sets the URL.

**Run 67 funnel (latest):** 30,243 corpus → 12,697 uncertain (D-250) / 2,167 ineligible →
`hidden_hard_filter` 17,891 → shortlist **8**, all 8 leads `us`. **3,502 postings clear every filter and are
cut only by `DEFAULT_TOP_N`** (run 66: 3,595) — the precision tension Mit rules on: fix precision, never tune
the cap (ideally show everything eligible).

**Discovery is budget-capped, and the backlog DRAINS on a known clock (D-270, confirmed D-271).**
`detail_fetch_budget` is **50** unseen postings per board per run, so a day's "new postings" figure measures
our throughput, not the market — 19 Workday boards sit at exactly 600 rows and gain exactly 50 × runs each
day. Run 67 left **15,535 listed postings unmaterialised** on 20 boards (Citi 1,614 … Fidelity 104), visible
only as prose inside `board_scans.error` and absent from the funnel. Every board's backlog falls
**monotonically, 26–49 per scan**; 15 boards have already drained. **ETA to empty: 48 more runs (~7 weeks at
1/day)**, worst board Citi. A contrary claim that Workday's newest-first ordering means tails are never read
was FALSIFIED by `posted_at` — Databricks reaches 2019-11, Cisco 2025-12, Adobe 2026-03; Citi is an outlier.
Budget-skipped postings are **not** falsely closed (0 closures on the 20 partial boards).

**Workday's own `total` is censored at 2,000 — the facet counts are not (D-271).** Summing a partition
facet's `values[].count` is a second, uncapped aggregation path, and the known-positive control PASSED
(Adobe 740/740, Intel 645/645, Regeneron 592/592, Fidelity 565/565 agree exactly). Measured: **Citi's real
board is 4,589 postings against 600 held — 13.1%**; NVIDIA 2,656 against 600. Our pager also wraps at
~2,000, so **after the backlog drains Citi stays at ~2,214 of 4,589 — a permanent, invisible hole that is
NOT the budget.** Mirror defect: Regeneron 101.4% and Fidelity 106.2% coverage mean we hold postings the
board no longer lists, because a permanently `partial` board never runs `_process_missing`.

**Seventeen boards produce nothing, and five of them report GREEN (D-271).** Snyk, Vercel, HubSpot, Plaid
and Qualcomm scan cleanly, carry `last_health='empty'` and a current `last_ok_at`, and have returned zero
postings across 12 scans — the dangerous class, because a board that fails loudly gets fixed. The other 12
fail outright with exactly {401 × 4, 403 × 1, 422 × 7}; **Workday sends 422 for a malformed request body,
not for auth**, so those seven are probably wrong slugs and therefore recoverable. No backoff, no
auto-disable, no quarantine — `get_watched_companies` filters on `watched` alone.

**boardwatch cannot see 92% of what job-apps surfaces, and that REOPENS D-008 (D-271).** Of job-apps' 530
eligible records over 2026-08-12…08-21, **41 (7.7%)** are at a company boardwatch watches; the set spans
**352 distinct companies** and boardwatch watches **24**. Largest missing: Amazon 25, TikTok 20, AWS 8,
Apple 7, ByteDance 7, SpaceX 6 — **none uses any of the six supported ATS**, so adding a slug cannot reach
them. Lane value by loss-if-removed: commercial aggregators 421 of 446, **GitHub new-grad lists 73 of 103
(19.1% of yield for ~5 public-repo GETs)**, direct ATS 5 of 14; cross-lane overlap only 5.8%. Where
boardwatch is BETTER: on greenhouse/lever/ashby it stores what job-apps title-filters away at fetch, and
job-apps' Workday lane is 3 hardcoded queries × 2 pages × 12 details = 77 roles over 39 boards with 16
returning zero. Counterweight: ~1/5 of job-apps' yield is staffing firms and list artifacts. **The 8-vs-42
shortfall is a SEPARATE problem** — `capped_by_top_n` is 3,502 and job-apps has no top-N anywhere, so
raising the cap matches volume but not parity (~8% overlap). **RULED 2026-08-22 (D-272): three lanes go in.** **The ORDER then reversed (D-278): Indeed via
JobSpy first**, because its body arrives free inside the search response; then hiring.cafe (one
unauthenticated GET); then the GitHub lists **last**, because they carry no body at all and 53.3% of
their active entries duplicate boards already scanned. The lanes exist to reach companies no
existing route can reach — Mit's ruling — and D-272's ordering was set on yield, not on that. **Bespoke first-party adapters are OUT** (Amazon/Apple/TikTok): job-apps'
own dead sources are *all* bespoke adapters or niche APIs, never aggregators. `PROGRAM.md` §4's three
blocking rows are struck.

**The coverage instrument is SHIPPED and ON `main` (D-271/D-272/D-273, PR #125, green under
`make check` and full CI), and D-274 makes it report itself unattended — see below.**
`boardwatch coverage` reports every watched board as a
**seven-way partition** — `measured` / `enumerated_only` / `censored` / `dark` / `stale` /
`unscanned` / `unreadable` — that never folds a bucket into a neighbour, and prints "not
measurable" rather than 0% or 100% when nothing can be measured. Four nullable `board_scans`
columns carry it, populated from values the six providers already computed, at **zero additional
HTTP cost**.

**Real 135-board scan against a store copy: global coverage 82.7%, 26,183 held of 31,643 stated**,
buckets summing to exactly 135 (measured 90 · enumerated_only 11 · censored 4 · dark 12 · stale
18). **Workday's `total` is censored at 2,000 and its facet sums are not — Target's real board is
12,097 postings against 649 held, 5.4%: the largest hole in the corpus, and invisible before this
work.** Citi 4,573, NVIDIA 2,656, T-Mobile 2,200. Worst measured: Capital One 34.7%, Wells Fargo
36.4%, Salesforce 42.3%.

**`DEFAULT_TOP_N` is 40 and LIVE** (armed 2026-08-22 08:17). The launchd job runs
`.venv/bin/boardwatch run --project`, and that venv is an **editable** install resolving to `src/`
in the primary working tree — so the tick executes whatever is CHECKED OUT there, not what is
merged. Code and store both report `p_board_coverage` (verified this session by reading the live store
`?mode=ro`). No sha is recorded here on purpose (D-017) — check `git log` in that tree.

**Run 68's scheduled tick FAILED, and that RESET Gate P3 to 0 of 7 (D-276) — it does not
"stay at 2".** The gate is *7 **consecutive** unattended runs* (`PROGRAM.md` §Gate P3), and a failed
unattended run breaks consecutiveness. Evidence: `runs = 4`, `last exit code = 1`, and the launchd
log carries the crash. Invocations 2 and 3 were the clean ticks (runs 63, 66); invocation 4 died.
**The next clean scheduled tick is 1 of 7, not 3 of 7** — seven more clean days, not five. Gate P4
(the owner's blind craft review) is barred until P3 is met, so this moves that too. A subagent had run a `boardwatch`
command against the DEFAULT data dir during the overnight build, migrating the live store to
`p_board_coverage` while the checkout was still pinned to older code — so alembic refused a
revision the code did not contain (`runs` 3 → 4, exit 1). Damage was schema-only: four nullable
columns, zero rows written, nothing corrupted. **The rule it buys: an agent handed a `boardwatch`
command must be REQUIRED to set `BOARDWATCH_DATA_DIR` to scratch on every invocation — the live
store is the default, so a forgotten flag reaches production.**

**Run 68 re-run manually with the new code: exit 0, ~24 minutes, 40 leads / 40 PDFs, reconciles,
no fatal** — roughly the wall-clock 8 leads used to cost. 135 boards attempted, 85 complete, 12
failed, 14,238 postings seen, and `capped_by_top_n` **3,628**: even at 40, that many postings still
clear every gate and are cut by rank alone. First live coverage reading **82.4% (26,075 of
31,629)**, within 0.3 points of the store-copy rehearsal.

**The instrument is no longer mute — MERGED AND ARMED (D-274, PR #127).** A scheduled run now reports coverage in the two
artifacts it already writes: a `board_coverage` section in the funnel (**`artifact_version`
5 → 6**) and a `## Discovery reach` block in the morning digest (**1 → 2**), plus one
`board coverage →` line on stdout, which is what a launchd run leaves in its log. The report is
loaded **once** in `runner.py`'s `finally` and the same object is rendered into both, because
`held` has no run dimension and two loads seconds apart can differ. `boardwatch coverage --json`
now shares that serializer, so the command and the artifacts cannot describe one number two ways.
A coverage failure costs the **section**, never the artifact.

**Correction to the row above:** `notify` was never a candidate surface — it is a standalone CLI
command, `runner.py` imports nothing from it, and the launchd plist runs only `run --project`.

**Exercised on live data before any scheduled tick, per D-273's rule (run 69, MANUAL).** exit 0,
22m29s, 40 leads / 40 PDFs, both artifacts carrying the section, the two sections **byte-identical**
(the single-load property, observed rather than asserted). The checkout is on `main` and the
editable venv resolves to it, so the next 08:00 tick reports coverage. **Run 69 does not move the
P3 counter** — only a scheduled tick does, and Gate P3 is 0 of 7 (D-276).

**Run 69 also exercised the 304 edge case by accident, and the partition held.** It ran ~3 hours
after run 68, so **81 boards answered `unchanged`** against run 68's 18. A 304 carries no fresh
total, so those went to `stale` and the headline fell to **76.5% over 37 measured boards** (16,602
of 21,697) from 82.4% over 90. That is the design's own "304 staleness" lie-vector, refused the way
it was meant to be: withhold the ratio rather than pair a carried total with a live numerator. **A
back-to-back run therefore reports a smaller measured set — that is not a regression.** On the
once-a-day cadence it barely bites. `enumerated_only` fell 11 → 0 for the same reason: `stale` is a
property of THIS scan and wins over any stored total.

**Cross-run movement is real and visible:** Capital One 34.7% → 37.4% (650 → 700 held), the detail
budget draining 50/run exactly as D-270 predicts.

Note on D-267: whether adding `locations` to `Lead` needs a bump of its own is **unresolved** —
that row says it does, while `run_funnel.py`'s own version comment cites D-113 as the precedent for
declining a bump on a key added inside a block that already exists. Either way it is a separate
ruling and was deliberately NOT folded into this change.

Design, and eight ways this metric could lie:
`docs/superpowers/specs/2026-08-22-coverage-assurance-design.md` (its §3.1 table predates
`unscanned`/`unreadable` and names five buckets; the shipped partition is seven). **Still Mit's:**
whether `censored` boards publish a ratio, `detail_fetch_budget`, and the 17 silent boards.

**Eligibility now decides AND removes.** `work_authorization.needs_sponsorship=true` set (D-249); a
zero-evidence `eligible` abstains to `uncertain` (D-250); two rules that could never resolve MET are fixed —
`degree:any_degree_required` and `work_auth:sponsorship_available` (D-256, #107); and **clearance is armed as
a `blocker`** with `security_clearance={state:none,level:none}` (D-257) so the ~138 clearance-required
postings resolve UNMET → ineligible → dropped.

**The role gate is tight and holding.** Four passes of SOFT denies — pre-sales/support/BD, non-eng
managers/directors, Data Scientist/Analyst, business/ops/admin/pricing, and bare `Lead`
(D-252/253/255/259/262). All 8 of run 66's leads were software, against 3 of 8 in run 65. The
`_NOENG` guard spares any engineering noun and is the correct multi-tenant form even where Mit's
`exclude_titles` would also catch it. **Deferred to owner** (borderline): Team Leader, Data Center Engineer,
bare Administrator. **NOT excluding "User Researcher"** — it overlaps real ML/Research *Engineer* roles.

**Hard location gate is US-only, ARMED and verified firing (D-251).** `config.toml`
`location_filter_mode=hard`; `rank/location_gate.classify_location` is a positive US allowlist (fail-open on
the unclassifiable, Mit's visa ruling). Default stays `soft` for other users. The funnel's stale "never
measured firing" note is now corrected (D-265) — that bucket carried 17,189 drops in run 66.

**Two real defects in that gate are fixed (D-263, D-264).** (1) **D-263:** `_alternation` built its pattern
without grouping the alternation body, so the word-boundary lookarounds bound only to the first and last
token and everything between matched as a bare substring. Region token `uk` fired inside `Waukesha` and
`West Milwaukee`, and the gate silently dropped **41 real GE HealthCare Wisconsin postings** — `Software
Engineer` among them. It was INTERMITTENT: which token lands last follows `frozenset` order under per-process
hash randomisation, so 43 postings' drop decision differed between `PYTHONHASHSEED` 0 and 4 — the same store
and code disagreeing run to run. (2) **D-264:** the deferred Buc/France leak is closed by three independent
non-US signals — 57 curated foreign city tokens, a structural ISO alpha-3 country code, and a new
`rank/foreign_ad_gate` reading DACH `(m/w/d)` / French `(H/F)` / `Ingénieur` off the TITLE (the only signal
that reaches three postings whose `locations_json` is exactly `["Remote"]`). Net **299 corpus drops, 36 US
false drops recovered, 280 of 444 `unknown` survivors still passing** — fail-open intact. `Dublin` and ten
other US-namesake names are left leaking BY RULING; the rejected list lives in the `location_data` docstring
so a later pass does not "complete" it.

**Seniority band = `entry` and internships excluded — SET and verified live (D-258).** `profile edit` proved
to be pipeable (NOT one of the TTY-guarded gates), so this was applied without Mit's terminal: band `entry`
activates the merged-but-inert gate (ambiguous level tokens like "Level 3" still ABSTAIN and pass — ladders are
not guessed), and `exclude_titles` gained `Intern`/`Internship`/`Co-op` (title-based, trap-safe; the engine is
body-only, below). **Done (run 65):** `ledger reopen --stale` released **19** decisions — the one-time
`policy_version` re-key the band + `exclude_titles` edit forced. **Done again (after run 67):** 16 more,
D-266's fingerprint re-key. `engine_version` feeds `policy_version`, so the drain is owed after ANY change to
it; a stamp mismatch never re-opens on its own, so no run self-heals this.

**The eligibility engine is body-only** — `preflight.py` feeds it `posting_versions.body_text` with no title
column — so title-based filtering (internship, seniority words) lives in the ranker (`exclude_titles`,
`role_gate`, `seniority_gate`), never the engine. job-apps (consulted this session) detects intern/co-op BY
TITLE for exactly this reason; boardwatch's body-only `internship_role_declared` is 100%-precision/~27%-recall
and already suppresses the "internships count" trap.

**Reviews of the precision merges have found five false-drop defects; all are fixed** — the US+foreign
location segment (#111), the seniority product-noun collision (#112), the `Lead` hole those reopened (#114),
and the location gate's two (D-263/D-264). **Deferred (MEDIUM, safe-direction):** the zero-output guard can
false-*alarm* on a genuine zero-lead day now that the ranker hides `not_swe`/`above_band`/`non_us`, not just
`ineligible` — a false alarm on the unattended run, never data loss.

**A manual `run --project` is the way to exercise a gate change on live data before a scheduled tick** — it
uses identical argv but does NOT move the P3 counter. Run 65 did this and caught the `Lead` hole (D-262).

**CI health — the nightly's THREE causes are fixed (D-269); #95 closes on a green scheduled run.** It had
failed **7 of its last 8** scheduled runs, which is not intermittency: ubuntu always passed, so every cause
sat in the schedule-only jobs and `make check` stayed green locally throughout. (1) A **production defect** —
`ensure_schema` runs alembic through an engine alembic builds itself, so the pragma listener never fires and a
store is **created in `delete` mode**; the deferred switch to WAL is a *conversion*, which no other
connection's lock permits (raises after the full busy timeout against a reader, **instantly** against a
writer), so two processes opening a fresh store race and the loser cannot open it. Mit's live store already
reads `wal`, so nothing needs migrating. (2) Five **deterministic** Windows `fs_safety` failures on all three
Windows jobs — `os.path.realpath` rewrites `/data` to `\data`, so the POSIX fixtures collapse onto the root
mount and the `None`-expecting cases passed **vacuously**. (3) tectonic: `actions/cache` only saves on a
**miss**, so the minimal-`article` warmup bundle was frozen forever and every run fetched the template's real
packages over the network — one hiccup cost ~52 render tests. **Windows/macOS evidence comes ONLY from a
`workflow_dispatch` of `ci.yml` and the nightly itself** — never from a PR's checks. **That evidence is now
IN: run 32514934447 is the first fully green full matrix — all 12 jobs, windows and macos 3.11/3.12/3.13
included.** Windows 3.11 went from 5 failed / 6888 passed / 50 skipped to **7003 passed / 58 skipped / 0
failed** (50m19s → 35m08s); the +8 skipped is exactly the eight `fs_safety` cases marked, so the pass is for
the right reason. **#95 stays OPEN by design** — `nightly-watch` is schedule-only, so it closes only on a
green scheduled nightly.

**The roadmap is UNFROZEN (D-240); its remaining gates are OPERATIONAL, not build.** P0/P1/P2/P5 gates are
**MET**. P3/P4/P6 builds are essentially done; their gates now close by *running* boardwatch daily. Gate P4
(Mit's blind craft review) is barred until P3's gate is met. Gate P6 needs a real 7-day dedup window plus
liveness-probed leads. The 14-day acceptance clock starts after P6; **P7 breadth stays last.**

**The bundle → résumé + projection + render tracks are COMPLETE and merged; nothing is queued there.** Gate B
is **MET** (0 blockers, D-201); 11 entities refined within the 220-char ceiling; projection reaches the daily
pipeline behind opt-in `run --project` (D-225); the render stack shipped ATS-parsable PDFs (D-233),
`fill_to_page` (D-234), `link_in_first_bullet` + `sort_projects_by_date` (D-235). **What is left on the résumé
is Mit's alone**: whether to send a document, and the two owner-gated prose rewrites of D-220. `resume.yaml` is
an import source, never hand-fixed (D-155).

### Reference facts (do not re-derive)

- **Bundle track:** live revision 22, 11 entities. Do not quote its digest (restamps daily, D-017); re-derive
  with `profile-bundle inventory`. Facts stay `owner_attested` (D-191). Editing is incremental (D-190):
  `checkout --draft` → `edit-fact` → `validate --draft` → Mit's **TTY** `approve` → `promote`. `approve` does
  NOT validate; a plain `validate` cannot see Gate B; `_catalog_admits` is a DIFF — always `validate --draft`
  and diff the blocker COUNT before Mit approves.
- **Stage 2** is live; the one-page budget is a **character** budget ≤ **3,439** (D-219). `mean_per_bullet` is
  the default scorer; `ADMISSION_FLOOR` stays `Decimal(0)` (D-197/8).
- **P5b criteria NAMED (D-229):** 3 clean projected runs, ≥30 postings, 0 preflight fatals, 0 résumé-QA
  failures, 0 fabrications. Four of five evidenced on a store copy.
- **Settled — do not reopen:** Projection (D-156/163); Gate A MET (D-157); autonomous backlog COMPLETE
  (D-202…D-210, D-237); Education Slice C (D-239); D-184 finding 2 (D-238).
- **Fixture + corpus drift (D-228):** R13/R14/R15 in `tools/generalization/fixtures.py`. The corpus content
  pin was re-recorded this session for the m0105 fix (987 rows unchanged). **On 2026-09-11** the greenhouse
  fixture reds `make check` (enforced at `fixtures.py` R15, `now > review_by`) — and that tripwire already has
  its drain: `python -m tools.fixture_refresh --extend <provider> --days N --reason "..."` records an audited
  extension, or re-check the live API and re-record. **The corpus is regenerable in principle:** only
  `scratchpad/gen_corpus.py` is missing — its inputs all survive in `.agent/p2-catalog/` (`proto.py` the
  oracle, `matrix.py`, `adv.py`). They are **gitignored**, so a `.agent/` clean is what would make the 987-row
  oracle truly unrecoverable; committing a generator plus its inputs is an owner call, not done.

### Owner-gated — do NOT start unilaterally

1. **P2 item 8 — the onboarding field-taxonomy gatherer** (needs its own brainstorm). D-054 forbids us
   authoring non-tech field content.
2. **Mit's two résumé content calls** — whether to send; the D-220 prose rewrites.
3. **`add-evidence` takes no bundle lock** (D-143) — raise before two authoring agents run against one bundle.

---

## Phase status

| Phase | Build | Gate |
|---|---|---|
| P0 Instrumentation | **COMPLETE** | **MET** (D-030) |
| P1 Résumé artifact gate | **COMPLETE** | **MET** (D-032/033) |
| P2 Profile + keystone | items 1–7 shipped; item 8 NOT STARTED | **MET AS RECONCILED** (D-075) |
| P3 Unattended one command | **COMPLETE, INSTALLED, FIRING** — runs 63 and 66 were genuine scheduled ticks (D-254) | **NOT MET — 0 of 7 unattended.** Streak reset by run 68's failed tick (D-276) |
| P4 Craft gate | **COMPLETE** | **NOT MET** — the owner's blind craft review, barred until P3's gate |
| P5 Eligibility decides | **COMPLETE** | **MET** — INELIGIBLE precision 16/16, 0 span violations |
| P6 Liveness + dedup | **BUILD COMPLETE** (D-110/111/113) | **NOT MET — 2 of 4** — needs a real 7-day run |
| 14-day acceptance | not started | starts after P6 |
| P7 Breadth | not started | gated on P0 attribution data |
| *Gate A / Gate B* | *complete, merged* | ***MET*** — *has moved no program gate* |

### Gate P6, clause by clause

| Clause | Standing |
|---|---|
| Duplicate leakage over 7 days ≤ 5% | **NOT met.** One-shot baseline 0.79%, not over 7 days. `posting_identities` already holds the collisions — 1,118 body-hash and 1,062 company+title+location keys whose postings sit in DIFFERENT jobs — so the clause needs Mit's ruling on which kinds count as a duplicate, not new code (D-270) |
| **0** dead postings reaching leads | **NOT met.** Needs a real probed run; recall low by design |
| Injected hash-collision test | **MET** (D-100) |
| Audit of 20 sampled suppressions | **MET** (D-101) |

---

## Open questions — Mit's, not to be resolved by fiat

1. **Should `pipeline/runner.py` keep swallowing a funnel-write failure into a printed warning?** (D-076.)
2. **The projection spec's six open questions** (§12) — soonest: whether `tailor run` should validate the
   projection manifest, and whether persona's `entries` list survives stage 2.
3. **The Snap `Level 5`/`Level 3` leak stays open by design** — with no bindings file every level token
   abstains, so a level-named title is shortlisted carrying its reason. Closing it takes one deliberate
   binding line; boardwatch ships no verifiable claim about any company's ladder ("Level 3" is entry at some
   shops, senior at others — Mit's point: read the JD's fine print, don't guess).

*(Recently resolved: open Q2 — clearance IS now a blocker (D-257); open Q4 — seniority band = `entry`, arming
pending Mit's TTY (D-258); the launchd trigger — FIRED (D-254).)*

---

## Windows and the lock reclaim window

**Windows is best-effort (D-212)** — in the nightly, out of the pyproject classifiers, caveated in README. A
`nightly-watch` job files a "Nightly CI is failing" issue on a failed scheduled run and closes it on recovery
— **#95 is OPEN now** (the two CI flakes above); it will auto-close on the next green scheduled run.

**The stale-lock race is FIXED at the root; all four `xfail` markers are gone on `main`** (D-224/227).
`core/lock_reclaim.py` owns the constants — **1.0s on `win32`, 0.0 elsewhere, so POSIX is bit-identical**.
Windows evidence comes only from a `workflow_dispatch` of `ci.yml`. **One false-refusal exposure is left
standing DELIBERATELY (D-224):** POSIX `UnixFileLock` unlinks before releasing the flock, so a live-holder
handoff can report `bundle_lock_held` while nobody holds the lock. **Ruled: record, do not widen.**

---

**A discovery lane without a JD body produces ZERO leads (D-272).** The eligibility engine is
**body-only** — `eligibility/preflight.py` selects `posting_versions.body_text` and passes it alone to
`evaluate`. A stub is a whitespace-only body (`count_stub_postings`; currently 17 of 30,243 = 0.056%), and
under D-250 a zero-evidence verdict abstains to `uncertain`. Aggregator postings arrive as title + URL, so
any of the three approved lanes shipped without JD acquisition would add corpus and surface nothing. This
MEETS the condition `PROGRAM.md` §4 set when it deferred the 2,200-line JD chain to "P7 where a non-API
source might first appear". **boardwatch needs far less than job-apps' 2,200 lines**: P7 already requires a
dereferencing step for any aggregator lane, and that same step is the fix — an aggregator link mostly
resolves to a Greenhouse/Lever/Ashby/Workday posting whose parser already exists. A link that resolves to
nothing parseable stays a stub and is REPORTED as one, never quietly dropped.

**The JD-acquisition design is RECORDED and awaits Mit's review (D-278):**
`docs/superpowers/specs/2026-08-22-jd-acquisition-design.md`. Four rulings taken — purpose (reach the
unreachable), lane order (reversed), a per-run new-company cap because adding a board IS breadth, and
UA scope (honest on the six providers, browser UA only on new aggregator fetches). The decisive
measurement: **job-apps' headless-browser tier is worth 13% historically and 0% currently** — dead
since 2026-08-11, 11 consecutive runs at zero, invisible because one `except Exception: return ""`
makes a missing dependency, a timeout and an empty page the same empty string. So the no-browser
rule costs almost nothing. But **job-apps has no generic careers-page extraction either** — 14
hand-maintained host regexes gate every fetch, and Apple and TikTok have no handling at all — so the
honest route to those companies is an aggregator that carries the body, not a page reader. Still
Mit's: whether **Oracle Cloud HCM and iCIMS should be PROVIDERS** instead of or before any lane
(~45% of the non-six tail, fits the existing architecture, reaches neither Amazon nor Apple nor
TikTok), the cap's number, and whether LinkedIn earns its per-posting request cost.

---

## Live blockers and carried gaps

| Item | Detail | Owner |
|---|---|---|
| **A metric that could not fail (D-267)** | `grep -ic buc funnel-N.json` was read as a Buc count; it counts the word "bucket" and is 4 on runs 61/63/65/66 regardless. The funnel enumerates **no ranked pool** and a `leads` row carries **no location** — so the hard location gate, the one gate whose failure is a visa-ineligible lead, leaves no trace in its own artifact. Closing it needs `locations` on `Lead` + an `artifact_version` bump. **Re-raised 2026-08-21c; still Mit's.** D-268 corrects this row's replacement metric too: "0 of 62" had the 0 robust under every bounded rule (27/27/69/70 matched, 0 surviving) but the **62 unreproducible** — match rule and corpus size were never recorded beside it, and a bare substring gives 103 matched / **39 surviving**. A ratio now records its match rule AND corpus size | **Mit** (shipped-schema change) |
| **boardwatch cannot see 92% of job-apps' eligible yield** | 41 of 530 records (7.7%) at a watched company; 352 companies in the set, 24 watched. Amazon/TikTok/Apple/ByteDance use none of the 6 ATS, so a slug cannot reach them. Closing it means a new discovery lane — GitHub new-grad lists are 19.1% of yield for ~5 public-repo GETs and are NOT the ToS trap the v2 decision was written about. **Reopens D-008** | **Mit** (reverses a shipped decision) |
| **Citi sits at 13.1% coverage, permanently** | Workday's `total` censors at 2,000; the facet sum (uncapped, control-verified) says 4,589. Our pager wraps at ~2,000 too, so post-drain Citi holds ~2,214 of 4,589 and nothing reports it | **Mit** (input-side) |
| **Five boards report GREEN and return zero, ever** | Snyk, Vercel, HubSpot, Plaid, Qualcomm — clean scans, `last_health='empty'`, 0 postings across 12 scans. 7 of the 12 dead boards are HTTP 422 (malformed request ⇒ probably wrong slugs, recoverable). No backoff, no quarantine, no drain | **Mit** (input-side) |
| **`unchanged` is an unaudited coverage assumption** | 59 of 135 boards listed nothing in run 67 on a payload hash. No test exists for a hash misreporting a changed board. A false `unchanged` is silent, permanent and undetectable by any current instrument | open |
| **`hidden_hard_filter` drain — SHIPPED (#129)** | `top --include-hard-filter`, unbounded by the rank cutoff (Mit's ruling). The blocker was never the flag: `passes_hard_filters` returned a bare `bool`, so the clause and the matched token were discarded at the `return`. `hard_filter_verdict` now carries them and the bool is a wrapper. **The bucket is FOUR clauses, not "all `exclude_titles`"** — that split was measured when the mode was `soft` and two clauses did not exist (D-277) | closed |
| **A body-less posting can suppress another one** | `content_hash("")` == `content_hash(whitespace)` == `e3b0c442…`, and that hash feeds `exact_quad` — the ONLY suppressing identity kind — while `_verify_quad` agrees because `"" == ""`. Live store: 32,229 open, **13** whitespace-only bodies, all on that hash, **0 colliding (company,title,locations) groups — latent, not firing.** Must be fixed before any aggregator lane lands a row (D-278) | open |
| **No external missed-window alarm** | nothing outside a run can detect a missed 08:00; the funnel heartbeat is only written from inside `runner.py` | P3 |
| **`resume.yaml` is an IMPORT SOURCE, never hand-fixed** | D-155. Mit pins `resume_max_pages=1`; never advise 2 | Mit |
| **`boardwatch top` advances the queue by default** | records `seen` unless `--no-record`; relevant to Gate P6's clean window | P6 |
| **`add-evidence` takes no bundle lock** | two concurrent captures race on up to 13 files (D-143) | owner-gated |
| **A live store is readable ONLY via Python `sqlite3` `?mode=ro`** | the `sqlite3` CLI with `?mode=ro` fails `CANTOPEN(14)` on a cleanly-checkpointed store (no `-shm`; not the sandbox), and `?immutable=1` skips the WAL so it is STALE against a live writer. Mid-run progress: `SELECT COUNT(*) FROM eligibility_evaluations WHERE run_id=N` (D-268) | tooling |
| **`make check` must be launched DETACHED** | the Bash tool clamps `timeout` to 10 min; a longer gate reads as `Error 143`. Launch double-fork + `setsid` and poll the log | tooling |

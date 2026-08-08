# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Keyword-coverage measurement for tailored résumés** (P4 item 6 — D-061). A per-lead and per-run report
  (never a veto) of how many of a JD's *requirement* terms the résumé genuinely covers. The denominator is
  the JD's qualifications span (via the existing `qualifications_span`), falling back to whole-body skills
  when no qualifications header is found, recording which source was used. The numerator counts only skills
  the **master** résumé actually has (`tailor/coverage.py::resume_fact_skills`), never the tailored output —
  so a bullet that echoes a JD term cannot inflate coverage. `fraction` is `None`, never `0.0`, when a JD
  has no recognized requirement terms. Surfaced in each tailored artifact's `meta_json`, the morning report,
  and a run-level funnel summary (mean/median coverage, most-frequent missing terms). Fail-safe: a coverage
  bug records `coverage=None` and never drops a lead. Shipped `58f032e`; `make check` green (3112 passed,
  95.32%).

- **Persona registry + résumé title de-senioritizer** (P4 item 7 + folded-in item 4 — D-063). A persona is
  a résumé-*presentation* lens (title, skill-group order, entry subset), never an eligibility variant, so
  the profile DB and eligibility engine are untouched. A versioned `tailor/personas.yaml` (bundled seed +
  `{config_dir}` override) declares personas; `select_persona` deterministically picks one from the JD's
  role family (`classify_role_family`, never a model; unmatched → the required default); `apply_persona`
  reorders skill groups and selects/orders the entry subset on a new frozen `Resume` with an optional
  `title`. The title is the JD title with seniority stripped (`tailor/title.py`, boundary-safe: `Sr`∉`SRE`,
  `Lead`∉`Leader`, `III` before `II`), validated against the persona's family — a "Senior iOS Engineer" JD
  yields an "iOS Engineer" headline, never stamping "Senior" on a new-grad résumé. Rendered into the paired
  `%%TITLE%%` template slot (graceful degrade when absent). A malformed registry is a loud run-level fatal;
  an unmatched JD family is the normal default path. Keyword coverage (item 6) still measures against the
  original master, so persona shaping can't inflate it. Shipped `1988c39`; `make check` green (3148 passed,
  95.23%).

- **P5a — verdict-safe eligibility-integrity slices** (D-064). Three changes that raise decision integrity
  without altering any deterministic eligibility verdict: (1) a corpus-wide **property gate** asserting
  every INELIGIBLE result carries a non-empty quoted JD span (Gate P5's "0 INELIGIBLE without a span");
  (2) `boardwatch eligibility abstain` now surfaces an out-of-catalog **family** and any **disposition
  token** outside `{met,unmet,unknown}` as their own FAILURE lines (closed-catalog discipline), while still
  reconciling the anomaly into `total_rows` so denominators never silently shrink; (3) the opt-in LLM
  eligibility lane's response cache is now keyed on **profile + catalog identity** (`profile_hash` +
  `rules_hash` folded into the cache key), so a cached verdict is never replayed across a changed profile
  or rule catalog — `ResponseCache.key`'s signature is unchanged, leaving the tailor rewrite lane intact.
  Shipped `faf8aa9`; `make check` green (3525 passed, 95.17%). Verdict-changing P5 items (new families,
  named exceptions, REQUIRED/PREFERRED context) and data-gated items (labeled eval set, 35+ visa phrases)
  are deferred — they need the human-verified labeled set to measure Gate P5's precision.

### Changed

- **The résumé render engine is now tectonic compiling the user's own LaTeX template, replacing Typst**
  (résumé-tailoring fix, Increment 1 — D-058, D-060). Diagnosis found the tailored output read as a
  "plain-text dump" for two reasons: a five-line Typst stub preamble with no real page setup, and tailoring
  itself being near-invisible. Typst could only ever *approximate* the user's own template — a different
  typesetting engine cannot reproduce a LaTeX file byte-for-byte — so tectonic (a single ~30 MB LaTeX
  binary, the same footprint class as Typst) now compiles the résumé's real `.tex` source unchanged.

  - **`render/typst.py` and its tests are deleted.** A new `LatexRenderer` (`render/latex.py`) emits
    sections into `%%SECTIONS%%` markers in a bundled default template (`render/templates/resume_base.tex`,
    registered in `SHIPPED_DATA`); a user's own template installs to `{config_dir}/resume_template.tex` and
    overrides the bundled default. `_validate_template` now requires the `%%SECTIONS%%` markers to be
    present in the resolved template, so a malformed template fails loudly instead of degrading silently.
  - **Bolding moves to native inline `\textbf{}`**, matching the job-apps LaTeX pattern; entailment
    (`output_is_entailed`) strips markup before comparing tokens to the master, and any non-`\textbf{}`
    LaTeX command inside a bullet is a violation.
  - **Page count now reads `pdfinfo`** instead of a Typst-native metadata query.
  - **`Entry` gained structured fields** — `kind`, `title`, `dates`, `subtitle`, `location` — plus a new
    `Resume.extracurricular` section, so LaTeX subheadings (role/company/dates on one line, tech stack on
    the next) render correctly; entailment now checks all of them, not just `title`.
  - **The persisted meta key `typst_pdf_built` keeps its legacy name.** Renaming it would ripple into
    funnel/reconcile queries that already read it, which is out of scope for this change.
  - Header and Education stay template-hardcoded in this increment (job-apps-exact); single-sourcing them
    from `resume.yaml` is a documented fast-follow, not built here. Keyword bolding from `jd_skills`
    (Increment 2) and per-role authored title/summary selection (Increment 3) are each their own plan.

  **Result: the user's real résumé now renders to 1 page** (verified by a real compile plus `pdfinfo`,
  measured on Mit's own résumé), resolving the standing Gate-P3 blocker where the old Typst stub rendered
  an authored résumé to 2 pages against a `resume_max_pages=1` limit, dropping every lead on every run.
  Fidelity against Mit's job-apps LaTeX PDF is a layout match — no emitter or layout bugs found. A new, real
  remaining blocker was found, and it is content, not the render engine: three bullets in Mit's
  `resume.yaml` exceed the per-lead layout gate's 220-character ceiling (D-053), so Tier-A degrades to the
  untailored master on every posting until they are shortened.

### Added

- **A run reaper drains phantom `running` rows instead of leaving them permanent forever** (P3 slice 2,
  D-046). A crashed or killed run left `runs.status='running'` with `finished_at IS NULL` with nothing to
  separate it from a live run. `reap_stale_runs(engine, *, older_than)` marks rows matching
  `status='running' AND finished_at IS NULL AND started_at < now-older_than` as `failed`, in a single
  atomic `UPDATE ... RETURNING id` (append-only `json_insert` note — no read-modify-write). Discrimination
  is age-based rather than process-liveness-based: `runs` carries no pid/heartbeat column, and a container
  writer and a host writer have disjoint pid namespaces anyway. Default threshold is the new
  `Settings.reap_stale_after_hours` (24h; classified operational, so it never enters `config_hash`). Runs
  inside `doctor` (report+reap, guarded so a lock-contended write can never crash the diagnostic) and at
  `boardwatch run` start, before the run's own row is minted. Fail-safe by construction: `finish_run` has
  no `status='running'` precondition, so a false reap on a run that later finishes self-corrects its
  `status` — though the `reaped` note intentionally persists in `errors_json` as a breadcrumb (an Opus 5
  checkpoint review corrected the original docstring, which had claimed a complete self-correction) — and a
  narrow theoretical `BUSY_SNAPSHOT` race on `finish_run`'s own read-modify-write is documented rather than
  restructured (D-046, D-055).

- **A P4 craft guard gauntlet — five deterministic checks on Tier-B rewrites, each reverting one bullet to
  its Tier-A source rather than dropping the lead:**
  - **Overmatch (style) guard** (D-048, `tailor/overmatch.py`, `OVERMATCH_VERSION="p4-overmatch-1"`): flags
    a Tier-B bullet that lifts a verbatim ≥7-gram from the job description, or copies the JD's unusual
    capitalization of a non-canonical term. Complements P1b's provenance (facts) veto — this one catches
    lift, not fabrication — and runs after provenance, before the judge, so a bullet about to be reverted
    never spends judge budget.
  - **Canonical-vocab consolidation** (D-049, `tailor/canonical.py::build_canonical_vocab`): one
    byte-identical source for the canonical-tech set (taxonomy names ∪ equivalence-table images), replacing
    the same seed expression previously duplicated across `rewrite/lane.py` and `rewrite/agent_lane.py`. A
    per-field vocabulary selector was declined as speculative — there is one field (SWE) today.
  - **Register / buzzword / verb-diversity guards** (D-050): a banned-register phrase list and a
    per-bullet buzzword-density ceiling (`tailor/register.yaml`, `register.py`), plus a résumé-wide
    verb-opening-diversity post-pass (`rewrite/verb_diversity.py`; no more than 2 bullets share an opening
    verb, and a rewrite is only demoted when doing so genuinely diversifies against the Tier-A verb that
    would otherwise ship).
  - **Requirement-echo detector** (D-051): an AND-gate flagging a Tier-B bullet that restates a JD
    qualification instead of describing work — a structural qualification-register cue AND a shared 4-gram
    with a JD qualifications-section sentence containing a non-canonical token, so pure tech-vocab overlap
    never corroborates on its own.
  - Each veto is a new closed `drop_reason` (`lift_rejected`, `banned_register`, `buzzword_density`,
    `verb_repeat`, `requirement_echo`) reported on the funnel's `FabricationCounters`, all excluded from
    bar metric B4's fabrication numerator — a conservative craft veto is not a caught fabrication. The
    pre-existing structural filter rejects (`empty`/`not_single_line`/`too_long`) were split into their own
    `filter_structural_rejected` bucket for the same reason (D-055 fix 3).

- **Two run-time résumé layout gates, both fail-safe to the untailored master** — a violation degrades to
  the master, it never drops a lead on layout alone:
  - **Per-lead layout gate** (D-053, `validate_layout` in `reports/resume_gate.py`): asserts bullet length
    ≤220 chars, bullet count ≤ `MAX_BULLETS_PER_ENTRY`, an escaping round-trip, and no template-artifact
    token leak — run on the tailored and Tier-B renders. It does **not** run on the untailored master
    (see Fixed, below).
  - **Run-once master validation** (D-056, `validate_master` in `tailor/load.py`): checks the authored
    master résumé once, at load, for a contact name and email and no template-artifact leak — deliberately
    skipping bullet length/count, which are the author's own choice, not a rendering defect. A broken
    master now aborts the run loudly (`MasterResumeError`, fatal) instead of silently dropping every lead
    one at a time.

### Fixed

- **The per-lead layout gate no longer runs on the untailored master résumé, and can no longer drop a lead
  on layout alone** (D-055, Opus 5 checkpoint review, fix 1 — HIGH). As first shipped, item 5a's gate also
  ran on the master fallback and reused a *selection* cap (`MAX_BULLETS_PER_ENTRY`, which bullet selection
  trims *to*) as a *layout* invariant; a low-`jd_skills` posting made `tailored == master`, both failed
  identically, the master-fallback rescue did nothing, and the lead was dropped where before P4 it would
  have shipped Mit's real résumé — breaking the "master fallback is unconditionally shippable" guarantee.
  The per-lead gate now applies to the tailored and Tier-B renders only; a genuine compile failure on both
  sides is the only remaining way a lead drops. Master-authoring defects are now caught separately, once,
  at load instead (D-056, above).
- **A valid single-combined-line résumé header (e.g. "Name · email · site") is no longer rejected as
  missing a name** (D-056, fix round). `validate_master`'s original `len(resume.header) < 2` check assumed
  a ≥2-line header as if it were schema rather than a scaffolding convention; fixed to check only that the
  first header line is non-blank, decoupled from line count.
- **A Tier-B rewrite's recorded lineage hash now points at the Tier-A bullet actually shipped, not at a
  possibly-rejected tailored render** (D-055, fix 2). `tier_a_content_hash` was capturing whichever render
  happened to run first rather than the shipped `chosen_hash`.

### Changed

- **A held scan lock now names the blocking process instead of a generic message** (P3, §3.P3 item 1,
  D-043). `run_scan` writes a message-only sidecar (`scan.lock.meta`: pid/hostname/started_at) around the
  existing `FileLock` acquire/release; on contention the error names the blocking pid, host, and start
  time, falling back to the unchanged generic message if the sidecar is missing or malformed. The sidecar
  is never a lock authority — `filelock` alone decides acquire/release — so a stale or corrupt sidecar only
  degrades the message, never correctness. `boardwatch scan`/`boardwatch run` now print the caught
  exception's own message instead of a hardcoded constant, so the pid-naming message actually reaches the
  CLI. Stale-reclaim was declined outright, not deferred (D-045) — unsound as designed, and the OS already
  reclaims a dead flock on process exit. Token-gated unlock remains deferred. The run reaper has since
  shipped (D-046, see below).
- **LLM adapter calls now retry transient 429/5xx failures with backoff instead of dropping the rewrite**
  (P3, §3.P3 item 10, D-040). Both `AnthropicClient` and `OpenAICompatClient` classify a 429 or 5xx
  response as `LLMTransientError` and retry through a shared `llm/retry.py` helper (tenacity,
  `Retry-After` honored when the provider sends one, bounded at 4 attempts) before falling back to
  today's Tier-A-keeping containment on exhaustion. The retry lives inside the adapter's own request path,
  below the rewrite lane's per-call budget metering, so a retried call still costs exactly one budget
  unit. Any other non-2xx status, or an invalid response body, still raises the flat, non-retryable
  `LLMError` unchanged.
- **The systemic-scan-outage predicate is now one function, `is_systemic_scan_outage`
  (`scan/coordinator.py`), called by both the pipeline (`run_pipeline`) and the standalone
  `boardwatch scan`** (P3, §3.P3 item 4, D-037). Previously the same "attempted > 0, complete == 0,
  unchanged == 0" logic was written out twice; behavior is unchanged, this only removes the risk of the
  two copies drifting apart.
- **`show` now renders an `eligible` verdict that fired zero eligibility rules, one that fired and
  cleared all of them, and one that fired some non-blocking `preference`-family rows that were NOT
  cleared, as three distinct headers** (P2, §3.P2 item 6, D-036). Previously all three rendered as a
  bare "Eligibility: eligible" — "no flags" is not the same claim as "cleared", and a fired-but-unmet
  row is not "cleared" either, even when it did not block the verdict (D-035's five still-`preference`
  families). A new derived `AuditView.presentation` (`VerdictPresentation`, no schema change, stored
  `verdict` unchanged) now headers the three cases "eligible — no eligibility rule applied (not
  screened)", "eligible — N requirement(s) cleared" (only when every fired row is `met`), and
  "eligible — N requirement(s) evaluated (M cleared; see details)" for the mixed case.
- **`work_auth`'s default severity is now `blocker`, not `preference`** (P2, §3.P2 item 7, D-035). Every
  eligibility family previously shipped `default_policy: preference`, so a fresh, policy-less profile got
  **0 `ineligible` verdicts ever** — the multi-tenancy requirement failing for anyone who had not, like Mit,
  set `work_auth: blocker` by hand. `work_auth` is the canonical hard-stop family (bar metric B7),
  the most-developed, and keystone-gated (it abstains to `uncertain`, never `ineligible`, when
  `work_authorization` is undeclared), so it is the one family safe to flip today; the other five
  (`experience_years`, `clearance`, `degree`, `contract_not_fte`, `internship`) remain `preference`,
  opt-in, pending further review.

### Added

- **`docs/program/WAL_DISCIPLINE.md`** — documented SQLite/WAL concurrency stance (P3 item 8 doc half, D-041): per-connection WAL + busy_timeout + single-writer scan lock; names the untested cross-OS two-writer config as the remaining hard half.
- **A run-scoped morning artifact, `morning-<run_id>.{json,md}`, written beside the funnel**
  (P3, §3.P3 item 7, D-038). For every lead a run tailored: apply URL, résumé PDF path, the
  honest `AuditView.presentation` verdict label, a quoted evidence span (or the eligibility
  rationale), and the ranker's one-line why — ranked by score. It links to `funnel-<run_id>.md`
  for the accounting rather than restating it, and is sourced from the same population as the
  funnel (this run's tailored leads), never from cursor-scoped `digest`/`notify`.
- **A freshness check, `check_run_freshness`** (`pipeline/freshness.py`), for whether a
  `<date>/` output folder's artifacts are genuinely from a finished run of that calendar date
  (P3, §3.P3 item 2, D-038) — not just a folder that happens to contain a `funnel-<run_id>.md`.
  Checks the run's terminal status, that `started_at`/`finished_at` fall on that date, and that
  the lead folders on disk reconcile with the store's tailored-artifact row count for that
  run_id. No new schema.
- **Three run-integrity guards on `boardwatch run`, each capable of turning a run non-zero, none capable
  of suppressing a real failure** (P3, §3.P3 items 5, 9, 6, D-039): a **zero-output guard** — 0 leads
  fails the run unless the count of open postings verdict `eligible` AND judged BY THIS RUN
  (`run_id`-attributed, not a cross-run ledger) is also 0, so a steady-state day where every eligible
  posting is a prior-run cache hit stays honest; a **cohort-completeness guard** — every candidate the
  ranker shortlisted (`ranked.visible`) must have become a lead or a recorded tailor failure, reconciled
  by posting_id SET rather than count, so a compensating bug cannot balance it; and a
  **filesystem-truth guard** — the leads the store says this run produced must have folders on disk,
  reusing the freshness reconciliation rather than a second implementation.
- **`work_authorization.needs_sponsorship` as an orthogonal bit** on the eligibility work-auth fact (P2,
  §3.P2 item 2, D-034). Previously sponsorship need was entangled as a `status` enum value, forcing an
  EAD/F-1-OPT holder to abstain; the bit lets them state a sponsorship need independently of status, so
  `ead_or_similar` + `needs_sponsorship=false` now resolves decisively. It influences only sponsorship
  rules — never citizenship rules — and with the bit unset, behaviour is unchanged.
- **A Tier-B reword provenance veto, fail-closed to the Tier-A bullet** (P1b, PROGRAM.md §3.P1 item 3c,
  D-033). The LLM-assisted rewording lane had no check that a reword's content is actually traceable to the
  source; a fabrication like *"single-handedly re-architected … eliminating downtime"* passed the existing
  overmatch filter, which only vetoes ALLCAPS/entity additions.

  - **`reword_is_provenanced`** (`tailor/rewrite/provenance.py`) is a pure, deterministic allowlist: every
    content token in a reword must be a source token, an approved equivalence-table image, or a member of
    a closed, versioned connective allowlist of claim-free structural words (articles/prepositions/
    coordinators only). No stemmer and no modals/auxiliaries — both were shown to let fabrications through
    (verb→agent-noun via a shared stem; a future-commitment fabricated via `will`).
  - **Slots before the judge**, in both `run_tier_b_core` (the API lane) and `screen_candidates` (the
    no-API-key agent lane), so a fabricated reword never spends a judge call. A veto emits a new closed
    `drop_reason="provenance"` and keeps the deterministic Tier-A bullet.
  - **A separate `provenance_rejected` fabrication counter**, reported on its own funnel line and
    deliberately **not** folded into bar metric B4's numerator (`rejected = judge_rejected +
    overmatch_filtered`) — a conservative veto is not a caught fabrication.
  - **`LLM_LANE_VERSION` bumped `tier-b-1` → `tier-b-2`**, invalidating cached Tier-B outputs from before
    the gate existed.
  - **The honest cost:** the gate is deliberately aggressive — a benign synonym or tense variant
    (`optimize`→`improve`, `optimize`→`optimized`) is vetoed and reverts to Tier-A until the equivalence
    table is curated to permit specific swaps.

- **A hard résumé PDF gate — no lead ships without a compliant, compiled PDF** (P1a). Replaces the old
  silent `"source only (no PDF; typst not available or compile failed)"` degrade with a typed,
  fail-closed pipeline:

  - **Binary-missing vs. compile-failure, split at the type.** A missing `typst` on `PATH` is an
    environment fault (`TypstUnavailableError`) that aborts the whole run fatal and exits the CLI
    non-zero with install guidance; a compile failure or a page-count overflow on one lead's résumé is a
    per-lead fault handled by the fallback below. Both are drawn from closed catalogs
    (`CompileReason`, `GateReason`) — never string-matched.
  - **Page count is a hard fail, checked Typst-native.** A new `resume_max_pages` profile column (default
    1) is enforced via a `typst eval` query against a metadata label the renderer now injects into every
    emitted résumé — no PDF-parsing dependency, no reliance on LaTeX-only `hbox`/`vbox` diagnostics (which
    Typst does not emit).
  - **Untailored-master fallback.** A tailored résumé that fails to compile or overflows the page limit
    falls back to rendering the untailored master; if that also fails, the lead is dropped with **no**
    `resume_tailored` row and **no** lead folder left behind — a plain compliant résumé beats none, and a
    dropped lead is invisible to the store rather than a half-written artifact.
  - **A compile log captured per lead**, including for a dropped lead (written to a durable
    `_failed/<slug>.log` before cleanup), so a fallback or a drop is always diagnosable after the fact.
  - **A slot-filled assertion** (`validate_slots`) runs on the tailored résumé right before render and
    fails the lead (routing into the same fallback) if tailoring stripped an entry down to nothing.
  - **`typst` is now packaged, not just assumed installed.** The Dockerfile installs the pinned release
    binary, and `doctor` probes both presence and version, warning loudly on a mismatch — an
    unpinned typst can silently break the page-count query syntax and make every lead fall back or drop.

- **`boardwatch verify`** — a standalone DB↔artifact reconciliation sweep (P0 item 5). Reads a run's frozen
  `funnel-<run_id>.json` off disk, re-queries the store independently for the run-keyed quantities that
  cannot legitimately change after the run finished (tailored-row count, PDF-built count, distinct lead
  count, exit status), and — the load-bearing check — confirms every run-keyed tailored artifact the DB
  records (`resume_tailored` and `resume_tailored_llm`) actually has a file on disk, reading
  `meta_json.pdf_uri` explicitly rather than guessing a sibling path. `verify --run <id>` verifies one run
  and exits non-zero with `NO_ARTIFACT` if no artifact exists for it; plain `verify` sweeps every
  `funnel-*.json` present on disk. Read-only; supplements Gate P0 rather than re-anchoring it (D-031).

- **A run manifest, a stub rate and fabrication counters in the funnel artifact** (artifact v3;
  `ARTIFACT_VERSION` 2→3) — P0 items 4, 6 and 8, batched because all three add a section to the same
  artifact.

  - **Manifest** (item 4): the versioned identity a run ran under, so two runs can be compared for
    reproducibility from the artifact alone — code fingerprint, `rules_hash`, `profile_facts_hash`,
    start/end and `runs.status`, all reused, plus two new hashes. `config_hash` covers the
    decision-relevant `Settings` fields over a **closed classification of all 21 `Settings`+`LLMTier`
    fields** that raises `UnclassifiedSettingError` on any unclassified field. `profile_row_hash` covers
    the five profile columns the ranker reads (`skills`, `target_titles`, `exclude_titles`, `locations`,
    `remote_only`) — none of which `profile_hash` covers, though `exclude_titles` drives the largest drop
    in the funnel. The one residual gap, the skill-taxonomy version, is named in the manifest note (D-030).

  - **Stub rate** (item 6): open postings with an empty JD body over the corpus head, one number every
    run — `None` over an empty corpus, never 0%. Expected near zero for structured ATS JSON; a non-trivial
    value is the signal a scraped source has appeared. The query uses SQLite's two-arg `trim` so a
    tab/newline-only body counts as a stub.

  - **Fabrication counters** (item 8, feeds bar metric B4): the Tier-B rewrite `drop_reason`s folded into a
    closed catalog, with the two truth-gate rejections (fail-closed entailment judge, deterministic
    overmatch filter) counted apart from the budget/error/no_candidate fallbacks. An unrecognised
    `drop_reason` lands in `other` and prints a FAILURE line rather than being absorbed silently.

- **A terminal exit status on every run row.** `runs.status` over the closed catalog
  `running | ok | failed`, so the ledger can separate "finished clean", "finished with errors",
  "crashed" and "still running". Out-of-catalog raises `UnknownRunStatusError` at the write site rather
  than being enforced by a `CHECK` constraint — adding one to an existing SQLite table costs a full
  rebuild, and six tables carry a foreign key to `runs.id`.

  **The column default carries the meaning.** A `SIGKILL` never reaches the pipeline's `finally`, so no
  code can ever set a terminal status for a killed run — whatever the column defaults to *is* what a
  killed run says. It defaults to `running`, leaving such a row saying `running` with `finished_at` NULL;
  a default of `ok` would launder a killed run into a clean one.

  Status tracks the run's `fatal` condition, not its error list: a run that loses one lead to a tailor
  failure is a successful run with an error. Tying it to `fatal` means the ledger's status and the funnel
  artifact's FATAL line cannot disagree about the same run.

  **Scope, stated rather than implied:** `running` with `finished_at` NULL means only *nothing closed this
  row*. A run in flight, a killed run, and a standalone lane that raised between minting its run and
  finishing it all share that signature; separating them needs the reaper that P3 owns.

  Two write paths were recording a *failed* run as `ok` and were fixed with it: the scan's own abort
  handler (under `boardwatch run` the scan is called outside the pipeline's `try`, so that handler is the
  only place a scan abort is ever recorded), and a *total* scan outage on the standalone path, which the
  pipeline already classified as fatal — so the same event reported `ok` under `boardwatch scan` and
  `failed` under `boardwatch run`.

- **Per-source outcome table in the funnel artifact.** Per watched board: open postings, `eligible`,
  `leads`, `applied` — plus a rollup by provider, since the question of whether direct-ATS-only can carry
  the volume is a question about providers and 118 board rows do not answer it at a glance.

  **`unique` and `assisted` both report `not instrumented`, never 0.** Both are dedup-attribution
  quantities: `assisted` credits a source that arrived *second* for a posting another source won. Postings
  here are 1:1 with jobs and each belongs to exactly one company, so there is no second source to credit
  until dedup lands in P6. Reporting 0 would assert that no source ever arrived second — the naive
  attribution that, per job-apps' own handover, nearly cost it a working adapter.

  The denominator is every **open** posting a board owns, not what it listed this run: an unchanged board
  answers 304 and lists nothing while still owning hundreds of open postings.

  **One** total is re-swept per board and compared with the funnel's own figure: `leads`, whose two sides
  have genuinely different shapes (`COUNT(*)` of this run's `resume_tailored` rows against
  `COUNT(DISTINCT posting)` resolved through `posting_versions`), so a lead that resolves to no board fails
  the run's reconciliation. Neither way it can disagree is reachable through today's tailor path, so it is
  a guard against a future writer rather than live evidence — the artifact says so too. A second total over `eligible` was written and then deleted before merge: it
  grouped the same subquery the verdict stage counts, by a `NOT NULL` foreign key, joined on a primary key,
  so it agreed for every possible database state. `applied` is excluded for a different reason — summing
  per-board distinct job counts is not the global distinct count if a job ever spans two boards, which is
  impossible today only by accident of the current data.

- **The ranker now accounts for every posting it considered**, which is what makes the funnel's
  `shortlist` stage evidence rather than bookkeeping. It previously reported two of its **five** exits, so
  hard-filter vetoes, `--new` narrowing and everything below the `--top` cutoff all vanished — **15,959 of
  19,262 open postings** on a measured run at `--top 5`, of which 11,517 were hard-filter vetoes and 4,442
  were below the cutoff. All five exits are counted where the posting actually leaves, and `entered` is the
  ranker's own row count measured independently of them, so the stage's balance can genuinely fail. `boardwatch run` now
  prints how many postings were considered and how many fell below the cutoff.


- **Per-run funnel artifact, written on every `boardwatch run`.** Two halves — `funnel-<run_id>.json` and
  `funnel-<run_id>.md` — land in `<out>/<YYYY-MM-DD>/` beside that day's tailored résumés, outside the git
  tree. The Markdown names the board each lead came from, and every stage states its drop buckets with
  counts rather than leaving the reader to subtract. (As first shipped it did not account for every
  non-lead — postings ranked below the `--top` cutoff appeared in no counter at all. P0 item 3, above, closed that.)

  The funnel's head is the **open-posting corpus**, not the number of postings the scan listed. Those are
  different populations — a board answering 304 lists nothing, and `--no-scan` lists nothing at all — so
  scan counts are reported as context in their own block rather than as a funnel edge.

  Two stages carry reconciliations that can genuinely fail (`corpus` and `tailor`), plus two cross-checks
  that recount `tailored` and `leads_with_pdf` from the store rather than trusting what the pipeline
  reported. `attribution` and `verdict` are SQL partitions of the set they are compared against, so their
  balance holds for any input; they are labelled `derived` rather than presented as evidence.
  `leads_with_pdf` is read from `meta_json.typst_pdf_built`, not from a row count: `artifacts.uri`
  holds the `.typ` path whether or not a PDF ever compiled.

  Stages that nobody has instrumented report **`null`, never 0** — dedup has never run, and reporting 0
  duplicates would assert the opposite of the truth. Stages that balance by construction are labelled
  `derived`, and the artifact prints which stages could actually have failed. The artifact
  also carries the abstain rate for **every** rule in the catalog (including the ones that have never
  fired) and the count of evaluations that carry no run at all, which is expected only to shrink.

  Written from the same `finally` that closes the run row, so a run that crashed partway still leaves a
  funnel explaining how far it got. A failure to write it is reported and never fails the run.

- **`boardwatch run` — one command that runs scan → eligibility → tailor under a single run.**
  Until now nothing in `src/` spanned the three stages: `runs` rows were inserted only inside the
  scan's file lock, eligibility was judged later as a side-effect of `top`'s preflight, and
  tailoring was later still and one posting at a time. The only thing stitching them together was
  a shell script outside the package. `boardwatch run` owns one run row across all three stages and stamps
  `finished_at` only after the last, so a run means the pipeline, not the scan. (The row itself is created
  by the scan stage, inside the file lock — see below.)

  Options: `--top N` (how many ranked postings to tailor, default 8), `--out` (root for the dated
  `<out>/<YYYY-MM-DD>/` folders), `--resume`, and `--no-scan` to reuse already-fetched postings.

  Exit 2 if another scan holds the lock. Exit 1 when the run is fatally broken — no profile, a **systemic
  scan outage** (boards attempted and not one completed, i.e. DNS/network rather than a few dead slugs),
  or **every shortlisted lead failing to tailor**. Exit **0 otherwise, including when SOME boards were
  unreachable or SOME leads would not tailor**: those are counted, printed and persisted, but they are the
  documented norm across 85 watched boards and `boardwatch scan` already treats them as success, and an
  exit status that is non-zero every day carries no information.

  The two fatal cases above are the ones that would otherwise be silent empty days. The general
  zero-output guard — deciding when producing nothing was *provably right* — needs cohort completeness
  and is not built here.

  A contended run writes nothing at all: the run row is created by the scan stage, inside the file lock,
  so on the default path there is no window in which the schema is migrated or a row inserted before the
  lock is held. (`--no-scan` acquires no scan lock at all, so it migrates unlocked exactly as every other
  read command does.)

- **`run_id` is now written on every evaluation and every artifact.** The column was added
  previously but nothing populated it, so it was NULL everywhere. It is now threaded through
  `run_eligibility` → `write_evaluation` → `record_evaluation`, through the opt-in LLM lane, and
  through `run_tailor` into all three artifact inserts.

  A stage invoked on its own — `boardwatch tailor run`, `eligibility run`, `top`'s preflight —
  mints its own run rather than writing NULL, so that **NULL keeps exactly one meaning: the row
  predates run attribution.** Those rows cannot be backfilled (the evaluation ledger is
  append-only), so preserving that single meaning is what lets a funnel report separate them from
  live work instead of silently mixing the two. To keep `runs` a ledger of work rather than a
  command log, the eligibility preflight mints a run only once it has something pending.

  A cache hit keeps the run that first produced the evaluation, and a reused master résumé
  artifact keeps the run that first authored it — in both cases no row is written, and claiming
  otherwise would erase the distinction the column exists to record.

- **`boardwatch eligibility abstain` — abstain rate for every rule in the catalog, including
  rules that have never fired.** `eligibility summary` groups the requirement rows that exist,
  so a rule that has never been detected produces no group and is invisible in it; that is
  precisely backwards, because a rule which cannot fire is the one worth knowing about. The new
  command enumerates from the rule catalog and joins the observed counts onto that enumeration.

  Three states are kept distinct: `never fired` (no rows, so the rate is undefined and is
  **not** reported as 0% — that would rank a rule which has never fired as the healthiest in
  the catalog), `100%` (fires and never decides anything), and a real rate. Requirement rows
  carrying no `rule_id`, or a `rule_id` the catalog does not declare, are reported as their own
  buckets rather than folded into a rule; an undeclared `rule_id` exits non-zero, since the
  catalog is closed.

  On the current database it reports that 7 of 44 rules have never fired and 17 more fire
  without ever deciding — among them every clearance rule that fires (105 detections, zero met
  and zero unmet) and `work_auth:no_sponsorship_offered`, which has abstained on all 1,052
  postings that stated they offer no sponsorship.

- **Nullable `run_id` on `eligibility_evaluations` and `artifacts`** (Alembic revision
  `run_attribution`, additive). `eligibility_evaluations` is append-only, so rows predating the column can
  never be backfilled and NULL means "predates attribution", never zero. *(Landed inert; the entry above is
  what populates it. Both are in this same unreleased version.)*

### Changed

- **Funnel artifact version 1 → 2**, for the `sources` and `source_totals` sections.

- **`boardwatch doctor` now says "a run is in progress" rather than "a scan is in progress".** Since run
  attribution, an unfinished run is also a `boardwatch run` still tailoring or a standalone eligibility
  pass still judging — the old wording sent users looking for a held scan lock that was in fact free.

- **Ranking: a title role gate, and a neutral coverage for postings with no recognized
  skills.** These are one change in two parts, and they only work together — see below.

  A posting with no recognized skills used to have its `skill_coverage` component dropped and
  the remaining weights renormalized. That is not neutral: renormalizing is arithmetically
  identical to imputing the *weighted mean of the surviving components*, so dropping a
  component promotes a posting whenever that component would have scored below the rest.
  `skill_coverage` carries half the total weight and is undefined for about 18% of open
  postings, so the effect was large — a posting with **zero** recognized skills and a perfect
  title scored 0.9586 while a posting matching **7 of 8** skills scored 0.9168. §3.6 asks for
  "neutral, never a punitive 0 or free 1"; the old behaviour delivered the free 1 (29 of 80
  eligible zero-skill rows scored exactly 1.000). Coverage is now imputed at a neutral
  `zero_skill_coverage_prior` (default `0.50`, configurable), which puts that posting at
  0.7293 — exactly what a real 4-of-8 posting scores — and leaves the 7-of-8 row above it.
  `skill_coverage()` itself is unchanged, the assumption is named in `show` and in the one-line
  `why`, and the profile-side empty case still renormalizes.

- **`top` and `notify` now skip postings whose TITLE is not a software role.** Fuzzy title
  overlap cannot separate roles: Intel's "On Shift (IOS) Technology Development Engineer"
  matched the target "iOS Engineer" through the literal "(IOS)" token and ranked **first** at
  1.000. A categorical gate (`rank/role_gate.py`) runs beside the score and returns
  `swe` / `not_swe` / `uncertain`. `uncertain` passes through to scoring completely unchanged,
  which is why the gate keeps 100% of software-titled postings whose skills the taxonomy
  missed. A body-text gate was measured and rejected: those postings have long bodies
  genuinely empty of technical nouns, so no threshold separates them from noise.

  **A `not_swe` verdict is never silent.** It is counted in `top`'s footer, listed in `stats`,
  shown by `show <id>`, and viewable with `top --include-non-swe` — always carrying the exact
  title text that vetoed it. A gate you cannot audit is how a real job disappears unnoticed.

  Order inside the gate is load-bearing. The deny patterns guard themselves with
  `(?!.*\bsoftware\b)`, and a negative lookahead only sees text to its right, so evaluating
  denies first vetoes "Software Quality Engineer" — it matches `quality engineer`, looks right,
  and misses the "Software" on the left. Sixteen real software titles were buried that way in
  the prototype. Checking the software rescue first fixes all sixteen at no measured precision
  cost and runs 2.3x faster. Regression tests pin the ordering.

  Measured on 515 labelled postings: noise vetoed 76/76, targets kept 1.00, protected
  software-titled zero-skill rows kept 1.00, P@20 1.00, P@50 0.89 -> 1.00. The two changes are
  coupled: the imputation **alone** takes P@50 to 0.53, because it demotes the protected rows
  while leaving one-spurious-skill noise in place.

  Known and filed, not fixed: skill *extraction* precision is the root cause of the underlying
  symptom — "Deal Strategist" is tagged `Concurrency`, "Asset Tracking Technician" `Real-time`.
  That is separate work.

- **Extraction precision: four generic buzzwords dropped from the skill taxonomy.**
  `skill_coverage` is `|profile ∩ posting| / |posting|`, so a posting whose only recognized
  skill is one the profile also has scores a perfect 1.0. Four taxonomy tokens —
  `Scalability` (`\bscalab(le|ility)\b`), `Concurrency` (`\bconcurren(cy|t)\b|multi-thread`),
  `Real-time` (`\breal[- ]time\b`) and `Agile/Scrum` (`\bagile\b|\bscrum\b`) — matched
  non-technical prose ("scalable business processes", "multi-threaded deals", "real-time
  locating systems", "agile environment"). Each is in the profile, so as a posting's sole
  recognized skill it drove `skill_coverage` to 1.0 on ops/finance/sales roles the role gate
  correctly leaves `uncertain` (e.g. "Commercial Contracts Specialist", "Accounts Receivable
  Manager", "Deal Strategist"). On the live database this affected 257 such postings; 249 are
  non-software roles now dropped to the neutral zero-skill prior, and only 8 are genuine
  software postings (which the role gate keeps visible regardless). None of the four is ever
  the sole recognized skill on a labelled TARGET posting, so removing them costs no target
  coverage. Real, discriminating tokens — including `SQL`, `Distributed systems`,
  `Low latency / high throughput` and `High availability` — are untouched.

### Added

- **`boardwatch stats` — one read-only readout of where you stand.** Two views over your
  local database: qualified opportunities in a trailing window (`--days`, default 7),
  partitioned into `qualified` / `uncertain` / `ineligible` / `unevaluated`; and the
  discovery pipeline (seen → passes filters → not ineligible → tracked). The partition is
  deliberately honest — a posting with no current eligibility verdict is counted as
  `unevaluated`, never silently folded into `qualified`, so an empty eligibility ledger reads
  as "N unevaluated" rather than "0 qualified". Keyless and read-only; needs a profile
  (`boardwatch init`).

- **Workday support — a sixth provider, and the first with a composite board identity.**
  A Workday board is a host + tenant + career-site triple, so its target form is
  `workday:<host>/<tenant>/<CareerSite>` (pasting the career-site URL works too and derives
  the tenant). It is carried as a single composite slug, so `UNIQUE(provider, slug)` is
  unchanged and there is no migration — that constraint is in fact load-bearing here,
  because one tenant can serve several disjoint career sites. Site slugs are case-sensitive;
  hosts and tenants are normalized to lowercase.

  Workday's public API had to be measured rather than assumed, and every finding below has a
  regression test. It is POST-only (a GET returns 400), which is why `Fetcher` gained
  `post_json` — routed through the same per-host pacing and backoff, which matters because a
  2000-posting board is 100+ requests to one host. Its page size is a hard 20 (`limit=21`
  returns 400, it is not clamped). Its reported `total` is capped at 2000 while
  `offset >= 2000` wraps back to page 1, so pagination terminates on a short page rather
  than on `offset < total`, which would never terminate on a large board. And `timeType` is
  *not* an intern signal — it reads "Full time" on a real PhD-intern requisition — so the
  intern/new-grad signal is read from the `workerSubType` facet instead, via one bounded
  facet-filtered query per matched bucket, matched on the human-readable descriptor because
  the facet ids are tenant-specific. `timeType` and the matched descriptor are captured into
  `raw_json` because backfilling them would mean re-scanning every Workday board; nothing
  reads them yet.

  Two consequences worth stating plainly. Workday serves no `ETag` and no `Last-Modified`,
  so conditional fetches are inert for it and every scan re-reads the board. And no Workday
  boards are added to the bundled registry, so you watch them with `companies add` — until
  you do, `doctor` reports Workday connectivity as *not checked* rather than guessing.

  One deliberate deviation from the other five providers: `remote_policy` prefers Workday's
  structured `remoteType` field ("Fully Remote" / "Partially Remote") over the location-text
  heuristic, the same way the Ashby adapter already prefers its structured `isRemote`
  boolean. Tenants that do not set the field fall back to the heuristic.

- **Two eligibility rule families: `contract_not_fte` and `internship`.** The catalog now
  carries six families. `contract_not_fte` reads whether a posting declares a contract,
  contract-to-hire, temporary, fixed-term, 1099 or corp-to-corp engagement — or, symmetrically,
  permanent full-time employment — and resolves it against a stated employment-type
  preference (`fte_only`, `open_to_contract`, `contract_only`). `internship` reads whether a
  posting declares itself an internship or co-op and resolves it against whether you want
  them. Both are prompted by `init` and `profile edit` through the existing catalog-driven
  loop, so neither adds a question to maintain.

  Both default to `preference` rather than `blocker`, which is a measurement and not a
  guess: the patterns were tuned against 13,590 real postings and score 100% precision
  (internship) and 86% precision (contract) against the providers' own structured
  employment-type field. Only `blocker` can produce `ineligible`, so at the shipped default a
  false positive costs one visible informational row and hides nothing. Opt either into
  `blocker` with `eligibility policy set <family> blocker`.

  Known limit, stated plainly: the engine reads a posting's body and never its title, so
  internship recall is 27% of postings whose title names an internship, and 20% of those whose
  provider states an internship employment type. A posting titled "Software Engineering Intern"
  whose body never says so is not detected. Raising that needs the title in the engine's input,
  which is a separate change.

### Changed

- **Editing the rule catalog re-evaluates every stored verdict.** Adding the two families
  moves `rules_hash`, so the first `eligibility run` after upgrading re-evaluates the whole
  corpus and writes fresh rows. Prior verdicts are superseded, never rewritten — the
  eligibility tables remain append-only.

- **`--verify` on `companies add` and `companies import`.** Opt-in live board probe before
  the watch is written, reusing each provider's existing `healthcheck`. Reachable boards are
  watched (reachable-but-empty is watched with a note); boards that return 404, error, or
  cannot be reached are skipped instead of written, since an unreachable board is absence of
  evidence rather than evidence the slug is wrong. `import --verify` exits non-zero when it
  skipped any entry, so a partial import cannot be mistaken for a complete one. Both
  commands remain offline by default.

### Fixed

- **`companies import` now rejects duplicate `provider:slug` rows.** It built validated
  entries but never ran the catalog's `validate_entries` integrity check, so a file listing
  the same board twice imported silently.

- **`httpx.TooManyRedirects` and `httpx.DecodingError` now surface as `FetchFailure`.** Both
  are `RequestError` but not `TransportError`, so they escaped `Fetcher`'s conversion and
  every provider's `except FetchFailure`, which let a redirect loop traceback `doctor`
  instead of reporting an unreachable board. Only the conversion widened — the retry
  predicate is unchanged, so these fail fast rather than being retried.

- **A provider that raises is contained to one board.** `scan` and `doctor` guard the
  per-board `board_url()` / `healthcheck()` calls, so a single malformed stored target no
  longer aborts the whole run. `doctor` also stops reporting a provider it never probed
  (no watched board and no registry entry) as unreachable.

## [0.2.0] - 2026-08-04

### Added

- **`boardwatch tailor` command (`init`/`validate`/`run`).** Tailors an authored,
  structured YAML résumé (`{config_dir}/resume.yaml`, scaffolded by `tailor init`)
  against one posting's extracted JD skills: deterministic bullet selection plus
  whole-token synonym substitution from a small, bundled, frozen equivalence table —
  never free-text generation. A no-fabrication guarantee re-verifies the output against
  the master résumé before anything is written, rejecting rather than degrading on
  failure. Renders Typst source and a best-effort PDF (local `typst` binary, if present)
  to `{data_dir}/tailored/`. Tier A: local-only, no network, no LLM. `profile.text` from
  `boardwatch init` is never imported into a tailored résumé.
- **`tailor run --tier-b` (alias `--llm`), opt-in LLM résumé rewording.** Off by default;
  requires `llm.enabled` and `llm.resume_tailoring` (a new key reusing the existing
  `[llm]` block — no new config keys or secrets) plus `BOARDWATCH_LLM_API_KEY`. Per
  bullet, a proposed rewrite is kept only if it passes a deterministic overmatch filter
  and a fail-closed entailment judge (blind to the job description); anything else falls
  back to the Tier A text for that bullet. This is evidence, not proof — unlike Tier A's
  no-fabrication guarantee, Tier B output is not structurally verified. Writes the plain
  Tier A file alongside a second, clearly marked `resume_tailored_llm` artifact/file with
  a `rewritten_from` lineage edge back to the Tier A artifact; reworded bullets are
  annotated `// reworded (Tier B)` in the rendered source. Tier A itself never calls a
  model, regardless of Tier B's settings.
- **`notify` command.** Pushes NEW matching postings to enabled channels since the last
  `notify` run; a standalone sibling of `digest`, chain it after `scan` (`boardwatch scan
  && boardwatch notify`). Two zero-new-dependency channels, both off by default: a webhook
  (one dual-key payload that renders on Slack, Discord, or a generic consumer, enabled with
  `config set notify.webhook_enabled true` and a URL from `BOARDWATCH_NOTIFY_WEBHOOK_URL`
  in the environment only, never in `config.toml`) and a best-effort desktop notification
  (macOS/Linux, enabled with `config set notify.desktop_enabled true`, degrading non-fatally
  elsewhere). `--dry-run` previews without delivering or advancing the notify cursor.
- **Workable and SmartRecruiters providers.** boardwatch now covers five keyless ATS
  providers: Greenhouse, Lever, Ashby, Workable, and SmartRecruiters.
- **`detail_fetch_budget` setting.** Caps how many unseen postings SmartRecruiters'
  per-posting detail fetches will pull in a single scan (default 50, range 1-1000, takes
  effect next scan).

## [0.1.0] - 2026-08-01

First public release.

### Added

- **Job radar over official ATS APIs.** Watch company boards on Greenhouse, Lever, and
  Ashby. No scraping, no credentials, no accounts.
- **Change detection.** `digest` reports what is new, reopened, updated, or closed since
  your last run, and `top --new` limits ranking to postings you have not seen.
- **Deterministic eligibility engine.** Work authorization, experience, clearance, and
  degree requirements are extracted with auditable rules, and every requirement it surfaces
  cites the exact job description span it came from. No model is involved in the default path.
- **Persisted eligibility audit trail.** `show` renders a per-posting verdict with its
  supporting evidence, so a decision can be re-checked later rather than taken on trust.
- **Ranking against your profile.** `top` scores open postings, with a live component
  breakdown available in `show`.
- **Application tracking.** `track` records your own funnel state per job.
- **Data portability.** `export` writes every open or tracked posting with its verdict and
  funnel state as JSONL or CSV. `top --json` emits machine-readable rankings.
- **Opt-in LLM eligibility extraction.** Disabled by default. When enabled, the model acts
  only as a span locator: it returns verbatim job description quotes, every one of which is
  validated as a literal substring of the source before use. Fabricated citations are
  dropped. LLM findings are advisory and can never produce an "ineligible" verdict.
- **Local-first storage.** Its primary store is one SQLite database in your platform
  data directory; the opt-in LLM tier also caches raw responses there as plain files on
  disk. Overridable with `--data-dir`. No server, no cloud, no telemetry.
- **`doctor`** for connectivity, per-board health and freshness, and database integrity.

[0.2.0]: https://github.com/mit112/boardwatch/releases/tag/v0.2.0
[0.1.0]: https://github.com/mit112/boardwatch/releases/tag/v0.1.0

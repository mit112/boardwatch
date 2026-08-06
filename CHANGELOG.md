# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **`boardwatch run` — one command that runs scan → eligibility → tailor under a single run.**
  Until now nothing in `src/` spanned the three stages: `runs` rows were inserted only inside the
  scan's file lock, eligibility was judged later as a side-effect of `top`'s preflight, and
  tailoring was later still and one posting at a time. The only thing stitching them together was
  a shell script outside the package. `boardwatch run` mints the run row before the first stage
  and stamps `finished_at` after the last, so a run means the pipeline, not the scan.

  Options: `--top N` (how many ranked postings to tailor, default 8), `--out` (root for the dated
  `<out>/<YYYY-MM-DD>/` folders), `--resume`, and `--no-scan` to reuse already-fetched postings.

  Exit 2 if another scan holds the lock, 1 only if the run is fatally broken, and **0 otherwise —
  including when some boards were unreachable or some leads would not tailor.** Those are counted,
  printed and persisted, but they are the documented norm across 85 watched boards and `boardwatch scan`
  already treats them as success; an exit status that is non-zero every day carries no information.

  A contended run writes nothing at all: the run row is created by the scan stage, inside the file lock,
  so there is no window in which the schema is migrated or a row inserted before the lock is held.

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

### Changed

- **`boardwatch doctor` now says "a run is in progress" rather than "a scan is in progress".** Since run
  attribution, an unfinished run is also a `boardwatch run` still tailoring or a standalone eligibility
  pass still judging — the old wording sent users looking for a held scan lock that was in fact free.

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
  `run_attribution`, additive). Nothing writes it yet, so it stays NULL until the write paths
  thread it; `eligibility_evaluations` is append-only, so rows predating the column can never be
  backfilled and NULL means "predates attribution", never zero.

### Changed

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

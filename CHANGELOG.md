# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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

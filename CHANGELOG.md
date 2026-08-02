# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[0.1.0]: https://github.com/mit112/boardwatch/releases/tag/v0.1.0

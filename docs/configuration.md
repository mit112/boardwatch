# Configuration

Boardwatch reads `config.toml` from its config directory. Use `boardwatch config
show` to see current values (and their defaults) and `boardwatch config set <key>
<value>` to change them. All keys are validated at both `set` time and load time;
out-of-range values are rejected with a clear error. Weights are read live on
every `top` run (no restart needed).

`config show` prints every key on this page except `llm.base_url` and
`lane_new_companies_per_run_overrides`, each with its value, its default, its range and when it
takes effect. **An unknown key in `config.toml` is ignored silently**, so read any hand edit back
with `config show` — the file alone cannot tell a typo from success.

### Scanning and politeness

| Key | Type / Range | Default | What it controls | Takes effect |
|---|---|---|---|---|
| `per_host_delay_seconds` | float, ≥ 0.25 | 1.0 | Seconds between two requests to one host | next scan |
| `pace_from_request_start` | bool | `false` | `true` measures that delay between request starts (a true 1/delay ceiling); `false` measures it from the previous request's end | next scan |
| `retry_attempts` | int, 1–10 | 3 | Total attempts per request (1 = no retry) | next scan |
| `fetch_deadline_seconds` | float, > 0 | 240.0 | Wall-clock seconds one request may take, all attempts included | next scan |
| `scan_workers` | int, 1–32 | 4 | Boards fetched in parallel | next scan |
| `board_deadline_seconds` | float, > 0 | 600.0 | Wall-clock seconds one board may take before it is recorded failed | next scan |
| `detail_fetch_budget` | int, 1–10000 | 50 | Per-posting detail fetches per board per scan (providers whose list carries no body) | next scan |
| `validator_max_age_hours` | int, ≥ 1 | 24 | Hours after which a board's cached `ETag`/`Last-Modified` is dropped and the board refetched unconditionally | next scan |
| `busy_timeout_ms` | int | 5000 | SQLite busy timeout in milliseconds | next command |

### Ranking and the slate

| Key | Type / Range | Default | What it controls | Takes effect |
|---|---|---|---|---|
| `seen_ttl_days` | int, ≥ 1 | 7 | Days a surfaced-but-unbuilt lead stays suppressed | next top/run |
| `slate_ceiling` | int, ≥ 0 | 0 (exactly `--top`) | Most leads one run may deliver. The slate grows past `--top` only by tier 0–1 leads (entry-marked software titles for an entry-band profile, and decided-eligible software leads); above `gate.depth` the gate judges up to this many leads per run | next run |
| `location_filter_mode` | `soft` \| `hard` | `soft` | `soft` ranks by location only; `hard` vetoes a mismatch | next top |
| `zero_skill_coverage_prior` | float, [0, 1] | 0.50 | Score given when a posting lists no detectable skills | next top |
| `recency_half_life_days` | float | 14.0 | Days at which the recency score halves | next top |
| `weights.skill_coverage` | float, [0, 1] | 0.50 | Weight of skill coverage in the score | next top |
| `weights.title_match` | float, [0, 1] | 0.25 | Weight of the fuzzy title match | next top |
| `weights.recency` | float, [0, 1] | 0.15 | Weight of recency | next top |
| `weights.location_fit` | float, [0, 1] | 0.10 | Weight of location fit | next top |

### Runs, liveness and the death probe

These govern `boardwatch run`; [the unattended run guide](unattended-run.md) explains how to size
the two death-probe budgets.

| Key | Type / Range | Default | What it controls | Takes effect |
|---|---|---|---|---|
| `reap_stale_after_hours` | int, ≥ 1 | 24 | Age at which an unfinished run row is treated as crashed | next run |
| `death_probe_budget` | int, ≥ 0 | 50 | Liveness probes per run against postings no board scan enumerates (0 disarms it) | next run |
| `death_probe_company_budget` | int, ≥ 0 | 100 | List-endpoint reads per run, one per company, for providers that publish a whole board (Ashby, Greenhouse, Lever); 0 disarms that half | next run |
| `death_probe_ttl_hours` | int, ≥ 1 | 24 | Hours before such a posting may be probed again | next run |
| `form_question_fetch_budget` | int, ≥ 0 | 100 | Greenhouse application forms fetched per queue sync, looking for a citizenship or export-control hard stop the job description never states (0 disarms it) | next run |

### Discovery lanes

Every lane is off until you name it in `lanes_enabled`. Read the README's
[Responsible use](https://github.com/mit112/boardwatch#responsible-use--legality) section before
enabling one: the lanes are held to a different standard than the ATS boards.

| Key | Type / Range | Default | What it controls | Takes effect |
|---|---|---|---|---|
| `lanes_enabled` | comma-separated names | empty | Which lanes run: `linkedin`, `indeed`, `hiringcafe`, `jsonld`, `jobapps`. Blank disarms every lane | next run |
| `lane_search_hubs` | JSON array | empty | LinkedIn search hubs, e.g. `'["Austin, TX", "Boston, MA"]'`; blank disables hub nets | next run |
| `lane_github_lists` | comma-separated `owner/repo` | empty | Public GitHub job lists to read, e.g. `SimplifyJobs/New-Grad-Positions`; blank reads none | next run |
| `lane_new_companies_per_run` | int, ≥ 0 | 10 | Companies one lane may add per run (already-known ones are free) | next run |
| `lane_new_companies_per_run_overrides` | table of lane name → int ≥ 0 or `"unlimited"` | `jobapps` and `hiringcafe` unlimited | Per-lane replacements for `lane_new_companies_per_run`; an `"indeed.tier1"` key bounds the Indeed lane's tier-1 admissions separately. Hand-edit only, and not printed by `config show` | next run |
| `lane_posting_budget` | int, ≥ 1 | 60 | Job-description requests one lane may make per run (to switch a lane off, leave it out of `lanes_enabled`) | next run |
| `lane_search_pages` | int, ≥ 1 | 1 | Search pages one lane requests per facet | next run |
| `lane_hub_combos_per_run` | int, ≥ 0 | 12 | LinkedIn term/hub combinations searched per run | next run |
| `lane_company_combos_per_run` | int, ≥ 0 | 0 (off) | Per-company LinkedIn searches per run. Each asks your first target title at one watched company and takes a slot from `lane_new_companies_per_run` | next run |
| `lane_hub_distance_miles` | int, ≥ 0 | 25 | LinkedIn hub search radius in miles | next run |
| `indeed_search_pages` | int, ≥ 1 | 1 | Search pages the `indeed` lane requests per facet | next run |
| `indeed_results_per_page` | int, 1–100 | 100 | Hits the `indeed` lane asks for per search page | next run |
| `jobapps_discovery_dir` | absolute path | unset | The discovery output folder of a separate job-apps tool, read by the `jobapps` lane (which reports an error without it) | next run |
| `jobapps_queue_dir` | absolute path | unset | That tool's promoted queue, read in addition to `jobapps_discovery_dir` | next run |

## `[notify]`

Delivery channels for `boardwatch notify`. Both flags are off by default; enabling one is
an explicit opt-in to outbound delivery.

| Key | Type / Range | Default | Takes effect |
|---|---|---|---|
| `notify.desktop_enabled` | bool | `false` | next notify |
| `notify.webhook_enabled` | bool | `false` | next notify |

The webhook URL is not a config key — it is a secret and is read only from the
environment:

    export BOARDWATCH_NOTIFY_WEBHOOK_URL=...

One payload works for Slack incoming webhooks, Discord webhooks, and generic/structured
consumers. Like the LLM API key below, this URL is never stored in `config.toml`.

A second env-only URL is the unattended run's dead-man's-switch: a successful `boardwatch run`
pings it, so an external monitor can alert when a scheduled run never happens (see
[the unattended run guide](unattended-run.md)). Presence-gated, off unless set:

    export BOARDWATCH_HEARTBEAT_URL=https://hc-ping.com/<your-check-uuid>

A third carries the opposite half: a run that succeeded while degraded still pings the heartbeat,
so `boardwatch run` also POSTs its end-of-run alerts to `BOARDWATCH_ALERT_URL` when that is set —
any endpoint that accepts a text body, such as a healthchecks.io `/fail` URL. Only those alerts
are sent, never the routine per-board or per-lead errors a normal run also logs. Presence-gated
too, and a failed post never fails the run.

## `[gate]`

The headless final-eligibility judge that runs inside `boardwatch run` between ranking and
tailoring. It calls the `claude` CLI on your `PATH` under your own Claude account, and
[SECURITY.md](../SECURITY.md) lists what each call sends. Off by default; arming it is a hand edit of
`config.toml` (`config set` refuses `gate.*` keys and there is no toggle), and it spends Claude
usage on every run while on. Every seam around the call fails open: a missing binary, a
timeout, a non-zero exit or an unreadable response drops that batch's verdicts, never a lead.
`boardwatch config show` prints every `gate.*` key — read them back there after any edit, because
an unknown key under `[gate]` is ignored silently, so the file alone cannot tell a typo from
success.

| Key | Type / Range | Default | What it controls | Takes effect |
|---|---|---|---|---|
| `gate.enabled` | bool | `false` | Arms the judge | next run |
| `gate.claude_config_dir` | absolute path (`~` is not expanded) | unset | `CLAUDE_CONFIG_DIR` for the headless call, i.e. which Claude account it uses | next run |
| `gate.model` | string, a `claude` model alias | `sonnet` | The model the judge runs on | next run |
| `gate.batch_size` | int, ≥ 1 | 13 | Leads per call | next run |
| `gate.call_timeout_s` | int, ≥ 1 | 300 | Seconds per call | next run |
| `gate.effort` | `low` \| `medium` \| `high` \| `xhigh` \| `max` | unset | The call's `--effort`; unset passes no flag, so the CLI default applies | next run |
| `gate.depth` | int, ≥ 0 | 0 | Leads judged, counted against `--top` delivered; 0 = only the shortlist | next run |
| `gate.refresh_budget` | int, ≥ 0 | 0 (off) | Standing-queue leads re-judged per run when their reading is stale | next run |
| `gate.backlog_budget` | int, ≥ 0 | 0 (off) | Unjudged in-field postings below the judged slate sent to the judge per run | next run |
| `gate.seniority_hold` | bool | `false` | Hold a lead for review when the judge reads its body as above your target band; off, the reading is still recorded | next run |

## Résumé tailoring

`boardwatch tailor` introduces no new config keys. It follows the same `config_dir` /
`data_dir` conventions as everything else:

| Path | Purpose |
|---|---|
| `{config_dir}/resume.yaml` | Your authored, structured résumé (written by `tailor init`, read by `tailor validate`/`tailor run`). |
| `{data_dir}/tailored/` | Output directory for rendered LaTeX source and its compiled PDF, one `<Your Name>_<Company>_<Role>.{tex,pdf}` pair per posting. The untailored-master safety net and the Tier B render take a `_untailored` / `_llm` suffix so all three stay apart. |

### Tier B (opt-in LLM rewording)

`tailor run --tier-b` adds exactly one new key, `llm.resume_tailoring`, as a second gate
alongside `llm.enabled` on the existing `[llm]` block below — it does not introduce a new
config section, a new secret, or a separate credential/endpoint. Everything else it needs
(`enabled`, `provider`, `model`, `base_url`, `max_calls_per_run`, `BOARDWATCH_LLM_API_KEY`)
is the same `[llm]` block already used by the opt-in LLM eligibility-extraction tier.

| Key | Type / Range | Default | Takes effect |
|---|---|---|---|
| `llm.resume_tailoring` | bool | `false` | next `tailor run --tier-b` |
| `llm.resume_tailoring_via_agent` | bool | `false` | next `tailor rewrite request`/`screen`/`apply` |

Both flags are settable via `boardwatch config set` or interactively via `boardwatch
settings toggle` (see [Settings menu](#settings-menu) below) — `config set llm.*` is no
longer reserved for these four booleans. `provider`, `model`, and `base_url` are a
different matter: they still require a hand-edit to `{config_dir}/config.toml`:

```bash
boardwatch config set llm.enabled true
boardwatch config set llm.resume_tailoring true
```

```toml
# config.toml — provider/model/base_url are hand-edit only
[llm]
provider = "anthropic"
model = "claude-..."
```

`--tier-b` requires both `llm.enabled` and `llm.resume_tailoring` to be `true`, plus a
resolvable `BOARDWATCH_LLM_API_KEY`; missing any of them exits 1 before writing anything
rather than silently falling back to Tier A for the whole run. (A per-bullet fallback to
Tier A text is a different, expected thing — see [tailoring](tailoring.md#tier-b-opt-in-llm).)

**Tier B agent lane (no API key).** `llm.resume_tailoring_via_agent` gates a separate,
subscription-driven Tier B lane — the three-command `tailor rewrite request` /
`screen` / `apply` handshake driven by the `tailor-rewrite` boardwatch skill, where
Claude Code itself proposes and judges rewrites instead of a metered API provider (see
[tailoring](tailoring.md#tier-b-without-an-api-key-agent-lane) for the full flow).
Unlike `--tier-b`, this gate is checked **alone** — it needs neither `llm.enabled` nor
`BOARDWATCH_LLM_API_KEY`, because boardwatch never makes an LLM call itself in this
lane:

```toml
[llm]
resume_tailoring_via_agent = true
```

Each of the three `tailor rewrite` commands checks this flag before touching the data
directory and exits 1 if it's unset. The `llm.max_calls_per_run` budget still applies
internally, but it's **advisory** in this lane, not a hard spend limit: subscription
calls aren't API-metered, so it's sized wide enough to never truncate a legitimate run
and acts only as a soft cap on how many bullets get proposed and judged in one pass.

**`max_calls_per_run` in a Tier B context.** Tier B spends 2 calls per surviving bullet
(one to propose a rewrite, one for the entailment judge) against `llm.max_calls_per_run` —
default 50, so about 25 bullets per run before the rest fall back with
`drop_reason: "budget"`. Despite the name, this is **not a shared pool**: the number is a
ceiling applied *separately* to each **résumé** in the tailor lane and to each **invocation**
of the eligibility LLM lane, so the two never draw the same calls down and a single
`boardwatch` invocation can legitimately spend more than 50 in total. The budget is
consumed even on a cache hit (a deliberate choice, so behaviour stays deterministic across
runs), which means re-running the same posting does **not** extend it; raise
`llm.max_calls_per_run` in `config.toml` if a résumé's bullet count routinely exceeds it.

## Career-profile bundle

`boardwatch profile-bundle` introduces no config keys either. Its root is resolved at the
command boundary from `config_dir`, with a per-invocation override:

| Path | Purpose |
|---|---|
| `{config_dir}/career-profile/` | The bundle root — revisions, drafts, evidence blobs, approval stamps. Default for every `profile-bundle` command. |
| `{config_dir}/career-profile/local-sources.yaml` | Machine-local map of logical source IDs to absolute roots. Root-only: excluded from every revision, from both digests, and from every export. |

`--bundle PATH` overrides the root on any `profile-bundle` command. The path is machine-local
and deliberately **not** a `Settings` field: it does not participate in lead selection and does
not change `policy_version`, so relocating a bundle (an encrypted backup volume, say) needs no
config change — just `--bundle`.

`config_dir` itself follows the usual resolution, `BOARDWATCH_CONFIG_DIR` then the platform
config directory, so the macOS default root is `~/Library/Application Support/boardwatch/career-profile/`.

The bundle is separate from `{config_dir}/resume.yaml` and does not feed it. `boardwatch tailor`
reads `resume.yaml` unless `--resume` names another file, and a run renders from the bundle only
with `run --project`, through [projection](projection-rendering.md). See
[the authoring guide](profile-bundle-authoring.md) for the format, the exit contract, and recovery.

## Level-aware gating

Only a confident hit hides a posting. A title carrying a level token boardwatch cannot resolve —
and most bare `L2`/`T3` tokens are not levels at all, but OSI layers, support tiers or facility
codes — is **abstained**: passed through, and counted under the table so you can see the gate's
blind spot rather than inherit it silently. To resolve levels for a company you watch, bind it to one
of the shipped company-free rung ladders in `{config_dir}/leveling-bindings.yaml`:

```yaml
bindings:
  - provider: workday
    slug: example.wd1.myworkdayjobs.com/example/careers
    scheme: ic_1_to_7
```

The schemes themselves ship with boardwatch and name no companies — which company uses which ladder
is yours to declare, exactly like your board list. With no bindings file, every level token abstains,
which is the honest default.

## Settings menu

`boardwatch settings` is a read-only view of every opt-in feature (the `[llm]` and
`[notify]` booleans): its current state (ON/OFF), what it does, and what it sends
anywhere it leaves your machine. It also prints an always-on block — `scan` connects
over HTTPS to each ATS host you watch; that's core function, not a toggle — and secret
status as `set`/`unset` for `BOARDWATCH_LLM_API_KEY` and `BOARDWATCH_NOTIFY_WEBHOOK_URL`,
never the value itself. For numeric tuning (politeness, ranking weights,
`llm.max_calls_per_run`), it points you to `boardwatch config`.

`boardwatch settings toggle` is the same view, made interactive: pick a listed number to
flip that feature on/off (blank to quit), and the menu re-renders after each flip so you
can see the new state before quitting. It shares the exact same writer as `boardwatch
config set` — same validation, same refusal if `config.toml` already contains a secret —
so there is no separate code path between the two surfaces.

The four `llm.*` booleans are settable through either surface:

| Key | Type / Range | Default | Takes effect |
|---|---|---|---|
| `llm.enabled` | bool | `false` | next relevant run |
| `llm.eligibility_extraction` | bool | `false` | next relevant run |
| `llm.resume_tailoring` | bool | `false` | next `tailor run --tier-b` |
| `llm.resume_tailoring_via_agent` | bool | `false` | next `tailor rewrite` |

`notify.desktop_enabled`/`notify.webhook_enabled` (see [`[notify]`](#notify) above) are
also settable through both surfaces. `llm.max_calls_per_run` is settable via
`boardwatch config set` **only** — `settings toggle` is a numbered on/off flipper over
the six boolean features above and does not handle scalar keys. `llm.provider`,
`llm.model`, and `llm.base_url` remain **hand-edit only** in `config.toml` — `config
set` and `settings toggle` both refuse them by design, since they aren't booleans with
an on/off state.

**Prerequisites, correctly stated.** Turning on `llm.resume_tailoring_via_agent` does
**not** require `llm.enabled` or an API key — it's a separate, subscription-driven lane
where Claude Code itself proposes and judges the rewrite (see
[tailoring](tailoring.md#tier-b-without-an-api-key-agent-lane)). The two API lanes,
`llm.eligibility_extraction` and `llm.resume_tailoring`, do require `llm.enabled` **and**
a resolvable `BOARDWATCH_LLM_API_KEY` **and** `llm.model`. `boardwatch settings` shows
any unmet prerequisite next to a feature that's ON but can't actually run yet.

## Secrets

By default boardwatch uses no credentials, so `config.toml` never contains secrets and
there is nothing to leak. The opt-in LLM tier reads its API key only from the
environment:

    export BOARDWATCH_LLM_API_KEY=...

Secrets are never stored in `config.toml`, and `boardwatch config show` never prints a key
value (it shows only whether one is set). `boardwatch config set` refuses to write a
reserved secret key into `config.toml`. A persistent-secret file at
`{config_dir}/secrets.toml` is reserved for a future release and is not read yet.

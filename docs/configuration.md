# Configuration

Boardwatch reads `config.toml` from its config directory. Use `boardwatch config
show` to see current values (and their defaults) and `boardwatch config set <key>
<value>` to change them. All keys are validated at both `set` time and load time;
out-of-range values are rejected with a clear error. Weights are read live on
every `top` run (no restart needed).

| Key | Type / Range | Default | Takes effect |
|---|---|---|---|
| `per_host_delay_seconds` | float, ≥ 0.25 | 1.0 | next scan |
| `retry_attempts` | int, 1–10 | 3 | next scan |
| `scan_workers` | int, 1–8 | 4 | next scan |
| `detail_fetch_budget` | int, 1–1000 | 50 | next scan |
| `weights.skill_coverage` | float, [0, 1] | 0.50 | next top |
| `weights.title_match` | float, [0, 1] | 0.25 | next top |
| `weights.recency` | float, [0, 1] | 0.15 | next top |
| `weights.location_fit` | float, [0, 1] | 0.10 | next top |

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

## Résumé tailoring

`boardwatch tailor` introduces no new config keys. It follows the same `config_dir` /
`data_dir` conventions as everything else:

| Path | Purpose |
|---|---|
| `{config_dir}/resume.yaml` | Your authored, structured résumé (written by `tailor init`, read by `tailor validate`/`tailor run`). |
| `{data_dir}/tailored/` | Output directory for rendered Typst source and best-effort PDFs, one `tailored-<posting-id>.{typ,pdf}` pair per posting. |

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
Tier A text is a different, expected thing — see the README's Tier B section.)

**Tier B agent lane (no API key).** `llm.resume_tailoring_via_agent` gates a separate,
subscription-driven Tier B lane — the three-command `tailor rewrite request` /
`screen` / `apply` handshake driven by the `tailor-rewrite` boardwatch skill, where
Claude Code itself proposes and judges rewrites instead of a metered API provider (see
the README's "Tier B without an API key (agent lane)" section for the full flow).
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
(one to propose a rewrite, one for the entailment judge) out of the *same*
`llm.max_calls_per_run` budget the eligibility LLM lane shares — default 50, so about 25
bullets per run before the rest fall back with `drop_reason: "budget"`. The budget is
consumed even on a cache hit (a deliberate choice, so behaviour stays deterministic across
runs), which means re-running the same posting does **not** extend it; raise
`llm.max_calls_per_run` in `config.toml` if a résumé's bullet count routinely exceeds it.

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

The four `llm.*` booleans plus `llm.max_calls_per_run` are settable through either
surface:

| Key | Type / Range | Default | Takes effect |
|---|---|---|---|
| `llm.enabled` | bool | `false` | next relevant run |
| `llm.eligibility_extraction` | bool | `false` | next relevant run |
| `llm.resume_tailoring` | bool | `false` | next relevant run |
| `llm.resume_tailoring_via_agent` | bool | `false` | next relevant run |
| `llm.max_calls_per_run` | int, ≥ 1 | 50 | next relevant run |

`notify.desktop_enabled`/`notify.webhook_enabled` (see [`[notify]`](#notify) above) are
also settable through both surfaces. `llm.provider`, `llm.model`, and `llm.base_url`
remain **hand-edit only** in `config.toml` — `config set` and `settings toggle` both
refuse them by design, since they aren't booleans with an on/off state.

**Prerequisites, correctly stated.** Turning on `llm.resume_tailoring_via_agent` does
**not** require `llm.enabled` or an API key — it's a separate, subscription-driven lane
where Claude Code itself proposes and judges the rewrite (see the README's "Tier B
without an API key (agent lane)" section). The two API lanes,
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

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

`boardwatch config set llm.*` is reserved (see below) and refuses to write any `llm.*`
key, `resume_tailoring` included. Enable it by editing `{config_dir}/config.toml`
directly:

```toml
[llm]
enabled = true
resume_tailoring = true
provider = "anthropic"
model = "claude-..."
```

`--tier-b` requires both `llm.enabled` and `llm.resume_tailoring` to be `true`, plus a
resolvable `BOARDWATCH_LLM_API_KEY`; missing any of them exits 1 before writing anything
rather than silently falling back to Tier A for the whole run. (A per-bullet fallback to
Tier A text is a different, expected thing — see the README's Tier B section.)

**`max_calls_per_run` in a Tier B context.** Tier B spends 2 calls per surviving bullet
(one to propose a rewrite, one for the entailment judge) out of the *same*
`llm.max_calls_per_run` budget the eligibility LLM lane shares — default 50, so about 25
bullets per run before the rest fall back with `drop_reason: "budget"`. The budget is
consumed even on a cache hit (a deliberate choice, so behaviour stays deterministic across
runs), which means re-running the same posting does **not** extend it; raise
`llm.max_calls_per_run` in `config.toml` if a résumé's bullet count routinely exceeds it.

## Secrets (reserved for the v1.1 LLM tier)

boardwatch v1 uses no credentials, so `config.toml` never contains secrets and there is
nothing to leak. The opt-in LLM tier (planned for v1.1) will read its API key only from
the environment:

    export BOARDWATCH_LLM_API_KEY=...

Secrets are never stored in `config.toml`, and `boardwatch config show` never prints a key
value (it shows only whether one is set). `boardwatch config set` refuses to write a
reserved secret key into `config.toml`. A persistent-secret file at
`{config_dir}/secrets.toml` is reserved for a future release and is not read yet.

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

## Secrets (reserved for the v1.1 LLM tier)

boardwatch v1 uses no credentials, so `config.toml` never contains secrets and there is
nothing to leak. The opt-in LLM tier (planned for v1.1) will read its API key only from
the environment:

    export BOARDWATCH_LLM_API_KEY=...

Secrets are never stored in `config.toml`, and `boardwatch config show` never prints a key
value (it shows only whether one is set). `boardwatch config set` refuses to write a
reserved secret key into `config.toml`. A persistent-secret file at
`{config_dir}/secrets.toml` is reserved for a future release and is not read yet.

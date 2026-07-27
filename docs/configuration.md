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
| `weights.skill_coverage` | float, [0, 1] | 0.50 | next top |
| `weights.title_match` | float, [0, 1] | 0.25 | next top |
| `weights.recency` | float, [0, 1] | 0.15 | next top |
| `weights.location_fit` | float, [0, 1] | 0.10 | next top |

## Secrets (reserved for the v1.1 LLM tier)

boardwatch v1 uses no credentials, so `config.toml` never contains secrets and there is
nothing to leak. The opt-in LLM tier (planned for v1.1) will read its API key only from
the environment:

    export BOARDWATCH_LLM_API_KEY=...

Secrets are never stored in `config.toml`, and `boardwatch config show` never prints a key
value (it shows only whether one is set). `boardwatch config set` refuses to write a
reserved secret key into `config.toml`. A persistent-secret file at
`{config_dir}/secrets.toml` is reserved for a future release and is not read yet.

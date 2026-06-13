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

# Run the full daily pipeline unattended

`scan` only fetches boards. The full daily job is **`boardwatch run`**: one command that
scans, evaluates eligibility, ranks, and tailors a résumé for the top leads, attributing every
row it writes to a single `runs` entry and dropping a `morning-<run_id>.{json,md}` report
beside the day's output. This is the command to schedule for an unattended daily driver.

Schedule it exactly like `scan` (see [scheduling](scheduling.md)) — same cron, launchd, and systemd mechanics — with the
command swapped from `scan` to `run` and its own log file. A macOS launchd example:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
  <dict>
    <key>Label</key>
    <string>com.boardwatch.run</string>
    <key>ProgramArguments</key>
    <array>
      <string>/absolute/path/to/boardwatch</string>
      <string>run</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
      <key>Hour</key><integer>8</integer>
      <key>Minute</key><integer>0</integer>
    </dict>
    <key>StandardOutPath</key>
    <string><home>/Library/Logs/boardwatch-run.log</string>
    <key>StandardErrorPath</key>
    <string><home>/Library/Logs/boardwatch-run.log</string>
  </dict>
</plist>
```

Save it as `~/Library/LaunchAgents/com.boardwatch.run.plist`, then load it the same way:

```console
$ launchctl bootstrap "gui/$(id -u)" ~/Library/LaunchAgents/com.boardwatch.run.plist
$ launchctl print "gui/$(id -u)/com.boardwatch.run"
```

What to expect from an unattended run:

- **It exits 0 unless something is genuinely fatal.** An unreachable board or an un-tailorable
  lead is a normal partial day, not a failure — so a non-zero exit is worth alerting on. A
  steady-state day where every eligible posting was already handled can legitimately exit 0 with
  no new leads; the zero-output guard fails a run only when it produced nothing it provably
  should have.
- **It makes no network LLM calls by default.** Tier-B rewriting is opt-in and requires an
  explicit API key, so a scheduled `run` never spends tokens unattended.
- **The first scheduled run migrates the store to head** before doing anything, so any pending
  schema repair is applied automatically.
- **Liveness checking is on by default** — each run re-fetches shortlisted postings and withholds
  any that answers 404/410; pass `--no-check-liveness` to skip those per-posting re-fetches. Pass
  **`--project`** to render each lead from the career-profile bundle's projection instead of the
  authored résumé; this needs a **current projection approval** (`profile-bundle
  approve-projection`), and without one the run refuses rather than silently falling back.
- **The delivery queue's root can be overridden with `--queue-root PATH`**, the same option `web`
  takes; omit it and the queue defaults to `~/boardwatch-queue`. If `BOARDWATCH_DATA_DIR` is set
  (rather than `--data-dir`) and `--queue-root` is not, `run` refuses instead of reconciling the
  real queue against whatever store the environment variable points at — pass `--queue-root` to
  point both at the same scratch location, or unset the variable to use the real store and its
  real queue together.

**Alerting when a run never happens.** launchd, cron, and systemd timers share one blind spot:
if the machine is off or asleep across the whole scheduled window, the job simply never runs —
and nothing *on* the machine can notice a run that did not occur. To close that, a successful
`run` pings a heartbeat URL (a "dead-man's-switch"), read only from the environment:

```bash
export BOARDWATCH_HEARTBEAT_URL=https://hc-ping.com/<your-check-uuid>
```

Point it at a free cron-monitor (e.g. healthchecks.io, Cronitor) whose check is set to your
schedule plus a grace window, and have that service email or message you when a ping does not
arrive. The ping fires **only on a clean run**, so a run that failed, crashed, or never started
all leave the monitor silent and it alerts — the failure mode a local check can't see. It is
presence-gated (unset ⇒ no ping) and, like the webhook URL, the value is a secret read from the
environment, never `config.toml`; put it in the agent's `EnvironmentVariables` alongside `PATH`.

Everything the `scan` schedule notes — environment variables, running as the same user that ran
`init`, and running the command once by hand first — applies here too. See
[scheduling](scheduling.md) for those mechanics.

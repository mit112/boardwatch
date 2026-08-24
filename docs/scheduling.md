# Scheduling scans and notifications

## Schedule scans

Run `boardwatch init` once interactively before scheduling scans. The scheduler must run as the same user that ran `init`, so it reads the same local profile and database. Start with a daily scan; the default politeness settings are designed for that cadence.

Each example below appends the scan summary to a log. Replace `/absolute/path/to/boardwatch` with the output of `command -v boardwatch`, then run the command once manually before enabling its timer.

### cron (Linux or macOS)

Create a log directory, then add a daily job with `crontab -e`:

```console
$ mkdir -p "$HOME/.local/state/boardwatch"
```

```cron
# Run every day at 08:00 local time.
0 8 * * * /absolute/path/to/boardwatch scan >> "$HOME/.local/state/boardwatch/scan.log" 2>&1
```

Cron has a deliberately small environment. If you set `BOARDWATCH_DATA_DIR` or `BOARDWATCH_CONFIG_DIR` when running boardwatch normally, define the same values above the job in the crontab.

### launchd (macOS)

Save this as `~/Library/LaunchAgents/com.boardwatch.scan.plist`, replacing the boardwatch path and the home-directory placeholder. The standard output and error paths must use absolute paths.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
  <dict>
    <key>Label</key>
    <string>com.boardwatch.scan</string>
    <key>ProgramArguments</key>
    <array>
      <string>/absolute/path/to/boardwatch</string>
      <string>scan</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
      <key>Hour</key><integer>8</integer>
      <key>Minute</key><integer>0</integer>
    </dict>
    <key>StandardOutPath</key>
    <string><home>/Library/Logs/boardwatch-scan.log</string>
    <key>StandardErrorPath</key>
    <string><home>/Library/Logs/boardwatch-scan.log</string>
  </dict>
</plist>
```

Load it and confirm its status:

```console
$ launchctl bootstrap "gui/$(id -u)" ~/Library/LaunchAgents/com.boardwatch.scan.plist
$ launchctl print "gui/$(id -u)/com.boardwatch.scan"
```

After editing the file, reload it with `launchctl bootout "gui/$(id -u)/com.boardwatch.scan"` followed by the `bootstrap` command above.

### systemd user timer (Linux)

Create `~/.config/systemd/user/boardwatch-scan.service`:

```ini
[Unit]
Description=Scan watched job boards with boardwatch

[Service]
Type=oneshot
ExecStart=/absolute/path/to/boardwatch scan
```

Then create `~/.config/systemd/user/boardwatch-scan.timer`:

```ini
[Unit]
Description=Run boardwatch scan every day

[Timer]
OnCalendar=*-*-* 08:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

Enable the timer and inspect the most recent run:

```console
$ systemctl --user daemon-reload
$ systemctl --user enable --now boardwatch-scan.timer
$ systemctl --user list-timers boardwatch-scan.timer
$ journalctl --user -u boardwatch-scan.service --since today
```

`Persistent=true` runs a missed daily scan after the next login. To keep user timers running after logout, enable lingering for the account with `loginctl enable-linger "$USER"`.

## Notifications

`notify` is a standalone command, a sibling of `scan`: chain them in your scheduled job so
each run scans, then pushes anything new:

```bash
/absolute/path/to/boardwatch scan && /absolute/path/to/boardwatch notify
```

Notifications are **off by default**. Turn on one or both channels:

```bash
boardwatch config set notify.webhook_enabled true
boardwatch config set notify.desktop_enabled true
```

The webhook channel needs a URL from the environment, never from `config.toml`:

```bash
export BOARDWATCH_NOTIFY_WEBHOOK_URL=https://hooks.slack.com/services/...
```

One payload works for Slack incoming webhooks, Discord webhooks, and generic/structured
consumers, so the same URL drops into any of them. Desktop notifications are best-effort
(macOS via `osascript`, Linux via `notify-send`); on any other platform, or if the notifier
binary is missing, desktop delivery degrades non-fatally and webhook remains the
cross-platform, headless-friendly channel. Run `boardwatch notify --dry-run` to preview what
would be sent without delivering anything or advancing the notify cursor.

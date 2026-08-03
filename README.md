# boardwatch

**A self-hosted job radar that reads the fine print.** Point it at the companies you
care about. boardwatch watches their **official ATS job boards**, catches new postings
early, and ranks them against your profile with an explainable score. It also reads each
posting for the hard eligibility requirements that quietly rule people out (visa
sponsorship, security clearance, a required degree, years of experience, a location) and
flags the ones you could not actually apply to, each backed by the exact sentence it read
as evidence. Nothing is guessed, nothing phones home, and it all runs on your own machine.

[![CI](https://github.com/mit112/boardwatch/actions/workflows/ci.yml/badge.svg)](https://github.com/mit112/boardwatch/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/boardwatch.svg)](https://pypi.org/project/boardwatch/)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

> **Status: pre-release, under active development.** No auto-apply, ever. No telemetry.
> No accounts, no API keys. Your data stays in a local SQLite file.

```console
$ boardwatch top
 #   Title                            Company     Score   Eligible   Why
 12  Senior Backend Engineer          Stripe      0.86    no flags   covers 9/11 skills · title · 1d
 7   Software Engineer, Platform      Linear      0.81    check      covers 7/10 skills · title · 3d
 33  Backend Engineer (Payments)      Ramp        0.74    no flags   covers 6/9 skills · 2d
 5   Full-Stack Engineer              Supabase    0.68    no flags   covers 5/8 skills · title · 6d
 18  Infrastructure Engineer          OpenAI      0.61    check      covers 4/9 skills · 4d

2 postings hidden as ineligible (run with --include-ineligible to see them).
```

*(Illustrative output. `#` is the posting id; pass it to `boardwatch show <id>` for the
full posting, a per-component score breakdown, and the eligibility audit with quotes.
"no flags" means no catalogued disqualifier was found, not that you are cleared to
apply; "check" means the posting was ambiguous.)*

---

## Why boardwatch?

Job boards optimize for their advertisers, not for you. LinkedIn/Indeed bury fresh roles
under sponsored noise and stale reposts; paid trackers put a subscription (and their
servers, and your search history) between you and postings that are **already public**.

boardwatch takes the direct route. Greenhouse, Lever, Ashby, Workable, and SmartRecruiters
each expose a **public, keyless JSON endpoint** for every board they host, the same data
the company's own careers page renders. boardwatch polls those endpoints politely, on
your schedule, and tells you what's *new* since last time.

|                          | boardwatch            | LinkedIn/Indeed        | Paid trackers          |
|--------------------------|-----------------------|------------------------|------------------------|
| Source of truth          | company's own ATS     | aggregated + sponsored | aggregated             |
| Freshness                | as fast as you poll   | ranking-dependent      | vendor-dependent       |
| Reads eligibility        | audit + quoted proof  | no                     | no                     |
| Your data                | local SQLite, yours   | the product            | on their servers       |
| Cost                     | free (self-hosted)    | free-ish (ad-driven)   | subscription           |
| Auto-apply / spam        | never                 | no comment             | sometimes              |

**Honest limits.** boardwatch only covers companies hosted on **Greenhouse, Lever, Ashby,
Workable, or SmartRecruiters** (a large slice of tech, but not everyone, no
Workday/Taleo/etc. yet). It reads exactly what those APIs expose. It is pre-release:
expect rough edges, and read [Responsible use](#responsible-use--legality) before
pointing it at boards you don't own.

---

## Quickstart (≈2 minutes to your first shortlist)

### pipx (recommended)

```bash
pipx install boardwatch      # isolated, on your PATH
boardwatch init              # pick a starter set of companies + paste your profile
boardwatch scan              # poll the watched boards (polite, conditional GETs)
boardwatch top               # ranked shortlist
```

`boardwatch init` is interactive. Pick **[1] Starter set** to watch a curated group of
well-known boards in one keystroke, **[2] Search registry** to pick from the bundled
catalog, or **[3] Paste** any `provider:slug` or board URL. Then paste your résumé text
and a few target/exclude titles and locations. A cold `init → scan → top` lands your
first ranked shortlist in well under ten minutes.

### Docker

```bash
docker run --rm -v boardwatch-data:/data \
  ghcr.io/mit112/boardwatch:latest --data-dir /data init
docker run --rm -v boardwatch-data:/data \
  ghcr.io/mit112/boardwatch:latest --data-dir /data scan
docker run --rm -v boardwatch-data:/data \
  ghcr.io/mit112/boardwatch:latest --data-dir /data top
```

### From source

```bash
git clone https://github.com/mit112/boardwatch && cd boardwatch
uv sync                      # https://docs.astral.sh/uv/
uv run boardwatch init
```

---

## How it works

```
   init ──▶ scan ──▶ top ──▶ show <id>
   │        │        │        │
   companies fetch    rank on   full posting +
   + profile boards   demand    score breakdown
```

- **`init`**: one-time setup. Choose companies (starter set / registry search / paste),
  then your profile (résumé text, target titles, excludes, locations, remote-only).
- **`scan`**: fetches every watched board through a polite fetcher (per-host pacing,
  retries with backoff, conditional `If-None-Match`/`If-Modified-Since` so unchanged
  boards cost a `304`), then applies each board transactionally. Prints a one-line summary.
- **`top [N]`**: ranks open postings against your profile *right now* (weights are read
  live), newest-and-most-relevant first, with a one-line "why".
- **`show <id>`**: the full posting plus a per-component score table (skill coverage,
  title match, recency, location fit) and the eligibility audit with quoted evidence.
- **`eligibility`**: `facts` / `policy` to tell boardwatch your situation, `run` to
  evaluate open postings, `summary` for a funnel of what the catalog matched. See
  [Eligibility audit](#eligibility-audit).
- **`companies`**: `add` / `remove` / `search` / `list` / `import` / `export` your watched
  boards. `boardwatch companies add https://boards.greenhouse.io/acme` just works.
- **`doctor`**: per-board connectivity and freshness, plus a local DB integrity check.
- **`config show` / `config set`**: tune politeness and ranking weights (see below).

### Ranking, briefly

Each posting gets a 0–1 score: a weighted blend of **skill coverage**, **title match**
(fuzzy), **recency** (exponential decay), and **location fit**. Undefined components
renormalize away, so a sparse profile still ranks sensibly. Nothing is precomputed:
change a weight and the next `top` reflects it. `show <id>` prints the exact arithmetic.

---

## Eligibility audit

Ranking tells you how well a posting fits. The eligibility audit tells you whether you
could apply at all, and shows its work.

You describe your situation once, in the catalog's own vocabulary:

```bash
boardwatch eligibility facts set work_authorization.status citizen
boardwatch eligibility facts set highest_degree bachelor
boardwatch eligibility policy set visa_sponsorship blocker   # treat this family as disqualifying
```

Then `boardwatch eligibility run` reads each open posting for catalogued requirements
(visa sponsorship, security clearance, degree, years of experience, location, and more),
resolves them against your facts, and stores a verdict. `boardwatch show <id>` prints it
with the receipts:

```console
Eligibility: ineligible
  unmet · required: work authorization / sponsorship
      quote: "This role is not able to sponsor employment visas now or in the future."
```

Three properties are deliberate:

- **Evidence-linked.** Every requirement carries the exact sentence it was read from,
  sliced from the posting version that was evaluated. Nothing is paraphrased or invented.
- **Deterministic.** The same posting and the same facts always produce the same verdict.
  There is no language model in the loop and nothing to hallucinate: the vocabulary and
  rules are a versioned catalog, and a verdict is invalidated and recomputed only when
  your profile or the catalog changes.
- **Honest.** A clean posting reads as "no flags", never as a guarantee. "no flags" means
  only that no catalogued disqualifier was found, not that you are cleared to apply, and
  ambiguous wording reads as "check" rather than a false all-clear.

`boardwatch eligibility summary` shows the funnel (how many postings were evaluated, the
verdict split, and what fired per family) so you can watch the catalog working before you
trust a hidden count. By default `top` hides postings that are ruled out and reports the
count; `top --include-ineligible` shows them.

---

## What changed since you last looked

`boardwatch scan` records every appearance, disappearance and body revision in an
append-only ledger. `digest` reads the ledger from wherever you left off:

```bash
boardwatch digest          # new, reopened, updated, and a closed count
boardwatch digest --peek   # the same view without consuming it
boardwatch top --new       # rank only the postings first seen since your last digest
```

The cursor is an event id, not a timestamp, so a clock change or a missed day cannot skip
or repeat a window.

---

## Your funnel

boardwatch never applies for you. It records what you did, so the state stays yours:

```bash
boardwatch track add 42                    # start tracking a posting
boardwatch track status 1 applied          # move it, with an immutable ledger entry
boardwatch track status 1 interviewing --note "phone screen booked"
boardwatch track list --status applied
boardwatch track log 1                     # the full history for one application
```

---

## Take your data with you

```bash
boardwatch export --format jsonl --out postings.jsonl
boardwatch export --format csv
```

Every row carries the posting, your funnel state, and the eligibility verdict together
with the profile and rules hashes that identify the evaluation it was computed under.
This is a flat snapshot, not a full audit trail; it does not support independent
recomputation of verdicts.

---

## Configuration

`boardwatch config show` prints every key, its value, and its default;
`boardwatch config set <key> <value>` changes it (validated at set time and load time).

| Key | Range | Default | Effect |
|---|---|---|---|
| `per_host_delay_seconds` | ≥ 0.25 | 1.0 | politeness between requests to one host |
| `retry_attempts` | 1–10 | 3 | retries on transient failures |
| `scan_workers` | 1–8 | 4 | concurrent boards per scan |
| `weights.skill_coverage` | 0–1 | 0.50 | ranking weight |
| `weights.title_match` | 0–1 | 0.25 | ranking weight |
| `weights.recency` | 0–1 | 0.15 | ranking weight |
| `weights.location_fit` | 0–1 | 0.10 | ranking weight |

See [docs/configuration.md](docs/configuration.md) for details.

---

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

### Notifications

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

---

## Tailor a résumé

boardwatch never parses a résumé — parsing free-form PDFs/Word docs to *understand* a
person's history is exactly the kind of guessing this project avoids. Instead you author
your résumé once as structured YAML, and `tailor` only ever *renders* it:

```bash
boardwatch tailor init                 # scaffold {config_dir}/resume.yaml, edit it in your editor
boardwatch tailor validate             # confirm it loads; see entry/bullet counts + detected skills
boardwatch tailor run <posting-id>     # tailor it against one posting's extracted JD skills
```

`validate` and `run` read `{config_dir}/resume.yaml` unless you pass `--resume PATH`. `run`
also takes `--out DIR` (default `{data_dir}/tailored`), `--format typst` (the only 1.0
adapter), and `--dry-run` (report only; writes no file and records no artifact). It prints
one line per bullet — kept, reordered, swapped, or dropped, with the JD skills that bullet
covers — and the same per-bullet audit is stored on the artifact row.

`tailor run` selects which of your authored bullets to keep (favoring ones that cover the
posting's extracted skills), reorders skill mentions, and applies whole-token synonym
swaps from a small, bundled, frozen equivalence table (e.g. "JS" ↔ "JavaScript") — never
free text generation. Before anything is written, a **no-fabrication guarantee** re-checks
the output against your master résumé: every kept bullet's tokens must be either unchanged
or a substitution the equivalence table names, and no bullet, entry, or section can appear
that wasn't in the original. A résumé that fails this check is rejected before any file or
database row is written, never delivered as a "best effort".

**Honest bounds (Tier A).** This is Tier A: a local, deterministic bullet-selection and safe-synonym
pass — it does not rewrite your prose, invent new claims, or call any model. **Your
`profile` text (the free-form blurb from `boardwatch init`) is never imported into the
résumé** — `tailor` reads only what you author in `resume.yaml`. PDF output is
**best-effort**: it shells out to a local [Typst](https://typst.app/) install if present;
without one you still get the rendered Typst source and can compile it yourself, or paste
it elsewhere. Output lands at `{data_dir}/tailored/tailored-<posting-id>.{typ,pdf}` — a
deterministic path, so **re-running `tailor run` for the same posting overwrites that
file** even though each run is recorded as its own artifact in the database; the file on
disk always reflects your most recent run, not necessarily the one you're currently
reading about. If a later Typst compile fails, the stale PDF from the previous run is
removed rather than left behind next to the new source.

### Tier B (opt-in LLM)

Tier A never rewrites your prose. If you want bullets reworded toward a posting's
language, Tier B is an **opt-in**, off-by-default LLM lane on top of it:

```bash
boardwatch tailor run <posting-id> --tier-b     # alias: --llm
```

`--tier-b` requires all of the following, and does nothing (writes nothing, exits 1)
if any is missing:

- `llm.resume_tailoring = true` **and** `llm.enabled = true` in `{config_dir}/config.toml`
  — `resume_tailoring` is the only key Tier B adds, and it lives on the same `[llm]`
  block as the opt-in LLM eligibility-extraction tier (see
  [docs/configuration.md](docs/configuration.md)); no new section, no new secret.
  `config set llm.*` is reserved and refuses to write these, so set them by editing
  `config.toml` directly.
- `BOARDWATCH_LLM_API_KEY` in the environment (never in `config.toml`).

Per bullet, Tier B proposes a reworded version, then runs it through a deterministic
overmatch filter and a fail-closed entailment judge (the judge sees only the two bullet
texts — original and reworded — and never the job description). A bullet is only kept
reworded if it passes both; otherwise Tier B silently falls back to the Tier A text for
that bullet, so a `--tier-b` run degrades to Tier A on any single bullet without failing
the whole command. The CLI reports how many bullets were reworded vs. fell back, and why.

Tier B costs **2 LLM calls per bullet** (propose, then judge), drawn from the same
`llm.max_calls_per_run` budget (default 50, shared with the eligibility LLM lane) — so
roughly 25 bullets per run before the tail starts falling back with `drop_reason:
"budget"`. That budget is consumed even on a cache hit, by design, so re-running the same
posting does not extend it; raise `llm.max_calls_per_run` in `config.toml` instead. See
[docs/configuration.md](docs/configuration.md).

**Dual output, not a replacement.** `--tier-b` always writes the ordinary Tier A file
first — Tier B never runs in place of it — plus a second file/artifact
(`resume_tailored_llm`) with reworded bullets marked `// reworded (Tier B)` in the
rendered source. The lineage is recorded as B —`rewritten_from`→ A —`tailored_from`→
your master résumé, so either output can be traced back.

**Honest bounds (Tier B).** Tier B is **not** the no-fabrication guarantee above: passing
the filter and judge is evidence, not proof, and every reworded bullet is meant to be
**read by you before you send it**, not trusted blind. The Tier A path never calls out
to a model, regardless of Tier B's settings; only `--tier-b` sends bullet text and the
posting's extracted JD skill names to the configured provider, and only when explicitly
enabled and requested. See [SECURITY.md](SECURITY.md) for exactly what leaves your
machine and when.

---

## Supported boards

| Provider        | Public endpoint boardwatch reads                                          | Auth |
|-----------------|----------------------------------------------------------------------------|------|
| Greenhouse      | `boards-api.greenhouse.io/v1/boards/<slug>/jobs`                          | none |
| Lever           | `api.lever.co/v0/postings/<slug>`                                         | none |
| Ashby           | Ashby public job-board posting API                                        | none |
| Workable        | `apply.workable.com/api/v1/widget/accounts/<slug>?details=true` (single request, whole board) | none |
| SmartRecruiters | `api.smartrecruiters.com/v1/companies/<slug>/postings?limit=100&offset=0` (paginated list, plus one detail fetch per unseen posting) | none |

boardwatch ships a bundled **registry** of verified public boards (35+ companies, with a
curated **starter set**), so `init` works offline out of the box. You can watch any board
these providers host, not just the registry, with `companies add`. The registry is
community-maintainable by PR; see
[`src/boardwatch/registry/README.md`](src/boardwatch/registry/README.md).

**SmartRecruiters honest limits.** Its API cannot distinguish a typo'd company slug from
a real, empty board — an unknown company returns an empty board, not an error, so
`companies add` and `doctor` flag it as unverifiable rather than confirmed. Job bodies are
fetched once per posting (bounded by `detail_fetch_budget`, default 50) and never
refreshed, since the list endpoint carries no revision signal for description-only edits.
A posting that goes inactive while still listed is not re-detected as closed until it
drops off the list — it self-heals on a later scan.

---

## Responsible use & legality

boardwatch reads the **same public, keyless endpoints that power each company's own
careers page**: it does not scrape rendered HTML, log in, or bypass any access control.
That is deliberately the least-invasive way to get this data. Still, these are
third-party services, and using them responsibly is on you:

- **Keep the politeness defaults.** The defaults (≥1 request/sec per host, conditional
  GETs, bounded retries, a descriptive User-Agent) are intentionally gentle. Don't crank
  `scan_workers` up or `per_host_delay_seconds` down to hammer a board.
- **It's for personal job-search use**, not bulk data resale or redistribution of posting
  content. boardwatch stores postings locally for *your* review.
- **Provider terms & rate limits can change** and may restrict automated access. You are
  responsible for complying with each provider's Terms of Service. If a provider asks you
  to stop, stop.
- **No warranty.** These are undocumented-stability public endpoints; they can change or
  break without notice.

If you're unsure whether your use is appropriate, err toward watching fewer boards, less
often. A job seeker checking a dozen companies once a day is the intended shape.

---

## Privacy & data

- **Local-first.** Its primary store is one SQLite database in your platform data directory;
  the opt-in LLM tier also caches raw responses there as plain files on disk (override with
  `--data-dir`). No server, no account, no cloud.
- **No telemetry.** boardwatch phones home to nobody.
- **Two optional secrets, env-only.** The default path authenticates to nothing. The
  opt-in LLM tier reads `BOARDWATCH_LLM_API_KEY` and the opt-in webhook notifier reads
  `BOARDWATCH_NOTIFY_WEBHOOK_URL`, both from the environment only and never written to
  disk. See [SECURITY.md](SECURITY.md).

---

## Roadmap

- [x] PyPI + GHCR published releases (`pipx install boardwatch`, `docker run …`)
- [x] Notifications on new matches (desktop / webhook)
- [x] `digest` and `top --new` change detection (only what changed since last run)
- [x] More ATS providers (community-driven)
- [x] Data-portability export (`--format jsonl|csv`)
- [x] Résumé tailoring (`tailor init/validate/run`, local, no-fabrication guarantee)

Have a company on a board boardwatch doesn't reach yet, or an ATS you want supported?
[Open an issue.](https://github.com/mit112/boardwatch/issues)

---

## Contributing

Contributions welcome: code, registry entries, or bug reports. See
[CONTRIBUTING.md](CONTRIBUTING.md) for dev setup (`uv sync`, `make check`) and
[the registry guide](src/boardwatch/registry/README.md) for adding a company board.
All changes land via PR against a branch-protected `main`.

## License

[MIT](LICENSE).

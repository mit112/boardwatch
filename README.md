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

> **Status: pre-release, under active development.** boardwatch does not submit
> applications: it finds and evaluates postings, and you decide what to do with them.
> No telemetry. No accounts, no API keys. Your data stays in a local SQLite file.

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

boardwatch takes the direct route. Greenhouse, Lever, Ashby, Workable, SmartRecruiters and
Workday each expose a **public, keyless JSON endpoint** for every board they host, the same data
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
Workable, SmartRecruiters or Workday** (a large slice of tech, but not everyone, no
Taleo/etc. yet). It reads exactly what those APIs expose. It is pre-release:
expect rough edges, and read [Responsible use](#responsible-use--legality) before
pointing it at boards you don't own.

---

## Quickstart (≈2 minutes to your first shortlist)

**Prerequisites.** Scanning and ranking need nothing beyond the install. Building résumé PDFs
additionally needs two binaries on `PATH` — [tectonic](https://tectonic-typesetting.github.io/)
and poppler's `pdfinfo`:

```bash
brew install tectonic poppler                       # macOS
sudo apt-get install poppler-utils                  # Debian/Ubuntu (tectonic: see its docs)
```

`boardwatch doctor` reports whether both are present. The Docker image bundles them.

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
boardwatch eligibility facts set employment_type_preference fte_only
boardwatch eligibility policy set work_auth blocker   # treat this family as disqualifying
```

Then `boardwatch eligibility run` reads each open posting for catalogued requirements
(visa sponsorship, security clearance, degree, years of experience, employment type,
internships, location, and more),
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
- **Deterministic by default.** The same posting and the same facts always produce the same
  verdict. Out of the box there is no language model in the loop and nothing to hallucinate:
  the vocabulary and rules are a versioned catalog, and a verdict is invalidated and
  recomputed only when your profile or the catalog changes. There is an **opt-in,
  off-by-default** model-assisted gate that can additionally hide a posting it reads as
  ineligible; it can only ever hide, never clear, and turning it off restores the fully
  deterministic path.
- **Honest.** A clean posting reads as "no flags", never as a guarantee. "no flags" means
  only that no catalogued disqualifier was found, not that you are cleared to apply, and
  ambiguous wording reads as "check" rather than a false all-clear.

`boardwatch eligibility summary` shows the funnel (how many postings were evaluated, the
verdict split, and what fired per family) so you can watch the catalog working before you
trust a hidden count. By default `top` hides postings that are ruled out and reports the
count; `top --include-ineligible` shows them.

`top` also hides postings whose **title** is not a software role — a "Deal Strategist" or an
"Asset Tracking Technician" that fuzzy title matching would otherwise float to the top. The
same rule applies to `notify`. This filter is deliberately loud rather than silent: the count
appears under the table, `stats` reports it, `show <id>` tells you what the gate made of any
posting, and `top --include-non-swe` lists the hidden rows with the exact title text that
vetoed each one. A title that gives no signal either way is never filtered — it is scored
normally, so a genuine software job with an unusual title is not at risk.

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

## Where you stand

`boardwatch stats` is a one-screen, read-only readout over your local database — no network,
no writes of its own:

```bash
boardwatch stats             # qualified opportunities (last 7 days) + the discovery pipeline
boardwatch stats --days 30   # widen the trailing window
```

The first view partitions recent postings into `qualified` / `uncertain` / `ineligible` /
`unevaluated`; a posting you have not evaluated yet is `unevaluated`, never counted as
qualified. The second view is the pipeline: seen → passes filters → not ineligible → tracked.
It needs a profile, so run `boardwatch init` first.

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
| `seen_ttl_days` | ≥ 1 | 7 | how long a lead you were shown, but which produced nothing, stays out of the shortlist |
| `reap_stale_after_hours` | ≥ 1 | 24 | age at which an unfinished run row is treated as crashed |
| `location_filter_mode` | `soft`/`hard` | `soft` | whether a location mismatch only lowers rank, or vetoes the posting |
| `weights.skill_coverage` | 0–1 | 0.50 | ranking weight |
| `weights.title_match` | 0–1 | 0.25 | ranking weight |
| `weights.recency` | 0–1 | 0.15 | ranking weight |
| `weights.location_fit` | 0–1 | 0.10 | ranking weight |

See [docs/configuration.md](docs/configuration.md) for details.

`boardwatch settings` gives a read-only view of every opt-in feature (LLM tiers,
notifications) — state, what it does, what it sends anywhere — and `boardwatch settings
toggle` flips them interactively; both share the same validation as `config set`. See
[docs/configuration.md](docs/configuration.md#settings-menu).

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
also takes `--out DIR` (default `{data_dir}/tailored`), `--format latex` (the only 1.0
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
résumé** — `tailor` reads only what you author in `resume.yaml`.

**PDF output is a hard gate, not best-effort.** The renderer is
[tectonic](https://tectonic-typesetting.github.io/), compiling a LaTeX template you can
override at `{config_dir}/resume_template.tex`. A lead without a shippable PDF is refused
rather than delivered as rendered source: a missing `tectonic` on `PATH` fails the run
loudly, and a résumé that compiles to more pages than `resume_max_pages` (default 1) is
rejected. **Two binaries are required, not one** — `tectonic` to compile and poppler's
`pdfinfo` to count the pages; without `pdfinfo` the page-count gate cannot answer and every
lead is refused. `boardwatch doctor` probes for both and exits non-zero if either is
missing. Output lands at
`{data_dir}/tailored/tailored-<posting-id>.{tex,pdf}` — a deterministic path, so
**re-running `tailor run` for the same posting overwrites that file** even though each run
is recorded as its own artifact in the database; the file on disk always reflects your most
recent run, not necessarily the one you're currently reading about. If a later compile
fails, the stale PDF from the previous run is removed rather than left behind next to the
new source.

### Tier B (opt-in LLM)

Tier A never rewrites your prose. If you want bullets reworded toward a posting's
language, Tier B is an **opt-in**, off-by-default LLM lane on top of it:

```bash
boardwatch tailor run <posting-id> --tier-b     # alias: --llm
```

`--tier-b` requires all of the following, and does nothing (writes nothing, exits 1)
if any is missing:

- `llm.resume_tailoring = true` **and** `llm.enabled = true` — `resume_tailoring` is the
  only key Tier B adds, and it lives on the same `[llm]` block as the opt-in LLM
  eligibility-extraction tier (see [docs/configuration.md](docs/configuration.md)); no
  new section, no new secret. Both are settable via `boardwatch config set llm.enabled
  true` / `boardwatch config set llm.resume_tailoring true`, or interactively via
  `boardwatch settings toggle`. `provider`/`model`/`base_url` still require a hand-edit to
  `config.toml`.
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
**read by you before you send it**, not trusted blind. The guarantee is layered: the
deterministic filter rejects invented skills, added/inflated numbers, and invented
brand/company names outright, provider-independently; the entailment judge is a
best-effort, model-dependent second layer for the fabrications a text-diff can't see
(flipped negations, inflated seniority, swapped outcomes); and you are the backstop. The Tier A path never calls out
to a model, regardless of Tier B's settings; only `--tier-b` sends bullet text and the
posting's extracted JD skill names to the configured provider, and only when explicitly
enabled and requested. See [SECURITY.md](SECURITY.md) for exactly what leaves your
machine and when.

#### Tier B without an API key (agent lane)

`--tier-b` needs `BOARDWATCH_LLM_API_KEY` and a metered provider. If you only have a
Claude Code subscription and no API key, there's a second, subscription-driven Tier B
lane that gets the same reworded-bullet output by having Claude Code itself do the
rewrite, with boardwatch validating it through the identical filter + judge + Tier A
stack described above.

It's a three-command handshake, driven by the `tailor-rewrite` boardwatch skill
(`.claude/skills/tailor-rewrite`):

```bash
boardwatch tailor rewrite request <posting-id>                                     # 1. writes rewrite_request.json
# the skill's rewriter agent reads it and writes candidates.json
boardwatch tailor rewrite screen <posting-id> --candidates candidates.json         # 2. writes judge_request.json
# a SEPARATE, freshly scoped judge subagent reads it and writes verdicts.json
boardwatch tailor rewrite apply <posting-id> --candidates candidates.json --verdicts verdicts.json  # 3.
```

`request` runs Tier A internally and hands the rewriter agent each bullet plus the
posting's JD skills. `screen` re-derives the authoritative bullet text from a fresh
Tier A run and puts the rewriter's candidates through the same deterministic overmatch
filter as the API lane — but the `judge_request.json` it writes is **JD-blind by
construction**: it's built from only `(original, candidate)` pairs, with no job
description or skills field anywhere in it, and boardwatch's skill instructs the judge
to run as a separate subagent so it never inherits the rewriter's JD-aware context.
`apply` parses the judge's verdicts with the same exact-token allowlist as the API
lane and emits both artifacts.

Gate: `llm.resume_tailoring_via_agent = true`, settable via `boardwatch config set
llm.resume_tailoring_via_agent true` or `boardwatch settings toggle`. Unlike `--tier-b`,
this lane needs **no** `llm.enabled` and **no** API key — boardwatch makes no LLM call
itself in this lane; the rewriting and judging happen in Claude Code subagents outside
the CLI. Do not enable `llm.enabled` for this lane; it isn't required and isn't checked.

The per-bullet call budget is **advisory** here, not a hard spend limit: subscription
calls aren't API-metered, so it's set wide enough to never truncate a legitimate run
and functions only as a soft cap on how many bullets get attempted in one pass. Every
other safety backstop is unchanged: the Tier A file is always emitted alongside, every
reworded bullet is marked `// reworded (Tier B)`, and the artifact is meant to be
reviewed by you before it's sent — this lane is LLM-assisted and filter+judge gated,
not structurally proven, same as `--tier-b`. Provenance on the artifact records
provider `claude-code-agent`, model `subscription`, so it's distinguishable from an
API-lane run.

---

## Career-profile bundle (unstable, not wired to anything yet)

`boardwatch profile-bundle` is a private, revisioned, filesystem-only store for the career
facts a résumé is assembled from: typed YAML records, evidence captured by digest, owner
approval bound to a content digest, and immutable content-addressed revisions. It lives at
`{config_dir}/career-profile` (override with `--bundle PATH`) and nothing leaves your machine.

**It is not connected to anything.** `boardwatch tailor` still reads
`{config_dir}/resume.yaml`; there is deliberately no bundle-to-résumé bridge yet, and the
bundle's on-disk grammar, digests and JSON reports may still change. Use it only if you want
to try the authoring model.

See [docs/profile-bundle-authoring.md](docs/profile-bundle-authoring.md) for the format, the
twelve commands, the 0/1/2/3 exit contract, and recovery from a stale draft or a corrupt
evidence blob.

---

## Supported boards

| Provider        | Public endpoint boardwatch reads                                          | Auth |
|-----------------|----------------------------------------------------------------------------|------|
| Greenhouse      | `boards-api.greenhouse.io/v1/boards/<slug>/jobs`                          | none |
| Lever           | `api.lever.co/v0/postings/<slug>`                                         | none |
| Ashby           | Ashby public job-board posting API                                        | none |
| Workable        | `apply.workable.com/api/v1/widget/accounts/<slug>?details=true` (single request, whole board) | none |
| SmartRecruiters | `api.smartrecruiters.com/v1/companies/<slug>/postings?limit=100&offset=0` (paginated list, plus one detail fetch per unseen posting) | none |
| Workday         | `<tenant>.wd<N>.myworkdayjobs.com/wday/cxs/<tenant>/<site>/jobs` (**POST**-only, paginated at the server's hard maximum of 20/page, plus one detail fetch per unseen posting) | none |

**Workday boards need three parts, not one.** A Workday board is identified by a host, a
tenant and a career-site slug, so its target form is
`workday:<host>/<tenant>/<CareerSite>` — for example
`workday:acme.wd5.myworkdayjobs.com/acme/AcmeCareers`. Pasting the career-site URL
(`acme.wd5.myworkdayjobs.com/AcmeCareers`) works too and derives the tenant for you. Site
slugs are **case-sensitive**; hosts and tenants are not. One tenant can serve several
disjoint career sites, so each site is watched as its own board.

boardwatch ships a bundled **registry** of verified public boards (35+ companies, with a
curated **starter set**), so `init` works offline out of the box. You can watch any board
these providers host, not just the registry, with `companies add`. The registry is
community-maintainable by PR; see
[`src/boardwatch/registry/README.md`](src/boardwatch/registry/README.md).

**Verifying a slug before you watch it.** `companies add` and `companies import` are
offline by default — they accept any well-formed `provider:slug` and let the next `scan`
or `doctor` discover a typo. Pass `--verify` to probe each board first: boards that come
back reachable are watched (a reachable-but-empty board is watched with a note), and boards
that return 404 or cannot be reached are skipped rather than written. `import --verify`
exits non-zero if it skipped anything, so a partial import does not read as a clean one.

**SmartRecruiters honest limits.** Its API cannot distinguish a typo'd company slug from
a real, empty board — an unknown company returns an empty board, not an error, so
`companies add`, `--verify` and `doctor` flag it as unverifiable rather than confirmed.
`--verify` therefore cannot catch a typo'd SmartRecruiters slug; it says so when it sees one. Job bodies are
fetched once per posting (bounded by `detail_fetch_budget`, default 50) and never
refreshed, since the list endpoint carries no revision signal for description-only edits.
A posting that goes inactive while still listed is not re-detected as closed until it
drops off the list — it self-heals on a later scan.

**Workday honest limits.** Its list endpoint serves no `ETag` and no `Last-Modified`, so
conditional fetches are inert and every scan re-reads the whole board — a 2,000-posting
board is 100+ requests to one host, paced by the usual per-host delay. Each scan admits at
most `detail_fetch_budget` (default 50) **previously-unseen** postings — a body is fetched
once per admitted posting and never refreshed. The rest of the board's live inventory is
carried forward so nothing it still lists is closed, and the remaining postings are admitted
on later scans. A large board therefore reports **`partial`** as its normal outcome and fills
in — postings and bodies alike — across many scans, the same incremental fill SmartRecruiters
bodies get. Raise the ceiling with `boardwatch config set detail_fetch_budget <N>` to admit
more per scan, at the cost of more requests to one host each scan. The registry ships **no**
Workday boards, so `doctor` reports Workday connectivity as *not checked* until you watch one
with `companies add`.

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
- [x] Workday provider (host/tenant/site composite board identity)
- [x] More eligibility rule families (contract vs. full-time, internships)
- [x] A readable settings surface, so every opt-in feature is discoverable and reversible
      without hand-editing `config.toml`
- [x] Deduplication, so the same role posted twice is one lead and not two
- [x] A durable decision ledger, so a lead you were already shown does not come back tomorrow
- [x] Applied-state suppression, so a job you already applied to stays off the list
- [x] A liveness re-check during `run`, so a requisition that has been taken down is dropped
      before a résumé is built for it

Next:

- [ ] An onboarding flow that fits fields other than software, so the eligibility taxonomy is
      gathered from you rather than assumed
- [ ] A measured acceptance run — the daily numbers published rather than asserted
- [ ] Broader company coverage, but only after the above shows the funnel converts; breadth
      multiplies whatever is downstream of it, including the mistakes

> **These boxes track `main`, which can run ahead of the latest published release.**
> [CHANGELOG.md](CHANGELOG.md) is the authoritative record of what shipped in the version
> `pipx install boardwatch` gives you; anything under *Unreleased* needs an install from
> source.

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

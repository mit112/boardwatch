# boardwatch

**A self-hosted job radar for technical job seekers.** Point it at the companies you
care about; it watches their **official ATS job boards**, catches new postings early,
ranks them against your profile with an explainable score, and hands you a shortlist —
all on your own machine.

[![CI](https://github.com/mit112/boardwatch/actions/workflows/ci.yml/badge.svg)](https://github.com/mit112/boardwatch/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/boardwatch.svg)](https://pypi.org/project/boardwatch/)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

> **Status: pre-release, under active development.** No auto-apply, ever. No telemetry.
> No accounts, no API keys. Your data stays in a local SQLite file.

```console
$ boardwatch top
 #   Title                            Company     Score   Why
 12  Senior Backend Engineer          Stripe      0.86    covers 9/11 skills · title · 1d
 7   Software Engineer, Platform      Linear      0.81    covers 7/10 skills · title · 3d
 33  Backend Engineer (Payments)      Ramp        0.74    covers 6/9 skills · 2d
 5   Full-Stack Engineer              Supabase    0.68    covers 5/8 skills · title · 6d
 18  Infrastructure Engineer          OpenAI      0.61    covers 4/9 skills · 4d
```

*(Illustrative output. `#` is the posting id — pass it to `boardwatch show <id>` for the
full posting and a per-component score breakdown.)*

---

## Why boardwatch?

Job boards optimize for their advertisers, not for you. LinkedIn/Indeed bury fresh roles
under sponsored noise and stale reposts; paid trackers put a subscription (and their
servers, and your search history) between you and postings that are **already public**.

boardwatch takes the direct route. Greenhouse, Lever, and Ashby each expose a **public,
keyless JSON endpoint** for every board they host — the same data the company's own
careers page renders. boardwatch polls those endpoints politely, on your schedule, and
tells you what's *new* since last time.

|                          | boardwatch            | LinkedIn/Indeed        | Paid trackers          |
|--------------------------|-----------------------|------------------------|------------------------|
| Source of truth          | company's own ATS     | aggregated + sponsored | aggregated             |
| Freshness                | as fast as you poll   | ranking-dependent      | vendor-dependent       |
| Your data                | local SQLite, yours   | the product            | on their servers       |
| Cost                     | free (self-hosted)    | free-ish (ad-driven)   | subscription           |
| Auto-apply / spam        | never                 | —                      | sometimes              |

**Honest limits.** boardwatch only covers companies hosted on **Greenhouse, Lever, or
Ashby** (a large slice of tech, but not everyone — no Workday/Taleo/etc. yet). It reads
exactly what those APIs expose. It is pre-release: expect rough edges, and read
[Responsible use](#responsible-use--legality) before pointing it at boards you don't own.

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

- **`init`** — one-time setup: choose companies (starter set / registry search / paste),
  then your profile (résumé text, target titles, excludes, locations, remote-only).
- **`scan`** — fetches every watched board through a polite fetcher (per-host pacing,
  retries with backoff, conditional `If-None-Match`/`If-Modified-Since` so unchanged
  boards cost a `304`), then applies each board transactionally. Prints a one-line summary.
- **`top [N]`** — ranks open postings against your profile *right now* (weights are read
  live), newest-and-most-relevant first, with a one-line "why".
- **`show <id>`** — the full posting plus a per-component score table (skill coverage,
  title match, recency, location fit).
- **`companies`** — `add` / `remove` / `search` / `list` / `import` / `export` your watched
  boards. `boardwatch companies add https://boards.greenhouse.io/acme` just works.
- **`doctor`** — per-board connectivity and freshness, plus a local DB integrity check.
- **`config show` / `config set`** — tune politeness and ranking weights (see below).

### Ranking, briefly

Each posting gets a 0–1 score: a weighted blend of **skill coverage**, **title match**
(fuzzy), **recency** (exponential decay), and **location fit**. Undefined components
renormalize away, so a sparse profile still ranks sensibly. Nothing is precomputed —
change a weight and the next `top` reflects it. `show <id>` prints the exact arithmetic.

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

## Supported boards

| Provider  | Public endpoint boardwatch reads                     | Auth |
|-----------|------------------------------------------------------|------|
| Greenhouse| `boards-api.greenhouse.io/v1/boards/<slug>/jobs`     | none |
| Lever     | `api.lever.co/v0/postings/<slug>`                    | none |
| Ashby     | Ashby public job-board posting API                   | none |

boardwatch ships a bundled **registry** of verified public boards (35+ companies, with a
curated **starter set**), so `init` works offline out of the box. You can watch any board
these providers host — not just the registry — with `companies add`. The registry is
community-maintainable by PR; see
[`src/boardwatch/registry/README.md`](src/boardwatch/registry/README.md).

---

## Responsible use & legality

boardwatch reads the **same public, keyless endpoints that power each company's own
careers page** — it does not scrape rendered HTML, log in, or bypass any access control.
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

- **Local-first.** Everything lives in one SQLite file in your platform data directory
  (override with `--data-dir`). No server, no account, no cloud.
- **No telemetry.** boardwatch phones home to nobody.
- **No secrets.** v1 has nothing to authenticate, so there's nothing to leak.

---

## Roadmap

- [ ] PyPI + GHCR published releases (`pipx install boardwatch`, `docker run …`)
- [ ] Notifications on new matches (desktop / webhook)
- [ ] `scan --new` event cursor (only what changed since last run)
- [ ] More ATS providers (community-driven)
- [ ] Data-portability export (`--format jsonl|csv`)

Have a company on a board boardwatch doesn't reach yet, or an ATS you want supported?
[Open an issue.](https://github.com/mit112/boardwatch/issues)

---

## Contributing

Contributions welcome — code, registry entries, or bug reports. See
[CONTRIBUTING.md](CONTRIBUTING.md) for dev setup (`uv sync`, `make check`) and
[the registry guide](src/boardwatch/registry/README.md) for adding a company board.
All changes land via PR against a branch-protected `main`.

## License

[MIT](LICENSE).

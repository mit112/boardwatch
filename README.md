# boardwatch

**A self-hosted job radar that reads the fine print.** Point it at the companies you
care about. boardwatch watches their **official ATS job boards**, catches new postings
early, and ranks them against your profile with an explainable score. It also reads each
posting for the hard eligibility requirements that quietly rule people out (visa
sponsorship, security clearance, a required degree, years of experience, a location) and
flags the ones you could not actually apply to, each backed by the exact sentence it read
as evidence. For the leads worth your time it renders a one-page résumé PDF tailored from what
you wrote, never adding a claim you did not make, and lays them out in a local web page to work
through. Nothing is guessed, nothing phones home, and it all runs on your own machine.

[![CI](https://github.com/mit112/boardwatch/actions/workflows/ci.yml/badge.svg)](https://github.com/mit112/boardwatch/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/boardwatch.svg)](https://pypi.org/project/boardwatch/)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](https://github.com/mit112/boardwatch/blob/main/LICENSE)

> **Status: pre-release, under active development.** boardwatch does not submit
> applications: it finds and evaluates postings, and you decide what to do with them.
> No telemetry. The default install needs no accounts and no API keys (the LLM tiers are opt-in).
> Your data stays on your machine: a local SQLite file and the folders `run` writes.

```console
$ boardwatch top 5
 #   Title                            Company     Score   Eligibility   Why
 12  Senior Backend Engineer          Stripe      0.86    no flags      covers 9/11 skills · title · 1d
 7   Software Engineer, Platform      Linear      0.81    check         covers 7/10 skills · title · 3d
 33  Backend Engineer (Payments)      Ramp        0.74    no flags      covers 6/9 skills · 2d
 5   Full-Stack Engineer              Supabase    0.68    no flags      covers 5/8 skills · title · 6d
 18  Infrastructure Engineer          OpenAI      0.61    check         covers 4/9 skills · 4d
2 hidden as ineligible. "no flags" means no catalogued disqualifier was detected, not that you qualify.
41 hidden as non-software roles — see them with --include-non-swe, each with the title text that vetoed it.
→ `boardwatch show <#>` for the full posting and eligibility evidence
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

boardwatch takes the direct route. Greenhouse, Lever, Ashby, Workable, SmartRecruiters,
Workday, Eightfold, Oracle HCM, Phenom and Jibe each serve every board they host from a
**public, keyless endpoint**, the same data the company's own careers page renders; Amazon's
and Apple's own career sites are read the same way. boardwatch polls those endpoints politely,
on your schedule, and tells you what's *new* since last time.

|                          | boardwatch            | LinkedIn/Indeed        | Paid trackers          |
|--------------------------|-----------------------|------------------------|------------------------|
| Source of truth          | company's own ATS     | aggregated + sponsored | aggregated             |
| Freshness                | as fast as you poll   | ranking-dependent      | vendor-dependent       |
| Reads eligibility        | audit + quoted proof  | no                     | no                     |
| Your data                | local SQLite, yours   | the product            | on their servers       |
| Cost                     | free (self-hosted)    | free-ish (ad-driven)   | subscription           |
| Auto-apply / spam        | never                 | no comment             | sometimes              |

**Honest limits.** boardwatch's boards cover companies hosted on **Greenhouse, Lever, Ashby,
Workable, SmartRecruiters, Workday, Eightfold, Oracle HCM, Phenom or Jibe**, plus Amazon and
Apple (a large slice of tech, but not everyone, no Taleo/etc. yet). Opt-in discovery lanes
(`lanes_enabled`, off by default) can add postings from listings beyond the ATS boards —
LinkedIn guest search, Indeed, hiring.cafe, GitHub new-grad lists and schema.org JSON-LD
pages — and are held to a different standard, set out under
[Responsible use](#responsible-use--legality). It reads exactly what those sources expose. Its
bundled role knowledge covers software roles: another field can declare its own role families
at `init`, but the eligibility catalog is still software-first. It is pre-release: expect rough
edges, and read [Responsible use](#responsible-use--legality) before pointing it at boards you
don't own.

---

## Quickstart (a first shortlist in a few minutes)

**Prerequisites.** Python 3.11–3.13 and [pipx](https://pipx.pypa.io/) (or
[uv](https://docs.astral.sh/uv/)). Scanning and ranking need nothing else. Building résumé PDFs
additionally needs two binaries on `PATH` — [tectonic](https://tectonic-typesetting.github.io/)
and poppler's `pdfinfo`:

```bash
brew install tectonic poppler                       # macOS
sudo apt-get install poppler-utils                  # Debian/Ubuntu (tectonic: see its docs)
```

`boardwatch doctor` reports whether both are present. The Docker image bundles them.

> Supported on macOS and Linux. Windows is best-effort — see [platform support](https://github.com/mit112/boardwatch/blob/main/docs/platform-support.md).

```bash
pipx install boardwatch      # isolated, on your PATH (or: uv tool install boardwatch)
boardwatch init              # pick companies, then describe what you are looking for
boardwatch scan              # poll the watched boards (polite, conditional GETs)
boardwatch top               # ranked shortlist
boardwatch show <#>          # one posting: score breakdown and eligibility evidence
```

`boardwatch init` is interactive. Pick **[1] Starter set** to watch 15 well-known boards in one
keystroke, **[2] Search registry** to pick from the bundled catalog, or **[3] Paste** any
`provider:slug` or board URL. Then paste your résumé text or a short profile, a few target and
excluded titles, and locations. The eligibility questions are optional (you can answer them
later). Last, name your field for the role filter: `software` uses the bundled role knowledge,
any other name asks for your own role families, and blank leaves the filter off. On the
starter set the first `scan` takes well under a minute (about 30 s and 3,200 postings when this
was written), and the first `top` about two minutes, because it reads and evaluates every new
posting once; after that `top` answers in a second or two.

Two settings most people want next, both in `boardwatch profile edit`: a **target seniority
band** (`entry`, `mid` or `senior`; the default `any` leaves the seniority filter off) and
**target countries** (ISO-3166 alpha-3 codes such as `USA`), without which the country-based
location filters stay off.

`top` remembers what it showed you: a lead it surfaced stays off `run`'s shortlist for
`seen_ttl_days` (7 by default), so the same job is not served twice. `top --no-record` looks
without marking anything seen.

New here? `boardwatch guide` prints the full command reference, generated from your installed
copy. It is written for a coding agent working on your behalf, so it also says what each command
reads and writes; `boardwatch skill` prints a short skill file for that agent to save.

### Other install methods

#### Docker

```bash
docker run --rm -it -v boardwatch-data:/data \
  ghcr.io/mit112/boardwatch:latest --data-dir /data init
docker run --rm -v boardwatch-data:/data \
  ghcr.io/mit112/boardwatch:latest --data-dir /data scan
docker run --rm -v boardwatch-data:/data \
  ghcr.io/mit112/boardwatch:latest --data-dir /data top
```

`init` asks questions, so it needs `-it`. Everything lives in the `boardwatch-data` volume: the
database at `/data`, and your settings, résumé files and role taxonomy under `/data/config`. The
review app (`boardwatch web`) binds loopback only, so it cannot be reached from outside the
container; for [the daily pipeline](#the-daily-pipeline), install natively.

#### From source

```bash
git clone https://github.com/mit112/boardwatch && cd boardwatch
uv sync                      # https://docs.astral.sh/uv/
uv run boardwatch init
```

---

## The daily pipeline

`scan` and `top` answer "what is new and worth a look". **`boardwatch run`** does the whole job
in one command: it scans, evaluates eligibility, ranks, re-checks that each shortlisted posting
is still live, and renders a tailored one-page résumé PDF for every lead it puts in the apply
lane.
**`boardwatch web`** then opens those leads in a local review page.

It needs a résumé to tailor, which you write once as structured YAML — boardwatch never parses
a PDF or Word file:

```bash
boardwatch tailor init       # scaffold {config_dir}/resume.yaml, then edit it
boardwatch tailor validate   # confirm it loads: entry and bullet counts, detected skills
boardwatch run --top 10      # scan → eligibility → rank → liveness → tailored PDFs
boardwatch web               # review the delivered leads in your browser
```

Edit two files in your config directory before the first `run` (`init` and `tailor init` print
their paths):

- **`resume.yaml`** — your skills and your experience entries and bullets: the only text a
  tailored résumé selects from. Its first `header` line is also your name in each PDF's file
  name and metadata, unless `answers.yaml` sets `identity.full_name`.
- **`resume_template.tex`** — the page layout, and the source of the name, contact line and
  education block printed at the top of the page. `init` wrote a starter copy, and a run
  refuses it until its placeholder identity is replaced ("Your Name", "555 555 5555",
  "you@example.com", "Example University", "Example Field"). Replace the rest of that block
  too — the city, the sample links, courses and GPA — because only those five phrases are
  checked.

What a run leaves behind:

- **`~/boardwatch-queue/`** — one folder per delivered lead, holding its tailored PDF, the job
  description, a link to the posting (`apply.webloc` on macOS, `apply.url` on Windows,
  `apply-link.txt` elsewhere) and a `details.json`. Leads a check could not clear wait in
  `_review/`, without a PDF, for you to read first; what you act on moves to `_applied/`,
  `_skipped/` or `_reported/`.
- **`~/boardwatch-applications/<date>/`** — the day's render folders, a `morning-<run>.md`
  summary, and a `funnel-<run>.md` that accounts for every posting the run considered.

The review app reads that queue. It lists the apply and review lanes with each lead's PDF,
job description and eligibility evidence, and marking a lead **applied** there keeps it from
resurfacing, just like `track`. It binds `127.0.0.1` only and authenticates with a token kept in
`{config_dir}/web-token`, so the URL it prints can be bookmarked. An optional
`{config_dir}/answers.yaml` fills a copy-to-clipboard panel with the answers every application
form asks for; nothing is ever typed into an employer's page.

Schedule `run` once a day and it becomes an unattended driver: see
[the unattended run guide](https://github.com/mit112/boardwatch/blob/main/docs/unattended-run.md)
for launchd, cron and systemd recipes, the heartbeat URL, and what a normal day's exit code
means.

---

## How it works

```
   init ──▶ scan ──▶ top ──▶ show <id> ──▶ track
   │        │        │        │             │
   companies fetch    rank on   full posting + record what
   + profile boards   demand    score breakdown you did
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
- **`track`**: record what you did with a posting — `add`, `status`, `list`, `log` — so a
  lead you already applied to doesn't resurface tomorrow. See [Your funnel](#your-funnel).
- **`eligibility`**: `facts` / `policy` to tell boardwatch your situation, `run` to
  evaluate open postings, `summary` for a funnel of what the catalog matched. See
  [Eligibility audit](#eligibility-audit).
- **`companies`**: `add` / `remove` / `search` / `list` / `import` / `export` your watched
  boards. `boardwatch companies add https://boards.greenhouse.io/acme` just works.
- **`doctor`**: per-board connectivity and freshness, plus a local DB integrity check.
- **`config show` / `config set`**: tune politeness and ranking weights (see below).
- **`run`** and **`web`**: the whole pipeline as one scheduled command, and the local review page
  for what it delivered. See [The daily pipeline](#the-daily-pipeline).
- **`guide`** / **`skill`**: the full command reference and a short agent skill file, both
  generated from your installed copy.

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
boardwatch eligibility facts set field_of_study computer_science
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
  off-by-default** model-assisted final gate inside `run` (`gate.enabled`, which calls your own
  `claude` CLI): it can withhold a lead it reads as ineligible, quoting the sentence it relied
  on, and when it reads a posting as eligible it can release into the apply lane a lead held
  for review only because the rules found no requirements to read or could not decide its
  experience bar. Turning it off stops new judge calls; the readings it already recorded keep
  applying to ranking and to the lanes.
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

`top` can also hide postings whose title names a **seniority band above the one you target** — a
"Distinguished Engineer" or a "Vice President, Engineering" that would otherwise crowd out the roles
you can actually get. This is **off until you ask for it**: the profile field `target_seniority_band`
is one of `entry`, `mid`, `senior` or `any`, it defaults to `any`, and on `any` the gate short-circuits
before reading a single title. Set it with `boardwatch profile edit`. Like the role gate it is loud:
the count appears under the table, `stats` reports it, `show <id>` explains any posting, and
`top --include-over-seniority` lists the hidden rows with the title text that decided each one.

Only a confident hit hides a posting; an unresolved level token abstains rather than guessing.
Level-aware gating is optional and documented in [configuration](https://github.com/mit112/boardwatch/blob/main/docs/configuration.md#level-aware-gating).

**The application form is not part of the posting boardwatch reads**, and on a Greenhouse board
a form question stating a citizenship, US-person or export-control requirement holds the lead for
you to read rather than writing a verdict — a form is not the posting an evidence chain can quote
from. On every other board the form is invisible, so a requirement that lives only there is a
permanent miss, and your own read of the form before you apply is the last gate.

**A posting that has been taken down does not always answer as gone:** a dead Ashby page answers
HTTP 200 with an empty shell, and a dead Greenhouse page redirects to an error URL that also
answers 200, so the per-URL liveness re-check reads both as alive. What closes them is absence
from the company's own job list — seen in a scan of a board you watch, or through that ATS's list
endpoint — so a stored URL with no board behind it can sit open indefinitely.

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

Already applied to some of these through another tool? Import that history once and those roles
stop re-surfacing. The file is a plain CSV or JSONL with the columns `company`, `title`, `url`,
`applied_at`, `status` — whatever you are migrating from, you can produce it:

```bash
boardwatch track import history.csv --dry-run --report audit.jsonl
boardwatch track import history.csv --report audit.jsonl
```

A row is matched on its url, or — with `--allow-title-match`, which is weaker because one title
at a large employer can cover several requisitions — on company and title. When that weaker key
does cover several, the row is recorded against none of them: marking a job applied removes it
from the queue for good, so guessing which requisition you meant is the one mistake you could not
find afterwards. Nothing is dropped silently: every row is counted as matched, already present,
unmatched, malformed or ambiguous, and `--report` writes each one out with the key that matched
it and the jobs it covered. Re-running the same file writes nothing.

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
The full key table lives in [docs/configuration.md](https://github.com/mit112/boardwatch/blob/main/docs/configuration.md).

`boardwatch settings` gives a read-only view of every opt-in feature (LLM tiers,
notifications) — state, what it does, what it sends anywhere — and `boardwatch settings
toggle` flips them interactively; both share the same validation as `config set`. See
[docs/configuration.md](https://github.com/mit112/boardwatch/blob/main/docs/configuration.md#settings-menu).

---

Schedule scans and get notified — see [scheduling](https://github.com/mit112/boardwatch/blob/main/docs/scheduling.md).

Run the whole pipeline unattended — see [the unattended run guide](https://github.com/mit112/boardwatch/blob/main/docs/unattended-run.md).

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
also takes `--out DIR` (default `{data_dir}/tailored`), `--format latex` (the only
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
[tectonic](https://tectonic-typesetting.github.io/), compiling a LaTeX template at
`{config_dir}/resume_template.tex` — **required, not optional**: a run refuses outright,
naming the missing path, if that file is absent, rather than silently falling back to the
bundled example template (whose header/education are placeholder text, e.g. "Your Name" /
"you@example.com"). A copy of that bundled template that was never edited is refused too. A
lead without a shippable PDF is refused rather than delivered as rendered source: a missing
`tectonic` on `PATH` fails the run loudly, and a résumé that compiles to more pages than
your profile's page limit (`resume_max_pages`, default 1, set with `boardwatch profile edit`)
is rejected. **Two binaries are required, not one** — `tectonic`
to compile and poppler's `pdfinfo` to count the pages; without `pdfinfo` the page-count gate cannot answer and every
lead is refused. `boardwatch doctor` probes for both and exits non-zero if either is
missing. Output lands at
`{data_dir}/tailored/<Your Name>_<Company>_<Role>.{tex,pdf}` — named for the application, so
it reads as itself in an employer's upload dialog, and the PDF's own Title and Author carry
`<Your Name> - <Role> - <Company>` and your name. Your name comes from your `answers.yaml`
`identity.full_name` or your résumé's header, never from the code. The path is still a
deterministic function of the lead, so **re-running `tailor run` for the same posting overwrites
that file** even though each run is recorded as its own artifact in the database; the file on
disk always reflects your most recent run, not necessarily the one you're currently reading
about. If a later compile
fails, the stale PDF from the previous run is removed rather than left behind next to the
new source.

Opt-in LLM rewriting is covered in [tailoring](https://github.com/mit112/boardwatch/blob/main/docs/tailoring.md).

---

## Career-profile bundle (advanced, optional)

`boardwatch profile-bundle` is a private, revisioned, filesystem-only store for the career
facts a résumé is assembled from: typed YAML records, evidence captured by digest, owner
approval bound to a content digest, and immutable content-addressed revisions. It lives at
`{config_dir}/career-profile` (override with `--bundle PATH`) and nothing leaves your machine.

It is an alternative to hand-writing `resume.yaml`, not a requirement. **Projection** turns a
promoted revision into a résumé: `profile-bundle approve-projection` records your approval of
the exact text it will print, and `boardwatch run --project` then renders each lead from the
bundle instead of `resume.yaml` (`resume project` followed by `tailor run --resume` does the
same for one posting). The bundle's on-disk format and JSON reports may still change between
releases.

See [docs/profile-bundle-authoring.md](https://github.com/mit112/boardwatch/blob/main/docs/profile-bundle-authoring.md) for the format, every
command, the 0/1/2/3 exit contract, and recovery from a stale draft or a corrupt evidence blob,
and [docs/projection-rendering.md](https://github.com/mit112/boardwatch/blob/main/docs/projection-rendering.md) for the path from a promoted
bundle to a PDF.

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
| Oracle HCM      | `<host>/hcmRestApi/resources/latest/recruitingCEJobRequisitions` (paginated list, plus one detail fetch per unseen posting) | none |
| Eightfold       | `<host>/api/pcsx/search`, after reading the tenant's `domain` from its public career page (plus one detail fetch per unseen posting) | none |
| Phenom          | `POST <host>/widgets` on the employer's own domain (plus one detail fetch per unseen posting) | none |
| Jibe            | `<careers-host>/api/jobs?page=<n>&limit=100` on the employer's own domain | none |
| Amazon          | `www.amazon.jobs/en/search.json`, one job category per board | none |
| Apple           | `jobs.apple.com/en-us/search` — the data embedded in the public search page, one country per board (plus one detail page per unseen posting) | none |

**Naming a board.** `companies add` takes a board URL or a `provider:slug`:

- **Greenhouse, Lever, Ashby, Workable, SmartRecruiters** — paste the board URL
  (`https://boards.greenhouse.io/acme`), or `greenhouse:acme` and so on.
- **Workday needs three parts, not one.** A Workday board is identified by a host, a tenant
  and a career-site slug, so its target form is `workday:<host>/<tenant>/<CareerSite>` — for
  example `workday:acme.wd5.myworkdayjobs.com/acme/AcmeCareers`. Pasting the career-site URL
  (`acme.wd5.myworkdayjobs.com/AcmeCareers`) works too and derives the tenant for you. Site
  slugs are **case-sensitive**; hosts and tenants are not. One tenant can serve several
  disjoint career sites, so each site is watched as its own board.
- **Oracle HCM** — paste the `…/hcmUI/CandidateExperience/en/sites/<Site>` URL, or
  `oraclehcm:<host>/<Site>`.
- **Eightfold** — paste `https://<tenant>.eightfold.ai/careers`, or `eightfold:<host>` for a
  career site on the employer's own domain.
- **Jibe and Phenom** live on the employer's own domain, so a pasted URL cannot name them:
  use `jibe:<careers-host>` and `phenom:<host>/<country>/<lang>`.
- **Amazon and Apple** are one board per job category or country: `amazon:<category>` (for
  example `amazon:software-development`) and `apple:<country>` (for example
  `apple:united-states`).

boardwatch ships a bundled **registry** of 37 verified public boards on Greenhouse, Lever,
Ashby, Workable and SmartRecruiters, 15 of them a curated **starter set**, so `init` works
offline out of the box. You can watch any board these providers host, not just the registry,
with `companies add`. The registry is community-maintainable by PR; see
[`src/boardwatch/registry/README.md`](https://github.com/mit112/boardwatch/blob/main/src/boardwatch/registry/README.md).

**Verifying a slug before you watch it.** `companies add` and `companies import` are
offline by default — they accept any well-formed `provider:slug` and let the next `scan`
or `doctor` discover a typo. Pass `--verify` to probe each board first: boards that come
back reachable are watched (a reachable-but-empty board is watched with a note), and boards
that return 404 or cannot be reached are skipped rather than written. `import --verify`
exits non-zero if it skipped anything, so a partial import does not read as a clean one.

Provider capabilities at a glance — bodies, registry counts, starter membership, and honest
limits — are in the [provider matrix](https://github.com/mit112/boardwatch/blob/main/docs/provider-matrix.md); per-provider coverage limits
are in [provider notes](https://github.com/mit112/boardwatch/blob/main/docs/providers.md).

---

## Responsible use & legality

By default boardwatch reads the **same public, keyless endpoints that power each company's own
careers page** — a JSON API for most providers, and for Apple (and the first request of an
Eightfold scan) the data embedded in that public page. It does not log in, present credentials,
or bypass any access control. That is deliberately the least-invasive way to get this
data. Still, these are third-party services, and using them responsibly is on you:

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

**The opt-in discovery lanes do not all meet that bar, which is why each is off unless you name
it in `lanes_enabled`** (`linkedin`, `indeed`, `hiringcafe`, `jsonld`, `jobapps`). They read
listings beyond an employer's own board. `jsonld` — like the GitHub new-grad lists and `grnh.se`
links that it and `companies discover` read — sends no key or credential and identifies itself
honestly, and `jobapps` only reads a folder another local tool writes. The rest go further: the
LinkedIn guest-search pages and the hiring.cafe search those lanes read are disallowed by those
sites' `robots.txt`, and the Indeed lane calls Indeed's mobile-app API while presenting that
app's own client identity. Each lane's module docstring under `src/boardwatch/lanes/` states
exactly what it requests and why. Whether to enable one is your decision, under that site's
terms.

---

## Privacy & data

- **Local-first.** Its primary store is one SQLite database in your platform data directory;
  the opt-in LLM tier also caches raw responses there as plain files on disk (override with
  `--data-dir`). No server, no account, no cloud.
- **No telemetry.** boardwatch phones home to nobody.
- **Every credential you supply is opt-in and read from the environment only**, never written
  to disk. The default path authenticates to nothing. The LLM tiers read `BOARDWATCH_LLM_API_KEY`, the
  webhook notifier `BOARDWATCH_NOTIFY_WEBHOOK_URL`, and an unattended `run` can ping
  `BOARDWATCH_HEARTBEAT_URL` (a dead-man's switch) and post its warnings to
  `BOARDWATCH_ALERT_URL`. The optional final-eligibility gate takes no key: it runs your own
  `claude` CLI. The one secret boardwatch creates itself is the review app's bearer token,
  written at mode 0600 to `{config_dir}/web-token` on first use.
  [SECURITY.md](https://github.com/mit112/boardwatch/blob/main/SECURITY.md) says exactly what each one sends.

**Where your files live.**

| What | macOS | Linux | Override |
|---|---|---|---|
| Settings and authored files (`config.toml`, `resume.yaml`, `resume_template.tex`, `answers.yaml`, `career-profile/`) | `~/Library/Application Support/boardwatch/` | `~/.config/boardwatch/` | `BOARDWATCH_CONFIG_DIR` |
| The database (`boardwatch.db`) and caches | `~/Library/Application Support/boardwatch/` | `~/.local/share/boardwatch/` | `--data-dir`, `BOARDWATCH_DATA_DIR` |
| The delivery queue | `~/boardwatch-queue/` | `~/boardwatch-queue/` | `run`/`web --queue-root` |
| Each run's PDFs and reports | `~/boardwatch-applications/` | `~/boardwatch-applications/` | `run --out`, `web --out-root` |

---

## Roadmap

- [x] PyPI + GHCR published releases (`pipx install boardwatch`, `docker run …`)
- [x] Notifications on new matches (desktop / webhook)
- [x] `digest` and `top --new` change detection (only what changed since last run)
- [x] More ATS providers: Workable, SmartRecruiters, Oracle HCM, Eightfold, Phenom, Jibe, and
      Amazon's and Apple's own career sites
- [x] Data-portability export (`--format jsonl|csv`)
- [x] Résumé tailoring (`tailor init/validate/run`, local, no-fabrication guarantee)
- [x] Workday provider (host/tenant/site composite board identity)
- [x] The unattended daily pipeline (`boardwatch run`) and a local review app (`boardwatch web`)
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
- [ ] A measured acceptance run — the daily numbers published rather than asserted (in progress)
- [ ] Broader company coverage, but only after the above shows the funnel converts; breadth
      multiplies whatever is downstream of it, including the mistakes

> **These boxes track `main`, which can run ahead of the latest published release.**
> [CHANGELOG.md](https://github.com/mit112/boardwatch/blob/main/CHANGELOG.md) is the authoritative record of what shipped in the version
> `pipx install boardwatch` gives you; anything under *Unreleased* needs an install from
> source.

Have a company on a board boardwatch doesn't reach yet, or an ATS you want supported?
[Open an issue.](https://github.com/mit112/boardwatch/issues)

---

## Contributing

Contributions welcome: code, registry entries, or bug reports. The smallest useful one is
adding a public board — see the [Contributing a board walkthrough](https://github.com/mit112/boardwatch/blob/main/CONTRIBUTING.md#contributing-a-board),
which has a one-command local check. See [CONTRIBUTING.md](https://github.com/mit112/boardwatch/blob/main/CONTRIBUTING.md) for dev setup
(`uv sync`, `make check`) and the [registry guide](https://github.com/mit112/boardwatch/blob/main/src/boardwatch/registry/README.md) for the
catalog schema. All changes land via PR against a branch-protected `main`. Questions and ideas
are welcome as [issues](https://github.com/mit112/boardwatch/issues) too.

## License

[MIT](https://github.com/mit112/boardwatch/blob/main/LICENSE).

# Run-result delivery and the local review web app — design

**Date:** 2026-08-26
**Status:** revision 4. Revision 1 was reviewed by `gpt-5.6-sol` (verdict BLOCK, 11 findings), by
four read-only probes of the repository, and by an adversarial friction critique measured against the
live store. Every finding is resolved below. Three changed the architecture.
**Scope owner:** Mit

---

## 1. The problem

boardwatch produces leads and then hides them. A run writes a résumé PDF, an apply URL, a title, a
score, a verdict, a coverage report and an eligibility evidence chain — then puts them in a flat
dated folder whose subfolders are named `accenture-52780`, beside 23 separate per-run report files.
Nothing tells the owner what is left to apply to.

Measured on 2026-08-26:

| Fact | Value |
|---|---|
| Output root | `~/boardwatch-applications/<UTC date>/` |
| Runs that day | 23 (launchd fires 8×/day, plus manual runs) |
| Lead folders that day | 230, flat, no run attribution |
| Lead folder name | `<company-slug>-<posting id>` (`pipeline/runner.py:708-714`) |
| Résumé files | `tailored-<posting id>.{tex,pdf}` (`reports/tailor.py:742-747`) |
| Per-run files | `funnel-<id>.{json,md}` **and `morning-<id>.{json,md}`** — the JSON of both exists |
| Store | `boardwatch.db`, 2.0 GB |

**The goal, in the owner's words:** applying to jobs is boring, so this should reduce friction as
much as it can. Every decision is judged against one question — does it shorten the path from "a job
exists" to "I applied"?

## 2. What job-apps does (the prior art this was asked to learn from)

1. **A per-lead folder named for the job**, at `APPLY_QUEUE/<ATS>/<Company>_<Role>/`, holding
   action-ordered files: `1_apply.webloc`, `2_Mit_Sheth_<Company>_<Role>.pdf`,
   `3_Cover_Letter_<Role>.pdf`, `4_Applied.command`, `5_Skip.command`, plus `job_description.txt`
   and `discovery_record.json`. The `.command` files mark the tracker and move the folder into
   `_applied/` or `_skipped/`.
2. **`daily_report.md`** — one deterministic report per day, parsed from that day's artifacts.
3. **`dashboard.py`** — a local HTTP server on `localhost:8050` with clickable links, status
   management and filtering.

What transfers: action-ordered files, human-readable folder and PDF names, the JD text sitting next
to the résumé, and a queue that drains. What does not: cover letters (banned repo-wide), and
`.webloc`/`.command` as the only interface, since both are macOS-only.

## 2.1 A measurement error this design is built to prevent

Two numbers in revision 3 were wrong, and the second matters more than the first.

1. Delivered leads were bucketed by `artifacts.created_at` over a 24-hour window and read as one
   day's output. It was **251 artifacts spanning runs 88-114 — twenty-six runs.** Every run delivers
   exactly ten; the cap is holding.
2. "Off-target" was computed by a title regex written for the measurement and reported as though it
   were the ranker's verdict. It was not. Measured with the shipped gate over post-fix runs (92+):
   **220 delivered — 151 `swe`, 69 `uncertain`, zero `not_swe`.** The role gate is not leaking;
   `role_verdict("Risk Strategy Execution Analyst")` returns `not_swe`, and the veto fires on the
   daily driver's path (`pipeline/runner.py:895`), not only on `top`.

**Roughly half of the 69 `uncertain` are real engineering roles the taxonomy does not know** — ASIC
Implementation Engineer STA, CPU Core Logic Designer, Silicon Photonics PIC Design Engineer,
Quantitative Developer, Quantum Computing Measurement Engineer, Android Systems Engineer, Threat
Hunter. That is the population the pass-through exists to protect. So `uncertain` is **never** styled
as a warning in the UI, and no ranker change is made in this pass.

Hence D15: the UI never computes a judgement. It renders the gate's verdict and the gate's own reason
string. A hand-written pattern inside a UI is invisible and permanent.

**Three data regimes exist on 2026-08-26 and no figure may be compared across them:** the watched
fleet went 140 → 235 boards at ~11:40 CDT, and `workable:alphax` (59 open postings, 0% `swe`) was
unwatched at ~12:10 CDT.

## 3. Decisions

| # | Decision | Source |
|---|---|---|
| D1 | The database is the single source of truth. Disk and browser are both views. | design |
| D2 | A draining queue is added **as a separate root**, holding only copies. The dated tree is never moved, renamed, or added to. | forced by probe — see §4 |
| D3 | A local web app is built in addition to the on-disk shape. | owner |
| D4 | Two pages: leads to triage, runs to diagnose. | owner |
| D5 | The leads page covers delivered leads. **The "what the cap cut" view is DEFERRED** — serving it read-only needs a new parameter on a ranker function the scheduled pipeline also calls, which should not arrive as a side effect of a web page. | owner, 2026-08-26 |
| D6 | Both update live as the owner marks things applied. | owner |
| D7 | Frontend is React + Vite + Tailwind. The node-in-a-Python-wheel cost was stated and accepted. | owner |
| D8 | Backend is the Python standard library's `http.server`. No new Python dependency. | design |
| D9 | In scope: decide-without-leaving-the-page, and a reusable answers panel. | owner |
| D10 | Deferred: keyboard triage, bulk skip, follow-up dates, applied history, closed-posting auto-drain. | owner |
| D11 | VibeCurb (`awwwards-sections`, `awwwards-motion`) governs the visual design; WCAG 2.2 AA is the floor. | owner |
| D12 | No new table and no migration. Historical per-posting ranking is **not** persisted. | forced by probe — see §6.3 |
| D13 | The queue is searchable and filterable, and the apply/applied controls live on the row, not only in the detail pane. | forced by friction measurement — see §6.5 |
| D14 | The detail pane leads with a decision block. The JD body is secondary, not dominant. | forced by friction measurement — median JD is 6,093 characters |
| D15 | Every role and eligibility judgement shown in the UI comes from the shipped gate, never from a pattern written for the UI. The role badge displays `role_verdict`'s own `reason`, which carries the matched text. | forced by a measurement error — see §2.1 |

## 4. Why the queue is a copy layer under its own root

Revision 1 proposed moving lead folders into a queue and renaming their PDFs. A read-only sweep of
every consumer of the output tree found that this breaks the repository in ways no test would catch
until production:

| Consumer | What a move or rename does |
|---|---|
| `cli/verify_cmd.py:130,134` via `store/reconcile_queries.py:64-76` | Reports `missing_typ_file` / `missing_pdf_file`. `verify` with no `--run` sweeps every funnel, so the whole command starts exiting 1 the moment the first lead is marked applied. |
| `pipeline/freshness.py:97-110` and `pipeline/runner.py:1272-1277` | Resolves each `resume_tailored` artifact's `uri` **parent** as the lead folder. A mismatch is a run-level fatal mid-run, and permanently unreconciled for historical runs. |
| `reports/tailor.py:874-880` | The projected master artifact is content-addressed and written once, so its `uri` pins the first folder that ever produced those bytes. A move orphans it with no rewrite path. |
| `pipeline/funnel_writer.py:240`, `reports/run_funnel.py:1328,1604`, `reports/morning.py:129,207` | Absolute lead paths are frozen into immutable per-run artifacts. Every historical one would point at a folder that moved. |
| `.agent/2026-08-25-craft-findings/b4_fabrication_audit.py:127-129` | Identifies a delivered résumé as any directory holding both `resume.projected.yaml` and `projection-manifest.json`. If queue folders lack those, it audits **zero files and reports clean** — a fabrication gate failing open. |
| `.agent/…/build_p4_blind_sample.py:47,51`, `finish_line_cert.py:54` | Glob `tailored-*.pdf` and derive the company from `folder.rsplit("-",1)[0]`. Renaming yields an empty blind sample (fails open) and a cert that reports every lead missing. |
| ~20 tests | Pin `_slug`'s exact output, `tailored-<pid>.{tex,pdf}`, `<parent>/_failed/<folder>.log`, and lead-folder depth. Two of them become **silently vacuous** rather than red. |

Therefore:

- **The dated tree is untouched.** Same root, same `_slug` folder names, same `tailored-<pid>.*`
  filenames, same sidecars, same `_failed/` sibling, same staging behaviour. Nothing in the run path
  changes. Every test, harness, artifact URI, `verify` and freshness check keeps working unmodified.
- **The queue is a second root**, `~/boardwatch-queue/` by default, holding **copies only**. No
  `artifacts` row ever points into it, so no stored URI can be invalidated by a move.
- **Queue folders deliberately do NOT contain `resume.projected.yaml` or
  `projection-manifest.json`.** That one rule is what keeps `b4_fabrication_audit.py` and
  `build_p4_blind_sample.py` counting exactly the canonical set. It is a correctness constraint, not
  a tidiness preference.

```
~/boardwatch-applications/           # machine record. UNCHANGED.
  2026-08-26/
    accenture-52780/  tailored-52780.pdf  tailored-52780.tex
                      resume.projected.yaml  projection-manifest.json
    funnel-114.json  funnel-114.md  morning-114.json  morning-114.md

~/boardwatch-queue/                  # the owner's workspace. Copies only.
  Intel_EDA_Tools_Software_Engineer/
    Mit_Sheth_Intel_EDA_Tools_Software_Engineer.pdf   # copy of the canonical PDF
    apply.webloc            # apply.url on Windows, apply-link.txt elsewhere
    job_description.txt     # from posting_versions.body_text
    details.json            # includes source artifact id, run id, content hash
  _applied/
  .queue.lock
```

### 4.1 Naming (`delivery/names.py`, pure, no I/O)

- Folder: `slug(company) + "_" + slug(title)`. On collision with a **different** posting, append a
  short stable hash of the posting identity — not the raw id, so the name stays stable if ids shift.
- Résumé copy: `slug(profile_full_name)_slug(company)_slug(title).pdf`. The name comes from the
  profile, never hardcoded.
- `slug()`: NFC-normalise; collapse whitespace and punctuation runs to `_`; strip the
  Windows-illegal set `< > : " / \ | ? *` and control characters; strip leading and trailing dots and
  spaces; reject the reserved device names (`CON`, `PRN`, `AUX`, `NUL`, `COM1`-`COM9`, `LPT1`-`LPT9`);
  preserve non-ASCII letters.
- **Length is budgeted in UTF-8 bytes, not characters, against the longest final destination.** The
  planner is given the resolved root and computes the budget for `<root>/_applied/<folder>/<longest
  child filename>` — so a path that is legal in `queue/` cannot become illegal when it drains into
  `_applied/`. Per-component cap is 200 bytes; the title truncates first, on a grapheme boundary,
  and a truncated component gets a stable hash suffix so two different long titles cannot collide.
- Empty result after slugging falls back to `posting_<hash>`, never to an empty component.
- Slugging is lossy, so `details.json` carries the unslugged title and company.
- Duplicate folders are reconciled **by posting identity recorded in `details.json`**, never by
  parsing the folder name. Nothing in the design ever derives data from a queue folder's name.

### 4.2 `details.json`

Posting id, canonical job id, the run that delivered it, company, title, location, apply URL, board
target, verdict, first-seen date, posted date (or null), the copied PDF's filename, and the lineage
required by review finding 3: **source `artifacts.id`, source `uri`, and content hash of the copied
PDF**. It is a projection; if it disagrees with the database, the database wins and the next sync
rewrites it.

### 4.3 Sync, drain and locking (`delivery/queue.py`)

- `sync_queue(conn, root)` derives the whole queue from the database and makes the filesystem match.
  Idempotent: a folder whose `details.json` content hash already matches is not rewritten.
- Called from three places: at the end of a run (failure logged and swallowed, exactly like the
  funnel emit at `runner.py:1319` — a queue failure must never fail a run), at web-server start-up,
  and after every successful mark-applied.
- **Writes are staged then renamed.** A folder is built under `.staging-<random>/` in the same root
  and `os.replace`d into place, so a crash cannot leave a half-written folder that the page lists as
  a lead.
- **One lock guards sync, reconcile and mark-applied**: a third `filelock` non-blocking lock
  following the two that already exist (`profile_bundle/locking.py`, `scan/coordinator.py`), binding
  `RECLAIM_WINDOW_SECONDS` by name in its own module as `core/lock_reclaim.py` requires. Contention
  is reported, never queued.
- **Reconcile runs on start-up, after any failed move, and on a timer while serving** — not only at
  start-up. For every posting with an applied application whose folder is still in the queue, move it
  to `_applied/`; for every folder in `_applied/` with no applied row, move it back. Anything it
  cannot classify is left alone and reported, never deleted.

## 5. Marking applied

Review finding 4 is confirmed: `applications` keys on the canonical `job_id` (`tables.py:354`), not
on a posting; `track add` returns early if the job has *any* application, including `interested`
(`cli/track_cmd.py:59-66`); `set_application_status` always appends an event even when the status is
already `applied` (`store/applications.py:137-164`).

So a new single writer is added:

```
store/applications.mark_job_applied(conn, *, posting_id, source) -> MarkResult
```

One transaction. Resolves `job_id` via the existing `job_id_for_posting` (`funnel_queries.py:37`),
links `posting_version_id` via `current_posting_versions`. If the job's latest attempt is already
`applied`, it returns `unchanged` and appends **no** event. If an attempt exists in another status it
transitions that attempt; if none exists it creates one. A missing posting and a posting with no job
are distinguished in the return value rather than collapsed into one error string, which is the flaw
in the current CLI message. Both `boardwatch track` and the web endpoint call this and nothing else.

## 6. Where each answer comes from

### 6.1 The queue — from the database

The delivered set is already persisted: one `artifacts` row per lead with `kind='resume_tailored'`,
carrying `run_id`, `job_id` and `posting_version_id` (`tables.py:385-404`, written at
`reports/tailor.py:884-893`). So the queue is:

> tailored artifacts ⋈ posting_versions ⋈ postings ⋈ companies, minus `applied_job_ids`,
> deduplicated by posting with the most recent delivery winning.

This resolves review finding 2: the queue is **every delivered, unapplied lead across all runs**,
not the latest run's leads. "Latest run" is a filter on that list, never its definition — otherwise a
run that delivers nothing would silently present an older run as current.

**Deduplication is by canonical job, not by posting.** Measured on the live store: 227 postings fall
into 100 multi-posting job groups. `applications` keys on `job_id`, so a posting whose sibling was
applied to must not reappear. One queue entry per job, showing the most recently delivered posting.

> **Departure, ruled 2026-09-02 (D-432).** "The most recently delivered posting" is no longer the
> whole rule, and the sentence above is kept as written so the departure is visible rather than
> silently overwritten. The winner is now the job's **LIVE** posting where it has one; delivery
> recency decides only between equally live ones. As written, a dead lane copy tailored after the
> employer's own live requisition decided the whole job, so `closed_job_ids` reported the JOB
> closed and a live requisition was filed under `_closed`, which offers nothing again — measured on
> the live store as one job, eBay 35249. Both liveness ties behave exactly as this paragraph says.

**Measured scale, which the design must survive on day one:** 656 tailored résumés exist across 547
distinct postings, and `applications` has **zero rows, ever**. So the first sync produces a queue of
roughly 540 entries, not ten — fewer once the unwatched board's nine drain out. It grows by about
**80 a day** (ten per run, eight scheduled runs). Every decision below about search, filtering and
drain follows from those two numbers.

### 6.2 One lead's detail — from frozen data

| Field | Source |
|---|---|
| JD body | `posting_versions.body_text` via `queries.current_posting_versions` (`queries.py:473`). **Never `postings.body_text`**, which `scan/apply.py:174` rewrites in place. |
| Eligibility evidence | `eligibility/audit.load_audit` (`audit.py:109`) — per-rule disposition, rationale, the profile field the rule read, and the quote sliced from the frozen body at `audit.py:203`. |
| Title, company, location, URL, first seen, open/closed | `postings` ⋈ `companies`. No store function exists for this shape; one is added rather than a fourth inline SELECT. |
| Score and "why ranked here" | Recomputed live by `rank/heuristic.score_posting` and `rank/explain.why_summary` — both pure. **Not persisted.** |
| Résumé coverage (covered / missing) | Recomputed live by `tailor/coverage.coverage_report` — pure. **Not persisted.** |

Two honesty consequences shown in the UI:

- Score, why and coverage are labelled **as of now**, not as-delivered. For a lead delivered three
  days ago the current number is the more useful one, but it must not be presented as the run's.
- **Age reads `—`, not `0d`, when the board publishes no date.** It derives from the nullable
  `postings.posted_at` (`rank/explain.py:52`); `first_seen_at` is a different quantity and is shown
  separately.
- If a posting has no current version, the API returns the detail with the JD marked unavailable
  rather than raising — the two existing callers disagree here (`audit.py:132` tolerates,
  `projection/posting.py:66-71` raises), so the API picks tolerate and says so.

### 6.3 "The rest" — DEFERRED, and why it could never have been historical

The below-the-cap population is not stored anywhere, and this is deliberate: `core/ledger.py:34-37`
declines to persist per-posting rank drops because it would be roughly 20,000 writes a run with no
reader. Review finding 1's proposed fix — immutable per-run ranked tables — is therefore **rejected
as contradicting a documented decision of this repository.**

A historical reconstruction is impossible regardless: `postings` is mutated in place (title,
locations, status), a run records only a *hash* of its weights (`reports/manifest.py:44`), and the
profile is overwritten on edit. Only the current answer exists.

So "the rest" could only ever have been a **live, read-only re-rank labelled as of now** — and it is
**deferred** (D5). The queue already holds ~540 entries, which makes a second list the least valuable
surface in the design, and the change it needs is not web-local: `rank_open_postings` (`cli/top_cmd.py:225`) is a writer
three times over: `run_preflight` writes the profile's skills and backfills extractions
(`extract/preflight.py:40,56`), `run_eligibility` inserts evaluations **and mints a `runs` row via
`ensure_run`** (`eligibility/preflight.py:174-178`), and `_record_surfaced` writes dispositions.
Only the third has an opt-out today. **A web request calling it as-is would create a phantom run on
every page load** — the automated form of the empty run 91 already in the live store.

The fix would be a `preflight=False` parameter. But `rank_open_postings` is imported and called by the
**daily driver** (`pipeline/runner.py:756` and `:895`), so that parameter would land in the scheduled
pipeline path too. A parameter on a function the unattended run depends on must not arrive as a side
effect of building a web page. **Nothing in this pass touches `cli/top_cmd.py`.**

### 6.4 What each queue row carries, and why

Chosen against measured availability on the live store, not by guesswork. A field that is mostly null
is worse than absent, because an empty column reads as a value.

| Field | Availability | In |
|---|---|---|
| title, company, location | 48,263 / 48,285 postings | yes |
| `remote_policy` | 22.6% definite corpus-wide; over the runs 88-114 delivery set, 52 remote / 10 hybrid / 2 onsite | **yes** — the first question a new grad asks, and absent from every artifact today |
| age from `posted_at` | 48,026 / 48,285 | yes, as `—` when null |
| open / closed `status` | **35 postings with a tailored PDF are already closed** | yes, as a label |
| thin JD | free: `coverage.fraction is None` | **yes**, as one boolean badge |
| off-target role family | **From `role_verdict`, never from a UI pattern (D15).** 69 of 220 post-fix deliveries are `uncertain`, about half of them real engineering titles the taxonomy missed | yes, as a label carrying the gate's own `reason` string |
| sponsor / target flag | `companies.tags_json` | yes where present |
| `salary_min` | **56 / 48,285 — 0.12%** | **no.** Omitted deliberately |

### 6.5 Search, filter and sort

At 547 entries the list is not workable without them, and the source measurement is direct: today's
231 leads include 12 same-company-same-title duplicate groups covering 28 rows.

- A free-text box filtering company, title and location as you type.
- A minimum-score input.
- Column sort, user-initiated.
- The status band recomputes against the active filter, and shows **applied ever**, not applied today.
  With zero applications ever recorded, "applied today: 0" and "applied ever: 0" are indistinguishable,
  and only the second says whether the tool works.

**Correction to a rule stated too broadly in revision 2.** "The list never re-orders under the pointer"
applies only to a *background refresh*: a new run must never reshuffle rows while the owner is reading.
User-initiated sorting is not merely allowed, it is required — a triage list you cannot sort is not a
triage list.

### 6.6 The runs page — from each run's own funnel file

`funnel-<run_id>.json` is the artifact designed for exactly this question, is already read per-run by
`verify`, and carries the stage-by-stage drops by name with `derived` marked. The runs page reads it
from the dated tree. Nothing new is written.

## 7. The web app

### 7.1 Routes

| Method | Path | Returns |
|---|---|---|
| GET | `/api/queue` | Every delivered, unapplied lead across runs. Ranked. |
| GET | `/api/queue/<posting_id>` | The full detail of §6.2. |
| GET | `/api/pdf/<posting_id>` | **Streams** the canonical PDF, `Content-Type: application/pdf`, `Content-Disposition: inline` with the human-readable filename, so it opens in a browser tab beside the job rather than in a separate viewer. Resolves through the `artifacts` row, then asserts the resolved path is contained under the output root before opening. |
| POST | `/api/queue/<posting_id>/applied` | `mark_job_applied`, then queue reconcile. Idempotent. |
| POST | `/api/queue/<posting_id>/reveal` | Opens the platform file manager at the queue folder. POST-only, path-containment checked, and the UI hides the button where the platform has no handler. |
| GET | `/api/answers` | The answers panel content. |
| GET | `/api/runs`, `/api/runs/<run_id>` | Recent runs, and one run's funnel. |

Review finding 8 is resolved: returning a local path does not make it openable from an HTTP origin,
so the PDF is streamed and reveal is an explicit server operation.

### 7.2 Database access

`store/db.py` has no read-only opener; `get_engine` (`db.py:41-55`) creates the directory, opens
read-write and sets `journal_mode=WAL` on every connection. So a `get_readonly_engine(data_dir)` is
added:

- Python `sqlite3` with a `file:...?mode=ro` URI. This is the **only** route that works against both
  a live and a cleanly-checkpointed store: the `sqlite3` CLI fails `SQLITE_CANTOPEN(14)` with no
  `-shm`, and `immutable=1` silently skips the WAL and reads stale.
- No `mkdir`, no `journal_mode` pragma, `query_only=ON`.
- It **keeps** the `unsafe_wal_filesystem` check (`store/fs_safety.py`, raised at `db.py:24-44`). A
  read-only opener that skipped it would silently permit the case that check exists to catch.
- Reads use a request-scoped read-only connection. The writer is opened only inside
  `mark_job_applied`. A locked database is a bounded retry and then **HTTP 503**, never a five-second
  stall ending in an exception.

### 7.3 Security

The API serves demographic answers and third-party text, so review finding 7 is adopted in full:

- **The token is stable per install**, stored in the config directory at mode 0600 — not minted per
  launch. A per-launch token cannot be bookmarked, so it costs three actions at the start of every
  session, and it buys nothing: it is passed to the browser opener, so it appears in that process's
  argv and any same-user process can read it from `ps`. What the token genuinely defends against is a
  malicious page in the browser reaching loopback by DNS rebinding or a cross-site form post, and a
  stable secret sent in a header defeats that just as well. The URL becomes pinnable.
- The URL carries it **in the fragment**; the app reads it, calls `history.replaceState` immediately,
  holds it in memory, and sends it only in an `Authorization` header. Nothing token-bearing enters
  browser history or a referrer.
- The `Host` header is checked against the bound loopback address, which is the other half of the
  rebinding defence.
- Bind `127.0.0.1` only; a non-loopback bind is refused, not warned about.
- Cross-origin requests and preflights are rejected. `Referrer-Policy: no-referrer` and a CSP with
  no inline script and no remote origins.
- **The JD body is rendered as text, never as HTML.** Apply URLs come from third-party boards, so
  only `http:` and `https:` are rendered as links, opened with `noopener noreferrer`; anything else
  is shown as inert text.
- `answers.yaml` is never written into an output folder, never copied into an artifact, never logged.

## 8. The two pages

**Motion personality: Surgical** (Linear, Raycast, Vercel dashboard). Exactly three curves:
`--ease-out` for arrival, `--ease-in-out` for state, `--ease-snap` for hover. No springs, no scroll
reveals, no counting-up numbers, no ambient motion.

`awwwards-motion`'s "every element animates" mandate is deliberately not applied. The same skill's
frequency gate overrides it: something used 100+ times a day gets zero animation. This is a tool
opened daily, not a landing page.

### 8.1 Queue page

A tabular-numerals status band, then full-width rows — not a card grid, which would cost the ability
to compare eight jobs at once. Each row: rank, title, company, location, age, verdict label, score,
coverage. Selecting a row opens a detail pane (right on desktop, full-height sheet on mobile), an
asymmetric bento with one dominant cell:

| Cell | Content |
|---|---|
| **Dominant: the decision block** | Company, title, location, remote policy, age, open/closed, score, verdict, off-target and thin-JD badges — everything needed to decide without reading prose. Modelled on job-apps' JD header, which puts exactly this above the text. |
| Requirements | Covered and missing as two labelled lists. **When the JD yields no recognised requirements, the pane says so explicitly** — two empty lists read as "nothing missing", which is the most dangerous possible rendering, and this is not rare: 3 of run 114's 10 leads were in that state. |
| Evidence | Which rule cleared or abstained, against which profile field, quoting the JD span |
| Secondary, scrollable | The frozen JD body, rendered as text. Median 6,093 characters, p90 8,635 — roughly a thousand words, so it is what you read *after* deciding, never the largest element. |
| Actions | Open apply link · Open PDF (inline tab) · **Copy PDF path** · Reveal folder · Mark applied |
| Answers | The reusable panel, **expanded** — the owner opened this pane on purpose |

**"Copy PDF path" is the highest-value single button in the design.** Both the macOS and Windows file
dialogs accept a pasted absolute path, which collapses the measured three-to-five action détour
through Finder into one paste. The identity fields also get one "copy the whole block" control, turning
seven copy-paste round trips into one.

**The apply and mark-applied controls also live on the row.** Requiring a pane-open per lead costs one
extra action multiplied by the size of the queue.

### 8.2 "The rest" — not built

Deferred with D5. The app ships exactly two routes: the queue and the runs page. It is not built
behind a flag either — dead code in a first cut is worse than a missing page.

### 8.3 Runs page

The funnel as connected vertical stages, each naming what entered and what dropped by name, with
`derived` stages marked so no reader mistakes a partition that balances by construction for
evidence. Coverage as one quiet metric band. Boards behind an accordion. A picker for recent runs.

### 8.4 Colour, type, accessibility

Dark-first, one accent, tight palette. Verified against WCAG 2.2 AA by computation, not by eye:

| Token | Value | On `#0B0C0E` | On `#14161A` |
|---|---|---|---|
| text primary | `#E8EAED` | 16.24 | 15.03 |
| text secondary | `#9AA1AB` | 7.51 | 6.95 |
| text tertiary | `#7C838D` | 5.11 | 4.73 |
| control / focus boundary | `#606774` | 3.44 | 3.18 |
| accent (selection, focus ring) | `#4DB6E2` | 8.48 | 7.85 |
| decorative divider | `#2A2E35` | 1.44 — decorative only, never carries meaning |

Body text ≥ 4.5:1, UI boundaries ≥ 3:1, visible focus rings, 44px touch targets, no meaning carried
by colour alone.

**The three verdicts are not a good-to-bad ramp.** `eligible` and `ineligible` take opposing fills;
`uncertain` takes an outlined, unfilled chip — visually orthogonal, not "in between". The repo's rule
is that abstain is never folded into either neighbour in any report, and a page is a report.

### 8.5 Motion

| Interaction | Behaviour |
|---|---|
| Row hover | Background tone shift, 120ms `--ease-snap`. No lift, no tilt. |
| Detail pane open | 8px slide plus fade, 180ms `--ease-out` |
| Mark applied | The row collapses to zero height over 200ms and the counts retarget, **with a toast carrying an undo** for as long as it is visible. Revision 2 had no confirm and no undo, which made a mis-click unrecoverable. CSS transition, not keyframes, so rapid clicks do not stutter. |
| A write fails | An error toast and the row returns. The optimistic update is reverted, never left inconsistent with the database. |
| Copy button | Label swaps to "Copied" for 1.2s. No bounce. |
| New run lands | A quiet "N new leads — refresh" line. The list never re-orders under the pointer. |
| `prefers-reduced-motion` | Opacity only, everywhere |

## 9. The answers panel

A new local `answers.yaml` beside the config. Schema in the repo, values on the owner's disk, never
committed. `answers.example.yaml` ships with placeholders only.

```yaml
identity:  { full_name, email, phone, city_state, linkedin, github, portfolio }
work_auth: # from the profile's eligibility facts where they exist — never restated
education: # read from resume.yaml — never retyped
questions: # entries of { q, a, note }. `note` is shown and never copied.
           # notice period, salary expectation, "why this company", and the
           # demographic questions if the owner chooses to store them
```

`identity`, `work_auth` and `education` are all read from existing files, so in practice this file only
ever holds `questions` — which is what job-apps' `Common_App_Questions.md` already is. The `note` field
exists because a bare `{q, a}` pair is a **downgrade** on that file: its most important entry carries a
twenty-line "do not reuse as-is, two claims are contradicted by the source repo" warning. There has to
be somewhere to put that, and it must never end up on the clipboard.

Read-and-copy only. Nothing types into an employer's page: the repo bans auto-fill and browser
automation, and copy-to-clipboard keeps the owner as the actor.

## 10. Build, packaging and the gate

| Concern | Decision |
|---|---|
| Source | `web/` — Vite, React, TypeScript, Tailwind |
| Shipped form | Built bundle committed to `src/boardwatch/web/static/`. **Verified empirically:** hatchling ships arbitrary non-Python files under `src/boardwatch/` with the current `pyproject.toml` and no new configuration, including nested subdirectories, and with no `__init__.py`. Confirmed in both wheel and sdist. |
| **The one trap** | `.gitignore:6` is `dist/`, unanchored, so it matches a `dist` directory at any depth — and Vite's default `outDir` is `dist`. The bundle would be silently dropped from every wheel. **Vite's `outDir` must be set to `src/boardwatch/web/static/`.** A packaging override would re-include the file in the build while leaving it untracked in git, so any wheel built from a clean checkout would ship an empty UI. |
| Size | Current wheel 1.05 MiB; a minified bundle adds roughly 5-9% compressed. |
| Freshness | `make web` records a hash over **every build input under `web/` except the output directory and `node_modules`** — sources, `package.json`, the lockfile, and the Vite, TypeScript, Tailwind and PostCSS configs. A pytest test recomputes it and fails on mismatch. |
| Stronger check | CI rebuilds and compares the emitted asset manifest and per-asset content hashes against the committed bundle. Adopted (review finding 11). **Measured correction:** revision 3 claimed Vite output is "not byte-reproducible enough to diff directly". Two consecutive builds produced byte-identical assets, so the comparison is a plain sorted `sha256sum` listing of the output directory — which, because Vite content-hashes asset filenames, is simultaneously the asset manifest and the per-asset hashes. A changed, renamed or dropped asset all surface in one diff. |
| `make check` | Targets unchanged (`generalization index-check lint type test`). The freshness check is a test, so it runs on all three operating systems with no node installed. |
| CI | One new Linux-only job: `make web`, `tsc --noEmit`, eslint, and the asset-manifest comparison. The Python matrix is untouched. |
| Types | `mypy --strict` for the new Python. TypeScript checked in the node job. |

**Tests.** Naming and slug rules including the Windows reserved set, the UTF-8 byte budget, and the
`_applied/` destination budget; queue sync idempotency; reconcile in both directions; staged-write
crash recovery; `mark_job_applied` idempotency and its no-event-on-repeat guarantee; the read-only
engine refusing writes; token rejection; non-loopback bind refusal; PDF path containment; a
`javascript:` apply URL rendering inert. No JavaScript unit tests in the first cut.

## 11. Out of scope

Unchanged repo-wide exclusions: cover letters, outreach, auto-apply, auto-fill, browser automation.
The apply link is a link the owner clicks; the answers panel is a clipboard, not a form filler.

Deferred by owner decision (D10), not oversight: keyboard triage and bulk skip, follow-up dates,
applied history, closed-posting auto-drain.

## 12. Open questions

0. **A lane-sourced lead can never close, so the queue cannot tell "still open" from "unverifiable".**
   Measured 2026-08-26: **282 lane-acquired postings, every one `open`, none ever closed.** The only
   path to `closed` is `_process_missing` in `scan/apply.py`, which runs on `complete` snapshots only,
   and `lanes/base.py::lane_snapshot` deliberately always returns `partial` because a lane never
   enumerates a whole board. `pipeline/liveness.py::check_leads` writes nothing, and lane companies are
   `watched=False` so the coordinator never revisits them. A lane re-acquires by *search*, so a posting
   that drops out of the result set is simply never seen again rather than counted missing — **absence
   can never be evidence for a lane posting.** Consequence for this design: the queue's `closed` label
   will never appear on a lane-sourced row even when the job is long gone. The detail pane's board
   target (`hiringcafe:…`) is the only signal available, and skip is the only drain. Not fixed here —
   an age-based close needs a trigger other than absence and is an owner decision.

1. **A posting that closes while it sits in the queue.** Auto-drain is deferred, so the folder stays.
   The page will still *show* open/closed state, because the store knows it and hiding it would send
   the owner to a dead application. Confirm that labelling without draining is what is wanted.
2. **`_skipped/` does not exist, and the measurements say this is the design's weakest point.**
   Single-lead skip sits in the deferred bundle (D10), so a lead the owner rejects has nowhere to go and
   returns on every sync. Against the measured numbers that is not survivable: the queue starts at ~547
   entries, grows by ~231 a day, and **50 of today's 231 delivered leads carry no engineering word in
   the title at all** — front-desk agent, tax CPA, drywall estimator, personal shopper. In job-apps,
   which has the same shape, `_skipped` holds 72 folders against `_applied`'s 64 — rejecting is the more
   common terminal action. Search makes those rows easier to find, not fewer. **Reversing D10 for skip
   alone is the owner's call and is requested.**
3. **Retention.** Nothing prunes `_applied/`, and nothing prunes the dated tree. Out of scope as
   asked, but the queue makes the growth visible for the first time.
5. **Nothing tells the owner a run finished.** `cli/run_cmd.py` never calls notify. The desktop channel
   exists with zero dependencies (`notify/desktop.py`) but is off by default, and its own text points at
   the CLI rather than the web app. launchd fires eight times a day into silence. A one-line text change
   plus enabling it would remove the "remember, unprompted, that runs happened" step that currently
   opens every session. Cheap, but outside the original ask.
4. **Separate from this work:** hatchling reads `.gitignore` but not `.git/info/exclude`, so an sdist
   built from a checkout with linked worktrees packages them — measured at 2,493 files and 39 MiB.
   The published `0.5.0` sdist was checked and is clean (833 entries, no worktree paths), so this is
   a hazard for the next release, not a leak that happened. One line fixes it: add `"/.claude"` and
   `"/.playwright-mcp"` to the existing `[tool.hatch.build.targets.sdist] exclude`.

## 13. Risks

| Risk | Mitigation |
|---|---|
| A node toolchain enters a published Python package | Bundle committed, node confined to one CI job, wheel verified to install and serve without node |
| The queue and the database disagree | Database authoritative; the queue holds no independent state; reconcile on start-up, after any failed move, and on a timer |
| The queue disturbs an existing contract | It cannot: separate root, copies only, no artifact row points into it, and it deliberately omits the two sidecars the fabrication gate counts |
| A web request mutates the store | Read-only engine for reads; `preflight=False` for the live re-rank; the only writer is `mark_job_applied` |
| The answers panel leaks | Loopback bind, token in a header, no cross-origin, CSP, never written to artifacts or logs |
| Slugging produces an illegal or colliding path | One pure module, byte-budgeted against the longest final destination, hash-suffixed on truncation, and duplicates reconciled by recorded identity rather than by folder name |

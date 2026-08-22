# Coverage assurance — can boardwatch replace job-apps without missing JDs?

**2026-08-22 · design · status: awaiting owner ruling on Track 5**

Mit's ask, verbatim: *"boardwatch will be running daily. I need to know with confidence and clarity that
it can replace job apps and i dont have any insecurity that it does not miss any jd's job apps wont."*

This document records what was **measured** to answer that, and designs the work that follows. It
supersedes the comparative posture retired by **D-008** (`PROGRAM.md` §4 lists "Statistical parity testing
vs job-apps" under *Deliberately NOT doing*). Reopening that is Mit's call and is recorded as such.

---

## 1. The answer, measured

**boardwatch cannot currently see ~92% of the postings job-apps surfaces as eligible.** The insecurity is
correct. It is not a defect — it is the architecture.

Corpus: job-apps' 530 eligible records carrying a company name, over 2026-08-12 … 2026-08-21, taken from
`resumes/<DATE>/eligibility_manifest.json` where `status == "eligible"`. Match rule: company name
normalised (lowercased, punctuation stripped, corporate suffixes removed, whitespace removed) against both
`companies.name` and the leading label of `companies.slug` for all 135 rows where `watched=1`, giving 159
distinct keys. Both numbers are stated because a ratio needs its match rule and its corpus size (D-268).

| | count | share |
|---|---:|---:|
| eligible records at a company boardwatch watches | **41** | **7.7%** |
| eligible records at a company boardwatch has never heard of | 489 | 92.3% |
| distinct companies in that eligible set | **352** | — |
| of those, watched by boardwatch | **24** | 6.8% |

**No 135-board hand-curated list covers 352 companies.** The largest missing employers are not obscure:
Amazon 25, TikTok 20, AWS 8, Apple 7, ByteDance 7, SpaceX 6, IBM 5, Vanguard 5. None of them uses
Greenhouse, Lever, Ashby, Workday, SmartRecruiters or Workable — **adding a board slug cannot reach them**;
each needs a bespoke first-party adapter.

### 1.1 Where boardwatch is *better*

The comparison is not one-directional, and the direct-ATS half of it favours boardwatch:

- **Greenhouse / Lever / Ashby** — 86 boards in job-apps, 85 here. Both fetch an entire board in one
  un-paginated request; neither has a cap. But job-apps applies `_is_relevant_career_page_title` **inside
  the fetch loop** and discards non-SWE before storing, while boardwatch stores everything and filters at
  rank time. **boardwatch holds strictly more.**
- **Workday** — job-apps does not enumerate; it *searches*, with three hardcoded strings
  (`WORKDAY_SEARCH_QUERIES`), `WORKDAY_MAX_PAGES_PER_QUERY = 2`, and
  `WORKDAY_MAX_DETAILS_PER_COMPANY = 12`. On 2026-08-21 its 39 Workday boards yielded **77 roles total,
  with 16 boards returning zero**. boardwatch enumerates the whole board. **boardwatch is dramatically
  better here.**

So the gap is not fetch depth on shared boards. It is **which companies are reachable at all**.

### 1.2 The lane that carries the gap

job-apps touched **1,183 distinct companies** on 2026-08-21 and 3,966 over seven days; only 94 were
direct-ATS. Lane attribution of the 538-record eligible set (8 unattributed, never folded into either side):

| lane | eligible records | **lost if lane removed** |
|---|---:|---:|
| commercial aggregators (LinkedIn, Indeed, hiring.cafe) | 446 | **421** |
| GitHub new-grad lists | 103 | **73** |
| direct ATS (the six boardwatch providers) | 14 | **5** |

Only **5.8%** of eligible records were seen by more than one lane. The lanes are almost entirely
non-redundant, so a lane's yield cannot be recovered by another lane.

**The GitHub lists are the outlier finding.** SimplifyJobs, jobright, vanshb03 and speedyapply are
`raw.githubusercontent.com` README fetches — five plain HTTP GETs against public repositories, no auth, no
rate-limit negotiation, curated specifically for new-grad roles. They carry **19.1% of the entire eligible
yield**. The decision that excluded "aggregators" (`boardwatch-vs-jobapps-decision-v2.md` §4.1) was argued
on ToS and anti-bot-treadmill grounds — an argument that is strong for LinkedIn and Indeed and does not
obviously reach a public GitHub JSON file. They were swept up by category, not on their merits.

### 1.3 A counterweight

job-apps' median 42/day is **not** 42 good jobs. The same eligible set contains Infosys 5, TCS 5,
BeaconFire 5, Capgemini 3, UST 2 — staffing firms and body shops — plus artifacts named `Jobright.ai`,
`RemoteHunter`, `Sapphire Partners`, `Stealth Startup` and a literal `↳`. Roughly a fifth is noise
boardwatch's existing gates would reject. The gap is smaller than 92%. It is nowhere near zero.

### 1.4 The 8-vs-42 shortfall is a *separate* problem

`DEFAULT_TOP_N = 8` (`pipeline/runner.py`). Run 67's shortlist stage reconciles exactly:

```
30,243 entered · 17,891 hidden_hard_filter · 7,981 hidden_non_swe · 3,502 capped_by_top_n
   493 hidden_ineligible · 335 hidden_over_seniority · 23 hidden_duplicate · 10 hidden_handled · 8 leads
```

**3,502 postings cleared every gate and were discarded by the cap.** job-apps' 42 is a *natural yield* —
there is no top-N constant anywhere between its discovery and its manifest. Raising the cap to 40 matches
job-apps' volume but **does not close the parity gap**, because the two shortlists would overlap by ~8%.
Both facts are true and must not be conflated.

The cap also makes P7's own gate un-runnable: per-source yield is `8/26,997` with *the numerator fixed by
construction*, so no source can be judged by "leads produced over ≥3 runs" while the cap is 8.

---

## 2. Coverage defects found, with evidence

### 2.1 Workday's `total` is censored at 2,000; the facet counts are not

`WorkdayProvider` reads `payload["total"]`, which Workday caps at 2000. Facet dimensions aggregate
server-side by a different path and are uncapped. Probed live 2026-08-22, one POST per board with the exact
body `_search_body(0)` already builds:

| board | `total` | facet sum | boardwatch holds | coverage | |
|---|---:|---:|---:|---:|---|
| Citi | 2,000 | **4,589** | 600 | **13.1%** | censored |
| NVIDIA | 2,000 | **2,656** | 600 | 22.6% | censored |
| Adobe | 740 | 740 | 600 | 81.1% | agrees |
| Intel | 645 | 645 | 600 | 93.0% | agrees |
| Regeneron | 592 | 592 | 600 | 101.4% | agrees |
| Fidelity | 565 | 565 | 600 | 106.2% | agrees |

**The known-positive control passed**: on every board under the cap the facet sum equals `total` exactly,
so the metric can agree when it should and is not a number that cannot fail (the failure mode that produced
D-267 and the deleted `SourceTotal` check).

Two consequences:

1. **Citi's real board is 4,589 postings.** boardwatch's pager also wraps at ~2,000, so even its *listed*
   count (600 held + 1,614 deferred = 2,214) is under half the board. When the backlog drains, boardwatch
   will hold ~2,214 and **still be permanently missing ~2,375 Citi postings, invisibly.** This is a real
   blind spot and it is *not* the detail budget.
2. **Coverage over 100% is the mirror defect.** Regeneron 101.4% and Fidelity 106.2% mean boardwatch holds
   postings the board no longer lists. Those boards are permanently `partial`, and `_process_missing` runs
   only on `complete` — so nothing can ever close a posting there and dead rows accumulate.

### 2.2 The detail budget is a real queue, and it has an ETA

D-270's reading is **correct** and a contrary claim raised during this session was checked and rejected.
Every board's deferred backlog falls monotonically, 26–49 per scan, no exceptions; 15 boards have drained
to completion (35 boards reporting a backlog → 20).

| board | deferred @ run 67 | drains/run | runs to zero |
|---|---:|---:|---:|
| Citi | 1,614 | 33.7 | **48** |
| Wells Fargo | 1,479 | 33.7 | 44 |
| Target | 1,572 | 38.9 | 40 |
| NVIDIA | 1,511 | 44.5 | 34 |
| Fidelity | 104 | 43.4 | 2 |

**At one run per day the 15,535-posting backlog clears in about seven weeks.** Raising
`detail_fetch_budget` shortens it proportionally.

The contrary claim was that Workday serves newest-first and `unseen[:50]` re-takes the same prefix forever,
so tails are never read. It was inferred from Citi's shallow `posted_at` history (max age at capture 2
days). The date column falsifies the generalisation: Databricks reaches back to 2019-11, Cisco to 2025-12,
Adobe to 2026-03. Those boards *are* reading their tails. **Citi is an outlier, not the pattern.**

### 2.3 Seventeen boards produce nothing — and five of them report green

- **12 dead boards**, all Workday, all `last_ok_at IS NULL` — they have *never* succeeded in 12 scanning
  runs over 16.5 days. Failure set is exactly {401 × 4, 403 × 1, 422 × 7}. Workday returns **422 for a
  malformed request body**, not for auth, which points at a wrong tenant/site slug — i.e. **recoverable
  coverage**. Never diagnosed.
- **5 boards that scan cleanly and return an empty list** — Snyk, Vercel, HubSpot, Plaid, Qualcomm.
  `last_health = 'empty'`, `failed_scans = 0`, `last_ok_at` current, `max_listed = 0` across all 12 scans.
  HubSpot, Plaid and Qualcomm plainly have open roles. **This is the dangerous class**: a board that fails
  loudly gets fixed; a board that succeeds at nothing does not.

`get_watched_companies` selects on `watched.is_(True)` and nothing else. There is **no backoff, no
auto-disable, no quarantine** — a dead board is retried at full cost forever, and per `CLAUDE.md`'s own
rule that quarantine has no drain.

### 2.4 `unchanged` is an unaudited assumption

59 of 135 boards listed nothing in run 67 because the payload diff reported no change
(`scan/apply.py:_scan_row` writes `postings_listed=0`). **No test and no metric exists** for whether a
payload hash can report `unchanged` for a board that did change. A false `unchanged` is a silent,
permanent coverage loss that no current instrument would ever detect.

### 2.5 The largest filter has no drain

`hidden_hard_filter` cut **17,891 postings — 59% of the corpus**. Buckets 4–9 each have an `--include-`
flag; this one has none, so the rows behind it cannot be listed from the CLI. `CLAUDE.md`: *"Every
quarantine needs a drain."*

### 2.6 The scan census already happens and is thrown away

Every provider enumerates its whole board every run. `WorkdayProvider` and `SmartRecruitersProvider` build
a complete `listed_ids` set before fetching any body; both parse a server-side total
(`payload["total"]`, `payload["totalFound"]`). Greenhouse returns `meta.total` — confirmed live
(stripe 576, databricks 818) on the *cheap* `_health_url` shape that `probe_health` already fetches for
every Greenhouse board.

None of it reaches the database. `board_scans.postings_listed` stores `len(snapshot.postings)`, which on a
capped Workday board is the budget (50), not the board size. `snapshot.listed_ids` is used transiently and
discarded. The deferred remainder exists only as English inside `board_scans.error`, which means reading it
requires string-matching a message — the thing `CLAUDE.md` forbids.

**The instrument is therefore mostly a persistence problem, not a fetching problem.**

---

## 3. Design — Track 1: the coverage instrument

The confidence deliverable. Everything else is optional; this is not.

### 3.1 Coverage is a partition, not a number

Following the keystone invariant's shape — a thing that cannot be measured gets its own bucket and is
**never folded into either neighbour**:

| bucket | meaning | ratio published? |
|---|---|---|
| `measured` | a trustworthy board-stated total exists | **yes** — `held / board_reported_total` |
| `enumerated_only` | no server total (lever, ashby, workable) | **no** — reported *not independently evidenced* |
| `censored` | Workday `total == 2000`, or the offset-wrap stop fired | **no** — real size ≥ 2000, use facet sum |
| `dark` | the board failed | **no** — undefined, not zero |
| `stale` | board answered 304; no fresh total | **no** — age-stamped, carried forward only |

The global roll-up is a weighted figure over `measured` **only**, printed beside the counts of the other
four. It is labelled **board-scoped**, because one Workday tenant can serve several sites and summing board
totals double-counts.

### 3.2 Smallest change that closes it

1. `core/models.py:BoardSnapshot` — add `board_reported_total: int | None`, `board_enumerated: int | None`,
   `detail_deferred: int | None`. The defaults are a **serialization decision**: `None` means *the board
   stated no total* and must never be silently backfilled with `len(...)`.
2. Six provider lines. SmartRecruiters and Workday set the total they already parse; Greenhouse reads
   `payload["meta"]["total"]`; lever/ashby/workable set `None` **explicitly**.
3. `scan/apply.py:_scan_row` — persist the three values. `detail_deferred` becomes a typed field at the
   raise site so the number stops living in a prose column.
4. One Alembic migration, three nullable columns on `board_scans`.
5. Workday only: sum a partition facet's `values[].count` and store it as the uncapped truth when
   `total == 2000`.
6. A read-only `boardwatch coverage` report over `board_scans` + `postings`, and a `coverage` section in
   the funnel artifact (an `artifact_version` bump — **owner-gated**, same class as D-267's `locations`
   on `Lead`).

**Zero new HTTP requests** for steps 1–4. Step 5 adds none either: the facets arrive in the response
`_search_body(0)` already fetches.

Note the funnel already has a key named `coverage` — it measures **résumé keyword coverage**
(`tailor/coverage.py`). The new section needs a different name (`board_coverage`) or the collision will
mislead every future reader.

### 3.3 How this metric could lie

A coverage metric that cannot fail is worse than none — this program has already deleted one for exactly
that reason (`SourceTotal`, D-028).

| risk | detection |
|---|---|
| **Unfailable ratio.** For lever/ashby/workable the only "total" is our own array length; coverage is 100% by arithmetic, forever. | Never compute a ratio when `board_reported_total is None`. A test must assert the ratio is `None`, **not** `1.0`. |
| **The 2,000 censor reads green where the hole is largest.** A 5,000-job board reports 2,000 and enumerates 2,000 → 100%. | Flag `total == 2000` exactly as `censored`; cross-check against the facet sum, which is uncapped. Proven on Citi (4,589) and NVIDIA (2,656). |
| **A total counting rows we cannot see** (drafts, internal reqs). | Track `board_reported_total − board_enumerated` per board over runs. A stable constant offset is counting semantics, not a leak. |
| **Dark boards vanish from the denominator.** Averaging over boards that answered prints ~100% while 12 contribute nothing. | Denominator = all **watched** boards. `dark` is its own bucket, never folded. Mirrors ABSTAIN. |
| **304 staleness.** 59 of 135 boards were `unchanged`; a carried total with a live numerator looks green during an outage. | Age-stamp every total; refuse to publish a ratio whose total is older than N runs. |
| **Rounding hides a real defect.** Mastercard run 67: `"collected 1128 of 1129"` = 99.91%, reads as noise, is actually an id-less row that shrinks `listed_ids` while status can stay `complete` — the one status authorising `_process_missing` to close postings. | Report **absolute shortfall beside the percentage**; keep `dropped_no_id` as its own typed counter. Any non-zero value is actionable. |
| **Not actually independent.** `total` arrives in the same response as the array it describes. | Call it **board-stated**, not independent, in the report's own wording. The facet sum *is* a second aggregation path and may be called independent; `total` may not. |
| **Never tested against a known positive.** | Two fixtures minimum — one where total > enumerated, one where they match — plus a mutation check that deleting the comparison turns a test red. The live control in §2.1 is the model. |

### 3.4 Testing

`make check` is the only gate. Beyond it: the ratio-is-`None` assertion, the `censored` detection against a
recorded 2,000-cap fixture, the facet-sum-equals-total control on an uncapped fixture, and a behaviour test
that this change did not author (a fixture whose board shrank between runs must move a board from
`measured` to `stale`, not silently to 100%).

---

## 4. Tracks 2–5

| # | Track | Effort | Evidence it is worth it |
|---|---|---|---|
| 2 | **Raise `DEFAULT_TOP_N` 8 → 40** | one constant | 3,502 qualifying postings discarded per run; unblocks P7's gate, which is un-runnable at 8 |
| 3 | **Recover the 17 silent boards** | slug repair | 12.6% of the registry produces nothing; 7 × HTTP 422 are probably wrong slugs |
| 4 | **Defeat the Workday 2,000 wrap** | facet-partition paging | Citi stuck at 13.1% coverage permanently otherwise |
| 5 | **Close the 92%** — owner-gated | see below | 92.3% of job-apps' eligible yield is unreachable today |

**Track 5, in value order:**

- **(a) GitHub new-grad lists** — 19.1% of eligible yield for ~5 HTTP GETs against public repos. Recommended.
- **(b) First-party adapters** for Amazon, Apple, TikTok/ByteDance — ~66 records (12.5%), the biggest names
  missing. Bespoke code, each with its own breakage risk. Arguable.
- **(c) Commercial aggregators** — 79% of yield, and the genuine ToS/anti-bot treadmill the original
  decision was written about. **Not recommended.**

Any Track 5 lane ships behind all existing gates plus a dereferencing step, with a hard assertion that no
aggregator URL survives into the final apply surface (`PROGRAM.md` P7).

---

## 5. Owner rulings required

1. **Reopening D-008.** Comparative measurement against job-apps is currently listed under *Deliberately
   NOT doing*. This document is that measurement. Supersede D-008, or reject this framing.
2. **Track 5 scope** — (a), (a)+(b), everything, or instrument-first.
3. **The cap** — 40, keep 8, or show everything eligible (Mit's stated ideal; ~3,500 rows is not renderable
   as PDFs and would need on-demand résumé building).
4. **`artifact_version` bump** for the funnel's `board_coverage` section — shipped-schema change, same
   class as D-267.
5. **Whether "breadth is last" still binds.** `CLAUDE.md` gates input-side work behind proven conversion,
   and conversion is unproven (0 applications, ever). Every one of Tracks 3–5 adds input. Mit has said
   slower runs are acceptable; that is not the same as lifting the rule.

---

## 6. Facts recorded so they are not re-derived

- job-apps runs once daily at 08:30 via `com.mitsheth.job-discovery`; each run covers its whole universe,
  no rotation. Its eligible median is 42/day (min 4, max 95, n=25 days) and is a natural yield, uncapped.
- job-apps' `target_companies.json` has 222 rows; **126** are actually crawled. 22 `custom`, 12 disabled
  (`null`), 5 iCIMS have no adapter.
- job-apps' unit — one `eligibility_manifest.json` record = one folder = one deduplicated posting — is
  **directly comparable** to a boardwatch lead.
- job-apps' Workday lane is *worse* than a 50-cap: 3 fixed queries, 2 pages, 12 details, 16 of 39 boards
  returning zero.
- boardwatch has **no** aggregator, RSS, search or scraping lane. Grepped `rss|atom|feedparser|indeed|
  linkedin|aggregat|serpapi|crawl` across `src/boardwatch/`; every hit was a false positive.
- `detail_fetch_budget` sits in `manifest.py:_CONFIG_IRRELEVANT` as `"throughput"`, so changing it does not
  invalidate a cached verdict and **leaves no manifest trace** — two runs with different corpora look
  identically configured. Given §2, the budget decides which postings exist, not throughput.
- Host concentration bounds any future probe: all 64 Greenhouse boards share one hostname and are
  serialised at ≥1.0s, so `scan_workers` buys nothing there. Workday has 38 hostnames and scales to 8.
- `doctor` is **not** read-only (`scan/health.py:_write_board_health` writes `companies.last_health`).
- The store's intake has an 11-day hole, 2026-08-08 → 08-18: 54 runs recorded `boards_attempted = 0`.

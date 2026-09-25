# JD-body acquisition for the aggregator lanes — design

**2026-08-22. Owner rulings this session: lane purpose, lane order, breadth cap, UA scope.**
Supersedes the plan sketched in D-272 and scoped in D-275. Nothing is built yet.

---

## 1. What this is for

**Owner ruling: the lanes exist to reach companies no existing route can reach.** Not to multiply
yield inside the six ATS families. That decides every trade-off below, and it rules out two
approaches that would otherwise look cheaper.

The measured gap it targets: of 352 companies job-apps found eligible roles at over
2026-08-12…08-21, boardwatch watches **24**. Amazon, TikTok, Apple and ByteDance use none of the
six supported ATS, so no slug can reach them.

**One named target is already reachable and needs nothing: SpaceX is on Greenhouse** (96 postings
across the lists, all `boards.greenhouse.io`). D-271's list of five is a list of four.

---

## 2. The finding that sets the lane order

**The engine is body-only** (`eligibility/preflight.py` selects `posting_versions.body_text` and
passes it alone), a stub is a whitespace-only body, and D-250 abstains a zero-evidence verdict to
`uncertain`. So a lane that lands titles and links adds corpus and yields **zero leads**.

Measured, per lane, this session:

| Lane | Body | Cost of the body | Reaches non-six |
|---|---|---|---|
| **Indeed via JobSpy** | **YES, in the search response** | **zero extra requests** — `description { html }` is a field of the GraphQL search query itself | yes, any employer |
| **hiring.cafe** | no, one extra GET | `GET /api/job-description?id={objectID}` — unauthenticated, 200, verified 3,463 chars | yes; its own `source`/`board_token` mix is mostly iCIMS / Oracle Cloud / Taleo / UltiPro / SuccessFactors |
| LinkedIn via JobSpy | behind a flag | `linkedin_fetch_description=True`, one GET per posting, **O(n)** | yes |
| **GitHub new-grad lists** | **none at all** | a per-posting fetch that does not exist yet | 34.7% of active entries; **53.3% duplicate the six we already scan** |

**Ruling: reverse D-272's order.** Indeed first, then hiring.cafe, then the lists. D-272 ordered
them GitHub → hiring.cafe → JobSpy on *yield and materialization quality*, which was measured on
real data but not on this question. For the purpose in §1 the order is close to backwards.

### Corrections to D-272's source list

- `vanshb03/Summer2026-Internships` now redirects to `Summer2027-Internships`; the new-grad sibling
  is `vanshb03/New-Grad-2027` (branch `dev`). `speedyapply/2026-SWE-College-Jobs` redirects to
  `2027-SWE-College-Jobs`. **A hardcoded name follows the redirect on the API but the content is a
  different season.** Pin the season explicitly, and fail loudly on a redirect rather than
  silently ingesting next year's list.
- `jobright-ai` publishes **no JSON** — README markdown only, and 100% of its links are
  `jobright.ai/jobs/info/{id}` trackers that do not redirect to the employer. Recoverable: the page
  embeds a schema.org `JobPosting` in `application/ld+json` with a real body (verified 5,298 chars).
  But its `url` and `directApply` are both null, so it never reveals the canonical apply URL.
- `speedyapply` keeps its data in a private Supabase; the only public artifact is markdown.
- Simplify's links are **86.8% direct ATS** (76.2% on the active subset). Exactly **1 of 18,823**
  is a `simplify.jobs` tracker. The tracker fear in the v2 exclusion does not apply to Simplify.

---

## 3. What the prior art proves, and what it does not

job-apps' chain is ~4,300 live lines (its own docs say 2,958 across 9 modules; D-272's "2,200" is
low). Measured over 33 scheduled runs, 9,811 stubs:

| Tier | Resolved | Share |
|---|---|---|
| LinkedIn plain HTTP (`requests.get` + one regex) | 5,950 of 6,089 attempted, **97.7% hit** | 60.6% |
| Reuse a body already fetched (no network) | 1,845 | 18.8% |
| Headless browser | 1,277 | 13.0% |
| Unresolved | 739 | 7.5% |

**The browser tier is worth 0% today.** It died 2026-08-11 — `~/Library/Caches/ms-playwright/` has
no chromium bundle — and ran 11 consecutive scheduled runs at exactly zero recoveries without
anyone noticing, because `fetch_rendered_jd` wraps everything in `except Exception: return ""`.
Corroborated three independent ways: the candidate mix did not change (185 attempts → 146 OK on
08-11; 53 attempts → 0 OK on 08-12, same Workday-family hosts), and the step's wall clock fell
from 13m58s to 1m40s to 28s. **So boardwatch's no-browser rule costs 13% of historical recovery
and 0% of current recovery**, and job-apps' own `HANDOVER.md` already documents the replacement:
Workday CXS, LinkedIn guest, and Ashby JSON endpoints, "parallel HTTP, no browser", ~786 bodies,
"higher-yield than the generic browser path".

**What it does NOT prove: there is no generic careers-page extraction anywhere in it.**
`_is_fetchable_url()` gates every fetch on **14 hand-maintained host regexes**; the browser tier has
a second, non-overlapping list of 8. An arbitrary careers page is never fetched. Apple and TikTok
have no handling at all. Amazon has a bespoke adapter — the class D-272 ruled out, and the class
that demonstrably rots (Glassdoor and ZipRecruiter removed at 100% error rate; the Google scrape
removed at 0 JDs in every logged run; **zapply silently went 585–600/day → 0 on 08-19**).

`_JDTextExtractor` is a whole-page visible-text dump with a 300-char floor — no main-content
detection, no boilerplate stripping, `readability`/`trafilatura` not installed. It works only
because it is pointed exclusively at server-rendered ATS pages. **Do not copy it as an extractor.**

**Consequence for boardwatch:** the honest route to Amazon/Apple/TikTok is *an aggregator that
carries the body*, not a careers-page reader. That is exactly §2's ordering.

---

## 4. Design

### 4.1 A lane is not a `Provider`

Do **not** register a seventh `Provider`. Two hard blockers, both verified:

- `tests/unit/test_provider_registry.py::test_build_providers_one_instance_per_class_keyed_by_name`
  asserts `set(built) == {the six names}` — a set *equality*.
- Fixture rule **R13** (`tools/generalization/fixtures.py`) requires a flat pinned fixture dir per
  registered provider, both directions, and fires immediately on a provider with no fixtures.

A lane also does not fit the protocol: `Provider` declares `board_url` / `fetch_board` /
`healthcheck` and **no `fetch_posting`**, and `registry` duck-types five further undeclared members
(`board_host_suffixes`, `slug_from_path`, `normalize_slug`, `composite_slug`, `slug_help`).

**Instead:** a `Lane` protocol of its own, returning the same `BoardSnapshot` so it reuses
`apply_board` and inherits every persistence invariant for free.

### 4.2 Persistence — the invariants a lane must not break

All verified this session by reading `scan/apply.py`:

1. **A lane MUST emit `status="partial"`, never `"complete"`.** `_process_missing` runs on
   `complete` only, and `BoardSnapshot`'s validators permit an **empty** `complete` — which sets
   `effective = frozenset()` and marks every open posting of that company missing. Two consecutive
   such scans close them (`CLOSE_AFTER_MISSES = 2`). `partial` also does not advance the
   conditional-GET validators, which is correct for a lane that never enumerates a whole board.
2. **`postings.job_id` is nullable but a trigger aborts on NULL** —
   `postings_job_required_insert` / `..._update`. Insert into `jobs` first, exactly as
   `_apply_listed` does.
3. **`_write_posting_identity` is not optional.** Skipping it for one open posting makes
   `identities_complete()` False, which turns duplicate suppression off **corpus-wide**
   (`top_cmd` only calls `resolve_duplicates` inside `if ids_complete:`) and degrades **every**
   `SourceOutcome.unique` to None.
4. **`companies.source` has `CheckConstraint("source IN ('registry','user')")`** — a lane cannot
   introduce a third value without a migration.
5. **`board_scans.status` must be one of the four `SnapshotStatus` values.**
   `reports/board_coverage.classify_board` **raises** `UnknownScanStatus` on anything else, so a
   novel status string takes down the whole coverage report rather than degrading.

### 4.3 The empty-body collision — fix before the first lane row lands

`content_hash("")` and `content_hash("   \n\t ")` are both `e3b0c442…`, the SHA-256 of the empty
string. Verified by calling it. `posting_identity.compute_identities` emits `exact_quad` from
`(company_id, normalized_title, locations, content_hash)`, and `exact_quad` is the **only**
suppressing identity kind. `dedup._verify_quad` re-verifies with
`normalize_body(a) == normalize_body(b)`, and `"" == ""` passes.

**So two genuinely different body-less postings at one company with the same normalized title and
locations suppress each other, and the verifier agrees.**

Measured on the live store (read-only, `?mode=ro`): 32,229 open postings, **13** with a
whitespace-only body, all 13 carrying that hash, clustered on two companies (9 and 4) — and **0
colliding (company, title, locations) groups**. So it is latent, not firing, today. A lane that
lands bodyless rows in volume is exactly what would fire it.

**Design: a bodyless posting must never receive an `exact_quad` identity.** Suppression requires
body evidence, and an empty body is the absence of evidence — the same reasoning D-250 used to
abstain a zero-evidence verdict rather than clear it.

### 4.4 Failure taxonomy — the one thing to copy inverted

job-apps' 11-day silent outage is the specification for what not to do. **Every acquisition
outcome is a distinct typed value with its own counter**, raised at the site that knows:

`body_inline` · `body_fetched` · `fetch_refused` (401/403) · `fetch_gone` (404/410) ·
`fetch_unavailable` (timeout/5xx/transport) · `dependency_missing` · `extracted_empty` ·
`rejected_login_wall` · `rejected_quality_gate` · `not_attemptable` (no resolvable URL)

Out-of-catalog is a failure, never a new bucket. **A tier that resolves zero for a whole run is a
reportable condition, not a benign zero** — the launchd log must be able to say "this tier
recovered 0 of 53 attempted" rather than exiting 0 in silence.

**Per-source attribution is required and does not exist yet.** `count_stub_postings` is
corpus-wide (`WHERE status='open' AND trim(body_text,…)=''`, no source filter) and `SourceOutcome`
has no stub field — so today a lane's stub rate moves the global number with nothing naming the
lane. P7 judges a source by leads over ≥3 runs, so this must land with the first lane.

### 4.5 Quality control — copy these four, they are the good part

1. **Two-sided login-wall test.** Requires ≥2 wall markers **AND zero** real-JD section markers.
   One-sided fails: nearly every real posting has "Sign in" in its footer.
2. **Boundary extraction** for a known shell (LinkedIn: start after "report this job", end at
   "seniority level"), then ≥500 chars, ≥1 section marker, ≥8 substantive lines.
3. **`role_body_mismatch()`** — if the body declares its own title and that title classifies to a
   different role family than the lead's, **refuse to write** and leave it for re-fetch.
   Precision-first: ambiguous or unclassifiable passes through.
4. **A write-back assertion** — "recovered" must mean "actually persisted", checked by re-reading.
   job-apps' `freeze_violations()` catches exactly the case where a step reports success and
   nothing landed.

**And do not repeat its quarantine bug:** `_skipped/stub_jd` holds 2,201 folders of which **1,462
now have a full body** and will never re-enter, and the designed human drain
(`--triage-unresolved`) is passed by no scheduled script — zero such folders exist. This is
boardwatch's own "every quarantine needs a drain" rule being violated in the reference
implementation. A boardwatch stub bucket ships with its drain, running on both sides of the gate.

### 4.6 Breadth cap — owner ruling

**Adding a company's whole board counts as breadth** and is subject to breadth-is-last. So the
"resolve the link to its company and watch the board" route — free for 4 of 6 providers, whose
board endpoints already inline every body (`greenhouse ?content=true&pay_transparency=true`,
`lever ?mode=json`, `ashby ?includeCompensation=true`, `workable ?details=true`) — is permitted
only under an explicit per-run cap on new companies, and every addition is reported.

Unbounded, one Simplify pull would add 5,695 companies. For scale: the largest single non-six
company in the lists is **Sainsbury's at 1,639 postings**, a UK grocer on Oracle Cloud that the
US-only gate discards anyway; TikTok alone is 613 active postings against a shortlist cap of 40.

### 4.7 Fetch posture — owner ruling

**Honest UA on the six ATS providers; a browser UA only on the new aggregator fetches.**
boardwatch ships `boardwatch/{version} (+https://github.com/mit112/boardwatch)` today and that
stays, because the package is published and other people run it. robots.txt is not parsed
(unchanged from today). The functional basis for the exception: a live Pinterest posting answers
403 to an unfamiliar UA, and job-apps' aggregator reach was measured entirely with a Chrome UA.

Politeness stays boardwatch's, not job-apps': `PER_HOST_DELAY_FLOOR = 0.25`, default
`per_host_delay_seconds = 1.0`, enforced by a real per-host lock held for the request's duration.
job-apps' one impolite path is an 8-worker pool with no delay at all — do not copy it. Note
LinkedIn guest "rate-limits hard — retry fails at 3 workers + backoff", and JobSpy's own
per-posting description fetches sit **outside** its page-loop throttle.

---

## 5. Deliberately not doing

- **A careers-page reader.** No generic extractor, no per-site DOM rules. The prior art has none
  either; what it has is a host allowlist, and the honest version of that is a provider.
- **Bespoke first-party adapters** (Amazon/Apple/TikTok direct). D-272's ruling stands and this
  session found more confirmation, not less.
- **Any browser automation.** Out of scope by `CLAUDE.md`, and measured at 0% current value.
- **Trusting hiring.cafe's pre-extracted fields.** It ships `v5_processed_job_data` with 90 fields
  including `visa_sponsorship`, `security_clearance` and `seniority_level`. These are somebody
  else's eligibility extractions. The keystone invariant requires boardwatch's own evidence chain
  with a quoted span from the frozen JD; adopting theirs would clear postings by a route that
  cites nothing. Fetch the body, judge it here.
- **DuckDuckGo fan-out.** Disabled in every one of job-apps' scheduled paths as "slow/flaky
  unattended", and it still ships. A dead tier is worse than no tier.

## 6. Open — owner's, not to be resolved by fiat

1. Whether Oracle Cloud HCM and iCIMS should become **providers** instead of, or before, any lane.
   They are ~45% of the non-six tail, they are real ATS families that fit the existing
   architecture, and job-apps' `oracle_hcm_api` dying is weak counter-evidence — its
   `smartrecruiters_api` and `workable_api` died too, and boardwatch's own versions of both work.
   This does **not** reach Amazon/Apple/TikTok.
2. The per-run new-company cap's actual number.
3. Whether the LinkedIn lane is worth its O(n) request cost given Indeed's body is free.

# Part 3 — lane wiring and the hiring.cafe client

**Goal: the first leads from a company no ATS provider can reach, end to end.**

Read `docs/superpowers/research/2026-08-23-hiringcafe-lane-contract.md` before writing any request
code. It is the pinned contract; nothing here restates a request shape it does not already record.
Part 2's groundwork — `lanes/outcomes.py`, `lanes/base.py`, `lanes/admission.py`,
`lanes/dereference.py` — is on `main` and is reused, not rebuilt.

---

## 0. What was measured this session, beyond the pinned contract

One read-only unauthenticated GET of `https://hiringcafe.com/`, no captures committed. It answered
the two fields the contract does not record, both of which the lane cannot build a `RawPosting`
without. Counts are from that fetch (159 hits that day, against 160 in the contract — the search
result is live, which is exactly why the fixture must be authored rather than frozen):

| Field | Finding |
|---|---|
| `enriched_company_data.name` | **159/159 non-blank.** The employer display name (`"Claire's"`). This is the company name to store. |
| `enriched_company_data` other keys | `homepage_uri`, `hq_country`, `industries`, `nb_employees`, `organization_type`, `parent_company` (33/159), `tagline`, `year_founded`, funding fields, `status`, `enriched_at` |
| `_geoloc` | `[{"lat": 35.1983, "lon": -111.6513}]` — **coordinates only, no place names.** Useless to `rank/location_gate`, which matches text |
| Location text | lives ONLY in `v5_processed_job_data`: `workplace_cities`, `workplace_states`, `workplace_countries`, `workplace_continents`, `workplace_counties`, `formatted_workplace_location`, `workplace_type`, `is_workplace_worldwide_ok` |
| `job_information` | confirmed `job_title_raw`, `title`, `num_views`, `viewedByUsers` — no body, no location |
| top-level keys | `_geoloc`, `apply_url`, `board_token`, `collapse_key`, `enriched_company_data`, `id`, `is_expired`, `job_information`, `liberal_dedup_cluster`, `objectID`, `requisition_id`, `source`, `source_and_board_token`, `strict_dedup_cluster_id`, `v5_processed_job_data` |
| non-blank 159/159 | `source`, `board_token`, `apply_url`, `objectID`, `requisition_id`, `source_and_board_token` |
| paging | `ssrPage=0`, `ssrPageSize=40`, `ssrIsLastPage=false`, `ssrTotalCount≈3.89M`, `ssrCompanyCount≈123k`, and **159 hits returned in one response** — four pages' worth |

### The one judgement call this forces, and it is flagged for Mit

D-278 ruled `v5_processed_job_data` **untrusted**, and the contract write-up gives the reason: those
91 fields "cite no span from the frozen JD and the keystone invariant requires a quoted span."

The location text is only there. Two readings:

1. **Untrusted means untrusted everywhere** ⇒ `RawPosting.locations = None` ⇒
   `classify_location` finds nothing to classify ⇒ it **fails open** (Mit's visa ruling) ⇒ every
   hiring.cafe posting survives the hard US gate. Against a general job board of 3.89M postings
   whose first sampled JD was a Prep Cook, that is the flood the write-up warns about.
2. **The keystone invariant governs ELIGIBILITY RULES, and location is not one.** The eligibility
   engine is body-only (`eligibility/preflight.py` passes `posting_versions.body_text` alone), so it
   structurally cannot read these fields. `RawPosting.locations` is *provider-asserted metadata* —
   and every one of the six providers already fills `locations_json` straight off its own payload
   with no span. greenhouse's `location.name` is trusted at exactly this level today.

**Taken: reading (2).** `workplace_cities` / `workplace_states` / `workplace_countries` populate
`RawPosting.locations`, at the same trust level as every other provider's location field, and
**never** as evidence for an eligibility verdict. Recorded as a decision, not buried: if Mit reads
D-278 more broadly, the fix is one function and the lane then needs a different location source
before it can be armed.

---

## 1. Design decisions

### D1 — the `Lane` protocol gains an admission callback

```python
CompanyAdmission = Callable[[str, str], bool]        # (provider, slug) -> may we spend on it

class Lane(Protocol):
    name: str
    def collect(self, fetcher: Fetcher, admits: CompanyAdmission) -> LaneResult: ...
```

**Why, and it is not a convenience.** The body costs **one GET per posting** and the per-run cap
admits **10 new companies**. With `collect(fetcher)` alone the runner can only refuse companies
*after* the lane has already paid for every body — 159 requests to keep a handful. The is-new check
also needs a store connection, which only the runner holds (`lanes/admission.py` says so explicitly
and deliberately does not build it). Passing the predicate in puts the decision before the spend
and leaves the store query with the runner. The protocol has **zero implementations on `main`**, so
widening it costs no migration.

The lane MUST call `admits` **once per distinct `(provider, slug)`**, never once per posting.

### D2 — how a hit becomes a company and a posting id

Per hit, in order:

1. Try `dereference.parse_posting_target(apply_url)`.
   - **Succeeds** (greenhouse / lever / ashby / workable) ⇒ `provider`, `slug` and
     `provider_posting_id = target.posting_ref`. This is the **convergence case** D-284 built the
     utility for: the same `(company_id, provider_posting_id)` a later board scan produces, so the
     aggregator posting converges instead of duplicating. ~5% of hits (`grnhse` 8/160).
   - **Raises** `UnknownBoardURL` or `UnresolvablePostingURL` ⇒ step 2. Both are expected and
     ordinary here; neither is an error to report.
2. `provider = "hiringcafe"`, `slug = f"{source}:{board_token}"`, `provider_posting_id = objectID`.

**`objectID` is an opaque key. Never split it.** It looks like `{source}___{board_token}___{id}` and
is that for 128 of 160 hits; a `___` split mis-attributes **36 of 160 (22.5%)** in three ways
(`taleo_careersection` single underscores, `fountain` board tokens containing `___`, `saashr` case
mismatch). `source` and `board_token` are explicit top-level keys, non-blank on every hit. Read
those. The slug is *composed from* them, never *decomposed from* `objectID`.

Company name: `enriched_company_data.name`, falling back to `board_token` when blank.

### D3 — `companies.source` gains `'lane'`, and lane companies are NOT watched

The migration is settled (D-285). The `watched` value is **new here and load-bearing**:

`scan/coordinator.py:254` does `providers.get(row.provider)`, and on a miss appends
`f"{row.slug}: unknown provider {row.provider!r}"` to `summary.errors` and continues. A watched
company keyed `hiringcafe` would therefore add one error line to **every run, forever**, and those
errors land in `runs.errors_json`. Ten new companies a run makes the run error count meaningless
within a week.

So: **lane-discovered companies are inserted with `watched=False`.** Consequences, all checked:

- `apply_board` needs only a `company_id` and does not read `watched` — postings land normally.
- Nothing in eligibility or ranking filters on `watched` (verified: the only readers are
  `scan/coordinator`, `store/coverage_queries`, `scan/health`, `doctor`, and the `companies list`
  CLI). Lane postings reach the shortlist.
- `store/run_funnel_queries.count_by_source` groups by `postings.company_id` and joins `companies`
  only for labels, so lane boards appear in the funnel's per-source table carrying
  `company_source='lane'` — the attribution comes free.
- The coverage corpus (`watched.is_(True)`) is untouched by lane-only companies.

`upsert_watch` forces `watched=True`, so this needs a sibling — `upsert_lane_company` — rather than
a new parameter on it (a defaulted parameter would silently backfill every existing caller).

**Not done here:** promoting a lane-discovered greenhouse board to `watched`. That is "adding a
board", which is breadth, and it is a separate deliberate act.

### D4 — the board-coverage double-count (D-284 debt a)

`apply_board` always writes a `board_scans` row (`scan/apply.py:81`), and
`coverage_queries.load_board_coverage` outer-joins `board_scans` on `(company_id, run_id)`, emitting
one `BoardCoverage` per joined row. A lane touching an **already-watched** company — the greenhouse
convergence case, which is the whole point — produces a second row for that pair, so the company
appears twice, once `measured` and once `enumerated_only`, inflating `corpus_boards` and
`bucket_counts`.

Fix: **`board_scans.scan_kind`**, `TEXT NOT NULL DEFAULT 'board'`, `CheckConstraint IN
('board','lane')`, written through a new `apply_board(..., scan_kind: str = "board")` parameter.
A default normally hides a decision from existing callers, but here every existing caller genuinely
*is* a board scan, so the default states that fact rather than concealing it — and the lane, the one
caller for which it is false, passes `"lane"` explicitly.

Then filter on it in `load_board_coverage`. Put the clause in the **JOIN condition, never a
`WHERE`** — the existing docstring warns that a `WHERE` silently converts the LEFT JOIN to an inner
join, since SQL compares `NULL = run_id` as NULL, and that would drop every never-scanned board out
of the corpus instead of bucketing it `unscanned`.

### D5 — `CompanyBudget.refused` is not deduplicated (D-284 debt c)

`.admitted` dedupes, `.refused` does not, so a refusal *count* overstates companies. D1 makes
`admits` a per-company call so it cannot bite in this design — but a count that lies under a
different caller is still a measurement defect. Dedupe it.

The **is-new check** (D-284 debt c, the substantive half) lives in the runner:

```python
def admits(provider: str, slug: str) -> bool:
    if company_exists(conn, provider=provider, slug=slug):
        return True          # already known: free, and NOT charged to the cap
    return budget.admit(provider, slug)
```

Without the first clause all ten slots go to companies already stored, reach never widens, and the
refusal list looks exactly like a normal capped run.

### D6 — §4.5 quality controls (new `lanes/quality.py`)

Reuse `core/html_text.py` (selectolax) for HTML→text; do not add a dependency.

- **Two-sided login-wall test** ⇒ `rejected_login_wall`. Fires only on **≥2 wall markers AND zero
  JD section markers**. One-sided fails: nearly every real posting says "Sign in" in a footer.
- **Boundary floor** ⇒ `rejected_quality_gate`: ≥500 chars, ≥1 section marker, ≥8 lines.
- **`role_body_mismatch()`** ⇒ `rejected_quality_gate`: the body declares a different role family
  than the title.
- **Write-back verified by re-read**: count the stored body through a different path than the one
  that wrote it.

Each control maps onto an existing `AcquisitionOutcome`; **no new outcome names.** The catalog is
closed and `record()` raises `UnknownAcquisitionOutcome` off-catalog.

### D7 — reporting

- One stdout line, the shape `board coverage →` already uses, so a launchd run leaves it in the log.
- A `lanes` section in the funnel: per lane, the ten outcome counts, `attempted`, `resolved`,
  `is_silent_outage`, and the admitted/refused company lists.
- **`artifact_version` stays at 6.** Additive key, on the D-113 → D-147 R3 / D-148 R3 precedent that
  D-285 verified and applied five hours ago to `SourceOutcome.stubs`. The three assertion sites
  pinning the 6 stay untouched: `tests/unit/test_run_funnel_projection.py:529-530`,
  `tests/unit/test_run_funnel.py:739`, `tests/pipeline/test_run_funnel_projection_stage.py:94`.

### D8 — configuration, and it ships OFF

New `Settings` fields:

| Field | Default | Why |
|---|---|---|
| `lanes_enabled: tuple[str, ...]` | `()` | Off. Additive for lanes 2–4 without another flag |
| `lane_new_companies_per_run: int` | `10` | `admission.DEFAULT_NEW_COMPANIES_PER_RUN` |
| `lane_posting_budget: int` | `60` | Hard ceiling on body GETs per lane per run |

**Default off is not caution, it is Gate P3.** The gate needs **7 consecutive clean scheduled
ticks** and stands at 0 of 7. Arming an unproven network lane in the daily driver puts the streak at
risk for no gain — the lane can be exercised by a manual `run --project`, which does not touch the
counter. Arm it after a scratch run proves it, the same build-then-arm order D-274 and D-258 used.

Note `settings.per_host_delay_seconds` is 1.0 and pacing is **per `Fetcher` instance**, so §4.7's
browser-UA `Fetcher` does not share a delay with the honest one. Two instances must never target the
same host. They do not here: the six providers keep the honest UA, hiring.cafe gets the browser UA.

---

## 2. Slices — three disjoint file sets, built in parallel

Ownership is by file and is strict. No slice edits another's files.

### Slice A — store and schema

Owns: one new `store/migrations/versions/*.py`, `store/tables.py`, `store/queries.py`,
`store/coverage_queries.py`, `scan/apply.py`, `lanes/admission.py`, and their tests.

1. Migration (single revision, `down_revision = "p_board_coverage"`): rebuild `companies`' check
   constraint to `('registry','user','lane')`, and add `board_scans.scan_kind`. SQLite needs
   `batch_alter_table` for a constraint change.
2. `queries.upsert_lane_company(conn, *, provider, slug, name)` → `source='lane'`, `watched=False`,
   conflict on `(provider, slug)` **leaving an existing row's `watched` and `source` alone** (a
   lane must never silently unwatch a board the user watches, nor relabel a `registry` company).
3. `queries.company_exists(conn, *, provider, slug) -> bool`.
4. `apply_board(..., scan_kind="board")` threaded to `_scan_row`.
5. `coverage_queries`: `scan_kind == 'board'` in the **join condition**.
6. `admission.CompanyBudget`: dedupe `.refused`; delete the "Open question" paragraph in the module
   docstring, which D-285 has now answered.

### Slice B — the client

Owns: `lanes/base.py` (the D1 signature only), new `lanes/hiringcafe.py`, new `lanes/quality.py`,
and their tests.

`__NEXT_DATA__` parse → `ssrHits` → distinct `(provider, slug)` → `admits` → body GET per admitted
posting → `lane_snapshot(...)` per company → `LaneResult`.

**One GET of `/` only.** `ssrPage`/`ssrIsLastPage` are recorded in the contract but the request
parameter that turns a page is **not**, and 159 hits arrive in that one response anyway. Inventing a
paging parameter would fabricate a request contract — the exact defect `lanes/dereference.py`
refuses SmartRecruiters and Workday for. If paging is wanted later it needs its own probe.

### Slice C — pipeline wiring

Owns: `core/settings.py`, `pipeline/runner.py`, `pipeline/funnel_writer.py`,
`reports/run_funnel.py`, `cli/run_cmd.py`, and their tests.

A lane stage in `run_pipeline` immediately after `run_scan` and before eligibility, built and tested
against a **stub lane**, so Slice C never waits on Slice B. Then: `upsert_lane_company` for each
admitted new company, `apply_board(..., scan_kind="lane")` per `LaneCompanySnapshot`, tally and
admission results into the funnel section and the stdout line.

A lane failure must **never** fail the run: a lane is additive breadth, and the fail-safe direction
for "judge unavailable" is fail-open. Catch, record into `summary.errors`, continue.

---

## 3. The fixture problem, and the trap on both sides

The generalization gate **refuses captured third-party payloads and is right** — R2 caught a real
employer contact address inside a JD body, R7 refused two files absent from `SHIPPED_DATA`, and
registering them obliges a `provenance` whose only honest value (`public`) then obliges a
**license**, which does not exist for a third party's job-description text in a public repo. Do not
pick `synthetic` (a lie) and do not invent a license.

So the fixture is **authored**. But an authored fixture inherits the opposite failure: it proves only
what our own code constructs — which is exactly how SmartRecruiters' round-trip passed against a
README saying "All text is synthetic", and how 5 of 6 providers passed a wrong dereference rule.

**Therefore the authored fixture must trace to this document's recorded counts, not to a guess**, and
must carry the three `objectID` counter-examples by name:

| Must appear in the fixture | Source |
|---|---|
| a `taleo_careersection` hit whose `objectID` uses **single** underscores | contract §3 |
| a `fountain` hit whose `board_token` itself contains `___` | contract §3 |
| a `saashr` hit whose `objectID` case differs from `board_token` | contract §3 |
| a `grnhse` hit whose `apply_url` dereferences to a real greenhouse target | contract §4 |
| `enriched_company_data.name` on every hit | §0 above |
| location only under `v5_processed_job_data.workplace_*` | §0 above |

A test must assert that **`source`/`board_token` reading and `___`-splitting disagree** on the
first three — that is the test the 22.5% tail earns, and a fixture of only well-formed hits cannot
fail it. Add an R15-style `review_by` drift tripwire; R13's pinned-fixture-dir rule does **not**
apply, because a lane is not a registered provider.

---

## 4. Invariants a lane must not break

- **`status="partial"` always** — `lane_snapshot()` is the only sanctioned constructor and makes
  `complete` unexpressible. An empty `complete` closes a company's entire board after
  `CLOSE_AFTER_MISSES = 2`.
- **`jobs` first, then `postings`** — an ABORT trigger enforces it. `_apply_listed` already does.
- **`_write_posting_identity` on every posting** — skipping one flips `identities_complete()` to
  False and disables duplicate suppression **corpus-wide**. `apply_board` already does it; do not
  add a path that bypasses `apply_board`.
- **A lane is never a registered `Provider`** — `tests/unit/test_provider_registry.py` asserts set
  *equality* on the six names, and fixture rule R13 wants a pinned fixture dir per registered
  provider in both directions.
- **Use the `httpx` `Fetcher`** in `core/politeness.py` with an injected `httpx.Client` carrying the
  browser UA. Never `python-jobspy` (pins `NUMPY==1.26.3`, cp312-only wheels against
  `requires-python >=3.11`, and its HTTP stack escapes the politeness lock).
- **No `verify=False`, no lifted API key, no app impersonation, anywhere.** That is why Indeed is
  parked; re-introducing the pattern for hiring.cafe would park this lane too.

## 5. Exit criteria

1. `make check` green — all five stages, launched detached against a uniquely named log + sentinel.
2. A scratch run (`BOARDWATCH_DATA_DIR` **and** `BOARDWATCH_CONFIG_DIR` both set) with the lane
   enabled surfaces **≥1 lead at a company none of the six providers can reach**, carrying a real JD
   body.
3. The funnel's per-source table shows that lead's board with `company_source='lane'`.
4. Coverage `corpus_boards` is unchanged by a lane run that touches an already-watched company.
5. `artifact_version` still reads 6.

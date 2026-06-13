# Ashby fixtures

Captured fixtures for the Ashby provider contract tests (Task 17 / Issue #17, GH #32).

## Provenance & sanitization (D9 / §6.6 / §0 guardrail 2)

These fixtures use the **exact response shape** of the Ashby public posting API
(`GET https://api.ashbyhq.com/posting-api/job-board/<slug>?includeCompensation=true`),
recorded during an attended session on **2026-06-13** from a public board only. The
structure (top-level `{apiVersion, jobs}`; per-job fields and the compensation tree below)
mirrors the live API.

**All text is synthetic.** No real company copy, names, URLs, recruiter contacts, or other
data was carried over from any recorded board — only the field *shape* was. There are no
email addresses or PII of any kind (CI's gitleaks job and a fixture-time scan both confirm
this). The company is the invented "Acme Corp"; `jobUrl`/`applyUrl` point at a fictional
`acme` board. The loop never fetches a live API (§0); it only reads these files.

## Recorded field names (the Issue #17 / GH #32 contract — plan deviation 5)

Confirmed against the live shape at the attended session. Per-job:
`id`, `title`, `jobUrl`, `location`, `secondaryLocations[].location`, `department`, `team`,
`publishedAt` (ISO 8601), `isRemote` (structured boolean), `descriptionHtml` (→ `html_to_text`),
and `compensation`.

**Compensation tree (path corrected at this session — plan deviation 5 amendment):**

```
compensation
├── compensationTierSummary            (display string)
├── scrapeableCompensationSalarySummary
├── compensationTiers[]
│   └── { id, tierSummary, title, additionalInformation,
│         components[] {                <-- the per-tier monetary list the provider reads
│           id, summary,
│           compensationType,           ("Salary", "EquityPercentage", "Bonus", …)
│           interval,                    ("1 YEAR", "1 MONTH", "NONE", …)
│           currencyCode, minValue, maxValue } }
└── summaryComponents[]                 (a flattened compensation-LEVEL mirror of the same
                                         leaf fields; present live but NOT the path the
                                         provider reads — it reads compensationTiers[].components[])
```

> **Amendment note:** the plan originally pinned `compensationTiers[].summaryComponents[]`.
> The live `ramp` recording confirmed every leaf field name exactly but showed that a tier
> has **no** `summaryComponents` key — its monetary list is `components[]` (a flattened
> `summaryComponents[]` exists only at the compensation level). Per deviation 5's
> CONFIRM-OR-STOP rule the session stopped and the plan was amended (Option B): the path is
> `compensationTiers[0].components[0]`. Semantics unchanged: salary scalars are written
> **iff** exactly one tier holds exactly one `Salary` component in a single currency with a
> recognized interval.

## Recorded dead-board signature

A non-existent board returns **HTTP 404** with body `Not Found` (`content-type: text/plain`,
**not** JSON). `dead.json` holds that literal recorded body; the contract test serves it with
status 404 → `BoardHealth.DEAD` / `failed`.

## Validators

The live API serves a `Last-Modified` header but **no `ETag`**.
`normal_response_headers.json` carries a real-shape synthetic `etag` plus a recorded-shape
`last_modified` so the conditional-GET (304) contract test can exercise both `If-None-Match`
and `If-Modified-Since`.

## Files

| File | Purpose |
|---|---|
| `normal.json` | A healthy board: `{apiVersion, jobs}` with 6 postings. The fixture contract below. |
| `huge.json` | D26's maximum-supported representative fixture: synthetic Ramp-scale, **110 postings, ≥ 1.7 MB on disk**, unique ids. Parsed in a subprocess under a tracemalloc ≤ 64 MiB ceiling. |
| `empty.json` | A live but vacant board: `{"apiVersion": 1, "jobs": []}` → a *complete, empty* inventory (a 200, not a 304). |
| `dead.json` | The recorded dead-board body (`Not Found`), served with HTTP 404. |
| `normal_response_headers.json` | The `etag` / `last_modified` validators for the 304 exchange. |

## `normal.json` contract (relied on by `tests/contract/test_ashby.py`)

- **≥ 5 postings**, each with `id`, `title`, `jobUrl`, `location`, `publishedAt`,
  `descriptionHtml`; `body_text` (via `html_to_text`) is non-empty and HTML-free.
- **≥ 1 posting with single-tier / single-`Salary`-component / recognized-interval compensation**
  → `salary_*` scalars populated (the fixture has a `1 YEAR` and a `1 MONTH` case).
- **≥ 1 one-sided** posting (`minValue` only, `maxValue` null) → present side mapped.
- **≥ 1 multi-tier** posting (`len(compensationTiers) > 1`) → all `salary_*` NULL, `raw_json` intact.
- **≥ 1 posting with NO `compensation` block** → all `salary_*` NULL.
- `jobs[0]` has a `title` (the partial-parse test deletes it to force a `partial` snapshot).
- At least one posting derives `remote_policy == "remote"` (via `isRemote: true` or a `"remote"`
  location name).

If any file is missing or the contract is not met, Task 17 must STOP — that is an
attended-session gap, not loop work.

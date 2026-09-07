# Jibe fixtures

Captured fixtures for the `jibe` provider contract tests (T64). "Jibe" is the iCIMS Career
Sites front end: an employer serves its own careers host (`careers.acme.test`) and that host
exposes a public JSON listing API at `/api/jobs`.

## Provenance & sanitization (D9 / §6.6 / §0 guardrail 2)

These fixtures use the **exact response shape** of the public listing API
(`GET https://{host}/api/jobs?page={n}&limit={k}`), recorded during an attended, read-only
session on **2026-09-06** against four public employer career hosts (rate-limited to
1 request/second, `boardwatch-probe` User-Agent). Only the field *shape* was carried over.

**All text is synthetic.** No real employer name, posting copy, requisition id, URL or
recruiter contact appears in any file here. The employer is the invented "Acme Corp" on the
fictional hosts `careers.acme.test` / `careers-acme.icims.test`. The contract tests never
reach the network; they only read these files.

## Recorded envelope

```
{ "jobs": [ { "data": { ... } } ],
  "locations": [], "totalCount": N, "count": N,
  "request_id", "meta_data", "languageCounts", "filter" }
```

`totalCount` and `count` were equal on every probed response and are the board's own stated
size. `board_reported_total` is read from `totalCount`.

## Recorded per-job `data` fields

`slug`, `language`, `client_code`, `req_id`, `title`, `description` (HTML),
`qualifications` (HTML), `responsibilities` (HTML), `location_name`, `street_address`,
`city`, `state`, `country`, `country_code`, `postal_code`, `location_type`, `categories`,
`department`, `salary_value`, `salary_min_value`, `salary_max_value`, `employment_type`,
`hiring_organization`, `posted_date`, `update_date`, `create_date`, `apply_url`, `internal`,
`external`, `searchable`, `applyable`, `ats_code`.

The live payload additionally carries `category`, `full_location`, `short_location`,
`latitude`, `longitude`, `multipleLocations`, `hiring_flow_name`,
`hiring_organization_logo`, `languages`, `tags1`–`tags4`, `isFrontLineAIJob`,
`li_easy_applyable` and a per-job `meta_data` block. None of them is read by the provider,
so they are deliberately not reproduced here — `raw_json` keeps whatever the live payload
carries.

## Measured pagination contract

- `limit` maximum is **exactly 100**. `limit=101`, `limit=150` and `limit=200` all return
  **HTTP 422** with `{"timestamp", "path", "data": {"error": "An unexpected error occurred"}}`
  — a hard error, **not** a silent clamp.
- `page` is **1-based**. Paging past the last page returns **HTTP 200 with `"jobs": []`** and
  a still-correct `totalCount`; it does not 4xx and it does not wrap to page 1. Termination is
  therefore on a **short page**, with a page-count backstop.

## Measured validators

The listing responses carry a weak **`ETag`** (`W/"..."`) and **no `Last-Modified`**, alongside
`cache-control: no-cache, no-store`. A conditional GET replaying that ETag as `If-None-Match`
returned **HTTP 304** live, so the D22 conditional-fetch path is real for this provider.
`normal_response_headers.json` records a synthetic-shape `etag` and an explicit
`"last_modified": null` to state the absence.

## Recorded dead-board signature

An unrecognized API path answers **HTTP 404** with `content-type: application/json` and the
body `{"error": "Not Supported"}`. `dead_404.json` holds that shape; the contract test serves
it with status 404 → `BoardHealth.DEAD` / `failed`.

## Posting URL: the fallback is the only path measured

The payload's only URL field is `apply_url`, and on **all four probed tenants it pointed at a
different host** (`https://{something}-{tenant}.icims.com/jobs/{req_id}/login`) — never the
careers host. The provider therefore takes `apply_url` only when it is on the board's own host
(a case never observed live, kept because the shape permits it) and otherwise falls back to
`https://{host}/jobs/{req_id}`.

**That fallback is a measured redirector, not a guess.** The canonical on-site path differs per
tenant — `/careers-home/jobs/{req_id}` on one, `/main/jobs/{req_id}` on another, `/jobs/{req_id}`
on a third — and `/jobs/{req_id}` resolved on every one: HTTP 200 where it is canonical, and
HTTP 302 to the tenant's canonical path where it is not.

## Fields measured EMPTY on every probed tenant

These are reproduced with their measured empty values, and the provider must not mine around
them:

- **`department`** was `""` or `null` on 228/228 probed postings. Mapped straight through
  (`None` when blank); `categories` is deliberately **not** used as a substitute.
- **`salary_min_value` / `salary_max_value` / `salary_value`** were `0` or `null` on 228/228.
  **Zero means "not published", not "$0"**, so a non-positive value maps to NULL. One tenant
  carried a display-string pay range in `tags2`/`tags3` (`"INR ₹2,186,520.00/Yr."`); D19 is
  structured-only, so that is never mined.
- **`location_type`** read `"LAT_LNG"` on 228/228. It is a geocoding mode, not a remote signal.
  The remote rule keyed on it is implemented as specified but has **no live evidence**; the
  location-text heuristic is what actually fires.

## Authored (not observed) values, and why

Two values in `normal.json` are authored rather than recorded, so that the mapping paths they
guard are covered by the fixture rather than only by an inline payload:

- `1000001` carries `salary_min_value: 185000` / `salary_max_value: 225000`, and `1000005`
  carries `salary_min_value: 0` / `salary_max_value: 96000` (a one-sided case). The FIELDS and
  their integer type are recorded; the positive values are not. No probed tenant published one.
- `1000004` carries `location_type: "REMOTE"`. The FIELD is recorded; that value is not.

**Currency and period are unknown.** The API states neither anywhere in the payload, so
`salary_currency` and `salary_period` are always NULL even when the scalars are written.

## Files

| File | Purpose |
|---|---|
| `normal.json` | A healthy single-page board: 5 postings, `totalCount: 5`. The fixture contract below. |
| `empty.json` | A live but vacant board: `"jobs": []`, `totalCount: 0` → a *complete, empty* inventory. |
| `dead_404.json` | The recorded dead-path body, served with HTTP 404. |
| `normal_response_headers.json` | The `etag` validator (and the recorded absence of `last_modified`) for the 304 exchange. |

## `normal.json` contract (relied on by `tests/contract/test_jibe.py`)

- **5 postings**, each with `req_id`, `title`, `description`; `body_text` is non-empty and
  HTML-free.
- `jobs[0].data` has a `title` (the partial-parse test deletes it to force a `partial`
  snapshot) and is the row the pagination test clones to build full pages.
- **≥ 1 posting with all three HTML sections** (`description` + `qualifications` +
  `responsibilities`), concatenated in that order.
- **≥ 1 posting with blank `qualifications` and `responsibilities`** → those sections are
  skipped, not rendered as blank lines.
- **≥ 1 posting with a non-empty `location_name`** and **≥ 1 with `location_name: ""`** →
  the second falls back to `city, state, country`.
- **≥ 1 posting whose location text contains "Remote"** → `remote_policy == "remote"`.
- **≥ 1 posting with `location_type: "REMOTE"` and a non-remote location text** → also
  `remote_policy == "remote"` (authored value; see above).
- **≥ 1 posting with positive `salary_min_value` and `salary_max_value`** → both scalars
  mapped, currency and period NULL.
- **≥ 1 one-sided posting** (`salary_min_value: 0`, `salary_max_value: 96000`) → only the
  present side mapped.
- **≥ 1 posting with `salary_min_value: 0` and `salary_max_value: 0`** and **≥ 1 with both
  `null`** → all four scalars NULL.
- **≥ 1 posting with `department: ""` or `null`** → `department is None`.
- Every `apply_url` is on a host OTHER than the board host, so every posting exercises the
  `https://{host}/jobs/{req_id}` fallback.

If any file is missing or the contract is not met, the affected tests must STOP — that is an
attended-session gap, not loop work.

# Workday fixtures

Captured fixtures for the Workday CXS provider contract tests (Task 5 / issue p10-workday).

## Provenance & sanitization (D9 / §6.6 / §0 guardrail 2)

These fixtures mirror the **exact response shape** of Workday's public CXS API — the list
endpoint (`POST https://{host}/wday/cxs/{tenant}/{site}/jobs`) and the per-posting detail
endpoint (`GET https://{host}/wday/cxs/{tenant}/{site}{externalPath}`) — live-verified
against two tenants (NVIDIA, Etsy) during an attended session on **2026-08-04**. The
structure (list envelope `{total, jobPostings[], facets[]}`; per-listed-posting `title`,
`externalPath`, `locationsText`, `postedOn`, `bulletFields`, and the optional `remoteType`;
facet group `{facetParameter, descriptor, values[]}` with bucket keys `descriptor`, `id`,
`count`; detail payload `jobPostingInfo` with `title`, `jobDescription`, `location`,
`startDate`, `timeType`, `externalUrl`, `jobReqId`, `jobPostingId`) mirrors the live API.

The live probe forced four corrections to the assumed shape, all reflected in these
fixtures:

1. There is **no `jobRequisitionId` key**. The requisition identifier and the internal
   posting identifier are two separate keys, `jobReqId` and `jobPostingId`.
2. `remoteType` is a **real structured remote signal** on the listed-posting object (and on
   the detail payload), but it is tenant-dependent: some tenants populate it (Etsy:
   `"Partially Remote"`), some omit the key entirely (NVIDIA). This is the same shape as
   Ashby's `isRemote`, and `remote_policy` prefers it over the location-text heuristic —
   `"Partially Remote"` is the value that exercises the **hybrid** branch, which a
   location-text-only reading of `"Santa Clara, CA"` cannot reach.
3. Requisition tokens embedded in `externalPath` carry a real `-N` instance suffix
   (e.g. `..._JR1000001-1`), not just the bare requisition id.
4. `locationsText` is not always a place name — for postings open at many sites it is a
   count string like `"6 Locations"`.

**All text is synthetic.** No real company copy, names, URLs, recruiter contacts, or other
data was carried over from any recorded board — only the field *shape* was. There are no
email addresses or PII of any kind (CI's gitleaks job and a fixture-time scan both confirm
this). Tenant `acme`, host `acme.wd5.myworkdayjobs.com`, site `AcmeCareers` are invented.
The loop never fetches a live API (§0); it only reads these files.

## Which validators the live API serves: none

Across both probed tenants the CXS list `POST` returns no `ETag` and no `Last-Modified`,
and answers `cache-control: no-store, no-cache`. `normal_response_headers.json` records
this **explicitly** (`{"etag": null, "last_modified": null}`) so the absence reads as
deliberate, not an oversight. Consequently `unchanged` is unreachable against the real
service; the 304 branch is exercised only by a mocked 304 in the provider's tests, never by
a fixture in this directory.

## The three pagination traps

A future reader must not "simplify" the pager. All three of the following were confirmed
live:

1. `limit` has a hard ceiling of exactly **20** — `limit=21` is rejected with HTTP 400.
2. `total` and `facets` are populated **only in the `offset=0` response**; every other page
   reports them as absent-equivalent (`facets: []` and a `total` that must not be
   re-trusted).
3. `total` is capped at **2000** and `offset >= 2000` **wraps back to page 1** rather than
   erroring, so a naive `while offset < total` loop never terminates. The pager must stop
   on a page-count or empty-page condition, not on `total`.

## The dead-board signature

A retired or mistyped site slug answers **HTTP 404** with body `{"errorCode": "S21", ...}`
(`dead_s21.json`). This is distinguishable from a valid but empty board, which answers
**HTTP 200** with `{"total": 0, "jobPostings": [], "facets": []}` (`list_empty.json`).

## Files

| File | Purpose |
|---|---|
| `list_normal.json` | A healthy single-page board: 3 postings, `total: 3`, and a `facets` block. The fixture contract below. |
| `list_page_full.json` | An `offset=0` page with exactly 20 postings (the pager's page limit) and `total: 2000`, `facets: []`, forcing the pager to fetch another page. |
| `list_page_short.json` | A subsequent page with 5 postings, `total: 2000`, `facets: []` — a short page that ends the pager. |
| `list_empty.json` | A live but vacant board: `{"total": 0, "jobPostings": [], "facets": []}` — a *complete, empty* inventory (a 200, not a 304). |
| `list_facet_intern.json` | The `appliedFacets: {"workerSubType": [<intern id>]}` response: `total: 1` with the Compiler Intern row from `list_normal.json`, verbatim, and `facets: []`. |
| `detail_normal.json` | A detail payload for the Senior Platform Engineer posting: full `jobPostingInfo` including `remoteType: "Fully Remote"`, `jobReqId: "JR1000001"` (bare), and `jobPostingId: "JR1000001-1"` (carries the instance suffix). |
| `dead_s21.json` | The wrong-site-slug signature: HTTP 404 with `errorCode: "S21"`. |
| `normal_response_headers.json` | `{"etag": null, "last_modified": null}` — Workday sends **neither** validator on the list endpoint; recorded explicitly so the absence is deliberate, not an oversight. |

The non-JSON maintenance-page case (a live signature seen on another tenant) is
deliberately **not** a fixture file here — it is a literal `b"<html>...</html>"` body
inlined directly in the Task 5 test, which avoids dragging a new, non-`.json` suffix into
the inventory question for no benefit.

## `list_normal.json` contract (relied on by `tests/contract/test_workday.py`)

1. `jobPostings` has 3 rows with unique `externalPath` values; `total == 3`; 3 is fewer
   than the 20-row page limit, so this is a single-page board.
2. Exactly one row's `locationsText` contains `"Remote"` (`Senior Platform Engineer`,
   `"Remote, USA"`) — drives `remote_policy`.
3. `bulletFields` lengths differ across rows (1, 2, and 3) — pins that `bulletFields[0]`
   is **not** a reliable requisition id.
4. Row 1 carries `remoteType: "Fully Remote"`, row 2 carries `remoteType: "Partially
   Remote"` (the value that must resolve to the **hybrid** branch of `remote_policy`, not
   `onsite` — a location-text-only reading of row 2's `"Santa Clara, CA"` would return
   `unknown`), and row 3 has **no `remoteType` key at all** — pinning all three
   `remote_policy` branches, including the fallback for a tenant that omits the field.
5. Row 1's requisition token in `externalPath` carries the real `-N` instance suffix
   (`..._JR1000001-1`), so `_posting_id` yields `JR1000001-1` — the id is derived from
   `externalPath`, not from `bulletFields[0]`, and the two deliberately differ here.
6. Row 3's `locationsText` is the count string `"6 Locations"`, not a place name — pins
   that `locationsText` cannot be trusted as a location unconditionally.
7. The `facets` list contains a `workerSubType` group with exactly one intern-shaped
   bucket (`"Intern (Fixed Term)"`) and one that must not match (`"Regular Employee"`),
   plus a second, non-`workerSubType` group (`locations`) that must be ignored.
8. Every `externalPath`'s last `_`-delimited token contains a digit, so `_posting_id`
   never takes its fallback branch here.

If any file is missing or the contract is not met, this task must STOP — that is an
attended-session gap, not loop work.

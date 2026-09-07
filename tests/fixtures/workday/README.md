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

## Facet slicing, and the extra request it costs

Trap 3 means a board larger than 2,000 postings is enumerated **blind and partially**. Measured
live on 2026-09-07 against five real tenants: one board of 21,190 postings reported
`total: 2000` and yielded 1,998 rows; one of 4,376 reported 2000 and yielded 1,988; one of
12,307 reported its real size and stopped at the provider's 150-page backstop with 3,000.

**The facets are not capped** — `timeType`, `jobFamilyGroup` and `jobFamily` each sum to the
board's true size even when `total` is censored, which is how those numbers were obtained. So a
slug may name **one facet bucket** and fetch that instead of the whole board:

    acme.wd5.myworkdayjobs.com/acme/AcmeCareers#jobFamilyGroup=Technology

Sliced, `total` reads the **bucket's own true size** and the pager enumerates all of it. On the
4,376-posting board, slicing to its 1,074-posting technology bucket enumerated 1,074 distinct
ids in 54 pages, against the 100 pages a blind scan spends to reach roughly half of them.

Two properties of the live API force the design, and both are recorded in
`list_facet_catalog.json`:

1. **The bucket id is an opaque, tenant-specific hash.** One tenant's id for `Technology` is a
   32-character hex string that means nothing on another tenant, and posting an id the tenant
   does not know answers **HTTP 400**. It therefore cannot be hardcoded in a slug or a catalog:
   the provider issues **ONE extra unfiltered POST per sliced board**, reads
   `facets[] -> {facetParameter, values: [{descriptor, id, count}]}`, and resolves
   `descriptor -> id` at fetch time. That request's own `jobPostings` rows are discarded — they
   are the unfiltered board's first page.
2. **A facet group can nest another group inside its `values`.** `locationMainGroup` returns a
   single value that is itself a group (`facetParameter: "locations"`) with the buckets under
   it and no `id`/`count` of its own. A top-level-only read reports `locations` absent.

**Tenants expose different groups.** Three of the five probed boards offer `jobFamilyGroup` and
**no `jobFamily` at all**, which is why the slug fragment names the group as well as the
descriptor. A group or descriptor that is not in the live catalog is a **board-level ERROR with
zero rows** and never an unfiltered fetch — a fallback would restore the blind 2,000-row
listing while the operator believed the board was sliced.

## The dead-board signature

A retired or mistyped site slug answers **HTTP 404** with body `{"errorCode": "S21", ...}`
(`dead_s21.json`). This is distinguishable from a valid but empty board, which answers
**HTTP 200** with `{"total": 0, "jobPostings": [], "facets": []}` (`list_empty.json`).

## Files

| File | Purpose |
|---|---|
| `list_normal.json` | A healthy single-page board: 3 postings, `total: 3`, and a `facets` block. The fixture contract below. |
| `list_page_full.json` | A full page of exactly 20 postings (the pager's page limit) with `total: 2000`, forcing the pager to fetch another page. `facets: []` here — facet shape is pinned separately by `list_normal.json`, so this fixture stays focused on pagination mechanics. |
| `list_page_short.json` | A subsequent page with 5 postings, `total: 2000`, `facets: []` — a short page that ends the pager. |
| `list_empty.json` | A live but vacant board: `{"total": 0, "jobPostings": [], "facets": []}` — a *complete, empty* inventory (a 200, not a 304). |
| `detail_normal.json` | A detail payload for the Senior Platform Engineer posting: full `jobPostingInfo` including `remoteType: "Fully Remote"`, `jobReqId: "JR1000001"` (bare), and `jobPostingId: "JR1000001-1"` (carries the instance suffix). |
| `dead_s21.json` | The wrong-site-slug signature: HTTP 404 with `errorCode: "S21"`. |
| `normal_response_headers.json` | `{"etag": null, "last_modified": null}` — Workday sends **neither** validator on the list endpoint; recorded explicitly so the absence is deliberate, not an oversight. |
| `list_facet_catalog.json` | The **unfiltered** `offset=0` response of a censored board, i.e. the facet catalog a sliced fetch resolves against: `total: 2000` with facets summing to 4589, a `jobFamilyGroup` whose `Technology` bucket counts 25, a `timeType`, and a `locationMainGroup` that **nests** a `locations` group. Its 2 `jobPostings` rows carry ids no sliced fixture uses, so a test can prove they never enter the slice's inventory. The unknown-**descriptor** and unknown-**group** cases are read off this same file rather than getting fixtures of their own: each is an ABSENCE (no `Warehouse Operations` value, no `jobFamily` group at all), and a file whose only content is what it lacks records nothing a reader could check. |
| `list_sliced_page_full.json` | The **sliced** `offset=0` response for that board's `Technology` bucket: `total: 25` — the bucket's TRUE size, **not** the 2000 censor — with a full 20-row page and facets re-aggregated over the slice. |
| `list_sliced_page_short.json` | The slice's `offset=20` page: 5 rows, and `total: 0` / `facets: []` as trap 2 requires of any page past the first. 20 + 5 = 25 = the bucket's count, so the catalog count, the sliced `total` and the enumeration are three independent paths to one number. |
| `list_censored_with_facets.json` | `total: 2000` (the censor value) with three facet dimensions summing to 3000+1589=4589, 4589, and 0 — pins that `_uncapped_total` returns a facet dimension's own sum (4589) rather than the sum of all dimensions (9178) when total is censored. The two non-zero dimensions tie at 4589, so this fixture cannot distinguish "largest" from "first", and dropping the zero dimension does not change the result either way, so it does not exercise the zero-skip (D-271). |

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
7. The `facets` list carries two dimensions of the same 3-posting corpus — `workerSubType`
   summing to 3, `locations` summing to 1 — which is what
   `test_facet_sum_agrees_with_an_uncensored_boards_total` uses as its known-positive
   control (the largest-non-zero-dimension rule against a smaller sibling).
8. Every `externalPath`'s last `_`-delimited token contains a digit, so `_posting_id`
   never takes its fallback branch here.

If any file is missing or the contract is not met, this task must STOP — that is an
attended-session gap, not loop work.

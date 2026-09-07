# Eightfold fixtures

Authored fixtures for the Eightfold PCSX provider contract tests (T67).

## Provenance & sanitization (D9 / §6.6 / §0 guardrail 2)

These fixtures mirror the **exact response shape** of Eightfold's public PCSX API — the
listing endpoint (`GET https://{host}/api/pcsx/search?domain={domain}&start={n}`) and the
per-posting detail endpoint
(`GET https://{host}/api/pcsx/position_details?domain={domain}&position_id={id}`) —
live-verified against four tenants on **2026-09-06** during an attended probe: two on
employer-owned domains, one on a second employer-owned domain, and one on the vendor's own
`*.eightfold.ai`. Both endpoints share the envelope `{status, error, data, metadata}`; the
listing's `data` carries `positions[]`, `count`, `filterDef`, `sortBy`, `appliedFilters`,
`debug`, `savedSearchMetadata`, `resultsMetaData`; a listed position carries `id`,
`displayJobId`, `name`, `locations`, `standardizedLocations`, `postedTs`, `solrScore`,
`stars`, `department`, `creationTs`, `isHot`, `workLocationOption`, `locationFlexibility`,
`atsJobId`, `positionUrl`; the detail payload adds `location`, `publicUrl`, `jobDescription`,
`jdHighlight`, `positionExtraDetails` and `positionUserActions`.

**All text is synthetic.** No real company copy, names, URLs, ids, recruiter contacts, or
other data was carried over from any probed board — only the field *shape* was. Tenant host
`careers.acme.test`, domain `acme.test`, and every title, department, location and posting id
are invented. There are no email addresses or PII of any kind. The tests never fetch a live
API (§0); they only read these files.

The live probe forced five corrections to the assumed shape, all reflected here:

1. **`/api/apply/v2/jobs` is closed.** It answers HTTP 200 with
   `{"message": "Not authorized for PCSX"}` on the vendor-hosted tenants and the SPA's HTML
   shell on the employer-owned ones. `/api/pcsx/search` is the endpoint the shipped client
   bundle calls, and it needs no token, cookie, `Referer` or `X-Requested-With`.
2. **The listing requires a `domain` the host does not carry.** Omitting it is HTTP 422
   (`{"messages": {"domain": ["Missing data for required field."]}}`); a wrong value is a
   200 that returns HTML. It is not derivable from the host — one probed tenant's career host
   and its `domain` share no label at all. Every tenant page states it in a
   `<code id="pcsx-data">` element holding HTML-escaped JSON, which is why a board scan starts
   with an HTML bootstrap. That page is **not** a file here: it is a synthetic literal inlined
   in `tests/contract/test_eightfold.py`, on the same reasoning that keeps Workday's
   maintenance-page body inline — it avoids dragging a non-`.json` suffix into the inventory
   question for no benefit.
3. **The page size is fixed at 10 and `num` is ignored.** `num=50` returned ten rows; the
   client bundle hardcodes `num: 10`. `start` past the end returns an empty `positions` list
   rather than wrapping, so the pager terminates on a short page.
4. **The remote value is `remote_local`, not `"remote"`.** 80 unfiltered rows across three
   tenants gave only `onsite` and `hybrid`; a `location=remote` search returned 34 rows, every
   one `workLocationOption: "remote_local"`. `"remote"` occurs in the client bundle solely as a
   *location* keyword. Guessing the enum's third member would have produced a provider that
   reported zero remote postings on a real board.
5. **A detail 404 is not a close signal.** An unknown `position_id` answers HTTP 404 with
   `{"status": 404, "error": {"message": "Position not found"}, "data": {}}`. Unlike
   SmartRecruiters' `active: false` — an explicit flag inside a 200 — this is
   indistinguishable from an edge blip, so the provider keeps the id in its live inventory.

## Which validators the live API serves: none

Across all four probed tenants the career page and `/api/pcsx/search` both return **no
`ETag`** and **no `Last-Modified`**, and answer
`cache-control: private, max-age=0, no-cache, no-store`.
`normal_response_headers.json` records this **explicitly** (`{"etag": null,
"last_modified": null}`) so the absence reads as deliberate, not an oversight. Consequently
`unchanged` is unreachable against the real service; the 304 branch is exercised only by a
mocked 304 in the provider's tests, never by a fixture here.

## The dead-board signature: there is not one on the API

A mistyped `*.eightfold.ai` subdomain does not resolve at all — the probe got no HTTP
response, not a 404 — so a typo is a **transport** failure (`UNREACHABLE`), not a
distinguishable dead board. On an employer-owned domain a mistyped host is likewise a DNS or
TLS failure. `healthcheck` therefore reports `DEAD` only for a career page that answers 404,
and `EMPTY` for a page that bootstraps and lists nothing (`search_empty.json`).

## Files

| File | Purpose |
|---|---|
| `search_normal.json` | A healthy single-page board: 4 positions, `count: 4`, a `filterDef.facets.locations` block. The fixture contract below. |
| `search_page_full.json` | A full page of exactly 10 positions (the server's fixed page size) with `count: 12`, forcing the pager to fetch another page. |
| `search_page_short.json` | The second page: 2 positions, `count: 12` — a short page that ends the pager. The second row's `id` is `null`, so `board_enumerated` (2 pages, 11 keyable ids) falls short of the stated 12. |
| `search_empty.json` | A live but vacant board: `positions: []`, `count: 0`, empty facets — a *complete, empty* inventory (a 200, not a 304). |
| `detail_normal.json` | The detail payload for `search_normal.json`'s first position: `jobDescription` as HTML, `publicUrl`, the scalar `location`, and `workLocationOption: "remote_local"`. |
| `detail_not_found.json` | The 404 body for an id the listing just returned: `{"status": 404, "error": {"message": "Position not found"}, "data": {}}`. |
| `normal_response_headers.json` | `{"etag": null, "last_modified": null}` — Eightfold sends **neither** validator on either endpoint; recorded explicitly so the absence is deliberate. |

## `search_normal.json` contract (relied on by `tests/contract/test_eightfold.py`)

1. `positions` has 4 rows with unique `id` values; `count == 4`; 4 is fewer than the 10-row
   page size, so this is a single-page board and the pager stops after one request.
2. The four rows carry `workLocationOption` values `remote_local`, `hybrid`, `onsite` and
   `flex_hybrid_v2` — the three catalog members plus one deliberately **out of catalog**,
   which must resolve to `unknown` rather than minting a bucket.
3. Row 1's `locations[0]` is literally `"Remote"`. That is what makes the out-of-catalog row
   meaningful: a location-text fallback would read row 1 correctly for the wrong reason, so
   the provider has none and the *catalog* is what is under test.
4. Row 4's `department` is `null` — `RawPosting.department` must be `None`, never `"None"`.
5. `postedTs` is epoch **seconds** (`1788652800` → 2026-09-06T00:00:00), and `creationTs` is
   always earlier, which is why `updated_at` is `None` rather than being filled from it.
6. `positionUrl` is a site-relative path; the absolute posting URL comes from the detail
   payload's `publicUrl`, and the two are consistent in `detail_normal.json`.

If any file is missing or the contract is not met, this task must STOP — that is an attended-
session gap, not loop work.

# Apple fixtures

Authored fixtures for the jobs.apple.com provider contract tests (T70).

## Provenance & sanitization (D9 / §6.6 / §0 guardrail 2)

These fixtures mirror the **exact response shape** of Apple's public career site —
the listing route (`GET https://jobs.apple.com/en-us/search?location={filter}&page={n}`) and
the per-posting detail route
(`GET https://jobs.apple.com/en-us/details/{positionId}/{transformedPostingTitle}`) —
live-verified on **2026-09-07** during an attended probe.

**All text is synthetic.** No real company copy, posting text, titles, ids, URLs or recruiter
contacts were carried over — only the field *shape* was. The employer is `Acme Corp`, the
country is `Acmeland` (`postLocation-AAA`), every posting id is in a reserved `9000000xx`
range, and every location name (`Springfield`, `Shelbyville`, `Ogdenville`) is invented. There
are no email addresses or PII of any kind. The tests never fetch the live site (§0); they only
read these files.

## There is no JSON API: the payload is a hydration blob

`/api/role/search` and `/api/csrfToken` both **301 to `apple.com/pagenotfound`**, and
`GET /api/v1/search` answers **`401 User Unauthorized`**. What the site ships is a
server-rendered React Router document whose data is inlined as:

```
window.__staticRouterHydrationData = JSON.parse("{\"loaderData\":{...}}");
```

The argument is a **double-encoded** JSON string — a JSON string literal whose contents are
themselves JSON — so it decodes twice. On the live document `JSON.parse(` occurs exactly once
and the terminating `");` exactly once after the marker, which is what makes the provider's
non-greedy capture unambiguous.

**These fixtures store the DECODED blob as `.json`**, and
`tests/contract/test_apple.py::_page` re-encodes it into the recorded HTML document with
`json.dumps(json.dumps(blob))` — genuinely double-encoded, `\"` escaping included. That is
deliberate: `.html` is outside `DATA_SUFFIXES`, so an `.html` fixture would be pinned by
nothing, while a `.json` payload is byte-pinned by R7 *and* the test still exercises the real
two-step decode. The same reasoning keeps Eightfold's bootstrap page and Workday's
maintenance page inline. The **no-hydration** document (a page carrying no blob at all) is an
inline literal in the test file for the same reason.

## The seven corrections the live probe forced

1. **The redirect trap.** A bare `GET /en-us/search` **301s** to
   `/en-us/search?location=united-states-USA` and reports `totalRecords: 4509`. Adding ANY
   query parameter suppresses the redirect: `?page=1` reports **6108** (worldwide). The two
   numbers describe *different boards*, so `board_url()` always carries an explicit
   `location`, and every fetch asserts the effective URL still carries the filter the slug
   asked for. A redirect that changes the filter is an **ERROR**, not a board.
2. **An unknown location code empties the board rather than erroring.** `location=x-ZZZ`
   answers HTTP 200 with `totalRecords: 0` and `searchResults: []`. That is amazon's
   `category[]` failure mode, and an empty *complete* board is the one status that authorizes
   `apply_board` to close every posting it holds — so the slug is a closed catalog.
3. **Only the trailing `-CODE` is read, and the codes are not guessable.** `x-USA`, `-USA` and
   `completelybogusname-USA` all return the same 4,509 as `united-states-USA`, while
   `united-states-usa` returns 0 — the name part is decorative and the code is case-sensitive.
   The codes follow no rule (`JPNC`, `AUSC`, `BRAC` but `IRL`, `SGP`, `USA`; `IRLC` and `USAC`
   are empty), and the namespace is **flat**, mixing country rollups with site codes: `NOR`,
   `FIN`, `GRC`, `HUN`, `LUX` and `ARG` return rows whose `countryName` is the United States,
   and `PRT`, `CHL` and `PHL` return Australian ones. Every catalog entry was therefore
   accepted only after its page-1 rows reported the **expected `countryName`** — nine
   candidates passed a `totalRecords > 0` check and failed that one.
4. **`totalRecords` counts position-LOCATION rows, not postings.** A multi-location
   requisition is served once *per location*, each row carrying a single-entry `locations`
   array. Measured: 160 rows over 8 pages of the US board held **120 distinct `positionId`s**,
   one requisition appearing 4 times. The arithmetic confirms the unit — the worldwide board
   reported 6,108 and paged out as 305 full pages plus a final page of 8. This is why the
   provider reports `board_reported_total = None`: `board_enumerated` is defined repo-wide
   (D-271) as *distinct posting ids*, and a row count in that subtraction would report a
   permanent ~25% shortfall no scan could ever close.
5. **The page size is 20 and is not settable.** `limit`, `pageSize` and `perPage` are all
   ignored (20 rows each). Paging is 1-indexed. Past the last page the server answers HTTP 200
   with `searchResults: []` **and `totalRecords: 0`** — it does not 4xx and does not wrap —
   which is why `totalRecords` is read on the first page only.
6. **An ETag is sent and is useless.** Both routes answer `ETag: W/"..."` with **no**
   `Last-Modified`, under `cache-control: no-store, no-cache, must-revalidate`. A conditional
   GET carrying that exact ETag answered **200, not 304**, so `unchanged` is unreachable
   against the live site; the 304 branch is covered only by a mocked 304.
   `normal_response_headers.json` records the ETag and the explicit `"last_modified": null` so
   the absence reads as deliberate.
7. **A dead detail is a 200, not a 404.** `/en-us/details/000000000/nope` answers HTTP 200
   with a perfectly valid hydration blob whose `loaderData` holds **only `root`** — no
   `jobDetails` key. Like Eightfold's 404 and unlike SmartRecruiters' explicit `active: false`,
   that is indistinguishable from an edge blip, so the id stays in `listed_ids` and the posting
   is simply not materialised.

## Bodies live only on the detail page

The listing's `jobSummary` is a **teaser** — measured over a full page: min 626, mean 668, max
1,055 characters. `body_text` is assembled from the **detail** payload's `jobSummary`,
`description`, `minimumQualifications` and `preferredQualifications`, in that order, blank
sections skipped. A row whose detail was not fetched (budget, failure, or correction 7) is
**not materialised at all**: it stays in `listed_ids` so `apply_board` does not close it, and
it is counted in `detail_deferred`. Because it was never stored it is still absent from
`known_posting_ids` next scan, so the next run fetches its detail — that is how the deferral
drains. This is the D-492 phenom defect, deliberately not reproduced.

## What is deliberately not read

- **Salary.** Neither payload carries any salary field, so all four scalars stay NULL (D19).
- **`postingDate`** (`"Sep 07, 2026"`) is a display string whose month name would be read
  through the process locale; `postDateInGMT` is the ISO field. The two payloads spell it
  differently — the listing with nanosecond precision and a `Z`, the detail with milliseconds
  and an offset — and both parse.
- **Location text as a remote signal.** Measured over ~140 US rows, no location `name`
  contained "remote" or "home" even once, so a text rule could never fire on any Apple board —
  a monitoring failure, not conservatism. `homeOffice` is the only signal, and a *false* value
  is `unknown` rather than `onsite` because it is the feed's default for anything unstated.
  `homeOffice: true` rows still carry physical city locations, which is why the flag and not
  the text is what distinguishes them.
- **`team=` as a board axis.** `team=APPST` returns the full unfiltered 6,108 — the facet is
  silently ignored, amazon's "silent widen" failure mode. `location` is the only honoured axis.
- **`loaderData.search.filters`.** It is `{}` on every probed page, so the facet catalog is
  **not** discoverable from the payload; the location catalog was measured token by token.

## Files

| File | Purpose |
|---|---|
| `search_normal.json` | A healthy single-page board: **4 rows holding 3 distinct postings** (rows 2 and 3 are one multi-location requisition), `totalRecords: 4`. The fixture contract below. |
| `search_page_full.json` | A full page of exactly 20 rows (the server's fixed page size) with `totalRecords: 22`, forcing the pager to fetch another page. |
| `search_page_short.json` | Page 2: 2 rows, `totalRecords: 22` — a short page that ends the pager. |
| `search_empty.json` | A live but vacant board: `searchResults: []`, `totalRecords: 0` — a *complete, empty* inventory (a 200, not a 304). |
| `search_idless.json` | 3 rows, the middle one carrying `positionId: null` — a row that cannot be keyed, fetched, deduped or closed. |
| `detail_normal.json` | The detail payload for `search_normal.json`'s multi-location posting, carrying **both** its locations with the richer detail-side fields, `teamNames` as a two-entry list, and `homeOffice: true`. |
| `detail_missing.json` | Correction 7: a 200 whose `loaderData` holds only `root` and no `jobDetails`. |
| `normal_response_headers.json` | The ETag the live host sends, plus `"last_modified": null` — recorded explicitly so the absence is deliberate. |

## `search_normal.json` contract (relied on by `tests/contract/test_apple.py`)

1. 4 rows, `totalRecords == 4` — the count is of ROWS, and 4 is fewer than the 20-row page
   size, so this is a single-page board and the pager stops after one request.
2. Rows 2 and 3 share `positionId: "900000002"` and differ only in `locations`, so the board
   lists **4 rows / 3 distinct postings**. `board_enumerated` must be **3**, and exactly **3**
   detail requests must be made — not 4.
3. The two location dicts on those rows carry **`postLocationId`**, which is what a *listing*
   row spells it; the detail payload spells the same field **`id`**. Reading only one of the
   two collapses every row of a multi-location requisition onto a single key, and the walk
   then reports a spurious shortfall and downgrades a healthy board to `partial`. This is a
   real defect the contract tests caught during T70.
4. Row 1's `jobSummary` is a long teaser containing the sentinel sentence
   `This teaser is truncated by the listing endpoint.`, which must appear **nowhere** in any
   `body_text`.
5. Row 4 carries a country-level location (`level: 1`) and a `RETAIL` `jobType`, so the
   country-only location path is exercised alongside the city one.
6. `postDateInGMT` on rows 1–3 is the listing's nanosecond `Z` form
   (`2026-09-07T05:22:08.324174937Z`); `detail_normal.json`'s is the detail's millisecond
   offset form (`2026-09-07T12:42:42.277+00:00`). Both must parse, and `postingDate` must never
   be read.

If any file is missing or the contract is not met, this task must STOP — that is an attended-
session gap, not loop work.

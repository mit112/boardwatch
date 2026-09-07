# Oracle HCM (Oracle Recruiting Cloud) fixtures

Captured fixtures for the `oraclehcm` provider contract tests (ticket T65).

## Provenance & sanitization (D9 / §6.6 / §0 guardrail 2)

These fixtures mirror the **exact response shape** of Oracle Recruiting Cloud's public
Candidate Experience REST API — the list endpoint

```
GET https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions
    ?onlyData=true&expand=requisitionList.secondaryLocations
    &finder=findReqs;siteNumber={site},limit=200,offset={n},sortBy=POSTING_DATES_DESC
```

and the per-posting detail endpoint

```
GET https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails
    ?expand=all&onlyData=true&finder=ById;Id={id},siteNumber={site}
```

— live-verified against three tenants during an attended session on **2026-09-06**. The
structure (list envelope `{items: [ {...search echo..., TotalJobsCount, SiteNumber,
requisitionList[]} ], count, hasMore, limit, offset, links}`; per-listed-requisition `Id`,
`Title`, `PostedDate`, `PrimaryLocation`, `PrimaryLocationCountry`, `ShortDescriptionStr`,
`WorkplaceType`, `WorkplaceTypeCode`, `Department`, `JobFamily`, `secondaryLocations[]` with
`RequisitionLocationId` / `GeographyId` / `Name` / `CountryCode` / `Latitude` / `Longitude`;
detail envelope `{items: [ {...} ], count, hasMore, limit, offset, links}` adding
`ExternalDescriptionStr`, `ExternalQualificationsStr`, `ExternalResponsibilitiesStr`,
`CorporateDescriptionStr`, `OrganizationDescriptionStr`, `ExternalPostedStartDate`,
`ContentLocale`, `requisitionFlexFields[]`, `primaryLocationCoordinates[]`, `media[]`,
`skills[]`) mirrors the live API. `Department` is on **both** payloads and is what
`RawPosting.department` reads; `JobFamily` is on the **listed row only** (the detail payload
carries `JobFamilyId` instead), so it is the fallback and never the detail-side read.

**All text is synthetic.** No real company copy, names, URLs, requisition ids, recruiter
contacts, or other data was carried over from any recorded board — only the field *shape*
was. There are no email addresses or PII of any kind. Host `acme.fa.us2.oraclecloud.com`,
site `CX_1` and every id, title and location are invented. The loop never fetches a live API
(§0); it only reads these files.

## The detail finder: what the endpoint actually accepts

Three finder spellings were tried against the live detail resource and **all three were
rejected**:

| Attempt | Response |
|---|---|
| `finder=ByRequisitionId;requisitionId={id},siteNumber={site}` | HTTP 400 `URL request parameter finder with value ... is not valid.` |
| `finder=ByRequisitionId;requisitionId={id}` | HTTP 400, same message |
| `finder=ByRequisitionId;requisitionId={id}` + `siteNumber={site}` as its own query parameter | HTTP 400 `URL request parameter siteNumber cannot be used in this context.` |

The resource's own metadata (`GET .../recruitingCEJobRequisitionDetails/describe`) names the
finders it really has: **`ById`**, `ByIdNoCache` and `PrimaryKey`. `ById` declares exactly two
attributes, `Id` and `siteNumber`. So the working call is
`finder=ById;Id={id},siteNumber={site}` — there is no `ByRequisitionId` finder and no
`requisitionId` attribute anywhere on the resource. `/describe` is the cheapest way to settle
this again if the API moves.

## Five traps, all confirmed live

A future reader must not "simplify" the pager or the healthcheck.

1. **`expand` is load-bearing, not an optimisation.** Without
   `expand=requisitionList.secondaryLocations` the list answers HTTP 200 with a populated
   `TotalJobsCount` and **no `requisitionList` key at all** (measured: total 2273, zero rows).
   A pager that dropped `expand` would report a 2,273-posting board it enumerated 0 of, on a
   200, indefinitely. `list_no_expand.json` pins this shape.
2. **`limit` maxes out at exactly 200, silently, and the echo lies.** `limit=201`, `limit=300`
   and `limit=500` each returned exactly 200 rows while `items[0].Limit` echoed back the
   number *asked for*. The response cannot be trusted to report its own page size, so
   termination is on a **short page**, never on the echoed limit.
3. **`TotalJobsCount` is only meaningful at `offset=0`.** An out-of-range offset answers 200
   with `TotalJobsCount: 0` and no rows (measured at `offset=99000` against a 2,273-posting
   board). Read at any other offset it reports a live board as empty. It is captured once, on
   the first page. `list_page_short.json` carries `TotalJobsCount: 0` for exactly this reason
   — that is the honest value at a non-zero offset, not a mistake.
4. **An unknown `siteNumber` silently serves the host's default board.** This is worse than
   SmartRecruiters' unknown-org case. `siteNumber=CX_999` and `siteNumber=ZZnotasite` each
   returned the first tenant's real board (`TotalJobsCount` 2273, identical leading ids to
   `CX_1`), and on a second tenant both returned *its* default board (1322, identical leading
   ids to `CampusHiring`) — while echoing the bogus site straight back in `SiteNumber`, so
   even the echo cannot detect the typo. A mistyped site is therefore indistinguishable not
   just from an empty board but from a **real and different** one. `healthcheck` can only ever
   return OK / EMPTY / ERROR / UNREACHABLE, and there is no dead-board fixture in this
   directory because **there is no dead-board signature to record.**
5. **The detail endpoint has no 404.** An unknown or withdrawn requisition answers HTTP 200
   with `items: []`, `count: 0` (measured with `Id=99999999`). `detail_gone.json` pins it. The
   provider reads that as "no longer listable" and drops the posting from both `postings` and
   `listed_ids`, the disposition SmartRecruiters gives `active: false`.

## Which validators the live API serves: none

The list endpoint returns no `ETag` and no `Last-Modified`, and answers
`Cache-Control: no-cache, no-store, must-revalidate`. `normal_response_headers.json` records
this **explicitly** (`{"etag": null, "last_modified": null}`) so the absence reads as
deliberate, not an oversight. Consequently `unchanged` is unreachable against the real
service; the 304 branch is exercised only by a mocked 304 in the provider's tests, never by a
fixture in this directory.

## A known limit of the public URL shape

The public posting URL is `https://{host}/hcmUI/CandidateExperience/en/sites/{site}/job/{id}`
and the provider constructs it from the stored slug. Live, a request for that URL **302s to
whichever site the tenant has designated for public browsing** — `.../sites/CX_1/job/{id}`
redirected to `.../sites/jobsearch/job/{id}`. So a URL a user copies out of a browser may name
a different `siteNumber` than the one whose API serves the board, and `slug_from_path` will
recover the site that is in the pasted path. Both sites answer with the same inventory (trap 4),
so this costs correctness nothing today; it is recorded because it means a pasted URL and the
constructed URL can legitimately disagree on the site segment.

## Files

| File | Purpose |
|---|---|
| `list_normal.json` | A healthy single-page board: 3 requisitions, `TotalJobsCount: 3`. The fixture contract below. |
| `list_empty.json` | A live but vacant board: `requisitionList: []` with `TotalJobsCount: 0` — a *complete, empty* inventory (a 200, not a 304). |
| `list_no_expand.json` | Trap 1: `TotalJobsCount: 2273` with **no `requisitionList` key**. Must be read as a failure, never as an empty board. |
| `list_page_full.json` | A full page of exactly 200 requisitions (the server's page ceiling) with `TotalJobsCount: 202`, forcing the pager to fetch another page. |
| `list_page_short.json` | The second page: 2 requisitions at `Offset: 200`, and `TotalJobsCount: 0` — the honest value at a non-zero offset (trap 3). A short page ends the pager. |
| `detail_normal.json` | A detail payload for requisition `1001`: all three `External*Str` sections populated, plus `CorporateDescriptionStr` (which must be **excluded** from `body_text`), `ExternalPostedStartDate`, `WorkplaceTypeCode: "ORA_REMOTE"` and one secondary location. |
| `detail_empty_sections.json` | Requisition `1003` with all three `External*Str` values `""` and `WorkplaceTypeCode: null` / `WorkplaceType: ""`. Must yield `body_text == ""` and `remote_policy == "unknown"`, not an error. |
| `detail_gone.json` | Trap 5: `{"items": [], "count": 0, ...}` — a withdrawn or unknown requisition. |
| `normal_response_headers.json` | `{"etag": null, "last_modified": null}` — Oracle sends **neither** validator; recorded explicitly so the absence is deliberate. |

## `list_normal.json` contract (relied on by `tests/contract/test_oraclehcm.py`)

1. `items` has exactly one search envelope; `requisitionList` has 3 rows with unique `Id`s
   (`1001`, `1002`, `1003`); `TotalJobsCount == 3`; 3 is fewer than the 200-row page limit, so
   this is a single-page board.
2. Row `1001` carries `WorkplaceTypeCode: "ORA_REMOTE"` **and** `WorkplaceType: "Remote"` —
   the code is the field `remote_policy` must read.
3. Row `1002` carries `WorkplaceTypeCode: null` with `WorkplaceType: "Hybrid"` — the
   label-only fallback, and the value that must resolve to the **hybrid** branch. A tenant
   that populates only the localized label is real; this row is why the fallback exists.
4. Row `1003` carries `WorkplaceTypeCode: null` **and** `WorkplaceType: ""` — present-but-empty
   rather than absent, which is how a posting with no workplace type actually arrives. A
   `.get(key, default)` presence check would not see it, because the key *is* there.
5. Row `1001` has one secondary location naming a **different** place from its
   `PrimaryLocation`; row `1003` has two, the first of which **duplicates** its
   `PrimaryLocation` — pinning that `_locations` concatenates primary + secondaries and dedupes
   in order rather than emitting the same place twice.
6. Row `1002` has `secondaryLocations: []` — the common case, one location only.
7. Every row's `ExternalQualificationsStr` and `ExternalResponsibilitiesStr` are `null` on the
   **list** endpoint even though the keys exist, which is why a body needs the detail fetch and
   `ShortDescriptionStr` is not used as one.

If any file is missing or the contract is not met, this task must STOP — that is an
attended-session gap, not loop work.

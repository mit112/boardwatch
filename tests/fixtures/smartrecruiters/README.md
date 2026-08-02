# SmartRecruiters fixtures

Captured fixtures for the SmartRecruiters provider contract tests (Task 5 / issue p4a-providers).

## Provenance & sanitization (D9 / §6.6 / §0 guardrail 2)

These fixtures mirror the **exact response shape** of the SmartRecruiters public postings
API — the list endpoint (`GET https://api.smartrecruiters.com/v1/companies/<slug>/postings
?limit=100&offset=0`) and the per-posting detail endpoint (`GET .../postings/{id}`) —
live-verified during an attended session on **2026-08-01**. The structure (list envelope
`{offset, limit, totalFound, content[]}`; per-listed-posting `id`, `name`, `uuid`, `company`,
`releasedDate`, `location` (`city`/`region`/`country`/`remote`/`hybrid`/`fullLocation`),
`department`, `typeOfEmployment`, `experienceLevel`; detail payload adding `active`,
`postingUrl`, `applyUrl`, and `jobAd.sections` with `companyDescription` / `jobDescription`
/ `qualifications` / `additionalInformation`) mirrors the live API.

**All text is synthetic.** No real company copy, names, URLs, recruiter contacts, or other
data was carried over from any recorded board — only the field *shape* was. There are no
email addresses or PII of any kind (CI's gitleaks job and a fixture-time scan both confirm
this). `company.identifier` is the invented `acme`; `postingUrl`/`applyUrl` values point at
a fictional `acme` board. The loop never fetches a live API (§0); it only reads these files.

## Files

| File | Purpose |
|---|---|
| `list_normal.json` | A healthy paginated list: 3 postings. The fixture contract below. |
| `list_empty.json` | A live but vacant board: `{"totalFound": 0, "content": []}` — a *complete, empty* inventory (a 200, not a 304). Also stands in for an unknown org: SmartRecruiters returns this SAME shape for a typo'd slug (DEAD is unreachable for this provider). |
| `detail_normal.json` | A detail payload for posting `744000000000001`: `active: true`, a `postingUrl`, and non-empty `jobAd.sections` (all four keys, including `companyDescription`, which must be excluded from `body_text`). |
| `detail_inactive.json` | Same shape as `detail_normal.json` with `"active": false` — the posting must be dropped from `snapshot.postings` and from `snapshot.listed_ids`. |
| `detail_empty_sections.json` | `"active": true` with all four section `text` values `""` — the observed live case (Visa) where an active posting carries no body. Must yield `body_text == ""`, not an error. |
| `normal_response_headers.json` | `{"etag": "W/\"abc123\"", "last_modified": null}` — SmartRecruiters sends a weak `ETag` on both list and detail responses; recorded explicitly so the value is deliberate, not an oversight. |

## `list_normal.json` contract (relied on by `tests/contract/test_smartrecruiters.py`)

1. `content` has ≥3 postings with unique `id`s; `totalFound` equals `len(content)`.
2. ≥1 posting with `location.remote: true` (`744000000000002`), ≥1 with
   `location.hybrid: true` (`744000000000001`), ≥1 with neither (`744000000000003`).
3. ≥1 posting whose `location` has no `fullLocation` (`744000000000003`) — exercises the
   city/region/country fallback in `_locations`.

If any file is missing or the contract is not met, this task must STOP — that is an
attended-session gap, not loop work.

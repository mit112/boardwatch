# Phenom fixtures

Captured fixtures for the Phenom People provider contract tests (T66).

## Provenance & sanitization (D9 / §6.6 / §0 guardrail 2)

These fixtures mirror the **exact response shape** of a Phenom People career site's single
widget endpoint — `POST https://{host}/widgets` — live-verified during an attended session on
**2026-09-06** against three employer-hosted sites. The envelope, the row fields and the detail
widget were byte-shape identical on all three; only the request body's `country` and `lang`
differed, which is why they are part of the composite slug `{host}/{country}/{lang}`.

The **list** body that answered (`ddoKey: "refineSearch"`):

```json
{"lang":"en_global","deviceType":"desktop","country":"global","pageName":"search-results",
 "ddoKey":"refineSearch","sortBy":"","subsearch":"","from":0,"jobs":true,"counts":true,
 "all_fields":["category","country","state","city"],"size":10,"clearAll":false,
 "jdsource":"facets","isSliderEnable":false,"pageId":"page12","siteType":"external",
 "keywords":"","global":true,"selected_fields":{},"locationData":{}}
```

It answers `{"refineSearch":{"status":200,"hits":N,"totalHits":T,"data":{"jobs":[...]}}}`.
`size` clamps server-side at **500** (`size=1000` returns 500 rows, it is not an error);
pagination is `from`/`size` and a `from` past the end returns an **empty** `jobs` list rather
than wrapping.

The **detail** body that answered is the same URL with `"pageName":"job-details"`,
`"ddoKey":"jobDetail"` (**singular** — `jobDetails` answers `{"status":"failure"}`, the shape in
`widget_failure.json`) and `"jobId"`, plus the same `lang`/`country`. It answers
`{"jobDetail":{"status":200,...,"data":{"job":{...}}}}` whose `description` is HTML.

The endpoint sends **no `ETag` and no `Last-Modified`** and answers
`cache-control: no-cache, no-store, must-revalidate` (recorded in
`normal_response_headers.json`), so the provider never sends validators and `unchanged` is
unreachable. `applyUrl` points at the *underlying* ATS on two of the three measured sites and is
empty on the third, so a posting URL is normally built as
`https://{host}/{country}/{lang_short}/job/{jobId}` — `lang_short` being `lang` up to the first
underscore, because `.../global/en_global/job/{id}` redirects to the board root while
`.../global/en/job/{id}` serves the posting (all three verified 200 with the posting's title).

**All text is synthetic.** No real company copy, names, URLs, requisition ids, recruiter contacts
or other data was carried over from any recorded board — only the field *shape* was. There are no
email addresses or PII of any kind. The host is the invented `jobs.acme.test`, the country/lang
pair is `global`/`en_global`, and the foreign apply host is `ats.example.test`. The loop never
fetches a live API (§0); it only reads these files.

## Files

| File | Purpose |
|---|---|
| `list_normal.json` | A healthy list widget: 3 postings. The fixture contract below. |
| `list_empty.json` | A live site with no matching postings: `totalHits: 0`, `jobs: []` — a *complete, empty* inventory. DEAD is only reachable here through a transport or HTTP failure on the employer's own host. |
| `detail_normal.json` | A `jobDetail` payload for `100001BR`: HTML `description`, and the same structured fields the list row carries. |
| `widget_failure.json` | `{"status": "failure"}` — the whole-response refusal a wrong `ddoKey` gets. No widget envelope at all, so both the list and the detail paths must treat it as unusable rather than raising. |
| `normal_response_headers.json` | The recorded cache headers: `etag` and `last_modified` are **null**, which is why `fetch_board` ignores `request.validators`. Recorded explicitly so the absence is deliberate, not an oversight. |

## `list_normal.json` contract (relied on by `tests/contract/test_phenom.py`)

1. `data.jobs` has 3 postings with unique `jobId`s; `totalHits` equals their count.
2. Exactly one posting has `city: "Remote"` (`100002BR`) — the only remote signal the payload
   carries. The other two must yield `remote_policy == "unknown"`, never `onsite`.
3. The three `applyUrl` values cover all three measured cases: a **foreign** host
   (`100001BR`, → the constructed fallback URL), **empty** (`100002BR`, → the fallback), and the
   board's **own** host (`100003BR`, → used verbatim).
4. `100003BR` has an empty `cityStateCountry` and an empty `state`, exercising the
   city/state/country join in `_locations`, and an empty `category`, which must yield
   `department is None` rather than `""`.
5. Every posting carries a non-empty `descriptionTeaser`: it is the body the provider falls back
   to when a detail fetch fails.

If any file is missing or the contract is not met, this task must STOP — that is an attended-
session gap, not loop work.

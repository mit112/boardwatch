# Amazon fixtures

Authored fixtures for the `amazon` provider contract tests (T69). The provider reads one
public endpoint and nothing else:

```
GET https://www.amazon.jobs/en/search.json?offset={n}&result_limit={k}&sort=recent&category[]={category}
```

Unauthenticated — no cookie, no token, no `Referer`.

## Provenance & sanitization (D9 / §6.6 / §0 guardrail 2)

These files use the **exact response shape** of that endpoint, recorded during an attended,
read-only session on **2026-09-07** (rate-limited to 1 request/second, `boardwatch-probe`
User-Agent). Only the *shape* was carried over.

**All posting text is synthetic.** No real posting copy, requisition id, posting URL or
recruiter contact appears here. The employer is the invented "Acme Corp" on the fictional host
`careers.acme.test`; posting ids are `9000001`–`9000005`.

**Two things are deliberately real, and both have to be.** (1) The API host
`www.amazon.jobs`, because the provider's identity *is* that host. (2) The 38 category names
and their counts in `facets_category.json`, because that file exists to pin the provider's
closed slug catalog against the live facet vocabulary — a synthetic taxonomy would pin nothing.
Neither is posting content, an employer name we recorded, or a person.

The contract tests never reach the network; they only read these files.

## Recorded envelope

```
{ "error": null, "hits": N, "facets": {},
  "content": {"sidebar": {}, "search_results": {}},
  "jobs": [ { ... } ],
  "job_posting_search_request": "<the request, echoed back as a JSON STRING>" }
```

`hits` is the board's own stated size and `board_reported_total` is read from it — subject to
the cap below. `facets` is `{}` unless `facets[]` was requested. `content` was
`{"sidebar": {}, "search_results": {}}` on every probed response.

## Recorded per-job fields

`id`, `id_icims`, `title`, `job_path`, `description`, `basic_qualifications`,
`preferred_qualifications`, `description_short`, `city`, `state`, `country_code`, `location`,
`locations`, `normalized_location`, `posted_date`, `updated_time`, `job_category`, `job_family`,
`job_schedule_type`, `team`, `company_name`, `business_category`, `is_intern`, `is_manager`,
`university_job`, `source_system`, `url_next_step`, `department_cost_center`, `display_distance`,
`job_function_id`, `optional_search_labels`, `primary_search_label`.

All 32 are reproduced. `raw_json` keeps whatever the live payload carries.

## No detail endpoint, and none is needed

`description`, `basic_qualifications` and `preferred_qualifications` are full HTML-ish text
(`<br/>` separators) **on the listing row** — non-empty on 2,597 of 2,597 probed Software
Development rows. This provider therefore defines no `_detail_url`, its `detail_deferred` is
**always 0**, and `detail_fetch_budget` never applies to it. The whole 2,597-posting Software
Development category cost **26 requests** end to end.

## Five measured hard limits, every one of them an HTTP 200

The status code is never the failure signal here; the `error` field is.

| Probe | Answer |
|---|---|
| `result_limit=500` | `{"error": "Result limit cannot be greater than 100", "hits": 0, "jobs": null}` — **not clamped**, so the page size is pinned at 100 |
| `offset=10000` | `{"error": "Cannot return more than 10000 results at once", ...}` — one query can never enumerate more than 10,000 rows |
| unfiltered `hits` | exactly `10000`, while the category facet summed **22,282**. `hits` is **capped**, not reported |
| `category[]=Totally Made Up` | `{"error": null, "hits": 0, "jobs": []}` — **a silent lie**, not an error |
| bogus `job_function_id[]` | `hits: 10000`, i.e. silently unfiltered |
| `category[]=Software Development` | `hits: 2597` — the facet *is* honoured |

**On the two error bodies `jobs` is `null`, not `[]`.** That is why the provider reads `error`
before `jobs`: the other order reports "invalid payload" and discards the server's own sentence.

## The closed catalog is the only defence, and it cannot be made self-checking

An unknown category and a genuinely vacant one are **indistinguishable**: both answer
`hits: 0`, `jobs: []`, `error: null`, and with `facets[]=category` both answer
`category_facet: []`. There is no second path that separates them, so a stale catalog entry
would present as a board that is merely empty today — and one `complete` empty inventory is the
single status that authorizes `apply_board` to close every posting the real board holds.

What exists instead: `_CATEGORIES` is closed and versioned, `normalize_slug` raises on anything
outside it, `facets_category.json` pins it against the capture, and R15's review deadline is
what forces the live facet list to be re-read on schedule.

## `board_reported_total` at the cap

`hits >= 10000` is the board refusing to state its size, so the provider persists
`board_reported_total = NULL` **beside** `board_total_censored = 1` rather than persisting
10000 as a count — `providers/workday.py:_uncapped_total` makes the same call for the same
reason. Unlike Workday there is no uncapped second path to recover a real number from:
`facets[]=category` on a category-filtered query just echoes `hits` back (measured 19/19).

**In practice this cannot fire for a catalog slug.** The largest live category held 3,370
postings and every one of the 38 is under the ceiling, which is precisely what makes
category-per-board a correct enumeration strategy rather than a convenience — the unfiltered
query provably cannot enumerate the corpus, and a category always can.

## Measured pagination contract

- `result_limit` is **pinned at 100** (see above). `offset` steps by 100 and is 0-based.
- Termination is on a **SHORT PAGE**, counted off the raw `jobs` array. Software Development
  walked offsets 0…2500 and ended on a 97-row page; past the end of a category the API answers
  200 with `"jobs": []`, `error: null` and a still-correct `hits`.
- `_MAX_PAGES = 100` is a backstop that **is also the server's own offset ceiling**
  (100 × 100 = 10,000), so raising it walks into the ceiling refusal rather than reading more.
- **`sort=recent` is not a stable snapshot.** It orders by created date descending, so a posting
  landing mid-walk shifts every later page by one and a row can be served twice. Rows are
  deduped by `id_icims` across pages.

## Measured validators

Listing responses carry a **weak `ETag`** (`W/"..."`) and **no `Last-Modified`**, with
`cache-control: max-age=0, private, must-revalidate`. Replaying that ETag as `If-None-Match`
returned **HTTP 304** live, so the D22 conditional-fetch path is real here.
`normal_response_headers.json` records a synthetic-shape `etag` and an explicit
`"last_modified": null` to state the absence.

## Recorded dead-board signature — and why there is no `dead.json`

An unrecognized path answers **HTTP 404** with `Content-Type: text/html` and a **zero-byte
body** (`/en/nope.json` and `/en/searchx.json` both). There is no body to record, so the dead
case is exercised inline in the contract test rather than from a file.

## The three field traps

- **`id` is a UUID; `id_icims` is the posting id.** `id` reads
  `88d3dd17-...`; the number in the posting URL is `id_icims`, and `job_path` is
  `/en/jobs/{id_icims}/{title-slug}`. Measured over a full category: `id_icims` present and
  **distinct on 2,597 of 2,597** rows, and equal to the `job_path` id segment on all 2,597.
  `job_path` was present and that one shape on all 2,597.
- **`posted_date` is a human string with an optional DOUBLE SPACE**: `"September  4, 2026"`
  (819 of 2,597) and `"October 12, 2026"` both occur. Parsed against a pinned month table
  rather than `%B`, because `strptime` reads `%B` through the process locale and a non-English
  `LC_TIME` would silently NULL every `posted_at`. A value that will not parse keeps
  `posted_at = NULL`; it does not fail the row.
- **`updated_time` is RELATIVE** (`"2 days"`, `"10 months"`, `"about 1 hour"`) and is not a
  timestamp. `updated_at` is therefore **always NULL** and the value stays in `raw_json` only.

## No salary fields exist (D19)

The payload carries no pay key of any kind — checked over all 2,597 Software Development rows
and 770 more across three other categories. All four salary scalars keep their NULL defaults.
There is no display string to mine either, so D19's structured-only rule costs nothing here.

## `remote_policy`: the structured signal is the one that fires

Measured 2026-09-07 over 770 rows / 1,456 locations across four categories:

- the location **TEXT** (`normalized_location`) said "remote" or "virtual" **0 times**;
- each `locations` entry is a **JSON-encoded string** carrying an explicit `"type"`, which read
  `ONSITE` 1,432 times and **`VIRTUAL` 24 times**.

So the provider reads `locations[].type == "VIRTUAL"` first and the location text second. **This
is a departure from the T69 ticket**, which said Amazon has no explicit remote flag and that the
text should decide; a text-only rule provably never fires on any Amazon board.

`ONSITE` is deliberately **not** mapped to `onsite`. The type is per location and one posting
carried up to ten of them, so a row is only unambiguously onsite when every location says so —
and asserting `onsite` for ~98% of the corpus off a value that is also the feed's default for
anything unstated is a claim no probe here can separate from "not set". `hybrid` has no signal.

## `department` is `job_family`, not `job_category`

`job_category` is the search facet the board *is*, so it is a constant per board and carries
nothing. Measured over 370 rows in two categories: `job_family` held **33 distinct values** and
equalled `job_category` **0 times**.

## Locations

`normalized_location` ("Seattle, Washington, USA") was non-empty on **770 of 770** probed rows,
so the `city, state, country_code` fallback is the unmeasured path and is kept only because the
shape permits it. `state` was blank on 115 of those 770, which is why the parts are filtered
rather than joined blindly. The `locations` array is not read for location TEXT — its entries
are JSON-encoded strings, and one posting carried ten.

## Files

| File | Purpose |
|---|---|
| `normal.json` | A healthy single-page board: 5 postings, `hits: 5`. The fixture contract below. |
| `empty.json` | A live but vacant category: `"jobs": []`, `hits: 0`, `error: null` → a *complete, empty* inventory. |
| `error_result_limit.json` | The `result_limit > 100` refusal: HTTP 200, `error` set, `jobs: null`. |
| `error_offset_ceiling.json` | The `offset >= 10000` refusal, same shape. Served on a LATER page, it must be a `partial`. |
| `facets_category.json` | The `facets[]=category` capture: 38 single-key dicts, sum 22,282, max 3,370, alongside the capped `hits: 10000`. Pins `_CATEGORIES`. |
| `normal_response_headers.json` | The `etag` validator (and the recorded absence of `last_modified`) for the 304 exchange. |

There is deliberately **no `dead.json`** — see the dead-board signature above.

## `normal.json` contract (relied on by `tests/contract/test_amazon.py`)

- **5 postings** `9000001`–`9000005`, each with `id_icims`, a UUID `id` that differs from it,
  `title`, `job_path` of the form `/en/jobs/{id_icims}/{title-slug}`, and a non-empty,
  HTML-free `body_text`.
- `jobs[0]` has a `title` (the partial-parse test deletes it) and is the row the pagination
  tests clone to build full pages.
- **`9000001`**: all three HTML sections, concatenated description → basic → preferred;
  `normalized_location` set; `locations[].type == "ONSITE"`; `posted_date` with the **double
  space**; `job_family` set.
- **`9000002`**: blank `basic_qualifications` and `preferred_qualifications` → those sections
  are skipped, not rendered as blank lines; blank `job_family` → `department is None`;
  `posted_date` with a **single** space.
- **`9000003`**: `normalized_location: ""` → falls back to `city, state, country_code`.
- **`9000004`**: `locations[].type == "VIRTUAL"` with non-remote location text →
  `remote_policy == "remote"` through the structured path.
- **`9000005`**: two locations, both `ONSITE`, with `"Remote - ..."` in the location text →
  `remote_policy == "remote"` through the text path; and an **unparseable `posted_date`** →
  `posted_at is None` while the row survives.
- No posting carries any salary field, because the live payload has none.

If any file is missing or the contract is not met, the affected tests must STOP — that is an
attended-session gap, not loop work.

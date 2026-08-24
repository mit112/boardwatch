# Company-discovery contract: the GitHub new-grad lists — pinned against the live files

**2026-08-24. Read-only. Four unauthenticated `GET`s against `raw.githubusercontent.com`, no token, no
key, no impersonation, no TLS bypass.** Every number below was produced this session, twice, by two
independent readers: a stdlib-only transcription that knows nothing about boardwatch, and a second pass
that ran boardwatch's own `core.board_urls.parse_board_target` over the same bytes. Where they are quoted
together it is because they agree.

## 1. What this source is, and what it is not

**It is company discovery. It is not a posting source.** No field in any of the 34,958 records carries a
job description, and none carries anything a body could be extracted from. That is D-291's deciding
measurement and this probe re-confirms it: the full key set is 12-15 fields, all scalar or short list,
listed in §3.

Two independent reasons the boards — not the postings — are the deliverable:

1. No body. A lane with no JD body yields zero leads, because the eligibility engine is body-only.
2. `lanes.dereference.parse_posting_target` covers greenhouse / lever / ashby / workable only, so a
   *posting* identity cannot be recovered for the workday and smartrecruiters records, which are 1,136
   of the 1,991 in-scope provider records. `parse_board_target` covers all six.

So this reads each record's `url`, keeps the `(provider, slug)` **board** it names, and throws the
posting away.

## 2. Licence — a correction to the ruling's premise

| repo | GitHub licence endpoint | licence |
|---|---|---|
| `SimplifyJobs/New-Grad-Positions` | 404 | **none** |
| `vanshb03/New-Grad-2027` | 200 | MIT |
| `SimplifyJobs/Summer2026-Internships` | 301 | not MIT (redirects) |
| `vanshb03/Summer2027-Internships` | 200 | MIT |

The build brief recorded "both repos in that scope are MIT-licensed, so the licensing question
disappears". **That is not true** — the larger of the two in-scope repos ships no licence at all.

It changes nothing, and the reason is worth stating so the premise is not re-litigated: **no byte of
this data is committed.** The licence question would only bite on redistribution, and R7's
provenance -> source -> licence chain is what would catch an attempt. Reading a public file to derive a
list of board slugs, then writing those slugs into a file in the *user's* config directory, redistributes
nothing. The licensing question is moot, not resolved.

## 3. The corpus, and the two record shapes inside the in-scope pair

`GET https://raw.githubusercontent.com/<repo>/dev/.github/scripts/listings.json` — worked first try for
all four, on branch `dev`, no fallback needed. **Every root is a bare JSON array**, no envelope key.

| | repo | bytes | records | `active: true` |
|---|---|---|---|---|
| S1 | `SimplifyJobs/New-Grad-Positions` | 12,814,358 | 18,813 | 3,145 |
| S2 | `vanshb03/New-Grad-2027` | 626,464 | 1,142 | 631 |
| S3 | `SimplifyJobs/Summer2026-Internships` | 10,890,902 | 14,532 | 1,934 |
| S4 | `vanshb03/Summer2027-Internships` | 275,487 | 471 | 371 |

**In scope is S1 + S2 with `active is True` — 3,776 records.** S3 and S4 are internships and are out of
scope by the owner's ruling; they are transcribed only so the fixture can say what it is not modelling.

**S1 and S2 do not share a schema, and a fixture that models one record shape is wrong.**

| field | S1 | S2 | type | notes |
|---|---|---|---|---|
| `source` | 100% | 100% | str | a GitHub username, unbounded cardinality (13 / 20 distinct) |
| `company_name` | 100% | 100% | str | **whitespace-padded on 114 S1 records** |
| `id` | 100% | 100% | str | uuid-shaped; one S2 value is 37 chars with an embedded backtick |
| `title` | 100% | 100% | str | 2 S2 values padded, one with a literal TAB |
| `active` | 100% | 100% | **bool** | never a string |
| `is_visible` | 100% | 100% | **bool** | S1 has 20 `false`; S2 has none |
| `date_updated` / `date_posted` | 100% | 100% | **int** | epoch seconds; `updated >= posted` is violated by 5 records |
| `url` | 100% | 100% | str | never null, never blank, never non-string, in any source |
| `locations` | 100% | 100% | list[str] | **never empty**, min 1, max 55 |
| `company_url` | 100% | 100% | str | `simplify.jobs/c/<slug>` on S1; **`""` on all 1,142 S2 records** |
| `sponsorship` | 100% | 100% | str | closed, 4 values, 98.4% is the useless `"Other"` |
| `category` | 100% | **absent** | str | not closed: `Software` and `Software Engineering` both exist |
| `degrees` | 100% | **absent** | list[str] | 14-value vocabulary, **29.3% empty lists**, may repeat a value |
| `season` | absent | **2 of 1,142** | str | vestigial; `"Summer"` |

**Absence is always a missing key, never JSON `null`.** Not one field in any source is ever null. So a
reader must handle a *missing* key and need not handle a null one — and `season`, at 2 records in 1,142,
is the field that proves it.

**`company_url` is useless for board discovery and that is a measured fact, not an assumption.** It names
an ATS host on **0 of 3,129** records; it is either a `simplify.jobs` profile page or the empty string.
The board can only come from `url`.

## 4. The URL -> board rule, measured through boardwatch's own parser

`parse_board_target(record["url"])`, distinct on `(provider, slug)`, workday kept as the full
`host/tenant/site` composite, differenced against the 135 boards the live store holds.

| corpus | records | matched | boards | new |
|---|---|---|---|---|
| **S1+S2, `active` (in scope)** | **3,776** | **1,956** | **926** | **897** |
| S1+S2, all records | 19,955 | 12,627 | 2,819 | 2,760 |
| all four, `active` | 6,081 | 3,189 | 1,292 | 1,256 |
| all four, all records | 34,958 | 23,512 | 3,881 | 3,813 |

**The `active`-filtered rows are not stable and no test may assert them against a live fetch.** D-291
recorded 3,778 -> 927 -> 898 for the in-scope corpus a few hours earlier; this session measures
3,776 -> 926 -> 897. The all-records rows reproduce D-291 *exactly* — 19,955, 2,819, 2,760, 34,958,
3,881, 3,813 — which is what proves the match rule is the same one and the drift is `active` flipping as
postings close. That is the whole reason the fixture below is authored rather than captured.

**Provider split of the 897 new boards — the number that bounds the ramp, and it is not the split D-291
recorded.** D-291's split (workday 1,704 / greenhouse 800 / ashby 601 / lever 325 / smartrecruiters 262 /
workable 121) is over *all four lists, all records* — a 3,813-board corpus, not this one.

| provider | new boards | watched today | first-exposure cost |
|---|---|---|---|
| workday | 349 | 50 | spends `detail_fetch_budget` per unseen posting |
| ashby | 167 | 17 | body inline, ~1 request |
| greenhouse | 147 | 64 | body inline, ~1 request |
| smartrecruiters | **107** | **0** | spends `detail_fetch_budget`; **this path has never run at scale** |
| workable | 65 | **0** | body inline, ~1 request |
| lever | 62 | 4 | body inline, ~1 request |

Five of the six serve every board from one host, and `Fetcher` holds a per-host lock for each request's
full duration plus a >=1.0s pace, so boards on one provider serialize against each other and no worker
count compresses it. That is why the ramp is stratified rather than uniform: 441 of the 897 are on the
four inline-body providers and cost about one request each; the other 456 are on the two that spend a
detail budget per unseen posting, and 107 of those are on a provider boardwatch watches zero of today.

**Records per board is 1 for 627 of the 926.** The strongest-evidenced board carries 64 records; the
median carries one. A candidate resting on a single record is the normal case, not a warning — but the
count is worth showing a reviewer, because it is the only evidence of the slug that exists.

## 5. Traps — every one of these is measured, and four of them cannot fire against today's corpus

1. **The malformed-URL set is exactly 7 records, all in S2, all `active`.** Same defect each time: a
   single slash after `https:`, so the host is empty. Verbatim shape:
   `https:/.workable.com/<company>/j/<id>/`. Scanning all 34,958 records finds the same 7 and no others.
   `parse_board_target` refuses them as ordinary input — it raises `UnknownBoardURL`, the same class it
   raises for the 1,820 records on hosts we do not serve — so **there is no exception path to write.**
   One pair differs only by a trailing slash, so they are 6 boards' worth of typo, not 7.
2. **`boards.greenhouse.io/embed/job_app?token=<n>` parses to the slug `embed`.** The board is identified
   by the `token` query parameter, which names a *job*, not a board, so there is no slug in that path at
   all and `parse_board_target` returns one anyway. One live record has this shape. **A shipped defect in
   `parse_board_target`, reachable today by `companies add`, and deliberately NOT fixed in this change:**
   changing a provider's slug extraction changes `companies add` for every user and is its own ruling.
   What this change owes instead is that the candidate carries its evidence URL, so a reviewer sees
   `greenhouse:embed` next to `.../embed/job_app?token=...` and refuses it.
3. **Three ashby slugs are percent-encoded** (`Flock%20Safety`, `Citizen%20Health`, `Rose%20Rocket`).
   `parse_board_target` does not unquote, and whether ashby's API accepts the encoded or the decoded form
   is **not** something this probe established. Unresolved on purpose: guessing would fabricate a request
   contract, and the human review step is where an unproven slug belongs.
4. **`company_name` is whitespace-padded on 114 S1 records.** It must be stripped before it reaches
   `companies.name`, because `scan/apply.py` feeds that column into the `cross_host` posting identity —
   a padded name silently re-keys every identity written under it.
5. **`job-boards.eu.greenhouse.io` — 26 in-scope records on a provider we support, lost to a hostname
   gap.** Greenhouse registers `boards.greenhouse.io` and `job-boards.greenhouse.io` and not the EU
   twin; lever already registers `jobs.eu.lever.co`, so the pattern has precedent and greenhouse is
   simply missing its half. A provider host-map change, so not this change. Same for
   `*.myworkdaysite.com`, which is 9 records.
6. **There is no CJK anywhere in these lists.** Scanned `company_name`, `title` and every `locations`
   element over CJK Unified Ideographs, Hangul, Kana, Compatibility and Halfwidth/Fullwidth forms across
   all 34,958 records: **0 hits in all four sources.** The real non-ASCII is U+2013 EN DASH (610 in S1),
   curly quotes, one U+2011 non-breaking hyphen, and `é` in one employer name. A fixture carrying CJK
   would be modelling something that is not there.
7. **Four checks the live corpus cannot exercise**, so the fixture carries them and the suite is the only
   place they can fire: a missing `url` key (0 records today), a non-string `url` (0), an empty-host URL
   (7 records, and all 7 are in S2 — a source that could stop carrying them tomorrow), and `active`
   disagreeing with `is_visible` (1 record is `active: true, is_visible: false`). "0 today" means inert,
   not safe.
8. **Neither `url` nor `(company_name, title)` is unique** among active records — 12 repeated URLs, and
   one `(employer, title)` pair appears 58 times. Distinctness has to be taken on `(provider, slug)`,
   which is what `companies` is unique on anyway.

## 6. What is deliberately not committed

**No captured record, in any form.** The repo is public. R7 admits a data file only with a declared
`provenance`, and the only honest value for a third party's job listings is `public`, which then obliges
a `license` — and the larger in-scope repo has none (§2). `synthetic` would be a lie. R8 independently
refuses a second `company_enumeration` at any path, so the *emitted candidate file* cannot be committed
either, whatever its provenance: it goes to a path the user names, never into the tree.

The 24 MB of captured JSON lives in a session scratch directory and is not in this repository.

**The fixture is authored to the shape recorded here, and the opposite trap is real:** an authored
fixture proves only what our own code constructs — that is how five of six providers passed a
dereference rule that was wrong. The guard is that every count in `tests/unit/github_lists_shape.py`
traces to a table above, and the tests assert those numbers against literals written independently in
the test file.

## 7. Reproducing every claim here

Four unauthenticated requests and no credentials:

```
for r in SimplifyJobs/New-Grad-Positions vanshb03/New-Grad-2027 \
         SimplifyJobs/Summer2026-Internships vanshb03/Summer2027-Internships; do
  curl -s "https://raw.githubusercontent.com/$r/dev/.github/scripts/listings.json" |
    python3 -c 'import sys,json; d=json.load(sys.stdin); print(len(d), len([r for r in d if r["active"]]), sorted(d[0]))'
  curl -s -o /dev/null -w '%{http_code}\n' "https://api.github.com/repos/$r/license"
done
```

Then, for §4, `boardwatch companies discover --json` over the same two files reports the census, the
board count and the per-provider split of what is new against the store it is pointed at.

**Review deadline.** `tests/unit/github_lists_shape.py` carries `PROBED` and `REVIEW_BY`. Red there is
actionable with the commands above and nothing else: confirm the key sets and the `active` proportion,
then roll `REVIEW_BY` forward with the date and the reason recorded beside it. It is a review deadline,
not a freshness claim.

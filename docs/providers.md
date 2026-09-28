# Per-provider coverage limits

**SmartRecruiters honest limits.** Its API cannot distinguish a typo'd company slug from
a real, empty board — an unknown company returns an empty board, not an error, so
`companies add`, `--verify` and `doctor` flag it as unverifiable rather than confirmed.
`--verify` therefore cannot catch a typo'd SmartRecruiters slug; it says so when it sees one. Job bodies are
fetched once per posting (bounded by `detail_fetch_budget`, default 50) and never
refreshed, since the list endpoint carries no revision signal for description-only edits.
A posting that goes inactive while still listed is not re-detected as closed until it
drops off the list — it self-heals on a later scan.

**Workday honest limits.** Its list endpoint serves no `ETag` and no `Last-Modified`, so
conditional fetches are inert and every scan re-reads the whole board — a 2,000-posting
board is 100+ requests to one host, paced by the usual per-host delay. Each scan admits at
most `detail_fetch_budget` (default 50) **previously-unseen** postings — a body is fetched
once per admitted posting and never refreshed. The rest of the board's live inventory is
carried forward so nothing it still lists is closed, and the remaining postings are admitted
on later scans. A large board therefore reports **`partial`** as its normal outcome and fills
in — postings and bodies alike — across many scans, the same incremental fill SmartRecruiters
bodies get. Raise the ceiling with `boardwatch config set detail_fetch_budget <N>` to admit
more per scan, at the cost of more requests to one host each scan. The registry ships **no**
Workday boards, so `doctor` reports Workday connectivity as *not checked* until you watch one
with `companies add`.

**Oracle HCM honest limits.** A board is a `{host, site}` pair (`oraclehcm:<host>/<Site>`), and an
unknown site number does not fail: the host silently serves its default board instead, echoing the
wrong site back, so `--verify` and `doctor` cannot catch a typo and a mistyped site watches a real
but different board. Check that the first scan's postings are the employer you meant. Bodies need
one detail fetch per unseen posting, bounded by `detail_fetch_budget`, so large boards fill in
across scans.

**Eightfold honest limits.** The board is the career-site host. The listing API needs the
tenant's `domain`, which the host does not carry, so every scan first reads the public career
page to find it. Bodies need one detail fetch per unseen posting, bounded by
`detail_fetch_budget`.

**Phenom honest limits.** A board is `{host, country, language}` on the employer's own domain,
so it is added only as `phenom:<host>/<country>/<lang>` — a pasted URL cannot name one. The
endpoint sends no `ETag` or `Last-Modified`, so every scan re-reads the board, and a wrong
country or language on a live site reads as an empty board rather than an error.

**Jibe honest limits.** Jibe (iCIMS career sites) lives on the employer's own careers host, so
it is added only as `jibe:<careers-host>`. Bodies arrive with the listing, paged at the API's
hard maximum of 100 per request.

**Amazon honest limits.** A board is one amazon.jobs job category (`amazon:software-development`),
checked against a closed catalog when you add it, because the API answers an unknown category
with an empty board instead of an error. The API cannot page past 10,000 results, which is why
a board is one category: the largest held 3,370 postings when measured, so each board is read
whole. Bodies arrive with the listing.

**Apple honest limits.** A board is one country (`apple:united-states`), checked against a closed
catalog when you add it. jobs.apple.com has no public JSON API: boardwatch reads the data the
public search page embeds, and one detail page per unseen posting, bounded by
`detail_fetch_budget`. A change to Apple's front end therefore surfaces as a board error, never
as an empty board that would close every posting.

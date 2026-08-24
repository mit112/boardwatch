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

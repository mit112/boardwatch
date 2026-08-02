# Workable fixtures

Captured fixtures for the Workable provider contract tests (Task 2 / issue p4a-providers).

## Provenance & sanitization (D9 / §6.6 / §0 guardrail 2)

These fixtures use the **exact response shape** of the Workable public widget API
(`GET https://apply.workable.com/api/v1/widget/accounts/<slug>?details=true`), recorded
during an attended session on **2026-08-01**. The structure (top-level `{name,
description, jobs}`; per-job `title`, `shortcode`, `code`, `employment_type`,
`telecommuting`, `department`, `url`, `shortlink`, `application_url`, `published_on`,
`created_at`, `country`, `city`, `state`, `locations[]` (inner key `region`, not
`state`), `description`) mirrors the live API.

**All text is synthetic.** No real company copy, names, URLs, recruiter contacts, or
other data was carried over from any recorded board — only the field *shape* was.
There are no email addresses or PII of any kind (CI's gitleaks job and a fixture-time
scan both confirm this). `name` is the invented "Acme Corp"; `url`/`shortlink` values
point at a fictional `acme` board. The loop never fetches a live API (§0); it only
reads these files.

## Files

| File | Purpose |
|---|---|
| `normal.json` | A healthy board: 5 jobs. The fixture contract below. |
| `empty.json` | A live but vacant board: `{"jobs": []}` → a *complete, empty* inventory (a 200, not a 304). |
| `dead_404.json` | The real Workable 404 body shape (`{"error": "Not found"}`), served with HTTP 404 → `BoardHealth.DEAD`. |
| `normal_response_headers.json` | `{"etag": null, "last_modified": null}` — Workable sends **neither** validator; recorded explicitly so the absence is deliberate and visible, not an oversight. |

## `normal.json` contract (relied on by `tests/contract/test_workable.py`)

1. **≥ 5 jobs.**
2. **≥ 1 job with `telecommuting: true`** (`BBBB222222`) — this branch is unverified
   against live data, so it is synthetic by construction.
3. **≥ 1 job with multiple entries in `locations`** (`CCCC333333`: Austin + Toronto).
4. **≥ 1 job with an empty `department`** (`DDDD444444`: `""`).
5. **All `shortcode` values unique.**
6. `jobs[0]` (`AAAA111111`) has a non-empty `title` **and** a non-empty `department` —
   the Task 7 harness mutates `jobs[0]`'s department as its metadata field.

If any file is missing or the contract is not met, this task must STOP — that is an
attended-session gap, not loop work.

# Greenhouse fixtures

Captured fixtures for the Greenhouse provider contract tests (Task 6 / Issue #6).

## Provenance & sanitization (D9 / §6.6 / §0 guardrail 2)

These fixtures use the **exact response shape** of the Greenhouse public Job Board API
(`GET https://boards-api.greenhouse.io/v1/boards/<slug>/jobs?content=true&pay_transparency=true`),
recorded during an attended session on **2026-06-12**. The structure (top-level
`{jobs, meta}`; per-job `id`, `title`, `content`, `location`, `departments`, `offices`,
`absolute_url`, `first_published`, `updated_at`, `requisition_id`, `metadata`,
`data_compliance`, `pay_input_ranges`) mirrors the live API.

**All text is synthetic.** No real company copy, names, URLs, recruiter contacts, or other
data was carried over from any recorded board — only the field *shape* was. There are no
email addresses or PII of any kind (CI's gitleaks job and a fixture-time scan both confirm
this). `company_name` is the invented "Acme Corp"; `absolute_url`s point at a fictional
`acme` board. The loop never fetches a live API (§0); it only reads these files.

## Files

| File | Purpose |
|---|---|
| `normal.json` | A healthy board: 5 jobs. The fixture contract below. |
| `empty.json` | A live but vacant board: `{"jobs": [], "meta": {"total": 0}}` → a *complete, empty* inventory (a 200, not a 304). |
| `dead_404.json` | The real Greenhouse 404 body shape (`{"status": 404, "error": "Job not found"}`), served with HTTP 404 → `BoardHealth.DEAD`. |
| `normal_response_headers.json` | The `etag` / `last_modified` validators for the conditional-GET (304) exchange. |

## `normal.json` contract (relied on by `tests/contract/test_greenhouse.py`)

- **≥ 5 jobs**, each with a non-empty `id`, `title`, `absolute_url`, and HTML-escaped `content`
  that unescapes to non-empty `body_text`.
- **≥ 1 job with `pay_input_ranges`**, and **≥ 1 of those with ≥ 2 ranges** (multi-zone).
  `pay_input_ranges` entries carry `{min_cents, max_cents, currency_type, title, blurb}` and are
  preserved inside `raw_json` only — D25: Greenhouse pay is captured, never projected to
  `salary_*` scalars in v1.
- `jobs[0]` has a title (the partial-parse test deletes it to force a `partial` snapshot).
- At least one job's location derives `remote_policy == "remote"`.

If any file is missing or the contract is not met, Task 6 must STOP — that is an
attended-session gap, not loop work.

# Lever fixtures

Captured fixtures for the Lever provider contract tests (Task 16 / Issue #16).

## Provenance & sanitization (D9 / §6.6 / §0 guardrail 2)

These fixtures use the **exact response shape** of the Lever public postings API
(`GET https://api.lever.co/v0/postings/<slug>?mode=json`), recorded during an attended
session on **2026-06-13** from public boards only. The structure (a top-level JSON
**array** of postings; per-posting `id`, `text`, `categories` (`location`, `team`,
`commitment`, `allLocations`), `createdAt`/`updatedAt` as epoch **milliseconds**,
`hostedUrl`, `applyUrl`, `descriptionPlain`, `additionalPlain`, `workplaceType`,
`country`) mirrors the live API.

**All text is synthetic.** No real company copy, names, URLs, recruiter contacts, or
other data was carried over from any recorded board — only the field *shape* was. There
are no email addresses or PII of any kind (CI's gitleaks job and a fixture-time scan both
confirm this). The company is the invented "Acme Corp"; `hostedUrl`/`applyUrl` point at a
fictional `acme` board. The loop never fetches a live API (§0); it only reads these files.

## Recorded API facts (attended 2026-06-13)

- **Empty-but-live board** returns HTTP **200** with body `[]` → a *complete, empty*
  inventory (not a 304).
- **Dead board** returns HTTP **404** with body `{"ok": false, "error": "Document not found"}`.
- **Bodies are plain text** in `descriptionPlain` / `additionalPlain` — `html_to_text()` is
  **not** on the Lever path (contrast Greenhouse/Ashby HTML).
- `createdAt` / `updatedAt` are epoch **milliseconds** (13 digits), not seconds.
- **Validators:** the live API serves an `ETag` (weak, e.g. `W/"...."`) but **no
  `Last-Modified`**. `normal_response_headers.json` therefore carries a real-shape synthetic
  `etag` and a synthesized `last_modified` so the conditional-GET (304) contract test can
  exercise both `If-None-Match` and `If-Modified-Since`.
- **Salary** text may appear in `additionalPlain` and is **never mined** (D19): Lever writes
  no `salary_*` columns.

## Files

| File | Purpose |
|---|---|
| `normal.json` | A healthy board: 6 postings (JSON array). The fixture contract below. |
| `empty.json` | A live but vacant board: `[]` → a *complete, empty* inventory (a 200, not a 304). |
| `dead_404.json` | The real Lever 404 body shape (`{"ok": false, "error": "Document not found"}`), served with HTTP 404 → `BoardHealth.DEAD` / `failed`. |
| `normal_response_headers.json` | The `etag` / `last_modified` validators for the conditional-GET (304) exchange. |

## `normal.json` contract (relied on by `tests/contract/test_lever.py`)

- **≥ 5 postings** (a JSON array), each with a non-empty `id`, `text`, `hostedUrl`, and a
  non-empty `body_text` joined from `descriptionPlain` + `additionalPlain`.
- Every posting has a 13-digit epoch-**millisecond** `createdAt` that resolves to a year ≥ 2020
  (the ms-vs-s guard).
- **≥ 1 posting with salary text inside `additionalPlain`** (contains `$`) — proves D19:
  the text is preserved in `raw_json` and never projected to `salary_*` scalars.
- **≥ 1 multi-location posting** (`categories.allLocations` with ≥ 2 entries).
- `postings[0]` has a `text` (the partial-parse test deletes it to force a `partial` snapshot).
- At least one posting's location derives `remote_policy == "remote"` (case-folded `"remote"`
  in a location name).

If any file is missing or the contract is not met, Task 16 must STOP — that is an
attended-session gap, not loop work.

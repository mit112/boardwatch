# Companion status documents

A companion is any tool you run beside boardwatch — a nightly reviewer, an apply planner — that
wants its state shown in `boardwatch web`. boardwatch does not know where a companion lives or
what files it keeps. The companion writes one small JSON document, and boardwatch reads it.

## Where

`<data_dir>/companions/<name>.json`, one file per companion. `<data_dir>` is the one
`boardwatch settings` prints. Write the file atomically (write a temporary file in the same
folder, then rename it) so the viewer never reads half a document.

## Format (schema `boardwatch.companion/1`)

```json
{
  "schema": "boardwatch.companion/1",
  "name": "reviewer",
  "updated_at": "2026-11-17T10:14:00-06:00",
  "state": "failed",
  "summary": "Batch done 10:14; store write failed: scan lock held.",
  "counts": {"asked": 80, "closed": 18, "skipped": 62},
  "items": [
    {"label": "Acme — Software Engineer", "reason": "sign-in wall", "link": "https://…", "needs_owner": true}
  ]
}
```

| Field | Required | Rule |
|---|---|---|
| `schema` | yes | exactly `boardwatch.companion/1` |
| `name` | yes | equal to the file name without `.json` |
| `updated_at` | yes | ISO 8601 with a UTC offset |
| `state` | yes | `ok`, `running`, `failed` or `stale` |
| `summary` | yes | one plain sentence, not empty |
| `counts` | no | a flat object of `label: integer` |
| `items` | no | rows with a string `label`, and optional string `reason` and `link` and boolean `needs_owner` |
| `history` | no | at most 31 rows of `{"label": "2026-11-17", "counts": {...}}`, newest first, shown as a table on the Runs page |

Items carry no other keys. Do not put private answer text or personal data in a document; the
viewer shows what it is given.

## History

A companion that runs nightly (a reviewer, say) can keep its last nights in `history`. Each row
is one night: a `label` (the date) and flat `counts` (asked, answered, closed, held, the store
write's result as a count of rows written). The Runs page shows one table per companion with a
history, one column per count label. Put a rate you want shown, such as a second judge's
agreement, in as a count over its denominator (`agreed` beside `proposed`); the page prints the
numbers it is given and computes nothing.

## Apply-plan counts

A companion that plans applications reports its plan in `counts` with three key prefixes, and
the Applied page shows them beside boardwatch's own application pace:

- `fillable:<board>` — leads ready to fill on that apply board (`fillable:ashby: 51`);
- `dropped:<reason>` — leads taken out of the plan, by reason;
- `waiting:<reason>` — leads held until something happens, by reason.

Days of capacity is the fillable total divided by the trailing 7-day application rate. A
companion in state `failed` is not read as a plan.

## What the viewer does

`GET /api/companions` returns `{"companions": [...]}`, sorted by name, with each valid document
unchanged. A file that is not valid JSON or breaks a rule above is shown as `state: failed` with
the summary `unreadable status: <why>`. It is never hidden: a status nobody can read is a
monitoring failure. With no `companions` folder the list is empty.

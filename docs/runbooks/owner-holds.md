# Owner holds

A hold is a reversible owner decision on one canonical job and its sibling postings. It does not
change eligibility, application history, manual routing, or skip/report state. It remains active
until explicit release, including across JD/profile/policy changes.

```sh
boardwatch ledger hold --job 123 --reason "Awaiting employer verification"
boardwatch ledger holds --json
boardwatch ledger release-hold --job 123
boardwatch ledger holds --all --json
```

Use the canonical job ID, not a posting ID. A missing job or blank reason is refused. Commands
operate on the selected store (`--data-dir` precedes `ledger`); no old triage overrides are imported
automatically. Releasing an absent hold is a no-op. Repeating a hold replaces that job's last
hold/release record; this is not an immutable event log.

Held leads leave the API's actionable apply/review/manual/rejected lists immediately. The API's
`held` list and `ledger holds` explain the reason; no frontend controls are added. Existing queue
folders move to `_held` during ordinary queue refresh, preserving owner files. Applied, skipped,
reported and closed drains retain precedence. Release returns a lead to its current lane on
refresh, subject to every existing eligibility/application/ledger decision. It does not clear a
separate built/skip disposition or reopen a closed posting.

Normal ranking and execution, plus explicit projection/tailoring, honor the hold. A hold added
after selection defers work at the next boundary without marking it seen/built/skipped. A check
is not a lease: work already running may finish or register artifacts. This mechanism does not
cancel a subprocess, remove projections, infer company caps, or expire pending owner decisions.

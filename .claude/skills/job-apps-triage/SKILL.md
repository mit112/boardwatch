---
name: job-apps-triage
description: "Re-triage every lead in boardwatch web (Apply by hand + queue + review): native-close dead postings, skip hard stops and duplicates, build missing résumés, regenerate the portal-grouped apply sheet. Triggers: '/job-apps-triage', 'triage boardwatch web', 'clean up the apply list', 'which of these jobs are still open'."
user-invocable: true
origin: hand-authored
---

# /job-apps-triage

This skill lives in the job-apps repo, which owns the triage engine, the apply sheet and the closed/skip logs.
Read `~/dev/Job apps/.claude/skills/job-apps-triage/SKILL.md` and follow it exactly. Run every command from
`~/dev/Job apps`; the engine calls this checkout's `.venv` for the DB writes.

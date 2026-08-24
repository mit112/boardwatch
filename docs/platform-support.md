# Platform support

**Linux and macOS are supported** — every push is tested on both, across Python 3.11, 3.12
and 3.13. **Windows is best-effort**: the core is written to be portable and the full suite
runs there nightly, but it is not a platform any release is blocked on, and three caveats are
known and unfixed:

- **Résumé PDFs are effectively unavailable.** poppler's `pdfinfo` has no package-manager route on
  Windows, and without it the page-count gate cannot answer, so tailoring fails the run. Scanning,
  ranking and the eligibility audit are unaffected.
- **Desktop notifications are unavailable**; configure a webhook instead (see
  [scheduling](scheduling.md#notifications)).
- **No Task Scheduler recipe** is provided — only cron, launchd and systemd.

A fourth caveat used to sit here and is now **fixed**: killing a command mid-write could briefly make
its bundle look locked, so the next `profile-bundle promote` or `rebase-draft` reported
`bundle_lock_held` for a lock nobody held. Windows tears a killed process's file handles down
asynchronously, and the acquire believed the first refusal; it now re-asks the operating system for up
to a second instead. That window is a judgement rather than a measurement, so a slower teardown could
still surface it — if you ever see `bundle_lock_held` with no other command running, **retry rather
than deleting the lockfile**, which is never a safe repair, and please report it: the report is
evidence the window is too small.

If you run Windows and any of this blocks you, open an issue — the constraint is attention, not a
decision that it should not work.

# boardwatch docs

- [Configuration](configuration.md) — settings and where they live.
- [Platform support](platform-support.md) — Windows caveats and what's fixed.
- [Scheduling](scheduling.md) — cron/launchd/systemd scan recipes and notifications.
- [Running the pipeline unattended](unattended-run.md) — `boardwatch run` as a scheduled daily driver.
- [Tailoring](tailoring.md) — opt-in LLM résumé rewriting, API and agent lanes.
- [Provider notes](providers.md) — SmartRecruiters and Workday honest limits.
- [Authoring the career-profile bundle](profile-bundle-authoring.md) — the private, revisioned store
  of the facts a résumé is assembled from: what the format admits, every command, and recovery.
- [Projecting a bundle into a résumé](projection-rendering.md) — the two files you author and the
  `approve-projection` → `project` → `tailor run` path from a promoted bundle to a PDF.
- [Predicate catalog audit](profile-bundle-predicate-catalog-audit.md) — the seeded starter catalog.

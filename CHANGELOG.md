# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- **A failed run now records why it failed.** Run 132 was stamped `failed` with an empty error
  list: one board was attempted, it came back `partial`, nothing completed, and the sentence that
  explained it — "systemic scan outage: 1 boards attempted, none completed" — was written only to a
  console log that has since scrolled away. That is the shape several fatal paths took. Four guards
  below the tailor loop (the all-leads-unrendered fatal, the zero-output guard, cohort completeness
  and filesystem-truth) set the run's fatal outcome and fell straight through to `finish_run`
  without ever adding it to the list that gets persisted, and the standalone `boardwatch scan`
  classified the outage as fatal without recording it at all — `partial` is counted neither
  complete nor failed, so not even a per-board error line was left behind. The fix is one choke
  point rather than five patches: the `finally` that closes the run row now appends the fatal
  reason unless a stage already recorded it, so a fatal path added a year from now is covered
  without anyone remembering to record it, which is precisely the discipline the old design kept
  asking for and not getting. The dedup is a suffix test, because every site that does record
  prefixes the reason with its stage; where that test is ever wrong it errs toward writing the
  reason twice rather than losing it. The standalone scan gained the same sentence — shared with
  the pipeline's copy, so one event cannot be described two ways depending on which command
  observed it — and only when it owns the run's terminal status, so `boardwatch run` still records
  it exactly once.

- **A heartbeat the monitor refuses is no longer silent.** The dead-man's-switch ping's return
  value was discarded, and only a raised exception produced so much as a console line. An HTTP
  4xx/5xx, a rotated token, or a deleted healthchecks.io check therefore left no local trace of any
  kind — and the external monitor cannot help, because it sees no ping and cannot tell a refused one
  from a machine that never woke up. The whole unattended safety net rests on that one request, so
  its failure read as health. `send_heartbeat` now returns the same `str | None` soft alert shape
  the intake-death detector uses: `None` when there is nothing to act on — the ping was
  acknowledged, or no URL is configured, which stays the silent default for everyone who never set
  one — and a one-line alert when a ping was attempted and did not land. The run prints it, puts it
  on the error list the CLI reprints, and makes it durable on the run row. It remains strictly
  fail-open: no fatal, no raise, no retry, and never a second ping. The alert names an HTTP status
  or the transport exception's class and never the URL, which embeds a token. One limitation is
  worth stating rather than hiding: the heartbeat gate is deliberately the last thing a run does,
  because it has to observe whether the funnel and the morning digest were written before it
  asserts the run was clean — so this note reaches the console and the run row, and neither of that
  day's artifacts.

- **A delivery-queue failure is now recorded, not just printed.** The funnel and morning-digest
  handlers already record their write failures to `runs.errors_json` (via `append_run_error`, because
  they run after `finish_run`), but the queue-sync handler only printed a console line and appended to
  the in-memory error list — which never reaches the store. Under unattended operation that made a
  queue that stopped receiving leads invisible to anything reading the database. The handler now
  records it durably, exactly like its two siblings. Per-lead copy failures (already surfaced as a
  count on the queue line) keep their existing deliberate behaviour — they are not escalated.

- **The hiring.cafe search now asks the way the user agent it sends says it will.** The lane has
  carried a Chrome user agent since it shipped, but none of the headers that user agent implies —
  and httpx's default `Accept: */*` contradicts it outright, because no browser asks for `*/*` when
  navigating to an HTML page. The reference client that reaches this host daily from the same
  machine sets exactly one header by hand, `Accept: text/html`, and is otherwise *sparser* than we
  are: no `Accept-Language`, no `Sec-Fetch-*`, `Connection: close`. It is not refused. That rules
  out "too few browser headers" and leaves the contradiction as the difference worth removing. The
  search route now sends a browser's navigation header set; `/api/job-description` — an XHR, and the
  half of this lane that still works — deliberately keeps the defaults, so the change touches one
  request kind on one lane rather than every request on the shared lane client. Two omissions are
  deliberate and pinned by a test: no `sec-ch-ua*` client hints, which a server negotiates with
  `Accept-CH` and which would assert something the user agent does not; and no hand-set
  `Accept-Encoding`, because this client cannot decode the `br`/`zstd` a real Chrome advertises and
  advertising an encoding it cannot read would trade a header mismatch for a corrupted body.

### Added

- **Soft alerts can now reach an owner who is away from the machine.** The six run alerts render
  into the morning digest, which is a file under `~/boardwatch-applications/<date>/` on local disk —
  in no synced folder. The heartbeat gate is satisfied by a merely non-fatal run, so a run that
  raised every one of those alerts still pinged the monitor, and pinged green. A crash or a machine
  asleep was always covered (the ping simply stops and the monitor alerts); what nothing reported was
  the run that **succeeded while degraded** — intake death against a dead fleet, a scan outage, a
  collapsed corpus — which over a fortnight of unattended running reads exactly like a fortnight of
  healthy ones. `notify/alert_escalation.py` POSTs the run's alerts to a URL read from
  `BOARDWATCH_ALERT_URL`; point it at a healthchecks.io `/fail` URL and the check already watching
  for silence also reports degradation. Presence-gated and **unset by default**, so it is a no-op
  until configured, and read from the environment rather than `config.toml` because the URL embeds a
  token. It is deliberately the last thing the finalize block does: it reports the alerts every
  handler above raised rather than raising one, so it runs after all of them — and after the
  heartbeat, so a refused ping travels in the report too (D-376).

- **A collapse that makes the whole corpus ineligible is no longer the one failure nothing watches.**
  The delivery-drought alert abstains on it by design — its honest guard is "did this run judge a
  candidate?", and a corpus that has gone entirely ineligible judged none — and the intake alert stays
  quiet because postings keep arriving. So a rules edit or a profile fact that stops resolving could
  empty the standing eligible corpus and every signal would still read green. The three numbers that
  would have shown it existed only inside each run's funnel artifact on disk, where no cross-run query
  could reach them, so they now also land on the run row: the open corpus, how much of it was
  evaluated, and how much of that cleared. A new detector compares the run's candidate **rate** against
  the median of the last five comparable runs and raises a soft alert when it has halved. A rate rather
  than a count, and that choice is load-bearing: the eligibility identity re-keys often enough that a
  perfectly healthy run can evaluate 5% of its own corpus, which any count-based threshold reads as a
  96% collapse and pages on at four in the morning. Runs that judged less than half their corpus are
  skipped for the same reason. Checked against the recorded history before shipping — across 66 clean
  runs the rate never moved by more than the trigger allows, and an injected collapse fires on the first
  run it touches. Like the other detectors it never fails the run, and the alert is written to the run
  row as well as printed, because an unattended machine prints to a log nobody reads.

- **The morning digest now carries the run's alerts, and the heartbeat waits for it.** Every soft
  alert this program raises — a collapsed lane, a stalled intake, an unsynced delivery queue, a
  degraded tailor — did the same two things: appended to the run's error list and wrote the note
  onto the run row. Neither had a reader. The list is reprinted to a console that, unattended, is a
  log file nobody opens; `runs.errors_json` is queried by nothing; and the funnel renders them under
  `## Errors` at the very bottom, which on run 131 put a real hiring.cafe failure at line 1388 of a
  116 KB file. The one artifact the owner actually reads each morning rendered no error at all. It
  now opens with an `## Alerts` section, above `## Discovery reach`, because reach is a measurement
  and an alert is very often the reason that measurement is wrong. A healthy run says so in one line
  rather than omitting the section: a block that disappears when it has nothing to say is
  indistinguishable from a block that stopped working, which is exactly the state this file was in.
  The run's fatal message is carried separately and never folded into the alert count, because three
  guards — zero-output, cohort completeness, filesystem-truth — set it without appending anything to
  the error list, and a digest reading only that list would have printed "no alerts" on a run that
  failed outright. The markdown stops after eight alert lines and names how many it withheld and
  where they live; the JSON sibling carries the full list, so the cap costs a reader nothing. The
  digest is also emitted last in the run's finalize block, after the queue sync and the intake-death
  check, so the notes those append reach it rather than landing after it was written.

  The heartbeat is gated on that write. It was already gated on the funnel, on the grounds that a
  run whose authoritative record is missing must not ping green; the digest now earns the same
  treatment for a stronger reason, because it is the only channel by which any of this reaches an
  absent owner. A run whose digest failed to write delivered its leads and delivered none of its
  warnings, and looked identical to a run with nothing to warn about. Withholding the ping never
  fails the run, never changes its status and never discards a lead — the leads still ship — it only
  makes the external monitor say something.

- **A liveness prober that cannot reach anything no longer passes as a clean corpus.** The liveness
  stage is fail-open by design: any transport fault returns `unknown`, and `unknown` is served, so
  that a timeout costs a wasted résumé rather than a missed job. The cost of that direction is that
  a prober whose egress has broken — DNS, a proxy in front of it, the machine's IP blocked — returns
  `unknown` for the entire shortlist, drops the gone count to zero, and ships every lead unverified
  while the run line reads exactly as it does on a good night; unattended, the owner would be handed
  dead requisitions presented as live for as long as the break lasted. A new detector raises a soft
  alert on the conjunction, which is what neither half says alone: a high `unknown` share is a normal
  bad afternoon on one provider, and a gone count of zero is the ordinary state — it has been zero on
  every instrumented run on record — but together they say the prober asked about the whole shortlist
  and got not one definitive answer. The threshold is a rate rather than a count, because the
  shortlist size is `--top` and that has moved 8 → 40 → 10 → 40 inside a fortnight; it is set at 75%
  of a shortlist of at least ten, against a recorded worst clean run of 3 unknown of 8 (37.5%), and
  of 2 of 10 and 3 of 40 at the sizes the pipeline actually runs at. A run that was never probed
  abstains rather than reporting a clean result it never took. Like the rest of this family the alert
  reaches `summary.errors` and the `runs` row through `append_run_error` and never sets the run's
  fatal outcome, so the heartbeat still fires — a blind prober tickets, it does not trip the
  dead-man's switch. It judges one run rather than a window, and that is a limitation rather than a
  preference: the three liveness counts live only on the in-memory summary and in the per-run funnel
  JSON, so there is no persisted per-run column to read a window off the way the intake detector reads
  `runs.new_count`.

- **A run that scans fine but finds nothing new no longer passes silently.** The heartbeat fires on
  any clean outcome, so a dead board fleet or a silent fetch regression — the pipeline running
  perfectly and returning zero new postings every night — looked identical to a healthy run. A new
  detector reads the per-run net-new count the scan already records (`runs.new_count`) and raises a
  soft alert when three scanning runs in a row all find zero. It is a slow-burn signal by design: the
  alert is appended to the run's error list (reprinted by the CLI and persisted to the run row via
  `append_run_error`) and never sets the run's fatal outcome, so the heartbeat still fires — a stalled
  intake tickets, it does not trip the dead-man's switch. Runs whose scan never recorded a count — a
  `top --no-record` phantom — are skipped rather than read as zero, and fewer than three scanning runs
  of history abstains rather than firing on a fresh store.

- **A majority-of-the-fleet scan outage is no longer silent.** A run is only made fatal when *every*
  board fails; a provider block — Workday is the bulk of the 379-board fleet — or an IP-reputation
  problem can dark most of the boards while a handful of other providers still complete. That is not
  systemic, so the run stays clean and the heartbeat fires green while intake collapses, and the
  intake-death detector cannot see it because the survivors still emit some new postings. A run whose
  failed-board fraction crosses half now raises a soft, non-fatal alert recorded on the run — a partial
  outage tickets rather than paging, because it is not a systemic one and a false page on a transient
  timeout burst is worse than a note read on the next review.

- **A pipeline that finds leads but ships none no longer passes silently.** Intake can be healthy —
  boards up, new postings arriving — while the tailor, rank, or delivery path drops every candidate:
  an over-suppression bug, a ranker that hides everything, a broken résumé render. The run reaches a
  clean outcome, so the heartbeat fires green, and the intake-death detector stays quiet because
  net-new is not zero. A detector now raises a soft, non-fatal alert when the last three clean runs
  each judged at least one new eligible/uncertain candidate yet delivered zero leads. The candidate
  guard keeps it honest: a quiet steady-state run that had nothing new to judge, and a full
  eligibility collapse where nothing was judged eligible, both judge zero candidates and abstain — it
  fires only when the pipeline is finding deliverable postings and dropping all of them.

- **Twenty more Workday boards are watched; the fleet is 379.** Breadth batch 2 had been deferred
  because its boards had never been timed cold. One was: a cold Workday board scanned in 604 s,
  enumerated 420 of 420 postings, and stopped at exactly 400 — the detail-fetch budget — deferring the
  remaining 20. A cold Workday board is therefore bounded by that budget rather than by how big the
  board is, which puts the whole batch at roughly +34 minutes of scanning on its first run and about
  +5 minutes thereafter. The four SmartRecruiters boards in the same batch are deliberately left out,
  and the reason inverts the intuition: every SmartRecruiters board is served from one host, which the
  fetcher serializes and extra scan workers cannot help, so those four would cost more wall clock than
  all twenty Workday boards combined. Each Workday board was re-verified as watched by querying the
  store back against the source list rather than trusting the importer's own count.

- **`Fetcher.get` accepts per-request headers.** One caller needs them — the lane above — and they
  are merged *under* the conditional-GET validators, so a caller cannot clear an `If-None-Match` and
  silently turn every conditional GET on a board into an unconditional refetch.

- **The React viewer has a test suite, and the gate runs it.** Until now the frontend's only checks
  were `tsc --noEmit` and eslint, so `make check` could not see a render regression at all — the
  error boundaries added for the queue page, and the loose `== null` guards that absorb the viewer's
  structural disk-bundle-vs-memory-API skew, were both behaviour no test covered. vitest and jsdom
  now run as a `web-test` prerequisite of `check`, and as a step in CI's web job, because nothing in
  CI runs `make check` on a pull request. The target is deliberately **not** conditional on node
  being installed: a check that skips itself where the toolchain is missing reports green while
  verifying nothing. Eight tests cover the four boundary scopes and the skew guards, and each was
  confirmed to fail against the broken implementation before being counted — removing any one
  boundary, or tightening any `== null` to `=== null`, turns the suite red. Two guards were left
  unasserted on purpose and say so in the file: `new Date(undefined)` and `new URL(undefined)`
  behave identically under both comparisons, so a test on them would pass against the tightened
  version and prove nothing.

### Changed

- **A lead the delivery queue could not copy is now recorded, not just printed.** `sync_queue` and
  `reconcile_queue` both isolate their per-lead failures inside their own report rather than raising,
  which is what keeps a queue copy from ever failing a run — and the run hook counted those failures
  into its log line and did nothing else with them. That was a deliberate contract, and it was the
  right one while somebody was watching the run: the queue holds copies, and the dated tree and the
  funnel are the real output. It stops being the right one unattended. The log line goes to a file
  nobody opens, so a queue that had quietly stopped copying leads was byte-identical in the store to
  one that copied every single one, and the owner would go on trusting a queue that had gone empty.
  The hook now returns the combined failed count and a non-zero one is escalated the same way every
  other reporting failure in the run's finalize block is — onto `summary.errors`, which the CLI
  reprints, and onto the run row through `append_run_error`, because the hook runs after
  `finish_run` and nothing appended to the summary alone survives the process. Still non-fatal: the
  run's outcome, its status and its leads are all untouched, and all three are asserted so. The test
  that pinned the old console-only contract was inverted to the new one and confirmed to fail
  against the old implementation first, and a second test covers the drain half of the count, which
  had no provocation of its own and would otherwise have let a version that reported only sync
  failures ship green.

- **A degree requirement's boilerplate no longer reads as a field of study.** The `education` field
  surface matched the mass noun wherever a posting talked *about* education rather than naming it as
  a subject — "or educational equivalent", "an equivalent combination of education and experience",
  "Accreditation Commission for Education" — so a posting asking for a degree in Engineering was
  read as demanding a degree **in education** and decided `unmet` against a candidate it had named
  no field for at all. Counted over the open corpus, those frames outnumber the genuine field sense
  by roughly twenty to one. The surface now rejects them on the word immediately preceding the noun,
  which the field sense never takes, and no longer matches `educational` at all. Separately, the
  relatedness escape could not read **"or another related field"** or "or other related field" — the
  alternation admitted only "a" and "an" — so a posting that had plainly opened its requirement was
  still treated as naming a closed set. 483 open postings carry that phrasing. Both defects could
  only ever produce a wrong rejection, never a wrong clearance.

- **Every held-back lead now says which reason held it.** The queue splits leads into an apply lane
  and a review lane, but a review row carried a marker only when the role gate had positively
  classified its title as *not* software. A lead held because its location was confirmed outside the
  US, or because the gate simply would not vouch for the title either way, rendered exactly like a
  clean one. The lane decision now returns its reason alongside the lane from the same branch, so
  the page and the `_review` folder cannot start disagreeing about a lead, and each review row is
  labelled `outside the US`, `role vetoed`, `role unconfirmed` or `ineligible verdict`. The two role
  cases stay separate on purpose: the gate's `uncertain` is an abstain, and reporting it as "not
  software" would assert a decision the gate declined to make.

- **A held-back lead no longer carries the same reason twice.** Once every review row began naming
  the reason it was held, a lead held because the role gate vetoed its title showed both "role
  vetoed" and "off target" side by side — two chips derived from the same check, saying the same
  thing. The second is now suppressed on exactly that case. It is kept everywhere else it still
  means something: on a lead held for a location or an ineligible verdict, where it reports a
  separate finding such as a seniority band, and on the apply queue, where a lead that is otherwise
  ready to send but carries an off-target title has nothing else to warn the reader with. Opening a
  lead still shows both, with each reason spelled out.

- **The review app has a new visual language.** One type size appeared in 47 places, one corner
  radius in 42, and a border was drawn around every container, so a dense instrument read as a
  spreadsheet. Depth now comes from elevation rather than outlines, the corner radius is a language
  of three deliberate steps instead of a default, and the monospace face carries headings, metric
  numerals and labels while the sans face keeps prose. The two figures the page is opened to read
  are set at display scale. No web font is downloaded or bundled: the app ships inside the wheel and
  is served from localhost, often offline. Every foreground and background pair was re-checked
  against the lightest surface it can land on and clears WCAG 2.2 AA, and the keyboard model, focus
  containment and reduced-motion behaviour are unchanged.

- **The per-host request delay can be measured from the start of a request.** It was measured from
  the end of the previous one, so a host saw one request every delay *plus* however long each took —
  about 0.6 requests per second where the setting read 1.0. `pace_from_request_start` makes the
  delay the whole interval. It is **off by default and stays off unless you turn it on**: raising it
  is a real increase in the load every job board sees, and that is not a default this project sets
  on anyone's behalf.

- **The delivery slate is capped at one lead per company, title and byte-identical JD.** Run 129
  delivered ten leads and nine were a single requisition — one CGS Federal `ServiceNow Developer`
  posted to nine cities, with one `company_id`, one normalized title and one byte-identical
  `content_hash`. Nothing suppressed it and nothing could: `exact_quad`, the only suppressing
  identity kind, includes `locations`, so one requisition split across nine cities is nine groups
  of one. The ranker now allows **one lead per `(company_id, normalized_title, content_hash)` per
  run**. It is a delivery cap, not a claim that two postings are the same job: nothing is suppressed
  permanently, a capped lead is never recorded `seen` so it ranks again on the very next run, and no
  identity, ledger or `IDENTITY_ALGORITHM_VERSION` change is implied. Because the cap sits inside the
  rank cutoff, the freed slot is **refilled** from further down the ranking — the same run now
  delivers three distinct employers where it delivered three copies of one. Sized over delivered
  leads rather than the corpus: across runs 119-129's 110 delivered leads it frees nine slots and
  fires on two runs, with no collateral. The hash is part of the key because one run's two
  same-company, same-title leads carried **different** hashes and were two genuinely distinct
  requisitions. **A body-less posting is never capped** — `content_hash` is never null or empty, so
  its presence proves nothing, and every body-less posting hashes the empty string: all 245 in the
  corpus share one digest and six `(company, title, hash)` groups are already collisions of that
  kind, one of them a `software engineer frontend` pair. `hidden_slate_cap` is its own never-folded
  bucket, equal to the number of slots freed, listable with `top --include-slate-cap`, and each
  drained row names the lead that displaced it.

- **Each JD-acquisition lane now reports its cost split into paced fetching and serial applying.**
  The lane stage cost 6.5 minutes on run 129 and swung fourfold run to run for *more* work, and a
  stage total could not say why: upstream throttling and contention on the single writer produce the
  same number. The funnel now carries `fetch_seconds` and `apply_seconds` per lane, and the `Lanes`
  markdown names the fetch **share**, because the ratio is what tells you whether parallelism would
  help. `null` means not measured and is never rendered as `0.0s`, so a lane that failed before it
  was timed can never read as a lane that cost nothing.

- **The lane fetches now overlap, while `apply_board` remains the single writer.** Lanes ran strictly
  one after another, so hiring.cafe waited for LinkedIn even though they are different hosts and
  politeness never required it. Each lane is now split into a paced fetch, which runs off the main
  thread, and an apply, which does not — two lanes applying at once would put two writers on one
  SQLite store. Per-host pacing is unchanged and unchangeable by this: the fetcher holds a lock per
  host for a request's full duration and paces inside it, so requests to one host still serialize and
  no third party sees a higher rate. The gain is bounded by the slowest lane rather than divided by
  the lane count — about two minutes, after which the stage is tail-bound on LinkedIn alone.

- **The queue UI's WCAG 2.2 AA failures are fixed and the triage list is keyboard-first.** The
  review page is worked top-down every morning against a few hundred leads, and measurement of the
  shipped bundle found it neither accessible nor fast to work. Each failure was measured in a
  browser rather than argued: `--color-fg-3` and `--color-control` were verified against
  `--color-bg` and then painted on `--color-surface-2`, where they compute **4.32:1** (needs 4.5)
  on every selected row and **2.90:1** (needs 3.0) for the border of every chip and badge inside
  the detail pane — both are now derived against the lightest surface they ever land on.
  `role="row"` and eight `role="columnheader"` were emitted with **no grid or rowgroup above them
  and no role on any data row**, so every `aria-sort` the table set was announced to nothing; the
  list is a real `role="grid"` now. Four focusable controls per row measured **1,399 tab stops** on
  one page and nothing below the list was reachable in practice — the tab stop is the row now
  (roving `tabIndex`), which measures **14**, and every row control keeps a single-key equivalent.
  Neither route had an `h1`. `scroll-margin-top` was 0 under a 61px sticky header (SC 2.4.11). The
  undo toast — the only route back from a mark-applied or a skip — expired on a timer the reader
  could not stop (SC 2.2.1); hover or focus holds it now. Rows are 37px rather than 53px (18 on
  screen, not 12) and no longer lose their actions when the detail pane opens, with `j`/`k`,
  `Enter`, `o`, `a`, `s` on the focused row and `/` for the filter — all handled on the grid, never
  on `window`, so a keystroke aimed at the filter box can never mark a lead applied. **The skip
  link is a `<button>`, not `<a href="#view">`**: the URL fragment is both this app's router and the
  channel the CLI passes the bearer token over, and `api/token.ts` reads any fragment not starting
  with `/` back as a token. Which leads render, in what order, and their counts are unchanged.
  The row shortcuts refuse **held modifiers and auto-repeat on the acting keys**: `Cmd+A` on a
  focused row is `event.key === "a"`, and a held `a` marks each successive lead applied as focus
  follows the collapsing rows down the list — every repeat lands on a different posting, so API
  idempotency is no defence. Navigation keys still repeat, because holding `j` is the point.

- **The run funnel times its own stages, because a fifth of a run was attributable to nothing.**
  Run 128 took 132.4 minutes and `scan.fetch_cost` could only price the SCAN, per provider; every
  stage after it was timed nowhere. Reconstructing the shape meant joining `board_scans`,
  `extractions`, `eligibility_evaluations` and `artifacts` on their side-effect timestamps, and even
  then **26.8 minutes — 20% of the run — landed in one block spanning two stages** with no way to
  split it. A `_StageClock` now marks eight boundaries (`scan`, `projection`, `lanes`, `death_probe`,
  `eligibility`, `liveness`, `tailor`, `finalize`) and each mark closes the stage behind it, so
  consecutive rows leave no gap and a stage that returned early or raised is charged to the mark that
  follows it rather than dropped — both the projection preflight's refusal and the `NoProfileError`
  path do exactly that, which is why a per-stage wrapper was rejected. The last mark is inside the
  `finally`, so a crashed run — the one whose breakdown is worth most — still reports where its time
  went. New `stage_durations` JSON key and `## Wall clock` markdown section. **The total is the run
  up to the artifact, and the section says so**: the funnel, the morning file and the queue sync are
  all written after the last mark, because the funnel cannot contain its own duration. `None` means
  the run was not timed (a stored artifact predating this), which is not `()`, "timed and no boundary
  reached". **`artifact_version` stays 7** — additive key, the `scan.fetch_cost` precedent.

- **The scan dispatches boards by HOST, so a wider worker pool actually pays.** `Fetcher` holds a
  per-host lock for a request's full duration and paces requests apart, so a worker that picks up a
  board whose host is already busy does no work at all. Five of the six providers serve every board
  from ONE API host; only Workday has a host per tenant (105 hosts, 114 boards, 92% of the fetch
  cost). Boards were dispatched in company-rowid order — the order they were added, in per-provider
  batches — so **the first sixteen boards of the live 345-board fleet were all `api.ashbyhq.com`**,
  leaving three of four workers idle at the start of every run and seven of eight.
  `coordinator.host_diverse` now round-robins boards across hosts before submission, keyed on the
  newly exported `politeness.host_key` — the exact key the lock uses, never the provider name, which
  would bucket Workday's 105 independent hosts as one. **No host sees a different request rate**;
  only the number of distinct hosts in flight changes, and a completed run persists exactly what it
  persisted before (`exact_quad`, the only suppressing identity, keys on `company_id`, so no
  cross-host pair can collide). Modelled against run 128's own numbers — the model reproduces its
  measured 92.8-minute board scan at 93.0 — this is 87.8 min at 4 workers and 47.4 min at 8.

- **The run funnel publishes the scan's full four-way board split, so its numbers reconcile.**
  `ScanSummary` sorts every attempted board into exactly one of `complete | partial | failed |
  unchanged`, and the artifact published three of them. Live run 126 read "346 boards attempted ·
  166 complete · 1 failed", which reads as **179 boards that silently did nothing**; they were 39
  `partial` (a detail budget truncated them) and 140 `unchanged` (HTTP 304). Run 127 hid 200 the same
  way (145 / 35 / 165 / 1). The `scan` block now carries `boards_partial` and `boards_unchanged`
  beside the two it had, plus `boards_reconciled` — `true` when the four sum to `boards_attempted`,
  and **`null`, never `true`, on a `--no-scan` run**, because `0 == 0` is not a passed check. An empty
  bucket emits a measured `0` rather than dropping its key. The Markdown line and the JSON both move.
  The four-way partition was verified against the live store (`board_scans`, `scan_kind='board'`) for
  both runs: 166+39+140+1 and 145+35+165+1, each exactly 346. **`artifact_version` stays 7** — these
  are additive keys in a block that has existed since v1, on the `scan.fetch_cost` precedent, and no
  existing value changes meaning.

- **The four-way board split now reaches the store, `/api/runs` and the web run list (D-341's other half).**
  D-341 published `complete | partial | unchanged | failed` in the funnel artifact, but the `runs` table
  kept only `boards_attempted` and `boards_complete`, so run 127 read "346 attempted / 145 complete" from
  the row with the other 200 boards unaccounted — the same fold, one layer down, inherited by `/api/runs`
  and the run list that read it. A migration (`p_runs_board_split`) adds `boards_partial`,
  `boards_unchanged` and `boards_failed` to `runs` as **nullable** columns: NULL means a run predating the
  column or one whose scan never ran, kept distinct from a measured 0 — a zero default would read every
  historic run as a scan that found zero partial boards. `finalize_run` writes the three buckets from
  `ScanSummary`, `/api/runs` serializes them, and the run list shows `partial`/`unchanged`/`failed` tiles
  beside `boards` (an em-dash for a run that never measured them). The end-to-end scan test now asserts the
  split reaches the row, not only the artifact — the wiring is where D-341's bug lived. No manifest change:
  board counts are observations about a scan, not inputs to a verdict.

- **Two spellings of one city are now one location (`IDENTITY_ALGORITHM_VERSION` p6.2 -> p6.3).**
  `normalized_locations` is a component of every location-bearing identity key, so a requisition
  published as `["Austin, TX"]` on one board and `["Austin, Texas, United States"]` on another held two
  keys and no identity kind could ever group it. Measured on the live queue tree, **47 of 70 redundant
  folders differ only in the location string**. `core.normalize.canonical_location` now folds each
  comma-separated segment against a closed, versioned catalog (`rank/location_data`, which is also now
  the single source for both state sets): a US state name becomes its USPS abbreviation but **never in
  the first segment**, so `New York, NY` does not become `ny, ny`; a trailing `United States` is dropped
  only beside a US state, so `Remote, US` keeps its country; a trailing office segment is dropped; a
  parenthetical site code is dropped only from a state segment, so `Remote (IND)` — the D-264 country
  signal — survives; and `X County, ST` becomes `X, ST` only with a US state after it.
  `canonical_locations` then de-duplicates the list and drops an office alias whose city the list
  already names. Out-of-catalog segments are left alone: `London, United Kingdom`, `Toronto, ON, Canada`
  and `Bengaluru, Karnataka, India` pass through unchanged, so a non-US tenant's locations are not
  mangled. **Nothing merges two different places.** Cross-city (PayPal's San Jose / Austin / Scottsdale
  / New York), subset/superset (Twitch's Seattle+SF against SF alone) and US-against-Canada (Affirm) are
  owner policy calls, are untouched, and each has a test asserting it does not fold; five more tests
  pin the guards by mutation. On the live corpus of 84,821 open postings the suppressing `exact_quad`
  kind gains 31 groups and 48 suppressions (2.43% -> 2.49% of open), `company_title_location` goes
  3,451 -> 3,535 groups and `cross_host` 3,899 -> 3,987; every newly merged suppressing group is one
  requisition published per office by Brex or Anduril. **A version bump degrades to "no identities yet"
  — suppression off, `unique` None — until `boardwatch identities backfill` re-runs.** Measured against
  a copy of the live store: **83 s, 423,706 rows written, 1.3 GB peak RSS**, and `identities verify`
  clean afterwards. The dead p6.2 generation (476,277 rows) is not reaped; the table has no reaper.

- **CI shards the test suite across jobs, and one aggregate check replaces six required contexts
  (D-334).** A pull request took 30-42 minutes, and per-step timings showed the whole of it is a single
  step: gitleaks, generalization, perf and web bundle total about twenty seconds between them, while
  `pytest -n auto` ran 1764s / 2480s / 1903s on 3.11 / 3.12 / 3.13. A GitHub standard runner has four
  vCPU; the same suite takes 6m24s on a ten-core Mac. There is no hot spot to remove — the slowest
  single test is 1.5% of total CPU and the top 25 are 9% — so the suite is now split N ways per Python
  version by SHA-256 of the node id, chosen over a durations file because a flat profile balances
  without one (8 shards measured 996-1094 tests, a 9.5% spread). Every shard emits a manifest and
  `tools/shard_audit.py` proves the shards are a genuine partition: exactly N manifests per version,
  identical collection digests, pairwise disjoint, union equal to the whole. Coverage is combined per
  Python version and the 85% threshold applied three times, preserving what the pre-shard matrix
  guaranteed rather than collapsing it into one easier union number. Branch protection now names the
  single `ci` job, which derives what should have run from the event rather than from job results,
  because GitHub counts a skipped required check as a passing one. macOS and Windows stay unsharded and
  keep their own type-checking, so this change targets pull-request latency specifically; pushes and
  the nightly are still bounded by those full-suite jobs. Measured on the first sharded run: 30-42 minutes becomes 10.6, a 3.3x improvement, and the shard count settled at 4 rather than 8 because wall clock turns out to be bounded by the concurrent-job ceiling rather than by how finely the suite is sliced — so 8 shards paid double the per-job setup for the same ten minutes.


### Fixed

- **A component that fails to draw now costs a card, not the whole page.** The queue viewer had no
  error boundary anywhere, so any error thrown while rendering unmounted the entire React tree and
  left a blank page — which is how one undefined field blanked the queue. Boundaries now sit at four
  scopes, each keeping a different thing usable: the app root, the route switch (so the tabs still
  work and the other view is one click away), the review lane (so a failure there cannot cost the
  apply queue above it), and the detail pane (so a failure there cannot cost the queue beside it).
  Each card says what failed, what still works, and offers one named recovery action; the technical
  detail is there but folded, and focus moves to the recovery button only when the failure destroyed
  the element that had it. The detail pane's action closes the lead rather than redrawing it, because
  below the side-by-side breakpoint a lead that stays selected holds the queue behind it inert.

- **The viewer no longer breaks when it is newer than the server it is talking to.** The page's
  JavaScript is served from disk while the data comes from the copy the server loaded at startup, so
  a long-running viewer can read a field its own API never learned to send. An absent field arrived
  as `undefined`, the guards tested only for `null`, and the read threw. The queue's own lane list
  is the worst case and the one no error boundary can catch — it is read inside a promise, so the
  page showed a load failure blaming the connection and advising a reload that would not have
  helped, and on the background refresh it failed silently and stopped reporting new leads
  altogether for as long as the page stayed open. The lane list is now normalised once where the
  response arrives, the shared display helpers and the verdict chip accept an absent value the same
  way the review badge already did, and the runs page tolerates funnel files written before the
  fields it reads existed.

- **The experience-years floor patterns now read possessive and qualified phrasings.** The floor
  patterns anchored on the literal word `experience` immediately after an optional whitelisted
  adjective, so three common phrasings never registered as floors at all: the possessive
  `5 years' experience`, where the word-boundary after `years` fell before the apostrophe; a
  qualifier the whitelist did not carry, such as `demonstrated` or `proven`; and such a qualifier
  ahead of a multi-word scope. Across the open corpus, 11,379 postings carried a four-year-or-more
  mention that no pattern matched, of which roughly 4,571 were real floors — and roughly 4,599 were
  ages rather than experience, which is why the obvious widening had been held back. An age guard now
  makes `N years of age` structurally incapable of reading as an experience floor. The published
  default for this family is unchanged, so on a stock configuration this changes what is *detected*
  and no verdicts; it tightens verdicts only where the family has been configured to block.

- **Focus is now contained in the queue detail sheet at the tier where it is a modal.** Below 64rem
  the detail pane is a full-screen sheet, and focus could leave it: `Shift+Tab` reached a row of the
  triage grid *behind* the opaque sheet, after which the single-key mark-applied shortcut acted on a
  row the reader could not see. The subtrees the sheet covers are now `inert` at that tier only — at
  or above 64rem the pane is a column beside a list that must stay reachable, so nothing is inerted
  there. The undo toast is deliberately excluded: it draws above the sheet and holds the only route
  back from a mark-applied.

- **A board slug differing only in case no longer becomes a second company row (D-339).**
  `companies` enforces `UNIQUE(provider, slug)` and SQLite compares that case-sensitively, so
  `ashby:Lightfield` and `ashby:lightfield` were two watched rows for one board — identical open
  postings, identical provider posting ids, URLs differing only in the slug's case. It was fetched
  twice every run and contributed redundant postings that no identity kind can suppress, because
  every suppressing key is scoped by `company_id`. Two comparisons had to be wrong for the row to
  appear: the lane's is-new check read the variant as new, which spent one of the run's
  new-company slots as well as letting it through, and the insert's conflict target then failed to
  converge. Both now resolve through one helper that returns the slug the store already holds, so
  no existing slug is rewritten and no live URL moves; the fold is done in SQL on both sides,
  because a Python-side `.lower()` disagrees above ASCII and would fail toward two rows.
  `companies add` and `companies import` report the resolution instead of silently doing nothing.
  Workday site slugs stay case-significant (`NVIDIAExternalCareerSite` and `external_experienced`
  are both real) and are unaffected, since the guard never rewrites a slug.

- **`companies remove` and the `--company` filter now case-resolve the way `add` does (D-339 loose ends).**
  D-339 folded slug case for the store calls behind `add`/`import`/`remove` but left two edges. The
  `--company` scan filter (`get_watched_companies`) still compared the slug case-sensitively, so
  `--company KAYAK` skipped a board stored as `kayak`; the comparison now folds case in SQL the way
  `stored_slug` does, and needs no `--provider` to do it. And `companies remove` unwatched the correct
  row yet echoed the slug the operator typed, so `remove ashby:KAYAK` printed `Unwatched ashby:KAYAK.`;
  it now reports the stored spelling (`ashby:kayak`), matching what `add` and `import` already do. The
  fold is SQL-side on both, because a Python `.lower()` disagrees above ASCII.

- **A degree requirement naming several fields produced no row at all (D-328).** The three
  `*_in_field_required` patterns bounded the span between "in" and the requirement marker at 60
  characters. That was assumed to truncate the captured field; it does not — the pattern fails to
  match, so *"A Bachelor's degree in Computer Science, Computer Engineering, Mathematics, or a related
  discipline is required."* yielded **zero rows** and the posting read as though it named no degree
  requirement. The bound is now 160, chosen by measuring the live corpus (25 in-field rows at 60, 29
  at 160, 29 at 240, 30 at 400, none lost at any width), and it stays **closed** rather than becoming
  unbounded, because `[^.;:]` and sentence scope are the outer fence and the count is the inner one.
  About **248** open postings gain a degree row they never had; none loses one. This buys no
  additional `ineligible` verdicts — it is an honesty fix, so that a stated requirement produces an
  abstain instead of silence.

### Added

- **The LinkedIn lane paginates its search, behind `lane_search_pages` (default `1`).** The lane
  converts better per posting than any whole-board scan — 19 leads from 213 open postings — because it
  is facet-filtered at the source against the user's target titles, but it surfaced only ~63-69
  candidates a run. The body budget was not the constraint and the funnel says so: `body_fetched` was
  49 and 53 against a `lane_posting_budget` of 60 on runs 126 and 127, under budget every time. One
  search page per facet was. `start` had been probed as a working ITEM offset (10 cards to a page) and
  deliberately left unimplemented on the reasoning that a facet already lists more cards than the body
  budget can fetch; those two runs falsify it, and the module's comment now says so rather than
  narrating a rationale the code no longer follows. **The ceiling is a setting defaulting to 1, which
  is byte-for-byte the single-page behaviour that shipped** — page 0 is the URL unchanged, never
  `&start=0` — so no existing user's request volume or request shape moves and the owner opts in
  locally. **The correctness trap is that under paging an empty page becomes a legitimate outcome:**
  `card_nodes` raises `SearchPageError` on a page with no cards *by design*, so paging naively would
  make every facet shorter than the ceiling look like a structural outage. Page 1 empty still raises,
  unweakened; page N>1 empty is the end of that facet's results and ends it cleanly. A full page adding
  no new posting id ends it too — the offset-wrap tail `providers/workday.py` guards for the same
  reason. Per-facet page counts are reported in the funnel's `lanes` block (additive key, no
  `artifact_version` bump), because a facet that ran out at page 2 and one truncated at a 5-page
  ceiling produce the same posting count and only the second is lost reach. `location=` and `f_WT=2`
  are still never sent, at any offset. hiring.cafe is untouched: it has no recorded paging parameter
  and its `?page=` form is disallowed by `robots.txt`, so its one-page ceiling is structural.

- **`boardwatch track import` fills the funnel from a history kept in another tool.** The ranker has
  always suppressed a job carrying a submitted application — `applied_job_ids` feeds `hidden_applied`
  in `top`, and `delivered_unapplied` keeps the same job out of the delivery queue — but on a store
  whose user applied through something else that machinery is starved: `applications` sits at **0
  rows**, so a role applied to months ago re-surfaces and is re-tailored on every run. Measured on a
  real 64-row history against a 95,897-posting store, **21 of the 64 (32.8%) were still open there**
  and would have re-surfaced. The importer takes a deliberately generic file, CSV or JSONL with the
  columns `company`, `title`, `url`, `applied_at`, `status`, so it is not tied to any particular
  source tool. Rows match on **url** first, folded through the same `normalize_url` the duplicate
  suppressor uses, and on **(company, title)** only behind `--allow-title-match`, because one title
  at a large employer can cover several requisitions; the key that matched is recorded per row.
  **No row is dropped silently** — each lands in exactly one of `matched`, `already_present`,
  `unmatched` or `malformed`, all four counts are printed even at zero, and `--report` writes a
  per-row JSONL audit. Importing the same file twice writes nothing, bumps no `attempt_no` and
  appends no event, and a job that was **withdrawn** is left withdrawn rather than silently
  re-applied. A role boardwatch never saw cannot be recorded at all, since `applications.job_id` is
  a foreign key to `jobs`; that is why `unmatched` is a reported bucket rather than an error.
- **The funnel's `dedup` stage is instrumented.** It reported `entered: null, advanced: null` and
  the note *"this stage counts nothing"* for the whole of P0-P6, so no run could show from its own
  artifact whether dedup was working; the only dedup numbers a run emitted were the ranker's
  `hidden_duplicate` and the per-source `unique` column. The stage now carries the corpus that
  entered grouping, what survived, and a named `suppressed_duplicate` drop, plus a `dedup_detail`
  block beside the drop — `suppressing_groups`/`suppressing_redundant`, and one
  `candidate_redundant_*` per audit-only kind. Those bounds are never summed into the drop
  (D-327): `company_title_location` spans genuinely different jobs. Not-measured stays
  distinguishable from zero, and the two reasons for it — the sweep did not run, or the backfill is
  incomplete — stay distinguishable from each other. On the live corpus the stage reads 84,821 in,
  82,757 out, 2,064 suppressed across 1,472 groups, with bounds of 5,268 / 5,775 / 12,571.
  `exact_provider` is absent rather than reported as 0, because a UNIQUE constraint makes its
  collision count structurally zero. **`artifact_version` stays 7**: no new top-level section, and
  no existing value changes meaning — a nullable stage field going from `null` to a number is the
  transition it exists to make, and `SourceOutcome.unique` set that precedent when P6 landed.

- **The funnel's corpus-wide duplicate sweep stops materialising every posting body.** The sweep
  called `load_identity_inputs(conn)` with no id list and pulled 503 MB of `body_text` for a
  1.33 GB peak RSS. `resolve_duplicates` drops every identity group with fewer than two members, so
  it now loads bodies only for the postings that share a suppressing key with another open posting
  — 3,536 of 84,821 (4.2%) on the live corpus. Measured on a scratch copy: peak RSS **1356 MiB ->
  109 MiB**, CPU 3.64 s -> 1.28 s, and the suppression set is byte-identical (2,064 suppressions,
  same survivors). The candidate set is driven by `SUPPRESSING_KINDS`, never by a literal
  `exact_quad`, so enabling a second suppressing kind cannot silently narrow it.

- **`boardwatch identities reap` removes the identity rows a version bump leaves behind.**
  `write_identities` only rewrites a posting's rows at the CURRENT
  `IDENTITY_ALGORITHM_VERSION`, so a bump writes a whole new generation beside the old one and
  nothing ever removed the old one. `posting_identities` held **476,277 rows** on 2026-08-28,
  about five per posting, and every reader filters to the current version. The `p6.2 → p6.3`
  bump in this same release retires every one of them, and without a reaper the next backfill
  would take the table past 950k rows with half of it permanently unread. Reaping the p6.2
  generation on a
  scratch copy of the live store deleted **476,277 rows across 95,336 postings in 4.5 s** and
  returned **121 MiB** to SQLite's free list (the file itself shrinks only under a separate
  `VACUUM`, which the command deliberately does not run). It reports by default and deletes only
  under `--apply`, and nothing else in the CLI reaps as a side effect. **Only retired generations
  are in scope.** 11.0% of the table sits on closed postings and reaping that looks like the
  bigger win, but postings reopen — run 127 alone reopened 18 — and `identities_complete()` gates
  suppression over all open postings, so a reopened posting with no identity rows would silently
  disarm dedup store-wide until the next backfill.

- **The delivery queue splits into an APPLY lane and a REVIEW lane (D-332).** The queue root is a
  *blind-apply* surface — you open a folder, read the rendered PDF and apply — but 82% of it was
  `uncertain` (314 of 383 leads, only 27 `eligible`), and a lead is `uncertain` precisely *because* a
  ranker gate failed open on it: the hard US gate passes an unplaceable location by the visa ruling,
  and the role gate passes an unrecognised title. Live examples that reached the queue: an Allstate
  "Field Auto Appraiser", a Humana care-support role, an ITW "Recycle Operator", a Hyatt "Front Office
  Agent". A fourth drain `_review` now sits beside `_ineligible`, and
  `delivery/review_gate.lane(verdict, locations, title)` is the single definition of the split, called
  by both writers. `eligible` promotes; `uncertain` (and an unevaluated `None`) reaches the apply lane
  only when it is **confirmed US and confirmed software**. Location fails *open* on `unknown` — a bare
  `"Remote"` stays appliable, and only a confirmed non-US lead is demoted — while a title carrying no
  positive software signal is held. `_review` is a managed second location, not an exclusion: leads are
  created there and drawn back up if their class changes. Measured on the live store, roughly one lead
  in three was in the blind-apply surface without a software title. No engine change.

- **The queue page follows the same split, with its own Review section.** `GET /api/queue` returns
  `rows` (the apply lane, exactly the queue root) and `review` (exactly `_review`), split by calling
  the same `review_gate.lane` rather than re-deriving it, so the page and the folder tree cannot
  disagree about a lead. The Review section is collapsed by default with its count always visible, and
  each lane ranks and sorts independently. This matters more than "the page was unfiltered": the
  `off_target` badge is `not_swe` **only, never `uncertain`** — deliberately, since badging an abstain
  would assert a decision the gate declined to make — so most review leads previously rendered with
  **no marker at all** and were indistinguishable from blindly-appliable ones. A review lead is listed,
  never hidden; only `ineligible` is excluded-and-counted. The status band gains a `review` cell, so
  `in queue`, `review` and `ineligible` account for every delivered lead.

- **A near-miss experience-years bar abstains instead of rejecting (D-333).** `experience_years` drove
  about 89% of the reject pile against a profile declaring **one** year, and 8,745 postings were
  rejected for needing three years or fewer. That population is invisible by construction: the reject
  pile is never inspected and boardwatch never applies, so a wrong `unmet` there has no outcome loop
  that could contradict it — and internships, co-ops and course projects routinely clear an
  early-career bar that a single declared integer cannot represent. A `required` bar at or under the
  new `experience_years.near_miss_years_ceiling` (3) now resolves `unknown` rather than `unmet`, so the
  lead becomes `uncertain` and reaches the review lane instead of being dropped. It **cannot** produce
  a new `eligible`: `unknown` is caught by the blocking roll-up before the `eligible` fall-through, so
  the worst it can do is move `ineligible` to `uncertain`. Measured on a full re-evaluation of 83,718
  rows: 5,980 of 36,141 `ineligible` leads move (16.5%), every one of them a two- or three-year bar,
  and none becomes `eligible`. A stated *preference* is untouched — the band applies only to rows that
  can actually block. **Moves `engine_version`**, so the next run re-evaluates the corpus once.

- **The run funnel records FETCH wall clock per provider (D-330).** Run cost could not be attributed
  from the record, because every existing signal was wrong in a different way:
  `board_scans.started_at → finished_at` times the *apply* (26.5 s of a 3,286 s run),
  `wall_clock / boards` averages a population where one provider is 20× the others (it mispredicted a
  346-board run by 24 minutes), and the gap between scan completions sums to wall clock by construction
  because the scan fetches through a `scan_workers`-wide pool. The fetch is now timed at the single seam
  all six providers pass through, accumulated per provider, and reported in the funnel's `scan` block
  costliest-first. A failed fetch is charged for the seconds it burned; an untimed board is never folded
  in as zero; and "not measured" stays distinct from "measured, nothing timed". No `artifact_version`
  bump, no schema change, no migration.

- **The run funnel now says where each lead is, and how the hard US gate read it — artifact v7 (D-323).**
  The US-only location gate is the one gate whose failure is a lead you cannot legally take, and until now a
  `leads[]` row in `funnel-<id>.json` carried no location at all, so the gate left no trace in the record it
  produces: every "all leads US-located" claim came from a by-hand database read and could not be reproduced
  from the artifact afterwards. Each lead now carries `locations` (what the posting itself named — `null`,
  never `[]`, when it named no place) and `location_class` (`us` / `non_us` / `unknown`, computed by the same
  classifier the ranker vetoes with, never stored separately from the locations it describes). The manifest
  carries `location_filter_mode` in plain text, because the verdicts are unreadable without it: the mode is
  `soft` by default, and in `soft` the hard gate never ran. The Markdown half names the classifier and the
  number of leads it was evaluated over, so the claim stays quotable later. **`artifact_version` moves 6 → 7**;
  no consumer validates the number, and `boardwatch verify` reads named keys out of the file as before.

- **Two eligibility rules that could never fire now decide.** Both abstained unconditionally because the
  fact they needed did not exist, which the keystone treats as a monitoring failure rather than
  conservatism.
  - **Obtain-after-hire clearance eligibility.** `clearable_required` ("must be able to obtain a Secret
    clearance") fired on ~118 rows per run and returned `unknown` every time. `security_clearance` gains an
    `obtainable` bool, declared in the catalog so `boardwatch eligibility facts set
    security_clearance.obtainable no` and the `init` wizard both reach it with no new call site. The bit is
    orthogonal to what you hold: an F-1 holder holds nothing and can obtain nothing, and a Secret holder may
    still be barred from an upgrade, so inferring either direction from the held clearance inverts the
    verdict both ways. Undeclared still abstains.
  - **Field of study.** `degree_required_with_field` ("a Bachelor's degree in Computer Science") is the
    commonest degree sentence there is and abstained on every satisfied rank — ~405 rows per run. `Facts`
    gains `field_of_study`; set it with `boardwatch eligibility facts set field_of_study computer_science`.
    The vocabulary, the reviewed relatedness partition and the phrasings by which a posting opens its list
    are versioned catalog data in `rules.yaml`, overridable per user; a value outside the catalog, on either
    side, abstains rather than becoming a new bucket. `met` needs an exact match, or **both** a reviewed
    relation and the posting's own escape ("or a related field") — "must have a Computer Science degree"
    means Computer Science. `unmet` is reached only when the posting names a closed set of catalogued fields
    and offers no escape.

  **Both change `engine_version`, so stored eligibility evaluations re-evaluate on the next run.**

### Fixed

- **A posting no board scan enumerates can now be closed — but only by a measured death (D-325).** A posting
  under an unwatched company was open for ever: the only thing that closes a posting is absence from two
  complete board fetches, and nothing ever fetches those boards. A search-based source re-finds a posting by
  searching, so a posting that stops appearing has not been proved gone. Each run now re-fetches a bounded
  slice of those postings and closes one only when its own URL answers 404 or 410 — twice, on different runs,
  with no redirect in between. A timeout, a 403, a 5xx, or a 404 that arrived after a redirect all count for
  nothing. Any sighting of the posting on a board, or any successful re-fetch, wipes the slate.

  **Read the numbers before trusting it.** Against 60 postings already proved closed, this finds 4 — **6.7%**
  (95% CI 2.6%–15.9%). None of the 37 closed Workday requisitions in that set were caught, because a closed
  Workday requisition still answers normally. It produced no false deaths across 90 live postings. So it
  rarely fires and it rarely lies, and **a run reporting zero closed is the expected result, not evidence the
  backlog is healthy**. The run funnel gains a `death_probe` section that reports what was due, what was
  probed, what the budget refused, and what had no URL to ask, so a check that quietly stops working shows up
  as a number rather than as silence. Tune with `boardwatch config set death_probe_budget` (default 50 probes
  per run; `0` turns it off) and `death_probe_ttl_hours` (default 24).

### Fixed

- **A lead the eligibility gate rejects no longer sits in the review queue (D-321).** `delivered_unapplied`
  attached each lead's current verdict but never filtered on it, and the status band reported `eligible` and
  `uncertain` with no cell for `ineligible` — so a rejected lead was an unexplained remainder between
  `in queue` and the two counted buckets. Rejected leads now drain to a third directory, `_ineligible`,
  alongside `_applied` and `_skipped`, and the count is reported. Nothing is deleted; a folder returns to the
  queue if its verdict stops governing. An application or a skip still wins, because each is a statement you
  made and a rule tightening later must not sweep that record away.

### Fixed

- **A years-of-experience requirement can now make a posting ineligible (D-319).** Two independent reasons it
  could not before. `experience_years` ships with `default_policy: preference`, and only a `blocker` family
  can yield `ineligible`, so a correctly-detected and correctly-resolved "Minimum of 12 years of experience"
  was written into the evidence chain and then discarded — set it with
  `boardwatch eligibility policy set experience_years blocker`. And `scoped_years_minimum`, the family's
  highest-volume pattern, abstained unconditionally on the grounds that no per-skill durations are stored.
  One direction of a scoped requirement needs no per-skill data: **a duration scoped to a single skill cannot
  exceed the career it sits inside**, so `total < need` now resolves `unmet`. The other direction still
  abstains — `total >= need` says nothing about that skill, and a wrong `met` is the worst verdict this design
  can produce. Measured over a 588-posting delivered set, 142 of which state a minimum of five or more years:
  101 of those 142 are now blocked. **Changes `engine_version`, so stored eligibility evaluations
  re-evaluate on the next run.**

- **An activity gerund is read as a years floor (D-320).** `5+ years building and deploying web applications`
  names no "experience" and was invisible to every pattern in the family; 37 of the 142 postings above
  produced no requirement row at all. Added as `scoped_years_activity`, with its own `activity_years_minimum`
  vocabulary value so it cannot collide with the total/range/scoped exclusive group. Aggregator summaries
  phrase floors this way, so this mostly affects lane-sourced postings.

- **The company's own tenure is no longer read as a requirement (D-320).** `We bring 30 years of experience
  to every engagement.` resolved `unmet` against a one-year profile: the company-side subject suppressor
  required a noun (`our team has`), which a bare `we` subject escapes.

## [0.5.0] - 2026-08-24

Catches the published package up to `main` (608 commits since 0.3.0). The headline change for users
is a clearer first run: the beginner path is wired end to end and the README leads with a single
golden path, with operator detail moved into linked guides.

### Notes

- Upgrading from 0.3.0 applies a one-time store migration automatically on the first `scan` or `run`
  (see the Migration section below). No manual step is required.

### Added

- **A clearer first run (onboarding).** Each step now points to the next — `scan`, `top`, `show`, and
  `run` print a `→ do this next` hint, and a new `boardwatch guide` command shows the whole journey
  (`init → scan → top → show → track`) on one screen. The README now leads with one golden path
  (`install → init → scan → top`) instead of a platform wall, and scheduling, unattended runs, résumé
  tailoring, and per-provider limits moved into linked `docs/` guides.

- **Validator TTL forcing periodic board revalidation (D-298).** `get_validators` drops a cached
  conditional-request validator (ETag / Last-Modified) older than the new `validator_max_age_hours` setting
  (default 24), so the next scan refetches the board unconditionally instead of trusting a possibly-stale
  upstream validator forever — a permanently-stale ETag can no longer silently freeze a board's postings
  (`304 → unchanged` with no self-healing). Provider-agnostic; classified out of `config_hash` (throughput,
  not decision-relevant, so it does not restamp `policy_version`); `max_age=None` preserves prior behaviour.

- **Greenhouse `_meta_total` NaN/Infinity guard test.** Pins the `except (ValueError, OverflowError)` branch
  that keeps a non-finite `meta.total` from failing the whole board (`json.loads` accepts `NaN`/`Infinity`).

- **LinkedIn guest discovery lane (`lanes/linkedin.py`), registered but off by default (D-297).** The last of
  the approved discovery lanes. A posting source keyed on the company **slug** — LinkedIn exposes no external
  apply URL, so convergence with an ATS copy of the same role is left to the P6 dedup identity, not a link.
  Two unauthenticated GETs (guest search, then one body per posting), a browser UA, no key/cookie/app
  impersonation, and **nothing captured is committed**. It ships reachable but NOT enabled (`linkedin` is not
  in `lanes_enabled`) and has never run against the live service; the card selectors are reconstructed from
  the recorded probe and want live verification before the lane is armed.

- **`boardwatch companies discover` — company discovery from the two public GitHub new-grad lists, behind a
  human review step.** boardwatch watches 135 boards; these two files name **926** and **897 of them are
  new**. Two unauthenticated GETs, no token and no key, and **nothing captured is committed**.

  It is company discovery and not a posting source, which is a measurement rather than a preference: no
  field in any of the 34,958 records carries a job description, and `parse_posting_target` covers four of
  the six providers where `parse_board_target` covers all six. So each record's `url` is resolved to a
  `(provider, slug)` **board** and the posting is thrown away. Of 19,955 records read: 16,179 inactive,
  1,820 on a host no provider here serves, 1,956 matched. Every record lands in exactly one bucket.

  **It writes nothing to the store.** It emits a registry-format candidate file; `companies import`,
  unchanged, does the watched-write on the file a human read. That is deliberate — a bad slug becomes a
  permanently failing board and there is no quarantine or backoff for one, and this corpus contains a live
  example: an `embed/job_app?token=` URL that parses to the board `embed`. Every candidate therefore carries
  the evidence URL it was parsed from, the employer name, and how many records named it.

  Boards ramp cheapest-first in three cost tiers — the four inline-body providers, then workday, then
  smartrecruiters — and round-robin inside a tier. `Fetcher` holds a per-host lock for each request's full
  duration and five of the six providers serve every board from one host, so ten boards on one provider are
  ten serial requests where ten across four providers are not. The cap is
  `lane_new_companies_per_run`, so there is one knob rather than two, and `companies.source` stays `'user'`
  — no migration.

- **The first discovery lane: hiring.cafe, behind a per-run company cap, off by default.** boardwatch can now
  reach employers no ATS provider covers. Over a 160-hit sample, 8 (5.0%) sit on one of the six supported
  providers and 152 do not — that 95% is the whole point of the lane.

  Two requests, and no others: one GET of the server-rendered search page (`__NEXT_DATA__` →
  `props.pageProps.ssrHits`), then one GET per posting for its JD body. No key, no cookie, no TLS bypass, no
  app impersonation. Paging is deliberately absent: the response records `ssrPage` and `ssrIsLastPage`, but
  the parameter that turns a page is not, and inventing one would fabricate a request contract.

  `objectID` is treated as an opaque key. It looks like `{source}___{board_token}___{id}` and is exactly that
  for 128 of 160 hits, so a round-trip test over a typical sample passes — while a `___` split mis-attributes
  36 of 160 (22.5%) in three distinct ways. The explicit `source` and `board_token` fields are read instead.

  A lane is not a seventh provider and its companies are stored **unwatched**, so they never enter the scan
  or coverage corpus, and their postings still reach the shortlist. Enabling it is `lanes_enabled`; it ships
  empty, because Gate P3 counts consecutive clean unattended runs.

- **`companies.source` admits `'lane'`, and `board_scans.scan_kind` distinguishes a lane's scan row from a
  board's.** Without the second, a lane touching a board already scanned this run made that company appear
  twice in the coverage report — once `measured`, once `enumerated_only` — inflating `corpus_boards` and
  every bucket count.

### Fixed

- **The test suite could migrate the real database.** A CLI test invoked without `--data-dir`, while only
  `BOARDWATCH_CONFIG_DIR` was set, let `load_settings()` fall through to the default data directory and run
  `alembic upgrade head` against the user's live store. On a branch adding a migration that stamps the store
  with a revision the released code does not have, and the next unattended run then fails to start. An
  autouse fixture now pins `BOARDWATCH_DATA_DIR` to a scratch directory for every test. This closes the
  environment-variable route; a `data_dir` key in a real `config.toml` still outranks it.


- **Lane groundwork — the persistence and attribution guarantees a JD-acquisition lane needs.** A lane is
  not a seventh ATS provider. It returns the same `BoardSnapshot` a provider returns and goes through the
  existing `apply_board`, so it inherits every persistence invariant instead of restating them.

  `lane_snapshot()` is the only sanctioned way to build one, and it makes `status="complete"`
  **unexpressible**. That is load-bearing rather than cautious: a snapshot may carry an empty `complete`,
  which marks every open posting of that company missing and closes them after two consecutive scans. A lane
  never enumerates a whole board, so it can never make that claim truthfully. `listed_ids` stays empty and
  the four board-coverage fields stay `None` for the same reason — a ratio that cannot fail is worse than no
  ratio.

- **A per-run cap on the companies a lane may add**, defaulting to 10, with every refusal recorded **by
  name**. Adding a company's whole board is breadth, and breadth multiplies whatever sits downstream of it.
  A company dropped silently is indistinguishable from one the lane never saw, and that difference is the
  entire diagnostic value.

- **Per-source stub attribution.** A stub is an open posting with an empty JD body. The existing count was
  corpus-wide with no source filter, so a new source's stub rate would move the global number with nothing
  naming the source. `SourceOutcome` now carries a `stubs` field that is instrumented — it reports a measured
  0 rather than `None` or an absent key, because an absent key would read as "not measured". Note that the
  field does not yet reach either persisted artifact; surfacing it needs a funnel schema-version bump that is
  deliberately deferred.

- **`parse_posting_target` — recovering the posting reference a board URL carries.** Board-target parsing
  returned `(provider, slug)` and discarded the rest of the path, so nothing could turn a posting link back
  into a posting identifier. The new helper reuses that parsing for the provider and slug, then extracts the
  reference, and raises a typed `UnresolvablePostingURL` where a provider's public-URL contract is not
  evidenced in this repository rather than guessing one.

  Two providers refuse today, and both refusals are deliberate. Workday's detail endpoint needs an
  `externalPath` path-string rather than an id, and the mapping from its public URL form is verified nowhere
  here. SmartRecruiters refuses because its pinned fixture's URL values are synthetic by the fixture's own
  documentation and happen to mirror a constructed fallback, while its real posting URLs combine the id and
  a title slug in a single path segment — so the obvious extraction would silently return the wrong
  reference for the one provider where it would actually be used. Each needs a single live probe to close.

- **`boardwatch identities leakage` — Gate P6's duplicate-leakage clause becomes readable.** The gate
  asks for duplicate leakage over 7 days at or under 5%; nothing could report it. The new command
  answers it over a configurable window (`--days`, default 7, plus `--json`).

  Three choices make the number mean what the gate asks. Only an **`exact_quad`** identity
  (company + title + location + body) counts as a duplicate, matching `SUPPRESSING_KINDS` — a shared
  body hash alone spans genuinely different titles and locations. Leakage is counted over **jobs that
  reached leads**, not over the corpus, because a corpus-wide suppression rate answers a different
  question. And the unit is the **job**, not the posting, since a correct `regroup` merge would
  otherwise read as a leak.

  A posting with no body is deliberately withheld an `exact_quad` identity, so it cannot be judged
  here. Those jobs are reported in their own `unidentified` bucket, never folded into either
  neighbour and never counted in the denominator; with nothing measurable the command prints "not
  measurable" rather than 0%.

- **Board coverage is reported by an unattended run, not only by a command.** The instrument below
  persisted its four columns and said nothing: seeing coverage meant typing `boardwatch coverage`.
  A scheduled run now reports it in the two artifacts it already writes — a `board_coverage`
  section in the funnel (per-board table, worst coverage first) and a `## Discovery reach` block in
  the morning digest — plus one line on stdout, which is what a launchd run leaves in its log.

  The report is loaded **once per run** and the same object is rendered into both artifacts. This
  is deliberate rather than incidental: `held` is a live count of open postings with no run
  dimension, so loading it per artifact would let one run's two files disagree about its own
  coverage. Both carry the caveat in JSON as well as prose — stated totals are the run's, `held` is
  as of the moment the artifact was written, and the section is not a frozen historical record.

  The section is named `board_coverage`, and the morning block is titled *Discovery reach*, because
  `coverage` in both artifacts already means résumé keyword coverage. `boardwatch coverage --json`
  now emits through the same serializer as the artifacts, so the command and the files cannot
  describe one number two different ways.

  A coverage failure costs the section and never the artifact: both writers swallow any exception
  and write nothing at all, so the load is guarded separately and the section reports
  "not measured this run" instead of taking the funnel down with it.

- **Per-board discovery coverage — `boardwatch coverage`.** Every scan already asked each board how
  many postings it holds, and threw the answer away. Now it is persisted and reported, so a day where
  44 of 135 boards finished no longer looks identical to a day where 89 did.

  Coverage is published as a **partition, never a single number**, following the same rule that makes
  `ABSTAIN` load-bearing in the eligibility engine: a board whose total cannot be obtained gets its own
  bucket and is never folded into a neighbour. The seven are `measured` (a trustworthy board-stated
  total exists), `enumerated_only` (the API states no total — lever, ashby, workable — so no ratio is
  published, because `held / held` is 1.0 by arithmetic on every run forever), `censored` (Workday
  reports its cap), `dark` (the board failed — undefined, not zero), `stale` (the board answered 304),
  `unscanned` (watched, but no scan row for this run), and `unreadable` (a row that could not be
  classified, isolated so one bad board cannot hide the other 134). The global figure is a weighted
  roll-up over `measured` only, printed beside the counts of the other six, and it renders as
  "not measurable" rather than 0% or 100% when nothing can be measured.

  Three new nullable columns on `board_scans` plus a typed censor flag carry it
  (`board_reported_total`, `board_enumerated`, `detail_deferred`, `board_total_censored`), all
  populated from values the providers already computed. **The scan makes no additional HTTP
  requests.** The deferred-posting count in particular is now a typed column rather than a number
  embedded in an English error string.

- **Workday's real board size, past its own 2,000 cap.** `total` is censored at exactly 2000; the
  response's facet dimensions are aggregated by a different path and are not. Measured on a live
  135-board scan: Target reports 2,000 and actually holds **12,097**; Citi 4,573; NVIDIA 2,656. The
  known-positive control passed on four uncensored boards, where the facet sum equals `total` exactly.
  When no facet dimension is usable the provider reports no total at all rather than the censor value,
  so a floor is never mistaken for a measurement.

### Changed

- **Funnel `artifact_version` 5 → 6** and **morning `artifact_version` 1 → 2**, both for the new
  `board_coverage` / *Discovery reach* section. Additive: no existing key changed meaning, and
  `boardwatch verify` reads named keys and tolerates unknown ones.

- **`DEFAULT_TOP_N` raised from 8 to 40.** The cap is a display limit, not a filter: run 67 discarded
  **3,502 postings that had cleared every gate** — eligibility, title, role, seniority, location and
  dedup — to show eight. Everything beyond the cap was already counted into `capped_by_top_n` and
  stayed `status='open'`, so nothing was ever deleted by it and nothing is un-deleted now. This also
  unblocks P7's own gate, which cannot run while per-source yield is `8/26,997` with the numerator
  fixed by construction.

- **The canonical career-profile bundle — `boardwatch profile-bundle`.** A private, revisioned,
  filesystem-only store for the career facts a résumé is assembled from. It lives at
  `{config_dir}/career-profile`, with `--bundle PATH` overriding that; it is machine-local, is not a
  `Settings` field, and does not participate in lead selection.

  These seventeen commands are reachable from a terminal — `init`, `checkout`, `rebase-draft`,
  `validate`, `inspect`, `inventory`, `conflicts`, `migrate`, `import`, `extract`,
  `promote-candidates`, `add-evidence`, `resolve-conflict`, `approve`, `approve-projection`,
  `project`, `promote` — each returning the same four exit tiers
  (0 clean, 1 findings, 2 usage error, 3 could not complete), and each carrying a `--json` machine
  report alongside the human rendering **except `approve-projection`**, which ships without one
  deliberately: it is a consent prompt on a controlling terminal, and a machine-readable rendering of
  a consent prompt invites a caller to answer it.

- **Deterministic candidate extraction — `profile-bundle extract`.** Reads one declared source's
  enumerated records through the bundle's own `policy/extraction-mappings.yaml` and proposes
  candidates, so a record moves from `review_required` to `imported` without anyone retyping it.
  The mapping is data, not code: it is seeded into the bundle at `init` and checked against the
  bundle's predicate catalog before any record is read, so a rule that would land a fact on a
  subject kind the catalog does not admit is refused rather than promoted into an illegal graph.

  Every record that produces no candidate gets exactly one closed reason in
  `imports/extraction-report.yaml` — the drain — and that report must explain every
  `review_required` record for the bundle to be *complete*. Nothing is inferred and nothing is
  guessed: a line the deterministic lane cannot type is deferred with a reason, never approximated.

- **Authored exclusions — `profile-bundle exclude-record`.** The other way a `review_required`
  record leaves the Gate B blocker bucket: the owner says why it is not material, with a reason from
  §18's closed seven-member catalog and a required rationale. Three documents move together — the
  exclusion, the ledger row whose disposition is *re-derived* from it (never authored), and the
  extraction-report entry that retires because §6.3a forbids one on an excluded record.

  An exclusion cannot be taken back: nothing removes one and a record carries exactly one reason, so
  every check runs before the first byte, as a diff of the real validation layers over the
  prospective tree — including the completeness layer that owns the drain reconciliation, which no
  authoring command's closing revalidation reaches.

  It moves **exactly the record named**. Re-deriving the whole ledger is what keeps disposition
  derived, and it is also how a ledger that already disagreed with the documents it derives from
  would have had that repaired as a side effect: a second row moving, its drain entry retiring, and
  Gate B's counts changing with nothing shown to the operator. That is refused —
  `import_ledger_derivation_drift` — rather than silently absorbed, in all **three** shapes the
  claim has to cover, distinguished by a typed `drift_kind` detail rather than by their prose: a
  `ledger_row` you did not name that would move; a stale `drain_entry` that would retire with **no**
  row moving at all, since the extraction report is re-derived from the same rebuilt ledger by a
  different rule; and the `named_record` itself, which the other two checks skip by construction and
  which derives as `imported` rather than `excluded` whenever its candidate is still in
  `imports/candidates.yaml`. The ledger and the drain are written before the exclusion, so the one
  half-applied state the renames can leave is the one the same command run again completes.

  `owner_excluded` is the one reason that costs an `approve_source_record_exclusion` sub-approval.
  It is derived from the write, shown by `approve`, and filed in that candidate's single stamp;
  promoting without it is `missing_owner_approval`. The stamp now binds
  `source_exclusion_target_digest` — the function §18 names — rather than a second spelling of the
  same join. `approve_source_scope`'s stamp now binds `source_scope_target_digest` for the same
  reason: it carried the identical divergence, a published helper with no callers beside an inline
  join that was the one actually enforced, and the helper has been moved onto the spelling already
  on disk so no promoted stamp changes value.

- **Candidate promotion — `profile-bundle promote-candidates`.** Turns one source's imported
  candidates into the renderable graph: entities, `FactRecord`s, and the `SkillRecord`s whose
  `skill_id` is a real reference. It is grounded and owner-mediated by construction — **every fact
  is born `unresolved` with no evidence and no attestation**, and a skill exists only where a
  bullet's authored `tech_tags` ties it to an entity. Confirming, attesting and approving those
  facts stays the owner's step, because synthesising it would be fabrication. Promotion is one-shot:
  it refuses rather than clobber a draft that already holds entities or skills.

- **The bundle-to-résumé projection — `resume project`, `profile-bundle project`, and
  `profile-bundle approve-projection`.** The bridge from the bundle to a rendered résumé, in two stages
  with the owner's editorial choices in one declaration file.

  `{config_dir}/projection.yaml` is that declaration: it groups bundle skill ids under labels you choose,
  names which entries appear in what order, and points at the shell document supplying the parts the bundle
  is deliberately not authoritative for. **Omitting `skill_groups` entirely synthesizes them from the
  bundle's own `policy/skill-categories.yaml`**, so the owner's skill taxonomy lives in one versioned place
  rather than being restated, unversioned, in the declaration. **An entry's bullets come from its `claims`,
  from `bullet_predicates` (predicate ids whose résumé-surfaced facts render directly as bullets — so an
  `employment.accomplishment` fact reaches the page without a `ClaimRecord`), or both.**
  **v1 projects `skill_groups`, `entries` and `extracurricular` only — not your name, contacts or
  education.** That is not an omission: the LaTeX renderer never reads `Resume.header` or
  `Resume.education`, so projecting them could not change a PDF.

  `profile-bundle project` serializes the JD-blind Stage 1 pool for review, touching no database, so the
  pool can be inspected before any posting is involved. `resume project --posting N --scorer NAME` runs
  Stage 1 and then Stage 2, selecting which entries reach the résumé against that posting's JD skills and
  a page budget, and writes `resume.projected.yaml` and `projection-manifest.json` beside each other
  under `--out`. Rendering stays a second command — `tailor run <id> --resume <path>` — because folding
  projection into `tailor run` would require `tailor` to know about the bundle, which is the one wall this
  design keeps up. Two costs are accepted rather than optimised away: the JD is read twice, and the
  résumé compiles twice, a scratch compile to fit the budget and the real artifact in `tailor run`.

  **`--scorer` is required and has no default.** All four registered scorers
  (`coverage_then_density`, `mean_per_bullet`, `mean_top_k`, `total_distinct`) are falsified by one
  rank-agreement probe or the other, and they collapse into two behavioural families, so they cannot
  break their own tie. Naming one is therefore a deliberate, visible choice rather than a silently
  picked winner, and it stays that way until an owner-labeled selection matrix rules. An unknown name is
  refused with the live list of registered choices.

  `approve-projection` records the owner's approval of the declaration's exact resolved content on a
  controlling terminal. The approval **binds the bundle it was made against**: the stamp carries the
  bundle digest, and projection compares it against the bundle actually being read, refusing when the
  bundle has moved since approval — the one case an unedited, still-approved declaration would otherwise
  hide completely. That comparison is unconditional; a `--check` flag that used to gate it was deleted,
  because an opt-in flag on a consent control is the wrong shape and a check that cannot behave
  differently from the plain command is a check to delete rather than keep.

  Carried, and known: the shell document's *content* is bound by no digest — it is hashed as a filename
  and lives outside the bundle, so editing it changes the projected header and education with no
  re-approval. The blast radius is small for exactly the reason above, the renderer reading neither
  field.

- **`profile-bundle import`** enumerates one owner-approved source into a draft's
  `imports/source-ledger.yaml`, through the deterministic adapters that shipped with the bundle and
  had no entry point until now. `--from PATH` names the source document, or it is resolved through
  the machine-local `local-sources.yaml` sidecar. It writes the ledger and nothing else: candidates
  and exclusions stay owner-authored, so every disposition is derived from what the draft already
  holds and a re-import cannot reset a decision the owner made. Re-importing an unchanged source
  writes no byte, and a source keeps both its position in the ledger and the scope it was approved
  under.

  The shape of the thing: you author YAML records into a **draft**; `validate` runs the structural,
  referential, evidence, semantic, history, imports and digest layers over it — plus four more under
  `--completeness` — and reports what every layer found rather than the first failure; `approve`
  records the owner's decision against the draft's exact content, on a controlling terminal;
  `promote` turns it into an immutable, content-addressed
  **revision** and selects it. Editing an approved draft invalidates the stamp, because the stamp is
  bound to the content digest and not to the draft's name. Evidence blobs are captured by digest and
  secret-scanned on capture.

  `add-evidence` writes the back-citation itself, default on: attaching an evidence record also updates
  every fact-bearing document that cites it, and the command **names the documents it rewrote** —
  `cited_back`, printed and in `--json`. Without it the command had become an up-to-thirteen-file edit
  that reported none of them.

  It also ships, as package data, the JSON Schema generated from the typed models and a complete
  synthetic example bundle, so the authoring contract is readable without running the code.

  **The existing tailoring path is untouched.** `boardwatch tailor` still reads
  `{config_dir}/resume.yaml`; there is no bundle-to-résumé bridge in this release, deliberately, and a
  test over the import graph holds that boundary in both directions. The package also adds no table and
  no Alembic migration, and ships its own canonical serializer rather than reusing the ones that feed
  `policy_version`.

  **Still unsupported and unstable.** Its acceptance gate has not been declared met, and its on-disk
  grammar, digests and JSON reports may still change. Nothing outside the package should depend on them
  yet. Note also that part of this package was already inside the published `0.3.0` wheel, where the
  `[0.3.0]` notes below do not enumerate it; it was unreachable there, with no command and no entry
  point.

- **Opt-in page-fill for bundle-to-résumé projection — `fill_to_page` on the projection declaration**
  (D-234). Stage-2 `select` enforces a strict `ADMISSION_FLOOR=0` (a candidate sharing no JD-skill overlap
  is never admitted) and an all-or-nothing `no_match_fallback`, so a narrowly-targeted JD could leave the
  page short with no way to fill it. When `fill_to_page: true`, a second growth phase runs after the ranked
  selection and tops off from the remaining candidates in declaration order, bypassing the floor, until the
  page budget is reached; the ids it added are recorded on `SelectionResult.fill_added_ids`. Default off
  leaves selection unchanged.

- **Opt-in first-bullet link placement and reverse-chronological project sort — `link_in_first_bullet`
  (per-entry) and `sort_projects_by_date` on the projection declaration** (D-235). `link_in_first_bullet`
  renders an entry's link as an underlined label appended to its first bullet instead of the project
  heading, clearing the link/date collision on a wide heading line. `sort_projects_by_date` orders project
  entries newest-first by their structured `year_month` start date, applied after selection and fill;
  experience entries are untouched. Both default off. The layout firewall reconstructs the first-bullet
  expected substring through the shared `_href` helper, so the escaping round-trip stays exact and tailoring
  is not silently degraded to the untailored fallback.

- **A rank-time seniority gate, a versioned leveling catalog, and the `target_seniority_band` profile
  field** (D-246). Run 61 shortlisted two off-target leads because seniority was only the
  `exclude_titles` substring list and nothing read a title's *band*. `boardwatch top` now gains a
  `hidden_over_seniority` bucket and an `--include-over-seniority` drain; the funnel's shortlist stage
  reports the new bucket and its reconciliation identity includes it. The same gate runs on `notify`
  and `stats`, and `show <id>` tells you what it made of any posting.

  The gate reads a new **versioned catalog**, `rank/leveling.yaml` — level grammars, named company-free
  rung ladders, and per-field word→band and roman→band maps. **It contains no company names**, because a
  company's ladder is not a fact boardwatch can ship; the company→scheme binding is user config in
  `{config_dir}/leveling-bindings.yaml`, keyed on `(provider, slug)`. Only a confident word, roman
  numeral, or bound-scheme hit may drop. An unbound level token, a level outside its scheme's range, and
  every ambiguous bare letter+digit token (`L2` is far more often OSI layer 2 than a level) all abstain,
  and abstains are **counted and reported** as `uncertain_band` rather than folded into either
  neighbour. Absence of any token is in-band — silence is never evidence of seniority.

  The new profile field `target_seniority_band` is a closed vocabulary — `entry | mid | senior | any` —
  and **defaults to `any`, which short-circuits the gate before any title is read**. Behaviour is
  therefore unchanged on upgrade until you set a band with `boardwatch profile edit`; while the gate is
  inert, `top` still counts the band tokens it saw and says so, so the feature is discoverable rather
  than silently dormant.

  Measured 2026-08-19 over 26,997 live open postings: only **three** companies put a resolvable level in
  their titles at all, the abstain rate is **0.25%** at `entry` and **0%** at the shipped default, and the
  gate closes **61** senior postings that leak into the shortlist today (21 Distinguished Engineer, ~15
  Vice President). Bare `fellow` was **dropped** from the word list as a measured false drop: a
  *fellowship* is early-career, and treating it as senior killed three entry-level software roles.

### Changed

- **`boardwatch eligibility extract` and `boardwatch tailor run <posting-id> --tier-b` now exit 1 when an LLM
  credential dies mid-run and nothing landed** (P3 slice 5, D-146). Previously a dead credential was
  swallowed silently: `eligibility extract` burned up to `max_calls_per_run` doomed calls, wrote zero
  eligibility rows, printed `"extracted N postings"`, and exited 0; `tailor run --tier-b` recorded every
  dropped bullet as the undifferentiated `drop_reason="error"` and exited 0 regardless. Both commands
  now classify credential death (exhausted credit, invalid credential, or a key lacking model access)
  from the provider's error body at the point of failure, stop making further calls for the rest of
  the invocation, and report which reason. The new exit 1 fires **only** when death was observed
  **and** nothing landed — a credential that dies partway through, or a healthy run that keeps zero
  results because nothing qualified, both still exit 0 exactly as before. This is a public CLI
  contract change: a caller relying on the old always-0 exit code from these two commands will now see
  1 in the dead-credential-with-zero-output case. On that exit-1 path **both** commands also record
  their run row as `status="failed"` with the lane-death reason in `errors_json`, instead of the `"ok"`
  previously written on every path (D-148 for `tailor run --tier-b`, which does this only for a run it
  owns — under `boardwatch run` the pipeline owns the terminal status, and one dead-credential lead must
  not fail the whole run); a run that merely hit an unclassified provider outage still finishes `"ok"`
  attributing zero rows, unchanged.
- **The per-run funnel artifact names `lane_dead` in its fabrication drop-reason catalog**, as a new
  `fabrication.lane_dead` key in the JSON and a new entry on the `fallbacks:` line in the Markdown.
  It is additive, so `artifact_version` stays `4`. Reaching it needs Tier B wired into
  `pipeline/runner.py`, which has not happened; without the catalog entry such a row would have
  rendered the artifact's out-of-catalog FAILURE line.
- **The title role gate denies a bare `… Coordinator` with no engineering head noun** (D-245, D-246).
  "Disaster Response Coordinator" reached run 61's shortlist because the gate verdicts it `uncertain`
  and the ranker passes `uncertain` through fail-open. The new pattern is anchor-guarded by the same
  `_NOENG` lookahead the bare-`sales` pattern uses, so "Engineer, Coordinator Services" stays reachable.
  Measured over 26,997 open postings: **135 postings flip `uncertain` → `not_swe`, and zero
  `swe`-classified titles contain the word**, so the deny cannot bury a software job; the anchor
  additionally spares 4 administrative roles at engineering schools. This closes 135 of the 11,171
  `uncertain` postings (1.2%) — reporting `uncertain_role` and closing the role gate's fail-open
  `uncertain` lane are separate, larger work and are **deliberately deferred**, not overlooked.

### Fixed

- **`top --include-non-swe` no longer records the rows it reveals as `seen`** (D-246). Draining the
  role-gate quarantine marked every revealed row `seen`, so looking into the bucket suppressed those
  rows from later runs inside the TTL — the drain closed behind you. A drained row is now excluded from
  the `seen` write, as CLAUDE.md requires of every quarantine: a drain is a re-entry path, not a one-way
  consumption of the queue. `--include-over-seniority` is built on the same rule from the start. The
  duplicate, applied and handled drains were never affected — they return before the surfacing line.

- **`profile-bundle extract` no longer imports a half-record when one field of an entry can't be typed**
  (D-238). `run_extraction` recorded a drain reason only for a record that produced *zero* candidates, so an
  entry that grounded some slots (say its heading → `project.name`) but hit a slot-level failure on another
  (a garbled `dates` → `value_not_typeable`) imported anyway, and the failed field went unaccounted — the
  disposition is derived from the candidate package, so the good candidate made the record `imported` with no
  reason attached. Now a record that hits any slot-level failure is set aside whole: its candidates are
  withheld and it drains that one reason, landing `review_required` for the owner. A record is imported only
  when it produced candidates *and* raised no reason; legitimate absence (an empty field, an open-ended date
  range) still imports as before. Latent today — every current résumé entry parses cleanly — so no live run
  changes.

- **`profile-bundle promote-candidates` no longer silently drops a skill-group label that collides with a
  seeded category** (D-237). A promoted skill's group label is slugged to a `category_id`; when that slug hit
  a category the bundle's catalog already defined under a *different* `display_name` (author writes group
  "Technique"; the catalog defines `technique` → "Techniques"), promotion skipped it and filed the skill under
  the catalog's label, discarding the author's — with nothing warning. Promotion now refuses, naming both
  labels and the shared id, so the author aligns the group label to the catalog (or changes the catalog's
  `display_name`). This closes the last of the five slug-collision sites (D-202…D-210); the catalog owns the
  `display_name`. Reachable only when a bundle ships a seeded catalog, so no default behaviour changes.

- **Rendered résumé PDFs are now ATS-parsable** (D-233). tectonic (XeTeX) with the default Computer Modern
  fonts emitted the `ff` ligature as the single codepoint U+FB00 with no ToUnicode mapping, so `pdftotext`
  — and every ATS that runs one — read "efficiency" and "traffic" as garbled or dropped text: correct on
  screen, unparseable underneath. The bundled `resume_base.tex` now loads the font through `fontspec` with
  `Ligatures=NoCommon`, so each glyph stays one ASCII codepoint, and names the small-caps face explicitly
  (`SmallCapsFont={lmromancaps10-regular.otf}`, Latin Modern) so section headers keep their small caps. The
  font resolves from tectonic's own bundle; nothing new is shipped, and the one-page fit is unchanged.

- **A missing `pdfinfo` now fails the run loudly instead of quietly degrading every lead.** poppler's
  `pdfinfo` supplies the page count the résumé gate measures against `resume_max_pages`. When the binary was
  absent, `_pdf_page_count` returned `None` and that was folded into `COMPILE_FAILED` for **every** lead — so
  a machine with `tectonic` but without poppler produced a degraded or empty run every morning, with the
  cause named nowhere on the run path. `boardwatch doctor` did report it, but only if you thought to run it,
  and a check the user must remember is not a guard. A missing `pdfinfo` is now `BINARY_MISSING`, the same
  run-level fatal a missing `tectonic` has always been, and the error names poppler and how to install it.
  The two other reasons a page count can come back unmeasured — `pdfinfo` exiting non-zero, or output with
  no parseable `Pages:` line — still read as `COMPILE_FAILED`, because those really are compile failures.
  Affects `boardwatch run`, `boardwatch tailor run`, and the projection budget loop, on every OS.

- **`boardwatch export --format csv` no longer crashes on a redirected non-UTF-8 stdout.** It wrote rows to
  the ambient `sys.stdout`, whose encoding when redirected on Windows is the ANSI codepage, so any non-ASCII
  company name raised `UnicodeEncodeError` and killed the export. The `--out` path had always been correct;
  only the stdout branch was wrong. That branch now writes UTF-8 through a locally-wrapped stream, flushed
  and detached so the shared buffer stays open for the rest of the process. Global stdout is never modified,
  so nothing else the command prints is affected.

### Migration

- **`target_seniority_band` re-keys `policy_version` once.** The band and the leveling catalog's digest
  now enter `profile_row_hash`, so every stored decision's policy stamp moves the first time you run
  after upgrading. Measured on the live store: **11 ledger rows** go stale. This is the intended
  fail-safe — a stamp mismatch is never released automatically, because auto-expiry on mismatch would
  rebuild the whole shortlist on any settings tweak — and it is a one-time step: `boardwatch ledger show
  --stale` lists them and `boardwatch ledger reopen --stale` releases them. Migration
  `p_seniority_band` adds the column, defaulting to `any`, so the gate is inert and no ranking changes
  until you choose a band.

- **The opt-in projection controls added this release — `fill_to_page`, `link_in_first_bullet` and
  `sort_projects_by_date` — shift `projection_digest`.** Adding these fields changes the projection's
  controlling shape, so an existing user must re-approve their projection once after upgrading:
  `boardwatch profile-bundle approve-projection`. This is the intended fail-safe — the digest reopens the
  owner's editorial gate whenever the projection changes — and it is a one-time step, even for users who
  leave all three controls off.

## [0.3.0] - 2026-08-10

### Added

- **`--verify` on `companies add` and `companies import`.** Opt-in live board probe before
  the watch is written, reusing each provider's existing `healthcheck`. Reachable boards are
  watched (reachable-but-empty is watched with a note); boards that return 404, error, or
  cannot be reached are skipped instead of written, since an unreachable board is absence of
  evidence rather than evidence the slug is wrong. `import --verify` exits non-zero when it
  skipped any entry, so a partial import cannot be mistaken for a complete one. Both
  commands remain offline by default.

- **Applied-state suppression** — a job you have already applied to is never served as a lead again
  (P6 item 5, D-111). The ranker reads `applications` directly, keyed on the canonical job so the
  suppression survives the posting being revised, closed or regrouped. The suppressing set is
  `APPLIED_STATUSES` (`applied`, `interviewing`, `offer`, `rejected`), reused from the funnel's conversion
  count rather than re-declared: `interested` does not suppress, because it is `track add`'s default and
  suppressing it would mean tracking a lead hid it. `boardwatch top --include-applied` is the drain, and
  `track status <id> withdrawn` releases the job — note this means withdrawing the attempt that was
  *submitted*; `track add --new-attempt` writes an `interested` row and does **not** release an earlier
  submission. Reported as `hidden_applied` in the funnel
  and in the run summary line. **No live population yet** — `applications` is 0 rows because `track` has
  never been used, so this ships as a mechanism with tests as its evidence.

- **Liveness at the lead list** — each shortlisted posting is re-fetched immediately before its résumé is
  built, and one answering **404/410** is withheld from that run (P6 item 6, D-111). Everything else —
  timeout, 403, 5xx, redirect, missing URL — is served: the cost of a dead lead is one wasted résumé, and
  the cost of withholding a live one is a job nobody can know they missed. Measured 2026-08-10, a live
  Pinterest posting answers 403 to an unfamiliar user agent, which is why that is not a gone-status.
  **Nothing is cached and nothing is written** — a withheld posting stays `open`, because
  `postings.status` belongs to the scanner's board-absence rule and one 404 from a flaky CDN must not
  retire a real requisition permanently. `boardwatch run --no-check-liveness` opts out, and an unprobed
  run reports liveness as *unmeasured* rather than as zero dead. The funnel artifact gains a top-level
  `liveness` block (**artifact version 4**).

- **`boardwatch top --no-record`** — rank without marking anything `seen`, so the call does not advance the
  queue (D-110). The write-side counterpart to `--include-handled`: needed by any script that ranks once to
  display and again to act, and by anyone taking a second look at a shortlist they just saw.

- **Durable decision ledger, its drain, and job regrouping — P6 Slice 2** (D-103 … D-107). A new
  `job_dispositions` table (migration `p6_job_dispositions`, now the Alembic head) records **one row per
  job**, upserted monotonically along `seen` < `skipped` < `built`. `built`/`skipped` are permanent and
  carry a **policy-version stamp**; `seen` is TTL'd by the new `seen_ttl_days` setting (default 7). Expiry
  is **lazy and read-time** — nothing sweeps the table and nothing deletes from it, including the drain,
  which sets `reopened_at` so a drained decision stays on record. One liveness predicate is shared by the
  reader and the writer, because a reader/writer disagreement would both hide a job and refuse to
  re-decide it. Three CHECK constraints repeat the closed catalogs and the permanence contract at the
  store, so a direct INSERT cannot invent a bucket or store a permanent decision with no stamp.
  **What this fixes, measured:** postings 2011, 2012, 10947, 15498 and 15499 each carried a tailored
  résumé from **four separate runs**, because nothing suppressed an already-built lead and the top-N never
  advanced. `boardwatch top` gains a `hidden_handled` bucket and an `--include-handled` drain; the funnel's
  shortlist stage reports the new bucket and its reconciliation identity includes it.
- **Job regrouping** — duplicate postings are now projected onto one canonical job
  (`boardwatch identities regroup [--dry-run]`, and automatically over the population each pipeline run
  ranked). The canonical job is the job of the survivor `resolve_duplicates` already elected, so there is no
  second election. `job_grouping_events` is written **before** the `postings.job_id` projection, because the
  projection can be rebuilt from the trail and not the reverse. A group is refused **whole** when any
  non-survivor member's job carries an `applications` or `artifacts` row — `run_funnel_queries` and
  `reports/export` both reach applications through `applications.job_id == postings.job_id`, so merging such
  a job would silently make a real applied count wrong. Verified on an isolated copy of the live store: 186
  merges over 147 groups, 0 refused, idempotent on a second pass, and `count(distinct job_id)` fell by
  exactly 186 with zero self-merges.
- **`boardwatch ledger show|reopen`** — the ledger's drain. `show` lists what is being suppressed and why
  (`--stale` for permanent decisions whose policy stamp has moved, `--expired` to include rows that no
  longer govern); `reopen --job N` / `reopen --stale` releases them. A stamp mismatch is never released
  automatically: auto-expiry on mismatch would rebuild the whole shortlist on any settings tweak.

- **Duplicate-posting suppression — P6 Slice 1, the identity and suppression half** (D-077 … D-101). A new
  `posting_identities` table (migration `p6_posting_identities`, now the Alembic head) stores multiple ranked
  identities per posting, computed from a **closed, ranked, versioned catalog** in which `exact_quad`
  (company + normalized title + normalized locations + `content_hash`) is the **sole suppressing kind**.
  `content_hash` alone may never suppress — 809 such groups exist live and 727 of them span a different title
  or location, so a hash-keyed dedup demonstrably collapses different jobs (D-081). `cross_host` is computed
  and stored but **annotate-only** (D-083): it may not suppress until it can dereference an aggregator posting
  to exact requisition evidence. A posting with no location evidence emits **no** location-bearing identity
  rather than an `"[]"` sentinel, because the sentinel makes every location-less posting equal on that
  component and neither the string-verify nor the recount can catch it. Suppression is resolved by a pure
  function with no DB, clock or I/O: it groups by stored identity key, **re-compares the underlying strings**
  before acting on a hash equality, and elects a survivor by `(host_class, earliest first_seen_at, lowest
  posting_id)` — **never by score**, since a survivor that moves between runs makes the 7-day duplicate-leakage
  measurement Gate P6 requires meaningless (D-086). `normalize_url` is an **allowlist**, not a denylist
  (D-080): an unlearned tracking param merges two postings, which the string-verify catches, whereas an
  unlearned identity param silently splits one posting into two.

  New commands `boardwatch identities backfill` and `boardwatch identities verify`. The backfill is explicit
  and idempotent, never a side effect of `alembic upgrade` (D-092), so it can be re-run after an algorithm
  bump. `verify` recounts through a genuinely different path — stored rows against freshly recomputed ones —
  and exits 1 on stale **or** missing identities, because "nothing is deduped because nothing was backfilled"
  is not a healthy subsystem.

  `boardwatch top` hides duplicates, threads a new `hidden_duplicate` counter into the funnel's reconciliation
  identity, and ships the drain in the same change as the quarantine: `--include-duplicates` surfaces every
  suppressed row, each naming the posting it duplicates. Drained rows do **not** consume `limit` slots — a
  drain bounded by the rank cutoff reaches only the suppressed rows that would also have ranked, which is not
  a re-entry path for the bucket. Suppression and the funnel's per-source `unique` are both **completeness-gated**: until every open posting carries a current-version identity, nothing is suppressed and `unique`
  reports `None` rather than a partial number (D-088). `top` states out loud when suppression is off and
  which command fixes it, so `0 duplicates` is distinguishable from "never measured". `assisted` stays not-instrumented on purpose: no suppressing
  kind in this slice can cross a source boundary, so `0` would be a structural zero dressed as a measurement.

  Measured on the live 23,455-posting corpus: **147 groups / 186 surplus rows / 0.79%**, all `exact_quad`,
  re-derived independently by grouping the stored keys in SQL. **20 of 20 sampled suppressions audited as
  genuine duplicates, zero false positives** (D-101) — same company, same title, same location, distinct
  requisition id. Gate P6 is **not** met: two of its four clauses now are, and the
  remaining two — duplicate leakage measured over 7 days, and 0 dead postings reaching the lead list —
  need the system RUN rather than more building.

- **Field-tier eligibility taxonomy — the `career_field` routing mechanism** (P2 item 4, D-075). The
  eligibility catalog now carries the three-tier vocabulary `CLAUDE.md` asks for as versioned *data*: every
  family declares a required `tier` (`universal | profile | field`), a field-tier family declares a flat
  `applies_to` list, and `rules.yaml` declares a closed top-level `career_fields` vocabulary. `CATALOG_REVISION`
  goes **1 → 2**, so every cached verdict re-keys once on upgrade. `Facts.career_field` is validated against
  that closed vocabulary and hashed **unconditionally** into `profile_hash` — it is not a resolver input, so
  `build_identity` hashes it explicitly rather than via `declared_fields`, and a career-field change can never
  silently reuse a stale verdict. It is settable and visible everywhere a fact should be: `boardwatch
  eligibility facts set career_field <value>` (rejecting out-of-vocabulary values with the valid list),
  prompted during `boardwatch init` and `boardwatch profile edit`, and shown in the `eligibility facts`
  display. `engine.field_applicability` routes each family three ways — **active** (not field-tier, or the
  profile's field is in `applies_to`), **skip** (the profile's field is a valid *other* catalog field, so the
  family is genuinely irrelevant and produces no rows), and **abstain** (the field is missing *or*
  out-of-catalog ⇒ `missing_profile_field:career_field`, the keystone: never a silent clear). The field-abstain
  branch is evaluated **before** the posting-waive branch, so a JD that would otherwise waive a requirement
  cannot convert an unresolvable profile into a pass. `not_applicable` is **report-only**: `eligibility
  abstain` and the run funnel now distinguish a family that is inapplicable to this profile from one that
  never fired, and no such disposition is ever persisted. All six bundled families ship `tier: profile` and
  the bundled `career_fields` is `[software]`, so **bundled behaviour is unchanged** apart from the one-time
  cache re-key; multi-field routing is exercised by test fixtures (controlled catalogs with 2–3 declared
  fields), not by a live run, because D-054 gathers non-tech field content per user at onboarding rather than
  authoring it here.

- **Final eligibility gate — a persistent, agent-lane check over the live shortlist** (D-074). A second,
  standing eligibility lane distinct from the one-time P5 answer-key labeling pass: `boardwatch eligibility
  gate request [--top N] [--out]` builds a JD-blind request from the ranked shortlist (the same request
  shape `label request` uses); the `eligibility-judge` skill judges it with the identical JD-and-facts-only
  rules; `boardwatch eligibility gate apply --verdicts path [--top N]` persists the verdicts as a new
  INELIGIBLE-capable `engine_kind='llm'`, `engine_version='final_gate:<POLICY_VERSION>:<PROMPT_VERSION>'`
  evaluation (`eligibility/final_gate.py::record_gate_verdict`), keystone-guarded (an accepted ineligible
  with an unresolvable JD span downgrades to `uncertain`, fail-open) and written under the user's STORED
  facts+policy so the identity matches what the ranker reads. `boardwatch top`/`boardwatch run` now hide a
  posting when EITHER the deterministic engine OR this gate says `ineligible` (one shared counter; a gate
  `uncertain`/`eligible`/missing row changes nothing). The advisory `extract_llm` lane's own read
  (`load_llm_audit`) is now scoped to its disjoint `llm:%` version prefix so it can never mislabel a gate row
  as advisory. `gate apply` mints its own `run_id` per D-019 and warns if the verdicts file exceeds `--top`.
  Migration-free (reuses `engine_kind='llm'`, disambiguated by `engine_version` prefix — no schema change);
  model-agnostic (the request/verdicts JSON is the provider boundary). This lane is purely additive: it
  changes no deterministic verdict and no number on the existing P5 precision/recall answer key.

- **P5b answer-key oracle judge — agent lane, no API key** (D-068). An AI oracle produces the Gate-P5
  answer key (`expected_verdict` ∈ eligible/ineligible/uncertain + spans) through a 3-step CLI handshake
  driven by the user's own Claude Code — the `eligibility-judge` skill — mirroring the P7b subscription lane:
  `boardwatch eligibility label request` writes a JD+facts request (excludes the `hint`; ships the reference
  all-blocker policy) → the skill judges each row → `boardwatch eligibility label apply` re-runs a
  deterministic provenance + four-ANDed routability gate (`eligibility/oracle.py::accept_oracle_verdict`)
  that **downgrades any unverified oracle `ineligible` to `uncertain`** (fail-open — a false INELIGIBLE
  never enters ground truth), merges results back preserving all worksheet columns, and flags any `applied/`
  hard-negative the oracle called `ineligible`. Non-circular: the oracle reads JD + facts only, never the
  deterministic engine's verdict; the closed reason catalog is the 6 `rules.yaml` families. `resolve_provenance`
  is ported from job-apps with the informativeness floor calibrated (3 tokens) so terse clearance/citizenship
  stops survive. The deferred human audit's drain is **mechanical**, not a printed warning:
  `PrecisionReport.audited_coverage` + `meets_ship_gate()` + `boardwatch eligibility score`'s non-zero exit
  block shipping B1–B4 until audited coverage ≥ `SHIP_AUDIT_COVERAGE_BAR` (0.20); `PROGRAM.md` §3.P5 carries
  the checkable gate line + the "modeled-family hard stops only" reframe. Built as 7 TDD tasks, each
  task-reviewed, with a whole-branch review (SHIP-AS-IS).

- **P5b B0 scaffolding — the Gate-P5 precision scorer + reference policy** (D-065). `eligibility/scoring.py`
  measures the P5 gate without shipping any verdict-changing rule: `reference_all_blocker_policy(catalog)`
  (a code constant setting every catalog family to `blocker` — auto-covers future B4
  families, no fixture/drift), `score()` → `PrecisionReport` (INELIGIBLE precision `None`-vs-0/0 disciplined,
  recall, per-rule abstain rate, false-positive triage, span violations), `meets_gate(0.95)`, and
  `load_labeled_set()` reading a `*.jsonl` worksheet that fills in over time (null verdict = unlabeled →
  skipped; malformed row fails loud). `carries_valid_span` extends P5a S1's "0 INELIGIBLE without a span"
  property to the labeled set, shared rather than forked, and deliberately kept out of the digested engine
  modules. The verdict-changing rules (B1–B4) stay gated on a human-verified labeled set. A stratified
  173-row candidate worksheet + labeling instructions were seeded locally (gitignored — real JD bodies are
  personal data).

- **Keyword-coverage measurement for tailored résumés** (P4 item 6 — D-061). A per-lead and per-run report
  (never a veto) of how many of a JD's *requirement* terms the résumé genuinely covers. The denominator is
  the JD's qualifications span (via the existing `qualifications_span`), falling back to whole-body skills
  when no qualifications header is found, recording which source was used. The numerator counts only skills
  the **master** résumé actually has (`tailor/coverage.py::resume_fact_skills`), never the tailored output —
  so a bullet that echoes a JD term cannot inflate coverage. `fraction` is `None`, never `0.0`, when a JD
  has no recognized requirement terms. Surfaced in each tailored artifact's `meta_json`, the morning report,
  and a run-level funnel summary (mean/median coverage, most-frequent missing terms). Fail-safe: a coverage
  bug records `coverage=None` and never drops a lead.

- **Persona registry + résumé title de-senioritizer** (P4 item 7 + folded-in item 4 — D-063). A persona is
  a résumé-*presentation* lens (title, skill-group order, entry subset), never an eligibility variant, so
  the profile DB and eligibility engine are untouched. A versioned `tailor/personas.yaml` (bundled seed +
  `{config_dir}` override) declares personas; `select_persona` deterministically picks one from the JD's
  role family (`classify_role_family`, never a model; unmatched → the required default); `apply_persona`
  reorders skill groups and selects/orders the entry subset on a new frozen `Resume` with an optional
  `title`. The title is the JD title with seniority stripped (`tailor/title.py`, boundary-safe: `Sr`∉`SRE`,
  `Lead`∉`Leader`, `III` before `II`), validated against the persona's family — a "Senior iOS Engineer" JD
  yields an "iOS Engineer" headline, never stamping "Senior" on a new-grad résumé. Rendered into the paired
  `%%TITLE%%` template slot (graceful degrade when absent). A malformed registry is a loud run-level fatal;
  an unmatched JD family is the normal default path. Keyword coverage (item 6) still measures against the
  original master, so persona shaping can't inflate it.

- **P5a — verdict-safe eligibility-integrity slices** (D-064). Three changes that raise decision integrity
  without altering any deterministic eligibility verdict: (1) a corpus-wide **property gate** asserting
  every INELIGIBLE result carries a non-empty quoted JD span (Gate P5's "0 INELIGIBLE without a span");
  (2) `boardwatch eligibility abstain` now surfaces an out-of-catalog **family** and any **disposition
  token** outside `{met,unmet,unknown}` as their own FAILURE lines (closed-catalog discipline), while still
  reconciling the anomaly into `total_rows` so denominators never silently shrink; (3) the opt-in LLM
  eligibility lane's response cache is now keyed on **profile + catalog identity** (`profile_hash` +
  `rules_hash` folded into the cache key), so a cached verdict is never replayed across a changed profile
  or rule catalog — `ResponseCache.key`'s signature is unchanged, leaving the tailor rewrite lane intact. Verdict-changing P5 items (new families,
  named exceptions, REQUIRED/PREFERRED context) and data-gated items (labeled eval set, 35+ visa phrases)
  are deferred — they need the human-verified labeled set to measure Gate P5's precision.

- **A run reaper drains phantom `running` rows instead of leaving them permanent forever** (P3 slice 2,
  D-046). A crashed or killed run left `runs.status='running'` with `finished_at IS NULL` with nothing to
  separate it from a live run. `reap_stale_runs(engine, *, older_than)` marks rows matching
  `status='running' AND finished_at IS NULL AND started_at < now-older_than` as `failed`, in a single
  atomic `UPDATE ... RETURNING id` (append-only `json_insert` note — no read-modify-write). Discrimination
  is age-based rather than process-liveness-based: `runs` carries no pid/heartbeat column, and a container
  writer and a host writer have disjoint pid namespaces anyway. Default threshold is the new
  `Settings.reap_stale_after_hours` (24h; classified operational, so it never enters `config_hash`). Runs
  inside `doctor` (report+reap, guarded so a lock-contended write can never crash the diagnostic) and at
  `boardwatch run` start, before the run's own row is minted. Fail-safe by construction: `finish_run` has
  no `status='running'` precondition, so a false reap on a run that later finishes self-corrects its
  `status` — though the `reaped` note intentionally persists in `errors_json` as a breadcrumb (an Opus 5
  checkpoint review corrected the original docstring, which had claimed a complete self-correction) — and a
  narrow theoretical `BUSY_SNAPSHOT` race on `finish_run`'s own read-modify-write is documented rather than
  restructured (D-046, D-055).

- **A P4 craft guard gauntlet — five deterministic checks on Tier-B rewrites, each reverting one bullet to
  its Tier-A source rather than dropping the lead:**
  - **Overmatch (style) guard** (D-048, `tailor/overmatch.py`, `OVERMATCH_VERSION="p4-overmatch-1"`): flags
    a Tier-B bullet that lifts a verbatim ≥7-gram from the job description, or copies the JD's unusual
    capitalization of a non-canonical term. Complements P1b's provenance (facts) veto — this one catches
    lift, not fabrication — and runs after provenance, before the judge, so a bullet about to be reverted
    never spends judge budget.
  - **Canonical-vocab consolidation** (D-049, `tailor/canonical.py::build_canonical_vocab`): one
    byte-identical source for the canonical-tech set (taxonomy names ∪ equivalence-table images), replacing
    the same seed expression previously duplicated across `rewrite/lane.py` and `rewrite/agent_lane.py`. A
    per-field vocabulary selector was declined as speculative — there is one field (SWE) today.
  - **Register / buzzword / verb-diversity guards** (D-050): a banned-register phrase list and a
    per-bullet buzzword-density ceiling (`tailor/register.yaml`, `register.py`), plus a résumé-wide
    verb-opening-diversity post-pass (`rewrite/verb_diversity.py`; no more than 2 bullets share an opening
    verb, and a rewrite is only demoted when doing so genuinely diversifies against the Tier-A verb that
    would otherwise ship).
  - **Requirement-echo detector** (D-051): an AND-gate flagging a Tier-B bullet that restates a JD
    qualification instead of describing work — a structural qualification-register cue AND a shared 4-gram
    with a JD qualifications-section sentence containing a non-canonical token, so pure tech-vocab overlap
    never corroborates on its own.
  - Each veto is a new closed `drop_reason` (`lift_rejected`, `banned_register`, `buzzword_density`,
    `verb_repeat`, `requirement_echo`) reported on the funnel's `FabricationCounters`, all excluded from
    bar metric B4's fabrication numerator — a conservative craft veto is not a caught fabrication. The
    pre-existing structural filter rejects (`empty`/`not_single_line`/`too_long`) were split into their own
    `filter_structural_rejected` bucket for the same reason (D-055 fix 3).

- **Two run-time résumé layout gates, both fail-safe to the untailored master** — a violation degrades to
  the master, it never drops a lead on layout alone:
  - **Per-lead layout gate** (D-053, `validate_layout` in `reports/resume_gate.py`): asserts bullet length
    ≤220 chars, bullet count ≤ `MAX_BULLETS_PER_ENTRY`, an escaping round-trip, and no template-artifact
    token leak — run on the tailored and Tier-B renders. It does **not** run on the untailored master
    (see Fixed, below).
  - **Run-once master validation** (D-056, `validate_master` in `tailor/load.py`): checks the authored
    master résumé once, at load, for a contact name and email and no template-artifact leak — deliberately
    skipping bullet length/count, which are the author's own choice, not a rendering defect. A broken
    master now aborts the run loudly (`MasterResumeError`, fatal) instead of silently dropping every lead
    one at a time.

- **A run-scoped morning artifact, `morning-<run_id>.{json,md}`, written beside the funnel**
  (P3, §3.P3 item 7, D-038). For every lead a run tailored: apply URL, résumé PDF path, the
  honest `AuditView.presentation` verdict label, a quoted evidence span (or the eligibility
  rationale), and the ranker's one-line why — ranked by score. It links to `funnel-<run_id>.md`
  for the accounting rather than restating it, and is sourced from the same population as the
  funnel (this run's tailored leads), never from cursor-scoped `digest`/`notify`.
- **A freshness check, `check_run_freshness`** (`pipeline/freshness.py`), for whether a
  `<date>/` output folder's artifacts are genuinely from a finished run of that calendar date
  (P3, §3.P3 item 2, D-038) — not just a folder that happens to contain a `funnel-<run_id>.md`.
  Checks the run's terminal status, that `started_at`/`finished_at` fall on that date, and that
  the lead folders on disk reconcile with the store's tailored-artifact row count for that
  run_id. No new schema.
- **Three run-integrity guards on `boardwatch run`, each capable of turning a run non-zero, none capable
  of suppressing a real failure** (P3, §3.P3 items 5, 9, 6, D-039): a **zero-output guard** — 0 leads
  fails the run unless the count of open postings verdict `eligible` AND judged BY THIS RUN
  (`run_id`-attributed, not a cross-run ledger) is also 0, so a steady-state day where every eligible
  posting is a prior-run cache hit stays honest; a **cohort-completeness guard** — every candidate the
  ranker shortlisted (`ranked.visible`) must have become a lead or a recorded tailor failure, reconciled
  by posting_id SET rather than count, so a compensating bug cannot balance it; and a
  **filesystem-truth guard** — the leads the store says this run produced must have folders on disk,
  reusing the freshness reconciliation rather than a second implementation.
- **`work_authorization.needs_sponsorship` as an orthogonal bit** on the eligibility work-auth fact (P2,
  §3.P2 item 2, D-034). Previously sponsorship need was entangled as a `status` enum value, forcing an
  EAD/F-1-OPT holder to abstain; the bit lets them state a sponsorship need independently of status, so
  `ead_or_similar` + `needs_sponsorship=false` now resolves decisively. It influences only sponsorship
  rules — never citizenship rules — and with the bit unset, behaviour is unchanged.
- **A Tier-B reword provenance veto, fail-closed to the Tier-A bullet** (P1b, PROGRAM.md §3.P1 item 3c,
  D-033). The LLM-assisted rewording lane had no check that a reword's content is actually traceable to the
  source; a fabrication like *"single-handedly re-architected … eliminating downtime"* passed the existing
  overmatch filter, which only vetoes ALLCAPS/entity additions.

  - **`reword_is_provenanced`** (`tailor/rewrite/provenance.py`) is a pure, deterministic allowlist: every
    content token in a reword must be a source token, an approved equivalence-table image, or a member of
    a closed, versioned connective allowlist of claim-free structural words (articles/prepositions/
    coordinators only). No stemmer and no modals/auxiliaries — both were shown to let fabrications through
    (verb→agent-noun via a shared stem; a future-commitment fabricated via `will`).
  - **Slots before the judge**, in both `run_tier_b_core` (the API lane) and `screen_candidates` (the
    no-API-key agent lane), so a fabricated reword never spends a judge call. A veto emits a new closed
    `drop_reason="provenance"` and keeps the deterministic Tier-A bullet.
  - **A separate `provenance_rejected` fabrication counter**, reported on its own funnel line and
    deliberately **not** folded into bar metric B4's numerator (`rejected = judge_rejected +
    overmatch_filtered`) — a conservative veto is not a caught fabrication.
  - **`LLM_LANE_VERSION` bumped `tier-b-1` → `tier-b-2`**, invalidating cached Tier-B outputs from before
    the gate existed.
  - **The honest cost:** the gate is deliberately aggressive — a benign synonym or tense variant
    (`optimize`→`improve`, `optimize`→`optimized`) is vetoed and reverts to Tier-A until the equivalence
    table is curated to permit specific swaps.

- **A hard résumé PDF gate — no lead ships without a compliant, compiled PDF** (P1a). Replaces 0.2.0's
  silent `"source only (no PDF; renderer not available or compile failed)"` degrade with a typed,
  fail-closed pipeline. (This gate was built against Typst and then ported when the engine changed —
  see *Changed* below. The description here is of the shipped, tectonic-based behaviour.)

  - **Binary-missing vs. compile-failure, split at the type.** A missing renderer binary on `PATH` is an
    environment fault that aborts the whole run fatal and exits the CLI
    non-zero with install guidance; a compile failure or a page-count overflow on one lead's résumé is a
    per-lead fault handled by the fallback below. Both are drawn from closed catalogs
    (`CompileReason`, `GateReason`) — never string-matched.
  - **Page count is a hard fail.** A new `resume_max_pages` profile column (default 1) is enforced on the
    compiled PDF, so a résumé that overflows the limit is rejected rather than shipped.
  - **Untailored-master fallback.** A tailored résumé that fails to compile or overflows the page limit
    falls back to rendering the untailored master; if that also fails, the lead is dropped with **no**
    `resume_tailored` row and **no** lead folder left behind — a plain compliant résumé beats none, and a
    dropped lead is invisible to the store rather than a half-written artifact.
  - **A compile log captured per lead**, including for a dropped lead (written to a durable
    `_failed/<slug>.log` before cleanup), so a fallback or a drop is always diagnosable after the fact.
  - **A slot-filled assertion** (`validate_slots`) runs on the tailored résumé right before render and
    fails the lead (routing into the same fallback) if tailoring stripped an entry down to nothing.
  - **The renderer is packaged, not just assumed installed.** The Dockerfile installs the pinned
    `tectonic` release binary, and `doctor` probes both presence and version, warning loudly on a
    mismatch rather than letting every lead silently fall back or drop.

- **`boardwatch verify`** — a standalone DB↔artifact reconciliation sweep (P0 item 5). Reads a run's frozen
  `funnel-<run_id>.json` off disk, re-queries the store independently for the run-keyed quantities that
  cannot legitimately change after the run finished (tailored-row count, PDF-built count, distinct lead
  count, exit status), and — the load-bearing check — confirms every run-keyed tailored artifact the DB
  records (`resume_tailored` and `resume_tailored_llm`) actually has a file on disk, reading
  `meta_json.pdf_uri` explicitly rather than guessing a sibling path. `verify --run <id>` verifies one run
  and exits non-zero with `NO_ARTIFACT` if no artifact exists for it; plain `verify` sweeps every
  `funnel-*.json` present on disk. Read-only; supplements Gate P0 rather than re-anchoring it (D-031).

- **A run manifest, a stub rate and fabrication counters in the funnel artifact** —
  P0 items 4, 6 and 8, batched because all three add a section to the same
  artifact.

  - **Manifest** (item 4): the versioned identity a run ran under, so two runs can be compared for
    reproducibility from the artifact alone — code fingerprint, `rules_hash`, `profile_facts_hash`,
    start/end and `runs.status`, all reused, plus two new hashes. `config_hash` covers the
    decision-relevant `Settings` fields over a **closed classification of all 21 `Settings`+`LLMTier`
    fields** that raises `UnclassifiedSettingError` on any unclassified field. `profile_row_hash` covers
    the five profile columns the ranker reads (`skills`, `target_titles`, `exclude_titles`, `locations`,
    `remote_only`) — none of which `profile_hash` covers, though `exclude_titles` drives the largest drop
    in the funnel. The one residual gap, the skill-taxonomy version, is named in the manifest note (D-030).

  - **Stub rate** (item 6): open postings with an empty JD body over the corpus head, one number every
    run — `None` over an empty corpus, never 0%. Expected near zero for structured ATS JSON; a non-trivial
    value is the signal a scraped source has appeared. The query uses SQLite's two-arg `trim` so a
    tab/newline-only body counts as a stub.

  - **Fabrication counters** (item 8, feeds bar metric B4): the Tier-B rewrite `drop_reason`s folded into a
    closed catalog, with the two truth-gate rejections (fail-closed entailment judge, deterministic
    overmatch filter) counted apart from the budget/error/no_candidate fallbacks. An unrecognised
    `drop_reason` lands in `other` and prints a FAILURE line rather than being absorbed silently.

- **A terminal exit status on every run row.** `runs.status` over the closed catalog
  `running | ok | failed`, so the ledger can separate "finished clean", "finished with errors",
  "crashed" and "still running". Out-of-catalog raises `UnknownRunStatusError` at the write site rather
  than being enforced by a `CHECK` constraint — adding one to an existing SQLite table costs a full
  rebuild, and six tables carry a foreign key to `runs.id`.

  **The column default carries the meaning.** A `SIGKILL` never reaches the pipeline's `finally`, so no
  code can ever set a terminal status for a killed run — whatever the column defaults to *is* what a
  killed run says. It defaults to `running`, leaving such a row saying `running` with `finished_at` NULL;
  a default of `ok` would launder a killed run into a clean one.

  Status tracks the run's `fatal` condition, not its error list: a run that loses one lead to a tailor
  failure is a successful run with an error. Tying it to `fatal` means the ledger's status and the funnel
  artifact's FATAL line cannot disagree about the same run.

  **Scope, stated rather than implied:** `running` with `finished_at` NULL means only *nothing closed this
  row*. A run in flight, a killed run, and a standalone lane that raised between minting its run and
  finishing it all share that signature; the run reaper above is what separates them.

  Two write paths were recording a *failed* run as `ok` and were fixed with it: the scan's own abort
  handler (under `boardwatch run` the scan is called outside the pipeline's `try`, so that handler is the
  only place a scan abort is ever recorded), and a *total* scan outage on the standalone path, which the
  pipeline already classified as fatal — so the same event reported `ok` under `boardwatch scan` and
  `failed` under `boardwatch run`.

- **Per-source outcome table in the funnel artifact.** Per watched board: open postings, `eligible`,
  `leads`, `applied` — plus a rollup by provider, since the question of whether direct-ATS-only can carry
  the volume is a question about providers and 118 board rows do not answer it at a glance.

  **`unique` and `assisted` both report `not instrumented`, never 0.** Both are dedup-attribution
  quantities: `assisted` credits a source that arrived *second* for a posting another source won. Postings
  here are 1:1 with jobs and each belongs to exactly one company, so there is no second source to credit.
  Reporting 0 would assert that no source ever arrived second — the naive
  attribution that, per job-apps' own handover, nearly cost it a working adapter.

  The denominator is every **open** posting a board owns, not what it listed this run: an unchanged board
  answers 304 and lists nothing while still owning hundreds of open postings.

  **One** total is re-swept per board and compared with the funnel's own figure: `leads`, whose two sides
  have genuinely different shapes (`COUNT(*)` of this run's `resume_tailored` rows against
  `COUNT(DISTINCT posting)` resolved through `posting_versions`), so a lead that resolves to no board fails
  the run's reconciliation. Neither way it can disagree is reachable through today's tailor path, so it is
  a guard against a future writer rather than live evidence — the artifact says so too. A second total over `eligible` was written and then deleted before merge: it
  grouped the same subquery the verdict stage counts, by a `NOT NULL` foreign key, joined on a primary key,
  so it agreed for every possible database state. `applied` is excluded for a different reason — summing
  per-board distinct job counts is not the global distinct count if a job ever spans two boards, which is
  impossible today only by accident of the current data.

- **The ranker now accounts for every posting it considered**, which is what makes the funnel's
  `shortlist` stage evidence rather than bookkeeping. It previously reported two of its **five** exits, so
  hard-filter vetoes, `--new` narrowing and everything below the `--top` cutoff all vanished — **15,959 of
  19,262 open postings** on a measured run at `--top 5`, of which 11,517 were hard-filter vetoes and 4,442
  were below the cutoff. All five exits are counted where the posting actually leaves, and `entered` is the
  ranker's own row count measured independently of them, so the stage's balance can genuinely fail. `boardwatch run` now
  prints how many postings were considered and how many fell below the cutoff.

- **Per-run funnel artifact, written on every `boardwatch run`.** Two halves — `funnel-<run_id>.json` and
  `funnel-<run_id>.md` — land in `<out>/<YYYY-MM-DD>/` beside that day's tailored résumés, outside the git
  tree. The Markdown names the board each lead came from, and every stage states its drop buckets with
  counts rather than leaving the reader to subtract. (As first shipped it did not account for every
  non-lead — postings ranked below the `--top` cutoff appeared in no counter at all. P0 item 3, above, closed that.)

  The funnel's head is the **open-posting corpus**, not the number of postings the scan listed. Those are
  different populations — a board answering 304 lists nothing, and `--no-scan` lists nothing at all — so
  scan counts are reported as context in their own block rather than as a funnel edge.

  Two stages carry reconciliations that can genuinely fail (`corpus` and `tailor`), plus two cross-checks
  that recount `tailored` and `leads_with_pdf` from the store rather than trusting what the pipeline
  reported. `attribution` and `verdict` are SQL partitions of the set they are compared against, so their
  balance holds for any input; they are labelled `derived` rather than presented as evidence.
  `leads_with_pdf` is read from `meta_json.typst_pdf_built` (a legacy key name — see *Changed*), not
  from a row count: `artifacts.uri` holds the résumé source path whether or not a PDF ever compiled.

  Stages that nobody has instrumented report **`null`, never 0**, because reporting 0 would assert a
  measurement nobody took. Stages that balance by construction are labelled
  `derived`, and the artifact prints which stages could actually have failed. The artifact
  also carries the abstain rate for **every** rule in the catalog (including the ones that have never
  fired) and the count of evaluations that carry no run at all, which is expected only to shrink.

  Written from the same `finally` that closes the run row, so a run that crashed partway still leaves a
  funnel explaining how far it got. A failure to write it is reported and never fails the run.

- **`boardwatch run` — one command that runs scan → eligibility → tailor under a single run.**
  Until now nothing in `src/` spanned the three stages: `runs` rows were inserted only inside the
  scan's file lock, eligibility was judged later as a side-effect of `top`'s preflight, and
  tailoring was later still and one posting at a time. The only thing stitching them together was
  a shell script outside the package. `boardwatch run` owns one run row across all three stages and stamps
  `finished_at` only after the last, so a run means the pipeline, not the scan. (The row itself is created
  by the scan stage, inside the file lock — see below.)

  Options: `--top N` (how many ranked postings to tailor, default 8), `--out` (root for the dated
  `<out>/<YYYY-MM-DD>/` folders), `--resume`, and `--no-scan` to reuse already-fetched postings.

  Exit 2 if another scan holds the lock. Exit 1 when the run is fatally broken — no profile, a **systemic
  scan outage** (boards attempted and not one completed, i.e. DNS/network rather than a few dead slugs),
  or **every shortlisted lead failing to tailor**. Exit **0 otherwise, including when SOME boards were
  unreachable or SOME leads would not tailor**: those are counted, printed and persisted, but they are the
  documented norm across 85 watched boards and `boardwatch scan` already treats them as success, and an
  exit status that is non-zero every day carries no information.

  The two fatal cases above are the ones that would otherwise be silent empty days. The general
  zero-output guard — deciding when producing nothing was *provably right* — is the separate entry above.

  A contended run writes nothing at all: the run row is created by the scan stage, inside the file lock,
  so on the default path there is no window in which the schema is migrated or a row inserted before the
  lock is held. (`--no-scan` acquires no scan lock at all, so it migrates unlocked exactly as every other
  read command does.)

- **`run_id` is now written on every evaluation and every artifact.** The column was added
  previously but nothing populated it, so it was NULL everywhere. It is now threaded through
  `run_eligibility` → `write_evaluation` → `record_evaluation`, through the opt-in LLM lane, and
  through `run_tailor` into all three artifact inserts.

  A stage invoked on its own — `boardwatch tailor run`, `eligibility run`, `top`'s preflight —
  mints its own run rather than writing NULL, so that **NULL keeps exactly one meaning: the row
  predates run attribution.** Those rows cannot be backfilled (the evaluation ledger is
  append-only), so preserving that single meaning is what lets a funnel report separate them from
  live work instead of silently mixing the two. To keep `runs` a ledger of work rather than a
  command log, the eligibility preflight mints a run only once it has something pending.

  A cache hit keeps the run that first produced the evaluation, and a reused master résumé
  artifact keeps the run that first authored it — in both cases no row is written, and claiming
  otherwise would erase the distinction the column exists to record.

- **`boardwatch eligibility abstain` — abstain rate for every rule in the catalog, including
  rules that have never fired.** `eligibility summary` groups the requirement rows that exist,
  so a rule that has never been detected produces no group and is invisible in it; that is
  precisely backwards, because a rule which cannot fire is the one worth knowing about. The new
  command enumerates from the rule catalog and joins the observed counts onto that enumeration.

  Three states are kept distinct: `never fired` (no rows, so the rate is undefined and is
  **not** reported as 0% — that would rank a rule which has never fired as the healthiest in
  the catalog), `100%` (fires and never decides anything), and a real rate. Requirement rows
  carrying no `rule_id`, or a `rule_id` the catalog does not declare, are reported as their own
  buckets rather than folded into a rule; an undeclared `rule_id` exits non-zero, since the
  catalog is closed.

  On the current database it reports that 7 of 44 rules have never fired and 17 more fire
  without ever deciding — among them every clearance rule that fires (105 detections, zero met
  and zero unmet) and `work_auth:no_sponsorship_offered`, which has abstained on all 1,052
  postings that stated they offer no sponsorship.

- **Nullable `run_id` on `eligibility_evaluations` and `artifacts`** (Alembic revision
  `run_attribution`, additive). `eligibility_evaluations` is append-only, so rows predating the column can
  never be backfilled and NULL means "predates attribution", never zero. *(Landed inert; the entry above is what populates it.)*

- **`boardwatch stats` — one read-only readout of where you stand.** Two views over your
  local database: qualified opportunities in a trailing window (`--days`, default 7),
  partitioned into `qualified` / `uncertain` / `ineligible` / `unevaluated`; and the
  discovery pipeline (seen → passes filters → not ineligible → tracked). The partition is
  deliberately honest — a posting with no current eligibility verdict is counted as
  `unevaluated`, never silently folded into `qualified`, so an empty eligibility ledger reads
  as "N unevaluated" rather than "0 qualified". Keyless and read-only; needs a profile
  (`boardwatch init`).

- **Workday support — a sixth provider, and the first with a composite board identity.**
  A Workday board is a host + tenant + career-site triple, so its target form is
  `workday:<host>/<tenant>/<CareerSite>` (pasting the career-site URL works too and derives
  the tenant). It is carried as a single composite slug, so `UNIQUE(provider, slug)` is
  unchanged and there is no migration — that constraint is in fact load-bearing here,
  because one tenant can serve several disjoint career sites. Site slugs are case-sensitive;
  hosts and tenants are normalized to lowercase.

  Workday's public API had to be measured rather than assumed, and every finding below has a
  regression test. It is POST-only (a GET returns 400), which is why `Fetcher` gained
  `post_json` — routed through the same per-host pacing and backoff, which matters because a
  2000-posting board is 100+ requests to one host. Its page size is a hard 20 (`limit=21`
  returns 400, it is not clamped). Its reported `total` is capped at 2000 while
  `offset >= 2000` wraps back to page 1, so pagination terminates on a short page rather
  than on `offset < total`, which would never terminate on a large board. And `timeType` is
  *not* an intern signal — it reads "Full time" on a real PhD-intern requisition — so the
  intern/new-grad signal is read from the `workerSubType` facet instead, via one bounded
  facet-filtered query per matched bucket, matched on the human-readable descriptor because
  the facet ids are tenant-specific. `timeType` and the matched descriptor are captured into
  `raw_json` because backfilling them would mean re-scanning every Workday board; nothing
  reads them yet.

  Two consequences worth stating plainly. Workday serves no `ETag` and no `Last-Modified`,
  so conditional fetches are inert for it and every scan re-reads the board. And no Workday
  boards are added to the bundled registry, so you watch them with `companies add` — until
  you do, `doctor` reports Workday connectivity as *not checked* rather than guessing.

  One deliberate deviation from the other five providers: `remote_policy` prefers Workday's
  structured `remoteType` field ("Fully Remote" / "Partially Remote") over the location-text
  heuristic, the same way the Ashby adapter already prefers its structured `isRemote`
  boolean. Tenants that do not set the field fall back to the heuristic.

- **Two eligibility rule families: `contract_not_fte` and `internship`.** The catalog now
  carries six families. `contract_not_fte` reads whether a posting declares a contract,
  contract-to-hire, temporary, fixed-term, 1099 or corp-to-corp engagement — or, symmetrically,
  permanent full-time employment — and resolves it against a stated employment-type
  preference (`fte_only`, `open_to_contract`, `contract_only`). `internship` reads whether a
  posting declares itself an internship or co-op and resolves it against whether you want
  them. Both are prompted by `init` and `profile edit` through the existing catalog-driven
  loop, so neither adds a question to maintain.

  Both default to `preference` rather than `blocker`, which is a measurement and not a
  guess: the patterns were tuned against 13,590 real postings and score 100% precision
  (internship) and 86% precision (contract) against the providers' own structured
  employment-type field. Only `blocker` can produce `ineligible`, so at the shipped default a
  false positive costs one visible informational row and hides nothing. Opt either into
  `blocker` with `eligibility policy set <family> blocker`.

  Known limit, stated plainly: the engine reads a posting's body and never its title, so
  internship recall is 27% of postings whose title names an internship, and 20% of those whose
  provider states an internship employment type. A posting titled "Software Engineering Intern"
  whose body never says so is not detected. Raising that needs the title in the engine's input,
  which is a separate change.

### Changed

- **`config_hash` moves**, because `seen_ttl_days` was added to `_CONFIG_RELEVANT` (P6 Slice 2). It is a P0
  artifact-v3 field and an input to the ledger's `policy_version`, so a run manifest written before this
  change is no longer hash-comparable with one written after. Recorded here because the changelog is
  authoritative for what shipped and a moved identity hash is not an implementation detail.

- **The résumé render engine is now tectonic compiling the user's own LaTeX template, replacing Typst**
  (résumé-tailoring fix, Increment 1 — D-058, D-060). Diagnosis found the tailored output read as a
  "plain-text dump" for two reasons: a five-line Typst stub preamble with no real page setup, and tailoring
  itself being near-invisible. Typst could only ever *approximate* the user's own template — a different
  typesetting engine cannot reproduce a LaTeX file byte-for-byte — so tectonic (a single ~30 MB LaTeX
  binary, the same footprint class as Typst) now compiles the résumé's real `.tex` source unchanged.

  - **`render/typst.py` and its tests are deleted.** A new `LatexRenderer` (`render/latex.py`) emits
    sections into `%%SECTIONS%%` markers in a bundled default template (`render/templates/resume_base.tex`,
    registered in `SHIPPED_DATA`); a user's own template installs to `{config_dir}/resume_template.tex` and
    overrides the bundled default. `_validate_template` now requires the `%%SECTIONS%%` markers to be
    present in the resolved template, so a malformed template fails loudly instead of degrading silently.
  - **Bolding moves to native inline `\textbf{}`**, matching the job-apps LaTeX pattern; entailment
    (`output_is_entailed`) strips markup before comparing tokens to the master, and any non-`\textbf{}`
    LaTeX command inside a bullet is a violation.
  - **Page count now reads `pdfinfo`** instead of a Typst-native metadata query.
  - **`Entry` gained structured fields** — `kind`, `title`, `dates`, `subtitle`, `location` — plus a new
    `Resume.extracurricular` section, so LaTeX subheadings (role/company/dates on one line, tech stack on
    the next) render correctly; entailment now checks all of them, not just `title`.
  - **The persisted meta key `typst_pdf_built` keeps its legacy name.** Renaming it would ripple into
    funnel/reconcile queries that already read it, which is out of scope for this change.
  - Header and Education stay template-hardcoded in this increment (job-apps-exact); single-sourcing them
    from `resume.yaml` is a documented fast-follow, not built here. Keyword bolding from `jd_skills`
    (Increment 2) and per-role authored title/summary selection (Increment 3) are each their own plan.

  **Result: a real authored résumé now renders to 1 page** (verified by a real compile plus `pdfinfo`),
  resolving the standing blocker where the old Typst stub rendered an authored résumé to 2 pages against a
  `resume_max_pages=1` limit and dropped every lead on every run. Note that a bullet long enough to overflow
  the per-lead layout gate's 220-character ceiling still degrades that lead to the untailored master, so
  `tailor validate` is worth running after editing `resume.yaml`.

- **A held scan lock now names the blocking process instead of a generic message** (P3, §3.P3 item 1,
  D-043). `run_scan` writes a message-only sidecar (`scan.lock.meta`: pid/hostname/started_at) around the
  existing `FileLock` acquire/release; on contention the error names the blocking pid, host, and start
  time, falling back to the unchanged generic message if the sidecar is missing or malformed. The sidecar
  is never a lock authority — `filelock` alone decides acquire/release — so a stale or corrupt sidecar only
  degrades the message, never correctness. `boardwatch scan`/`boardwatch run` now print the caught
  exception's own message instead of a hardcoded constant, so the pid-naming message actually reaches the
  CLI. Stale-reclaim was declined outright, not deferred (D-045) — unsound as designed, and the OS already
  reclaims a dead flock on process exit. Token-gated unlock remains deferred. The run reaper has since shipped (D-046, in *Added*).
- **LLM adapter calls now retry transient 429/5xx failures with backoff instead of dropping the rewrite**
  (P3, §3.P3 item 10, D-040). Both `AnthropicClient` and `OpenAICompatClient` classify a 429 or 5xx
  response as `LLMTransientError` and retry through a shared `llm/retry.py` helper (tenacity,
  `Retry-After` honored when the provider sends one, bounded at 4 attempts) before falling back to
  today's Tier-A-keeping containment on exhaustion. The retry lives inside the adapter's own request path,
  below the rewrite lane's per-call budget metering, so a retried call still costs exactly one budget
  unit. Any other non-2xx status, or an invalid response body, still raises the flat, non-retryable
  `LLMError` unchanged.
- **The systemic-scan-outage predicate is now one function, `is_systemic_scan_outage`
  (`scan/coordinator.py`), called by both the pipeline (`run_pipeline`) and the standalone
  `boardwatch scan`** (P3, §3.P3 item 4, D-037). Previously the same "attempted > 0, complete == 0,
  unchanged == 0" logic was written out twice; behavior is unchanged, this only removes the risk of the
  two copies drifting apart.
- **`show` now renders an `eligible` verdict that fired zero eligibility rules, one that fired and
  cleared all of them, and one that fired some non-blocking `preference`-family rows that were NOT
  cleared, as three distinct headers** (P2, §3.P2 item 6, D-036). Previously all three rendered as a
  bare "Eligibility: eligible" — "no flags" is not the same claim as "cleared", and a fired-but-unmet
  row is not "cleared" either, even when it did not block the verdict (D-035's five still-`preference`
  families). A new derived `AuditView.presentation` (`VerdictPresentation`, no schema change, stored
  `verdict` unchanged) now headers the three cases "eligible — no eligibility rule applied (not
  screened)", "eligible — N requirement(s) cleared" (only when every fired row is `met`), and
  "eligible — N requirement(s) evaluated (M cleared; see details)" for the mixed case.
- **`work_auth`'s default severity is now `blocker`, not `preference`** (P2, §3.P2 item 7, D-035). Every
  eligibility family previously shipped `default_policy: preference`, so a fresh, policy-less profile got
  **0 `ineligible` verdicts ever** — the multi-tenancy requirement failing for anyone who had not
  set `work_auth: blocker` by hand. `work_auth` is the canonical hard-stop family (bar metric B7),
  the most-developed, and keystone-gated (it abstains to `uncertain`, never `ineligible`, when
  `work_authorization` is undeclared), so it is the one family safe to flip today; the other five
  (`experience_years`, `clearance`, `degree`, `contract_not_fte`, `internship`) remain `preference`,
  opt-in, pending further review.

- **Funnel artifact version 1 → 4 over this release**, adding the `sources`/`source_totals`
  sections (v2), the run manifest, stub rate and fabrication counters (v3), and the `liveness`
  block (v4). A consumer pinned to v1 needs updating.

- **`boardwatch doctor` now says "a run is in progress" rather than "a scan is in progress".** Since run
  attribution, an unfinished run is also a `boardwatch run` still tailoring or a standalone eligibility
  pass still judging — the old wording sent users looking for a held scan lock that was in fact free.

- **Ranking: a title role gate, and a neutral coverage for postings with no recognized
  skills.** These are one change in two parts, and they only work together — see below.

  A posting with no recognized skills used to have its `skill_coverage` component dropped and
  the remaining weights renormalized. That is not neutral: renormalizing is arithmetically
  identical to imputing the *weighted mean of the surviving components*, so dropping a
  component promotes a posting whenever that component would have scored below the rest.
  `skill_coverage` carries half the total weight and is undefined for about 18% of open
  postings, so the effect was large — a posting with **zero** recognized skills and a perfect
  title scored 0.9586 while a posting matching **7 of 8** skills scored 0.9168. §3.6 asks for
  "neutral, never a punitive 0 or free 1"; the old behaviour delivered the free 1 (29 of 80
  eligible zero-skill rows scored exactly 1.000). Coverage is now imputed at a neutral
  `zero_skill_coverage_prior` (default `0.50`, configurable), which puts that posting at
  0.7293 — exactly what a real 4-of-8 posting scores — and leaves the 7-of-8 row above it.
  `skill_coverage()` itself is unchanged, the assumption is named in `show` and in the one-line
  `why`, and the profile-side empty case still renormalizes.

- **`top` and `notify` now skip postings whose TITLE is not a software role.** Fuzzy title
  overlap cannot separate roles: Intel's "On Shift (IOS) Technology Development Engineer"
  matched the target "iOS Engineer" through the literal "(IOS)" token and ranked **first** at
  1.000. A categorical gate (`rank/role_gate.py`) runs beside the score and returns
  `swe` / `not_swe` / `uncertain`. `uncertain` passes through to scoring completely unchanged,
  which is why the gate keeps 100% of software-titled postings whose skills the taxonomy
  missed. A body-text gate was measured and rejected: those postings have long bodies
  genuinely empty of technical nouns, so no threshold separates them from noise.

  **A `not_swe` verdict is never silent.** It is counted in `top`'s footer, listed in `stats`,
  shown by `show <id>`, and viewable with `top --include-non-swe` — always carrying the exact
  title text that vetoed it. A gate you cannot audit is how a real job disappears unnoticed.

  Order inside the gate is load-bearing. The deny patterns guard themselves with
  `(?!.*\bsoftware\b)`, and a negative lookahead only sees text to its right, so evaluating
  denies first vetoes "Software Quality Engineer" — it matches `quality engineer`, looks right,
  and misses the "Software" on the left. Sixteen real software titles were buried that way in
  the prototype. Checking the software rescue first fixes all sixteen at no measured precision
  cost and runs 2.3x faster. Regression tests pin the ordering.

  Measured on 515 labelled postings: noise vetoed 76/76, targets kept 1.00, protected
  software-titled zero-skill rows kept 1.00, P@20 1.00, P@50 0.89 -> 1.00. The two changes are
  coupled: the imputation **alone** takes P@50 to 0.53, because it demotes the protected rows
  while leaving one-spurious-skill noise in place.

  Known and filed, not fixed: skill *extraction* precision is the root cause of the underlying
  symptom — "Deal Strategist" is tagged `Concurrency`, "Asset Tracking Technician" `Real-time`.
  That is separate work.

- **Extraction precision: four generic buzzwords dropped from the skill taxonomy.**
  `skill_coverage` is `|profile ∩ posting| / |posting|`, so a posting whose only recognized
  skill is one the profile also has scores a perfect 1.0. Four taxonomy tokens —
  `Scalability` (`\bscalab(le|ility)\b`), `Concurrency` (`\bconcurren(cy|t)\b|multi-thread`),
  `Real-time` (`\breal[- ]time\b`) and `Agile/Scrum` (`\bagile\b|\bscrum\b`) — matched
  non-technical prose ("scalable business processes", "multi-threaded deals", "real-time
  locating systems", "agile environment"). Each is in the profile, so as a posting's sole
  recognized skill it drove `skill_coverage` to 1.0 on ops/finance/sales roles the role gate
  correctly leaves `uncertain` (e.g. "Commercial Contracts Specialist", "Accounts Receivable
  Manager", "Deal Strategist"). On the live database this affected 257 such postings; 249 are
  non-software roles now dropped to the neutral zero-skill prior, and only 8 are genuine
  software postings (which the role gate keeps visible regardless). None of the four is ever
  the sole recognized skill on a labelled TARGET posting, so removing them costs no target
  coverage. Real, discriminating tokens — including `SQL`, `Distributed systems`,
  `Low latency / high throughput` and `High availability` — are untouched.

- **Editing the rule catalog re-evaluates every stored verdict.** Adding the two families
  moves `rules_hash`, so the first `eligibility run` after upgrading re-evaluates the whole
  corpus and writes fresh rows. Prior verdicts are superseded, never rewritten — the
  eligibility tables remain append-only.

### Fixed

- **A posting whose URL redirects to a dead page is no longer withheld as gone** (D-113). The fetcher
  follows redirects, so a `302 → 404` chain reported a bare 404 and the liveness probe read it as the
  posting itself being gone — which would have hidden every live requisition of an employer whose old
  ATS links point at a new host with a dead deep-link path. Only a gone-status from the URL actually
  asked about withholds a lead now; a redirected one is served, under its own signal so it stays
  countable. Relatedly, a `Liveness` verdict its signal does not sanction can no longer be constructed
  at all.

- **`top` no longer hides why the list is empty** (D-113). When suppression removed everything, the
  human-readable output printed "no open postings match your filters" — a claim that the corpus is
  empty — and returned before naming what was hidden or how to see it. The duplicate, handled and
  applied notices, each of which names its own drain, now print on that path too. The `--json` path had
  the opposite half of the same defect — it printed before returning but named only two of the five
  buckets — and now shares one code path with the human one.

- **`boardwatch doctor` now probes for `pdfinfo`, not only `tectonic`.** poppler is as hard a dependency
  as tectonic — without it the page-count gate cannot answer and every lead is refused — but nothing
  checked for it, so a user with tectonic and no poppler got an empty run every morning and a `doctor`
  that reported healthy. `doctor` exits non-zero if either binary is missing, and the README now names
  both as prerequisites.

- **`config show` and `config set` now reach every setting.** Six of the ten scalar settings —
  including `seen_ttl_days`, which governs how long a lead you were shown stays out of the shortlist —
  were absent from the command's key registry, so `show` did not print them and `set` rejected them as
  unknown keys. They could only be changed by hand-editing `config.toml`, which is exactly what the
  settings surface exists to avoid. `busy_timeout_ms`, `reap_stale_after_hours`, `location_filter_mode`,
  `zero_skill_coverage_prior` and `recency_half_life_days` were the others. A test now asserts the
  registry covers every scalar field, so it cannot drift again.

- **The funnel artifact keeps reconciling when liveness withholds a lead** (D-111, from the Slice 3
  review). The tailor stage entered at `shortlisted` and advanced at `tailored` with `tailor_failed` as
  its only drop, so a withheld lead left a gap in a stage that is deliberately not `derived` — meaning any
  run where liveness did its job emitted an artifact stamped DOES NOT RECONCILE, breaking Gate P0's
  "three consecutive runs that reconcile to 100%" clause. The stage now carries a `withheld_not_live` drop.
- **A day where every candidate was already applied to no longer fails the run** (D-111). Applied state is
  checked ahead of the ledger, so those candidates left `hidden_handled` — the bucket the zero-output guard
  reads — and landed in `hidden_applied`, which it did not, re-arming the guard on exactly the
  steady-state day the `hidden_handled` clause was added to disarm.
- **A day whose whole shortlist turned out to be dead is reported as an honest empty day, not a broken
  résumé path** (D-111). Liveness withholding every lead would otherwise have tripped both the
  "every lead failed to tailor" fatal, which counted a withheld posting as a render failure, and the
  zero-output guard, which could not explain a run that judged new eligible postings and produced nothing.
  A withheld posting is also removed from the cohort guard's set rather than added to its accounted set —
  it is a third terminal state, neither a lead nor a render failure — and is dropped from
  `surfaced_job_ids`, so a lead delivered to nobody cannot consume the `seen` queue.

- **Only a caller that DELIVERS a lead consumes the queue** (D-110, from the Slice 2 review). The `seen`
  write had been applied to every `rank_open_postings` call, and three of the four production callers deliver
  nothing: `eligibility gate request` suppressed the shortlist it had just built for judging, so the
  `boardwatch run` the handshake exists to feed shortlisted **0** for the whole TTL and the verdicts never
  reached an artifact; the pipeline wrote `seen` *before* the tailor loop, so a missing `tectonic`, an invalid
  persona or a Ctrl-C hid every shortlisted lead for seven days with nothing built, and the documented retry
  re-ranked into an empty shortlist; and `bwd`, which ranks twice a day, suppressed the rows its own build
  call was about to request and built zero folders while printing "nothing new to build".
- **A transient render failure no longer deletes a lead permanently** (D-110). A non-zero `tectonic` exit
  (cold support-file cache with no network, disk full, OOM) maps to `shippable=False` exactly like the page
  limit, so it earned a permanent `skipped` — and no `policy_version` component covers the résumé or
  `resume_max_pages`, so `ledger reopen --stale` could not bring those leads back either. `LeadArtifactError`
  now carries both gate reasons as data and only the closed `DETERMINISTIC_GATE_REFUSALS` catalog earns a
  permanent disposition; anything else is retried.
- **Regrouping carries the ledger decision onto the canonical job** (D-110). Moving postings off a job left
  its `built` row governing a job nothing anchors while the canonical job carried nothing, so the
  already-built lead was surfaced and tailored again — the exact defect Slice 2 exists to remove, arriving
  through the projection Slice 2 added. The decision is carried forward monotonically and the emptied row is
  released, so no live row is left with no re-entry path.
- **`job_grouping_events` records only moves that happened** (D-110). A plan built against a stale read
  appended a trail entry whose guarded `UPDATE` then matched 0 rows, so the table D-104 names the undo path
  could not in fact rebuild the projection.
- **The run summary names `hidden_handled`** (D-110). `_zero_output_guard` had been widened to stop fataling
  on an already-handled shortlist, but the operator's one-line summary omitted the bucket, printing
  "0 shortlisted of 400 considered (0, 0, 0, 0)" and exiting 0. `top --json` now reports the bucket on stderr
  before returning, so a script no longer receives `[]` with no reason.

- **Duplicate suppression no longer switches itself off when a scan discovers a posting** (D-105, closing
  D-098). `write_identities` had exactly one caller in `src/` — the manual `boardwatch identities backfill`
  — so any run that discovered one new posting left it uncovered, `identities_complete()` went False, and
  suppression silently stopped corpus-wide, making `hidden_duplicate == 0` mean "not measured" on
  essentially every real run. Identities are now written **per posting inside the board's existing scan
  transaction**, so a posting and its identity commit or vanish together and the cost is O(postings this
  board listed) rather than a second corpus-wide `body_text` load. A retitle with an unchanged body — which
  moves an identity key without producing a revision — is covered by the same call.
- **The zero-output guard no longer calls a caught-up queue a failure.** A run can judge genuinely new
  eligible postings and still produce 0 leads because every candidate is already `built`; the guard now
  fires only when `eligible_judged_this_run > 0` **and** nothing was suppressed as handled. Without this the
  daily driver's exit status would have been 1 every day once the queue caught up, destroying the signal the
  run ledger exists to carry. A run with no handled candidates still cannot explain itself and still fires.

- **Disjunctive experience-years over-fire — Gate P5 MET at 100% precision** (D-073). The `experience_years`
  family's `total_years_minimum` / `range_years_minimum` patterns read the pure-years arm of a DISJUNCTION
  ("a Bachelor's degree … **or** N years of experience") as a hard floor, so a master's-plus-one-year
  candidate was told INELIGIBLE on a posting they clear via the degree path — deleting a real job, the
  unrecoverable direction. Both patterns now carry `abstain_by: [&degree_alternative_to_years]`, so a
  degree-gated alternative makes the years bar ABSTAIN (verdict `uncertain`) instead of resolving `unmet`,
  mirroring the degree family's "degree OR equivalent experience" handling. On the 173-row labeled set this
  moved exactly one verdict (the SpaceX false positive, `ineligible → uncertain`), taking INELIGIBLE
  precision 16/17 → **16/16 (100%)** with recall unchanged and zero span violations, so
  `boardwatch eligibility score` now exits 0. `abstain_by` is document-scoped (like the degree precedent);
  the recall the abstain concedes is the two-stage gate's (D-071) to recover.

- **The per-lead layout gate no longer runs on the untailored master résumé, and can no longer drop a lead
  on layout alone** (D-055, Opus 5 checkpoint review, fix 1 — HIGH). As first shipped, item 5a's gate also
  ran on the master fallback and reused a *selection* cap (`MAX_BULLETS_PER_ENTRY`, which bullet selection
  trims *to*) as a *layout* invariant; a low-`jd_skills` posting made `tailored == master`, both failed
  identically, the master-fallback rescue did nothing, and the lead was dropped where before P4 it would
  have shipped the author's real résumé — breaking the "master fallback is unconditionally shippable" guarantee.
  The per-lead gate now applies to the tailored and Tier-B renders only; a genuine compile failure on both
  sides is the only remaining way a lead drops. Master-authoring defects are now caught separately, once,
  at load instead (D-056, above).
- **A valid single-combined-line résumé header (e.g. "Name · email · site") is no longer rejected as
  missing a name** (D-056, fix round). `validate_master`'s original `len(resume.header) < 2` check assumed
  a ≥2-line header as if it were schema rather than a scaffolding convention; fixed to check only that the
  first header line is non-blank, decoupled from line count.
- **A Tier-B rewrite's recorded lineage hash now points at the Tier-A bullet actually shipped, not at a
  possibly-rejected tailored render** (D-055, fix 2). `tier_a_content_hash` was capturing whichever render
  happened to run first rather than the shipped `chosen_hash`.

- **`companies import` now rejects duplicate `provider:slug` rows.** It built validated
  entries but never ran the catalog's `validate_entries` integrity check, so a file listing
  the same board twice imported silently.

- **`httpx.TooManyRedirects` and `httpx.DecodingError` now surface as `FetchFailure`.** Both
  are `RequestError` but not `TransportError`, so they escaped `Fetcher`'s conversion and
  every provider's `except FetchFailure`, which let a redirect loop traceback `doctor`
  instead of reporting an unreachable board. Only the conversion widened — the retry
  predicate is unchanged, so these fail fast rather than being retried.

- **A provider that raises is contained to one board.** `scan` and `doctor` guard the
  per-board `board_url()` / `healthcheck()` calls, so a single malformed stored target no
  longer aborts the whole run. `doctor` also stops reporting a provider it never probed
  (no watched board and no registry entry) as unreachable.

## [0.2.0] - 2026-08-04

### Added

- **`boardwatch tailor` command (`init`/`validate`/`run`).** Tailors an authored,
  structured YAML résumé (`{config_dir}/resume.yaml`, scaffolded by `tailor init`)
  against one posting's extracted JD skills: deterministic bullet selection plus
  whole-token synonym substitution from a small, bundled, frozen equivalence table —
  never free-text generation. A no-fabrication guarantee re-verifies the output against
  the master résumé before anything is written, rejecting rather than degrading on
  failure. Renders Typst source and a best-effort PDF (local `typst` binary, if present)
  to `{data_dir}/tailored/`. Tier A: local-only, no network, no LLM. `profile.text` from
  `boardwatch init` is never imported into a tailored résumé.
- **`tailor run --tier-b` (alias `--llm`), opt-in LLM résumé rewording.** Off by default;
  requires `llm.enabled` and `llm.resume_tailoring` (a new key reusing the existing
  `[llm]` block — no new config keys or secrets) plus `BOARDWATCH_LLM_API_KEY`. Per
  bullet, a proposed rewrite is kept only if it passes a deterministic overmatch filter
  and a fail-closed entailment judge (blind to the job description); anything else falls
  back to the Tier A text for that bullet. This is evidence, not proof — unlike Tier A's
  no-fabrication guarantee, Tier B output is not structurally verified. Writes the plain
  Tier A file alongside a second, clearly marked `resume_tailored_llm` artifact/file with
  a `rewritten_from` lineage edge back to the Tier A artifact; reworded bullets are
  annotated `// reworded (Tier B)` in the rendered source. Tier A itself never calls a
  model, regardless of Tier B's settings.
- **`notify` command.** Pushes NEW matching postings to enabled channels since the last
  `notify` run; a standalone sibling of `digest`, chain it after `scan` (`boardwatch scan
  && boardwatch notify`). Two zero-new-dependency channels, both off by default: a webhook
  (one dual-key payload that renders on Slack, Discord, or a generic consumer, enabled with
  `config set notify.webhook_enabled true` and a URL from `BOARDWATCH_NOTIFY_WEBHOOK_URL`
  in the environment only, never in `config.toml`) and a best-effort desktop notification
  (macOS/Linux, enabled with `config set notify.desktop_enabled true`, degrading non-fatally
  elsewhere). `--dry-run` previews without delivering or advancing the notify cursor.
- **Workable and SmartRecruiters providers.** boardwatch now covers five keyless ATS
  providers: Greenhouse, Lever, Ashby, Workable, and SmartRecruiters.
- **`detail_fetch_budget` setting.** Caps how many unseen postings SmartRecruiters'
  per-posting detail fetches will pull in a single scan (default 50, range 1-1000, takes
  effect next scan).

## [0.1.0] - 2026-08-01

First public release.

### Added

- **Job radar over official ATS APIs.** Watch company boards on Greenhouse, Lever, and
  Ashby. No scraping, no credentials, no accounts.
- **Change detection.** `digest` reports what is new, reopened, updated, or closed since
  your last run, and `top --new` limits ranking to postings you have not seen.
- **Deterministic eligibility engine.** Work authorization, experience, clearance, and
  degree requirements are extracted with auditable rules, and every requirement it surfaces
  cites the exact job description span it came from. No model is involved in the default path.
- **Persisted eligibility audit trail.** `show` renders a per-posting verdict with its
  supporting evidence, so a decision can be re-checked later rather than taken on trust.
- **Ranking against your profile.** `top` scores open postings, with a live component
  breakdown available in `show`.
- **Application tracking.** `track` records your own funnel state per job.
- **Data portability.** `export` writes every open or tracked posting with its verdict and
  funnel state as JSONL or CSV. `top --json` emits machine-readable rankings.
- **Opt-in LLM eligibility extraction.** Disabled by default. When enabled, the model acts
  only as a span locator: it returns verbatim job description quotes, every one of which is
  validated as a literal substring of the source before use. Fabricated citations are
  dropped. LLM findings are advisory and can never produce an "ineligible" verdict.
- **Local-first storage.** Its primary store is one SQLite database in your platform
  data directory; the opt-in LLM tier also caches raw responses there as plain files on
  disk. Overridable with `--data-dir`. No server, no cloud, no telemetry.
- **`doctor`** for connectivity, per-board health and freshness, and database integrity.

[0.3.0]: https://github.com/mit112/boardwatch/releases/tag/v0.3.0
[0.2.0]: https://github.com/mit112/boardwatch/releases/tag/v0.2.0
[0.1.0]: https://github.com/mit112/boardwatch/releases/tag/v0.1.0

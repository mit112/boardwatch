# STANDING FACTS — what a fresh session should not re-derive

> Split out of `STATE.md` (D-139), which had grown to twice its stated length and was being read past.
> **`STATE.md` is still the read-first file**; this one is reference, read by section when you are about
> to touch the thing it describes.
>
> Claims only — the reasoning is in the cited decision, which is the point of the archive split. **Read
> the decision before changing the behaviour it describes.** If a fact here disagrees with the repo, the
> repo wins: fix this file and note the correction in `DECISIONS.md`.

| Section | Read it before |
|---|---|
| [Gates and process](#gates-and-process) | running a gate, committing, or dispatching an agent |
| [Gate A internals](#gate-a-internals) | touching `src/boardwatch/profile_bundle/` |
| [Liveness and the ledger](#liveness-and-the-ledger) | touching liveness, dedup, suppression or applied state |
| [The live store](#the-live-store) | anything that reads or migrates the real database |
| [Environment](#environment) | your first command in a new session |
| [Process lessons](#process-lessons-this-program-paid-real-time-for) | mutation testing, merging branches, reviewing |

---

## Gates and process

- **A docs-only commit owes `make generalization index-check`; anything else owes full `make check`** (D-116,
  resolving D-014). The boundary is the file extension, and `DATA_SUFFIXES` has **eleven** members —
  `.yaml .yml .json .jsonl .csv .tsv .toml .tex .typ .txt .mako`. `.md` is outside it; `.toml`, `.txt` and
  `.tex` are **not**, so they get no discount.
- **Two tests DO read the real `docs/` tree, and that is why the discount is sound** (correcting D-116's
  stated premise, which was "no test reads a `docs/` file" — D-140). `tests/generalization/test_real_tree.py`
  asserts `run(REPO_ROOT) == []`, and `tests/unit/test_program_index.py` runs the index checker with `cwd` at
  the repo root and asserts it exits 0. Each asserts **exactly** what one of the two owed commands asserts,
  so the short set is not a gap. **The discount breaks the day a test asserts something about a doc that
  `generalization` and `index-check` do not** — a link checker, a line-count cap, a spell check. Check for
  that before relying on it, rather than re-reading the premise.
- A doc in this program never quotes an exact catalog count, because no test can pin one and a stale number
  in a read-first file is worse than no number.
- **The gate runs in parallel and costs ~4½ minutes, not ~17** (D-150). `-n auto` is passed by
  `Makefile`'s `test:` target and `ci.yml`'s test job — **deliberately not in `addopts`**, because the
  `perf` job shares that config and measures wall-clock timings. `release.yml` inherits it through
  `make check`, which is intended. Two consequences worth knowing before reading a gate log: pytest is
  **~99% of the gate** (the other four phases cost about two seconds combined, so optimising them is
  worthless), and **xdist's summary drops the `1 deselected` tally** — reconcile counts against the
  `[N items]` figure instead. For a readable traceback while debugging, run serial with `-n 0`.
- **`make check` is the only gate for this repo's correctness** — pytest + ruff + mypy green is *not* green.
  Run it in a **detached worktree pinned to a sha**, capture the real exit code, never pipe it through
  `head`/`tail` (SIGPIPE gives a false negative — observed live giving a false `EXIT=0`), end a
  backgrounded gate with `exit $ec`. `All checks passed!` is the *lint* step and appears while pytest is
  still running; only `GATE_EXIT` and the pytest summary are the verdict.
- **Green locally ≠ green CI** (D-117), but the gap is **`gitleaks` and `perf` only**. `generalization` is
  inside `make check` and runs CI's exact command; the "three CI-only jobs" phrasing was wrong.
  `gitleaks git --log-opts=origin/main..HEAD` before a push is the cheap mitigation, not yet wired in.
- **Put the commit inside a guard that reads the check's exit code** — `if uv run ruff check . && uv run
  mypy --strict src tools; then git add <paths> && git commit …; fi`. Committing before reading an exit code
  shipped a `$HOME` path into a tracked file, a stale program index and a ruff failure, on three separate
  occasions in one session.
- **Re-check an agent's branch for late commits before gating.** A fix agent reported 10 commits after 9 had
  been merged; the gate was killed at 42% and restarted because the tree being gated was not the tree meant.
- **After appending to `DECISIONS.md`/`METRICS.md`, add the index row and run `make reindex`** — line numbers
  drift on any edit above a heading, and `make check` fails on a stale index (D-109).
- **The per-task fast-check set must include `test_store.py` and `test_schema_head.py`** for anything touching
  `tables.py`, a migration or the Alembic head (D-099). A new migration must bump the pinned head explicitly.
- **A violating fixture is assembled at runtime so the literal never exists on disk** (D-115, D-117) — for the
  generalization checker *and* `gitleaks`; both protect the repo's **bytes**. Never add a
  `HOME_PATH_EXCEPTIONS` row for a fixture: it excuses the string repo-wide and 31 shape tests assume those
  tables are empty. `.gitleaksignore` entries are fingerprint-pinned, excusing one blob rather than a pattern.
- **The tectonic pin has two homes and now a detector** — `Dockerfile`'s `ARG TECTONIC_VERSION` and the
  `setup-typesetting` action's default; `tests/unit/test_typesetting_pin.py` fails on drift (D-116).
- **`AGENTS.md` records no phase standing, test count or coverage figure, on purpose.** `STATE.md` is the only
  source of standing. `.agent/` and `.superpowers/` are gitignored working material; `CHANGELOG.md` is
  authoritative for what shipped. Review records that must outlive a session go in `.agent/`.
- **A finding's tier belongs to the OPERATION, not the code alone** (D-134). `tier_of()` is the catalog
  default; `outcome_with` reading `finding.tier` is correct. Every call-site override must carry a comment
  naming the operation-specific reason. `_TIER_RANK` is error 0, blocker 1, warning 2, information 3.

---

## Gate A internals

- **A closed review loop is evidence about the slices reviewed, not about the subsystem being
  defect-free** (D-161/D-162; carried here as D-149's fourth prerequisite so it survives the `STATE.md`
  trim, since STATE was the only place holding it). Earned, not cautionary: two silent-success defects
  (D-138/D-142, D-141) were found *after* the loop closed, in code six reviews and four gates had already
  passed. Gate A reading **MET** (D-157, green on all twelve CI jobs at `8475319`) says its slices were
  reviewed; it does not say the subsystem is clean.
- **`_root`, `.` and `..` are ESCAPED by the encoder, never refused** (`%5Froot`, `%2E`, `%2E.`). Refusing
  makes a legitimate document unenumerable. `normalize_locator` keeps a `.`/`..` guard for raw *paths*, where
  the same spelling means traversal (D-120, D-125).
- **The `_root` reservation is global on purpose**, and **`is_normalized_locator` is deliberately WEAKER than
  `emits_locator`** — it also serves owner-authored scope locators, so tightening it strands every legitimate
  selected scope.
- **The uniform JSON envelope on all twelve T18 commands is RIGHT** — both lenses upheld it independently. The
  **design text (§19) is what is wrong**; T19 amends it. `report_json`/`report_text` were production-dead and
  are deleted.
- **A two-document write is NAMED, not made atomic** (D-137). POSIX cannot rename two paths as one operation;
  a journal only moves the window; merging the documents would break the closed 33-document grammar. Hence
  `PARTIAL_EDIT_APPLIED`, deliberately **outside** `COULD_NOT_COMPLETE_CODES` because exit 3 would invite a
  retry guaranteed to refuse. The `rebase-draft` precedent for "two renames are fine" is **withdrawn** —
  those rename directories and stage no temporaries.
- **A missing bundle root is `bundle_not_found` on all twelve commands** (D-138, D-142). It is stated in
  **three** places, not one, and that is the fact worth knowing: `require_confined_root` (which
  `must_exist=True` makes the default for every reading surface, `init_draft` being the single opt-out),
  the pre-lock `is_dir()` checks in `promote` and `rebase-draft` (which must precede `filelock`, or it
  creates the directory), and `authoring._draft` plus the CLI's `_draft_tree` — because `add-evidence`,
  `resolve-conflict`, `approve` and `validate --draft` **reach no function that confines the root**.
  D-138 originally claimed one shared entry point covered the surface; it covered eight of twelve.
- **The guard asks `is_dir()`, never `exists()`.** A regular file, a device or a dangling symlink at the
  root all exist and are not bundles, and under `exists()` `inventory` reports a file root as a clean,
  empty bundle at exit 0. `is_dir()` also answers `False` for a symlink loop, which is why the refusal
  precedes `resolve()` — a loop used to escape as `RuntimeError` past every handler, carrying an absolute
  path. Both arms are pinned; only the file arm kills the `exists()` mutation.
- **`STATE_REFUSAL_CODES` has no production reader.** All thirteen members are documentation, so a code's
  membership in it cannot be wrong in a way any test can see. Do not treat that set as a mechanism.
- **The YAML `!!`-tag content-addressing bypass is CLOSED, not open.** `compose_node` refuses every explicit
  node tag; verified by probe (`!!omap` duplicate-key smuggling and `!!python/object/apply` both refused,
  plain YAML still loads) and by mutation (disabling the guard turns 12 tests red).
- **`METRIC_REVIEW_MISSING` is DELETED and metrics get no review interval** — a metric's freshness is its
  `reviewed_at` date alone (D-115, Mit's ruling). §20.6's clause binding an owner's approval to promoted
  content must fire for **every** revision, not only the first.
- **`Path.resolve()` on a symlink loop differs across the interpreters CI runs** — 3.11/3.12 raise
  `RuntimeError`, **3.13 returns the loop's own path**, which satisfies an equality check and admits the
  escape. Confinement therefore refuses on `is_symlink()`. **Keep a worktree on 3.13** — free cross-version
  coverage. `uv run --python X` inside the repo root **silently replaces `.venv`**; repair with
  `uv venv --clear --python 3.12 && uv sync --reinstall --all-groups`.
- **Import fixtures as `from tests.<package>.conftest import ...`, never bare `from conftest import`.** A bare
  import binds whichever `conftest.py` loaded first — under the full suite, `tests/unit/conftest.py`. This
  shipped in T15 and survived two lenses and a fix round; it is invisible to any narrow run.
- **The packaged example validates at 8 blocker, 0 error, exit 1.** That satisfies Gate A, whose clause is
  that the layers *run*, and **not** Gate B's separate "zero undispositioned blockers".
- **All three sites of the blocking-`open()` class are now closed.** A non-regular file is refused for a
  blob store entry (`storage._require_stored_blob`), for a compared tree (`storage.identical_trees`) and for
  a bundle **document** (`layout.discover_source_files`, D-141) — the last being the one that hung
  `validate --draft` and `promote` forever, `promote` while holding the bundle lock. The guard belongs at
  `discover_source_files` because every reader downstream of it (`load_documents`, promotion's verbatim
  copy, `checkout`'s tree copy) opens what it returns and none of them takes a timeout. **A fourth site is
  any new code that opens a path the layout did not hand it.**
- Upstream of T18 and deliberately not chased: a typo'd `--bundle` made `inventory` report clean at exit 0
  (**fixed**, D-138); `context.py:92` and `blobs.py:175` are deferred pre-existing `$HOME` leaks.
- `docs/superpowers/` holds the design and plan and is **tracked** (12 files under `git ls-files`), so a new
  worktree already has it. The directory that is untracked is the dotfile **`.superpowers/`**, excluded via
  `.git/info/exclude`, and that is the one a worktree needs copied in (D-171 corrects the conflation).

---

## Liveness and the ledger

- **Only a caller that DELIVERS a lead may consume the queue** (D-110). `eligibility gate request` and the
  pipeline pass `record_surfaced=False`; `top --no-record` is the operator's opt-out. The pipeline writes all
  three ledger tiers *after* the tailor loop. Do not move the `seen` write back into the ranker.
- **Liveness is never cached, and "never" includes `postings.status`** (D-111). One 404 from a flaky CDN would
  otherwise retire a live requisition **irreversibly**. That column belongs to the scanner's
  `CLOSE_AFTER_MISSES = 2` rule, which works: 0 open postings are stale beyond 7 days.
- **Only 404/410 withholds a lead, and only from the URL asked about** (D-111, D-113). Timeout, 403, 5xx, a
  redirect and a NULL URL are all `unknown`. A live Pinterest posting answers 403 to an unfamiliar user agent.
- **`Fetcher` sets `follow_redirects=True`**, so a `302 → 404` chain arrives as a bare 404, and
  `FetchFailure.redirected` is the only thing distinguishing a posting that is gone from one whose old link
  points at a dead path on a new host. The single most likely thing to be undone by accident.
- **"Gone" means the URL asked about said so, not where it redirected** (D-113). `refetch_gone_after_redirect`
  is a **subset of `unknown`**: that count climbing while `dead` stays 0 is the detector **disarmed**, not a
  healthy corpus. `tests/unit/test_liveness_prober.py` is the only module driving the real `Fetcher` — its two
  redirect cases are the sole coverage; do not delete them as duplicates.
- **A `Liveness` verdict must be the one its signal carries** (D-113) — `dead` is reachable through
  `refetch_gone` and nothing else. **An unprobed run reports liveness as UNMEASURED, never 0 dead** (D-111);
  `run --no-check-liveness` opts out.
- **Applied state is read from `applications`, never mirrored into the ledger** (D-111). `interested` does not
  suppress (it is `track add`'s default); `withdrawn` is the drain.
- **Only a deterministic refusal earns a permanent `skipped`** (D-110). `DETERMINISTIC_GATE_REFUSALS` is the
  closed catalog; a non-zero `tectonic` exit is environmental and must be retried. Out-of-catalog ⇒ environmental.
- **No `policy_version` component covers the résumé or `resume_max_pages`** (D-110), so trimming `resume.yaml`
  does **not** make a decision stale — `ledger reopen --job <id>` is the only path, not `--stale`.
- **Regrouping carries the ledger decision with the postings** and releases the emptied row (D-110).
  `protected_job_ids` cannot catch a merge that leaves it behind: `artifacts.job_id` is NULL on all 44 rows.
- **A new ranker drop bucket has SIX hand-maintained mirror sites and only three are checked** (D-111).
  **Nothing catches `_shortlist_line`** — the full list is in `RankedResults`'s docstring.
- **`hidden_duplicate == 0` is ambiguous; `hidden_handled == 0` and `hidden_applied == 0` are not** (D-106,
  D-111). **`_verify_quad` has never fired** (D-097) — never cite "string-verified" as precision evidence.
- **`track` has never been used** — `applications` and `application_events` are both 0 rows, which is why P6
  item 5 ships as a mechanism with tests as its evidence.
- **The closed-phrase catalog was NOT shipped, deliberately** (D-111). Providers assemble `body_text` only
  from JSON-payload description fields, so page chrome cannot reach that column: **11 of 23,455** matched,
  **all false positives**; a high-precision catalog matches **0**.

---

## The live store

- **The live store has NOT had Slice 2 applied**, and that is a standing fact, not a to-do. Migrated and
  backfilled for Slice 1 only (head `p6_posting_identities`, 117,254 identity rows, `identities verify` exit
  0). The cheap read-only proof: **no `job_dispositions` table**, and `postings` 24,073 against
  `count(distinct job_id)` **24,073 — exactly 1:1**, where a regrouped store would read 23,887.
  `identities regroup` would move 186 postings onto 147 canonical jobs and needs the `p6_job_dispositions`
  migration first; **Mit declined it on 2026-08-10** — not blocked, just not now. A 769 MB backup sits beside it.
- **Not demonstrated on real data:** the ledger end to end, and the liveness probe against real leads. A
  `boardwatch top 5` against the 23,455-posting copy ran past 20 minutes and was stopped — it pays for
  `run_preflight` + `run_eligibility` over the whole corpus. Both are mutation-checked by tests; neither has
  run at corpus scale.
- **0.3.0 is PUBLISHED (D-119)** — PyPI, GHCR (`amd64` + `arm64`) and GitHub Releases, verified through three
  paths independent of the workflow's own report. `v0.3.0` is a **lightweight** tag on `dc1ffec`, like every
  prior tag. It **ships Gate A inside it, deliberately** — the wheel carries the whole `profile_bundle`
  package. **Mit was offered "hold until Gate A is reviewed" twice and declined both times.** The basis holds
  because the package is **inert**: no CLI command, no bundle-to-`Resume` bridge, a test asserts both
  directions. Publishing changed the release, **not** the review's standing.

---

## Environment

- Neither `python` nor `boardwatch` is on PATH — always `uv run …`.
- No `__init__.py` under `tests/`, so test module basenames must be globally unique or collection aborts.
  `make check` runs mypy on `src` and `tools` only, ruff on everything.
- **A migration must never import a live catalog into its CHECK constraint** — it changes the constraint
  retroactively and diverges a fresh database from a migrated one. `tables.py` may (that is metadata, not
  history). Name constraints with `op.f()` or `test_migrations_match_metadata` sees permanent drift.
- **The résumé renderer is `tectonic`** compiling Mit's real LaTeX template, **not Typst** (D-058/D-060). A
  `typst` binary exists on this machine; nothing calls it. The tailoring architecture is already correct.
- **D-072, the model-tier benchmark, is DEFERRED INDEFINITELY** (D-102) — not owed, not blocking.
- `bwd` lives in gitignored `.agent/bin/bw-daily`, so its `top --no-record` fix is local to this machine.
- Foreground `sleep` is blocked in this harness; background a waiter instead. zsh does **not** word-split an
  unquoted parameter expansion, so a `for spec in "a --b" ...; do cmd $spec; done` loop passes one argument.
- **There is NO live urgency — job-apps is delivering.** `STAGE1_ONLY=1` is in job-apps' launchd plist, so
  its 08:30 run does stop after discovery, but résumés are produced anyway. Measured 2026-08-13 against
  `~/dev/Job apps/resumes/`: 08-09 **3 folders / 8 PDFs**, 08-10 **3 / 28**, 08-11 **5 / 24**, 08-12
  **4 / 18**. The former claim here — "nothing is generating Mit's résumés daily" — was **false**, and
  `PROGRAM.md` §2's output-side-first ordering argument rested on it (D-155). **Re-measure before citing:
  this is a fact about another repo's cron behaviour and it decays.**

---

## Process lessons this program paid real time for

Only what `CLAUDE.md` does not already say.

- **Commit before EVERY mutation round, not once before you start.** The `git checkout` that reverts a
  mutation destroys any uncommitted edit. Fired three times. Clear `__pycache__` too — stale bytecode fakes
  both a CAUGHT and a spurious failure. Derive the mutation from the test's CLAIM, not the implementation.
  **Check the driver for byte-identical duplicates before quoting a count** (D-122 reported 13 when 12 were
  distinct; the driver now aborts). **Mutate a COPY of `src`** (`cp -R src "$S/msrc"` + `PYTHONPATH`) rather
  than a worktree: it costs nothing and cannot race another writer.
- **A test derived from a constant agrees with itself.** Mutating `_MAX_HEADING_LEVEL` survived because every
  assertion about the cap read the same constant it was checking (D-125). Pin the outside fact.
- **A detector must be confirmed to FIRE** — mutate the thing it watches and watch it go red (D-116). Its
  mirror image: **a check that cannot fire is deleted, not shipped** (D-115) — write a test saying *where* the
  guarantee actually lands. A fix elsewhere can make a live check dead: escaping `.`/`..` in the encoder
  killed a guard that had been firing until then (D-125).
- **Budget a review for the FIX round, not just for the build** (D-137). Five rounds on T18 and every round
  found a defect in the round before it — a fix is written by someone who has just convinced themselves of
  one failure mode and is therefore the worst-placed person to enumerate the others. **State the loop's exit
  criterion before running the round that might close it**; "review until APPROVE" does not terminate.
- **Two reviewers with different LENSES beat two sequential rounds** (D-125). Reviewers that RUN the code find
  what reviewers that read it cannot (D-111). **Verify a finding's premise before ruling on it, including a
  reviewer's** — lens B's count and extent were both wrong (D-134). **Give the reviewer the attack list**: a
  reviewer told only "review this" reviews the happy path.
- **Enumerate the arms from the code's own catalog, not from the reproduction you were handed.** Replaying a
  reviewer's probe is a regression check, not verification. Probing eight of twelve commands and generalising
  is how D-138's fix was first written too narrow to reach `promote` and `rebase-draft`.
- **Look for the same thing under two names, and for a deletion that is really a rename.** Two byte-identical
  `OSError` helpers; a test `main` deleted that a branch kept; `main` fixing the FIFO in `rebase._tree_contents`
  while T16 fixed the same defect in the `storage.py` copy it had MOVED. **Two independently-green branches
  rewrote the same guard and neither was a superset** — resolve as the union, not by picking one.
- **Resolving conflict markers is not resolving the conflict** — files sit at `UU` until an explicit `git add`,
  which a passing test run will not tell you. **Sweep every `quoted_yaml(` call** in any branch being merged;
  a line-based grep gives false positives, only the suite settles it.
- **`git add -A` and `git add -u` both sweep another writer's work.** Stage explicit paths, always. Run
  `git status` immediately after stopping any agent.
- **When two sessions share a clone, a position in `git log` proves neither authorship nor order.** Push an
  explicit sha (`git push origin <sha>:main`) so a concurrent commit cannot ride along un-gated.
- **Concurrent subagents and a gate contend for the same CPU.** Load average 21 stretched a 65-second suite to
  eight minutes and SIGTERMed a gate. Pin the gate to a sha in its own worktree; do not start a second heavy
  suite beside it.
- **Measure the spec's premise before building it.** D-098 priced a deferral with the wrong subsystem's
  figures (D-105); D-111 found PROGRAM item 6's authoritative signal was 0-for-11 on the real corpus and
  structurally unable to reach the column it reads. A spec written against another codebase's data is a
  hypothesis, not a requirement.
- **A scheduled job is a standing claim about the repo, and it decays** (D-123, D-135). A prompt naming a
  starting sha must self-check or be deleted after it runs.

# boardwatch — agent instructions

**This file states only what is true now.** Change history goes in `docs/program/DECISIONS.md`; known gaps
and current standing go in `docs/program/STATE.md`. Instructions that narrate their own history stop being
followed — keep incidents out of this file.

---

## Session-start ritual — do this before anything else

1. **Read `docs/program/STATE.md`.** It is the single source of truth for where the program stands:
   current phase, what shipped, next action, blocked items, open questions.
2. **Verify it against the repo.** `git log --oneline -5`, `git status`, and check that any phase STATE
   claims is complete actually is. **If STATE and the repo disagree, the repo wins** — correct STATE and
   record the correction in `DECISIONS.md`. A stale state file that is trusted is worse than none.
3. **Pick the next task from `docs/program/PROGRAM.md`.** Work one phase at a time. **Do not start a phase
   whose predecessor's gate has not been met.** A gate is met when its metric says so, not when the work
   feels done.
4. **Work.** Run the tests (below). **Preserve dirty files and linked worktrees** — do not reset or clean
   another worker's changes.
5. **Before ending, update `STATE.md` and `METRICS.md`** — even if the session accomplished little. An
   honest "blocked on X" is worth more than silence. Append to `DECISIONS.md` for any architectural choice
   so it is never re-litigated after a context reset.
   **Write them ONCE, at the end.** Keep running notes in `.agent/` (gitignored) and do the real write at
   close. Live-editing `STATE.md` through a session is churn, not memory — one measured session rewrote it
   43 times — and it guarantees a conflict with any branch that rewrites the file wholesale.

---

## Program documents

| File | What it is |
|---|---|
| `docs/program/STATE.md` | **Read first.** Current standing. Rewritten every session. Kept near 170 lines. |
| `docs/program/STANDING-FACTS.md` | Facts a fresh session should not re-derive, in six sections. Read the section for the subsystem you are about to touch — not the whole file. |
| `docs/program/PROGRAM.md` | Phases, measurable gates, scope, departures from job-apps' roadmap. |
| `docs/program/ROADMAP.md` | **The focus view.** Five milestones in order with exit criteria, what is deliberately off the path. Read it to pick what to work on; rewrite it only when a milestone closes. |
| `docs/program/LINKEDIN-CLOSURE-PLAN.md` | **LinkedIn is the whole retirement residual.** The measured decomposition, the JobSpy refusal and three sized tracks. Read before proposing ANY LinkedIn work — it exists so the JobSpy comparison is never re-derived. |
| `docs/program/RETIREMENT-PLAN.md` | **The job-apps retirement plan.** The finished gap analysis, job-apps' full source list, the phases, and what is already settled. Read before proposing any discovery work — it exists so the comparison is never re-derived. |
| `docs/program/DECISIONS.md` | Append-only decision log. Context · choice · alternatives rejected. Holds D-077 onward, and **the index for both decision files**. |
| `docs/program/DECISIONS-ARCHIVE.md` | D-001 … D-076, verbatim. **Closed** — never append here. |
| `docs/program/METRICS.md` | Per-run numbers. Gates are checked here. Holds the live tables, the P6-era records, and **the index for both metrics files**. |
| `docs/program/METRICS-ARCHIVE.md` | The closed P0–P5 session records. **Closed** — never append here. |
| `CHANGELOG.md` | Authoritative for what actually shipped. |

**Neither log is read end to end** — together they are ~100k tokens. **Nor is the index**: the one in
`DECISIONS.md` is 114 KB (~28.6k tokens) on its own, so reading it to find a single entry costs more than
most sessions can afford. Use the lookup instead:

```sh
python -m tools.decisions --find windows ci     # matching index rows + the sed range
python -m tools.decisions --show D-151          # the entry itself
python -m tools.decisions --log metrics --find gate
```

Titles are truncated at 160 chars; `--full` opts out. Exit 1 means no match, 2 means the log could not be
read. Falling back to the index by hand still works: find the row, then `sed -n '<start>,<end>p'`. Line
numbers drift on any edit above a heading, so confirm one with `grep -n` before trusting it. **After appending an entry, add its index row and run `make reindex`**; `make check`
fails on a stale index (D-109). Cross-references are by number (`D-028`), never by file, so they resolve
across the split.

`.agent/` and `.superpowers/` are gitignored working material — useful context, **not** a source of truth
for released behaviour.

---

## Testing

**`make check` is the only gate.** pytest + ruff + mypy passing individually is *not* green — the
generalization checker only runs under `make check`. Run it in plain mode and capture the real exit code;
never pipe it through `head`/`tail` (SIGPIPE kills the run and you will read a false negative).

If a change has no runnable suite covering it, say so in one line rather than skipping silently.

---

## Scope — deliberately deferred by Mit, do not build

- Cover letters
- Outreach / referral scaffolding
- Auto-apply, auto-fill, or browser automation of any kind

**In scope even though it sounds adjacent:** per-JD résumé repositioning (that is tailoring), and marking a
lead as applied (without it, applied roles re-surface forever and dedup can never improve).

---

## The keystone invariant

> Every eligibility rule declares which user-profile fields it reads. If a declared field is missing or
> unresolvable, the rule returns `ABSTAIN(missing_profile_field:X)` — **never** `ELIGIBLE`, **never**
> `INELIGIBLE`. Abstain rates are reported per rule, every run.

**A rule that cannot fire is a monitoring failure, not a conservatism feature.** This is what makes a
never-resolving rule visible as a 100% abstain rate instead of silently clearing every posting.

Related, and equally load-bearing:

- `ABSTAIN` is never folded into either neighbour, in any report, ever.
- `INELIGIBLE` must carry a quoted span from the frozen JD. No span ⇒ downgrade to `ABSTAIN`.
- **"No flags" ≠ cleared.** `ELIGIBLE` carries its own evidence chain: which rule cleared which
  requirement, against which profile field, citing which span, and which rules abstained.
- Every quarantine needs a drain, designed in the same change as the quarantine, running on both sides of
  the gate. A bucket without a scheduled re-entry path is a leak.

---

## Multi-tenancy is a requirement, not an aspiration

boardwatch is built to fit anyone who runs it — not just Mit. The user could be on OPT, a citizen, a visa
holder in another country, or working in a field with nothing to do with software. The groundwork (rules,
schema, tooling) must be generic; what makes it work for a *specific* person is their own profile, targets,
and persona data layered on top — never new code.

job-apps has empirical evidence on what breaks first: when a second user appeared, the thing that failed to
port was the **eligibility taxonomy** — not the fetchers, not the templates, not the tracker.

Split rules into **universal** (nothing user-specific) / **profile-dependent** (work auth, seniority,
experience, employment terms) / **field-dependent** (role families, credentials, title taxonomies) from the
start, and ship the taxonomy as versioned **data**, not code.

Keep the generalized mechanism in the repository; keep Mit's profile, persona, résumé, targeting policy,
live store, and credentials local.

---

## Engineering defaults

- Reuse existing code → platform/native feature → stdlib → small dependency → new code (last resort).
- Minimum code that solves the problem. No speculative abstractions, no unrequested configurability.
- Surgical diffs: every changed line traces to the request. Do not reformat adjacent code.
- Typed violations at the raise site — never classify behaviour by string-matching a message.
- Closed, versioned catalogs. Out-of-catalog ⇒ treated as a failure, never as a new bucket.
- A component's self-report is not verification. Count the deliverable through a different path than the
  one that produced it.
- **Fixtures must be derived from live config or fingerprinted so drift fails the test.** A green
  end-to-end test whose fixture sits still while production churns passes for weeks while the behaviour
  it guards has moved.
- **A failed command is not a negative result.** Confirm a check actually ran before reading its silence
  as evidence. Prefer reading code over reading a summary of code — a summary has already discarded the
  details worth transferring.
- Fail-safe direction is chosen **per gate** and they legitimately differ: judge unavailable ⇒ fail-open
  (never silently delete a real job); fabrication check ⇒ fail-safe (drop tailoring, emit static);
  systemic outage ⇒ fatal (prevents the silent empty day).

---

## Git

- Descriptive commit messages, imperative mood. One logical change per commit.
- **No AI attribution anywhere** — not in commits, PRs, branches, tags, or release notes. No
  `Co-Authored-By` for Claude/Anthropic/any AI tool, no "Generated with" lines. Check the final message
  before committing and strip anything a tool inserted.
- Do not commit local `.agent/` or `.superpowers/` working material, personal data, secrets, or live-store
  artifacts.

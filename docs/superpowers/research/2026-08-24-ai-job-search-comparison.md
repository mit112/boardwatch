# `ai-job-search` comparison and boardwatch public-readiness findings

**Date:** 2026-08-24

**Status:** Research memo only — not a program decision, gate movement, or implementation plan

**Purpose:** Preserve the repo-grounded comparison requested by Mit so a later Claude Code session can
turn the findings into an owner-approved public-readiness plan without redoing the research.

## Evaluation inputs

- boardwatch working checkout: `/Users/mitsheth/dev/projectY/boardwatch`
- boardwatch local `HEAD` during the evaluation: `0cb494089523390719411b3ac4f423ddd0c84cc9`
- boardwatch `origin/main` after a read-only fetch: `dd45e0761940db821f574046478cee333658ae4b`
  - the one remote-only commit changed only `CHANGELOG.md` and program documents; evaluated product code
    was equivalent
- comparison repository: <https://github.com/MadsLorentzen/ai-job-search>
- comparison repository `master`: `e2c311a5b40512daf79a04b22c96d7e049afc745`
- GitHub metadata and activity were checked live on 2026-08-24
- The comparison repository was shallow-cloned to a disposable directory and inspected locally.
- Its Python gate was run locally: `python3 -m unittest discover -s tests -t . -q` →
  **313 tests passed in 5.808 seconds**.
- boardwatch's full `make check` was not rerun because this was a read-only product/repository
  evaluation, not a source change. Current GitHub CI on boardwatch `main` was green when checked.

All counts below are dated observations, not permanent facts. Refresh them before using them in public
copy.

## Executive verdict

**boardwatch is already public, but it is not ready for a serious attention-seeking launch.**

`ai-job-search` is the better **product presentation, onboarding experience, end-to-end user journey,
and community project**. boardwatch is the substantially better **software engine**: more deterministic,
auditable, private, scalable, testable, and operationally robust.

The useful lesson is:

> Copy `ai-job-search`'s product packaging, proof, onboarding shape, focused public surface, and community
> flywheel. Do not replace boardwatch's architecture with its prompt-driven model.

This is not a feature-parity contest. The two repositories solve overlapping but different problems:

- `ai-job-search` is primarily a personalized Claude Code workspace that coordinates an entire job hunt.
- boardwatch is a packaged discovery, eligibility, ranking, liveness, deduplication, tracking, and résumé
  engine with deterministic default behavior.

## Public repository snapshot

As observed on 2026-08-24:

| Dimension | `MadsLorentzen/ai-job-search` | `mit112/boardwatch` |
|---|---:|---:|
| Created | 2026-03-18 | 2026-06-12 |
| Stars | 33,946 | 0 |
| Forks | 11,868 | 1 |
| Contributors returned by GitHub | 50 | 3 |
| Open issues | 3 | 3 |
| Closed issues | 51 | 28 |
| Open PRs | 3 | 0 |
| Closed PRs | 276 | 123 |
| Releases | 7 | 3 |
| Current release | v1.6.0 | v0.3.0 |
| Discussions | enabled and active | disabled |
| Distribution | clone/fork a Claude Code workspace | PyPI wheel/sdist + GHCR image |

These numbers prove attention and contribution activity, not active-user retention. In particular,
`ai-job-search`'s setup historically encouraged users to fork, so fork count is partly a distribution
mechanism. It has no telemetry and no package-download number comparable to PyPI. Its usage proof is a
mix of the maintainer's own reported funnel, third-party walkthroughs, discussion activity, and public
adaptations.

The activity is nevertheless real enough to study: its pinned community discussion had 28 comments and
57 replies and indexed maintained market/language/runtime adaptations for many countries plus Codex,
OpenCode, Antigravity, and local-model harnesses.

## The repositories are different kinds of systems

Approximate inspected size:

| Surface | `ai-job-search` | boardwatch |
|---|---:|---:|
| TypeScript portal implementation | 7,555 lines | — |
| Python tools | 1,992 lines | — |
| Claude command/skill Markdown | 4,658 lines | — |
| Production Python | — | 61,498 lines |
| Python test code | 4,754 lines | 92,740 lines |
| Python test methods | 303 | 4,547 |
| TypeScript test cases | 217 | — |
| Collected boardwatch cases | — | 7,464, per current program state |

Code size is not a quality score. It establishes that `ai-job-search`'s apparent breadth comes partly
from letting a general agent interpret Markdown procedures at runtime, whereas boardwatch implements and
persists its guarantees in code and data.

## Where `ai-job-search` is better

### 1. It presents a complete human journey

The public workflow is immediately legible:

```text
/setup -> /scrape -> /rank -> /apply -> /outcome -> /interview
```

It owns or connects:

- profile creation and enrichment;
- portal search and quick fit assessment;
- batch ranking;
- CV and cover-letter drafting;
- fresh-context reviewer critique;
- rendered-PDF and ATS text-layer checks;
- application-form answers;
- application tracking and archives;
- follow-ups and thank-you notes;
- interview preparation and mock interviews;
- Gmail status detection;
- Notion and offline HTML views;
- skill-gap planning; and
- outcome-driven recalibration of future fit evaluation.

boardwatch has more machinery but a narrower public journey. Its beginner story is still primarily
`init -> scan -> top -> show`; the unattended `run`, tailored output, application tracking, canonical
profile bundle, and projection system are harder for a new reader to connect into one transformation.

### 2. Its onboarding is materially stronger

`/setup` offers three routes:

1. read a populated career-documents directory;
2. import one pasted CV; or
3. conduct a conversational career interview.

It also:

- detects conflicts between sources before writing;
- asks for owner resolution instead of silently normalizing them;
- supports section-only reruns;
- derives search queries and target-role categories;
- captures behavioral and writing-style context;
- surfaces incomplete STAR examples for owner completion; and
- points directly from setup to search and application commands.

boardwatch's current first-run flow is much lighter: choose companies, paste résumé text, and enter
target/excluded titles and locations. The field-taxonomy onboarding gatherer remains P2 item 8 and has
not started.

### 3. It sells a human outcome before implementation detail

The README says the maintainer used the workflow for 69 tailored applications, reached 20 first
interviews, and signed one contract. This is self-reported, not an independent effectiveness study, but
it gives a prospective user a reason to care before asking them to understand the architecture.

boardwatch's current authoritative counterweight is honest but not yet promotable:

- zero applications recorded;
- P4 blind craft review not met;
- P6 awaiting its true seven-day window;
- 14-day acceptance not started; and
- the measured-acceptance roadmap item still open.

### 4. It keeps the first public surface focused

The README advertises `/setup`, `/scrape`, and `/apply` as the core. Other commands are introduced as
extensions after the user understands the basic loop.

Its public assets include:

- a one-sentence promise;
- a mascot/animated visual;
- a concrete workflow diagram;
- a personal success story;
- a third-party video walkthrough;
- community-fork links;
- funding/support links; and
- frequent, named releases.

boardwatch's README already has a strong opening, illustrative `top` output, a clear competitive table,
and a usable quickstart. It then grows to 863 lines and exposes a substantial amount of scheduling,
configuration, projection, tailoring, platform caveat, and operational detail before social proof exists.

### 5. It has a working community flywheel

Two user-facing generators are important:

- `/add-portal` investigates and scaffolds a market-specific portal skill.
- `/add-template` registers and verifies a new document toolchain.

Installed portal skills follow a shared contract and are auto-discovered by `/scrape`. Upstream stays
universal while a pinned Discussion indexes adaptations maintained in forks. A weekly upstream-watch
workflow helps personalized forks find changes without automatically merging them.

This is technically less centralized than boardwatch's provider architecture, but socially much more
effective: users can make the project fit their market, publish the adaptation, and get indexed without
waiting for upstream to own every portal forever.

boardwatch's registry/provider contribution surface is sound but comparatively demanding. The public
path is a short `CONTRIBUTING.md`, issue templates, and the registry guide; a code contributor faces the
entire `make check` gate and a much larger repository.

### 6. It closes the outcome feedback loop

`/outcome` owns applied/interview/offer/rejection/silence state, archives the submitted materials, drafts
bounded follow-ups, and gives `/setup` resolved evidence that can recalibrate fit guidance.

boardwatch persists application statuses and their immutable history, but it does not yet make the
learning loop a visible product feature. This is a worthwhile takeaway that does not require auto-apply.

### 7. Its release rhythm gives outsiders checkpoints

It published v1.0.0 through v1.6.0 between 2026-07-22 and 2026-08-19. Release names describe user-visible
outcomes rather than internal phase numbers.

boardwatch published v0.1.0 through v0.3.0 between 2026-08-01 and 2026-08-11, then accumulated a very
large unreleased delta.

## Limits and risks in `ai-job-search`

These are reasons not to copy its architecture blindly.

### Its main guarantees are instruction-enforced

Anti-fabrication, prompt-injection handling, source grounding, requirement coverage, reviewer separation,
and many state transitions are prose instructions interpreted by an LLM. The repository itself says
these protections are instruction-level, not a sandbox.

boardwatch's typed catalogs, exact evidence spans, `ABSTAIN` semantics, hashes, approvals, migrations,
and verification paths are materially stronger guarantees.

### Setup is heavier than the story suggests

A full user needs:

- Claude Code plus a subscription or API key;
- Python;
- Bun;
- a LaTeX distribution; and
- optionally Poppler for ATS text-layer verification.

boardwatch scanning/ranking installs through `pipx`; Docker bundles résumé dependencies. It requires no
model subscription for its default path.

### Personalized tracked files create a privacy hazard

`/setup` writes personal data into tracked template files. A real user published toward a public fork,
which led to explicit preflight warnings and regression tests. Many generated artifacts are ignored, but
tracked profile templates remain tracked after personalization; safe use requires keeping the copy local
or publishing to a genuinely private repository.

boardwatch's private profile and state live outside the source repository by design.

### Portal reliability and access rules are weaker

The comparison repo includes HTML portal scrapers, WebSearch fallback, and LinkedIn guest endpoints. It
documents personal-use/ToS warnings and deliberately avoids live portal traffic in CI. Health checking is
an LLM-orchestrated procedure over flat files rather than boardwatch's persisted scan and coverage model.

### Its state model is simpler and more fragile

Seen jobs live in JSON and application state in CSV. This is approachable and fork-friendly, but it does
not provide boardwatch's transactional updates, migrations, run attribution, append-only event ledger,
durable dedup identities, stored eligibility inputs, or independent reconciliation.

### Stars are not a conversion metric

The repository has strong attention and community evidence. It does not publish active users, completed
applications across users, retention, or outcome distributions. Do not treat 33,946 stars as evidence
that 33,946 people completed setup or got value.

## Where boardwatch is better

### 1. Discovery and unattended operation

boardwatch has:

- six official ATS providers;
- conditional requests, pacing, retries, and transactional board application;
- a large local corpus and scheduled execution;
- liveness checks before résumé work;
- per-board coverage reporting;
- durable decision and application ledgers;
- dedup identities and regrouping;
- run attribution and reconciliation; and
- daily-driver artifacts with explicit failure semantics.

This is a real engine, not an agent reinterpreting a search procedure each session.

### 2. Trust and auditability

boardwatch's differentiator is not generic AI assistance. It is evidence-backed decision-making:

- exact JD spans for ineligibility;
- explicit abstention on missing profile fields;
- deterministic default rules;
- closed versioned catalogs;
- evidence chains for positive eligibility results;
- profile/rule hashes;
- approval-bound profile projections;
- stored artifact derivation; and
- refusal rather than guessed values at unknown boundaries.

That is a defensible public position that `ai-job-search` cannot make.

### 3. Privacy and dependency posture

The default boardwatch path needs no account, API key, or model. Personal data remains local, no telemetry
exists, and optional model paths disclose what leaves the machine. `ai-job-search` necessarily gives a
general agent file access to career data while it reads untrusted web content.

### 4. Packaging

boardwatch already ships through PyPI and GHCR. Users do not need to fork the source repository or merge
upstream changes into their personal career data. This is a better long-term distribution model for the
core engine.

### 5. Engineering assurance

boardwatch has strict typing, an 85% coverage floor, multi-OS CI, gitleaks, performance checks,
generalization checks, schema migrations, mutation/negative-control expectations, and the full
`make check` gate.

The comparison repository's CI is thoughtful for its smaller shape — pinned Actions, portal discovery,
fixture tests, security guards, PDF compilation, and fork-aware checks — but it cannot execute and verify
the central Claude workflows end to end.

## Public-readiness blockers for boardwatch

### Blocker 1: current effectiveness proof is incomplete

Before a serious launch, complete the program's existing evidence path rather than inventing a second
marketing gate:

1. P4 blind craft review;
2. P6's true seven-day window;
3. the provisional frozen-run pass;
4. the passive 14-day acceptance; and
5. at least one real lead taken through résumé review, application, tracking, and outcome.

The product should publish measured numbers with their population and limitations, not only assert that
the machinery works.

### Blocker 2: the package is far behind `main`

As measured on 2026-08-24:

- PyPI and the latest GitHub release were still v0.3.0;
- `origin/main` was **608 commits** ahead of v0.3.0;
- the diff covered **428 files**, with 122,165 insertions and 1,456 deletions; and
- the live README described many capabilities that an ordinary `pipx install boardwatch` user would not
  receive.

A publicity push against the current package would send users to a materially older product. Cut a fresh
release from a verified launch candidate before directing traffic at the quickstart.

### Blocker 3: the intended initial audience is ambiguous

Two legitimate interpretations exist:

1. **Tech-first launch (recommended near term):** explicitly target software/technical candidates using
   supported ATS boards. This matches the current role gate and avoids delaying proof for speculative
   breadth.
2. **Field-agnostic launch:** wait until P2 item 8 gathers the user's field taxonomy and the non-software
   onboarding path is executable.

Advertising boardwatch as universal today would conflict with behavior that confidently hides non-software
titles by default. Pick one position explicitly.

### Blocker 4: the beginner journey is not compressed enough

The root CLI exposed 24 top-level commands during the evaluation, and the program reports 71 leaf
commands. That depth is valuable for operators and maintainers but should not be the public mental model.

The beginner story should be one path:

```text
install -> init -> run -> inspect -> review résumé -> track outcome
```

Advanced bundle authoring, projection internals, ledger maintenance, identity repair, long scheduler
recipes, detailed Windows caveats, and deep settings material can remain available behind links.

### Blocker 5: no public proof asset exists

The README contains illustrative console output but no screenshot, animated run, or video. A 60–90 second
recording should show:

1. installation;
2. choosing companies;
3. the first scan;
4. a ranked lead;
5. eligibility evidence quoted from the posting;
6. a grounded tailored résumé; and
7. the morning report.

Pair it with sanitized, reproducible funnel numbers and time-to-first-shortlist.

### Blocker 6: there is no visible community home

GitHub Discussions is disabled. The issue templates are good, but they provide support intake rather than
a place for users to show outcomes, share boards, compare configurations, or maintain extensions.

## Recommended sequence

This ordering deliberately avoids adding input breadth or new application-writing features before the
existing conversion proof.

### Phase 1 — finish proof

1. Complete P4, P6, and the already-defined acceptance evidence.
2. Run at least one real application through the owner-reviewed output path.
3. Preserve an honest, sanitized funnel and its population definitions.
4. Do not treat stars, posting count, or test count as the effectiveness metric.

### Phase 2 — choose the public contract

1. Owner decides tech-first versus field-agnostic launch.
2. Keep the current no-auto-apply boundary.
3. Keep cover letters and outreach deferred unless Mit explicitly reverses that program scope.
4. State the product category plainly: a trustworthy local radar and grounded résumé pipeline, not an AI
   mass-application bot.

### Phase 3 — ship what will be promoted

1. Freeze a release candidate after the proof gates.
2. Run the repository's full release gate.
3. Cut a fresh PyPI/GHCR/GitHub release.
4. Ensure the README quickstart describes the released package rather than later `main` behavior.
5. Write release notes in user outcomes, not only internal decision vocabulary.

### Phase 4 — simplify the public surface

1. Keep the strong opening value proposition and illustrative `top` output.
2. Add a short end-to-end journey before the detailed subsystem documentation.
3. Move operator/reference material into linked docs.
4. Add a `Does it work?` section with measured, population-scoped results.
5. Add the short demo asset.
6. Make the next action after every beginner command obvious.

### Phase 5 — pilot outside the maintainer's machine

Run 3–5 external users through the release without live coaching where possible. Measure:

- installation completion;
- setup completion;
- time to first shortlist;
- whether results contain credible live postings;
- whether the user accepts a generated résumé;
- whether an application is submitted;
- where the user stops; and
- which instructions they misread.

Fix observed blockers before a broad launch. Do not infer onboarding quality from Mit's familiarity with
the system.

### Phase 6 — create the community flywheel

1. Enable Discussions.
2. Add `Show and tell`, `Boards/providers`, and `User results` categories.
3. Publish a focused registry/provider contribution walkthrough.
4. Provide narrow local verification commands for common contribution shapes while retaining full CI as
   the merge gate.
5. Seed genuinely bounded good-first issues.
6. Publish a provider/compatibility matrix and synthetic sample configuration.
7. Consider a community extension index only after there are real external extensions to index.

### Phase 7 — launch with the story

Lead with:

- the job-search pain;
- why official ATS sources are fresher and quieter;
- why eligibility evidence matters;
- what stays private;
- the measured funnel; and
- the short demonstration.

Use GitHub, a Show HN post, relevant self-hosted/open-source/job-search communities, LinkedIn, and a
walkthrough. The message is not “61,000 lines and 7,464 tests.” Those are supporting trust evidence after
the user understands the outcome.

## Takeaways worth borrowing without changing current scope

- Three-path onboarding that converges on one canonical profile.
- A short, named lifecycle that users can remember.
- An outcome/reporting loop over already-tracked applications.
- Fresh-context review of human-facing documents, while retaining boardwatch's deterministic gates.
- A visible extension/contribution contract.
- A community home and indexed adaptations.
- Frequent releases with user-facing names.
- A real success/proof section and a short demonstration.

## Things not to copy

- A fork-first personal-data model.
- Tracked user profiles in a public template repository.
- Prompt instructions as substitutes for typed/enforceable invariants.
- Flat JSON/CSV as the durable source of truth for boardwatch state.
- Broad portal scraping or ToS-restricted access as the default discovery strategy.
- Cover letters, outreach, browser automation, or auto-apply without an explicit reversal of boardwatch's
  current owner-set scope.
- Feature breadth before conversion is demonstrated.

## Owner decisions required before planning

1. **Initial audience:** tech-first or field-agnostic?
2. **Launch evidence:** is the existing P4 + P6 + 14-day acceptance sequence the public-launch gate, and
   what external-pilot threshold should follow it?
3. **Product boundary:** does “something like `ai-job-search`” mean comparable adoption and lifecycle
   clarity, or a literal expansion into cover letters/interview support? The latter conflicts with current
   repository instructions and needs an explicit program decision.
4. **Community model:** keep all providers upstream, or eventually support a reviewed extension index?
5. **Outcome learning:** should tracked outcomes become ranking/calibration input, or remain reporting only?

Do not silently answer these in an implementation plan.

## Claude Code continuation boundary

A later Claude Code session should:

1. read `CLAUDE.md` and `docs/program/STATE.md` first;
2. refresh repository/GitHub/release facts that may have moved;
3. treat this file as research evidence, not authority over `PROGRAM.md`, decisions, or owner-gated work;
4. ask/batch the five owner decisions above before writing an implementation plan;
5. avoid starting cover-letter, outreach, auto-apply, or browser-automation work; and
6. avoid moving any program gate merely because this comparison recommends a launch sequence.

The most useful next artifact, after the owner decisions, is a bounded public-readiness plan that reuses
the existing program gates and names exact deliverables, verification, and stop boundaries. It should not
be another broad product roadmap.

## Primary sources

- `ai-job-search` repository: <https://github.com/MadsLorentzen/ai-job-search>
- `ai-job-search` README: <https://github.com/MadsLorentzen/ai-job-search/blob/master/README.md>
- `ai-job-search` setup guide: <https://github.com/MadsLorentzen/ai-job-search/blob/master/SETUP.md>
- `ai-job-search` apply workflow:
  <https://github.com/MadsLorentzen/ai-job-search/blob/master/.claude/commands/apply.md>
- `ai-job-search` scraper workflow:
  <https://github.com/MadsLorentzen/ai-job-search/blob/master/.claude/skills/job-scraper/SKILL.md>
- `ai-job-search` contribution policy:
  <https://github.com/MadsLorentzen/ai-job-search/blob/master/CONTRIBUTING.md>
- `ai-job-search` threat model:
  <https://github.com/MadsLorentzen/ai-job-search/blob/master/SECURITY.md>
- Community forks and portal index:
  <https://github.com/MadsLorentzen/ai-job-search/discussions/78>
- `ai-job-search` metadata: <https://api.github.com/repos/MadsLorentzen/ai-job-search>
- boardwatch metadata: <https://api.github.com/repos/mit112/boardwatch>
- boardwatch PyPI record: <https://pypi.org/project/boardwatch/>
- boardwatch live sources consulted: `README.md`, `CLAUDE.md`, `CONTRIBUTING.md`, `SECURITY.md`,
  `pyproject.toml`, `Makefile`, `.github/workflows/`, `docs/program/STATE.md`, and `CHANGELOG.md`

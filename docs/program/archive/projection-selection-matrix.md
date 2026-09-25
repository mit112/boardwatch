# The owner-labeled projection selection matrix (Task 20)

> **Status: steps 1–3 recorded — owner-labeled 2026-08-15.** The ten postings, their extracted JD
> skills, and the owner's rankings + cut lines are all filled in below.
>
> **No scorer has been run against any of this.** The rankings were set by the owner from JD-and-project
> fit alone, **without seeing any scorer's output** — so this file is the independent arbiter Task 23 reads
> to pick the scorer (by rank agreement) and set the admission threshold (from where each cut line falls).
> A matrix labeled after seeing a scorer's output would be a test that agrees with itself; this one was not.

This is a prose document on purpose. It gets no `SHIPPED_DATA` entry, so it cannot drift into a fixture
the scorer is tuned against. `projection/agreement.py` reads it only through a human transcribing each
block into a `MatrixCase(jd_skills=..., expected=...)`.

**Why it exists.** Two design rounds each picked an entry scorer analytically and a probe falsified both
(D-158). D-163 then showed the four registered candidates are two behavioural families and *none* survives
both probes, so they cannot break their own tie. D-168 made `--scorer` a required parameter with no
default. This matrix is the only arbiter that can end that, and it does not exist until the rankings below
are filled in. It sets **two** numbers, not one: the scorer (by rank agreement) and the **admission
threshold** (from where each cut line falls).

---

## Before this matrix can be used: the pinning decision — RESOLVED 2026-08-15 (D-195)

- [x] **Owner decision, blocked Stage 2 independently of the rankings below:** which of the 11 are `pinned`?

**Pinned (3):** `employment.saayam`, `employment.nio-coop`, `employment.sakec`.
**Candidates (8):** `employment.nakshatra` and all seven projects.

Verified after the edit: pinned 3 / candidates 8, and the pinned set alone is 7 bullets → **1 page**, so
`select` clears its own gate and reaches scoring. `PINNED_SET_EXCEEDS_BUDGET` no longer fires. (Previously
all 11 carried `pinned: true`, `candidate_entry_ids` was empty, and the pinned-only set *was* the whole
2-page reservoir against a 1-page budget — so `select` refused before computing a single score.)

### The capacity this leaves, and why it bounds the cut lines below

Measured by compiling hand-named subsets through the same path `select` builds — `LatexRenderer.emit` →
`to_pdf` → `evaluate_compile(max_pages=1)`. **No scorer was run**; the growth orders were probe orders, not
rankings.

| Experience base | Base bullets | SDE order survives | iOS order survives |
|---|---|---|---|
| all four jobs | 9 | 2 of 4 | **1** of 4 |
| **three jobs (the chosen pin)** | **7** | **2 of 4** | **2 of 4** |
| two jobs | 5 | 3 of 4 | 3 of 4 |

**The ceiling is 16 bullets, not a count of entries** — 16 fits in every configuration tested, 17 overflows
in every one, and two different 6-entry sets landed on opposite sides of the budget.

**Consequence for this document:** with three jobs pinned, **at most two candidates can ever be admitted**.
Rank what you would genuinely send anyway — the cut line is a statement about what belongs on that résumé,
and the budget truncating it at two is a separate fact about the pipeline. Do not compress your ranking to
fit the budget; that would fold two different numbers into one.

It also means the owner's stated sets — SDE = {Hookrail, Knowledge Forge, StreakSync, Random Forest}; iOS =
{StreakSync, FlickSwiper, BirthdayQuest, Fond}, **four projects each** — cannot be emitted at one page under
any split. The most that ever fits is three, and only if just two jobs are pinned.

---

## The candidate menu

**The three pinned jobs (`saayam`, `nio-coop`, `sakec`) are always present and are NOT ranked.** The
rankings below are over the **eight candidate entries** only (`nakshatra` + the seven projects); the
scorer is run over exactly the ids each posting names above its cut line (`agreement._rank_by_scorer` →
`_flatten(case.expected)`), so each below-the-line block lists the **rejected candidates**, never the
pinned jobs.

These are the ids to write in the rankings. **Use the `entry.` form**, not the bare `entity_id` the plan's
template sketched: `agreement.rank_agreement` compares against a scorer's output, which is keyed by
`Entry.entry_id`, and it raises `ValueError` unless both sides name exactly the same ids. Writing
`project.fond` where the code expects `entry.project.fond` is a transcription defect the harness will
catch loudly but only after the labeling session is over.

| `entry_id` | Heading as rendered | Bullets | Role |
|---|---|---|---|
| `entry.employment.saayam` | Full Stack Developer (Volunteer) — Saayam For All — Oct 2025–Present | 2 | **pinned** |
| `entry.employment.nio-coop` | Software Engineering Co-Op — National Internet Observatory — Jul 2024–Feb 2025 | 3 | **pinned** |
| `entry.employment.sakec` | Software Engineer Intern — SAKEC Marathon — Feb 2021–Apr 2021 | 2 | **pinned** |
| `entry.employment.nakshatra` | Software Developer Intern — Nakshatra Eye Care — Mar 2021–Feb 2022 | 2 | candidate |
| `entry.project.hookrail` | Hookrail | 4 | candidate |
| `entry.project.knowledge-forge` | Knowledge Forge | 3 | candidate |
| `entry.project.streaksync` | StreakSync | 4 | candidate |
| `entry.project.crop-rf` | Random Forest Sampling for Crop Recommendation | 3 | candidate |
| `entry.project.flickswiper` | FlickSwiper | 4 | candidate |
| `entry.project.birthdayquest` | BirthdayQuest | 3 | candidate |
| `entry.project.fond` | Fond | 3 | candidate |

## How this was filled in

For each posting the owner moved the entries genuinely wanted on that résumé **above** the cut line, best
first, and left the rest below it. Ties are allowed — tied ids on one line. Everything below the line is an
assertion too: it says that entry should **not** appear for this JD, and that is what fixes the admission
threshold. The owner ranked only what would genuinely be sent, and did **not** look at any scorer's output
first — that is the one thing this document exists to prevent.

**The owner's heuristic (recorded 2026-08-15):** most postings are general SDE, taking
`hookrail → knowledge-forge → streaksync → crop-rf` (Random Forest for the published-research signal).
Mobile/iOS postings lead with `streaksync` then `flickswiper` (both live on the App Store), then `fond`
**or** `birthdayquest` depending on which the JD's keywords reach. Experience is fixed to the three pinned
jobs. Five rows needed a keyword call, resolved with the owner: Ramp iOS 1372 → `fond` (only iOS project
with TypeScript); Snap 19754 → `hookrail` in the third slot (JD wants distributed systems + observability);
Spotify 13160 (Android, matches none) → `crop-rf` leads on its Flutter/cross-platform build, iOS apps kept
as mobile-craft evidence; Zillow 17187 → `crop-rf` promoted (the ML/research project); Ramp frontend 1370 →
`knowledge-forge` promoted (the only React/TS/Tailwind web project).

---

## Posting 10947 — Stripe, "Backend Engineer, Payments and Risk"  ·  role family: backend

JD skills extracted (5): `AWS`, `Docker`, `GraphQL`, `Kubernetes`, `gRPC`

Expected candidate entries, best first. Rank ties are allowed; write them on one line.

1. `entry.project.hookrail`
2. `entry.project.knowledge-forge`
3. `entry.project.streaksync`
4. `entry.project.crop-rf`
—— below here should NOT appear (rejected candidates) ——
- `entry.employment.nakshatra`
- `entry.project.flickswiper`
- `entry.project.birthdayquest`
- `entry.project.fond`

---

## Posting 349 — Confluent, "Distributed Systems Software Engineer - WarpStream"  ·  role family: distributed systems

JD skills extracted (14): `AWS`, `Azure`, `C++`, `Code review`, `Distributed systems`, `GCP`, `Go`,
`HTML/CSS`, `High availability`, `Java`, `JavaScript`, `Kafka`, `Microservices`, `Python`

Expected candidate entries, best first. Rank ties are allowed; write them on one line.

1. `entry.project.hookrail`
2. `entry.project.knowledge-forge`
3. `entry.project.streaksync`
4. `entry.project.crop-rf`
—— below here should NOT appear (rejected candidates) ——
- `entry.employment.nakshatra`
- `entry.project.flickswiper`
- `entry.project.birthdayquest`
- `entry.project.fond`

---

## Posting 2012 — Affirm, "Software Engineer I, Backend (Collections)"  ·  role family: backend (new grad)

JD skills extracted (8): `AWS`, `Code review`, `Distributed systems`, `High availability`, `Kotlin`,
`Kubernetes`, `MySQL`, `Python`

Expected candidate entries, best first. Rank ties are allowed; write them on one line.

1. `entry.project.hookrail`
2. `entry.project.knowledge-forge`
3. `entry.project.streaksync`
4. `entry.project.crop-rf`
—— below here should NOT appear (rejected candidates) ——
- `entry.employment.nakshatra`
- `entry.project.flickswiper`
- `entry.project.birthdayquest`
- `entry.project.fond`

---

## Posting 6397 — Dropbox, "Infrastructure Software Engineer"  ·  role family: infrastructure

JD skills extracted (5): `C++`, `Go`, `Java`, `Python`, `Security (word)`

Expected candidate entries, best first. Rank ties are allowed; write them on one line.

1. `entry.project.hookrail`
2. `entry.project.knowledge-forge`
3. `entry.project.streaksync`
4. `entry.project.crop-rf`
—— below here should NOT appear (rejected candidates) ——
- `entry.employment.nakshatra`
- `entry.project.flickswiper`
- `entry.project.birthdayquest`
- `entry.project.fond`

---

## Posting 12761 — Palantir, "Software Engineer - Apollo Platform"  ·  role family: platform (generalist)

JD skills extracted (1): `CI/CD`

> Kept deliberately. A one-skill JD is the degenerate case for every scorer — `mean_per_bullet` and
> `mean_top_k` can only return 0 or 1/bullet-count, and `total_distinct` can only return 0 or 1 — so this
> row is where the *admission threshold* does the deciding rather than the ranking. It is also a live
> example of the thin-extraction case a real run will hit.

Expected candidate entries, best first. Rank ties are allowed; write them on one line.

1. `entry.project.hookrail`
2. `entry.project.knowledge-forge`
3. `entry.project.streaksync`
4. `entry.project.crop-rf`
—— below here should NOT appear (rejected candidates) ——
- `entry.employment.nakshatra`
- `entry.project.flickswiper`
- `entry.project.birthdayquest`
- `entry.project.fond`

---

## Posting 1372 — Ramp, "Mobile Engineer, iOS"  ·  role family: iOS

JD skills extracted (9): `AI (umbrella)`, `Code review`, `Flask`, `Python`, `React`, `SQL (language)`,
`Swift`, `TypeScript`, `iOS/Swift (mobile)`

Expected candidate entries, best first. Rank ties are allowed; write them on one line.

1. `entry.project.streaksync`
2. `entry.project.flickswiper`
3. `entry.project.fond`
—— below here should NOT appear (rejected candidates) ——
- `entry.employment.nakshatra`
- `entry.project.hookrail`
- `entry.project.knowledge-forge`
- `entry.project.crop-rf`
- `entry.project.birthdayquest`

---

## Posting 19754 — Snap, "Software Engineer, iOS, Level 3"  ·  role family: iOS

JD skills extracted (3): `Distributed systems`, `Observability (word)`, `iOS/Swift (mobile)`

> Paired with 1372 on purpose. Both are iOS roles, but one extracts nine skills and one extracts three.
> If a scorer ranks the iOS projects differently across these two, the difference is extraction depth,
> not role fit — which is exactly the kind of thing a hand-labeled matrix can see and a formula cannot.

Expected candidate entries, best first. Rank ties are allowed; write them on one line.

1. `entry.project.streaksync`
2. `entry.project.flickswiper`
3. `entry.project.hookrail`
—— below here should NOT appear (rejected candidates) ——
- `entry.employment.nakshatra`
- `entry.project.knowledge-forge`
- `entry.project.crop-rf`
- `entry.project.birthdayquest`
- `entry.project.fond`

---

## Posting 13160 — Spotify, "Android Engineer - Experience"  ·  role family: Android / mobile

JD skills extracted (1): `Android (mobile)`

> A mobile role whose single extracted skill matches **none** of the reservoir's bullets, all of which are
> iOS/Swift. This is the honest near-miss: the owner may well want the iOS projects shown anyway, on
> mobile-craft grounds a skill-intersection scorer cannot represent. Where the cut line lands here is a
> real finding either way.

Expected candidate entries, best first. Rank ties are allowed; write them on one line.

1. `entry.project.crop-rf`
2. `entry.project.streaksync`
3. `entry.project.flickswiper`
—— below here should NOT appear (rejected candidates) ——
- `entry.employment.nakshatra`
- `entry.project.hookrail`
- `entry.project.knowledge-forge`
- `entry.project.birthdayquest`
- `entry.project.fond`

---

## Posting 17187 — Zillow, "Machine Learning Engineer"  ·  role family: ML / data

JD skills extracted (13): `AI (umbrella)`, `AWS`, `Airflow`, `CI/CD`, `Data pipelines`, `GCP`,
`Kubernetes`, `Machine learning`, `PyTorch`, `Python`, `Spark`, `TensorFlow`, `TypeScript`

Expected candidate entries, best first. Rank ties are allowed; write them on one line.

1. `entry.project.crop-rf`
2. `entry.project.hookrail`
3. `entry.project.knowledge-forge`
4. `entry.project.streaksync`
—— below here should NOT appear (rejected candidates) ——
- `entry.employment.nakshatra`
- `entry.project.flickswiper`
- `entry.project.birthdayquest`
- `entry.project.fond`

---

## Posting 1370 — Ramp, "Software Engineer, Frontend"  ·  role family: frontend

JD skills extracted (3): `JavaScript`, `React`, `TypeScript`

> Same company as 1372, deliberately. The two JDs share Ramp's boilerplate and differ only in the
> role-specific text, so a scorer that ranks them identically is reading the boilerplate. This is also the
> family the reservoir is weakest in, which makes it the best test of the cut line.

Expected candidate entries, best first. Rank ties are allowed; write them on one line.

1. `entry.project.knowledge-forge`
2. `entry.project.hookrail`
3. `entry.project.streaksync`
4. `entry.project.crop-rf`
—— below here should NOT appear (rejected candidates) ——
- `entry.employment.nakshatra`
- `entry.project.flickswiper`
- `entry.project.birthdayquest`
- `entry.project.fond`

---

## Provenance

Every posting above is a real, currently-open posting in the live store, `role=swe`, pulled with
`boardwatch top 400 --no-record` on 2026-08-15 — `--no-record` so ranking for this document did not mark
anything `seen` and did not advance the dedup queue.

JD skills are **not** transcribed from `boardwatch show`, which reports only a `covers 7/9 skills` summary
and never enumerates them. They come from `projection.posting.posting_context(engine, settings, id)
.jd_skills` — the same call `resume project` makes, resolved against each posting's current open version
and the live taxonomy. Recording them through a different path than the one Stage 2 reads would let the
matrix and the scorer disagree about what the JD even says.

Ten postings, by family: backend ×2 (10947, 2012), distributed systems (349), infrastructure (6397),
platform (12761), iOS ×2 (1372, 19754), Android (13160), ML/data (17187), frontend (1370).

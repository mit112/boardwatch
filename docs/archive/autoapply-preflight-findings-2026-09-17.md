# Autoapply pre-flight findings — 2026-09-17

Raw findings from the first job-apps `/autoapply` session run directly against boardwatch's
resume-built/eligible/open/unapplied queue (not yet formal tickets — no file:line references,
since this was written from the consuming side, not from the codebase). Each finding below is
one or more postings that boardwatch scored `eligible` (cleared the eligibility gate, passed the
role/title/zero-signal/seniority filters, and had a résumé built) but that a manual per-JD
pre-flight read caught as not actually apply-worthy. Posting IDs are stable and queryable via
`boardwatch show <id>` or `sqlite3 boardwatch.db` for exact JD text. Full disposition + reason for
every posting named here is also recorded in the owner's local tracker (`boardwatch track log
<app_id>`), so this file is a synthesis of that local ledger, not the only copy of the reasons.

## 1. Not a real job — title-matched a paid research study

- **Terac #61754** — "Full-Stack Engineers (Cybersecurity): Feedback On CI/CD Workflows."
  Employment Type on the live page is `Contract`, Department is `Participant Recruitment`, and
  the body is a $105/hr paid user-research interview about CI/CD practices, not an engineering
  role. Nothing in the discovery-time fields (title, company, department string if captured)
  obviously screamed "not a job" — the department name would have.
- **Gap:** no check for `department` containing recruiting/research-panel language, or for
  `Employment Type: Contract` combined with a compensation figure phrased as an hourly rate for a
  single interview rather than a salary band.

## 2. Skill/domain mismatch invisible to the eligibility gate

- **Inferact #61469, #61470 (duplicate), #61471, #61472** — all four "Member of Technical Staff"
  postings require deep vLLM/PyTorch-internals/transformer-research depth ("contributed core
  features to vLLM," "read and implement inference techniques from research papers"). The
  eligibility gate is about legal/visa/seniority hard-stops, not skill-fit, so it correctly scored
  these `eligible` — but nothing in the pipeline flags a generalist-profile mismatch against a
  posting this specialized.
- **#61469 and #61470 are also an exact-title duplicate** ("Member of Technical Staff, Inference")
  at the same company that boardwatch's slate/cluster cap did not catch, because they likely have
  different `content_hash` (different UUIDs, possibly slightly different body text).
- **Gap:** boardwatch has no skill-overlap scoring between the posting's stated stack/depth
  language and the profile's evidenced stack — it ranks by keyword coverage (`covers N/M skills`)
  which a posting can pass by mentioning generic terms (Python, PyTorch) despite requiring years
  of specialized research depth the coverage score doesn't capture.

## 3. Mass-posting / spam pattern, not deduplicated

- **Clera #111054, #111053, #224144** — the org's live Ashby board carries **278 open positions**,
  dozens of which are near-identical "Founding Engineer ($3M pre-seed)" postings independently
  listed per US/EU city (Houston, Austin, Denver, Toronto, Atlanta, Seattle, ...), plus bizarre
  "Founding Engineer – SF Hackerhouse (Visa sponsored)" postings listed as **on-site** in Stuttgart,
  Hamburg, Vienna, Aachen. All three of the specific postings surfaced to this session had also
  gone dead (404) by fill time. This reads as a company running a low-quality/possibly
  talent-farming recruiting funnel rather than a real hiring pipeline.
- **Gap:** no per-company "total open postings" or "posting-title entropy" signal that could flag
  a board like this as low-trust before it reaches the eligible queue. A simple heuristic — flag
  any company where >N postings share a normalized title, or where the same title appears in >M
  cities same-day — would have caught this without needing to read the board.

## 4. Duplicate posting, same company, different external title

- **Metaview #169645 (kept) / #169646 (skipped)** — "Software Engineer, Product" and "Full Stack
  Product Engineer" are the same internal role (`Member of Product Staff, Engineer`), same
  funding/comp blurb, same team — republished under two external titles, presumably for SEO/board
  reach. Content-hash-based dedup would not catch this since the JD text differs (different title,
  different framing paragraphs) even though the underlying job is identical.
- **Gap:** dedup keyed on JD content-hash misses "same company, same internal title/comp,
  differently-worded external posting." Would need a semantic-similarity or internal-title-field
  signal (when the ATS exposes one, as Ashby overview pages sometimes do — "Metaview's internal IC
  title is Member of Product Staff, Engineer").

## 5. Comp band signals seniority the scoring didn't downgrade for

- **Embedding VC / OpenArt #170878** — "Growth Engineer, Globalization" with **$300K–$400K total
  comp**. That band is an unambiguous senior/staff signal, but nothing in the eligibility or
  ranking pipeline reads compensation as a seniority proxy — `top` still surfaced it as apply-worthy.
- **Gap:** parse `salary_min`/`salary_max` (already columns on `postings`) against a
  profile-relative "new-grad band" ceiling and fold that into the seniority-band gate the README
  already documents for title-based over-seniority detection — this is the same gate, just missing
  a compensation-based input alongside the title-based one.

## 6. Visa sponsorship stated in JD, but not the visa needed — only visible at full read

- **Sauna (Wordware) #204390** — "Growth Engineer." States explicitly: *"We require US work
  authorization, but are open to O-1 or J-1 visa sponsorship for exceptional candidates."*
  O-1 (extraordinary ability) and J-1 (exchange visitor) are specific visa classes; a profile whose
  declared work-authorization need is a different class is not served by either. A naive "mentions
  sponsorship" keyword check would false-positive this as sponsor-friendly.
- **Gap:** if the eligibility gate has any "sponsors visas" keyword signal, it likely doesn't
  distinguish *which* visa class is offered against the profile's specific need. Worth checking
  whether `eligibility/` extracts visa-type specificity or just a boolean "mentions sponsorship."

## 7. Defense/export-control/citizenship — gate did not fire

- **Allen Control Systems #237734** — "Software Engineer – Enterprise Applications." Company
  overview explicitly: *"ACS is a defense technology company... flagship product, Bullfrog, is an
  autonomous precision weapon system... deployed with U.S. forces."* This specific req (ERP/Odoo,
  Python/React) has no clearance language of its own, but the company-level defense/weapons signal
  should be enough to exclude it under a conservative policy, and evidently wasn't.
- **Tenet3 #247643** (Greenhouse, not Ashby) — explicit on-form text: *"This position requires
  current U.S. citizenship in order to achieve and maintain a security clearance"*; company self-
  identifies as a federal contractor. Citizenship requirement was on the live application form, not
  necessarily in the JD body boardwatch indexes.
- **Relativity Space #52447** (Greenhouse) — explicit ITAR export-control gate on the live
  application form: must be a "U.S. person" (citizen/green-card/protected individual) **or**
  otherwise hold a federal export-control license — no general non-US-person pass-through (contrast
  with Cerebras Systems #237110 below, which *does* have a "not a US person, and not a citizen of
  Cuba/Iran/North Korea/Syria" option that clears a non-US-person applicant). This distinction —
  some ITAR/EAR gates have a real non-US-person path and some don't — is only visible on the actual
  form, never the JD.
- **Gap:** the "defense/clearance" hard-stop family evidently keys on JD-body text
  (regex/LLM judge over the stored posting body), which will always miss (a) company-level defense
  signals not repeated in every individual req's body, and (b) export-control language that lives
  only on the ATS's live application form, not the fetched JD. A company-level defense/ITAR flag
  (checked once per company, applied to all its postings) would close gap (a); nothing short of a
  live-form fetch closes gap (b) — this may be an accepted permanent limitation, worth stating
  explicitly rather than silently missing.

## 8. Dead postings still served as `open` + `eligible`

- **Ashby: 42dot #156724, Cohere #188104** — both apply URLs 404 (Ashby shows a bare "Jobs" page,
  empty).
- **Greenhouse: National Information Solutions Cooperative #224391, SoFi Tech Solutions #224393,
  Twilio #110283** — all three redirect to `?error=true` on the modern job-boards.greenhouse.io
  domain.
- **Gap:** `postings.status` still read `open` for all five at the time of this session (all
  were also `verdict=eligible`), meaning boardwatch's own liveness/board-scan cycle hadn't caught
  the closure yet, or these particular postings fell outside whatever liveness check exists. Worth
  checking `last_seen_at` / `death_strikes` / `last_death_probe_at` for these five specifically —
  if they're stale, that's a liveness-sweep gap, not a one-off.

## 9. Non-SWE title inside an otherwise-SWE-coded company

- **fanaticscollectibles "Relic Cutter" #47197** — a warehouse/manufacturing role (physically
  cutting sports-memorabilia relics) at a company whose other postings are legitimate e-commerce
  software roles. Title carries zero SWE signal but apparently didn't hit the non-SWE title
  filter's blocklist, and the JD body must have scored some skill-keyword overlap by coincidence.
  The README documents this filter as deliberately conservative on ambiguous titles ("a title that
  gives no signal either way is never filtered"), so this may be working as designed rather than a
  bug — flagging for awareness rather than as a clear defect.

## 10. Citizenship requirement only on the live form

- **Giftogram #169732** — "Junior Full Stack Developer." Live application form asks: *"Are you a
  US Citizen or Green Card Holder that can work onsite in Whippany NJ ~3 days per week?"* Nothing
  in the JD body signals this; same class of gap as #7's Tenet3/Relativity Space finding — some
  hard-stops only exist as an application-form question, not fetchable JD text.

## Summary by gap class

| Class | Postings | Fixable from stored JD text? |
|---|---|---|
| Not a real job (research panel) | 1 | Maybe — department/comp-framing heuristic |
| Skill-depth mismatch vs. generalist profile | 4 | Would need new scoring dimension |
| Mass-posting/spam board | 3 | Yes — per-company posting-count/title-entropy heuristic |
| Same-company duplicate, different external title | 1 | Hard — needs semantic similarity |
| Comp band implies seniority | 1 | Yes — already-stored `salary_min`/`salary_max` |
| Visa class offered ≠ visa class needed | 1 | Yes — if gate tracks visa type, not just boolean |
| Defense/clearance/ITAR, company-level or form-only | 3 | Partial — company-level flag catches 1 of 3 |
| Dead posting still `open`+`eligible` | 5 | Yes — liveness sweep should have caught these |
| Non-SWE title, ambiguous, filter abstained | 1 | Working as designed (conservative by choice) |
| Citizenship requirement, form-only | 1 | No — not in fetched JD |

Five of twenty-two skips (23%) were dead postings boardwatch still listed as open+eligible — the
single largest fixable category found this session, and the cheapest (it's a liveness-sweep gap,
not a scoring-logic gap).

---

# Measured follow-up, 2026-09-21 — what survived and what re-sized

This file sat untracked for four days. Before ticketing anything from it, every claim that could
be checked against the live store was checked. **Two of the ten classes changed materially.**

## §8 (dead postings) re-sizes, and it is LATENCY, not blindness

All five named postings have since closed — `156724` and `224391`/`224393` on 2026-09-21,
`188104` and `110283` on 2026-09-19 — each at `consecutive_missing = 2`. The liveness sweep was
not missing them; it was **behind** them by 2–4 days. So "the single largest fixable category"
is not a detection gap.

Sized at the population: of **8,495** open + eligible postings, **114 (1.34%)** carry
`consecutive_missing ≥ 1`, i.e. are already inside the closure pipeline. And over the 26,130
postings that closed in the last seven days, the interval from `last_seen_at` to `closed_at` is
**mean 8.33 days, max 16.9**.

**Caveat that bounds the 8.33, stated because it changes what the number means:** a board
answering `304 Not Modified` lists nothing, so this interval is not purely "days spent serving a
dead posting". Read it as closure latency of the sweep, not as a dead-serving duration, until the
`last_seen_at` semantics under `unchanged` are confirmed.

**This class is ALREADY INSTRUMENTED and should not be re-ticketed as new.** T117 and T126 ship
the reporting, and funnel-469 states the standing cohorts directly: **42 watched boards have
never recorded a `complete` scan with 16,567 open postings under them that nothing can retire**,
and 302 boards completed before but not within a day with 46,233 under them. What is open here is
whether the latency is worth reducing — a decision, not a defect.

## §5 (comp band) is the cheapest real fix in this file

`salary_min` / `salary_max` are already columns on `postings`, and the seniority-band gate already
exists — it is fed only by the title. This is a missing input to a shipped gate, not a new
subsystem.

## What the rest of the file is worth, given what run 469 measured today

Today's reading shows the pipeline is **supply-saturated**: 8,491 eligible, `capped_by_top_n`
**10,533** postings that cleared every filter and lost only on rank, against `--top 40`. So every
class in this file is worth more than it looks. These are not "leads we would otherwise miss" —
they are **slots**. A posting removed by any of these checks is replaced from a 10,533-deep queue,
so each fix converts directly into one more applyable lead per occurrence, and lands on B8's
precision half rather than its volume half.

That inverts the usual priority: precision work on the delivered 40 now pays better than
discovery work that adds to a pool already 263× larger than the daily slate.

## Standing classification

| § | class | status |
|---|---|---|
| 1 | research-panel posting mis-read as a job | open, new |
| 2 | skill-depth mismatch vs generalist profile | open, new — a scoring dimension, the largest build |
| 3 | mass-posting board (Clera, 278 open) | open, new — per-company title entropy |
| 4 | same company, one role, two external titles | open, new — needs semantic similarity |
| 5 | comp band implies seniority | **open, new — cheapest: columns and gate both already exist** |
| 6 | visa class offered ≠ visa class needed | open, new |
| 7 | defense/ITAR at company level or form-only | partial — company-level flag reaches 1 of 3 |
| 8 | dead posting served as open+eligible | **NOT new — instrumented by T117/T126; re-sized above** |
| 9 | non-SWE title, ambiguous, filter abstained | working as designed (conservative by choice) |
| 10 | citizenship stated only on the live form | permanent limitation — state it, do not chase it |

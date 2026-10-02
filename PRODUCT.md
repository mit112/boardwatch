# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

A job seeker running boardwatch on their own machine, reviewing the leads it delivered and applying to the ones worth their time, usually in a daily sitting. The viewer (`boardwatch web`) is theirs alone: it opens in their browser, on the loopback interface, behind a bearer token. The repository is built to fit anyone who runs it, whatever their visa status, seniority or field, so no field or person is assumed.

Their job in the viewer: choose which leads to look at, see what the automatic checks could and could not settle, get the prepared résumé and their saved application answers in hand, open the employer's page, and record the application when, and only when, they have sent it. Afterwards they track what happened to each application.

## Product Purpose

boardwatch finds postings, checks them against the person's profile with eligibility rules, prepares a résumé for each, and delivers a queue. The web viewer is the one interface onto that queue and onto the history after it. Success is that a person can get from "what is worth applying to" to "recorded, with the right materials" without friction, and can always tell what the tool knows, what it does not know, and what they did.

## Positioning

The tool reports what it knows and what it does not. Every verdict carries its own evidence (which rule read which requirement, against which profile field, quoting which span), an unmet or unknown requirement is never relabelled, and "no flags" never means "cleared". The mechanism is the evidence chain, taken from the repository's own keystone invariant; no comparison with other products has been made.

## Operating Context

- Leads arrive from a scheduled pipeline run. The viewer reads the store and writes only what the person does: mark applied or skipped, report a lead, dispute a verdict, add a note, set a follow-up date, change an application's status.
- The apply lane holds leads with a prepared résumé PDF; the review lane holds leads with something the checks could not settle. A lead is a posting, not a company.
- Applications are recorded in a ledger with statuses (applied, interviewing, offer, rejected, withdrawn) and an event history. "Unmark applied" and `withdrawn` are the same write.
- The viewer serves a committed bundle from disk while its API runs in memory, so a stale server is a real state the interface must tolerate.
- Application answers (the saved responses to common form questions) are personal and must never reach logs, screenshots shared outside the machine, or the repository.

## Capabilities and Constraints

- Four independent readings per job, never combined into a score: requirements, independent review, posting availability, résumé. A requirement is satisfied, unmet, unconfirmed or not assessed. Résumé keyword coverage is a separate question from eligibility.
- Progress counts only applications the server has confirmed, in the browser's local calendar. "This week" is the past 7 days (an assumption, not an owner ruling).
- Out of scope by the owner's ruling: auto-apply, auto-fill, browser automation of any kind, cover letters, outreach and referral scaffolding.
- Local only: loopback, a bearer token carried in the URL fragment (which is also the router), a content security policy with no inline script. The built bundle is committed under `src/boardwatch/web/static/` with a hash manifest that a test checks.
- Eligibility policy, ranking, résumé generation, discovery and the scheduled pipeline are separate subsystems and are not part of this product surface.
- Open product decisions: whether a record key (`a`) should require the job's workspace to be open; whether "this week" means the past 7 days or Monday to Sunday.

## Evidence on Hand

- `web/src/fixtures/` holds placeholder identity data and edge-case leads for demonstrating the interface without a store. It is never compiled into the shipped bundle.
- `CHANGELOG.md` and `docs/program/DECISIONS.md` (D-617 for the redesign) record what shipped and why.
- No usability study, interview or usage analytics exists. Nothing here may claim the interface increased applications, motivation or retention; none of those has been observed.

## Product Principles

1. **Unknown stays unknown.** A reading the tool could not take is shown as not taken, never as met, missing or clear, and a disagreement between two readings shows both.
2. **The person decides.** Opening a link, returning to the tab or reading a job records nothing. An application is recorded only when the person says so, and a count moves only after the write is confirmed.
3. **Progress shows the person's own effort.** No streaks, goals, countdowns or pressure, and a zero is printed as a zero.

## Accessibility & Inclusion

WCAG 2.2 AA is the required floor: visible focus that is never hidden by sticky chrome, targets of at least 24 px, contrast of at least 4.5:1 for text in both light and dark themes, reflow without two-dimensional scrolling at 320 CSS px, and full keyboard operation. The interface follows the system theme with an explicit toggle.

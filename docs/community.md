# Community home

boardwatch's community home is GitHub Discussions. This file is the **launch-ready plan**
for it: the categories to create, the seed posts to publish, and a short checklist to turn
it on. Discussions is intentionally **off until launch** so it opens with content and real
traffic rather than an empty forum. Nothing here enables anything — flipping the switch is
a manual owner step (see the checklist below).

## Why a community home

The engine, packaging, and eligibility evidence are the product. The community home is where
users do the things the code cannot do for them: show a working configuration, share a public
board that should be in the registry, and report an honest outcome. It is support intake's
counterpart — the issue templates take bug reports and provider requests; Discussions is for
everything that is a conversation rather than a defect.

## Categories to create

Three to start. Add more only when a real thread does not fit one of these.

| Category | Format | What it is for |
|---|---|---|
| **Show and tell** | Open discussion | A working setup: which boards you watch, your target/excluded titles, a scan or `top` you are proud of. Screenshots welcome — with personal data cropped out. |
| **Boards & providers** | Open discussion | "This public board should be in the registry", "please support provider X", "board Y went dead". The fast path for a board that is already supported is still a registry PR (see [CONTRIBUTING](../CONTRIBUTING.md)); this is for discussion and provider requests. |
| **User results** | Open discussion | Honest outcome reports — shortlists, applications, interviews, what did and did not work. Population and caveats encouraged; numbers without them are noise. |

Optionally add an **Announcements** category (announcement format, maintainers post) for
releases once the release cadence is public. Keep the starter set to the three above.

**Standing privacy rule for every category:** do not paste résumé text, work history,
work-authorization answers, home-directory paths, or contact details into a public thread.
The same rule that governs the repo (see [CONTRIBUTING](../CONTRIBUTING.md), "What must never
enter this repo") governs Discussions — the difference is that here no automated check can
catch it, so the poster owns it.

## Launch checklist

When launching, the owner performs these steps once (they cannot be scripted safely and are
deliberately manual):

1. **Enable Discussions:** repo **Settings → General → Features → Discussions**.
2. **Create the three categories** above with the listed formats. Delete the default
   categories you do not want.
3. **Publish the two seed posts** below — the welcome post in Show and tell (pin it) and the
   board post in Boards & providers.
4. **Link Discussions from the README** community/contributing area once it is live.

## Seed post — welcome (Show and tell)

> **Title:** Welcome — show your boardwatch setup
>
> boardwatch is a local job radar and a grounded résumé pipeline: it watches public company
> job boards, ranks new postings for you, explains each eligibility call with a quote from the
> posting itself, and helps you tailor a résumé — all on your machine, with no account, no API
> key, and no auto-apply.
>
> This is the place to show what you built: which boards you watch, how you set your target and
> excluded titles, a `top` you are happy with. Crop personal data out of any screenshot.
>
> Two neighbours: **Boards & providers** is for "this public board should be in the registry"
> and provider requests; **User results** is for honest outcome reports. Bug reports and
> provider requests with a reproducible shape still go through the issue templates.
>
> One rule everywhere here: do not paste résumé text, work history, work-authorization answers,
> or contact details into a public thread. No automated check catches it in a discussion.

## Seed post — share a board (Boards & providers)

> **Title:** Share a public board that should be in the registry
>
> boardwatch ships a bundled registry of public company boards so `init` works offline. It is
> community-maintainable: the fastest way to add a board that a supported provider already hosts
> (Greenhouse, Lever, Ashby, Workable, SmartRecruiters, Workday) is a small PR — see the
> ["Contributing a board" walkthrough](../CONTRIBUTING.md#contributing-a-board), which includes a
> one-command local check before the full gate.
>
> Use this thread when a PR is not the right first step: you are not sure which provider a board
> is on, you want a provider that boardwatch does not support yet, or a board you watch went dead
> and you want to flag it. Paste the **public** board URL — never a private or gated one.

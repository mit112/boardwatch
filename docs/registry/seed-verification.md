# Registry seed catalog — verification evidence

Pre-`companies.yaml` attended evidence for the §6.6 / Issue #19 (GH #34) seed
registry. **This file is not the catalog** — it is the dated live-verification log
that the starter-set stability rule requires. `src/boardwatch/registry/companies.yaml`
is finalized only **after check 2** (≥ 7 days later), with Mit's recognizability
sign-off and the set-level workload timing, and lands as its own attended PR before
the Task 19 (GH #34) loop runs.

## Provenance (§0 guardrail 2 / §6.6 / D9)

Recorded in an attended session from **public** boards only. **Names, providers, and
slugs only** — no company copy, posting text, URLs, or PII. Posting counts are
heuristic evidence of a live, healthy board (a sanity signal, **not a gate**). The
loop never fetches live boards; it reads the finalized `companies.yaml`.

## Verification schedule (starter-set stability rule)

- **Check 1: 2026-06-13** — this log. Every entry returned HTTP 200 with ≥ 1 posting
  under politeness defaults (custom UA, ≥ 2 s spacing).
- **Check 2: scheduled 2026-06-20** (≥ 7 days later) — must land **before** Issue #19
  (GH #34) merges. Re-verify every entry OK; entries that fail either check are
  dropped before starter tagging.

## Provider tally (check 1, 2026-06-13)

- greenhouse: **18**
- lever: **5**
- ashby: **12**
- **total: 35** (≥ 30 across all three providers ✓)

## Candidate entries

`http_check1` = HTTP status @ 2026-06-13; `postings_check1` = recorded posting count
(heuristic). `http_check2` / `postings_check2` filled at check 2.

| provider | slug | name | http_check1 | postings_check1 | http_check2 | postings_check2 |
|---|---|---|---|---|---|---|
| greenhouse | `stripe` | Stripe | 200 | 505 | — | — |
| greenhouse | `airbnb` | Airbnb | 200 | 221 | — | — |
| greenhouse | `databricks` | Databricks | 200 | 790 | — | — |
| greenhouse | `coinbase` | Coinbase | 200 | 84 | — | — |
| greenhouse | `robinhood` | Robinhood | 200 | 165 | — | — |
| greenhouse | `dropbox` | Dropbox | 200 | 60 | — | — |
| greenhouse | `gitlab` | GitLab | 200 | 137 | — | — |
| greenhouse | `reddit` | Reddit | 200 | 144 | — | — |
| greenhouse | `discord` | Discord | 200 | 70 | — | — |
| greenhouse | `instacart` | Instacart | 200 | 166 | — | — |
| greenhouse | `twitch` | Twitch | 200 | 54 | — | — |
| greenhouse | `lyft` | Lyft | 200 | 138 | — | — |
| greenhouse | `pinterest` | Pinterest | 200 | 175 | — | — |
| greenhouse | `brex` | Brex | 200 | 237 | — | — |
| greenhouse | `cloudflare` | Cloudflare | 200 | 193 | — | — |
| greenhouse | `figma` | Figma | 200 | 170 | — | — |
| greenhouse | `asana` | Asana | 200 | 133 | — | — |
| greenhouse | `datadog` | Datadog | 200 | 403 | — | — |
| lever | `mistral` | Mistral AI | 200 | 171 | — | — |
| lever | `palantir` | Palantir | 200 | 228 | — | — |
| lever | `spotify` | Spotify | 200 | 144 | — | — |
| lever | `shieldai` | Shield AI | 200 | 379 | — | — |
| lever | `ro` | Ro | 200 | 58 | — | — |
| ashby | `ramp` | Ramp | 200 | 112 | — | — |
| ashby | `linear` | Linear | 200 | 25 | — | — |
| ashby | `vanta` | Vanta | 200 | 110 | — | — |
| ashby | `posthog` | PostHog | 200 | 16 | — | — |
| ashby | `mintlify` | Mintlify | 200 | 9 | — | — |
| ashby | `baseten` | Baseten | 200 | 70 | — | — |
| ashby | `modal` | Modal | 200 | 31 | — | — |
| ashby | `supabase` | Supabase | 200 | 48 | — | — |
| ashby | `neon` | Neon | 200 | 7 | — | — |
| ashby | `browserbase` | Browserbase | 200 | 6 | — | — |
| ashby | `render` | Render | 200 | 22 | — | — |
| ashby | `openai` | OpenAI | 200 | 731 | — | — |

## Not done this session (waits for check 2 + sign-off)

- Finalizing `src/boardwatch/registry/companies.yaml`.
- Tagging ~15 entries `starter` (per the #19 selection rule).
- Measuring the set-level cold scan→extract→rank workload (≤ 480 s budget; Task 25).
- Mit's explicit recognizability sign-off.


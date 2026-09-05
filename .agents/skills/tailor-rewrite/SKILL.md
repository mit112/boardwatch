---
name: tailor-rewrite
description: Drive boardwatch's subscription-tier (no API key) résumé rewrite handshake — a JD-aware rewriter step and a separate, JD-blind judge step — for one job posting. Use when the user asks to LLM-rewrite or "tailor B" a résumé bullet set via Codex itself rather than a paid API, or mentions `boardwatch tailor rewrite`.
---

# tailor-rewrite

Drives boardwatch's subscription Tier B résumé rewrite lane: a three-step CLI
handshake plus two Codex agent invocations. Requires
`llm.resume_tailoring_via_agent = true` in the user's boardwatch config (the CLI
gates on this and will refuse to run otherwise).

The core safety property: **the rewriter and the judge are separate agent
invocations.** The rewriter is JD-aware (it needs `jd_skills` to write a targeted
bullet). The judge is **JD-blind** — it must never see the job description, the
skills list, or `rewrite_request.json`. If one agent both rewrote JD-aware and
judged, JD-blindness would collapse: a judge that already knows the JD it wrote
toward cannot independently verify the rewrite is still entailed by the original
bullet. That is why the judge runs as a **separate** subagent, scoped to nothing
but `judge_request.json`.

Follow these six steps, in order, for posting `<posting-id>`:

## 1. Request

Run:

```
boardwatch tailor rewrite request <posting-id>
```

This runs Tier A internally and writes `rewrite_request.json` (default path
`{data_dir}/tailored/rewrite_request-<posting-id>.json`; override with `--out`).
Read that file. Its shape:

```json
{
  "request_id": "...",
  "jd_skills": ["skill", "..."],
  "bullets": [{"bullet_id": "...", "entry_id": "...", "a_text": "..."}]
}
```

## 2. Rewrite (JD-aware, this agent)

Acting **as the rewriter** in the current context — you MAY see `jd_skills` here —
propose exactly ONE reworded line per bullet in `bullets`. Do not fabricate
skills or claims not entailed by the original `a_text`; a downstream filter and
judge will reject overmatched or unentailed rewrites, but the rewrite should aim
to pass on its own merits. Write `candidates.json` with this exact shape:

```json
{
  "request_id": "<same request_id>",
  "candidates": [{"bullet_id": "...", "candidate": "..."}]
}
```

One candidate per bullet_id in the request. If a bullet has no good rewrite,
omit it (the CLI drops it as `no_candidate`, spending no judge call on it).

## 3. Screen

Run:

```
boardwatch tailor rewrite screen <posting-id> --candidates candidates.json
```

This re-derives each bullet's authoritative `a_text` from a fresh Tier A run,
runs the deterministic overmatch filter, and writes a JD-free
`judge_request.json` (default path
`{data_dir}/tailored/judge_request-<posting-id>.json`) containing only
filter-survivors. Its shape has **no `jd_skills` field, by design**:

```json
{
  "request_id": "...",
  "items": [{"bullet_id": "...", "a_text": "...", "candidate": "..."}]
}
```

## 4. Judge (JD-blind, SEPARATE agent)

Invoke a **separate, freshly scoped subagent as the judge**. Hand it ONLY the
contents of `judge_request.json` — never the job description, never
`jd_skills`, never `rewrite_request.json`, and never any context from step 2
that would reveal what the JD was. The judge's context must be constructed from
`judge_request.json` alone.

For each item, the judge must decide whether `candidate` is entailed by
`a_text` — no new skills, no new claims, no exaggeration — and reply with
**exactly one token**: `ENTAILED`, `NOT_ENTAILED`, or `UNSURE`. No other text,
no hedges, no annotations. boardwatch parses the reply with an exact-token
allowlist (`parse_verdict`): anything that is not one of those three exact
tokens (after trimming whitespace/`-`/`_`/`:`) fails closed to `UNSURE`, which
the lane treats as a drop. A hedge like "ENTAILED (mostly)" or "this is
probably entailed" is NOT accepted — it drops the bullet, by design, rather
than risking a false accept.

Collect the judge's replies into `verdicts.json` with this exact shape:

```json
{
  "request_id": "<same request_id>",
  "verdicts": [{"bullet_id": "...", "raw_reply": "ENTAILED"}]
}
```

One verdict per item in `judge_request.json`.

## 5. Apply

Run:

```
boardwatch tailor rewrite apply <posting-id> --candidates candidates.json --verdicts verdicts.json
```

This parses every verdict via `parse_verdict`, keeps only filter-pass ∧
`ENTAILED`, and emits both artifacts: the safe Tier A résumé and the reworded
`resume_tailored_llm` variant.

## 6. Remind the user

Tell the user: **every reworded bullet is human-review-gated.** The Tier A file
is the safe copy — always sendable as-is. The `resume_tailored_llm` variant is
LLM-assisted (rewriter + JD-blind judge, not structurally proven) and must be
reviewed by the user before it is sent anywhere.

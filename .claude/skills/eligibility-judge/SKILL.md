---
name: eligibility-judge
description: Drive boardwatch's P5 eligibility-oracle labeling handshake — an independent, JD-and-facts-only judge that produces the answer key's eligible/ineligible/uncertain verdicts for the held-out labeled set (Gate P5). Use when the user asks to label the P5 eligibility set, run the oracle, or mentions `boardwatch eligibility label`.
---

# eligibility-judge

Drives boardwatch's P5 oracle-judge labeling lane: a CLI-and-agent handshake
that turns unlabeled worksheet rows into the answer key Gate P5 is scored
against (`docs/program/PROGRAM.md` §3.P5 — precision ≥ 0.95 on INELIGIBLE).

## Independence property (read this before judging)

The oracle's verdict is only a valid measurement if it is **independent** of
anything boardwatch's own eligibility engine already believes about this
posting. Judge from **`jd_text` + `facts` alone** — nothing else:

- Never consult the deterministic engine's verdict for this posting.
- Never consult the worksheet's `hint` field. `label request` already drops it
  from the request payload for exactly this reason — do not go looking for it
  in the source worksheet either.
- Never consult a prior guess, an earlier oracle run, or a human label already
  recorded for this row.

If the judge's opinion is contaminated by any of these, "precision ≥ 0.95"
stops being a measurement and becomes the engine validating itself against its
own restated opinion. That circularity is exactly why labeling is a separate,
freshly-scoped step instead of something the engine computes about itself.

## 1. Request

Run:

```
boardwatch eligibility label request
```

This reads every `*.jsonl` file in the worksheet directory (default
`{data_dir}/eligibility-labels`, override with `--worksheet`), selects rows
with no `expected_verdict` yet, and writes `label_request.json` (default
`{worksheet}/label_request.json`, override with `--out`). Read that file. Its
shape:

```json
{
  "request_id": "...",
  "policy_version": "...",
  "prompt_version": "...",
  "reason_catalog": ["work_auth", "experience_years", "clearance", "degree", "contract_not_fte", "internship"],
  "policy": {"families": {"work_auth": "blocker", "...": "blocker"}},
  "judging_policy": "...",
  "items": [{"label": "...", "facts": {...}, "jd_text": "...", "bucket": "hard_stop|hard_negative"}]
}
```

## 2. Judge (JD-and-facts-only)

For every object in `items`, decide the verdict using **only** that item's
`jd_text` and `facts`. The request's own `judging_policy` field carries the
full prompt boardwatch ships; its load-bearing rules are reproduced here so
this skill is self-contained:

- **`facts` describes one real candidate's ground truth.** It may include
  work-authorization status and whether sponsorship is needed, highest degree
  held, employment-type preference (e.g. full-time only), total years of
  professional experience, and clearance status. A field **absent** from
  `facts` means "unknown," not "no."
- **Classify REQUIRED vs PREFERRED first.** For every requirement the JD
  states, decide whether it is REQUIRED or PREFERRED before judging it. Only a
  REQUIRED hard stop that `facts` fails can produce `ineligible` — a
  PREFERRED / nice-to-have qualification the candidate lacks is never itself a
  hard stop.
- **All six `reason_catalog` families are treated as blockers for this
  labeling pass:** `work_auth`, `experience_years`, `clearance`, `degree`,
  `contract_not_fte`, `internship`. A REQUIRED hard stop in any of these six,
  that the supplied `facts` fails, is eligible to produce `ineligible` —
  regardless of whether the live engine treats that family as a soft
  preference at runtime. This pass is calibrating the answer key, not
  replaying engine policy.
- **No force-fitting — the rule that keeps the key honest.** If the JD states
  a decisive hard stop whose category is **not** one of the six
  `reason_catalog` families (seniority language, role-family mismatch,
  location, and similar), output `uncertain`. **Never** force it into the
  nearest available family. Those categories are real hard stops; they are
  just out of scope for this six-family judgment.
- **Evidence is mandatory for `ineligible`.** Cite the verbatim decisive
  sentence from the JD — an exact substring of `jd_text`, not a paraphrase or
  summary. An `ineligible` verdict whose `evidence` cannot be found in the JD
  as written is worthless as an answer-key row and will be downgraded to
  `uncertain` by the apply step's provenance check.

Output exactly one verdict object per item, using only this schema:

```json
{
  "label": "<same label from the item>",
  "decision": "eligible | ineligible | uncertain",
  "reason": "<a reason_catalog family id, or null (null unless decision is ineligible)>",
  "evidence": "<verbatim JD sentence, required when decision is ineligible>",
  "confidence": "high | medium | low"
}
```

Write all verdicts to `verdicts.json` as a flat JSON list, one object per item
in `label_request.json`:

```json
[
  {"label": "...", "decision": "ineligible", "reason": "work_auth", "evidence": "...", "confidence": "high"},
  {"label": "...", "decision": "uncertain", "reason": null, "evidence": "", "confidence": "medium"}
]
```

For a large worksheet, judge in batches, or dispatch a subagent per batch —
each batch still needs only that batch's own slice of `items`. Never widen a
batch's context with anything the independence property above excludes.

## 3. Apply

Run:

```
boardwatch eligibility label apply --verdicts verdicts.json
```

This runs every verdict through the ineligible-gate — only `high`-confidence,
catalog-allowed, JD-verified-span `ineligible` verdicts survive as
`ineligible`; everything else downgrades to `uncertain` — and rewrites the
worksheet files in place, preserving every other column. Hard-negative rows
(labels with an `applied/` prefix) accepted as `ineligible` print as a
warning: Mit actually applied to those postings, so that combination is worth
a human look, not a silent accept.

## 4. Remind the user

`boardwatch eligibility score` reports precision against this answer key, but
the result is **oracle-only** until a human has audited a sample of it. Per
`docs/program/PROGRAM.md` §3.P5, `eligibility score` itself exits non-zero
until the audited-coverage bar is met — running this skill labels the set, it
does not by itself close Gate P5.

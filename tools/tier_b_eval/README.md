# Tier B entailment-gate eval harness

A dev tool: not shipped, not imported by `src/`, and excluded from `make check`
beyond the one hermetic test (`tests/unit/test_tier_b_eval.py`). It measures how
well the Tier B safety gate (`boardwatch.tailor.rewrite.filter` +
`boardwatch.tailor.rewrite.judge`) catches fabrication in reworded résumé bullets.

## The bar

Tier B's defense is layered, and so is its guarantee. It is **not** an
unconditional "zero false-accepts" — that claim only holds where a deterministic
rule can enforce it:

- **Filter-side guaranteed (deterministic, provider-independent):** the
  `invented_skill` and `inflated_number` families, plus invented Title-case
  brand/company names in `scope_creep` (the `_proper_nouns` rule), are rejected
  by the overmatch filter alone with **zero false-accepts**, regardless of which
  model — or no model — is behind the judge.
- **Best-effort, model-dependent (the LLM judge):** the remaining judge-only
  families (`negation_flip`, `seniority_inflation`, `unsupported_outcome`, a
  lowercase mid-sentence skill in `scope_creep`) are caught only if the
  configured judge catches them. A live run against DeepSeek (2026-08-03) caught
  all three of negation/seniority/unsupported at zero false-accept — but judge
  recall is provider-dependent and not guaranteed.
- **Human-review backstop (always):** every reworded bullet is marked
  `// reworded (Tier B)` and is meant to be read before it is sent. The gate
  raises the floor; the reader is the last line.

Terms:

- A **false-accept** is a `fabricated` case the gate PASSES — a fabrication that
  reached the reader. This is the failure mode Tier B exists to reduce.
- A **false-reject** is an `entailed` case the gate REJECTS — a safe rewrite that
  gets dropped, falling back to the original (unedited) bullet. Lost polish, not
  a correctness bug.

## Corpus

`corpus.yaml` holds ≥2 hand-labeled cases per family across
`{invented_skill, inflated_number, scope_creep, seniority_inflation,
negation_flip, unsupported_outcome, faithful}`, plus a `held_out` list of case
ids reserved from prompt tuning (score the judge against them; never edit
`REWRITE_SYSTEM`/`JUDGE_SYSTEM` to fit them).

Two families — `invented_skill` and `inflated_number` — are asserted at zero
false-accept under the **deterministic filter alone** (no LLM), as is the
invented Title-case brand/company name in `scope_creep` (caught by the filter's
`_proper_nouns` rule; case c15). The remaining fabrications are judge-only: the
deterministic filter cannot see a lowercase mid-sentence skill mention, a
flipped negation, an inflated seniority claim, or a swapped-but-still-present
number, so those are caught (if at all) by the LLM judge. The corpus's
`scope_creep` and `unsupported_outcome` families each still include a confirmed
deterministic-filter blind spot (see the comments in `corpus.yaml`) — a
lowercase skill mention (c5) and a swapped-number outcome (c11) — so the
`--live` report is an honest record of where each layer of the defense actually
earns its keep.

## Usage

```bash
# Filter-only: hermetic, no network, no API key.
uv run python -m tools.tier_b_eval

# Full gate: filter + judge over a live client. Needs llm.enabled = true and a
# provider configured in config.toml, plus BOARDWATCH_LLM_API_KEY in the
# environment. Responses are cached under {data_dir}/llm-cache like the
# production Tier B lane.
uv run python -m tools.tier_b_eval --live
```

Both modes print a per-family table of `n`, `false_accept`, `false_reject`.

## Why it's excluded from `make check`

`--cov=boardwatch` in `pyproject.toml` only measures the `boardwatch` package,
so `tools/` never counts toward the 85% coverage gate. `make check` does run
`mypy --strict` over `tools/`, so this package is kept fully `mypy --strict`
clean, but its `--live` path is never invoked during `make check` — only the
hermetic filter-only test (`tests/unit/test_tier_b_eval.py`) runs there.

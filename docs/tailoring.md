# Opt-in LLM tailoring (Tier B and the agent lane)

## Tier B (opt-in LLM)

Tier A never rewrites your prose. If you want bullets reworded toward a posting's
language, Tier B is an **opt-in**, off-by-default LLM lane on top of it:

```bash
boardwatch tailor run <posting-id> --tier-b     # alias: --llm
```

`--tier-b` requires all of the following, and does nothing (writes nothing, exits 1)
if any is missing — this is a pre-flight on your configuration, checked before any work
starts, and is a different exit 1 from the credential-death one described below:

- `llm.resume_tailoring = true` **and** `llm.enabled = true` — `resume_tailoring` is the
  only key Tier B adds, and it lives on the same `[llm]` block as the opt-in LLM
  eligibility-extraction tier (see [configuration](configuration.md)); no
  new section, no new secret. Both are settable via `boardwatch config set llm.enabled
  true` / `boardwatch config set llm.resume_tailoring true`, or interactively via
  `boardwatch settings toggle`. `provider`/`model`/`base_url` still require a hand-edit to
  `config.toml`.
- `BOARDWATCH_LLM_API_KEY` in the environment (never in `config.toml`).

Per bullet, Tier B proposes a reworded version, then runs it through a deterministic
overmatch filter and a fail-closed entailment judge (the judge sees only the two bullet
texts — original and reworded — and never the job description). A bullet is only kept
reworded if it passes both; otherwise Tier B silently falls back to the Tier A text for
that bullet, so a `--tier-b` run degrades to Tier A per bullet rather than abandoning the
résumé. The CLI reports how many bullets were reworded vs. fell back, and why.

**One case exits 1: a dead credential that kept nothing.** If the LLM credential turns out
to be unusable (exhausted credit, an invalid credential, or a key without access to the
model) **and** zero rewrites were kept, `--tier-b` exits 1 rather than reporting success
over an entirely un-reworded résumé. The Tier A résumé is still produced and on disk either
way. A credential that dies partway through, after at least
one rewrite was kept, still exits 0 — that is a real partial success.

Tier B costs **2 LLM calls per bullet** (propose, then judge), bounded by
`llm.max_calls_per_run` (default 50) — applied **per résumé**, not shared with the
eligibility LLM lane, which applies the same number per invocation of its own — so
roughly 25 bullets per run before the tail starts falling back with `drop_reason:
"budget"`. That budget is consumed even on a cache hit, by design, so re-running the same
posting does not extend it; raise `llm.max_calls_per_run` in `config.toml` instead. See
[configuration](configuration.md).

**Dual output, not a replacement.** `--tier-b` always writes the ordinary Tier A file
first — Tier B never runs in place of it — plus a second file/artifact
(`resume_tailored_llm`) with reworded bullets marked `// reworded (Tier B)` in the
rendered source. The lineage is recorded as B —`rewritten_from`→ A —`tailored_from`→
your master résumé, so either output can be traced back.

**Honest bounds (Tier B).** Tier B is **not** the no-fabrication guarantee above: passing
the filter and judge is evidence, not proof, and every reworded bullet is meant to be
**read by you before you send it**, not trusted blind. The guarantee is layered: the
deterministic filter rejects invented skills, added/inflated numbers, and invented
brand/company names outright, provider-independently; the entailment judge is a
best-effort, model-dependent second layer for the fabrications a text-diff can't see
(flipped negations, inflated seniority, swapped outcomes); and you are the backstop. The Tier A path never calls out
to a model, regardless of Tier B's settings; only `--tier-b` sends bullet text and the
posting's extracted JD skill names to the configured provider, and only when explicitly
enabled and requested. See [SECURITY.md](../SECURITY.md) for exactly what leaves your
machine and when.

## Tier B without an API key (agent lane)

`--tier-b` needs `BOARDWATCH_LLM_API_KEY` and a metered provider. If you only have a
Claude Code subscription and no API key, there's a second, subscription-driven Tier B
lane that gets the same reworded-bullet output by having Claude Code itself do the
rewrite, with boardwatch validating it through the identical filter + judge + Tier A
stack described above.

It's a three-command handshake, driven by the `tailor-rewrite` boardwatch skill
(`.claude/skills/tailor-rewrite`):

```bash
boardwatch tailor rewrite request <posting-id>                                     # 1. writes rewrite_request.json
# the skill's rewriter agent reads it and writes candidates.json
boardwatch tailor rewrite screen <posting-id> --candidates candidates.json         # 2. writes judge_request.json
# a SEPARATE, freshly scoped judge subagent reads it and writes verdicts.json
boardwatch tailor rewrite apply <posting-id> --candidates candidates.json --verdicts verdicts.json  # 3.
```

`request` runs Tier A internally and hands the rewriter agent each bullet plus the
posting's JD skills. `screen` re-derives the authoritative bullet text from a fresh
Tier A run and puts the rewriter's candidates through the same deterministic overmatch
filter as the API lane — but the `judge_request.json` it writes is **JD-blind by
construction**: it's built from only `(original, candidate)` pairs, with no job
description or skills field anywhere in it, and boardwatch's skill instructs the judge
to run as a separate subagent so it never inherits the rewriter's JD-aware context.
`apply` parses the judge's verdicts with the same exact-token allowlist as the API
lane and emits both artifacts.

Gate: `llm.resume_tailoring_via_agent = true`, settable via `boardwatch config set
llm.resume_tailoring_via_agent true` or `boardwatch settings toggle`. Unlike `--tier-b`,
this lane needs **no** `llm.enabled` and **no** API key — boardwatch makes no LLM call
itself in this lane; the rewriting and judging happen in Claude Code subagents outside
the CLI. Do not enable `llm.enabled` for this lane; it isn't required and isn't checked.

The per-bullet call budget is **advisory** here, not a hard spend limit: subscription
calls aren't API-metered, so it's set wide enough to never truncate a legitimate run
and functions only as a soft cap on how many bullets get attempted in one pass. Every
other safety backstop is unchanged: the Tier A file is always emitted alongside, every
reworded bullet is marked `// reworded (Tier B)`, and the artifact is meant to be
reviewed by you before it's sent — this lane is LLM-assisted and filter+judge gated,
not structurally proven, same as `--tier-b`. Provenance on the artifact records
provider `claude-code-agent`, model `subscription`, so it's distinguishable from an
API-lane run.

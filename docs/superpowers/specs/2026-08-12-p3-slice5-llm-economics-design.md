# P3 Slice 5 — LLM economics: lane-death, scoped to the lanes that call out

**Date:** 2026-08-12 · **Status:** design approved by Mit, ready for an implementation plan.
**Supersedes the framing of** PROGRAM.md §3.P3 item 10, whose premise this design falsifies (§1).

---

## 1. The premise this replaces

PROGRAM.md item 10 opens: *"At 2 model calls per bullet, B1's ≥10 leads/day is ~300 calls/day
unattended."* **That configuration does not exist.** `boardwatch run` makes zero LLM calls in the
tailor lane, verified three independent ways:

1. `src/boardwatch/pipeline/runner.py` contains no reference to `client`, `llm`, or `build_client`.
2. `runner.py:522` calls `run_tailor(...)` with no `client` argument; the parameter defaults to
   `None` (`reports/tailor.py:401`).
3. `reports/tailor.py:459` gates the whole Tier-B block on
   `if client is not None or tb_override is not None:` — always false on that path.

`build_client` has exactly two callers: `cli/tailor_cmd.py:132` and `cli/eligibility_cmd.py:299`.
Neither runs inside the pipeline. No decision in either log records the omission as deliberate;
D-033 covers Tier-B provenance, not wiring.

**Consequence for this slice.** The unattended runner's leads are Tier-A-only always — not because
of budget, quota, or the `resume.yaml` bullet-length gate, but because the API lane was never wired
in. Mit ruled on 2026-08-12 to **scope this slice to the paths that do call out** and record the
unwired pipeline as a documented gap rather than fixing it by fiat.

Also stale, and to be corrected when this ships: PROGRAM.md:349 still lists *"resumable
idempotence"* as open under item 10. **D-042 declined it** (`DECISIONS-ARCHIVE.md:1815`) after four
unsound design iterations. Its justifying premise was re-verified here and holds — `ResponseCache`
is wired into the Tier-B lane at `tailor/rewrite/lane.py:357-366`, so a re-run does not re-pay for
model calls.

## 2. The defect this slice exists to fix

`eligibility/extract_llm.py:143-148` catches **every** exception from `client.complete()` and
returns `None`. Its caller, `cli/eligibility_cmd.py:362-384`, **ignores the return value** and does
`evaluated += 1` unconditionally, then prints `f"extracted {evaluated} postings"`.

With a dead credential and a cold cache over at least 50 open postings, `boardwatch eligibility
extract` therefore:

- makes up to `llm.max_calls_per_run` (default 50) doomed HTTP calls, one per posting;
- writes zero **eligibility** rows (a `runs` row *is* still minted and finished — see §5.3);
- prints **"extracted 50 postings"**;
- exits **0**.

With fewer postings or a warm cache the numbers differ; the shape does not.

This is the "no flags ≠ cleared" silent-success class the program has already paid for three times
(D-138, D-141, D-142). It is the highest-value target in the slice, and it is in the only lane that
loops over live calls.

The tailor lane has the same shape at lower volume: `tailor/rewrite/lane.py:90` and `:286` are bare
`except Exception` boundaries that record `drop_reason="error"`, so a dead credential burns
~2×bullets calls, keeps every Tier-A bullet, and ships the lead reporting success.

## 3. Scope

**In scope** — the two paths that construct clients:

| Consumer | Shape | Calls burned by a dead credential |
|---|---|---|
| `boardwatch eligibility extract` | loops over ranked postings | up to 50 (`max_calls_per_run`) |
| `boardwatch tailor --tier-b` | one posting, one résumé | ~2 × bullet count |

**Out of scope, deliberately:**

- Wiring Tier B into `pipeline/runner.py` — Mit's call, recorded as a gap (§8).
- A run-scoped call ceiling. Dropped as premature: the eligibility lane already has a working
  per-invocation cap (`eligibility_cmd.py:363`), and `boardwatch tailor` handles one posting, so
  per-lead and per-run coincide there. Only the misleading `max_calls_per_run` **name** is fixed,
  by docstring.
- Tailor-level idempotence — declined by D-042, not reopened.
- Batched judging — deferred with the rest of item 10's Tier-B work; it changes the
  `Proposer`/`Judge` callable contract and buys nothing until the pipeline calls out.

## 4. Decisions this design implements

Ruled by Mit on 2026-08-12, in order:

1. **Loud, but still terminal.** A dead credential keeps shipping the lead with its Tier-A bullets
   — that is a good outcome, not a failure. What changes is that the downgrade stops being
   *silent*: a typed reason, no further calls for the rest of the invocation, and it surfaces in
   the command's output. No new non-terminal lead state, so slice-3 cohort completeness is
   untouched.
2. **Fatal only when death was observed AND nothing landed.** If the credential dies partway, the
   invocation is a partial success — exit 0. If it dies before a single result landed, that is
   `RUN_CONTRACT.md` fatal condition 3's reasoning verbatim (*"an environment fault, not a per-lead
   one: every remaining lead would fail identically"*) — **exit 1**, via `typer.Exit(code=1)`,
   matching the existing failure exits in both commands. `RUN_CONTRACT.md`'s 0/1/2 table governs
   `boardwatch run` and is not extended here; these are subcommands with their own exit codes, and
   neither writes a `runs` row status that this change alters.

   **Both conjuncts are required, and the death conjunct is the load-bearing one.** Zero-landed
   alone is a routine *healthy* outcome, so keying the exit on it would break normal use:
   `tailor/rewrite/lane.py` has **thirteen** `kept=False` paths against exactly one `kept=True`
   (`lane.py:311`), and a healthy credential legitimately keeps zero rewrites whenever every
   candidate is judged not-entailed, echoed back `unchanged`, or filtered. Likewise a run whose
   calls all failed *unclassified* (network, malformed body — deliberately still swallowed per
   §5.3) must keep exiting 0. The condition is therefore **death observed** (a caught
   `LLMLaneDeadError` / a `lane_dead` row) **∧ zero landed** — never zero-landed alone.

   **This adds a new failure mode to commands that already have one.** `boardwatch eligibility
   extract` already exits 1 via `_no_profile()` (`eligibility_cmd.py:87-89`, called at `:332`), and
   `tailor_cmd` exits 1 on several configuration faults — so this is a new *reason* for a non-zero
   exit, not a new *possibility* of one. The precedent makes the change smaller than first written,
   but it is still a public CLI contract change and belongs in the changelog.
3. **One error class, not three.** A dead quota, a revoked key, and a key lacking model access all
   fail every remaining call identically; they differ only in why. One `LLMLaneDeadError` carries
   which in a typed field.
4. **A wrapper, not threaded state.** `ModelClient` is already a Protocol, so a wrapper is a
   drop-in requiring no signature changes.

## 5. Components

### 5.1 Typed lane-death at the raise site

**Files:** `llm/client.py` (new class), `llm/anthropic.py`, `llm/openai_compat.py`.

```
class LaneDeathReason(StrEnum):      # closed catalog
    CREDIT_EXHAUSTED
    CREDENTIAL_INVALID
    MODEL_FORBIDDEN

class LLMLaneDeadError(LLMError):
    reason: LaneDeathReason
```

Classification happens **at the raise site, from the response body's `error.type`** — never by
string-matching a message downstream (CLAUDE.md), and never from the HTTP status alone, because
Anthropic returns **403 for both `billing_error` and `permission_error`**, which mean different
things.

| Anthropic `error.type` | HTTP | Reason |
|---|---|---|
| `billing_error` | 403 | `CREDIT_EXHAUSTED` |
| `authentication_error` | 401 | `CREDENTIAL_INVALID` |
| `permission_error` | 403 | `MODEL_FORBIDDEN` |

`openai_compat.py` is **not** a single provider. `settings.provider` is a free-form `str | None` and
`base_url` is arbitrary (`core/settings.py:49-52`), so this adapter reaches OpenAI, DeepSeek,
Ollama, and any self-hosted proxy. One universal status table over arbitrary endpoints is unsound.
Its mapping is therefore deliberately **narrower** than Anthropic's, admitting only unambiguous
signals:

| openai-compat signal | Reason |
|---|---|
| HTTP 401 | `CREDENTIAL_INVALID` |
| HTTP 402 | `CREDIT_EXHAUSTED` |
| body `code`/`type` == `insufficient_quota`, **any status** | `CREDIT_EXHAUSTED` |

**Bare HTTP 403 is deliberately NOT mapped here** — on an arbitrary proxy it is not proof of
credential death, and mis-latching would suppress a lane that is merely misrouted. Anthropic keeps
its 403 mapping because its contract documents the two `error.type` values. This is narrower than
provider-specific classification tables and needs no provider identity plumbed into the adapter; if
a future provider's contract justifies more, add it then with the evidence.

**`insufficient_quota` is checked BEFORE the retryable-status branch, and this is the one place
lane-death overlaps 429.** OpenAI signals an exhausted balance as **429 with
`code: "insufficient_quota"`**, and DeepSeek as **HTTP 402**. Left to the status check alone, the
most common death mode — running out of money — is classified transient, retried four times per
posting under D-040's backoff, and then swallowed: the exact silent-success defect of §2, at 4×
the call volume. A 429 *without* that code remains transient and D-040 still owns it, so the
narrowing does not collide with `_RETRYABLE_STATUSES`; it removes one terminal case from it.

> **Externally-sourced, not repo-verifiable.** The OpenAI-429 and DeepSeek-402 behaviours come from
> provider documentation, which nothing in this repository can confirm. They are adopted because
> the error is asymmetric: mapping them wrongly costs one unnecessary lane-latch, while omitting
> them leaves the commonest death mode silently swallowed. Confirm against each provider's live
> error body during implementation and record what was observed.

**An unrecognized `error.type` stays a plain `LLMError`.** Out-of-catalog is a failure, never a new
bucket (CLAUDE.md).

**The classifier must never be the thing that raises.** Read defensively —
`isinstance(body, dict) and isinstance(body.get("error"), dict)` before touching `type`, and treat
a non-string `type` as unrecognized. A `TypeError` escaping the classifier would land in
`extract_llm.py:145`'s blanket `except` and reproduce the very silent success this slice removes.
The shapes that must degrade to plain `LLMError`: invalid JSON, empty body, non-object root
(`[]`, `"x"`), `error` as a string, missing `type`, non-string `type`.

### 5.2 The latching wrapper

**File:** `llm/run_client.py` (new, ~60 lines).

`RunScopedClient` implements `ModelClient` and wraps a real adapter. On `complete()`:

- if a death reason is already recorded, raise `LLMLaneDeadError(reason)` **without touching the
  network**;
- otherwise delegate; on `LLMLaneDeadError`, record the reason and re-raise.

It exposes `dead_reason` and `calls_attempted` for the consumers to report.

Constructed inside `build_client` (`llm/factory.py`), the single construction point. Both consumers
call `build_client` once per invocation, so the wrapper's lifetime is exactly one invocation — the
scope this design wants — and **no call site changes**. `build_client`'s existing contract is
preserved: it still returns `None` when the tier is off or uncredentialed.

D-040's ordering is preserved: retries live inside the adapter's `request_with_retry`, below the
wrapper, so a retried call still counts as one attempt.

### 5.3 Consumers stop and report

**`eligibility/extract_llm.py`** — add `except LLMLaneDeadError: raise` ahead of the blanket
`except` at line 145. The swallow stays correct for network failures and malformed bodies; it is
wrong for a dead credential, which no later posting can recover from.

**`cli/eligibility_cmd.py`** — **two counters, not one.** Today `evaluated` does double duty: it
caps the loop at `:363` *and* is the number reported at `:384`. Re-keying that single counter to
landed successes would silently destroy the cap — an unclassified failure (network, malformed
body) still returns `None`, so the counter would stop advancing and the loop would run the
**entire** posting set instead of stopping at 50. That would make this economics slice remove the
only working economics control in the codebase. Instead:

- `attempted` increments once per posting sent to `extract_and_record` and is what `:363` caps.
  **The ≤ `max_calls_per_run` bound must hold even when every call fails unclassified.**
- `extracted` increments only on a returned evaluation id, and is what the exit condition reads.
- Report both, plus the death reason when there was one.

Catch `LLMLaneDeadError` to break the loop, and exit 1 only under **death observed ∧
`extracted == 0`** (decision 2). `finish_run` still runs — the degenerate-run bookkeeping at
`eligibility_cmd.py:349-361` is unchanged and already documents that a provider outage recording a
finished run attributing zero rows is correct here. Note that a `runs` row therefore exists even
on the exit-1 path; that is deliberate and pre-existing.

Distinguishing genuine no-op from death is possible at this point: with a non-`None` client a
successful response always reaches `record_evaluation` (grounding failing closed to `[]` still
writes a row), so `None` **without** a caught `LLMLaneDeadError` is an ordinary swallowed failure,
and the typed exception is tracked separately from the counters.

**`tailor/rewrite/lane.py`** — both containment boundaries (`:90`, `:286`) gain
`except LLMLaneDeadError` ahead of the bare `except Exception`, recording
`drop_reason="lane_dead"` instead of the undifferentiated `"error"`. No re-raise and no
control-flow change: the wrapper already makes every later bullet free, and the run-level state
lives on the wrapper.

**`cli/tailor_cmd.py`** — scan the returned rows for `drop_reason == "lane_dead"` exactly as it
already scans for `"budget"` at line 235. That scan proves death **occurred**; it cannot say
*which* reason, because `RewriteRow.drop_reason` is a free-form string and duplicating the typed
reason into it would be classifying behaviour by string content (CLAUDE.md forbids it). To report
the reason, `tailor_cmd` narrows its own local `client` — which it constructed and therefore knows
the concrete type of — to `RunScopedClient` and reads `dead_reason`. `build_client` stays typed
`ModelClient | None`, and `ModelClient` keeps guaranteeing only `.complete`; no diagnostic method is
added to the Protocol, because only the two constructing call sites ever need it.

Exit 1 only under **death observed ∧ zero rewrites kept**. Zero-kept alone must stay exit 0 — it is
a normal healthy result (decision 2).

## 6. Fail-safe direction

Chosen per gate, as CLAUDE.md requires, and both gates here point the same way:

- The eligibility LLM lane is **advisory** — capped to `eligible`/`uncertain`, never `ineligible`
  (`extract_llm.py` docstring). The deterministic lane never sees a provider failure.
- Tier B is **opt-in rewording** layered over an intact Tier-A résumé.

So lane death must never delete or downgrade a real result. Nothing in this design touches a
verdict, a bullet, or a PDF. The behaviour changes are exactly three: stop calling, say why, and
exit non-zero when death was observed and nothing landed.

**Cached work still lands after the latch trips, deliberately.** The tailor lane checks
`ResponseCache` *before* `client.complete` (`lane.py:357-366`), so once the credential is dead,
cached bullets continue to succeed while uncached ones fail. That is the correct behaviour, not an
oversight: the cached response is identity-keyed and already paid for, and refusing it would
degrade a lead for no reason. Two consequences, both specified rather than left incidental:
a mixed invocation is a **partial success** and exits 0 under decision 2; and a fully-warm
invocation never probes the credential at all, so nothing dies in it and it exits 0 — correctly,
since this design reports what happened during *this* invocation, not the state of the account.
Test 11 locks this; test 5 requires a cold cache precisely because of it.

## 7. Testing

`make check` is the gate. Every test below must be confirmed red without its fix.

### 7.0 The trap this plan exists to avoid

**The established CLI fixture pattern monkeypatches `build_client` itself** —
`tests/pipeline/test_llm_lane.py:350,365,384` and `tests/unit/test_tailor_cmd_tier_b.py:206` all
replace `boardwatch.cli.<cmd>.build_client` with a lambda returning a scripted fake. Any new CLI
test written in that idiom **bypasses the factory, and therefore the wrapper entirely**: a fake that
raises `LLMLaneDeadError` on every call produces "one call attempted, extracted 0, exit 1" from the
consumer's `break` alone, with the latch and the factory wiring both reverted. Reverting
`build_client`'s wrapping would leave every such test green.

**Test 8 below is the only test that closes this**, and it must not monkeypatch `build_client`.

### 7.1 The tests

1. **Per-adapter classification** — each catalogued signal maps to its reason, for both adapters.
   **The test enumerates `LaneDeathReason` at run time** and asserts every member is covered by a
   fixture; a hard-coded list would let a mapping silently cover a subset (D-142's shape: "any of
   the twelve documents" survived a mutant covering 5 of 13). Two constraints on top of the
   enumeration: each fixture asserts its **expected reason**, not merely that the member is
   covered; and fixtures are **hand-written from provider error bodies**, never generated from the
   mapping table under test — a table-derived fixture agrees with itself.
2. **Out-of-catalog stays out** — an unknown `error.type` raises plain `LLMError`. Plus the
   explicit malformed-shape matrix from §5.1: invalid JSON, empty body, non-object root (`[]`,
   `"x"`), `error` as a string, missing `type`, non-string `type` — each raises plain `LLMError`
   with **no parser exception leaking**. Mutation: a default-reason fallthrough must go red.
3. **The latch is real** — against a counting fake, the second `complete()` after a death issues
   **zero** calls to the underlying adapter. Asserts on the fake's counter, never the wrapper's
   self-report.
4. **429 is discriminated, not blanket-transient** — a 429 *without* `insufficient_quota` still
   raises `LLMTransientError` and still retries under D-040; a 429 *with* it raises
   `LLMLaneDeadError(CREDIT_EXHAUSTED)` and does **not** retry. Asserts the retry count on both
   arms; a single-arm test would let the narrowing swallow ordinary rate limits.
5. **The silent-success fix** — a dead credential through `boardwatch eligibility extract` over a
   50-posting set, **on a cold cache** (fresh data dir; the shared `cli_env` fixture reuses one),
   yields `extracted 0`, exit 1, and **exactly one** call attempted. The call count is the
   load-bearing assertion; the message alone passes with the defect present.
6. **Partial success stays exit 0** — death after N successful extractions exits 0 and reports both
   counters and the reason.
7. **The tailor lane, both boundaries** — parameterised over death at *propose* (`lane.py:90`) and
   death at *judge* (`lane.py:286`). The judge arm needs a fake that succeeds propose and dies on
   judge, since with the latch set every later call would otherwise die at the propose boundary
   first and `:286` would never execute. Each arm asserts `drop_reason="lane_dead"` (not
   `"error"`), the Tier-A PDF still produced, the intended exit status, and **one** underlying
   adapter call across all remaining uncached bullets.
8. **The factory actually wraps** — call the object returned by the **real** `build_client` twice
   after a lane death and assert the underlying adapter was touched **once**, for both the
   anthropic and openai-compat branches. Stub at the HTTP layer (respx against
   `https://api.anthropic.com/v1/messages` returning a 401 `authentication_error` body;
   `AnthropicClient` constructs its own `httpx.Client`, which respx intercepts) and assert on the
   **route's** `call_count`. Also assert the disabled and uncredentialed paths still return `None`.
   **Do not monkeypatch `build_client` in this test** — that is the whole point of it.
9. **The cap survives unclassified failure** — an ordinary (non-lane-death) failure on a posting
   set **larger than 50** still attempts exactly `max_calls_per_run` and no more. This is the
   regression test for the two-counter split in §5.3; without it, re-keying the counter to
   successes silently unbounds the loop.
10. **Healthy zero-output stays exit 0** — the false-alarm lockout for decision 2, in both
    consumers: a healthy credential that keeps zero rewrites (every candidate `unchanged`, or the
    budget exhausted before any bullet) exits **0**, and an eligibility run whose calls all failed
    *unclassified* exits **0**. Without this, the exit-code change breaks normal use.
11. **Warm cache after death** — with cached entries present, work that hits the cache still lands
    after the latch trips and the invocation exits 0. Locks the §6 policy rather than leaving it
    incidental.

### 7.2 Regression sweep before the gate

A behaviour change verified only by the tests the commit itself edits ships red. Before spending 16
minutes on `make check`, grep for tests asserting the old `extracted N` message, the old
`drop_reason="error"` on provider failure, and any test asserting `build_client` returns a concrete
adapter type (`isinstance`, or attribute access on the result) — the wrapper changes what that
function returns.

## 8. Gaps recorded, not closed

- **`pipeline/runner.py` never constructs an LLM client**, so Tier B has never run under
  `boardwatch run`. Not a decision anywhere; needs one. Until it is wired, item 10's per-day call
  volume is zero and no ceiling is needed.
- **`llm.max_calls_per_run` is enforced per résumé in the tailor lane** (`reports/tailor.py:471`,
  `lane.py:62` resets `state` per call) while reading as a per-run cap. Harmless today because the
  pipeline never calls out; a docstring fix only. If the pipeline is ever wired, this becomes a
  real ceiling defect — leads × 50, not 50.
- **A cache hit still spends budget** (`_guarded` wraps the `call` closure, whose cache check is
  inside it). Known and user-facing — `tailor_cmd.py:239` says so explicitly. Left alone.

## 9. Decision to record at build

**D-146** — LLM lane-death is one typed error class classified at the raise site from the
provider's error body, latched per invocation by a `ModelClient` wrapper built in `build_client`;
consumers keep a separate attempted counter (which retains the `max_calls_per_run` cap) and landed
counter, stop calling on death, report both, and exit 1 only under **death observed ∧ zero landed**.
The openai-compat mapping admits only unambiguous signals (401, 402, `insufficient_quota` at any
status) and deliberately does **not** map bare 403, because `provider`/`base_url` are free-form.
The run-scoped ceiling and the pipeline wiring are deliberately not built, and PROGRAM.md item 10's
"~300 calls/day unattended" premise is retracted as false against the code.

## 10. Review record

Reviewed once by GPT-5.6-sol (**REWORK**, 2 BLOCKER / 4 MAJOR-MINOR) and DeepSeek-v4-flash
(**APPROVE-WITH-FIXES**, 4 MAJOR / 4 MINOR) on 2026-08-12, against `main` at `428ec76`. Both
independently verified all six load-bearing factual claims in §1/§2 as VERIFIED. The verdicts
differ in wording, not in substance: the two reviews' top findings are the same set, and the
severity curve is identical.

Findings adopted, each re-verified against the code before acceptance:

| # | Finding | Where fixed |
|---|---|---|
| 1 | Counting successes destroys the loop cap | §5.3 two counters, test 9 |
| 2 | openai-compat mapping misses the real quota signals (OpenAI 429 + `insufficient_quota`, DeepSeek 402) | §5.1 table, test 4 |
| 3 | Exit conditions unqualified — would fire on healthy runs | Decision 2, §5.3, test 10 |
| 4 | Tests bypass the factory via the established `build_client` monkeypatch | §7.0, test 8 |
| 5 | `drop_reason` string cannot carry the typed reason | §5.3 tailor paragraph |
| 6 | Malformed error-body shapes not enumerated | §5.1, test 2 |
| 7 | Judge boundary (`lane.py:286`) unreachable behind the latch | Test 7 parameterisation |
| 8 | Warm-cache-after-death policy left incidental | §6, tests 5 and 11 |

Two of the reviews' corrections were to **this spec's own factual claims**, both confirmed and
fixed: `boardwatch eligibility extract` already exits 1 via `_no_profile()` (so this adds a failure
*reason*, not a failure *possibility*), and the dead-credential path writes a `runs` row even
though it writes zero eligibility rows.

**One finding was adopted with a narrower fix than proposed.** GPT-5.6-sol's finding 2 recommended
provider-specific classification tables with provider identity plumbed into `OpenAICompatClient`.
Its own supporting argument — that an arbitrary proxy's 403 proves nothing — argues for *removing*
the ambiguous signal rather than cataloguing it, so bare 403 is simply unmapped for openai-compat.
That is less machinery than the spec originally had, not more, and needs no provider plumbing.

**One limitation is unresolved by design.** The OpenAI-429 and DeepSeek-402 quota behaviours are
provider documentation; nothing in this repository can verify them, and neither reviewer verified
them against a live endpoint. They are adopted on an asymmetric-cost argument (§5.1) and must be
confirmed against real error bodies during implementation.

**Exit criterion, stated before the round rather than after:** this spec took **one** external
review round, by Mit's instruction. It is closed by adopting the converged findings above; no
second external round is scheduled. The next review of this work is the code review of its
implementation, which reviews these fixes rather than re-reviewing the spec.

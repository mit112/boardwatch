# Pre-flight verification — P3 Slice 5 LLM lane-death plan

Read-only check of every factual claim in
`docs/superpowers/plans/2026-08-12-p3-slice5-llm-lane-death.md` against
`~/dev/projectY/bw-wt/p3-slice5` (branch `p3-slice5-llm-lane-death`, content
identical to `main` @ `428ec76`). Nothing was edited or committed.

**Score: 18 VERIFIED · 6 WRONG · 1 additional cross-cutting defect (not tied to a checklist item).**

| # | Claim | Verdict | Evidence |
|---|---|---|---|
| 1 | `client.py` imports / class names / `ModelClient.complete` / `LLMTransientError` is last | **WRONG** (sub-claim) | `client.py:3,6,10,25,33` |
| 2 | `retry.py` has `parse_retry_after`, imports `httpx`, exports `DEFAULT_ATTEMPTS` | VERIFIED | `retry.py:22,33,38` |
| 3 | `anthropic.py` error block at 89-96, URL, positional ctor | VERIFIED | `anthropic.py:14-15,22,33-40,69,89-96` |
| 4 | `openai_compat.py` error block at "87-93", URL, positional ctor | **WRONG** (range) | `openai_compat.py:86-93,31-38,73` |
| 5 | `_no_real_sleeps` at `test_llm_adapters.py:12-16`; no 401/402/403 assertions | VERIFIED | `test_llm_adapters.py:12-16`; repo-wide grep |
| 6 | `factory.py` returns at 40 and 46; type `ModelClient \| None` | VERIFIED | `factory.py:20,40,46` |
| 7 | `LLM_API_KEY_ENV` exists; how `build_client` reads the key | VERIFIED | `secrets.py:19,22-34`; `factory.py:32` |
| 8 | `LLMTier` kwargs + defaults; `Settings(data_dir, config_dir, llm=)` constructs | VERIFIED | `settings.py:38-56,71-101` |
| 9 | Nothing does `isinstance`/attr access on `build_client`'s result | VERIFIED | repo-wide grep, 8 call sites |
| 10 | `extract_llm.py` blanket `except` at 143-148; `complete(...)` shape | VERIFIED | `extract_llm.py:141-149` |
| 11 | `eligibility_cmd.py:348-384` names in scope; `evaluated` double duty; message | **WRONG** (one instruction) | `eligibility_cmd.py:348-384` |
| 12 | `extract_and_record -> int \| None`; `'{"requirements": []}'` writes a row | VERIFIED | `extract_llm.py:101,116-117,143-148,160`; `ground.py:55-56` |
| 13 | `test_llm_lane.py` fixtures / seeding helper / new fixtures buildable | **WRONG** (3 defects) | `test_llm_lane.py:60-109,282-320,388` |
| 14 | `lane.py` boundaries at 90/286, locals, `RewriteRow` fields, cache 357-366 | **WRONG** (misstated deltas) | `lane.py:74-103,270-299,357-366`; `result.py:17-25` |
| 15 | `tailor_cmd.py`: `client` in scope at 235; rewrites are dicts; budget scan | VERIFIED | `tailor_cmd.py:116,132,212-241` |
| 16 | `test_tailor_cmd_tier_b.py` helpers; `_write_tier_b_config(max_calls_per_run=)` | **WRONG** (3 test defects) | `test_tailor_cmd_tier_b.py:36-107,205-213,264-268`; `tailor_cmd.py:97` |
| 17 | `PROGRAM.md:335-355` | VERIFIED | `PROGRAM.md:340-350` |
| 18 | `settings.py:43-44` `max_calls_per_run` docstring | VERIFIED | `settings.py:43-44` |
| 19 | Highest D-number; heading + index-row format | VERIFIED | `DECISIONS.md:181,4290` |
| 20 | `CHANGELOG.md` top 25 / Unreleased section | VERIFIED | `CHANGELOG.md:1-25` |
| 21 | `respx` declared; no ordering plugin | VERIFIED | `pyproject.toml:57-67`; installed set = pytest, pytest-cov |
| 22 | Pre-existing `drop_reason == "error"` on provider failure | VERIFIED | `test_rewrite_lane.py:145-151`; `test_run_funnel.py:975` |
| 23 | Does `lane_dead` reach stdout? | VERIFIED (plan's assertion holds) | `tailor_cmd.py:222-229` |
| 24 | Rich `Console()` width / wrapping risk | VERIFIED (low risk) | `tailor_cmd.py:39`; `eligibility_cmd.py:63`; `test_eligibility_cmd.py:252,272,309` |

---

## 1 — `llm/client.py` — WRONG on one sub-claim

Current imports (`client.py:1-3`):

```python
from __future__ import annotations

from typing import Protocol, runtime_checkable
```

`Mapping` and `StrEnum` are absent, so the plan's replacement import block is a correct edit.

Classes and their bases:

- `client.py:6` — `class LLMError(RuntimeError):`
- `client.py:10` — `class LLMTransientError(LLMError):` with
  `def __init__(self, message: str, *, retry_after: float | None = None) -> None` (`:20`)
- `client.py:25-26` — `@runtime_checkable` / `class ModelClient(Protocol):`
- `client.py:33` — `def complete(self, prompt: str, *, system: str | None = None) -> str:`

**WRONG:** `LLMTransientError` is **not** the last class in the file. `ModelClient` follows it at
lines 25-46. "Immediately after the existing `LLMTransientError` class" therefore means *between*
`LLMTransientError` and the `ModelClient` Protocol, not at end-of-file. That placement is fine, but
an implementer who appends at EOF produces a different (also fine) file — the instruction is
ambiguous as written. Say "between `LLMTransientError` and `ModelClient`".

Note the Protocol signature matches `RunScopedClient.complete` in Task 4 exactly, and
`@runtime_checkable` means `isinstance(x, ModelClient)` works — nothing in the plan needs it, but it
exists.

## 2 — `llm/retry.py` — VERIFIED

- `retry.py:22` — `import httpx`
- `retry.py:33` — `DEFAULT_ATTEMPTS = 4`
- `retry.py:38-47` — `def parse_retry_after(response: httpx.Response) -> float | None:`

`safe_json` would be appended after line 47, before `request_with_retry` at `:50` — the plan's
"after the existing `parse_retry_after` function" is unambiguous here.

## 3 — `llm/anthropic.py` — VERIFIED

Lines 80-100 verbatim:

```python
 80	        if system is not None:
 81	            payload["system"] = system
 82	
 83	        # Use the provided client or create a new one
 84	        client = self._client or httpx.Client()
 85	
 86	        def _do_request() -> str:
 87	            response = client.post(url, json=payload, headers=headers, timeout=_TIMEOUT)
 88	
 89	            # Transient (retryable) vs. flat (non-retryable) HTTP errors
 90	            if response.status_code in _RETRYABLE_STATUSES:
 91	                raise LLMTransientError(
 92	                    f"HTTP {response.status_code}: {response.text}",
 93	                    retry_after=parse_retry_after(response),
 94	                )
 95	            if response.status_code < 200 or response.status_code >= 300:
 96	                raise LLMError(f"HTTP {response.status_code}: {response.text}")
 97	
 98	            # Parse and validate the response
 99	            try:
100	                body: Any = response.json()
```

Lines **89-96** are exactly the block to replace, comment included, and the shape matches the plan's
assumption (status check, `_RETRYABLE_STATUSES` at `:22`, `parse_retry_after`).

Current imports (`anthropic.py:14-15`):

```python
from boardwatch.llm.client import LLMError, LLMTransientError
from boardwatch.llm.retry import parse_retry_after, request_with_retry
```

URL: `base_url` defaults to `"https://api.anthropic.com"` (`:38`), and `url = f"{self.base_url}/v1/messages"`
(`:69`) → exactly `https://api.anthropic.com/v1/messages`. VERIFIED.

Constructor `__init__(self, model: str, api_key: str, *, base_url=..., client=...)` (`:33-40`) →
`AnthropicClient("m", "k")` is valid positional (model, api_key). VERIFIED, and matches the existing
suite's `AnthropicClient("claude-x", "k")`.

*Minor:* Task 2's **Files** header says `anthropic.py:86-96`; line 86 is `def _do_request() -> str:`.
Step 3's "lines 89-96" is the correct one.

## 4 — `llm/openai_compat.py` — WRONG (line range)

Lines 80-100 verbatim:

```python
 80	        # Use the provided client or create a new one
 81	        client = self._client or httpx.Client()
 82	
 83	        def _do_request() -> str:
 84	            response = client.post(url, json=payload, headers=headers, timeout=_TIMEOUT)
 85	
 86	            # Transient (retryable) vs. flat (non-retryable) HTTP errors
 87	            if response.status_code in _RETRYABLE_STATUSES:
 88	                raise LLMTransientError(
 89	                    f"HTTP {response.status_code}: {response.text}",
 90	                    retry_after=parse_retry_after(response),
 91	                )
 92	            if response.status_code < 200 or response.status_code >= 300:
 93	                raise LLMError(f"HTTP {response.status_code}: {response.text}")
 94	
 95	            # Parse and validate the response
 96	            try:
 97	                body: Any = response.json()
 98	            except (ValueError, json.JSONDecodeError) as e:
 99	                raise LLMError(f"Invalid response body: not JSON: {e}") from e
100	
```

**WRONG:** the replaceable block is **86-93**, not 87-93. The plan replaces 87-93 for this adapter but
89-96 (comment included) for Anthropic. Replacing only 87-93 strands the now-misleading comment at
line 86 — `# Transient (retryable) vs. flat (non-retryable) HTTP errors` — directly above a block
whose first check is lane death. Use 86-93 for symmetry with Task 2.

Imports are byte-identical to Anthropic's (`openai_compat.py:13-14`), so the plan's "update the
imports exactly as in Task 2" is correct.

Constructor `__init__(self, base_url: str, model: str, api_key: str, *, client=...)` (`:31-38`) →
`OpenAICompatClient("https://api.example.com/v1", "m", "k")` is valid positional. VERIFIED.

URL: `url = f"{self.base_url}/chat/completions"` (`:73`) → `https://api.example.com/v1/chat/completions`.
VERIFIED, and matches the existing suite's route.

## 5 — `tests/unit/test_llm_adapters.py` — VERIFIED

```python
12	@pytest.fixture(autouse=True)
13	def _no_real_sleeps(monkeypatch: pytest.MonkeyPatch) -> None:
14	    # Retry backoff must never cost real wall-clock time in tests (D-040).
15	    monkeypatch.setattr(time, "sleep", lambda _seconds: None)
```

It patches `time.sleep` globally (module-level `import time` at `:1`) — exactly what the plan says to
copy. Note tenacity sleeps via `time.sleep`, so this works.

**Existing transient/retry assertions Tasks 2/3 could break** — all survive, because every one of them
returns a **bodyless** response, so `safe_json` yields `None` and no lane death is classified:

- `:50-59` `test_openai_compat_retries_429_then_succeeds` — `Response(429)`, then 200.
- `:75-86` `test_openai_compat_honors_retry_after` — `Response(429, headers=…)`.
- `:89-96` `test_openai_compat_retries_exhausted_raises_transient` — `Response(429)` ×`DEFAULT_ATTEMPTS`.
- `:99-107` `test_openai_compat_non_retryable_400_fails_fast` — asserts `not isinstance(…, LLMTransientError)`, `call_count == 1`.
- `:169-181`, `:199-212`, `:215-224`, `:227-237` — the Anthropic mirrors.
- `:62-73` / `:184-197` — 500/502/503/504 parametrised.

**Tests asserting on 401/402/403/429 from either adapter:** none for 401/402/403 anywhere in `tests/`
except `tests/unit/test_liveness_prober.py:102` (`respx.get(URL).mock(return_value=httpx.Response(403))`),
which is the HTTP liveness prober, not an LLM adapter, and is untouched by this plan. 429 is asserted
only in the four transient tests listed above.

## 6 — `llm/factory.py` — VERIFIED

Whole file is 47 lines. Return type at `:20`:

```python
def build_client(settings: Settings) -> ModelClient | None:
```

Docstring `:21-29` (quoted in full):

```
    """Construct the provider adapter named by `settings.llm`, or None to skip the lane.

    Returns None when `settings.llm.enabled` is False, or when no credential is
    available via `resolve_secret(LLM_API_KEY_ENV)` (BOARDWATCH_LLM_API_KEY unset or
    blank). Both are ordinary runtime states, not errors. Once enabled with a
    credential present, a missing `model` (or, for a non-Anthropic provider, a missing
    `base_url`) is a configuration error and raises rather than degrading, so a
    misconfigured opt-in tier fails loudly instead of silently never calling out.
    """
```

Return statements:

- `:40` — `        return AnthropicClient(settings.llm.model, api_key)` (8-space indent, inside `if provider == "anthropic"`)
- `:46` — `    return OpenAICompatClient(settings.llm.base_url, settings.llm.model, api_key)` (4-space indent, function tail)

Both exactly where the plan says. The plan's two wrapped snippets use 8-space and 4-space indents
respectively, matching.

## 7 — `core.secrets` — VERIFIED

`secrets.py:19` — `LLM_API_KEY_ENV = "BOARDWATCH_LLM_API_KEY"`.
`secrets.py:22-34` — `resolve_secret(env_var, *, env=None)` reads `os.environ` **at call time**
(never bound at import) and treats blank/whitespace-only as unset. `factory.py:32` —
`api_key = resolve_secret(LLM_API_KEY_ENV)`.

`monkeypatch.setenv(LLM_API_KEY_ENV, "a-real-key")` in the plan's Task 4 tests therefore works.

## 8 — `core.settings` — VERIFIED

`settings.py:38-56`:

```python
38	class LLMTier(BaseModel):
39	    """Opt-in LLM tier config (D11, §5.1). Off by default; opt-in.
40	
41	    Carries only non-secret knobs; the credential is never a field here (it comes from
42	    the environment via core.secrets), which keeps secrets out of every serialize path.
43	    Includes extraction knobs (eligibility_extraction, base_url) and call budgets
44	    (max_calls_per_run) for LLM-assisted eligibility assessment.
45	    """
46	
47	    model_config = ConfigDict(frozen=True)
48	
49	    enabled: bool = False
50	    provider: str | None = None  # e.g. "anthropic" | "openai"; provider-neutral
51	    model: str | None = None
52	    base_url: str | None = None
53	    eligibility_extraction: bool = False
54	    resume_tailoring: bool = False
55	    resume_tailoring_via_agent: bool = False  # gates subscription Tier B; no API key needed
56	    max_calls_per_run: int = Field(default=50, ge=1)
```

All five kwargs the plan uses (`enabled`, `model`, `provider`, `base_url`, `max_calls_per_run`) exist,
with the types/defaults above. `max_calls_per_run` default is **50**, confirming the plan's
"more than 50 postings" requirement.

`Settings` (`:71-101`): only `data_dir: Path` and `config_dir: Path` are required; everything else is
defaulted, and `llm: LLMTier = Field(default_factory=LLMTier)` at `:100`. So
`Settings(data_dir=…, config_dir=…, llm=LLMTier(...))` constructs. The plan's `_settings` helper
mirrors `tests/contract/test_feature_prereq_contract.py:16-17` exactly.

*Note (Task 7 Step 3):* there is **no** `Field(description=...)` on `max_calls_per_run`. The text the
plan wants to amend is the LLMTier **class docstring** at 43-44. Amend the docstring; there is no
field description to edit.

## 9 — `build_client` result usage — VERIFIED (safe to wrap)

All 8 call/reference sites, none of which narrows the type:

| Site | Usage |
|---|---|
| `cli/tailor_cmd.py:132` | `client = build_client(gate_settings)`; then `if client is None:` (`:136`); passed to `run_tailor(client=client)` (`:156`) |
| `cli/eligibility_cmd.py:299` | `client = build_client(settings)`; then `if client is None:` (`:300`); passed to `extract_and_record(client=client)` |
| `tests/pipeline/test_llm_lane.py:220,231` | `assert build_client(settings) is None` |
| `tests/contract/test_feature_prereq_contract.py:25,27,29` | `is not None`, `pytest.raises(ValueError)`, `is None` |
| `src/boardwatch/core/features.py:90`, `eligibility/extract_llm.py:14` | comments only |

No `isinstance`, no attribute access, no `type(...)` assertion. Both consumers accept `client` typed
`ModelClient | None`, and `RunScopedClient.complete` matches the Protocol, so mypy is satisfied by
structural typing.

*Note:* `tests/contract/test_feature_prereq_contract.py:34-43` does `inspect.getsource(tailor_cmd)`
and asserts `"llm.enabled" not in fn_src` for `rewrite_request_cmd` / `rewrite_screen_cmd` /
`rewrite_apply_cmd`. Task 6 edits `run_cmd`, not those three, so it stays green — but do not
introduce the string `llm.enabled` into any of the three agent-lane commands.

## 10 — `eligibility/extract_llm.py` — VERIFIED

Lines 120-160 (the relevant window; the blanket `except` is at 145-148):

```python
141	    raw = cache.get(cache_key)
142	    if raw is None:
143	        try:
144	            raw = client.complete(payload["user"], system=payload["system"])
145	        except Exception:
146	            # Any provider/adapter failure (network, HTTP, malformed body) degrades this
147	            # opt-in lane to a skipped run. The deterministic lane never sees this.
148	            return None
149	        cache.put(cache_key, raw)
```

The plan says "replace lines 143-148" — correct, and the `client.complete(payload["user"], system=payload["system"])`
call matches its replacement byte for byte.

Docstring `Returns:` clause to update is at `:105-108`.

## 11 — `cli/eligibility_cmd.py:348-384` — WRONG on one instruction

Current block, verbatim:

```python
348	    evaluated = 0
349	    # This lane is invoked standalone, so it owns its run: a degenerate pipeline run whose
…	    (comment continues)
360	    # `runs` into a command log. The two rules differ because the invocations differ.
361	    run_id: int | None = None
362	    for current in ordered:
363	        if evaluated >= settings.llm.max_calls_per_run:
364	            break
365	        if run_id is None:
366	            run_id = ensure_run(app_ctx.engine, None)
367	        with app_ctx.engine.begin() as conn:
368	            extract_and_record(
369	                conn,
370	                posting_version_id=current.posting_version_id,
…	
380	            )
381	        evaluated += 1
382	    if run_id is not None:
383	        finish_run(app_ctx.engine, run_id)
384	    console.print(f"extracted {evaluated} postings")
```

**EXACT current printed message:** `f"extracted {evaluated} postings"` (`:384`). With one posting this
renders `extracted 1 postings`, which is asserted at `tests/pipeline/test_llm_lane.py:388`.

**`evaluated` double duty — VERIFIED.** It caps the loop at `:363` and is the reported number at `:384`.
The plan's warning is accurate. Note also that the current code **discards** `extract_and_record`'s
return value at `:368` — the plan's `evaluation_id = extract_and_record(...)` is a real change, not a
no-op rename.

**Every name the plan's replacement uses is in scope:**

| Name | Bound at |
|---|---|
| `ordered` | `:308` |
| `facts` | `:337` |
| `policy` | `:338` |
| `catalog` | `:339` |
| `cache` | `:340` |
| `client` | `:299` |
| `settings` / `settings.llm.max_calls_per_run` | `:292` / `settings.py:56` |
| `ensure_run`, `finish_run` | imported `:52-58` |
| `app_ctx.engine` | `:291` |
| `console` | `:63` (`Console()`) |
| `typer` | `:20` |

**WRONG:** Step 3 says *"Keep the existing explanatory comment about minting `run_id` (lines 349-361)
immediately above this block."* Line **361 is code**, not comment — `run_id: int | None = None`. The
comment is 349-**360**. Since the plan's replacement block re-declares `run_id: int | None = None`,
following the instruction literally produces a duplicate declaration. Say "lines 349-360".

## 12 — `extract_and_record` return contract — VERIFIED

Signature `:88-101` ends `-> int | None`. It returns `None` in exactly **two** places:

1. `:116-117` — `if client is None: return None`
2. `:145-148` — the blanket `except Exception: return None` around `client.complete`

Everything else falls through to `return record_evaluation(...)` at `:160`, which yields a real
evaluation id.

**`'{"requirements": []}'` writes a row and returns an id — VERIFIED.** `ground()` (`ground.py:51-56`)
does `json.loads` → gets a `dict` → `if not isinstance(parsed, list): return []`. So `spans == []`,
`items == []`, `verdict == "uncertain"` (`extract_llm.py:154-158` — empty `items` is falsy, so the
`all()` short-circuit is not reached), and `record_evaluation` runs and returns an id. This is the
same path `tests/pipeline/test_llm_lane.py:187-209` already pins with `FakeClient("[]")`.

The plan's partial-success test therefore gets `evaluation_id is not None` on call 1 → `extracted == 1`.
**Its dependency holds.**

## 13 — `tests/pipeline/test_llm_lane.py` — WRONG (3 defects in the new tests)

**Fixtures that exist** (all local to the file; there is no `tests/pipeline/test_llm_lane.py` conftest
contribution beyond `tests/pipeline/conftest.py` and `tests/conftest.py`):

| Fixture / symbol | Line | What it gives |
|---|---|---|
| `engine` | `:94-98` | `get_engine(tmp_path / "data")` + `ensure_schema`. **Shadows** `tests/pipeline/conftest.py:12`'s `engine` (`get_engine(tmp_path)`) — local wins. |
| `catalog_and_policy` | `:101-104` | `(load_rules(tmp_path/"no-such-cfg-dir"), Policy())` |
| `cache` | `:107-109` | `ResponseCache(tmp_path / "cache")` |
| `cli_env` | `:285-291` | Makes `cfg`, sets `BOARDWATCH_CONFIG_DIR`, **deletes** `BOARDWATCH_LLM_API_KEY`, returns `tmp_path / "data"` (a bare `Path`, **not** an `Env` dataclass) |
| `runner` | `:282` | module-level `CliRunner()` |
| `app` | `:13` | `from boardwatch.cli.app import app` |

`cli_env_with_postings` and `cli_env_with_many_postings` do **not** exist. VERIFIED as the plan states.

**Existing seeding helper:** `_seed_posting_version(engine, body, *, slug="acme-llm") -> int` (`:60-91`).
It seeds **exactly one** company + job + posting + posting_version per call, returns the
`posting_version_id`, and derives `provider_posting_id=f"p-{slug}"`, `content_hash=f"h-{slug}"`,
`slug=slug`. To get N postings you call it N times with distinct slugs. There is **no** multi-posting
seeder.

Other helpers the new fixtures must build on: `_invoke(data_dir, args, stdin=None)` (`:294-295`),
`_write_llm_config(cfg_dir, **fields)` (`:298-309`), `CLI_INIT_INPUT` (`:28`), `_posting_id_for_version`
(`:312-320`).

**Does any existing test assert `extracted` / `postings`?** Yes — one:

```python
388	    assert "extracted 1 postings" in result.output
```

in `test_extract_runs_and_writes_an_advisory_llm_row` (`:374-394`). Task 5 must update it. The plan
does flag this in Step 4; confirmed it exists and is the only one (repo-wide grep for
`extracted .* postings` returns exactly this line plus the emitter at `eligibility_cmd.py:384`).

### WRONG — defect (a): the new tests never pass `--data-dir`

The plan's tests call `runner.invoke(app, ["eligibility", "extract"])` **bare**. Every existing CLI test
in this file goes through `_invoke(cli_env, [...])`, which prepends `["--data-dir", str(data_dir)]`
(`:294-295`). Without it the command resolves `data_dir` from `BOARDWATCH_DATA_DIR`/platformdirs and
will read/write the developer's real boardwatch data directory. Use `_invoke(...)`.

### WRONG — defect (b): the response cache key omits `posting_version_id`

`extract_llm.py:130-139`:

```python
    content_hash = hashlib.sha256(jd_text.encode("utf-8")).hexdigest()
    identity_hash = hashlib.sha256(
        f"{content_hash}:{identity.profile_hash}:{identity.rules_hash}".encode()
    ).hexdigest()
    cache_key = cache.key(identity_hash, PROMPT_VERSION, model or "unknown")
```

`build_identity` (`hashing.py:76-116`) folds `posting_version_id` only into `input_fingerprint`, never
into `profile_hash` or `rules_hash`. So **two postings with identical `body_text` share a cache key.**

Consequence for `test_partial_success_before_death_exits_0`: if `cli_env_with_postings` seeds both
postings with the same body (the obvious thing to do, since `_seed_posting_version` varies only the
slug), then posting 1's successful `'{"requirements": []}'` is cached, posting 2 **hits the cache**,
`_DiesOnSecond.complete` is never called a second time, no death occurs, and the run prints
`extracted 2 of 2 attempted` and exits 0 — the assertion `"extracted 1 of 2 attempted"` fails.

The plan's fresh-`data_dir` requirement is necessary but **not sufficient**: `cli_env_with_postings`
must also seed **distinct `body_text` per posting**. Same applies to
`cli_env_with_many_postings`, though `_AlwaysFailingClient` never populates the cache so that test is
unaffected in practice.

### WRONG — defect (c): a profile row is mandatory

`eligibility_cmd.py:330-332` calls `get_profile(conn)` and `_no_profile()` (a `NoReturn`) when it is
`None`. The existing runnable test seeds it via `_invoke(cli_env, ["init"], CLI_INIT_INPUT)` (`:378`).
Both new fixtures must do the same, plus
`_write_llm_config(cfg_dir, eligibility_extraction=True)` — otherwise the command short-circuits at
`:293-298` with "LLM eligibility extraction is off".

*Also note:* `_write_llm_config` renders a non-`bool` value as `f'"{value}"'` (`:307`), i.e. a **quoted
TOML string**. Passing `max_calls_per_run=51` writes `max_calls_per_run = "51"`. Pydantic v2 lax mode
coerces it, but it is fragile — the tests as designed do not need to set it (default 50 is what
`test_cap_survives_unclassified_failures` asserts against).

*Minor:* `test_dead_credential_stops_after_one_call_and_exits_1`'s comment says "Seed strictly more
open postings than the cap" while its fixture docstring says "at least 2" and its assertion is
`extracted 0 of 1 attempted`. The comment is copy-pasted from the cap test; the assertion is correct
(the loop breaks after `attempted += 1`).

## 14 — `tailor/rewrite/lane.py` — WRONG (the plan misstates which values differ)

Lines 74-103 (propose boundary):

```python
 74	            try:
 75	                candidate = _guarded(propose, a_text, jd_skills)
 76	            except _BudgetExceeded:
 77	                rows.append(
 78	                    RewriteRow(
 79	                        bullet_id=b.bullet_id,
 80	                        entry_id=entry.entry_id,
 81	                        a_text=a_text,
 82	                        b_text=a_text,
 83	                        filter_pass=False,
 84	                        judge_verdict=None,
 85	                        kept=False,
 86	                        drop_reason="budget",
 87	                    )
 88	                )
 89	                continue
 90	            except Exception:  # containment boundary — provider failure drops rewrite, not the run
 91	                rows.append(
 92	                    RewriteRow(
 93	                        bullet_id=b.bullet_id,
 94	                        entry_id=entry.entry_id,
 95	                        a_text=a_text,
 96	                        b_text=a_text,
 97	                        filter_pass=False,
 98	                        judge_verdict=None,
 99	                        kept=False,
100	                        drop_reason="error",
101	                    )
102	                )
103	                continue
```

Lines 270-299 (judge boundary):

```python
270	            try:
271	                verdict = parse_verdict(_guarded(judge, a_text, candidate))
272	            except _BudgetExceeded:
…	
286	            except Exception:  # containment boundary — provider failure drops rewrite, not the run
287	                rows.append(
288	                    RewriteRow(
289	                        bullet_id=b.bullet_id,
290	                        entry_id=entry.entry_id,
291	                        a_text=a_text,
292	                        b_text=candidate,
293	                        filter_pass=True,
294	                        judge_verdict=None,
295	                        kept=False,
296	                        drop_reason="error",
297	                    )
298	                )
299	                continue
```

Both `except Exception:` boundaries are at **90** and **286** exactly as the plan says. Insertion
before each works: the preceding arm is `except _BudgetExceeded`, and `LLMLaneDeadError` is not a
subclass of it, so ordering is unaffected.

`RewriteRow` field list (`tailor/rewrite/result.py:17-25`) — `bullet_id: str`, `entry_id: str`,
`a_text: str`, `b_text: str`, `filter_pass: bool`, `judge_verdict: str | None`, `kept: bool`,
`drop_reason: str | None`. Frozen dataclass. The plan's snippet matches exactly.

Cache check at 357-366 — VERIFIED:

```python
357	    def call(payload: dict[str, str], version: str) -> str:
358	        key = cache.key(
359	            hashlib.sha256(payload["user"].encode()).hexdigest(), version, model_identity
360	        )
361	        cached = cache.get(key)
362	        if cached is not None:
363	            return cached
364	        raw = client.complete(payload["user"], system=payload["system"])
365	        cache.put(key, raw)
366	        return raw
```

The cache **is** consulted before the client, so Task 6's warm-cache test premise holds.

**WRONG:** the plan says *"The `bullet_id`/`entry_id`/`a_text` values differ per site — copy them from
the adjacent `except Exception` block at the same site."* Those three are **identical at both sites**
(`b.bullet_id`, `entry.entry_id`, `a_text`). What actually differs is:

- `b_text`: `a_text` at :96 vs **`candidate`** at :292
- `filter_pass`: `False` at :97 vs **`True`** at :293

The plan's single snippet hard-codes `b_text=a_text, filter_pass=False`, which is correct for the
propose site and **wrong for the judge site** — it would discard the candidate text and misreport
`filter_pass`, diverging from the sibling `"error"` row at the same boundary. Fix the instruction and
give the judge arm `b_text=candidate, filter_pass=True`.

## 15 — `cli/tailor_cmd.py` — VERIFIED

Lines 120-145:

```python
120	        # and migrates boardwatch.db — a gate failure against a pristine data dir must
…
124	        gate_settings = load_settings(data_dir=ctx.obj)
125	        if not gate_settings.llm.resume_tailoring:
…
131	        try:
132	            client = build_client(gate_settings)
133	        except ValueError as exc:
134	            console.print(str(exc))
135	            raise typer.Exit(code=1) from exc
136	        if client is None:
137	            console.print(
138	                "LLM tier is not enabled; set llm.enabled = true and BOARDWATCH_LLM_API_KEY"
139	            )
140	            raise typer.Exit(code=1)
141	
142	    app_ctx = build_context(ctx.obj)
143	    settings = app_ctx.settings
144	    if tier_b:
145	        cache = ResponseCache(settings.data_dir / "llm-cache")
```

**Is `client` in scope at line 235?** YES. It is a plain local of `run_cmd`, initialised
`client = None` at `:116` and reassigned at `:132`. It is never deleted or shadowed. VERIFIED.

Lines 225-250:

```python
225	            elif r["drop_reason"] == "unchanged":
226	                tag = "unchanged"
227	            else:
228	                tag = f"fallback:{r['drop_reason']}"
229	            console.print(f"  {tag:<16} [{r['entry_id']}] {r['bullet_id']}", markup=False)
230	        console.print(
231	            "Tier B is LLM-assisted: each reworded bullet passed a deterministic overmatch "
232	            "filter and a fail-closed entailment judge, but is NOT structurally proven — "
233	            "review the flagged variant before sending; the Tier A file above is the safe copy."
234	        )
235	        if any(r["drop_reason"] == "budget" for r in result.rewrites):
236	            console.print(
237	                "Tier B call budget exhausted before every bullet was reworded — raise "
238	                "llm.max_calls_per_run (Tier B spends 2 calls per bullet, shared with the "
239	                "eligibility LLM lane; a cache hit still spends budget, so re-running with "
240	                "no config change will not help)."
241	            )
242	        if not result.dry_run and result.llm_pdf_path is not None:
243	            console.print(f"tier B pdf: {result.llm_pdf_path}")
```

Lines 235-241 are the budget scan, quoted verbatim above. VERIFIED.

**Are `result.rewrites` entries dicts or objects?** **Dicts.** Every access is subscript:
`r["kept"]` (`:213,223`), `r["drop_reason"]` (`:217,225,228`), `r['entry_id']` / `r['bullet_id']`
(`:229`). The plan's `r["drop_reason"] == "lane_dead"` and `r["kept"]` are correct. (Note `lane.py`
returns `RewriteRow` **dataclasses**; the dict conversion happens further up in `reports/tailor.py`,
outside this plan's scope — but the CLI-level shape the plan targets is dicts, which is what matters.)

## 16 — `tests/unit/test_tailor_cmd_tier_b.py` — WRONG (3 defects in the new tests)

**Helpers and fixtures, quoted:**

```python
36	@dataclass(frozen=True)
37	class Env:
38	    data_dir: Path
39	    config_dir: Path
40	
41	
42	@pytest.fixture()
43	def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Env:
44	    cfg = tmp_path / "cfg"
45	    cfg.mkdir(parents=True, exist_ok=True)
46	    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(cfg))
47	    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
48	    monkeypatch.delenv("BOARDWATCH_LLM_API_KEY", raising=False)
49	    return Env(data_dir=tmp_path / "data", config_dir=cfg)
50	
51	
52	def _run(env: Env, args: list[str]):
53	    return runner.invoke(app, ["--data-dir", str(env.data_dir), *args])
54	
55	
56	def _seed_open_posting(env: Env, *, skills: tuple[str, ...] = ("Python", "JavaScript")) -> int:
57	    """Insert one company+job+posting+version+taxonomy extraction; return posting_id."""
…
96	    return posting_id
…
103	def _artifact_count(env: Env) -> int:
104	    engine = get_engine(env.data_dir)
105	    ensure_schema(engine)
106	    with engine.connect() as conn:
107	        return conn.execute(artifacts.select()).all().__len__()
```

**`_write_tier_b_config` — does it take `max_calls_per_run` as a keyword? YES:**

```python
264	def _write_tier_b_config(env: Env, *, max_calls_per_run: int | None = None) -> None:
265	    body = "[llm]\nresume_tailoring = true\nenabled = true\n"
266	    if max_calls_per_run is not None:
267	        body += f"max_calls_per_run = {max_calls_per_run}\n"
268	    _write_config(env, body)
```

Keyword-**only** (after `*`), `int | None`, rendered unquoted. The plan's
`_write_tier_b_config(env, max_calls_per_run=1)` is valid. VERIFIED — and it is already used that way
at `:303`.

**Line 206's scripted-client fixture** (it is a class, not a `@pytest.fixture`):

```python
205	class _FakeClient:
206	    """Scripted client for CLI-level tests: build_client is monkeypatched to return
207	    this instead of a real provider adapter, so no network is required."""
208	
209	    def __init__(self, bodies: list[str]) -> None:
210	        self.bodies = list(bodies)
211	
212	    def complete(self, prompt: str, *, system: str | None = None) -> str:
213	        return self.bodies.pop(0) if self.bodies else ""
```

### WRONG — defect (a): the CLI invocation is missing the `run` subcommand

`tailor` is a `typer.Typer` group (`tailor_cmd.py:41`); the command is registered as
`@tailor_app.command("run")` (`:97`). Every existing test invokes
`_run(env, ["tailor", "run", str(posting_id), "--tier-b", ...])`. The plan's three new tests all use
`_run(env, ["tailor", str(posting_id), "--tier-b"])`, which typer rejects as an unknown subcommand
(exit code 2). All three would fail before touching any lane code.

### WRONG — defect (b): the new tests never run `tailor init`

`_seed_open_posting` seeds the posting but **not the résumé**. Every existing Tier-B test that expects
a successful run calls `_run(env, ["tailor", "init"])` first (`:234, 287, 311, 337`). Without it
`run_tailor` raises `ResumeLoadError`, caught at `tailor_cmd.py:159-169` → exit 1 with a résumé
message, so `assert "lane_dead" in result.stdout` fails and
`test_healthy_run_keeping_zero_rewrites_still_exits_0`'s `exit_code == 0` fails.

### WRONG — defect (c): `_DiesOnNthCall`'s reply text cannot reach the judge boundary

The default `reply = "a rewritten bullet"` is not a provenanced reword of the scaffolded bullets
("Built a Python service handling 2M requests/day on Kubernetes" / "Cut p99 latency 40% by rewriting
the hot path in Rust"). It would be vetoed by `reword_is_provenanced` at `lane.py:165-184` with
`drop_reason="provenance"` — **before** `_guarded(judge, ...)` at `:271` is ever reached.

So the `die_on=2` ("judge-boundary") parameterisation actually spends call 2 on the **second bullet's
propose**, i.e. it exercises the propose boundary twice and never touches `lane.py:286`. Its three
assertions still pass, so the defect is silent — this is precisely the "a probe that cannot reach an
arm prints the same nothing as one that passes" failure mode.

Fix: use a reply modelled on the existing suite's provenance-passing rewords, e.g.
`"Built the Python service handling 2M requests/day on Kubernetes"` (`:280`, `:308`), so bullet 1's
propose succeeds through the filter/provenance/overmatch/register/echo gauntlet and call 2 lands on
the judge. Then assert the row's `b_text`/`filter_pass` to prove which boundary fired.

*Unverified:* `_artifact_count(env) > 0` after a successful Tier-B run. Existing tests only assert
`== 0` on gate failure. Plausible but not proven by any current test.

*Gate note (not a defect):* the new tests correctly do **not** need `BOARDWATCH_LLM_API_KEY` — with
`build_client` monkeypatched, `client is not None` and the gate at `:136-140` passes. This mirrors
`test_tier_b_dry_run_does_not_claim_nothing_written` (`:216-241`), which also omits the key.

## 17 — `docs/program/PROGRAM.md:335-355` — VERIFIED

```
335	   an evidence window to scaffold-only orphans that never settled. **DONE** (D-039) —
336	   `pipeline/runner.py::_cohort_guard`: the candidate set is `ranked.visible` (verified to already exclude
337	   `skipped_not_new`), reconciled against `summary.tailored` ∪ `summary.tailor_failed_ids` by **posting_id
338	   SET**, not by count — a compensating bug (one candidate lost, another double-counted) can balance a
339	   count identity but cannot hide inside a set difference.
340	10. **Tier-B quota and idempotence.** At 2 model calls per bullet, B1's ≥10 leads/day is ~300 calls/day
341	   unattended. Needs: meta-hash idempotence keyed on JD + template + model + prompt version +
342	   `profile_version` + `persona_version` so a re-run is not a full re-tailor; batched judging in the API
343	   lane (the agent lane already batches); and **split rate-limit classes** — a quota cap aborts the batch,
344	   a transient 429 retries with backoff. Untailored leads stay pending for a resumable re-run, and the
345	   run **never silently downgrades** to the deterministic engine to finish. **PARTIAL** (D-040) — the
346	   transient-429/5xx-retries-with-backoff half of the rate-limit-class split is **DONE**: both LLM
347	   adapters classify 429/5xx as `LLMTransientError` and retry through a shared `llm/retry.py` helper
348	   (tenacity, `Retry-After` honored, bounded at 4 attempts), placed below the rewrite lane's per-call
349	   budget metering so a retried call still costs one unit. Still open: the quota-abort half, resumable
350	   idempotence, and the never-silently-downgrade guarantee — P3 slice 5b, a Mit fork deliberately deferred.
351	
352	**Gate P3:** **7** consecutive unattended runs with **0** silent empty days, **0** runs reporting success
353	while producing nothing, **0** stale-day feeds, and the two-writer test green. (Seven, not fourteen — the
354	14-day clock is acceptance and runs after P6.)
355	
```

Both premises the plan claims to retract are present and quoted correctly: the "~300 calls/day"
sentence at `:340-341` and "resumable idempotence" listed as still open at `:349-350`.

*Minor:* Task 7's header says `PROGRAM.md:340-351`; item 10 actually ends at **350** (351 is blank).
The status paragraph to replace begins at `**PARTIAL** (D-040)` mid-line 345.

## 18 — `src/boardwatch/core/settings.py:43-44` — VERIFIED

```
43	    Includes extraction knobs (eligibility_extraction, base_url) and call budgets
44	    (max_calls_per_run) for LLM-assisted eligibility assessment.
```

This is the `LLMTier` **class docstring**, not a `Field(description=...)`. The field itself is
`max_calls_per_run: int = Field(default=50, ge=1)` (`:56`) with no description argument. Amend the
docstring; there is nothing else to amend.

The plan's Task 7 characterisation ("it is not a per-run total") is correct on the facts:
`eligibility_cmd.py:363` bounds one invocation of `eligibility extract`, and
`lane.py:65` (`budget`, sourced from the same setting) bounds one **résumé** in the tailor lane.

## 19 — `docs/program/DECISIONS.md` format — VERIFIED

**Highest existing D-number: D-145.** (Live file holds D-077 onward; D-001…D-076 are in the closed
`DECISIONS-ARCHIVE.md`.) So D-146 is correct and unclaimed.

Decision heading format (`DECISIONS.md:4290`), with the dated sub-line the recent entries use:

```markdown
## D-145 — The Gate A subsystem never ran on Windows, and one `write_text` hid it

*2026-08-12. Surfaced by pushing the Gate A range, which is the first time CI executed it on the
Windows matrix. Fixes: `32a109f` (collection), `dbb57ef` (the rest).*

### Context
```

Note the em-dash `—` after the number, and the `### Context` sub-heading. The file header (`:7`)
states the required shape: **context** · **choice** · **alternatives rejected** · **consequence**.

Index row format — 4 columns, separator at `:36`, rows from `:113`:

```
| D-145 | DECISIONS.md | 4290 | The Gate A subsystem never ran on Windows, and one `write_text` hid it |
```

i.e. `| D-NNN | DECISIONS.md | <heading line number> | <title verbatim> |`, appended after `:181`.
`make reindex` recomputes the line-number column; `make check` fails on a stale index (D-109).

## 20 — `CHANGELOG.md` top 25 lines — VERIFIED

```
 1	# Changelog
 2	
 3	All notable changes to this project are documented here. The format follows
 4	[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
 5	[Semantic Versioning](https://semver.org/spec/v2.0.0.html).
 6	
 7	## [Unreleased]
 8	
 9	### Added
10	
11	- **The canonical career-profile bundle — `boardwatch profile-bundle`.** A private, revisioned,
12	  filesystem-only store for the career facts a résumé is assembled from. It lives at
13	  `{config_dir}/career-profile`, with `--bundle PATH` overriding that; it is machine-local, is not a
14	  `Settings` field, and does not participate in lead selection.
15	
16	  Twelve commands are now reachable from a terminal — `init`, `checkout`, `rebase-draft`, `validate`,
17	  `inspect`, `inventory`, `conflicts`, `migrate`, `add-evidence`, `resolve-conflict`, `approve`,
18	  `promote` — each with a `--json` machine report alongside the human rendering, and each returning
19	  the same four exit tiers (0 clean, 1 clean findings, 2 usage error, 3 could not complete).
20	
21	  The shape of the thing: you author YAML records into a **draft**; `validate` runs the structural,
22	  referential, evidence, semantic, history, imports and digest layers over it — plus four more under
23	  `--completeness` — and reports what every layer found rather than the first failure; `approve`
24	  records the owner's decision against the draft's exact content, on a controlling terminal;
25	  `promote` turns it into an immutable, content-addressed
```

Yes, there is an `## [Unreleased]` section with `### Added` already open. A CLI **contract** change
(new non-zero exit) belongs under a `### Changed` sub-heading added beneath the existing `### Added`
block, per Keep a Changelog.

## 21 — Test dependencies and ordering plugins — VERIFIED

`pyproject.toml:57-67`:

```toml
[dependency-groups]
dev = [
    "pytest>=8.2",
    "pytest-cov>=5.0",
    "respx>=0.21",
    "mypy>=1.10",
    "ruff>=0.4",
    "pre-commit>=3.7",
    "types-PyYAML",
]
```

`respx>=0.21` is a declared dev dependency. **No** `pytest-randomly`, `pytest-order`, `pytest-xdist`
or any other ordering/parallelism plugin — the only pytest distributions installed in the venv are
`pytest` and `pytest-cov`. Test order is pure file/definition order.

Consequence for the plan: appending an `@pytest.fixture(autouse=True)` **mid-file** in Task 2 is safe.
Pytest collects fixtures at module scope regardless of textual position, so `_no_real_sleeps` will
apply to Task 1's tests too (harmless — they never sleep) and to everything after it.

### ADDITIONAL DEFECT (cross-cutting, not a numbered item): the coverage gate breaks every narrow run

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
addopts = "-m 'not perf' --cov=boardwatch --cov-fail-under=85"
```

`--cov-fail-under=85` is in `addopts`, so it applies to **every** invocation. The plan's Step 2/Step 4
commands — `uv run pytest tests/unit/test_llm_lane_death.py -v`,
`uv run pytest tests/pipeline/test_llm_lane.py -k "..." -v`, etc. — will report the tests as passing
and then **exit 1** with `FAIL Required test coverage of 85% not reached`. Every "Expected: PASS" in
Tasks 1-6 is wrong as written if the implementer reads the exit code.

Implementers must add `--no-cov` (or `-p no:cacheprovider --cov-fail-under=0`) to the narrow runs, and
read the pytest summary line rather than the exit code. This does not affect `make check`, which runs
the whole suite.

## 22 — Pre-existing `drop_reason == "error"` assertions — VERIFIED (no conflict)

```python
145	def test_provider_error_drops(tmp_path):
146	    res = run_tier_b(
147	        _resume(), RaisingClient(), ResponseCache(tmp_path / "c"),
148	        jd_skills=set(), taxonomy=load_taxonomy(tmp_path), table=_TABLE, model="m", budget=50,
149	    )
150	    assert res.accepted == []
151	    assert res.rows[0].drop_reason == "error"
```

`tests/unit/test_rewrite_lane.py:145-151`. `RaisingClient` raises a generic exception, **not** an
`LLMLaneDeadError`, so Task 6's new `except LLMLaneDeadError:` arm does not intercept it and this test
stays green. The only other occurrence is a hand-built fixture dict at
`tests/unit/test_run_funnel.py:975` (`{"kept": False, "drop_reason": "error"}`), which is input data,
not a behavioural assertion. Neither blocks Task 6.

## 23 — Does `lane_dead` reach stdout? — VERIFIED, the plan's assertion holds

The coordinator's concern is **unfounded**. `tailor_cmd.py` prints a **per-row line** for every rewrite
row, and it interpolates `drop_reason` directly:

```python
212	    if result.rewrites is not None:
213	        reworded = sum(1 for r in result.rewrites if r["kept"])
…
217	        unchanged = sum(1 for r in result.rewrites if r["drop_reason"] == "unchanged")
218	        fell_back = len(result.rewrites) - reworded - unchanged
219	        console.print(
220	            f"Tier B (LLM): reworded {reworded} · unchanged {unchanged} · fell back {fell_back}"
221	        )
222	        for r in result.rewrites:
223	            if r["kept"]:
224	                tag = "reworded"
225	            elif r["drop_reason"] == "unchanged":
226	                tag = "unchanged"
227	            else:
228	                tag = f"fallback:{r['drop_reason']}"
229	            console.print(f"  {tag:<16} [{r['entry_id']}] {r['bullet_id']}", markup=False)
```

A row with `drop_reason="lane_dead"` takes the `else` branch at `:227-228`, producing
`tag = "fallback:lane_dead"`, printed at `:229`. So the literal token **`lane_dead` does appear in
stdout** and `assert "lane_dead" in result.stdout` passes — via the existing per-row printer, not via
the plan's new message.

Two details that make this safe rather than lucky:

- `{tag:<16}` **pads**, it never truncates. `"fallback:lane_dead"` is 18 characters, so it prints
  intact.
- `markup=False` is set, so Rich does not eat the `[entry_id]` bracket as markup.

So the printing surface is: a **summary count line** (`:219-221`), then **one line per row**
(`:222-229`), then the disclaimer (`:230-234`), then the conditional budget hint (`:235-241`), then the
Tier-B PDF path (`:242-243`). There is no table.

One consequence worth acting on: because `lane_dead` already surfaces through the generic
`fallback:` printer, `assert "lane_dead" in result.stdout` is **not** a test of the plan's new message
block — it would pass even if the entire `if any(r["drop_reason"] == "lane_dead" ...)` block at Task 6
Step 3 were deleted. The load-bearing assertions are `"credential_invalid" in result.stdout` (only the
new block prints the reason) and `result.exit_code == 1`.

## 24 — Rich wrapping — VERIFIED (low risk, but assert defensively)

Both consoles are bare `Console()` with no width pinned:

- `src/boardwatch/cli/tailor_cmd.py:39` — `console = Console()`
- `src/boardwatch/cli/eligibility_cmd.py:63` — `console = Console()`

No conftest sets `COLUMNS`, `RICH_*`, or a console width — the only width control in the whole test
tree is per-test and lives elsewhere: `tests/unit/test_eligibility_cmd.py:252` (`COLUMNS=160`), `:272`
(`COLUMNS=80`), `:309` (`COLUMNS=200`), plus `tests/unit/test_preflight.py:33`
(`Console(file=buf, width=200)`). Under `CliRunner` stdout is not a tty, so Rich falls back to width
80 and **does** wrap the plan's long messages.

**The plan's specific assertions survive**, because Rich wraps at word boundaries and never splits a
word shorter than the line width: `(credit_exhausted).` is 19 characters and `(credential_invalid).`
is 21 — both move to the next line whole rather than being hyphenated or split. So
`"credit_exhausted" in result.stdout` and `"credential_invalid" in result.stdout` hold.
`extracted 0 of 1 attempted` is ~26 characters and cannot wrap at all.

Still worth doing, since it costs nothing and the file already establishes the idiom: existing Tier-B
tests flatten before asserting on any long line —
`flat = result.stdout.replace("\n", "")` (`test_tailor_cmd_tier_b.py:292, 316, 342`). The plan's new
tailor tests assert on raw `result.stdout`. Have them flatten too, so a later wording change that
pushes a token across a wrap boundary does not produce a mystery failure.

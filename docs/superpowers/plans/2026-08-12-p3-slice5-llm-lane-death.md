# P3 Slice 5 — LLM lane-death Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When an LLM credential is dead (out of credit, revoked, or lacking model access), stop calling the provider, say why, and exit non-zero only when nothing landed — instead of burning up to 50 doomed calls and reporting success.

**Architecture:** One typed exception (`LLMLaneDeadError`) classified at the adapter raise site from the provider's error body; a `RunScopedClient` wrapper installed in `build_client` that latches on the first lane death so every later call fails without touching the network; and two consumers (`eligibility extract`, `tailor --tier-b`) that stop, report attempted-vs-landed, and exit 1 only under *death observed ∧ zero landed*.

**Tech Stack:** Python ≥3.11, httpx, respx (test HTTP stubbing), pytest, typer, SQLAlchemy, ruff + mypy.

**Spec:** `docs/superpowers/specs/2026-08-12-p3-slice5-llm-economics-design.md` — read §5 (components), §7 (tests) and §10 (review record) before starting.

## Global Constraints

- **`make check` is the only gate.** pytest + ruff + mypy passing individually is not green. Run it in plain mode, capture the real exit code, never pipe through `head`/`tail` (SIGPIPE gives a false negative).
- **A diff touching only `*.md` owes `make generalization index-check` instead** (D-116). Anything touching `src/` or `tests/` owes the full gate.
- **Typed violations at the raise site.** Never classify behaviour by string-matching a message.
- **Closed, versioned catalogs.** An out-of-catalog value is a failure, never a new bucket.
- **`StrEnum` is the repo idiom** for closed string catalogs (`profile_bundle/layout.py:38`).
- **No AI attribution** in commits, branches, or messages. No `Co-Authored-By`, no "Generated with".
- **Commit messages:** imperative mood, one logical change per commit.
- **Never `git add -A` or `git add -u`.** Stage explicit paths only.
- **`docs/superpowers/` is never staged** — it is untracked working material by the owner's standing rule.
- **Test HTTP with respx** (`@respx.mock` + `respx.post(url).mock(...)`), asserting on `route.call_count`. Match `tests/unit/test_llm_adapters.py`.
- **Retry tests must not sleep** — copy the `_no_real_sleeps` autouse fixture from `tests/unit/test_llm_adapters.py:12-16`.

---

## File Structure

| File | Responsibility | Task |
|---|---|---|
| `src/boardwatch/llm/client.py` | Modify — add `LaneDeathReason`, `LLMLaneDeadError`, and the pure body classifier | 1 |
| `src/boardwatch/llm/retry.py` | Modify — add `safe_json` (httpx-coupled, so it does not belong in `client.py`) | 1 |
| `src/boardwatch/llm/anthropic.py` | Modify — classify Anthropic's `error.type` before the retryable branch | 2 |
| `src/boardwatch/llm/openai_compat.py` | Modify — classify the narrow openai-compat signal set | 3 |
| `src/boardwatch/llm/run_client.py` | **Create** — `RunScopedClient`, the latching wrapper | 4 |
| `src/boardwatch/llm/factory.py` | Modify — wrap both adapter branches | 4 |
| `src/boardwatch/eligibility/extract_llm.py` | Modify — re-raise lane death ahead of the blanket `except` | 5 |
| `src/boardwatch/cli/eligibility_cmd.py` | Modify — two counters, break on death, conditional exit 1 | 5 |
| `src/boardwatch/tailor/rewrite/lane.py` | Modify — `lane_dead` rows at both containment boundaries | 6 |
| `src/boardwatch/cli/tailor_cmd.py` | Modify — report the reason, conditional exit 1 | 6 |
| `tests/unit/test_llm_lane_death.py` | **Create** — classifier + adapter + wrapper + factory tests | 1–4 |
| `tests/pipeline/test_llm_lane.py` | Modify — eligibility consumer tests | 5 |
| `tests/unit/test_tailor_cmd_tier_b.py` | Modify — tailor consumer tests | 6 |
| `docs/program/DECISIONS.md`, `PROGRAM.md`, `STATE.md`, `CHANGELOG.md` | Modify — D-146, retract the false premise, changelog | 7 |

---

### Task 1: The vocabulary and a classifier that cannot raise

**Files:**
- Modify: `src/boardwatch/llm/client.py`
- Modify: `src/boardwatch/llm/retry.py`
- Test: `tests/unit/test_llm_lane_death.py` (create)

**Interfaces:**
- Consumes: nothing (first task).
- Produces:
  - `LaneDeathReason(StrEnum)` with members `CREDIT_EXHAUSTED`, `CREDENTIAL_INVALID`, `MODEL_FORBIDDEN`.
  - `LLMLaneDeadError(LLMError)` with `__init__(self, message: str, *, reason: LaneDeathReason)` and attribute `.reason: LaneDeathReason`.
  - `lane_death_reason(body: object, *, table: Mapping[str, LaneDeathReason]) -> LaneDeathReason | None` in `llm/client.py`.
  - `safe_json(response: httpx.Response) -> object` in `llm/retry.py`.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_llm_lane_death.py`:

```python
"""Lane-death classification, latching, and factory wiring (P3 slice 5, D-146)."""

import httpx
import pytest

from boardwatch.llm.client import (
    LaneDeathReason,
    LLMError,
    LLMLaneDeadError,
    lane_death_reason,
)
from boardwatch.llm.retry import safe_json

_TABLE = {
    "billing_error": LaneDeathReason.CREDIT_EXHAUSTED,
    "authentication_error": LaneDeathReason.CREDENTIAL_INVALID,
}


def test_lane_dead_error_carries_a_typed_reason():
    exc = LLMLaneDeadError("HTTP 403", reason=LaneDeathReason.CREDIT_EXHAUSTED)
    assert exc.reason is LaneDeathReason.CREDIT_EXHAUSTED
    # It must remain catchable as the existing base class, so every current
    # `except LLMError` site keeps working unchanged.
    assert isinstance(exc, LLMError)


def test_classifier_maps_a_catalogued_type():
    body = {"error": {"type": "billing_error", "message": "credit balance too low"}}
    assert lane_death_reason(body, table=_TABLE) is LaneDeathReason.CREDIT_EXHAUSTED


def test_classifier_reads_the_code_field_too():
    # OpenAI-compatible providers put the token in `code`, not `type`.
    body = {"error": {"code": "authentication_error"}}
    assert lane_death_reason(body, table=_TABLE) is LaneDeathReason.CREDENTIAL_INVALID


@pytest.mark.parametrize(
    "body",
    [
        None,                                  # unparseable body
        [],                                     # non-object root
        "forbidden",                            # string root
        {},                                     # empty object
        {"error": "forbidden"},                 # error is a string, not an object
        {"error": {}},                          # no type/code at all
        {"error": {"type": 7}},                 # non-string type
        {"error": {"type": "unknown_error"}},   # out of catalog
        {"error": {"code": None}},              # null code
    ],
)
def test_classifier_never_raises_and_returns_none_for_unclassifiable(body):
    # A classifier that raises would land in extract_llm.py's blanket `except`
    # and reproduce the exact silent success this slice removes.
    assert lane_death_reason(body, table=_TABLE) is None


def test_safe_json_returns_none_instead_of_raising():
    assert safe_json(httpx.Response(403, text="not json")) is None
    assert safe_json(httpx.Response(403, json={"error": {"type": "x"}})) == {
        "error": {"type": "x"}
    }
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_llm_lane_death.py -v`
Expected: FAIL — `ImportError: cannot import name 'LaneDeathReason'`.

- [ ] **Step 3: Add the vocabulary and classifier**

In `src/boardwatch/llm/client.py`, change the imports at the top to:

```python
from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Protocol, runtime_checkable
```

Then add, immediately after the existing `LLMTransientError` class:

```python
class LaneDeathReason(StrEnum):
    """Why the LLM lane is dead for the rest of this invocation.

    A closed catalog (CLAUDE.md): a provider signal outside it is an ordinary
    `LLMError`, never a new member. All three mean the same operationally --
    every remaining call will fail identically -- and differ only in cause,
    which is why they share one exception type rather than three (D-146).
    """

    CREDIT_EXHAUSTED = "credit_exhausted"
    CREDENTIAL_INVALID = "credential_invalid"
    MODEL_FORBIDDEN = "model_forbidden"


class LLMLaneDeadError(LLMError):
    """The credential cannot serve any further call in this invocation.

    Distinct from `LLMTransientError` (retry helps) and from a bare `LLMError`
    (this one call failed; the next may succeed). Raised at the adapter, from
    the provider's error body -- never by string-matching a message downstream.
    """

    def __init__(self, message: str, *, reason: LaneDeathReason) -> None:
        super().__init__(message)
        self.reason = reason


def lane_death_reason(
    body: object, *, table: Mapping[str, LaneDeathReason]
) -> LaneDeathReason | None:
    """Classify a provider error body, or None when it is not a lane death.

    Deliberately total: every malformed shape returns None rather than raising.
    A `TypeError` escaping here would be caught by `extract_llm.py`'s blanket
    `except` and reported as a successful skip -- the precise defect this slice
    exists to remove -- so the shape checks are load-bearing, not defensive
    padding. `type` is checked before `code`; providers use one or the other.
    """
    if not isinstance(body, dict):
        return None
    error = body.get("error")
    if not isinstance(error, dict):
        return None
    for field in ("type", "code"):
        value = error.get(field)
        if isinstance(value, str) and value in table:
            return table[value]
    return None
```

In `src/boardwatch/llm/retry.py`, add after the existing `parse_retry_after` function:

```python
def safe_json(response: httpx.Response) -> object:
    """Parse a response body as JSON, or None when it is not JSON.

    Lives here rather than in `client.py` because it is httpx-coupled and
    `client.py` is the provider-neutral protocol module.
    """
    try:
        return response.json()
    except ValueError:
        return None
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_llm_lane_death.py -v`
Expected: PASS (13 tests).

- [ ] **Step 5: Commit**

```bash
git add src/boardwatch/llm/client.py src/boardwatch/llm/retry.py tests/unit/test_llm_lane_death.py
git commit -m "Add a typed lane-death vocabulary and a total error-body classifier"
```

---

### Task 2: Anthropic classification

**Files:**
- Modify: `src/boardwatch/llm/anthropic.py:86-96`
- Test: `tests/unit/test_llm_lane_death.py`

**Interfaces:**
- Consumes: `LaneDeathReason`, `LLMLaneDeadError`, `lane_death_reason` (Task 1); `safe_json` (Task 1).
- Produces: `AnthropicClient.complete` raising `LLMLaneDeadError` for the three catalogued `error.type` values.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_llm_lane_death.py` (add `import time`, `import respx`, and `from boardwatch.llm.anthropic import AnthropicClient`, `from boardwatch.llm.retry import DEFAULT_ATTEMPTS` to the imports):

```python
@pytest.fixture(autouse=True)
def _no_real_sleeps(monkeypatch: pytest.MonkeyPatch) -> None:
    # Retry backoff must never cost real wall-clock time in tests (D-040).
    monkeypatch.setattr(time, "sleep", lambda _seconds: None)


_ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"

# Hand-written from Anthropic's documented error bodies -- NOT generated from
# the mapping under test, which would agree with itself (spec §7.1 test 1).
_ANTHROPIC_CASES = [
    (403, "billing_error", LaneDeathReason.CREDIT_EXHAUSTED),
    (401, "authentication_error", LaneDeathReason.CREDENTIAL_INVALID),
    (403, "permission_error", LaneDeathReason.MODEL_FORBIDDEN),
]


@pytest.mark.parametrize(("status", "error_type", "expected"), _ANTHROPIC_CASES)
@respx.mock
def test_anthropic_classifies_lane_death(status, error_type, expected):
    route = respx.post(_ANTHROPIC_URL).mock(
        return_value=httpx.Response(status, json={"error": {"type": error_type}})
    )
    with pytest.raises(LLMLaneDeadError) as caught:
        AnthropicClient("m", "k").complete("hi")
    assert caught.value.reason is expected
    # Terminal, so it must not be retried.
    assert route.call_count == 1


def test_anthropic_cases_cover_every_reason():
    # Read the catalog at RUN TIME. A hard-coded list would let the mapping
    # silently cover a subset and still pass (D-142: a 4-class list passed
    # 98/98 while covering 5 of 13).
    assert {expected for _, _, expected in _ANTHROPIC_CASES} == set(LaneDeathReason)


@respx.mock
def test_anthropic_unknown_error_type_is_not_lane_death():
    respx.post(_ANTHROPIC_URL).mock(
        return_value=httpx.Response(400, json={"error": {"type": "invalid_request_error"}})
    )
    with pytest.raises(LLMError) as caught:
        AnthropicClient("m", "k").complete("hi")
    assert not isinstance(caught.value, LLMLaneDeadError)


@respx.mock
def test_anthropic_429_without_a_death_token_still_retries():
    route = respx.post(_ANTHROPIC_URL).mock(return_value=httpx.Response(429))
    with pytest.raises(LLMError):
        AnthropicClient("m", "k").complete("hi")
    assert route.call_count == DEFAULT_ATTEMPTS
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_llm_lane_death.py -k anthropic -v`
Expected: FAIL — `LLMError` raised where `LLMLaneDeadError` expected.

- [ ] **Step 3: Add the mapping**

In `src/boardwatch/llm/anthropic.py`, add to the imports:

```python
from boardwatch.llm.client import (
    LaneDeathReason,
    LLMError,
    LLMLaneDeadError,
    LLMTransientError,
    lane_death_reason,
)
from boardwatch.llm.retry import parse_retry_after, request_with_retry, safe_json
```

Add below `_RETRYABLE_STATUSES`:

```python
# Anthropic's documented error types that mean the credential cannot serve any
# further call. Closed catalog: anything else is an ordinary LLMError. Status
# alone is insufficient -- 403 carries BOTH `billing_error` and
# `permission_error`, which mean different things.
_LANE_DEATH_TYPES = {
    "billing_error": LaneDeathReason.CREDIT_EXHAUSTED,
    "authentication_error": LaneDeathReason.CREDENTIAL_INVALID,
    "permission_error": LaneDeathReason.MODEL_FORBIDDEN,
}
```

Replace the error-handling block at lines 89-96 with:

```python
            # Lane death is checked FIRST: it is terminal, so it must not be
            # retried even when it arrives on an otherwise-retryable status.
            if response.status_code < 200 or response.status_code >= 300:
                reason = lane_death_reason(safe_json(response), table=_LANE_DEATH_TYPES)
                if reason is not None:
                    raise LLMLaneDeadError(
                        f"HTTP {response.status_code}: {response.text}", reason=reason
                    )
                if response.status_code in _RETRYABLE_STATUSES:
                    raise LLMTransientError(
                        f"HTTP {response.status_code}: {response.text}",
                        retry_after=parse_retry_after(response),
                    )
                raise LLMError(f"HTTP {response.status_code}: {response.text}")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_llm_lane_death.py tests/unit/test_llm_adapters.py -v`
Expected: PASS. The existing adapter suite must stay green — it asserts the transient path.

- [ ] **Step 5: Commit**

```bash
git add src/boardwatch/llm/anthropic.py tests/unit/test_llm_lane_death.py
git commit -m "Classify Anthropic lane-death from the error body, not the status"
```

---

### Task 3: openai-compat classification

**Files:**
- Modify: `src/boardwatch/llm/openai_compat.py:87-93`
- Test: `tests/unit/test_llm_lane_death.py`

**Interfaces:**
- Consumes: Task 1's exports.
- Produces: `OpenAICompatClient.complete` raising `LLMLaneDeadError` for HTTP 401, HTTP 402, and any status carrying an `insufficient_quota` token.

**Design note — read before implementing.** This adapter is not one provider: `settings.provider` is a free-form `str | None` and `base_url` is arbitrary (`core/settings.py:49-52`), so it reaches OpenAI, DeepSeek, Ollama and any self-hosted proxy. Its catalog is therefore **narrower** than Anthropic's, and **bare HTTP 403 is deliberately NOT mapped** — on an arbitrary proxy a 403 does not prove the credential is dead. Do not add it.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_llm_lane_death.py` (add `from boardwatch.llm.openai_compat import OpenAICompatClient`):

```python
_OPENAI_URL = "https://api.example.com/v1/chat/completions"


def _openai() -> OpenAICompatClient:
    return OpenAICompatClient("https://api.example.com/v1", "m", "k")


@respx.mock
def test_openai_compat_401_is_credential_death():
    route = respx.post(_OPENAI_URL).mock(return_value=httpx.Response(401))
    with pytest.raises(LLMLaneDeadError) as caught:
        _openai().complete("hi")
    assert caught.value.reason is LaneDeathReason.CREDENTIAL_INVALID
    assert route.call_count == 1


@respx.mock
def test_openai_compat_402_is_credit_exhausted():
    # DeepSeek signals an exhausted balance as HTTP 402.
    respx.post(_OPENAI_URL).mock(return_value=httpx.Response(402))
    with pytest.raises(LLMLaneDeadError) as caught:
        _openai().complete("hi")
    assert caught.value.reason is LaneDeathReason.CREDIT_EXHAUSTED


@respx.mock
def test_openai_compat_429_with_insufficient_quota_is_terminal_not_retried():
    # OpenAI signals an exhausted balance as 429 + code `insufficient_quota`.
    # Left to the status check alone this is retried 4x per posting and then
    # swallowed -- the silent-success defect at 4x the call volume.
    route = respx.post(_OPENAI_URL).mock(
        return_value=httpx.Response(429, json={"error": {"code": "insufficient_quota"}})
    )
    with pytest.raises(LLMLaneDeadError) as caught:
        _openai().complete("hi")
    assert caught.value.reason is LaneDeathReason.CREDIT_EXHAUSTED
    assert route.call_count == 1


@respx.mock
def test_openai_compat_429_without_the_token_still_retries():
    # The narrowing must remove exactly one terminal case from the retryable
    # set -- ordinary rate limiting keeps D-040's backoff.
    route = respx.post(_OPENAI_URL).mock(return_value=httpx.Response(429))
    with pytest.raises(LLMError) as caught:
        _openai().complete("hi")
    assert not isinstance(caught.value, LLMLaneDeadError)
    assert route.call_count == DEFAULT_ATTEMPTS


@respx.mock
def test_openai_compat_bare_403_is_not_lane_death():
    # Deliberate: on an arbitrary proxy a 403 does not prove credential death,
    # and mis-latching would suppress a lane that is merely misrouted.
    respx.post(_OPENAI_URL).mock(return_value=httpx.Response(403))
    with pytest.raises(LLMError) as caught:
        _openai().complete("hi")
    assert not isinstance(caught.value, LLMLaneDeadError)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_llm_lane_death.py -k openai -v`
Expected: FAIL — plain `LLMError`/`LLMTransientError` raised where `LLMLaneDeadError` expected.

- [ ] **Step 3: Add the mapping**

In `src/boardwatch/llm/openai_compat.py`, update the imports exactly as in Task 2, then add below `_RETRYABLE_STATUSES`:

```python
# This adapter reaches ANY openai-compatible endpoint (settings.provider is a
# free-form string and base_url is arbitrary), so its catalog admits only
# unambiguous signals. Bare 403 is deliberately absent: on an arbitrary proxy
# it does not prove the credential is dead.
_LANE_DEATH_CODES = {"insufficient_quota": LaneDeathReason.CREDIT_EXHAUSTED}
_LANE_DEATH_STATUSES = {
    401: LaneDeathReason.CREDENTIAL_INVALID,
    402: LaneDeathReason.CREDIT_EXHAUSTED,
}
```

Replace the error-handling block at lines 87-93 with:

```python
            if response.status_code < 200 or response.status_code >= 300:
                # Body first: OpenAI sends `insufficient_quota` on 429, which is
                # terminal and must not be retried. A 429 WITHOUT it stays
                # transient, so D-040's backoff is narrowed by exactly one case.
                reason = lane_death_reason(safe_json(response), table=_LANE_DEATH_CODES)
                if reason is None:
                    reason = _LANE_DEATH_STATUSES.get(response.status_code)
                if reason is not None:
                    raise LLMLaneDeadError(
                        f"HTTP {response.status_code}: {response.text}", reason=reason
                    )
                if response.status_code in _RETRYABLE_STATUSES:
                    raise LLMTransientError(
                        f"HTTP {response.status_code}: {response.text}",
                        retry_after=parse_retry_after(response),
                    )
                raise LLMError(f"HTTP {response.status_code}: {response.text}")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_llm_lane_death.py tests/unit/test_llm_adapters.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/boardwatch/llm/openai_compat.py tests/unit/test_llm_lane_death.py
git commit -m "Classify openai-compatible lane-death from unambiguous signals only"
```

---

### Task 4: The latching wrapper, installed by the factory

**Files:**
- Create: `src/boardwatch/llm/run_client.py`
- Modify: `src/boardwatch/llm/factory.py:40,46`
- Test: `tests/unit/test_llm_lane_death.py`

**Interfaces:**
- Consumes: Task 1's exports; `ModelClient` from `llm/client.py`.
- Produces: `RunScopedClient(inner: ModelClient)` with `.complete(prompt, *, system=None) -> str`, read-only property `.dead_reason -> LaneDeathReason | None`, and attribute `.calls_attempted: int`. `build_client` returns `RunScopedClient | None`.

**Read before implementing (spec §7.0).** The established CLI fixture pattern monkeypatches `build_client` itself — `tests/pipeline/test_llm_lane.py:350,365,384` and `tests/unit/test_tailor_cmd_tier_b.py:206`. Any test written in that idiom bypasses the wrapper entirely, so `test_build_client_wraps_*` below **must not monkeypatch `build_client`**. It is the only test that proves the wiring exists.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_llm_lane_death.py` (add `from pathlib import Path`, `from boardwatch.core.secrets import LLM_API_KEY_ENV`, `from boardwatch.core.settings import LLMTier, Settings`, `from boardwatch.llm.factory import build_client`, `from boardwatch.llm.run_client import RunScopedClient`):

```python
class _CountingClient:
    """Records how many calls reached the underlying adapter."""

    def __init__(self, exc: Exception | None = None) -> None:
        self.calls = 0
        self._exc = exc

    def complete(self, prompt: str, *, system: str | None = None) -> str:
        self.calls += 1
        if self._exc is not None:
            raise self._exc
        return "ok"


def test_wrapper_delegates_while_healthy():
    inner = _CountingClient()
    client = RunScopedClient(inner)
    assert client.complete("hi") == "ok"
    assert inner.calls == 1
    assert client.dead_reason is None


def test_wrapper_latches_and_stops_touching_the_network():
    inner = _CountingClient(
        LLMLaneDeadError("dead", reason=LaneDeathReason.CREDIT_EXHAUSTED)
    )
    client = RunScopedClient(inner)
    for _ in range(5):
        with pytest.raises(LLMLaneDeadError) as caught:
            client.complete("hi")
        assert caught.value.reason is LaneDeathReason.CREDIT_EXHAUSTED
    # Asserted on the INNER counter, never the wrapper's self-report: a
    # component's self-report is not verification (CLAUDE.md).
    assert inner.calls == 1
    assert client.dead_reason is LaneDeathReason.CREDIT_EXHAUSTED
    assert client.calls_attempted == 1


def test_wrapper_does_not_latch_on_ordinary_failures():
    inner = _CountingClient(LLMError("boom"))
    client = RunScopedClient(inner)
    for _ in range(3):
        with pytest.raises(LLMError):
            client.complete("hi")
    assert inner.calls == 3
    assert client.dead_reason is None


def _settings(tmp_path: Path, **llm) -> Settings:
    return Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "cfg",
        llm=LLMTier(enabled=True, model="m", **llm),
    )


@pytest.mark.parametrize(
    ("provider", "base_url", "url"),
    [
        ("anthropic", None, _ANTHROPIC_URL),
        ("openai", "https://api.example.com/v1", _OPENAI_URL),
    ],
)
@respx.mock
def test_build_client_wraps_every_adapter_branch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, provider, base_url, url
):
    # Routed through the REAL build_client with the HTTP layer stubbed. Do NOT
    # monkeypatch build_client here: doing so is what lets the whole wrapper be
    # reverted with every other test still green (spec §7.0).
    monkeypatch.setenv(LLM_API_KEY_ENV, "a-real-key")
    route = respx.post(url).mock(
        return_value=httpx.Response(401, json={"error": {"type": "authentication_error"}})
    )
    kwargs = {"provider": provider}
    if base_url is not None:
        kwargs["base_url"] = base_url
    client = build_client(_settings(tmp_path, **kwargs))
    assert client is not None

    for _ in range(2):
        with pytest.raises(LLMLaneDeadError):
            client.complete("hi")
    # One network call for two completes -- the latch is installed in production.
    assert route.call_count == 1


def test_build_client_still_returns_none_when_disabled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    monkeypatch.setenv(LLM_API_KEY_ENV, "a-real-key")
    settings = Settings(
        data_dir=tmp_path / "data", config_dir=tmp_path / "cfg", llm=LLMTier(enabled=False)
    )
    assert build_client(settings) is None


def test_build_client_still_returns_none_without_a_key(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    monkeypatch.delenv(LLM_API_KEY_ENV, raising=False)
    assert build_client(_settings(tmp_path, provider="anthropic")) is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_llm_lane_death.py -k "wrapper or build_client" -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'boardwatch.llm.run_client'`.

- [ ] **Step 3: Write the wrapper and install it**

Create `src/boardwatch/llm/run_client.py`:

```python
"""Invocation-scoped LLM client: one credential death stops the whole lane.

A dead credential (out of credit, revoked, or lacking model access) fails every
remaining call identically, so continuing to call it burns real quota to learn
the same fact once per posting. This wrapper latches on the first
`LLMLaneDeadError` and refuses subsequent calls without touching the network.

It is installed by `llm.factory.build_client`, which both consumers call exactly
once per invocation -- so "invocation-scoped" is a property of that call site,
not of this class.
"""

from __future__ import annotations

from boardwatch.llm.client import LaneDeathReason, LLMLaneDeadError, ModelClient


class RunScopedClient:
    """Wrap a `ModelClient`, latching dead on the first lane death.

    Implements `ModelClient`, so it is a drop-in for the real adapters and no
    caller signature changes.
    """

    def __init__(self, inner: ModelClient) -> None:
        self._inner = inner
        self._dead: LaneDeathReason | None = None
        self.calls_attempted = 0

    @property
    def dead_reason(self) -> LaneDeathReason | None:
        """The reason the lane died, or None while it is healthy."""
        return self._dead

    def complete(self, prompt: str, *, system: str | None = None) -> str:
        if self._dead is not None:
            raise LLMLaneDeadError(
                f"LLM lane already dead ({self._dead}); not calling the provider",
                reason=self._dead,
            )
        self.calls_attempted += 1
        try:
            return self._inner.complete(prompt, system=system)
        except LLMLaneDeadError as exc:
            self._dead = exc.reason
            raise
```

In `src/boardwatch/llm/factory.py`, add the import:

```python
from boardwatch.llm.run_client import RunScopedClient
```

Change the return type annotation to `-> RunScopedClient | None`, and wrap both returns:

```python
        return RunScopedClient(AnthropicClient(settings.llm.model, api_key))
```

```python
    return RunScopedClient(
        OpenAICompatClient(settings.llm.base_url, settings.llm.model, api_key)
    )
```

Append to `build_client`'s docstring:

```
    The result is wrapped in `RunScopedClient` so a dead credential latches for
    the rest of the invocation (D-146). Callers that need the death reason
    narrow the result with `isinstance(client, RunScopedClient)`; `ModelClient`
    itself is unchanged and still guarantees only `.complete`.
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_llm_lane_death.py tests/pipeline/test_llm_lane.py -v`
Expected: PASS. `test_llm_lane.py`'s two existing `build_client` assertions check for `None`, so they are unaffected.

- [ ] **Step 5: Commit**

```bash
git add src/boardwatch/llm/run_client.py src/boardwatch/llm/factory.py tests/unit/test_llm_lane_death.py
git commit -m "Latch the LLM lane dead for the rest of an invocation"
```

---

### Task 5: The eligibility consumer — two counters and a real exit code

**Files:**
- Modify: `src/boardwatch/eligibility/extract_llm.py:143-148`
- Modify: `src/boardwatch/cli/eligibility_cmd.py:348-384`
- Test: `tests/pipeline/test_llm_lane.py`

**Interfaces:**
- Consumes: `LLMLaneDeadError`, `LaneDeathReason` (Task 1); the wrapper installed by Task 4.
- Produces: `boardwatch eligibility extract` printing `extracted {extracted} of {attempted} attempted` and exiting 1 only under *death observed ∧ `extracted == 0`*.

**The trap in this task.** `evaluated` currently does double duty — it caps the loop at `:363` *and* is the number reported at `:384`. Re-keying that one counter to landed successes silently removes the cap: an unclassified failure still returns `None`, so the counter would stop advancing and the loop would run the entire posting set. Use two counters. Test 3 below is the regression guard.

- [ ] **Step 1: Write the failing tests**

Append to `tests/pipeline/test_llm_lane.py`, reusing that file's existing `engine` and
`catalog_and_policy` fixtures and its CLI-invocation style (see `tests/pipeline/test_llm_lane.py:365`
for the established `monkeypatch.setattr("boardwatch.cli.eligibility_cmd.build_client", ...)` shape).

**Two fixtures do not exist yet and must be written as part of this step:**

- `cli_env_with_postings` — a configured CLI environment with a profile, the rule catalog, an
  enabled LLM tier, and **at least 2** open postings (the partial-success test needs a second one
  to reach). Its `data_dir` must be **fresh per test** so the response cache starts cold: the
  cache is consulted before the client (`lane.py:357-366`), so a warm cache would serve the
  request and the dead credential would never be reached, silently voiding the test.
- `cli_env_with_many_postings` — the same, but with **more than `llm.max_calls_per_run` (50)** open
  postings, so "stopped at the cap" is distinguishable from "ran out of work". This distinction is
  the entire point of the cap-regression test; with 50 or fewer postings it passes either way.

Both should build on whatever profile/catalog seeding helper the file already uses rather than
re-deriving it.

```python
class _DeadClient:
    """Every call reports the credential is unusable."""

    def __init__(self) -> None:
        self.calls = 0

    def complete(self, prompt: str, *, system: str | None = None) -> str:
        self.calls += 1
        raise LLMLaneDeadError("no credit", reason=LaneDeathReason.CREDIT_EXHAUSTED)


class _AlwaysFailingClient:
    """Ordinary, unclassified failure -- the swallowed kind."""

    def __init__(self) -> None:
        self.calls = 0

    def complete(self, prompt: str, *, system: str | None = None) -> str:
        self.calls += 1
        raise LLMError("network went away")


def test_dead_credential_stops_after_one_call_and_exits_1(
    monkeypatch: pytest.MonkeyPatch, cli_env_with_postings
):
    # Seed strictly more open postings than the cap so "stopped early" is
    # distinguishable from "ran out of work". Use a FRESH data dir: the cache is
    # consulted before the client, so a warm cache would mask the death (§6).
    client = RunScopedClient(_DeadClient())
    monkeypatch.setattr(
        "boardwatch.cli.eligibility_cmd.build_client", lambda settings: client
    )
    result = runner.invoke(app, ["eligibility", "extract"])
    assert result.exit_code == 1
    assert "extracted 0 of 1 attempted" in result.stdout
    assert "credit_exhausted" in result.stdout
    # The load-bearing assertion. The message alone passes with the defect present.
    assert client.calls_attempted == 1


def test_partial_success_before_death_exits_0(
    monkeypatch: pytest.MonkeyPatch, cli_env_with_postings
):
    class _DiesOnSecond:
        def __init__(self) -> None:
            self.calls = 0

        def complete(self, prompt: str, *, system: str | None = None) -> str:
            self.calls += 1
            if self.calls == 1:
                return '{"requirements": []}'
            raise LLMLaneDeadError("no credit", reason=LaneDeathReason.CREDIT_EXHAUSTED)

    monkeypatch.setattr(
        "boardwatch.cli.eligibility_cmd.build_client",
        lambda settings: RunScopedClient(_DiesOnSecond()),
    )
    result = runner.invoke(app, ["eligibility", "extract"])
    assert result.exit_code == 0
    assert "extracted 1 of 2 attempted" in result.stdout


def test_cap_survives_unclassified_failures(
    monkeypatch: pytest.MonkeyPatch, cli_env_with_many_postings
):
    # REGRESSION GUARD for the two-counter split. `cli_env_with_many_postings`
    # seeds more than llm.max_calls_per_run open postings. If `attempted` were
    # keyed to successes, every one of them would be called.
    client = _AlwaysFailingClient()
    monkeypatch.setattr(
        "boardwatch.cli.eligibility_cmd.build_client", lambda settings: client
    )
    result = runner.invoke(app, ["eligibility", "extract"])
    assert result.exit_code == 0  # unclassified failure is NOT lane death
    assert client.calls == 50  # llm.max_calls_per_run default


def test_all_unclassified_failures_still_exit_0(
    monkeypatch: pytest.MonkeyPatch, cli_env_with_postings
):
    # Zero-landed alone must never be fatal -- only death-observed AND zero.
    monkeypatch.setattr(
        "boardwatch.cli.eligibility_cmd.build_client",
        lambda settings: _AlwaysFailingClient(),
    )
    result = runner.invoke(app, ["eligibility", "extract"])
    assert result.exit_code == 0
    assert "extracted 0 of" in result.stdout
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/pipeline/test_llm_lane.py -k "dead_credential or partial_success or cap_survives or unclassified" -v`
Expected: FAIL — exit code 0 where 1 expected; `extracted N postings` message where `extracted N of M attempted` expected.

- [ ] **Step 3: Re-raise lane death, then split the counters**

In `src/boardwatch/eligibility/extract_llm.py`, import `LLMLaneDeadError` and replace lines 143-148 with:

```python
        try:
            raw = client.complete(payload["user"], system=payload["system"])
        except LLMLaneDeadError:
            # The credential cannot serve any later posting either, so this must
            # NOT be swallowed as a skip: the caller has to stop the loop.
            raise
        except Exception:
            # Any other provider/adapter failure (network, HTTP, malformed body)
            # degrades this opt-in lane to a skipped run. The deterministic lane
            # never sees this.
            return None
```

Update the docstring's `Returns:` clause to note that a dead credential propagates rather than returning `None`.

In `src/boardwatch/cli/eligibility_cmd.py`, import `LaneDeathReason` and `LLMLaneDeadError`, then replace the loop at lines 348-384:

```python
    # Two counters, deliberately. `attempted` is what bounds the loop; keying the
    # cap to successes instead would let unclassified failures run the ENTIRE
    # posting set, removing the only working call ceiling in the codebase.
    attempted = 0
    extracted = 0
    lane_death: LaneDeathReason | None = None
    run_id: int | None = None
    for current in ordered:
        if attempted >= settings.llm.max_calls_per_run:
            break
        if run_id is None:
            run_id = ensure_run(app_ctx.engine, None)
        attempted += 1
        try:
            with app_ctx.engine.begin() as conn:
                evaluation_id = extract_and_record(
                    conn,
                    posting_version_id=current.posting_version_id,
                    jd_text=current.body_text,
                    facts=facts,
                    policy=policy,
                    catalog=catalog,
                    client=client,
                    cache=cache,
                    provider=settings.llm.provider,
                    model=settings.llm.model,
                    run_id=run_id,
                )
        except LLMLaneDeadError as exc:
            lane_death = exc.reason
            break
        if evaluation_id is not None:
            extracted += 1
    if run_id is not None:
        finish_run(app_ctx.engine, run_id)
    console.print(f"extracted {extracted} of {attempted} attempted")
    if lane_death is not None:
        console.print(
            f"LLM lane stopped: the credential is unusable ({lane_death}). "
            "Remaining postings were not called."
        )
        # Fatal only when death was observed AND nothing landed: a partial run
        # is a real partial success, and zero-landed alone is a routine outcome.
        if extracted == 0:
            raise typer.Exit(code=1)
```

Keep the existing explanatory comment about minting `run_id` (lines 349-361) immediately above this block — it still applies verbatim.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/pipeline/test_llm_lane.py -v`
Expected: PASS. Any pre-existing test asserting the old `extracted N postings` message must be updated to the new wording in this same commit.

- [ ] **Step 5: Commit**

```bash
git add src/boardwatch/eligibility/extract_llm.py src/boardwatch/cli/eligibility_cmd.py tests/pipeline/test_llm_lane.py
git commit -m "Stop the eligibility lane on a dead credential and report what landed"
```

---

### Task 6: The tailor consumer — both boundaries, and a reason the CLI can name

**Files:**
- Modify: `src/boardwatch/tailor/rewrite/lane.py:90,286`
- Modify: `src/boardwatch/cli/tailor_cmd.py:235-241`
- Test: `tests/unit/test_tailor_cmd_tier_b.py`

**Interfaces:**
- Consumes: `LLMLaneDeadError` (Task 1); `RunScopedClient.dead_reason` (Task 4).
- Produces: `RewriteRow.drop_reason == "lane_dead"` at both containment boundaries; `boardwatch tailor --tier-b` exiting 1 only under *death observed ∧ zero kept*.

**Why the judge arm needs its own fake.** With the latch set, a client that dies immediately dies at the *propose* boundary (`lane.py:90`) and every later call short-circuits there too — so `lane.py:286` is unreachable unless propose succeeds and judge dies. Parameterise, and give the judge arm a fake that returns a candidate then dies.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_tailor_cmd_tier_b.py`, following the scripted-client fixture at line 206:

```python
class _DiesOnNthCall:
    """Succeeds for `n - 1` calls, then reports the credential is unusable."""

    def __init__(self, n: int, reply: str = "a rewritten bullet") -> None:
        self._n = n
        self._reply = reply
        self.calls = 0

    def complete(self, prompt: str, *, system: str | None = None) -> str:
        self.calls += 1
        if self.calls >= self._n:
            raise LLMLaneDeadError("revoked", reason=LaneDeathReason.CREDENTIAL_INVALID)
        return self._reply


class _AlwaysSucceeds:
    """Never fails. Used to warm the response cache and to drive the budget path."""

    def __init__(self, reply: str = "a rewritten bullet") -> None:
        self._reply = reply
        self.calls = 0

    def complete(self, prompt: str, *, system: str | None = None) -> str:
        self.calls += 1
        return self._reply


@pytest.mark.parametrize("die_on", [1, 2], ids=["propose-boundary", "judge-boundary"])
def test_lane_death_records_lane_dead_and_keeps_tier_a(
    env: Env, monkeypatch: pytest.MonkeyPatch, die_on: int
) -> None:
    posting_id = _seed_open_posting(env)
    _write_tier_b_config(env)
    inner = _DiesOnNthCall(die_on)
    client = RunScopedClient(inner)
    monkeypatch.setattr("boardwatch.cli.tailor_cmd.build_client", lambda settings: client)

    result = _run(env, ["tailor", str(posting_id), "--tier-b"])

    assert "lane_dead" in result.stdout
    assert "credential_invalid" in result.stdout
    assert result.exit_code == 1  # death observed AND zero kept
    # Tier A is untouched: the lane is advisory and must never delete a lead.
    assert _artifact_count(env) > 0
    # One network call total, however many bullets remained.
    assert inner.calls == die_on


def test_healthy_run_keeping_zero_rewrites_still_exits_0(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 13 of lane.py's 14 row-writing paths set kept=False, so zero-kept is a
    # routine HEALTHY outcome. Exiting non-zero on it would break normal use.
    #
    # Driven through the BUDGET path rather than the judge: with the cap at 1 the
    # first propose spends the only call and every later bullet is dropped with
    # drop_reason="budget", kept=False. Deterministic, and it needs no knowledge
    # of the judge's verdict vocabulary. `_write_tier_b_config` already takes the
    # cap as a keyword.
    posting_id = _seed_open_posting(env)
    _write_tier_b_config(env, max_calls_per_run=1)
    monkeypatch.setattr(
        "boardwatch.cli.tailor_cmd.build_client",
        lambda settings: RunScopedClient(_AlwaysSucceeds()),
    )

    result = _run(env, ["tailor", str(posting_id), "--tier-b"])

    assert result.exit_code == 0
    assert "lane_dead" not in result.stdout


def test_warm_cache_work_still_lands_after_death(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The cache is checked BEFORE the client (lane.py:357-366), so cached bullets
    # keep landing after the latch trips. That is the specified policy (§6): a
    # mixed invocation is a partial success and exits 0.
    #
    # Warm the cache by running once with a healthy client, then re-run against a
    # dead one -- simpler and more faithful than hand-computing cache keys. Both
    # invocations share `env.data_dir` (via `_run`'s `--data-dir`), which is what
    # makes the cache warm on the second pass, and is exactly why the eligibility
    # dead-credential test insists on a fresh dir instead.
    posting_id = _seed_open_posting(env)
    _write_tier_b_config(env)
    healthy = RunScopedClient(_AlwaysSucceeds())
    monkeypatch.setattr("boardwatch.cli.tailor_cmd.build_client", lambda settings: healthy)
    first = _run(env, ["tailor", str(posting_id), "--tier-b"])
    assert first.exit_code == 0
    assert healthy.calls_attempted > 0

    dead = RunScopedClient(_DiesOnNthCall(1))
    monkeypatch.setattr("boardwatch.cli.tailor_cmd.build_client", lambda settings: dead)
    second = _run(env, ["tailor", str(posting_id), "--tier-b"])

    assert second.exit_code == 0
    # Every prompt was served from the cache, so the dead client was never called.
    assert dead.calls_attempted == 0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_tailor_cmd_tier_b.py -k "lane_death or zero_rewrites or warm_cache" -v`
Expected: FAIL — `drop_reason` is `"error"`, not `"lane_dead"`; exit code 0 where 1 expected.

- [ ] **Step 3: Record the typed drop reason, then report it**

In `src/boardwatch/tailor/rewrite/lane.py`, import `LLMLaneDeadError` and insert this arm **immediately before** each of the two `except Exception:` boundaries (currently at lines 90 and 286). The `bullet_id`/`entry_id`/`a_text` values differ per site — copy them from the adjacent `except Exception` block at the same site:

```python
            except LLMLaneDeadError:
                # The credential is dead for the rest of this invocation. No
                # re-raise: the wrapper makes every later bullet free, and the
                # invocation-level state lives there. Distinguished from "error"
                # so the CLI can tell a dead credential from a flaky one.
                rows.append(
                    RewriteRow(
                        bullet_id=b.bullet_id,
                        entry_id=entry.entry_id,
                        a_text=a_text,
                        b_text=a_text,
                        filter_pass=False,
                        judge_verdict=None,
                        kept=False,
                        drop_reason="lane_dead",
                    )
                )
                continue
```

In `src/boardwatch/cli/tailor_cmd.py`, import `RunScopedClient` and add after the existing budget warning at lines 235-241:

```python
        if any(r["drop_reason"] == "lane_dead" for r in result.rewrites):
            # The rows prove death occurred; they cannot say WHICH reason --
            # drop_reason is a free-form string and duplicating the typed reason
            # into it would be classifying behaviour by string content. Read the
            # reason off the client this command constructed and therefore knows
            # the concrete type of.
            reason = client.dead_reason if isinstance(client, RunScopedClient) else None
            console.print(
                f"Tier B stopped: the LLM credential is unusable ({reason}). "
                "Remaining bullets kept their Tier A text; the Tier A file above "
                "is unaffected."
            )
            if not any(r["kept"] for r in result.rewrites):
                raise typer.Exit(code=1)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_tailor_cmd_tier_b.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/boardwatch/tailor/rewrite/lane.py src/boardwatch/cli/tailor_cmd.py tests/unit/test_tailor_cmd_tier_b.py
git commit -m "Distinguish a dead credential from a flaky one in the Tier B lane"
```

---

### Task 7: Records, retractions, and the gate

**Files:**
- Modify: `docs/program/DECISIONS.md` (append D-146 + its index row)
- Modify: `docs/program/PROGRAM.md:340-351`
- Modify: `docs/program/STATE.md`
- Modify: `CHANGELOG.md`
- Modify: `src/boardwatch/core/settings.py:43-44` (docstring only)

**Interfaces:**
- Consumes: everything above.
- Produces: no code interface. This task makes the program documents true.

- [ ] **Step 1: Correct the falsified premise in PROGRAM.md**

Item 10 currently asserts *"At 2 model calls per bullet, B1's ≥10 leads/day is ~300 calls/day unattended"* and lists *"resumable idempotence"* as still open. Both are false. Replace its status paragraph with:

```markdown
   **PARTIAL** (D-040, D-146). The transient-429/5xx retry half is DONE (D-040). Lane-death
   classification, latching, and honest reporting are DONE for the two lanes that actually call
   out (D-146). **The premise of this item is retracted:** `boardwatch run` makes ZERO LLM calls
   in the tailor lane — `pipeline/runner.py` never constructs a client and passes none to
   `run_tailor`, so `reports/tailor.py:459` skips Tier B on every unattended run. There is no
   ~300-calls/day workload to bound until the pipeline is wired, which is an open owner decision,
   not part of this item. Resumable idempotence is **declined**, not open (D-042). Batched judging
   remains deferred.
```

- [ ] **Step 2: Append D-146 to DECISIONS.md**

Append the decision at the end of the file, in the established `## D-NNN — title` form, covering: the closed `LaneDeathReason` catalog; classification at the raise site from the error body (never the status alone, because Anthropic's 403 carries two meanings); the deliberately narrower openai-compat catalog with bare 403 **unmapped**; the latching wrapper installed in `build_client`; two counters in the eligibility loop with the cap on `attempted`; exit 1 only under death-observed ∧ zero-landed; and the two things deliberately not built (the run-scoped ceiling, the pipeline wiring). Record the alternatives rejected: three separate exception types, threading run-scoped state through `run_tailor`, and GPT-5.6-sol's provider-specific classification tables.

Then add its index row in the index table at the top of the file, and run:

```bash
make reindex
```

- [ ] **Step 3: Fix the misleading docstring**

In `src/boardwatch/core/settings.py:43-44`, amend the `max_calls_per_run` description to state that it bounds calls **per invocation of the eligibility lane** and **per résumé** in the tailor lane — it is not a per-run total. No behaviour change.

- [ ] **Step 4: Update STATE.md and CHANGELOG.md**

STATE.md: record that P3 slice 5 shipped scoped to the two calling lanes, that item 10's premise was retracted, and add the unwired pipeline to the live-blockers table as an owner-gated decision. CHANGELOG.md: note the new non-zero exit from `boardwatch eligibility extract` and `boardwatch tailor --tier-b` on a dead credential — it is a public CLI contract change.

- [ ] **Step 5: Run the full gate**

This diff touches `src/`, so it owes the full gate, not the docs-only one. Background it — it takes 5–17 minutes and is CPU-bound:

```bash
make check > /tmp/p3s5-gate.log 2>&1; ec=$?; echo "GATE_EXIT=$ec"; exit $ec
```

Expected: `GATE_EXIT=0`. `All checks passed!` is only the lint step and appears early — `GATE_EXIT` plus the pytest summary are the only verdict. Never pipe this through `head`/`tail`.

- [ ] **Step 6: Commit**

```bash
git add docs/program/DECISIONS.md docs/program/PROGRAM.md docs/program/STATE.md CHANGELOG.md src/boardwatch/core/settings.py
git commit -m "Record D-146 and retract item 10's unattended call-volume premise"
```

---

## Verification checklist

Before calling this done, confirm each spec §7 test exists and is red without its fix:

| Spec test | Task | Where |
|---|---|---|
| 1 — per-adapter classification, enum read at run time | 2, 3 | `test_anthropic_cases_cover_every_reason` |
| 2 — out-of-catalog + malformed shapes | 1, 2 | `test_classifier_never_raises_...` (9 shapes) |
| 3 — latch is real, asserted on the inner counter | 4 | `test_wrapper_latches_and_stops_touching_the_network` |
| 4 — 429 discriminated, both arms | 2, 3 | `test_openai_compat_429_*` |
| 5 — silent-success fix, cold cache, one call | 5 | `test_dead_credential_stops_after_one_call_and_exits_1` |
| 6 — partial success exits 0 | 5 | `test_partial_success_before_death_exits_0` |
| 7 — both tailor boundaries | 6 | `test_lane_death_records_lane_dead_...` (parameterised) |
| 8 — factory actually wraps, real `build_client` | 4 | `test_build_client_wraps_every_adapter_branch` |
| 9 — cap survives unclassified failure | 5 | `test_cap_survives_unclassified_failures` |
| 10 — healthy zero-output exits 0 | 5, 6 | `test_all_unclassified_failures_still_exit_0`, `test_healthy_run_keeping_zero_rewrites_still_exits_0` |
| 11 — warm cache after death | 6 | `test_warm_cache_work_still_lands_after_death` |

Then run the §7.2 regression sweep: grep for tests asserting the old `extracted N postings` message, the old `drop_reason="error"` on provider failure, and any `isinstance` or attribute access on `build_client`'s result.

**Confirm against a live endpoint if possible:** §5.1's OpenAI-429-`insufficient_quota` and DeepSeek-402 mappings are from provider documentation and are not verifiable from this repository. Record what a real error body actually contains when the opportunity arises, and correct the catalog if it differs.

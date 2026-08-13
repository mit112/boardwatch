# LLM lane-death provider error bodies — verification research

Research task, 2026-08-12. Goal: confirm or correct the two documentation-only mappings
(OpenAI 429/`insufficient_quota`, DeepSeek 402) and audit the `openai_compat` / `anthropic`
adapters for misfire risk, per the design doc's explicit call-out that neither mapping was
verified against a live endpoint.

Authority ranking used below: official API docs / official error-code pages > provider
changelogs > a real error body quoted in a GitHub issue (first-party evidence, but
second-hand transcription) > community forum posts > third-party blogs.

---

## 1. OpenAI, exhausted credit / quota

**Official, current source:** `https://platform.openai.com/docs/guides/error-codes` 301-redirects
to `https://developers.openai.com/api/docs/guides/error-codes` — fetched directly, this is the
single canonical current page (not a fork or a different/newer product's docs). Full relevant row,
quoted verbatim:

> **429 - Credit balance exhausted** — Code: `credit_balance_exhausted` — Cause: Your organization
> has no prepaid credits remaining. — Solution: Add credits to continue using the API.

And, critically, this sentence appears directly under the API-errors table:

> "For billing-related errors, inspect `error.code` to identify the specific cause. **The broader
> `error.type` can still be `insufficient_quota`.**"

So per the *current* official docs: **status 429 is right**, but the `error.code` token for this
condition is now `credit_balance_exhausted`, not `insufficient_quota`. The `error.type` field is
explicitly documented as still (as of today) carrying `insufficient_quota`.

**Real observed bodies** (community forum quotes, medium authority, undated but recurring
2023–2025 and referenced again in a 2026 Azure context — see §6): the full shape people actually
report receiving is

```json
{
  "error": {
    "message": "You exceeded your current quota, please check your plan and billing details.",
    "type": "insufficient_quota",
    "param": null,
    "code": "insufficient_quota"
  }
}
```

i.e. real-world bodies people quote still show `code == "insufficient_quota"` too, not
`credit_balance_exhausted`. I could not obtain a freshly-dated (2026), byte-exact raw HTTP capture
of a genuine OpenAI (non-Azure) credit-exhaustion response to settle whether `code` has actually
rolled over in production or whether the docs describe a value that hasn't fully replaced the old
one yet, or whether contributors are quoting stale/cached responses. **This point is not fully
established** — there is a real, sourced discrepancy between the current official docs (`code:
credit_balance_exhausted`) and the token everyone quotes from lived experience (`code:
insufficient_quota`).

**Verdict on the mapping under test:** the boardwatch adapter checks `error.code` **or**
`error.type` == `insufficient_quota`. Per the official docs, the `type` half of that OR is
confirmed current. The `code` half is checking a token the official docs say has been superseded
by `credit_balance_exhausted` — it may still catch real traffic (per community quotes) but is not
future-proof, and is exactly the "renamed token" risk the design doc worried about.
**Recommended change: add `credit_balance_exhausted` as an additional value the `code` check
matches, do not remove `insufficient_quota`.**

---

## 2. OpenAI, ordinary rate limiting

Official docs (same page): **429 - Rate limit reached for requests** has **no `Code:` field
documented at all** — only a Cause/Solution pair ("You are sending requests too quickly.").

A real quoted body for this case (community, medium authority):

```json
{ "error": { "message": "You've exceeded the rate limit, please slow down and try again later.",
  "type": "invalid_request_error", "code": "rate_limit_exceeded" } }
```

So ordinary rate-limit 429s carry `type: invalid_request_error` / `code: rate_limit_exceeded` —
neither token is `insufficient_quota`. The two cases are documented as structurally distinct rows
in the same official table, and every real body I found for each case stays on its own side.
**Reliable** — nothing found suggests ordinary 429s ever carry `insufficient_quota` in `type` or
`code`.

---

## 3. OpenAI, revoked or invalid key

Official docs list four distinct 401 causes:
- "Invalid Authentication" (bad key/org mismatch/insufficient endpoint permission) — no `code`
  documented in the table.
- "Incorrect API key provided" — no `code` documented in the table, but a real body (GitHub
  `openai/openai-python#1968`, first-party evidence) shows:
  ```json
  {"error": {"message": "Incorrect API key provided: sk-***...",
    "type": "invalid_request_error", "param": null, "code": "invalid_api_key"}}
  ```
- "You must be a member of an organization to use the API" — org membership issue.
- "IP not authorized" — IP allowlist mismatch.

**401 is confirmed correct.** A distinct code worth catching separately if finer granularity is
ever wanted: `invalid_api_key` — but all four 401 causes are genuinely "this credential/context
cannot be used," so folding them all into `CREDENTIAL_INVALID` at the status-code level (as the
adapter does) is sound and doesn't need the extra code check.

---

## 4. DeepSeek, exhausted balance

**Official source, fetched directly:** `https://api-docs.deepseek.com/quick_start/error_codes`.
Full table:

| Code | Cause | Solution |
|---|---|---|
| 400 - Invalid Format | Invalid request body format | Modify request body per error hints |
| 401 - Authentication Fails | Authentication fails due to the wrong API key | Check your API key |
| 402 - Insufficient Balance | You have run out of balance | Check account balance, top up |
| 422 - Invalid Parameters | Your request contains invalid parameters | Adjust parameters |
| 429 - Rate Limit Reached | You are sending requests too quickly | Pace requests / use another provider |
| 500 - Server Error | Server encounters an issue | Retry after brief wait |
| 503 - Server Overloaded | Server overloaded due to high traffic | Retry after brief wait |

**402 is confirmed.** No JSON body shape is shown on the official page at all — it documents only
status + cause + solution, no schema.

**Real observed body** (GitHub `continuedev/continue#4766`, first-party evidence, a live capture):

```json
{"error":{"message":"Insufficient Balance","type":"unknown_error","param":null,"code":"invalid_request_error"}}
```

Notably the body's own `type`/`code` fields are generic (`unknown_error` / `invalid_request_error`)
— DeepSeek does **not** put a distinguishing token in the body for this case. This directly
validates boardwatch's design: classification for DeepSeek 402 must rely on the **bare HTTP
status**, not a body-content match (there is no useful body token to match on). The
`openai_compat` adapter's 402→`CREDIT_EXHAUSTED` status-code rule, independent of body content, is
exactly right for this provider.

---

## 5. DeepSeek, invalid key

Official docs (same page): **401 - Authentication Fails** — "Authentication fails due to the wrong
API key." No distinct machine-readable code beyond the status is documented, and no body shape is
shown. **401 confirmed correct**, nothing further to add.

---

## 6. Misfire risk across OpenAI-compatible providers

This is the highest-value question. Findings, worst first:

### Azure OpenAI — CONFIRMED real misfire, high severity

Source: Microsoft Q&A, `learn.microsoft.com/en-in/answers/questions/5759907` (official Microsoft
response quoted on the page), corroborated by multiple other Microsoft Q&A threads found in
search. A user's exact captured body for a **recoverable, per-deployment TPM/RPM rate-limit
condition** (not billing exhaustion — the account had a live $5,000 Azure credit balance):

```json
{
  "error": {
    "message": "You exceeded your current quota, please check your plan and billing details. ...",
    "type": "insufficient_quota",
    "code": "insufficient_quota",
    "param": null
  }
}
```

Microsoft's own explanation, quoted: "Azure credits are not the same as OpenAI Quota... Azure
OpenAI can still return 429 insufficient_quota when you run out of the model quota assigned to
your Azure subscription/region... quota is typically scoped at the subscription level, and rate
limits are allocated per region + per model/deployment type (TPM/RPM)." This is recoverable within
minutes (TPM/RPM reset on a rolling window) or by requesting a quota increase — it is **not**
"the credential is dead."

Because boardwatch's body check runs at **any status** and matches on `error.type ==
"insufficient_quota"` before the retryable-status check ever sees the response, an Azure OpenAI
deployment that is merely rate-limited on its assigned TPM/RPM band will produce the bit-identical
token boardwatch treats as terminal credit exhaustion. **This latches `CREDIT_EXHAUSTED` and
silences the lane for the rest of the invocation on a condition that would have cleared itself in
under a minute.** Since the `openai_compat` adapter is explicitly designed to reach any
OpenAI-compatible endpoint including Azure, this is a real and currently-live risk, not a
hypothetical one.

### OpenRouter — CONFIRMED real misfire, medium severity

Source: OpenRouter official docs (`openrouter.ai/docs/api_reference/limits`, fetched directly) plus
a live captured body from GitHub `continuedev/continue#10298` (first-party evidence):

> "402 This request requires more credits, or fewer max_tokens. You requested up to 4096 tokens,
> but can only afford 4000."

This is a **per-request** sizing condition, not necessarily a dead/empty account — a smaller
`max_tokens` value on the very same key can succeed immediately afterward. Official docs describe
402 generally as "insufficient credits" (account or per-key limit), consistent with this. If
boardwatch treats a bare 402 as terminal `CREDIT_EXHAUSTED` for the rest of the invocation, a
single oversized request against OpenRouter can kill a lane that is, in fact, still usable for
every subsequent smaller request.

### Together AI — informative, but validates an existing design choice, not a new risk

Source: `docs.together.ai/docs/error-codes`, fetched directly. Together uses **403** — not 402 —
for "input tokens + max_tokens must be less than model's context length" (a per-request sizing
issue, not a permission/credential problem). This directly validates boardwatch's decision to leave
bare 403 unmapped: on at least one real OpenAI-compatible provider, 403 is a routine per-request
validation error, and mapping it to anything credential-related would misfire immediately. Together
AI's 402 is documented purely as "account has reached its maximum allowed monthly spending limit" —
account-level, not per-request, so the CREDIT_EXHAUSTED-for-the-rest-of-invocation behavior is
reasonably safe here (a monthly limit will not clear itself within one run either way).

### Groq — no misfire found, well-separated by design

Source: `console.groq.com/docs/errors`, fetched directly. Groq's docs do not define a 402 at all,
and reserve 401 strictly for "lacks valid authentication credentials." Parameter/model problems are
routed to 422, not 401. No evidence of a non-credential condition producing 401 or 402 on Groq.

### Ollama / vLLM / LM Studio / llama.cpp — low risk, but for a different reason: no billing layer exists

- **Ollama (local):** missing/unpulled model returns 404, not 401/402 (multiple GitHub issues,
  `ollama/ollama#2753` and others). **Ollama Cloud** (hosted, cloud-tagged models) can return 401
  when cloud access isn't enabled for the key — this is still auth-shaped, not a clean misfire, but
  worth noting it's "cloud feature not enabled" rather than "key revoked," a softer failure than
  boardwatch's `CREDENTIAL_INVALID` implies.
- **vLLM:** its own docs (`docs.vllm.ai/en/stable/usage/security`) show `--api-key` gates only
  `/v1`-prefixed paths; 401 fires only on a missing/incorrect bearer token. One reported quirk: an
  internal health-check request without an Authorization header can 401 — a client-side bug in the
  calling tool, not a vLLM misfire against real inference traffic. No 402 concept exists (no
  billing layer).
- **LM Studio:** ignores the `api_key` value entirely on localhost by default (auth off); when a
  static key is configured for LAN access, 401 is a plain bad-bearer-token case. No 402 concept.
- **llama.cpp server:** not established — no documented or reported evidence found either way for
  401/402 semantics. By analogy with vLLM/LM Studio (no billing subsystem in any self-hosted
  inference server), a 402 is very unlikely to ever be emitted, but this is inference from a
  pattern, not a confirmed fact about llama.cpp specifically, and I'm flagging it as such rather
  than asserting it.

**Net for question 6:** the two live, sourced misfire risks are Azure OpenAI (429 +
`insufficient_quota`, transient TPM/RPM band, not billing) and OpenRouter (402 as a per-request
`max_tokens`-vs-credit mismatch, not necessarily account-empty). Both are real providers reachable
through the generic `openai_compat` adapter today.

---

## 7. Anthropic's error types

**Official, current source, fetched directly:** `https://docs.anthropic.com/en/api/errors`
301-redirects to `https://platform.claude.com/docs/en/api/errors` (current canonical page, no
staleness markers). Full status/type table, quoted:

| Status | `error.type` |
|---|---|
| 400 | `invalid_request_error` |
| 401 | `authentication_error` |
| **402** | **`billing_error`** |
| **403** | **`permission_error`** |
| 404 | `not_found_error` |
| 409 | `conflict_error` |
| 413 | `request_too_large` |
| 429 | `rate_limit_error` |
| 500 | `api_error` |
| 504 | `timeout_error` |
| 529 | `overloaded_error` |

**All three type names (`billing_error`, `authentication_error`, `permission_error`) are current** —
confirmed against the live official page, no deprecation or rename notice anywhere on it.

**However, the status pairing asserted in the design/background is wrong.** The background states
the `anthropic` adapter maps "`billing_error`→credit exhausted (**403**)". Per the official docs,
`billing_error` is carried on **402**, and `permission_error` is what's carried on 403 — they are
two different types on two different status codes, not both on 403. **This should be corrected**
wherever it's written down; if the adapter's *dispatch logic* (not just its comments) actually
gates on HTTP status 403 to recognize `billing_error`, that branch would never fire in production,
because Anthropic never sends `billing_error` on a 403 response — worth checking the actual code,
not just the doc comment, since this task was scoped to sourcing rather than to reading the
adapter's source.

**Type the catalog arguably should include but doesn't:** none, for the specific purpose of
lane-death classification. Of the eleven documented types, the remaining eight
(`invalid_request_error`, `not_found_error`, `conflict_error`, `request_too_large`,
`rate_limit_error`, `api_error`, `timeout_error`, `overloaded_error`) are all either per-request
validation problems or transient/retryable server-side conditions — none of them indicate "this
credential is dead," so excluding them from the three-value catalog is correct, not a gap.

---

## Summary of source authority used

- Official, fetched directly, current: OpenAI error-codes page, DeepSeek error-codes page,
  Anthropic errors page, Groq errors page, Together AI errors page, OpenRouter limits page.
- First-party but second-hand (a real captured body quoted inside a GitHub issue): OpenAI
  `invalid_api_key` body, DeepSeek 402 body, OpenRouter 402 body, Azure `insufficient_quota` body +
  Microsoft's own explanatory response on that same page.
- Community forum quotes (medium authority, used only where no official/first-party source existed,
  and flagged as such): OpenAI ordinary-rate-limit body, general "insufficient_quota still seen in
  2025–2026" pattern.
- No blog-only claims were relied upon for any of the seven verdicts above; where a blog was the
  only source found (e.g. llama.cpp 401/402 behavior), the finding is marked "not established"
  rather than asserted.

---

## Addendum — tightened verification requested by the coordinator (2026-08-12)

Two findings above are load-bearing for committed code and a test fixture. Re-verified directly,
with full quotes, because a summary is not enough to change code against.

### 1. Anthropic: `billing_error` on 402 vs 403 — RECONFIRMED, quote in full

Fetched directly again: `https://docs.anthropic.com/en/api/errors` → 301 →
`https://platform.claude.com/docs/en/api/errors` (same canonical page, re-verified live).

Full bullet list, every row, verbatim, in order:

> * 400 - `invalid_request_error`: There was an issue with the format or content of your request.
>   This error type may also be used for other 4XX status codes not listed in this section.
> * 401 - `authentication_error`: There's an issue with your API key (for example, it's malformed,
>   revoked, or expired; see Key expiration). On Claude Platform on AWS, this can also indicate a
>   problem with your AWS credentials or SigV4 signature.
> * 402 - `billing_error`: There's an issue with your billing or payment information. Check your
>   payment details in the Claude Console, or in AWS Marketplace if you're using Claude Platform on
>   AWS.
> * 403 - `permission_error`: Your API key does not have permission to use the specified resource.
>   Check your organization's access and workspace settings in the Claude Console.
> * 404 - `not_found_error`: The requested resource was not found. Check the endpoint path and any
>   resource IDs in the request URL.
> * 409 - `conflict_error`: The request conflicts with the current state of a resource. For example,
>   the resource was modified concurrently, or a value that must be unique is already in use.
>   Resolve the conflict, then retry the request.
> * 413 - `request_too_large`: Request exceeds the maximum allowed number of bytes. See Request size
>   limits for per-endpoint maximums.
> * 429 - `rate_limit_error`: Your account has hit a rate limit.
> * 500 - `api_error`: An unexpected error has occurred internal to Anthropic's systems. Retry the
>   request with exponential backoff; if the error persists, contact support with the request ID.
> * 504 - `timeout_error`: The request timed out while processing. Consider using the streaming
>   Messages API for long-running requests. See Long requests for more options.
> * 529 - `overloaded_error`: The API is temporarily overloaded.

`billing_error` appears exactly once on the page, on 402. `403` appears exactly once, on
`permission_error`. There is no second table, note, or SDK-reference section elsewhere on the page
that re-pairs either token differently — confirmed by re-fetching and asking directly whether `403`
or `billing_error` appear anywhere outside this one list; they do not.

**Corroborating (not authoritative) historical data point:** GitHub
`anthropics/anthropic-sdk-typescript#618` (opened 2024-11-28), fetched directly:

> Status code: `400` (Bad Request) — Error message: "Your credit balance is too low to access the
> Anthropic API. Please go to Plans & Billing to upgrade or purchase credits." The reporter
> questioned whether `402 Payment Required` would be more appropriate... reserving `400` for
> actually malformed requests.

No maintainer reply is visible confirming a fix, so this is not proof of *when* the change to 402
happened — but it shows the type has, at different points in time, been observed on 400 and is
currently documented on 402. **At no point, in any source found, is `billing_error` paired with
403.** The claim "403 carries both `billing_error` and `permission_error`" in the code comment and
test fixture is not supported by the current official docs and should be corrected: `billing_error`
is 402, `permission_error` is 403 — two types, two different statuses, not one status with two
types. If the adapter's actual branch logic (as opposed to just the comment) gates `billing_error`
recognition on HTTP status 403, that branch is dead code against real Anthropic traffic.

### 2. OpenAI: `credit_balance_exhausted` — RECONFIRMED, quote in full, weaker than first stated

Fetched directly again: `https://developers.openai.com/api/docs/guides/error-codes` (canonical;
`platform.openai.com/docs/guides/error-codes` 301-redirects to this exact page).

Exact table row:

> **429 - Credit balance exhausted** | Code: `credit_balance_exhausted` | Cause: Your organization
> has no prepaid credits remaining. | Solution: Add credits to continue using the API.

Exact, only sentence anywhere on the page mentioning `insufficient_quota`:

> "For billing-related errors, inspect `error.code` to identify the specific cause. The broader
> `error.type` can still be `insufficient_quota`."

The page carries **no date, version number, or "last modified" marker** anywhere (checked top,
bottom, and metadata on a direct re-fetch). The page does **not** say `insufficient_quota` is
deprecated/legacy/phased out in `code`, and does **not** explicitly say both values are emitted
simultaneously in `code` — it only documents `credit_balance_exhausted` as *the* code for this row,
and separately says `type` "can still be" `insufficient_quota`.

**Correction to my first pass:** I do not have a dated, byte-exact 2026 raw capture proving `code`
has actually stopped being `insufficient_quota` in live traffic — real bodies people quote,
*including the Azure one below*, still show `'code': 'insufficient_quota'` verbatim. So: **treat
this as additive-safe, not a replacement.** Add `credit_balance_exhausted` as an extra value the
`code` check matches; do not remove the existing `insufficient_quota` check on either field, since
I cannot confirm it has stopped appearing — only that the docs now lead with a different token.

### 3. Azure misfire — solidity and discriminator, re-checked

Source re-confirmed as first-party, not an anonymous forum post: `https://learn.microsoft.com/en-in/answers/questions/5759907`, answered by a listed Microsoft
MVP/volunteer moderator. Full captured body, quoted from the original question:

> ```
> ERROR:root:OpenAI API call failed: Error code: 429 - {'error': {'message': 'You exceeded your
> current quota, please check your plan and billing details. For more information on this error, read
> the docs: https://platform.openai.com/docs/guides/error-codes/api-errors.', 'type':
> 'insufficient_quota', 'param': None, 'code': 'insufficient_quota'}}
> ```
> (account had $4,999 of $5,000 credits remaining at the time)

Official answer, quoted in full:

> "Azure credits ($5,000) are not the same as OpenAI Quota. Azure OpenAI can still return 429
> insufficient_quota when you run out of the model quota assigned to your Azure subscription/region.
> In Azure OpenAI, quota is typically scoped at the subscription level, and rate limits are
> allocated per region + per model/deployment type (TPM/RPM)."

**Discriminator — re-checked, and it is weaker than a clean confirmation.** Direct re-query of that
exact thread: "No one in the thread mentions a `Retry-After` header, an `innererror` field, or any
way to distinguish this error from real billing exhaustion." Separately (general Azure OpenAI
throttling documentation, not this specific body), 429 responses for TPM/RPM throttling are commonly
described as carrying `retry-after-ms`, `x-ratelimit-remaining-tokens`, and
`x-ratelimit-remaining-requests` headers, e.g.:

> `HTTP/1.1 429 Too Many Requests / retry-after-ms: 10000 / x-ratelimit-remaining-tokens: 0 /
> x-ratelimit-remaining-requests: 0`

And OpenAI's own official error-codes page places "follow the `Retry-After` header when it's
present" only under the **rate-limit** row, not under the credit-exhaustion row — a structural hint,
not an explicit statement.

**Verdict: the misfire itself is solid** (first-party captured body + a named Microsoft moderator's
explanation, corroborated by the account's own $4,999 remaining balance at the time). **The proposed
discriminator (`Retry-After` present ⇒ throttle, absent ⇒ real exhaustion) is NOT established** — no
source states this directly for the two cases side by side. Do not build a fix that assumes this
discriminator exists without capturing both response types directly against a live endpoint first.

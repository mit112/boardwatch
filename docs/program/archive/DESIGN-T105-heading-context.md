# T105 — Bounded heading context for bullet lists

**Status: DESIGN, no code.** Required by T105's own acceptance contract: *"A design document exists
and is reviewed **before** any code."*

**Read §0 first.** Two statements in the ticket's own "Test gap" paragraph are false, and one of
them is the reason a naive implementation breaks the corpus.

---

## 0. Corrections to the ticket text

1. **There are SIX direct `split_units` tests, not four, and one of them is already a
   heading-plus-bullet-list shape** — `tests/unit/test_eligibility_detect.py:33, :38, :46, :52,
   :59, :75` (plus the memoisation test at `:477`). The relevant one is
   `test_a_bullet_line_is_its_own_unit` (`:75-86`), and its docstring is an **explicit anti-change
   lock on this ticket's territory**:

   > The marker stays attached. `\n+` sits earlier in `_SENTENCE_SPLIT`'s alternation and consumes
   > the newline, so the bullet branch never sees the leading `\s` it needs… **Do NOT reorder the
   > alternation to strip the marker: the 108-case corpus was verified against these matching
   > semantics.**

   So T105 must either leave the unit list **byte-identical** or deliberately overturn that lock.
   The design below takes the first route.
2. **The golden corpus cannot express this shape at all** — not "the four `Nice to have:` rows are
   inline", as the ticket says. `CASES` spans `test_eligibility_corpus.py:121-1203`, one row per
   line, and **zero of the 1,076 rows contain a newline**. The corpus is structurally incapable of
   exercising any multi-line body. That is a stronger statement and it changes the test plan: a new
   multi-line fixture surface is needed, not a few more rows.

---

## 1. The regression this owns

Posting **261677** reads `ineligible` although its bare-bachelor's arm clears
(`DECISIONS.md:30382-30385`, `STANDING-FACTS.md:3532-3534`). It is a bullet ladder:

```
HS Diploma (or equivalent) AND 4+ yrs
OR Associate's AND 2+
OR Bachelor's
```

**Cause, mechanically.** `_SENTENCE_SPLIT` (`detect.py:46`) splits on `\n+` and on bullet markers,
so `split_units` (`:105-127`) returns each bullet as an isolated unit and the heading is gone by the
time any bullet is read. Every suppressor is bounded at or below the unit (`detect.py:9-27`), so a
hedge, negation, jurisdiction or explicit `OR` stated in a heading can never reach the bullet it
governs. The one inline mechanism that looks like it should help — the `introducer` allowance
(`detect.py:252-256`, `_ONLY_DELIMS` at `:57`) — cannot, because it tests the text *between* two
offsets **within one unit string**, and a heading and its bullet are never in the same string.

---

## 2. Why the obvious fix is forbidden

Making heading context reach its bullets is, mechanically, **document scope with a shorter leash**,
and document scope has been measured wrong four separate times in this engine:

- `rules.yaml:497-499` — *"Document scoped, `"Our founding team has deep expertise."` cancelled the
  genuine `"We require 8 years of experience."` in the NEXT sentence and returned `eligible`."*
- `rules.yaml:222-233` (FINDING 39) — document-scoped, *"Applicants must be US citizens. We also
  employ contractors or permanent residents in other roles."* dropped the gate and returned
  `eligible` with **zero rows** to a non-citizen.
- `rules.yaml:679-684` (D-449) — the document-scoped form of one escape would waive a *separate*
  `8+ years of C++` stated elsewhere; 7 postings depend on it not doing so.
- `detect.py:331-334` (astra finding 4) — document scope let an equivalence escape waive a bar
  **arbitrarily far away**, which is why `abstain_by_adjacent` exists with a one-unit reach.

And the doctrine is stated at `detect.py:4-7`: *"Polarity and a grammatical SUBJECT belong to a
CLAUSE; a qualifying ESCAPE belongs to the POSTING, and one mechanism cannot serve both."*

**Therefore: heading context must be a separately-scoped, hard-bounded channel — never a widening
of an existing suppressor's scope.**

---

## 3. The design

### 3.1 Keep the unit list byte-identical; carry context OUT OF BAND

`split_units` keeps its exact current contract, including absolute offsets
(`detect.py:106-107` — spans are persisted as locators and must stay sliceable against the stored
body). Add a **parallel** structure computed in the same pass:

> For each unit index, the index of the **heading that governs it**, or `None`.

Nothing about unit text, unit count, unit offsets or unit ordering changes. This is what protects
the `:75-86` lock, the 1,076 goldens, and — critically — `abstain_by_adjacent`'s `index + 1`
arithmetic (`detect.py:338-339`), which silently re-aims all eleven patterns that use it if unit
ordering moves. D-540 already measured that stage as job-deleting in principle.

### 3.2 A heading is recognised by an EXISTING vocabulary, not a new one

`tailor/requirement_echo.py` already owns this and it is already tested:
`_QUAL_HEADER` (`:51-56`), `_ANY_HEADER` (`:63`), `_HEADER_GLUE_WORDS` (`:73`),
`_looks_like_header` (`:82-96`), and **`qualifications_span` (`:99-116`)**, which already
implements *"the lines between a heading and the next header-like line or EOF"* — i.e. exactly the
bound this ticket needs. Reuse it; do not write a second heading vocabulary that can drift from the
first. (Engineering default: reuse before new code.)

**But note the coupling:** `requirement_echo.py` is **not** in `engine.digested_modules()`
(`engine.py:58`), so moving shared code between them changes what `ENGINE_VERSION` covers. Extract
the vocabulary into a module that **is** digested, or accept that the tailor lane's behaviour can
now move without a version bump — the second is not acceptable. `tests/unit/test_requirement_echo.py:158-200`
is the coverage that catches a `split_units` contract change; it must stay green.

### 3.3 Inheritance is bounded by THREE rules, all of them hard

1. **Forward only, and only until the next heading.** A heading governs the units after it up to
   the next header-like line or EOF (`qualifications_span`'s existing rule). A later
   `Requirements:` heading **ends** the previous heading's reach. This is the control the ticket
   itself demands.
2. **One level, never transitive.** A heading's context does not pass through a nested heading.
3. **Context may only make a requirement WEAKER or UNDECIDABLE, never stronger.** A heading may
   contribute a hedge (`Nice to have:`), a negation, a jurisdiction, or an explicit `OR` — i.e. it
   may suppress or abstain a bullet's bar. **It may never create a bar, and may never turn an
   abstain into an `unmet`.** This keeps the whole mechanism on the fail-safe side
   (`detect.py:30-33`: *"a mistake is toward zero rows rather than toward a verdict"*), and it means
   the worst case of a heading-detection error is a lead held for review rather than a job deleted.

### 3.4 What is deliberately NOT in scope

- **Tables.** Per the ticket (`:406-407`): zero rows → `uncertain` is already the fail-safe
  direction.
- **`or` as a clause boundary.** `detect.py:49-54` rules it out deliberately: *"`We do not require a
  degree or 5 years of experience.` needs the `not` to reach the second item, and making `or` a
  boundary would fabricate a requirement."* T105c's OR-between-bullets semantics must live in the
  heading channel and **must not** leak back into `_CLAUSE_BOUNDARY`.

---

## 4. Ordering against T152, and it matters

`detect.py` is in `digested_modules()` (`engine.py:58`), so T105 moves `ENGINE_VERSION`; any
`rules.yaml` edit for T105b moves `rules_hash` as well. **Both are D-537's release mechanism.**
Shipping T105 before T152 releases the standing seniority holds again — the third time this session
would have done so. `STANDING-FACTS.md:2509` states the procedural rule: *"Land the catalog PRs
first, then judge, then apply."*

**Recommended order: T153 (judge swap) → T152 (reading identity) → T105.**

---

## 5. Test plan, given that the corpus cannot hold a newline

1. **A new multi-line fixture surface** — the corpus is one-row-per-line and cannot express this
   (§0.2). Either a separate multi-line case list in `tests/unit/test_eligibility_detect.py` beside
   the existing `split_units` tests, or a new module. It must be pinned the way the corpus is, or it
   will drift.
2. **Posting 261677's shape as the headline case**, asserted to clear on its bare-bachelor's arm.
3. **The bound control, which is the one that matters most:** a `Nice to have:` heading followed by
   bullets, followed by a `Requirements:` heading and more bullets — asserting the hedge reaches the
   first group and **does not** reach the second. Without this, the change is the
   `rules.yaml:497-499` incident again.
4. **An inline/list pair asserted to agree.** Only `m0163` (`:285`) and `m0669` (`:791`) are
   discriminating; `m0670`/`m0672` already read `uncertain` inline, so pairing against them proves
   nothing.
5. **A unit-list invariance test:** `split_units` output is byte-identical before and after, over a
   corpus of real bodies. This is the assertion that protects the `:75-86` lock and the goldens.
6. **`tests/unit/test_requirement_echo.py:158-200` must stay green** — it is the second consumer and
   the one that breaks silently.

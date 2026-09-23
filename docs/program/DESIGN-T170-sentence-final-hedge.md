# T170 design note — a years bar its own sentence calls preferred

Branch `exec-t170` (base `ed21c056`). Prototype `c72feaf1` + R7 pin `57d50f91`. Owner rules later;
nothing ships from here. Measurement scripts and outputs are under `.agent/t170_*`.

## 1. The mechanism (verified against `ed21c056`)

- The hedge list `&years_hedges` (`rules.yaml:575`) is a `suppressed_by_unit` suppressor. `detect.py`
  reads it at `detect.py:633-638` with `bounds=_clause_bounds(unit, lo, hi)`, `introducer=True` and
  `aside_owned=True`. `_clause_bounds` (`detect.py:398`) cuts at `_CLAUSE_BOUNDARY` (`detect.py:56`),
  which is `[;:,]|and|but|while|whereas`. The introducer allowance only admits a hedge that comes
  BEFORE the clause and is separated from it by delimiters (`_suppressed`, `detect.py:485`). So a hedge
  after the next `,`, `and` or `but` in the same sentence is invisible to the bar.
- The reported case, `"5+ years of experience, not required but preferred."`, runs as follows:
  - `total_years_minimum` matches `5+ years of experience`. The comma closes the clause, and
    `preferred` sits after `but`.
  - Its twin, `total_years_preferred` (`rules.yaml:928`, window `[^.]{0,25}?` at `:934`), DOES reach
    `preferred`, 19 characters on. But its span then contains `not`, and `_cue_inside`
    (`detect.py:457`) drops any detection hiding a negation cue it does not consume.
  - The required row survives alone: unmet, so `ineligible`.
- **11 required patterns carry the hedge list, not the 6+months named in the handoff.**
  - Carry it: `total_years_minimum`, `total_months_minimum`, `scoped_months_minimum`,
    `range_years_minimum`, `scoped_years_minimum`, `scoped_years_activity`,
    `scoped_range_years_minimum`, `scoped_range_years_activity`, `domain_list_years_minimum`,
    `domain_years_minimum`, `labeled_years_minimum`.
  - Only three have a `preferred` twin: total and range through their own twin, and labeled through
    `total_years_preferred`.
- **Two pre-existing twin defects**, both verdict-neutral:
  - `"5+ years of experience, preferred."` is `ineligible` today, with BOTH rows. The twin reaches
    across the comma, but the comma still bounds the required row's clause.
  - `"3 years of experience, banking experience preferred."` writes a `total_years_preferred` row
    claiming the 3-year bar is preferred. The twin's 25-character window crosses the clause. The
    required row still blocks, so the verdict is right and one row is wrong.

## 2. The rule — a structural test, not a word list (`detect._hedged_tail`)

A hedge in a later clause hedges the BAR if and only if both of these hold:

- **(P)** It is the sentence-final PREDICATE. Only punctuation may follow it, or a negated
  requirement (`, but not required`). Its forms:
  - `[,|–] [is|are|would be|considered] [highly|strongly…] [a|an] HEDGE`;
  - `not required but HEDGE`;
  - a spaced bare `(HEDGE)`.
- **(C)** Everything between the bar's span and the predicate is the bar's own COMPLEMENT: one phrase
  that continues the bar. The complement fails if it does any of the following:
  - **(C1)** opens a new constituent (a leading delimiter or coordinator). The one exception is a span
    that stopped short of its own head noun (`experience`/`years`/`months`): there a comma or `and/or`
    continues the same phrase.
  - **(C2)** contains a clause break: `;` `:` `–` `—`, a spaced dash, brackets, a full stop the
    splitter missed, or a capitalised determiner mid-sentence (a list break lost in extraction).
  - **(C3)** states a second bar (a duration) or a requirement marker (`required`, `must`, `minimum`…).
  - **(C4)** holds an adverbial or exemplifying introducer (`preferably`, `ideally`, `including`,
    `such as`, `e.g.`, `specifically`) or a hedge of its own.
  - **(C5)** opens an adjunct: a comma followed by a preposition or subordinator, or a `with` that is
    neither the head's own preposition nor a gerund's.
  - **(C6)** crosses into a second `experience` head, either in the span or as `experience in|with|of…`.
  - **(C7)** has a comma outside a CLOSED list. A list is closed when an Oxford coordinator follows the
    last comma, or when there are two or more commas and a coordinator in the last item.

The hedge words are the catalog's own `years_hedges`. Every other word in the test belongs to a closed
grammatical class (delimiters, copulas, coordinators, prepositions, determiners), the same kind as
`_CLAUSE_BOUNDARY`. When in doubt, the test keeps the bar required, which is today's behaviour.

**WILL treat as a hedge on the bar.** Real store examples (pv ids), each a test in
`tests/unit/test_eligibility_tail_hedge.py`:

| Shape | Example |
|---|---|
| negated requirement then hedge | `5+ years of experience, not required but preferred.` (T163) |
| comma / dash then predicate | `2-4 years of retirement industry experience, preferred` (313543); `… supplier development – Highly preferred` (93105) |
| open complement, no delimiter | `At least 4 years of experience in fire and life safety system inspection or design preferred.` (255715); `2+ years of experience selling into the U.S. Government and private government contractors preferred` (312636) |
| closed list complement | `2+ years of experience in consulting, investment banking, or private equity a plus` (326910); `3-5 years' experience selling to … remodelers, or other residential trade customers preferred` (247765) |
| copula + intensifier | `15+ years of experience in marketing, …, or revenue operations within a … environment is highly preferred` (279793) |
| bare `(preferred)` after the complement | `5+ years of professional experience in accounting and/or finance (preferred)` (21301) |
| bar stopped short of its head | `2+ years of shipping, receiving, or manufacturing experience preferred.` (191197); `4+ years of experience building and developing software would be preferred.` (324298) |

**WILL NOT treat as a hedge on the bar** (the bar stays required):

| Shape | Example |
|---|---|
| `preferably / ideally in\|for\|with X` | `3+ years of retail management experience, preferably in a specialty or culinary retail environment.` (264199); `…, ideally within a multi-country EMEA environment` (156440) |
| parenthetical `(X preferred)` | `… within the high-tech industry (IT hardware, electronics manufacturing preferred).` (218877) |
| `with X preferred` / `with a focus on X preferred` | `2 years of experience in Identity and Access Management, with a focus on RBAC preferred.` (175490); `…, with financial services experience preferred` (172962) |
| `X experience preferred`, a different noun | `3 years of experience, banking experience preferred.` (243714); `5 years nursing experience required, pediatric and ambulatory experience preferred.` (279521) |
| `N required, M preferred` | `5+ years industry experience in financial services or a related field, 10+ years preferred` (1183) |
| `is a plus` on another noun | `2 years of management experience; fitness/personal training management is a plus!` (336231); `… experience required, and buy-side institution (…) experience is a plus.` (339885) |
| a one-comma new noun phrase | `… in the enterprise software/SaaS space, state and local governments strongly preferred` (327599) |
| the hedge glued to the last item | `… Kafka integration and Pega(Preferred).` (152433) |
| comma + prepositional adjunct | `4-6 years of experience within Financial Services, in a Risk Management, Audit or Compliance role preferred` (130413) |
| a second head / second noun | `…, and experience of 2nd line management preferred` (260655); `8 years of relevant experience and a BA/BS degree preferred.` (136894) |

**Known misses, all in the conservative direction** (the bar stays `ineligible`):
- **One-comma, non-Oxford lists.** `2-4 years Experience with Dynamics 365, Office 365 and Microsoft
  Power Platform preferred` is one of the handoff's own three true cases, and it is missed. The same
  surface carries the `…, state and local governments preferred` false accepts, so the miss is
  deliberate.
- `… including X, preferred` exemplification.
- A bare `not required` with no hedge word.

## 3. Candidate mechanisms

- **(a) Widen the hedge scope to the sentence, for sentence-final hedges only → DROP.** Rejected.
  - Over the pinned population, 2,610 unmet rows (2,353 postings) end their sentence in a predicate
    hedge. Only 530 rows (489 postings) pass the structural test.
  - The ~2,000 rows in between are mostly `…, banking experience preferred.`, `…, with X preferred`,
    `…; Y preferred`. Those are genuine floors that (a) would delete, the worst wrong direction.
  - "Sentence-final" is necessary but nowhere near sufficient. And DROP loses a total/range bar that
    its one-line form carries as a `preferred` row.
- **(b) A sentence-final `preferred` twin per shape → DEMOTE.** Rejected as built.
  - It means about 11 retyped regexes: YAML anchors cannot concatenate.
  - Each required pattern would need a trailing negative lookahead, which backtracking can escape.
  - Scoped, activity and domain bars have no preferred vocabulary. A twin would need a new `implies`
    value, and `resolve._SCOPED_YEARS` would have to learn it, or else a scoped preference resolves
    `met` on total years: a false claim in the evidence chain.
- **(c) RECOMMENDED: hedge equivalence.** One structural test in `detect.py` behind a per-pattern key
  `hedged_by_tail`, so a split-form bar does exactly what its one-line form already does:
  - **DEMOTE** where the pattern has a twin. `hedged_as: total_years_preferred | range_years_preferred`
    on total, range and labeled. The row takes the twin's rule id, `implies`, text and resolver, and
    keeps a span quoting the bar through its hedge. A twin already written at an overlapping span is
    not duplicated.
  - **DROP** everywhere else: the 6 scoped/activity/domain patterns and the 2 months patterns. This is
    exactly what the clause-scoped hedge does to their one-line forms today.
  - No new pattern, no new vocabulary, no resolver change. `catalog.py` refuses a `hedged_as` that
    does not name a preferred pattern of the same family capturing the same groups.
- **Keystone.**
  - No `ABSTAIN` is created or folded. A moved row goes from required-unmet to `preferred` or to
    absent.
  - Every `ineligible` left still carries its quoted span (the span gate suite passes).
  - A DROP that leaves zero rows yields `uncertain` (`_no_evaluable_requirement`), never a clear by
    silence. Measured: 186 movers.
  - A DEMOTE's `eligible` carries the preferred row as its evidence. Measured: 20 movers.
  - An `eligible` reached by a DROP rests on its other rows' own evidence. Measured: 52 movers.
- **The one owner decision this leaves.** Hedged SCOPED bars, in both the one-line and the split form,
  still carry no row. Carrying them as `preferred` would turn those 186 `uncertain` into `eligible`,
  and would move today's one-line forms in the uncertain→eligible direction too. That is a separate
  ticket and needs its own measurement.

## 4. What it costs

- **Hashes.** `detect.py` and `catalog.py` are digested, so `engine_version` moves
  `1+2e27583d3feb → 1+e7a47fbd3e7b`. `rules.yaml` moves `catalog.version`, and so `rules_hash` for the
  live profile moves `1b034dfb… → 48978d1b…`.
- **Consequences.** A full re-evaluation at the next preflight (~277k open postings). Every gate row
  written before goes dead and releases standing-queue holds (D-537). The ledger drain is owed and
  must be decided in writing. The owner's 14-day B8 window restarts.
- **Live checkout.** The primary checkout that writes the store is at `ccb52912` (engine
  `1+c35f7971cd13`), which is behind #415. If T170 lands before the primary is pulled, both bumps
  cost ONE re-evaluation.
- **Pins.**
  - R7 (`tools/generalization/allowlists.py:67`) moves `b5fdef98… → 03bee9ea…`. It is re-pinned in
    `57d50f91`, keyed on the old value.
  - R14 does NOT move: all 1,100 corpus cases pass unchanged, and no corpus row moves.
  - Shipping should add corpus rows for the shapes above, which then moves `CORPUS_PIN` and
    `CORPUS_ROWS` (1100 → N).
  - The pattern count is unchanged (no new patterns), so no pattern-count literal moves.
  - No test pins `engine_version` or `rules_hash`.

## 5. Measured (two arms, one process, pinned population)

- **Population.** 126,854 pinned (`sha256 ec1c9b9f…`), all evaluable. At the end, 2 were superseded by
  run 471, 0 closed, 0 missing.
- **Apparatus.** A0 (the store's own code) reproduces 126,854 of 126,854 stored verdicts.
- **Arm A.** Differs from the store on 2,295 postings (2,063 ineligible→uncertain, 232
  ineligible→eligible). A0 reproduces every one of them, so they come from the base's own #415 batch.
- **Null control.** N vs A: 0 verdict moves, 0 row differences.
- **Movers.** B vs A: **266**, of which 194 ineligible→uncertain and 72 ineligible→eligible. No other
  direction. Only `experience_years` rows change, anywhere. A further 167 postings lose or demote a row
  but stay `ineligible` on another bar.
- **Removed rows, by rule:**

  | Rule | Rows | What happens |
  |---|---|---|
  | `scoped_years_minimum` | 180 | dropped |
  | `scoped_range_years_minimum` | 46 | dropped |
  | `scoped_years_activity` | 16 | dropped |
  | `domain_years_minimum` | 15 | dropped |
  | `total_years_minimum` | 13 | carried as preferred |
  | `scoped_range_years_activity` | 4 | dropped |
  | `domain_list_years_minimum` | 3 | dropped |
  | `labeled_years_minimum` | 2 | carried as preferred |
  | `range_years_minimum` | 1 + 1 | 1 carried; 1 already carried by its own twin (dedupe) |

- **Precision.** A hand-read of 20 random movers finds 16 right, 2 ambiguous and 2 wrong. The wrong
  class is a `with <modifier>` phrase that survived (C5):
  - `8+ years of industry experience with a focus on …` (the scoped span swallowed `with`);
  - `… experience with demonstrated expertise in … preferred`.
  - Across all movers, 18 have a `with` near the bar: 13 right, 3 wrong, 2 ambiguous. A third wrong
    shape there is `… with either Python, and/or Spark as a plus`.
  - **Follow-up before shipping.** Reject `as HEDGE` (an object complement of the nearest noun), and
    reject a `with` followed by a determiner or quality-noun modifier (`with a focus on`, `with a mix
    of`, `with demonstrated expertise`), including where the span ends in `with`. Re-measure after.
- **Software roles (rough title regex).** 14 matched. About 10 are software engineering roles, mostly
  senior; 3 are borderline; 1 is a false match. All 14 moved sentences read right. This is rough, not
  an end-of-line count.

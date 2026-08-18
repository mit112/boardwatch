# Decision log

Append-only. One entry per architectural or program decision, so no decision is re-litigated after a
context reset. Newest last. If a decision is reversed, add a new entry that supersedes it — never edit or
delete the original.

Format: **context** (what forced a choice) · **choice** · **alternatives rejected** · **consequence**.

---

## Index — spans both files

**Do not read either file end to end.** Together they are ~80,000 tokens; `STATE.md` is the read-first
document, this is a reference. Find the entry you want below, then read just its range:

```
sed -n '<start>,<end>p' docs/program/<file>
```

Entries **D-001 … D-076** live in `DECISIONS-ARCHIVE.md`, which is closed. **D-077 onward** live in this
file, and new entries are appended here. Cross-references are by number (`D-028`), never by file, so they
resolve across the split.

Line numbers drift as entries are appended. Confirm one before trusting it:

```
grep -n '^## D-0NN' docs/program/DECISIONS.md docs/program/DECISIONS-ARCHIVE.md
```

**After appending an entry, add its index row and then run `make reindex`.** It reads every heading's
current position and rewrites the line numbers in place, so it corrects drift no matter how far it has gone,
and is a no-op when the index is already right. `make index-check` reports drift without writing, and
`make check` depends on it, so a stale index fails the gate (D-109).

| # | File | Line | Decision |
|---|---|---|---|
| D-001 | DECISIONS-ARCHIVE.md | 15 | Program machinery lives in `docs/program/`, version-controlled |
| D-002 | DECISIONS-ARCHIVE.md | 33 | Output-side phases precede input-side phases |
| D-003 | DECISIONS-ARCHIVE.md | 51 | The 14-day clock is acceptance-only, never a phase gate |
| D-004 | DECISIONS-ARCHIVE.md | 68 | Stub defense: take the metric now, defer the machinery |
| D-005 | DECISIONS-ARCHIVE.md | 87 | Do not rebuild the tailoring architecture |
| D-006 | DECISIONS-ARCHIVE.md | 109 | The PDF cliff is a silent-degrade defect, not a packaging problem |
| D-007 | DECISIONS-ARCHIVE.md | 127 | The work-auth fix is one declared field, not a phase |
| D-008 | DECISIONS-ARCHIVE.md | 146 | Retire the P12 pre-registered parity comparison |
| D-009 | DECISIONS-ARCHIVE.md | 167 | Applied-suppression belongs in P6, and is smaller than described |
| D-010 | DECISIONS-ARCHIVE.md | 185 | Published mechanism vs. personal instance, system wide |
| D-011 | DECISIONS-ARCHIVE.md | 211 | Two personas, and `needs_sponsorship` declared per user |
| D-012 | DECISIONS-ARCHIVE.md | 231 | Verify rather than assume, as a program rule |
| D-013 | DECISIONS-ARCHIVE.md | 253 | Independent review: verdict APPROVE WITH CHANGES, amendments adopted |
| D-014 | DECISIONS-ARCHIVE.md | 291 | `main` was red; program docs are subject to the generalization checker |
| D-015 | DECISIONS-ARCHIVE.md | 314 | Migration `run_attribution`: nullable, unnamed inline FK, evaluations + artifacts only |
| D-016 | DECISIONS-ARCHIVE.md | 350 | `run_id` means a pipeline run, and P0 introduces it |
| D-017 | DECISIONS-ARCHIVE.md | 386 | second independent review; STATE's own header was the defect |
| D-018 | DECISIONS-ARCHIVE.md | 428 | abstain-rate scope, and the `IN`-clause limit is a repo-wide debt, not this metric's |
| D-019 | DECISIONS-ARCHIVE.md | 462 | `run_id` is never NULL on a row written after attribution exists |
| D-020 | DECISIONS-ARCHIVE.md | 514 | the scan stage creates the run row; the pipeline finishes it |
| D-021 | DECISIONS-ARCHIVE.md | 587 | second review: the exit-code fix had over-corrected into bar metric B5 |
| D-022 | DECISIONS-ARCHIVE.md | 642 | the funnel's head is the open-posting corpus, not scan throughput |
| D-023 | DECISIONS-ARCHIVE.md | 661 | a stage reports `None` when unmeasured, and says when its balance is bookkeeping |
| D-024 | DECISIONS-ARCHIVE.md | 700 | the artifact is written from the `finally`, and never fails the run |
| D-025 | DECISIONS-ARCHIVE.md | 718 | mutation testing has two failure modes that both report a false PASS |
| D-026 | DECISIONS-ARCHIVE.md | 747 | `assisted` is as unmeasurable as `unique`, and both report `None` |
| D-027 | DECISIONS-ARCHIVE.md | 781 | the shortlist stage becomes evidence, by rooting it at what the ranker considered |
| D-028 | DECISIONS-ARCHIVE.md | 813 | only one per-source total was worth reconciling, and the first attempt could not fail |
| D-029 | DECISIONS-ARCHIVE.md | 870 | `runs.status` is a closed catalog whose DEFAULT carries the meaning |
| D-030 | DECISIONS-ARCHIVE.md | 918 | the run manifest ships two hashes, closing the profile-row gap rather than only noting it |
| D-031 | DECISIONS-ARCHIVE.md | 965 | `boardwatch verify` is a standalone DB↔artifact reconciliation sweep, supplementing Gate P0 rather than re-anchoring it |
| D-032 | DECISIONS-ARCHIVE.md | 1069 | P1a ships a hard PDF gate as impure-runner/pure-policy, splits P1b out, and closes D-006's silent degrade |
| D-033 | DECISIONS-ARCHIVE.md | 1175 | Tier-B reword provenance: a deterministic allowlist, fail-closed to Tier-A, counted separately from B4 |
| D-034 | DECISIONS-ARCHIVE.md | 1261 | `needs_sponsorship` is an orthogonal bit on the work-auth fact, and it only decides sponsorship rules |
| D-035 | DECISIONS-ARCHIVE.md | 1298 | `work_auth` ships `default_policy: blocker`; the other five families stay `preference` |
| D-036 | DECISIONS-ARCHIVE.md | 1364 | `eligible` with zero fired requirements renders distinctly from `eligible` with cleared ones |
| D-037 | DECISIONS-ARCHIVE.md | 1458 | the fatal-vs-non-fatal contract is written, and the outage predicate is one function |
| D-038 | DECISIONS-ARCHIVE.md | 1516 | the run-scoped morning artifact, and freshness from run_id + a terminal row + the funnel's own reconciliation |
| D-039 | DECISIONS-ARCHIVE.md | 1611 | run-integrity guards: cohort completeness by ID set, zero-output provably-right via run_id attribution, filesystem-truth reusing slice-4 |
| D-040 | DECISIONS-ARCHIVE.md | 1714 | LLM transient-error retry-with-backoff, ported from politeness into a shared adapter helper |
| D-041 | DECISIONS-ARCHIVE.md | 1793 | the SQLite/WAL concurrency stance is now documented (P3 item 8, doc half) |
| D-042 | DECISIONS-ARCHIVE.md | 1815 | the tailor-level idempotence short-circuit is DECLINED (YAGNI); the response cache already covers it |
| D-043 | DECISIONS-ARCHIVE.md | 1839 | the scan lock now notifies loudly with the blocking pid; the sidecar is message-only, never a lock authority |
| D-044 | DECISIONS-ARCHIVE.md | 1884 | P3 slice 5b: KEEP today's Tier-A downgrade on provider/quota error; decline the "never downgrade" inversion |
| D-045 | DECISIONS-ARCHIVE.md | 1913 | P3 slice 2: DECLINE custom stale-reclaim (unsound AND unnecessary); the loud-notify shipped, the reaper stays fresh-context |
| D-046 | DECISIONS-ARCHIVE.md | 1940 | P3 slice 2: age-based run REAPER (no schema); this CLOSES the last non-Mit / non-Docker P3 build item |
| D-047 | DECISIONS-ARCHIVE.md | 1979 | Proceed with P4 (craft rubric) ahead of Gate P3; Gate P3 is blocked only by Docker+ops, not by any P4 build dependency |
| D-048 | DECISIONS-ARCHIVE.md | 2005 | P4 item 1: deterministic overmatch (verbatim-lift + unusual-caps) guard SHIPPED; first P4 slice |
| D-049 | DECISIONS-ARCHIVE.md | 2037 | P4 item 2: consolidate the canonical-vocab seed; DECLINE the per-field selector (YAGNI) |
| D-050 | DECISIONS-ARCHIVE.md | 2068 | P4 item 3a: banned-register + buzzword-density + verb-diversity craft guards SHIPPED |
| D-051 | DECISIONS-ARCHIVE.md | 2103 | P4 item 3b: requirement-echo detector SHIPPED; item 3 COMPLETE |
| D-052 | DECISIONS-ARCHIVE.md | 2142 | P4 item 4: DEFER the de-senioritizer into item 7 (don't build inert dead code); do items 5–6 first |
| D-053 | DECISIONS-ARCHIVE.md | 2169 | P4 item 5a: per-lead layout gate SHIPPED (bullet length/count, escaping round-trip, template-artifact) |
| D-054 | DECISIONS-ARCHIVE.md | 2194 | Personas / field-specific knowledge are GATHERED per-user at onboarding, never authored by us (we ship tech expertise only) |
| D-055 | DECISIONS-ARCHIVE.md | 2226 | Opus 5 checkpoint reviews of the session's big pieces (reaper + P4 guard gauntlet); fix-forwards |
| D-056 | DECISIONS-ARCHIVE.md | 2259 | P4 item 5b: run-once fatal master-résumé validation at load; item 5 COMPLETE |
| D-057 | DECISIONS-ARCHIVE.md | 2285 | Résumé TAILORING is fundamentally wrong; a dedicated fix session precedes Gate 3 (and, recommended, the remaining P4 polish) |
| D-058 | DECISIONS-ARCHIVE.md | 2309 | Résumé render engine = tectonic compiling the user's actual LaTeX template (Typst decision reversed) |
| D-059 | DECISIONS-ARCHIVE.md | 2352 | Increment-1 plan cleared for execution after a SECOND fresh-context re-review (both REWORK, all folded in) |
| D-060 | DECISIONS-ARCHIVE.md | 2399 | Increment 1 (LaTeX render substrate) executed and shipped to `main`; the Typst→tectonic swap is complete |
| D-061 | DECISIONS-ARCHIVE.md | 2467 | P4 item 6 (keyword-coverage measurement) shipped to `main` |
| D-062 | DECISIONS-ARCHIVE.md | 2501 | Persona (P4 item 7) is a résumé-presentation lens, not an eligibility variant; the de-senioritizer is made live via JD-title stripping |
| D-063 | DECISIONS-ARCHIVE.md | 2543 | P4 item 7 (persona registry + live de-senioritizer) shipped to `main`; P4 build complete |
| D-066 | DECISIONS-ARCHIVE.md | 2589 | P5 answer-key is AI-oracle + human-audit-a-sample via a job-apps judge port (its own session) |
| D-065 | DECISIONS-ARCHIVE.md | 2623 | P5b B0 scaffolding: reference all-blocker policy + precision scorer + labeling worksheet |
| D-064 | DECISIONS-ARCHIVE.md | 2672 | P5a: three verdict-SAFE eligibility-integrity slices shipped to `main` |
| D-067 | DECISIONS-ARCHIVE.md | 2715 | P5 answer-key oracle judge: agent-lane port + deferred (but drained) human audit |
| D-068 | DECISIONS-ARCHIVE.md | 2760 | P5b answer-key oracle judge SHIPPED to `main` (agent lane, all 7 tasks) |
| D-069 | DECISIONS-ARCHIVE.md | 2803 | First Gate-P5 measurement: precision 94% (16/17), one FP = a disjunctive-experience over-fire |
| D-070 | DECISIONS-ARCHIVE.md | 2845 | Audit via historic data (Mit declined manual audit); B1–B4 unblocked at 28% coverage |
| D-071 | DECISIONS-ARCHIVE.md | 2900 | Two-stage eligibility gate agreed for a fresh session; model-agnostic, agent-lane cheap gate |
| D-072 | DECISIONS-ARCHIVE.md | 2927 | Model-tier benchmark for the eligibility judge + published guidance (research, next sessions) |
| D-073 | DECISIONS-ARCHIVE.md | 2957 | Disjunctive experience-years fix SHIPPED; Gate P5 MET (precision 100%) |
| D-074 | DECISIONS-ARCHIVE.md | 3009 | Final eligibility gate lane SHIPPED (persistent, agent-lane, fail-open); Gate P5 unchanged |
| D-075 | DECISIONS-ARCHIVE.md | 3084 | Gate P2 reconciled: three individually-correct verdicts (may coincide); ≥3-field mechanism via fixtures |
| D-076 | DECISIONS-ARCHIVE.md | 3153 | P2 item 4's final whole-branch review: what it caught, and four rulings it forced |
| D-077 | DECISIONS.md | 268 | P6 Slice 1: the design is settled and the plan is written; no code exists yet |
| D-078 | DECISIONS.md | 358 | P6 Slice 1: the plan's test fixtures are now real; eleven defects, all found by running code |
| D-079 | DECISIONS.md | 447 | P6 Slice 1 annotates only; `postings.job_id` is not mutated |
| D-080 | DECISIONS.md | 461 | `content_hash` alone may never suppress |
| D-081 | DECISIONS.md | 475 | `exact_quad` is the sole suppressing kind, and its yield is stated honestly |
| D-082 | DECISIONS.md | 493 | `cross_host` ships annotate-only, reversing an earlier draft |
| D-083 | DECISIONS.md | 514 | No location evidence ⇒ no location-bearing identity, never a `"[]"` sentinel |
| D-084 | DECISIONS.md | 529 | Three host classes, not two; matching is exact-or-dot-suffix |
| D-085 | DECISIONS.md | 543 | Allowlist URL normalization, not a denylist |
| D-086 | DECISIONS.md | 557 | Survivor election never consults score; `posting_id` is a load-bearing tiebreak |
| D-087 | DECISIONS.md | 572 | Instrumentation is completeness-gated, not existence-gated |
| D-088 | DECISIONS.md | 586 | `assisted` stays `None` in this slice |
| D-089 | DECISIONS.md | 601 | Identities are upserted on every observation; a kind that stops being produced is deleted |
| D-090 | DECISIONS.md | 618 | The ranker is completeness-gated for reproducibility, not safety |
| D-091 | DECISIONS.md | 636 | The recount recomputes in Python, and claims staleness only |
| D-092 | DECISIONS.md | 651 | Identities are backfilled by an explicit command, not by the migration |
| D-093 | DECISIONS.md | 665 | Slice 1 does NOT meet Gate P6, and makes only one of its four clauses measurable |
| D-094 | DECISIONS.md | 679 | P6 Slice 1 BUILT (unattended run): five more plan defects, three of them tests that could not fail |
| D-095 | DECISIONS.md | 807 | P6 Slice 1 reviewed by three independent reviewers; fourteen findings fixed, two rejected |
| D-096 | DECISIONS.md | 872 | The C++/C# fix folds punctuation into words; it does NOT add a raw-title comparison |
| D-097 | DECISIONS.md | 916 | `_verify_quad` rejected nothing on the live corpus; "string-verified" is not precision evidence |
| D-098 | DECISIONS.md | 945 | Suppression reports when it is OFF; wiring backfill into the pipeline is Slice 2 |
| D-099 | DECISIONS.md | 981 | Gate batching stays allowed; the per-task fast-check set must include the schema guards |
| D-100 | DECISIONS.md | 1007 | P6 Slice 1 merged to `main`; Gate P6 clause 3 is MET, not merely measurable |
| D-101 | DECISIONS.md | 1039 | Gate P6 clause 4 is MET: 20/20 sampled suppressions are genuine duplicates |
| D-102 | DECISIONS.md | 1069 | D-072 (model-tier benchmark) is deferred indefinitely |
| D-103 | DECISIONS.md | 1091 | P6 Slice 2: the ledger is a current-state row per job, `seen` suppresses on a TTL, and the policy stamp never auto-reopens |
| D-104 | DECISIONS.md | 1163 | Job regrouping: the survivor's job wins, and a tracked group is refused whole |
| D-105 | DECISIONS.md | 1206 | Identity writes move into the scan path, closing D-098 — and D-098's cost argument did not apply |
| D-106 | DECISIONS.md | 1237 | Two consequences the build forced: what earns a permanent `skipped`, and the zero-output guard |
| D-107 | DECISIONS.md | 1263 | P6 Slice 2 BUILT and verified on real data; `cross_host` dereference deferred by measured absence |
| D-108 | DECISIONS.md | 1312 | The decision log and the metrics log are archive-split; the reading protocol moves into the index |
| D-109 | DECISIONS.md | 1371 | Index drift fails the gate, and the fixer lives in `tools/` |
| D-110 | DECISIONS.md | 1449 | The Slice 2 review: only a caller that delivers a lead may consume the queue |
| D-111 | DECISIONS.md | 1566 | P6 Slice 3: applied-state suppression, and liveness sized to what the corpus actually is |
| D-112 | DECISIONS.md | 1735 | 0.3.0 is cut, the changelog gets ONE triple, and the tag is the owner's to push |
| D-113 | DECISIONS.md | 1839 | The Slice 3 external review: a followed redirect can forge a gone-status |
| D-114 | DECISIONS.md | 1927 | CI installs tectonic and pdfinfo on all three OSes; skipping the gate was refused |
| D-115 | DECISIONS.md | 1995 | Gate A of the career-profile bundle: 9 of 19 slices, and a rule for checks that cannot fire |
| D-116 | DECISIONS.md | 2077 | A docs-only commit owes the two fast gates, not the full suite; the tectonic pin gets a detector |
| D-117 | DECISIONS.md | 2124 | 0.3.0's tag moves rather than 0.3.1 being cut; gitleaks fixed by cleaning bytes, not allowlisting |
| D-118 | DECISIONS.md | 2174 | Gate A slice T10: effectiveness derived in one place, and two more §20.4 rows with no check |
| D-119 | DECISIONS.md | 2271 | 0.3.0 is PUBLISHED: the tag moved onto a CI-green commit, and ships two known BLOCKERs deliberately |
| D-120 | DECISIONS.md | 2339 | Gate A slice T12: the résumé emission order is fixed, and three more checks that cannot fire |
| D-121 | DECISIONS.md | 2422 | The T12 review: a green gate and a perfect mutation score hid five BLOCKING defects |
| D-122 | DECISIONS.md | 2483 | The T12 re-review: one defect the fix created, two contracts never enforced, and a decline that was wrong |
| D-123 | DECISIONS.md | 2606 | A recurring trigger holding a one-shot prompt re-fires a task that already shipped |
| D-124 | DECISIONS.md | 2651 | The third T12 review: the locator grammar keeps failing because it restates the emitter instead of deriving from it |
| D-125 | DECISIONS.md | 2716 | The T12 round-three fix, and two more reviews of it: a forbidden segment is escaped, never refused |
| D-126 | DECISIONS.md | 2848 | T12's review loop is CLOSED, with a stated exit criterion |
| D-127 | DECISIONS.md | 2904 | Gate A slices T13 and T14: an approval bound to nothing, and the first code that WRITES a bundle |
| D-128 | DECISIONS.md | 3025 | Gate A T14 round 2, T15 and T17: what three green suites could not see |
| D-129 | DECISIONS.md | 3214 | The two Gate A design departures are RULED: the design text was wrong, not the code |
| D-130 | DECISIONS.md | 3279 | Correcting D-128 and D-129: what the fix rounds actually established, and what the rebase actually deletes |
| D-131 | DECISIONS.md | 3354 | The T14/T15 fix-round review's findings are fixed: a merge short-cut that skipped the append-only rule, and five residues |
| D-132 | DECISIONS.md | 3489 | Gate A slice T16 reviewed by three lenses: the highest-risk slice, and the one defect two of them found separately |
| D-133 | DECISIONS.md | 3566 | Correcting D-130 and D-131: what is actually pushed, and five statements a docs review caught in this session's own records |
| D-134 | DECISIONS.md | 3638 | A finding's tier is a property of the operation, not of the code alone |
| D-135 | DECISIONS.md | 3695 | The Gate A integration gate is green on all nineteen slices, and the 03:10 job misfired a second time |
| D-136 | DECISIONS.md | 3768 | Gate A slices T18 and T19: two lenses, a ten-commit fix round, and an integration merge where two green branches wrote one rule twice |
| D-137 | DECISIONS.md | 3884 | Gate A's review loop CLOSES at round five, and a two-document write is named rather than made atomic |
| D-138 | DECISIONS.md | 3969 | A missing bundle root is its own fact, and `inventory` reporting it as clean was the defect |
| D-139 | DECISIONS.md | 4024 | `STATE.md` splits its standing facts out, because a read-first file at twice its stated length is read past |
| D-140 | DECISIONS.md | 4072 | D-116's conclusion survives, its premise does not: two tests do read the real `docs/` tree |
| D-141 | DECISIONS.md | 4120 | The third site of the blocking-`open()` class is closed, at the layout boundary |
| D-142 | DECISIONS.md | 4163 | D-138 delivered eight of twelve commands, and said twelve. The review that caught it, and what the surviving mutation cost |
| D-143 | DECISIONS.md | 4232 | `add-evidence` writes the back-citation, closing Gate A's last open question |
| D-144 | DECISIONS.md | 4315 | Grounding reads `supports` alone; citing a source is not being backed by it |
| D-145 | DECISIONS.md | 4373 | The Gate A subsystem never ran on Windows, and one `write_text` hid it |
| D-146 | DECISIONS.md | 4443 | LLM lane-death is one typed error, classified at the raise site, latched per invocation — scoped to the two lanes that call out |
| D-147 | DECISIONS.md | 4616 | Slice 5 merges as-is: four known residuals, recorded rather than fixed |
| D-148 | DECISIONS.md | 4701 | D-147's R1 closed: one flag drives the tailor lane's ledger row and its exit code |
| D-149 | DECISIONS.md | 4787 | The `STATE.md` trim is BLOCKED: three Gate A records disagree with the code or with each other |
| D-150 | DECISIONS.md | 4874 | The suite runs across worker processes; `-n auto` lives at the call sites, not in `addopts` |
| D-151 | DECISIONS.md | 4983 | Windows leaves the per-push path for a nightly schedule; it is not dropped |
| D-152 | DECISIONS.md | 5048 | Retraction: the archived CGPA claim is inverted; job-apps was never the stale copy |
| D-153 | DECISIONS.md | 5087 | A rich table's width can ignore `COLUMNS`, so terminal env is pinned for the whole suite |
| D-154 | DECISIONS.md | 5174 | `eligibility_inputs` gains an identity index; `top`'s pending anti-join cost 141 s per run |
| D-155 | DECISIONS.md | 5238 | The program reorients onto the bundle-to-résumé path; `resume.yaml` becomes an import source, not an artifact to hand-fix |
| D-156 | DECISIONS.md | 5326 | v1 projection is not authoritative for header, education or summary, because the renderer never reads them |
| D-157 | DECISIONS.md | 5421 | Corrections that unblock D-149: the manifest write order, and Windows closed by CI |
| D-158 | DECISIONS.md | 5505 | The projection scorer is chosen by measurement, because two design rounds picked two scorers and a probe falsified both |
| D-159 | DECISIONS.md | 5593 | `COLUMNS` is baked into a `Console` at import, so three width-controlling tests never controlled anything |
| D-160 | DECISIONS.md | 5698 | Preflighting a thrice-reviewed spec still found four false claims, and the plan argues from the preflight |
| D-161 | DECISIONS.md | 5802 | A third import wall guards the bundle serializer, and projection digests through the YAML writer instead |
| D-162 | DECISIONS.md | 5876 | A fourth import wall guards the CLI command module against the store, found only by tripping it |
| D-163 | DECISIONS.md | 5914 | The plan's four candidate scorers are two behavioural families, and none survives both probes |
| D-164 | DECISIONS.md | 5959 | Where the closed `ProjectionIssue` catalog is extended, and where a foreign error may escape |
| D-165 | DECISIONS.md | 6005 | A consent control gets one definition, because the rationale for copying it was false |
| D-166 | DECISIONS.md | 6046 | Projection maps its issues onto the bundle's catalog at the boundary, rather than inverting the dependency |
| D-167 | DECISIONS.md | 6081 | A projection approval binds the bundle it was made against, and the check is unconditional |
| D-168 | DECISIONS.md | 6132 | Stage 2's scorer is a required parameter with no default, because the plan is forbidden to pick one |
| D-169 | DECISIONS.md | 6166 | A plan can ship an artifact no task consumes, and only a whole-branch lens sees it |
| D-170 | DECISIONS.md | 6210 | `profile-bundle import` writes the ledger and nothing else, and derives no disposition |
| D-171 | DECISIONS.md | 6284 | A CI-only failure was a lazy-import race in typer, not an OS difference and not a regression |
| D-172 | DECISIONS.md | 6368 | Gate B is met at a promoted revision, and the extraction mapping lives inside the bundle |
| D-173 | DECISIONS.md | 6446 | Gate B gets a mechanical predicate, the drain gets a digest-bound carrier, and the mapping's carrier is questioned |
| D-174 | DECISIONS.md | 6543 | The extraction mapping's carrier is `policy/extraction-mappings.yaml`, not a `SourceSpec` field |
| D-175 | DECISIONS.md | 6579 | Review round 3 outcome: 7 findings, all accepted; the schema bump needs a real migrator, not a raw-v1 loader |
| D-176 | DECISIONS.md | 6625 | Review round 4 outcome: 4 blocking findings accepted; the kind→subject→predicate relation gets modelled once |
| D-177 | DECISIONS.md | 6670 | Review round 5: the rule interface is under-designed; revision 7 redesigns it completely, not by patch |
| D-178 | DECISIONS.md | 6724 | Stop the spec-review loop as the gate to building; de-risk the rule interface with a thin TDD slice |
| D-179 | DECISIONS.md | 6754 | The Task-1 predicate audit: seed the audited starter catalog, and roster three dead verification bases |
| D-180 | DECISIONS.md | 6788 | The skill-id derivation scheme, and the two easy extraction buckets proven in code |
| D-181 | DECISIONS.md | 6812 | Gate B extraction ships end to end: interpreter, schema v2, `extract`, and 78/81 records reach `imported` |
| D-182 | DECISIONS.md | 6863 | The §6.8 promotion slice: candidates become entities, facts, and grounded skills — deterministic, owner-mediated, one-shot |
| D-183 | DECISIONS.md | 6909 | Two owed Gate B gates ship: §5.2 invariant 4 reachability, and the drain reconciliation wired at the completeness tier, not validity |
| D-184 | DECISIONS.md | 6960 | The Gate B merge review: the catalog check was never wired, and is now the gate D-181 said it was |
| D-185 | DECISIONS.md | 7034 | boardwatch's first promoted revision: the bundle becomes a real résumé source, and Gate B's remaining nine are evidence, not code |
| D-186 | DECISIONS.md | 7091 | Revision 2: the skills surface, D-185's "not reachable" claim is retracted, and the bootstrap draft is a one-time dead end |
| D-187 | DECISIONS.md | 7131 | Projection `skill_groups` are optional and synthesized from the bundle catalog when omitted |
| D-188 | DECISIONS.md | 7170 | An entry's bullets can come from facts, not only claims: `bullet_predicates` |
| D-189 | DECISIONS.md | 7210 | The master is a RESERVOIR sourced from the wiki, and `project.contribution` is widened to owner_attested in Mit's bundle |
| D-190 | DECISIONS.md | 7252 | Content edits are incremental: `edit-fact` files a correction as an edge, and no rebuild is needed |
| D-191 | DECISIONS.md | 7385 | Repository evidence grounds the project bullets, and the verification basis deliberately does not change |
| D-192 | DECISIONS.md | 7456 | `exclude-record` ships, and both documents re-derived from one ledger are guarded |
| D-193 | DECISIONS.md | 7512 | Task 20's matrix is recorded unlabeled, and Stage 2 is blocked by a pinning decision underneath it |
| D-194 | DECISIONS.md | 7590 | `approve_source_scope` binds the spelling already on disk, and the helper is the side that moves |
| D-195 | DECISIONS.md | 7659 | The pinned set is the three fixed jobs, and the one-page ceiling is 16 bullets |
| D-196 | DECISIONS.md | 7715 | Gate B's three undispositioned import records are excluded as `owner_excluded`, 7 blockers → 4 |
| D-197 | DECISIONS.md | 7749 | Task 20's matrix is owner-labeled, unblocking scorer selection (Task 23) |
| D-198 | DECISIONS.md | 7787 | Task 23: `mean_per_bullet` is adopted as the CLI scorer default, threshold stays `Decimal(0)` |
| D-199 | DECISIONS.md | 7849 | `resume project`'s manifest maps bullets by their own id, not by re-parsing the declaration's `claims` |
| D-200 | DECISIONS.md | 7909 | Résumé heading formatting is declaration-driven; clickable project links are an optional code feature |
| D-201 | DECISIONS.md | 7958 | `employment.organization` is owner-attestable; the four org facts are resolved by a scoped owner attestation — Gate B 4 → 0 |
| D-202 | DECISIONS.md | 8005 | The skill-id slug collision (D-184 finding 3) is fixed: promotion refuses a grounded id built from more than one item, rather than silently merging |
| D-203 | DECISIONS.md | 8054 | The other two promotion slug-collision sites (entity_id, category_id) are closed the same way; a fourth (fact_id) is found open, not closed |
| D-204 | DECISIONS.md | 8129 | A missing `pdfinfo` is a run-level fatal, not a laundered `COMPILE_FAILED`; the tool identity travels as typed data |
| D-205 | DECISIONS.md | 8197 | The fourth promotion slug-collision site (`fact_id`) is refused; the guard sits on the derived id, not on each builder |
| D-206 | DECISIONS.md | 8256 | CSV export to stdout is written UTF-8 through a locally-wrapped stream |
| D-207 | DECISIONS.md | 8283 | The `STATE.md` trim executes D-149, and the fact-check that gated it corrects six stale figures |
| D-208 | DECISIONS.md | 8359 | Dates render at month precision, and a projection may declare a two-fact range so an open-ended project is renderable at all |
| D-209 | DECISIONS.md | 8440 | A fact that is simply wrong is retired by flipping its verification state to `rejected`; there is no delete, and `year_month` has no null form |
| D-210 | DECISIONS.md | 8477 | A skill listed under two skill groups is refused, because a skill has exactly one category and arrival order must not pick it |
| D-211 | DECISIONS.md | 8538 | Correction: Windows runs only on the scheduled CI build, and that build has been red since 2026-08-14 |
| D-212 | DECISIONS.md | 8597 | Windows is a best-effort platform, the nightly gets a consumer, and D-211's "not a flake" is corrected |
| D-213 | DECISIONS.md | 8678 | Résumé bullets state what was built with metrics, never a story; and a bullet is parked by surface, not by an extra fact |
| D-214 | DECISIONS.md | 8756 | Hookrail's bullets: a merged perf-plus-chaos claim, a keyword measured back in after a length trim, and a correct-but-unwanted bullet parked |
| D-215 | DECISIONS.md | 8827 | StreakSync ships two bullets; a control test is only evidence about the corpus it ran against, so a historical absence needs the pickaxe; authorship is verified per entity |
| D-216 | DECISIONS.md | 8885 | SAKEC's bullets are ruled and worded but NOT promoted; a private repo makes a disk sweep's negative worthless; and keywords are chosen by diffing the résumé's own Skills section |
| D-217 | DECISIONS.md | 8993 | Crop-RF's numbers all verify against the paper, but its award count, its host and its authorship do not; and `grep` here silently honours `.gitignore` |
| D-218 | DECISIONS.md | 9147 | Nakshatra's bullets are rewritten; both percentages stay, as client-supplied estimates |
| D-219 | DECISIONS.md | 9227 | The one-page budget is a character budget, not a bullet count; D-195's two-candidate ceiling is retired |
| D-220 | DECISIONS.md | 9281 | NIO's bullets drop the SwiftUI and SensorKit-authorship claims and add the VPN lifecycle work; the owner attests SensorKit shipped |
| D-221 | DECISIONS.md | 9372 | Saayam keeps its entry with one role-scoped bullet, because "role + org + dates only" is unrepresentable today |
| D-222 | DECISIONS.md | 9454 | Correction: D-212 marked two of the three tests exercising the Windows stale-lock race, and the third turned the nightly red |
| D-223 | DECISIONS.md | 9516 | Correction: D-222's own census was short one, and instance 4 is marked by mechanism rather than observation |
| D-224 | DECISIONS.md | 9594 | The Windows stale-lock race is fixed by re-asking the OS for a bounded window; the four `xfail` markers come off together |
| D-225 | DECISIONS.md | 9784 | The daily pipeline gets projection behind an opt-in `--project`, fail-closed before any lead earns a disposition |
| D-226 | DECISIONS.md | 9950 | A bullet-less entry is legal only when it is DECLARED; a bullet source that resolves to nothing stays fatal |
| D-227 | DECISIONS.md | 10083 | The scan lock gets the same reclaim window as the bundle lock, and the shared constant moves to `core/lock_reclaim.py` |
| D-228 | DECISIONS.md | 10189 | Fixture drift is three separate gates, and the staleness one enforces a review deadline rather than freshness |

---

## D-077 — P6 Slice 1: the design is settled and the plan is written; no code exists yet

**2026-08-09/10 · P6 Liveness + dedup, design + planning session. Stopped at Mit's request before
execution.** Repo unchanged except this file and `STATE.md`. The spec and the 9-task TDD plan live at
`.superpowers/sdd/2026-08-09-p6-liveness-dedup/` (gitignored — hence this entry, which is the durable
record of what was decided); `HANDOFF.md` there states where to resume.

**Scope.** P6 is split into three slices. **Slice 1** = PROGRAM items 1–3 (posting-identity table,
allowlist URL normalization, cross-host identity) plus the funnel's measured `unique` counter.
**Slice 2** = item 4's durable ledger with its drain, job regrouping, and cross-host dereference.
**Slice 3** = item 5 (applied-state suppression) and item 6 (liveness). Slice 1 **does not meet Gate
P6** and makes only one of its four clauses measurable; that is stated in the spec rather than
discovered later.

**The decisions, so they are never re-litigated.** Section references are to `design.md`.

- Slice 1 **annotates only**; `postings.job_id` is not mutated until Slice 2, because
  `applications.job_id` is the tracking key (§1.3).
- **`content_hash` alone may never suppress.** The live corpus contains 727 groups it would wrongly
  collapse (§2).
- **`exact_quad` is the sole suppressing kind**, and what it suppresses is stated honestly: 131 groups
  / 168 surplus rows / 0.72% of the live population, and the sampled groups are
  same-role-different-requisition pairs with byte-identical descriptions, not re-postings. The claim
  defended is "one application decision", not "the same requisition" (§2).
- **`cross_host` ships annotate-only** (`suppresses=False`), reversing an earlier draft that had
  assumed otherwise: an unanswered flag is not consent, `core/identity.py:3` already records that
  cross-ID heuristics may only annotate, PROGRAM item 1 says only exact identities may suppress, and a
  concrete false-suppression counterexample exists. Re-entry path: it becomes suppressible once an
  aggregator can be dereferenced to exact requisition evidence (§3.1).
- **A posting with no location evidence emits no location-bearing identity at all** —
  `normalized_locations` returns `None`, never `"[]"`. A `"[]"` sentinel is a silent collapse that
  neither string-verify nor the recount can detect, because both sides compare equal. Measured cost: 7
  rows of 23,455 (§2.1).
- Three host classes, not two. `unknown` is the default and never suppresses; host matching is
  exact-or-dot-suffix, **never substring** (§3).
- **Allowlist** URL normalization, not a denylist — direction chosen by which failure is detectable
  (§4.1), plus string-verify on hash hit (§4.2).
- **Survivor election never consults score.** `posting_id` is a load-bearing tiebreak because
  `first_seen_at` is second-resolution (§5.1). The drain (`--include-duplicates`) ships in the same
  change as the quarantine, per the standing invariant (§5.2).
- **Instrumentation is completeness-gated, not existence-gated:** `unique` is `None` unless *every*
  open posting has a current-version identity (§2.2). The ranker is completeness-gated too, but for a
  different reason — partial coverage cannot over-suppress, since an uncovered posting joins no group;
  it is that survivor election over a subset is backfill-order-dependent, and Gate P6 requires
  re-deriving 20 sampled suppressions from the data.
- **`assisted` stays `None` in this slice.** Nothing here can produce a non-zero value, and reporting
  the structurally-true `0` would assert a measurement that was never taken (§6.2) — the D-022/D-023
  rule.
- Identities are recomputed on **every observation** and upserted when any key component changed,
  because `scan/apply.py:153-170` refreshes title/locations *outside* the `content_hash` revision gate
  at `:124` (§2.3). A kind that stops being produced is **deleted**, not orphaned — an abandoned
  `exact_quad` row would keep suppressing for a posting that no longer earns one.
- The recount recomputes normalizers in Python rather than re-grouping the same table (§6.3), per
  D-028 — and its claim is narrowed to **staleness**, not normalizer correctness, since both paths
  share the normalizers.
- Identities are backfilled by an **explicit command, not by the migration** (§7).

**Three defects were found in the plan by running its code against the engine, not by reading it.**
Two are fixed in `plan.md`; the third is open and is the next action.

1. **FIXED — the one that would have disabled dedup silently.** `IdentityInputs.locations` was typed
   `str | None` and `normalized_locations` called `json.loads` on it. But `postings.locations_json` is
   a SQLAlchemy `JSON` column (`store/tables.py:67`), so a SELECT returns a *deserialized list*.
   `str(['Dublin','Madrid'])` is a Python repr, not JSON: the parse raises, the `except` swallows it,
   the function returns `None`, no `exact_quad` is ever emitted, and **dedup suppresses nothing,
   forever, with the entire suite green** — because the unit tests hand it a valid JSON string. Fixed
   by typing the field as what the column yields, moving the sole "is this really a list?" judgement to
   the loader boundary (`load_identity_inputs`), deleting the parse, and adding a round-trip test that
   goes red under the original shape. This is the CLAUDE.md fixture rule and D-028 applied to a *type*
   rather than a number.
2. **FIXED — a closed connection.** The dedup block reused `rank_open_postings`'s `conn`, whose `with`
   opens at `cli/top_cmd.py:113` and **closes at `:157`**; scoring and the visible/hidden loop both run
   with no connection open, so it would have raised `ResourceClosedError` on the first real run. It now
   opens its own, and passes `eligible_ids` so it does not pull 23,455 `body_text` rows to deduplicate
   a few thousand leads.
3. **OPEN — every pytest fixture Tasks 6/7/8 name is invented.** `tests/unit/conftest.py` defines
   exactly one fixture (`seeded_events`); the plan names twelve others. The plan fails at *collection*
   as written. Fix by authoring them on the repo's real idiom in `tests/unit/test_top_accounting.py`
   (`env` fixture + module-level `_seed`/`_settings` helpers), then re-running the plan's Self-Review.

**Both external plan reviews were abandoned without a verdict, and the reason is reusable.** deepseek
v4 flash spent its tail reading *alembic's own source* in the uv cache and its harness logged that it
was repeating work without new evidence; gpt-5.6-sol produced no verdict across two attempts (8.5k and
8.3k lines of repo trawling). The brief asked for six attack categories at once over eight files —
**that breadth is what sent both unbounded.** Give a plan reviewer one attack category per dispatch.
Note what did work: all three real defects came from the cheap thing — reading the engine and running
it — not from the reviewers.

---

## D-078 — P6 Slice 1: the plan's test fixtures are now real; eleven defects, all found by running code

**2026-08-10 · P6 Slice 1, planning session 2. Planning is COMPLETE; still no P6 code.** The plan
and spec stay at `.superpowers/sdd/2026-08-09-p6-liveness-dedup/` (gitignored), which is why this
entry exists. D-077 records the design; this records the plan being made executable.

**The open defect from D-077 is closed, and it was bigger than D-077 stated.** Every pytest fixture
Tasks 5–8 named was invented — **sixteen**, not the twelve counted before, and the defect reached
**Task 5**, not just 6/7/8. `tests/unit/conftest.py` defines exactly one fixture (`seeded_events`).

**What replaced them.** Two fixtures the plan authors as real code, not as an instruction to the
implementer to go find equivalents:

- `tests/conftest.py` (**new**, Task 5 Step 1) — `DedupSeed` + `dedup_env` + a `seed_dedup`
  factory (`count=N`, `identical=True/False`, `body=...`).
- `backfill_identities` (Task 6 Step 1), appended to the same file once `identity_queries` exists.

Three placement decisions, each forced by something measured rather than assumed:

- **Root `tests/conftest.py`, not `tests/unit/`.** Task 6's CLI test belongs in `tests/cli/`, which
  cannot see a unit-scoped conftest. Verified empirically that a root conftest resolves for both
  directories and coexists with the existing unit conftest.
- **`backfill_identities` imports inside the function body.** A root conftest is imported for every
  test in the repo, so a module-level `from boardwatch.store.identity_queries import …` would break
  collection repo-wide at the Task 5 commit and at every bisect point between Tasks 5 and 6.
- **A conftest factory, not a `tests/unit/_dedup_seed.py` module.** The repo already solved this:
  `seeded_events` is a factory fixture used by six modules. Reuse beats a new import mechanism whose
  `sys.path` behaviour depends on pytest's import mode.

**Eight further defects, found while authoring the fixtures.** None came from reading the plan.

1. `tests/integration/` **does not exist** (the tree is `cli/contract/fixtures/generalization/perf/
   pipeline/unit`). The CLI test moved to `tests/cli/`.
2. Task 5's own `seeded_posting_id` omitted three NOT NULL columns — `normalized_title`,
   `content_hash`, `body_text`. That is an `IntegrityError` at *runtime*, so D-077's "fails at
   collection" summary understated the blast radius.
3. **`tests/unit/test_schema_head.py` pins the Alembic head** and its docstring requires a new
   migration to state the new head rather than inherit it. Task 5 would have turned `make check` red
   with nothing in the plan explaining why. Now an explicit step. `p1_resume_max_pages` confirmed as
   the current head, so the migration's `down_revision` was right.
4. **Neither `python` nor `boardwatch` is on PATH** (`which python` → not found). Eleven
   `python -m pytest` lines, four `boardwatch` lines and one `python -m alembic` line would all have
   failed. All now `uv run`. The alembic line also carried a literal `<the repo's alembic.ini>`
   placeholder; replaced by `schema_revision()`, which the repo already has and which raises on a
   forked chain — so there is no `alembic` CLI step at all.
5. **The "two identical postings, one ineligible" fixture was unbuildable.** Eligibility reads the
   JD body, so making exactly one of a duplicate pair ineligible requires them to share a
   `content_hash` while their bodies differ — a state production cannot reach, since the hash is
   derived from the body. Reshaped to two identical postings that are *both* ineligible
   (`hidden_ineligible == 2, hidden_duplicate == 0`). The dedup-before-eligibility mutation still
   goes red — it would read 1 and 1 — and the fixture stops lying about a production invariant.
6. **A survivor-election test would have passed for the wrong reason.** With `first_seen_at`
   ascending in posting-id order, an election that ignores `first_seen_at` and sorts by `posting_id`
   elects the *same* row, so the mutation could never go red. The seed now inverts the two orderings
   deliberately (`posting_ids[-1]` is earliest-seen, `posting_ids[0]` has the lowest id). This is
   the D-020 lesson again: derive the mutation from the claim, then check the fixture can express it.
7. Task 8 named a nonexistent call site (`test_run_funnel.py`) for `count_by_source`'s arguments —
   they are in `test_run_funnel_queries.py::_by_source` — and no invented fixture created the `runs`
   row that function requires. The `_ARGS` placeholder is gone.
8. Tasks 7 and 8 named the same fixture two ways (`..._without_backfill` / `..._no_backfill`).

Also corrected: three `...` placeholders in the CLI module (the prior Self-Review said two, in the
wrong step) are now real code, `build_context(ctx.obj).engine` / `utcnow()`, copied from
`track_cmd.py:53`; the File Structure note claimed "Tasks 1–5 are pure … Task 3 adds the schema",
both halves wrong; and the live-smoke step now says to run the ~23k-posting backfill against a
**copy** of the store first, and to confirm the corpus-wide count — a top-20 showing zero
duplicates is equally consistent with dedup working and with dedup being inert.

**The Self-Review was re-run and had itself gone stale.** It still described
`normalized_locations` as `str | None -> str | None` — the shape D-077's JSON-column defect had
left behind — after the signature had been fixed to `list[str] | None -> str | None`. A plan's
self-review is a document like any other and rots the same way (D-017, and the "review the docs you
write" lesson).

**The method, stated because it keeps paying.** All eleven defects across both sessions came from
writing the fixture code and executing it against the real schema and the real ranker — not from
review. This session ran the seed helper against a live migrated DB (every NOT NULL column,
`locations_json` returning a real `list`, identical hashes with distinct `provider_posting_id`,
inverted `first_seen_at` ordering) and then ran `rank_open_postings` to confirm the three states
Task 7's tests assert: an identical pair is both-visible *today* (so `hidden_duplicate == 1` will be
a real change and not some pre-existing filter's work), the degree recipe yields
`hidden_ineligible == 2`, and the distinct pair is a genuine control. What is **not** verified is any
implementation — those modules do not exist; that is TDD's job, and the plan says so.

**Both external plan reviewers remain abandoned with no verdict** (D-077 has the detail). Not
re-dispatched, per that entry's own rule: one attack category per dispatch, or not at all.

---

## D-079 — P6 Slice 1 annotates only; `postings.job_id` is not mutated

**Context.** Dedup could either project its result onto `postings.job_id` (regrouping postings under
one canonical job) or record it beside the data and let readers apply it.

**Choice.** Slice 1 **annotates only.** Identities are stored in a new `posting_identities` table and
suppression is resolved at *read* time; `postings.job_id` is untouched. Design §1.3.

**Alternatives rejected.** Mutating `job_id` in this slice. `applications.job_id` is the tracking key,
so regrouping a posting silently rewrites which job a recorded application belongs to. Job regrouping
and the `applications.job_id` migration are Slice 2's, designed together with their drain.

---

## D-080 — `content_hash` alone may never suppress

**Context.** A shared `content_hash` is the cheapest possible duplicate signal and the obvious first
thing to key dedup on.

**Choice.** `content_hash_only` is computed and stored as an annotate-only kind. It may never suppress.

**Alternatives rejected.** Hash-keyed dedup. Measured on the live corpus: 809 hash-collision groups, of
which **727 span a different title or location** — the Datadog 5843/5846/5849 shape, where one
description text is reused across genuinely different requisitions. Suppressing on the bare hash
collapses different jobs, which is the unrecoverable direction.

---

## D-081 — `exact_quad` is the sole suppressing kind, and its yield is stated honestly

**Context.** Five identity kinds are computed. Which of them may remove a posting from the lead list?

**Choice.** **`exact_quad`** — `(company_id, normalized_title, normalized_locations, content_hash)` —
and nothing else. On the live corpus this suppresses **147 groups / 186 surplus rows / 0.79%** of
23,455 open postings (measured 2026-08-10; see D-094 for why this differs from the design's
pre-registered 131/168/0.72%).

**What is claimed, precisely.** The sampled groups are same-role-different-requisition pairs with
byte-identical descriptions, **not** re-postings. The claim defended is "these represent **one
application decision**", not "these are the same requisition". Design §2.

**Alternatives rejected.** Adding a second suppressing kind for reach. Precision over recall: a leaked
duplicate is counted and recoverable, a suppressed real lead is neither.

---

## D-082 — `cross_host` ships annotate-only, reversing an earlier draft

**Context.** An earlier draft assumed `cross_host` (same normalized company + title + locations across
an ATS and an aggregator) would suppress, on the strength of an unanswered design flag.

**Choice.** `cross_host` ships with `suppresses=False`. It is computed, stored, and its survivor
election is written and directly tested — but it is unreachable from `resolve_duplicates`.

**Alternatives rejected.** Shipping it as a suppressor. Four reasons, any one sufficient: an unanswered
flag is not consent; `core/identity.py:3` already records that cross-ID heuristics may only annotate;
PROGRAM P6 item 1 restricts suppression to *exact* identities and `cross_host` carries neither
`company_id` nor `content_hash`; and a concrete counterexample exists (Acme Greenhouse req ENG-241 vs
LinkedIn req ENG-319 — same company, title and location, different jobs, and string-verify cannot tell
them apart because it re-compares the same three weak fields).

**Re-entry path.** It becomes suppressible once an aggregator posting can be dereferenced to exact
requisition evidence. The election logic already ships and is proven, so enabling it is one boolean.
Design §3.1.

---

## D-083 — No location evidence ⇒ no location-bearing identity, never a `"[]"` sentinel

**Context.** `normalized_locations` needs a representation for a posting that carries no locations.

**Choice.** It returns **`None`**, and the caller emits no location-bearing identity at all — so
`exact_quad`, `cross_host` and `company_title_location` are simply absent for that posting.

**Alternatives rejected.** An `"[]"` sentinel. It makes every location-less posting compare **equal** to
every other one on that component, and the resulting false suppression is undetectable downstream:
string-verify re-compares the same two `"[]"` values and passes, and the §6.3 recount recomputes the
same `"[]"` and agrees. Both guards would agree on the wrong answer. Measured cost of the safe
direction: 7 rows of 23,455. Design §2.1.

---

## D-084 — Three host classes, not two; matching is exact-or-dot-suffix

**Context.** Survivor election across hosts needs to know which URL is authoritative.

**Choice.** Three classes — `ats`, `aggregator`, `unknown` — with `unknown` as the default. `unknown` is
never elected and never dropped. Host matching is `host == known or host.endswith("." + known)`.

**Alternatives rejected.** (a) A binary ATS/aggregator split: it classifies a company's own careers site
as "not ATS" and would drop the company's own page in favour of a job board. (b) Substring matching:
`greenhouse.io.evil.example` and `notgreenhouse.io` would both read as ATS and could win election.
Design §3.

---

## D-085 — Allowlist URL normalization, not a denylist

**Context.** `normalize_url` must strip tracking parameters while keeping identity-bearing ones
(`gh_jid` is load-bearing in real posting URLs).

**Choice.** An **allowlist** of identity params; everything else is dropped.

**Alternatives rejected.** A denylist of tracking params. The direction was chosen by *which failure is
detectable*: a denylist that has not yet learned a new tracking param silently **splits** one posting
into two, which nothing catches; an allowlist that has not learned a new identity param **merges** two
postings, which string-verify then catches. Merge-then-verify is the recoverable failure. Design §4.1.

---

## D-086 — Survivor election never consults score; `posting_id` is a load-bearing tiebreak

**Context.** When a group of duplicates is found, one row survives.

**Choice.** Election is `(host_class, earliest first_seen_at, lowest posting_id)`. Score is never a
tiebreaker.

**Alternatives rejected.** Electing the highest-scoring row. Scores move whenever the profile, taxonomy
or ranker changes, so the survivor's identity would change between runs — and Gate P6 requires
measuring duplicate leakage across a 7-day window, which a moving survivor makes meaningless.
`posting_id` is not decoration: `first_seen_at` is second-resolution and a single board's postings are
inserted in one pass, so ties are routine. Design §5.1.

---

## D-087 — Instrumentation is completeness-gated, not existence-gated

**Context.** The funnel's `unique` counter reads stored identities. When may it report a number?

**Choice.** Only when **every** open posting carries a row at the current
`IDENTITY_ALGORITHM_VERSION`. Otherwise `None`. An algorithm-version bump therefore degrades `unique`
to `None` until a re-backfill.

**Alternatives rejected.** `if identities:`. A single backfilled posting in a 23,455-posting corpus is
indistinguishable from a complete one under a truthiness check, and the number that falls out would be
printed in the same column as a real measurement. Design §2.2.

---

## D-088 — `assisted` stays `None` in this slice

**Context.** `SourceOutcome.assisted` credits a source that arrived second for a posting another source
won. With dedup now live, it is tempting to report it.

**Choice.** `assisted` reports **`None`**, even on a complete corpus with live suppressions.

**Alternatives rejected.** Reporting `0`. `exact_quad` is keyed on `company_id` and sources *are*
`company_id`, so no suppression this slice can produce crosses a source boundary — `assisted` is
structurally incapable of being non-zero. `0` would assert "we looked and no source arrived second";
the honest statement is "no mechanism exists that could have counted one". This is the D-022/D-023 rule,
which this program has already been bitten by twice. Design §6.2.

---

## D-089 — Identities are upserted on every observation; a kind that stops being produced is deleted

**Context.** `scan/apply.py` refreshes a posting's title and locations on *every* observation
(`_mutable_fields`, "regardless of content_hash") while gating a *revision* on `content_hash` alone. So
a retitle with an unchanged body moves an identity key without producing a revision.

**Choice.** `write_identities` makes a posting's current-version rows match the computed set **exactly**
— inserting, updating **and deleting**.

**Alternatives rejected.** Insert-if-absent. It leaves the superseded key stored forever, which makes
`identities verify` permanently red on a legitimate update — and a permanently-red check is a discarded
check. Deletion is part of the same contract: losing location evidence drops three kinds (D-083), and an
orphaned `exact_quad` row would keep suppressing on behalf of a posting that no longer earns one.
Design §2.3.

---

## D-090 — The ranker is completeness-gated for reproducibility, not safety

**Context.** The ranker skips suppression entirely unless identities are complete. It would be easy to
justify this as a safety measure; that justification would be wrong, and worth stating so it is not
repeated.

**Choice.** Gate the ranker on completeness, and record that the reason is **reproducibility**.

**Why not safety.** Partial coverage cannot over-suppress: a posting with no identity row joins no
group and is never suppressed. The worst a partial view does is elect a survivor from the covered
subset while the true survivor sits uncovered and stays visible anyway — which over-shows, the
acceptable direction. The real reason is that *which* rows get suppressed mid-backfill depends on
backfill order, and Gate P6 requires re-deriving 20 sampled suppressions from the data. A suppression
whose survivor election did not see all the candidates cannot be re-derived. The cost of the gate is one
command.

---

## D-091 — The recount recomputes in Python, and claims staleness only

**Context.** `identities verify` is the D-028 "count the deliverable through a different path" check.

**Choice.** Path A reads stored `posting_identities` rows; Path B **recomputes** them from `postings` in
Python. It lives in `identities verify`, not in `boardwatch verify` (which is run-artifact scoped), and
exits 1 on missing identities as well as stale ones.

**What it does NOT claim.** It is a staleness and consistency check, **not** proof that the normalizers
are correct — both paths call the same `normalize_title` / `normalized_locations`. Re-grouping the same
table a second way would have been the D-028 tautology this program has already shipped and deleted
once. Design §6.3.

---

## D-092 — Identities are backfilled by an explicit command, not by the migration

**Context.** The `p6_posting_identities` migration could populate the table as it creates it.

**Choice.** The migration creates the table and **does not backfill**. `boardwatch identities backfill`
is a separate, re-runnable command.

**Alternatives rejected.** Backfilling inside `upgrade()`. Recomputing identities for a 23k-row corpus
is not a side effect anyone wants from `alembic upgrade`, and it could not be re-run after an
`IDENTITY_ALGORITHM_VERSION` bump. Until the command is run the funnel honestly reports `not
instrumented` rather than a partial number. Design §7.

---

## D-093 — Slice 1 does NOT meet Gate P6, and makes only one of its four clauses measurable

**Context.** It would be easy to read "dedup shipped" as "Gate P6 met".

**Choice.** State plainly, in the spec and in `STATE.md`, that Slice 1 does not meet Gate P6.

**What it does.** It makes the funnel's `unique` counter a measured number instead of `not
instrumented` — one clause. The other three are operational measurements over a running system: 7-day
duplicate leakage, zero dead postings reaching the lead list, and a 20-sample suppression audit. The
build made them measurable; it did not meet them. Slice 2 is the durable ledger + drain + job
regrouping; Slice 3 is applied-state suppression + liveness. Design §0.

---

## D-094 — P6 Slice 1 BUILT (unattended run): five more plan defects, three of them tests that could not fail

**2026-08-10, unattended launchd run starting 03:10. All nine plan tasks executed on branch
`p6-slice1`. NOT merged, NOT reviewed.** `main` is untouched. Execution mode was inline
(`superpowers:executing-plans`), decided in advance: subagent-driven development is the better mode
when a human reviews between tasks, and there was no human.

**Constraints honoured, all three:** branch-only (no merge, no PR, no force-push); every live-data
step against a **copy** of the store (`/tmp/bw-smoke-copy`), with the live store never written to;
and no speculative fan-out, no D-072 benchmark, no re-dispatched plan review.

### The plan was executable, and the fixtures held

D-078's claim that the seeding was verified against the real schema held up: `seed_dedup` was
re-run before the table existed and produced exactly what it promised — `locations_json` reading
back as a Python `list`, one shared `content_hash` with distinct `provider_posting_id`, and
`first_seen_at` **inverted** against `posting_id` order. The three ranker preconditions Task 7
asserts also held. Every mutation check the plan specified was run in isolation with a cleared
`__pycache__` (D-025), and all of them were caught by the *named* test — except the four below.

### A fifth defect, found by `make check` — and the reason the gate is the gate

**The first full-branch gate run came back RED: `test_migrations_match_metadata` failed**, and it
was right to. `tables.py` declares `posting_identities`' UNIQUE constraint **unnamed**, letting
`metadata.naming_convention` render it as
`uq_posting_identities_posting_id_kind_algorithm_version`. The plan's migration text hard-codes
`name=op.f("uq_posting_identities_posting")`. The two disagree, so alembic's `compare_metadata`
saw permanent drift between the migrated database and the metadata — a defect that would have
poisoned every future autogenerate diff, not just this one test.

Fixed by writing both constraint names in their full convention-rendered form
(`uq_posting_identities_posting_id_kind_algorithm_version`,
`ck_posting_identities_identity_kind_enum`), which is what `p0_applications.py` and
`8df3b3809bba_schema_v1.py` already do. The CHECK name was wrong the same way and did *not* fail
the test — alembic does not reflect SQLite CHECK constraints — so it was corrected on the same
reasoning rather than left because nothing complained. Mutation-confirmed: restoring the old name
turns `test_migrations_match_metadata` red on its own.

**Why this one matters out of proportion to its size.** Every other defect this session was caught
by running code during TDD. This one was invisible to all of it: the migration applied cleanly, the
table worked, all five schema tests passed, the 23,455-posting backfill ran, and `identities
verify` exited 0. Only the full gate saw it. That is the whole argument for `make check` being the
only gate, and for never reporting a result before it has run.

### Four defects, found by running the plan's own code

1. **Task 3's separator test could not fail.** It shifted a word between `title` and `locations`
   to prove `_SEP` prevents `("ab","c")` and `("a","bc")` colliding. But `normalized_locations`
   emits `json.dumps`, so the locations component always arrives wrapped in `["..."]` and
   delimits itself; the two keys stayed distinct with `_SEP = ""`. **The only boundary where two
   *bare* components meet is company_id↔title.** Retargeted there (company 10 + title `"1data"`
   vs company 101 + title `"data"`, both concatenating to `"101data"`); it now goes red under the
   mutation.

2. **Task 4's `test_no_suppression_anywhere_ever_carries_the_cross_host_kind` could not fail.**
   Its two `_p(3)`/`_p(4)` rows shared the cross pair's normalized company, title and location, so
   all three unsuppressed rows landed in **one** `cross_host` group with two ATS members — which
   `elect_cross_host_survivor` correctly declines as ambiguous. The test therefore stayed green
   with `cross_host.suppresses` flipped to `True`, i.e. green against the one mutation it exists
   to catch. Fixed by giving the exact_quad pair a different company name and title, and by adding
   `assert result` — `all()` over an empty tuple is vacuously true, a second way the same test
   could have passed for nothing.

3. **Task 4's posting_id-tiebreak test could not isolate what it claimed.** Its docstring said
   that without the tiebreak "the survivor depends on dict ordering". It does not:
   `resolve_duplicates` groups over `sorted(by_id.items())`, so members always reach `_elect` in
   posting-id order and `min` returns the lowest id on a tie regardless. Dropping the `posting_id`
   term left the whole suite green. Fixed by adding
   `test_elect_breaks_a_first_seen_tie_by_lowest_posting_id`, which calls `_elect` directly with
   members deliberately out of order, and by correcting the misleading docstring rather than
   leaving it to mislead the next reader.

4. **Task 4's `_cross` helper passed `provider_posting_id` twice** — once positionally in its
   defaults and once through `**over`, which the ENG-241 test overrides — a `TypeError` at run
   time. Fixed by merging `over` into a dict so the override wins.

Also: one *mutation* in this session's own Task 6 checklist was mis-specified by the implementer
(removing the `posting_ids=[]` early return is compensated by `.in_([])`, so nothing changed).
Corrected to also make the filter truthiness-based, at which point the test went red as intended.
**A mutation that survives is not automatically a bad test — check the mutation expresses the
claim first.** And `Sequence` was deferred out of the Task 5 conftest import block to Task 6,
where it is first used, because ruff's F401 would otherwise have failed the Task 5 commit.

### What was measured, and the number that moved

On the copy: **23,455** open postings, **117,254** identity rows, `identities verify` **exit 0**,
`identities_complete` **True**, and **147 groups / 186 surplus rows / 0.79%** suppressed — all
`exact_quad`, no survivor itself suppressed.

**That is more than the pre-registered 131/168/0.72% baseline, and the cause was found before
committing** rather than explained away after. Re-running the grouping over the same corpus with
**raw** `locations_json` reproduces **136/174/0.74%**, matching the design's own *unguarded*
baseline (135/173/0.74%) to within one group. The delta is location **normalization** — sort,
case-fold, whitespace-collapse, exactly what design §2.1 specifies — which merges a further 11
groups / 12 rows; measured directly, **12 of the 186** suppressions have raw location lists that
differ. Title normalization contributes nothing: 0 of 186 have a stored `normalized_title`
disagreeing with `normalize_title(title)`.

~~**Precision was re-checked through a second path**, comparing company_id, normalized title,
normalized locations and normalized body outside `_verify_quad`: **0 of 186 failures**.~~
**RETRACTED 2026-08-10 — see D-097.** `_verify_quad` *is* those four comparisons with those
normalizers, so the check could not disagree. Sampled groups are same-role-different-requisition
pairs — identical titles, identical locations, distinct `provider_posting_id`; that observation
stands. ~~And the funnel's per-source `unique` reconciles independently: sum(open) − sum(unique) =
**186** across 118 sources, equal to the resolver's own count~~ — **RETRACTED 2026-08-10, same
entry**: `unique_by_company` is built from the same `identity_rows` and the same `resolve_duplicates`
output that produced the count, so that identity holds for every possible database state. `assisted`
was `None` on all 118, which is unaffected.

**Marked, not rewritten** — this log is append-only, so the original wording stays legible and the
withdrawal is annotated in place. Recorded here because the retraction commit itself missed this
entry: the grep that was supposed to find every restatement was piped through `head -30` and the
match on this line sat below the cut. **A truncated grep is not a negative result** — the same rule
that already applies to a failed command applies to a clipped one.

### Not finished

The `boardwatch top --top 20` half of Task 8's live smoke did not complete — it ran >40 minutes
against the 23,455-posting copy (it pays for `run_preflight` + `run_eligibility` over the whole
corpus) and was still running at close. **This is cosmetic:** the corpus-wide figure it exists to
sanity-check was obtained two other ways, and the plan itself notes that a top-20 usually shows 0
duplicates and so cannot distinguish working dedup from inert dedup. Recorded as skipped rather
than quietly dropped.

**Gate P6 remains NOT met** (D-093), and no clause of it was claimed.

---

## D-095 — P6 Slice 1 reviewed by three independent reviewers; fourteen findings fixed, two rejected

*2026-08-10, post-overnight-build fix session.*

**Context.** The branch was built unattended and gated green, but nothing had been reviewed. The P2
item 4 whole-branch review had caught a CRITICAL that every per-task review missed, so this
comparable checkpoint got the same treatment — widened to three reviewers to see whether the extra
lanes pay for themselves.

**Choice.** Three reviewers in parallel on the pinned range `main..3a35819`: fresh-context Opus 5
(whole-branch, read-only), DeepSeek v4 flash (full diff), GPT-5.6 sol at high reasoning (repo
access, read-only sandbox). Verdicts REWORK / REWORK / SHIP-WITH-FIXES. Every claim was verified
against the code before being acted on.

**Was the third lane worth it?** Yes, and not for the reason expected. **Corrected 2026-08-10 after a
docs review:** an earlier version of this entry said "seven findings" and "the reviewers overlapped on
exactly one finding". Both were wrong, and the second was load-bearing for this entry's own
conclusion. The full enumeration — **fourteen** findings fixed, each with an attribution (a second
docs review caught that the corrected entry still miscounted its own table, 12 against 14 rows; the
count is now stated as the row count and nothing else):

| Finding | Found by | Fixed in |
|---|---|---|
| `_verify_quad`'s `None == None` hole | **all three** | `dedup.py` |
| `load_identities` corpus-sized `IN` list (32,766 cap) | **DeepSeek + Opus** | `identity_queries.py` |
| `normalize_title` C++/C#/C collision | GPT-5.6 sol | `normalize.py`, D-096 |
| migration imports the live catalog into its CHECK | GPT-5.6 sol | `p6_posting_identities.py` |
| `ValueError` handler in `normalize_url` never exercised | GPT-5.6 sol | test |
| `host_class` precedence in `_elect` untested | GPT-5.6 sol | test |
| drain bounded by the rank `limit` | Opus | `top_cmd.py` |
| `company_id` untested in the only suppressing key | Opus | test |
| the two tautological verification claims | Opus | D-097, METRICS/STATE |
| `normalize_url` param-order test vacuous | Opus | test |
| three `all()`-over-empty assertions | Opus | test |
| bare `KeyError` for a resolver-less kind | Opus (minor, elevated) | `dedup.py` |
| `locations_json = [null]` as location evidence | DeepSeek | `identity_queries.py` |
| `split("_")` field-neutrality test vacuous | DeepSeek | test |

So the overlap is **two** findings, not one — and the second overlap (the `IN`-list cliff) is arguably
the most consequential of the whole set, since it made `identities verify` and the funnel sweep a
scheduled failure as the corpus grows past 32,766 open postings. It was previously unattributed here,
which is exactly the gap that let the miscount stand. Each reviewer still found things neither other
saw, so the conclusion holds — but on a corrected count.

**Two findings were rejected as factually wrong**, which is the cost of the extra lanes:

1. DeepSeek: *"`normalize_body` is ASCII-only (`[^a-z0-9 ]`), so `["Remote","远程"]` collides with
   `["Remote"," "]`."* It confused `normalize_body` with `normalize_company`. Measured:
   `normalized_locations(["Remote","远程"])` returns the JSON string `'["remote", "远程"]'` (escaped
   as `远程`, since `json.dumps` defaults to `ensure_ascii=True`), while
   `normalized_locations(["Remote","  "])` returns `'["", "remote"]'`. Two different keys, so no
   collision — the non-ASCII text is preserved, not stripped.
2. GPT-5.6 sol: *"survivor election prioritizes host class before `first_seen_at`, contrary to the
   stated earliest-seen rule."* D-086 explicitly ratifies `(host_class, earliest first_seen_at,
   lowest posting_id)` and the docstring matches. Its sub-claim was kept: no test covered the
   precedence, because every `exact_quad` test seeds one host.

**Alternatives rejected.** Trusting the reviewers' severities. DeepSeek rated the `_verify_quad`
hole a BLOCKER on precision grounds; it is not, because `_verify_quad` re-compares company, title,
locations **and body** against current data, so anything it clears still shares a byte-identical
normalized body. The real damage was narrower (a D-083 invariant violation), and mis-rating it
would have justified emergency work on the wrong thing.

---

## D-096 — The C++/C# fix folds punctuation into words; it does NOT add a raw-title comparison

*2026-08-10.*

**Context.** `normalize_title` folds `[\W_]` to spaces, so `C++ Developer`, `C# Developer` and
`C Developer` all normalize to `c developer`. Since `_verify_quad` re-runs the same normalizer, the
string-verify agrees with the key on the wrong answer — the exact failure shape D-083 names.

**Choice.** Fold `+` and `#` to words (` plus `, ` sharp `) inside `normalize_title`, before the
punctuation strip. Bump `IDENTITY_ALGORITHM_VERSION` to `p6.2` as any normalizer change requires.

**Alternatives rejected — and this one was rejected by measurement, after being recommended.** The
first proposal was to add a case-folded, whitespace-collapsed **raw title** comparison to
`_verify_quad`, so the verify would stop depending on the key's own normalizer. Measured against the
live corpus first: **8 of 147 suppression groups already differ in raw title, and all 8 differ only
in punctuation, spacing or case on the same role** (`Mobile Expert - Bilingual…` vs
`Mobile Expert, Bilingual…`; `Store-in-Store` vs `Store in Store`; `Javascript` vs `JavaScript`;
`IC design` vs `IC Design`; `Manager, Clinical Study Lead` vs `Manager Clinical Study Lead`). A raw
comparison would have leaked **6 of those 8 real duplicates** to defend a collision the corpus does
not contain. The shipped fix costs nothing: 123 open titles contain `+` and 16 contain `#`, and
**none of them sits in any suppression group**, so the measured figure stays 147/186. Both facts are
now pinned by tests — one asserting C++/C#/C produce different keys, one asserting the five real
punctuation-noise pairs still collapse.

**This RETIRES a previously pinned ACCEPTED caveat, deliberately.**
`tests/unit/test_normalize.py::TestNormalizeTitle::test_caveat_cpp_collapses_to_c` asserted
`normalize_title("C++ Developer") == "c developer"` with the comment *"Pinned ACCEPTED caveat: '+' is
stripped, so C++ titles collide with C titles."* So the collision was known and accepted — but it was
accepted when `normalize_title` fed no suppressing key and a title collision was cosmetic. P6 slice 1
made it a component of `exact_quad`, the only kind that can suppress, which changed the consequence
from "two titles look alike" to "a real, different posting is hidden". The caveat is therefore
re-ratified against its new stakes rather than inherited: the test is replaced by
`test_language_punctuation_no_longer_collapses`, which pins the new behaviour and records why.

**The two transferable lessons.** (1) A fix aimed at a theoretical failure must have its blast radius
measured on real data before it ships — this one would have traded live recall for hypothetical
precision, and only the corpus could say so. (2) **A pinned caveat is scoped to the consumers it was
pinned against.** When a normalizer acquires a new consumer with harsher consequences, every accepted
caveat on it needs re-checking; `grep` for existing tests of a function before changing it, because
the accepted-caveat tests are where the prior reasoning is recorded and they are easy to miss — this
one was found by `make check`, not by the focused test modules.

---

## D-097 — `_verify_quad` rejected nothing on the live corpus; "string-verified" is not precision evidence

*2026-08-10.*

**Context.** Re-deriving the suppression count in SQL (grouping stored `identity_key`s, calling no
Python normalizer and no resolver) returned **147 groups / 186 surplus rows** — identical to
`resolve_duplicates`.

**Choice.** Record the agreement as a finding rather than as reassurance. Equal counts mean
`_verify_quad` rejected **zero** members on the 2026-08-10 copy of the live store. Scoped to that
snapshot deliberately: "has never once fired" overreaches one corpus, and the function does reject in
`tests/unit/test_dedup_resolver.py` where a divergent body is forged.

It is not broken. It is redundant with the key on this data, because it re-runs the same normalizers
the key was built from. So it genuinely defends against a SHA-256 collision and against stale stored
identities, but **not** against the normalizers being lossy — which is precisely how the C++/C#
collision (D-096) got in. Nothing may cite "string-verified" as evidence of precision it cannot
supply. Precision evidence has to come from a comparison the key does not already make: the raw-field
audit in METRICS.md is the one that can disagree.

**Alternatives rejected.** Deleting `_verify_quad` as dead weight. It is the only guard that fires **in
the read path**, and staleness is a live condition (D-098); it costs one pass over a small group.
Corrected 2026-08-10 — an earlier draft said "the only guard against a stale stored identity", which
D-091 falsifies: `identities verify` detects staleness by recomputing (Path B) and exits 1 on it. The
distinction is the whole point, though — `verify` only catches it when somebody runs it, and nothing in
the automated path does.

---

## D-098 — Suppression reports when it is OFF; wiring backfill into the pipeline is Slice 2

**Context.** `write_identities` has exactly one caller in `src/` — the manual
`boardwatch identities backfill`. Nothing in the scan or pipeline path writes identities. So on any
run that discovers ≥1 new posting, `identities_complete()` is False, suppression is silently
disabled and `unique` reports `None` for every source; on a run that only mutates existing postings,
coverage stays complete and suppression runs on **stale** keys. The 147/186 figure was produced by a
manual backfill on a copy — a sequence that does not occur in the shipped automated path.

**Choice (ruled by Mit).** Ship the operator-visible notice now; defer wiring the backfill into the
pipeline to Slice 2. `top` prints, whenever coverage is incomplete, that suppression is OFF and
which command fixes it. `RankedResults` carries `identities_are_complete`, defaulting to **False** —
the noisy direction, so a caller that forgets to set it gets "disabled" rather than a silent claim
that the subsystem ran.

**Why the notice is not cosmetic.** `hidden_duplicate == 0` is ambiguous between "no duplicates
found" and "dedup never ran", and the second is the *common* case, not the corner. Without the notice
an uninstrumented run is indistinguishable from a clean one — the same "a rule that cannot fire is a
monitoring failure, not a conservatism feature" problem the keystone invariant exists for.

**Alternatives rejected.** Wiring the idempotent backfill into the pipeline now. It is the better end
state and makes the Gate P6 `unique` clause genuinely measurable, but it adds a **second corpus-wide
`body_text` load** beside the one `count_by_source` already does, and belongs with Slice 2's ledger
work where that load can be paid once rather than twice.

**Cost corrected 2026-08-10.** An earlier draft justified this deferral with "it adds the measured
471 MB peak RSS / 9.4 s to every run". Those figures belong to `count_by_source`'s survivor sweep,
which **already runs on every run**, so wiring in the backfill cannot add them. The backfill's own
measured cost is **41 s** cold (METRICS.md). Citing the
wrong subsystem's number — ~4× too small — in the sentence that rules the work out until Slice 2 is
precisely the kind of unchallengeable-looking figure this log exists to prevent. (A "10.3 s on a warm
copy" figure was also cited here and has been removed: it was measured in the fix session but never
recorded in METRICS.md, so it could not be checked from the file that owns per-run numbers.)

---

## D-099 — Gate batching stays allowed; the per-task fast-check set must include the schema guards

**Context.** The overnight run batched `make check` over Tasks 5–8 rather than gating each task, and
committed before the batched gate returned. That gate came back RED on
`test_migrations_match_metadata` — a constraint-naming drift the standing suite **already covered**.
The per-task fast checks (ruff, `mypy --strict`, the generalization checker, plus the focused test
modules) did not include `test_store.py`, so the defect survived four commits.

**Choice (ruled by Mit).** Do **not** ban batching. Batching a ~18-minute gate over several tasks is
the correct wall-clock trade and the pinned-worktree pattern that made it safe is worth keeping. The
ruling is narrower: the per-task fast-check set **must** include the schema/metadata guard tests —
`tests/unit/test_store.py` and `tests/unit/test_schema_head.py` — for any task that touches
`tables.py`, a migration, or the Alembic head. They run in seconds.

**Alternatives rejected.** A blanket "gate every task" rule. Five ~18-minute gates is most of an
unattended night, and the failure here was not that the gate ran late — it was that the cheap check
which would have caught it was not in the per-task set. Fixing the set is the surgical repair;
banning batching pays a large wall-clock cost for a defect that a two-second test catches.

**Also recorded, because it is the real cause of the commit order.** The run committed Tasks 5–8
before their gate returned. "Never commit on a red gate" is unenforceable when the gate result
arrives after the commit; the enforceable version is "do not commit a schema change without running
the schema guards", which is what this ruling installs.

---

## D-100 — P6 Slice 1 merged to `main`; Gate P6 clause 3 is MET, not merely measurable

*2026-08-10, on Mit's explicit authorization after the three-reviewer review.*

**Context.** Slice 1 was built unattended, reviewed by three independent reviewers, and every finding
fixed (D-095 … D-099). `make check` green at `f2f2430`. Mit authorized the merge.

**Choice.** Fast-forwarded `main` from `1c0747e` to `f26c87a` and pushed. **Fast-forward, not squash**,
so the 19 commits keep their individual history: each is one logical change, the TDD trail is legible,
and the review-fix commits stay distinguishable from the original build. Previous phases squashed via
PR; that collapses a nine-task TDD sequence into one commit and was not worth it here.

**Also recorded: Gate P6's third clause is MET.** The gate asks for "a deliberately-injected
hash-collision test proving the wrong job cannot be deduped".
`tests/unit/test_dedup_resolver.py::test_string_verify_blocks_suppression_when_bodies_diverge` forges
`identity_key` equality across two divergent bodies and asserts the group is refused; two adjacent
tests reproduce the real Datadog 5843/5846/5849 shape (one `content_hash`, three requisitions, 809
such groups live of which 727 span a different title or location). That clause is a **test**, not an
operational measurement, so it is satisfied outright rather than "made measurable".

**Alternatives rejected.** Continuing to report all four clauses as outstanding, per the earlier
"Slice 1 makes exactly one of four clauses measurable" line. That undersold a clause that is actually
met and would have left a future session re-building a test that exists. D-093's framing (Slice 1 does
not meet Gate P6 *as a whole*) is unchanged and still correct.

**Carried forward, not done.** The live store needs `boardwatch identities backfill` after this merge:
D-096 bumped `IDENTITY_ALGORITHM_VERSION` to `p6.2`, so the existing `p6.1` rows stop being read and
suppression stays off until the backfill runs. `top` now says so out loud (D-098), which is the only
reason this is a follow-up rather than a silent regression.

---

## D-101 — Gate P6 clause 4 is MET: 20/20 sampled suppressions are genuine duplicates

*2026-08-10, on the live store immediately after its first backfill.*

**Context.** Gate P6 requires "a suppression audit of 20 sampled suppressions confirming each was a
genuine duplicate or policy skip". Until the live store was backfilled there was nothing real to sample.

**Choice.** Sampled **deterministically** — every 7th group ordered by `identity_key`, first 20 — rather
than randomly, so the sample is reproducible and a future re-run audits the same groups. Read all 20 by
eye. **All 20 are same-company, same-title, same-location, distinct `provider_posting_id`.** Zero false
positives. Spread over 13 employers and both software and non-software roles, so it is not an artifact of
one board's requisition scheme.

**The one group that earns its own line.** Duolingo `6469`/`6470` ("Software Engineer II, Android")
differ **only** in location list order: `["Pittsburgh, PA", "New York, NY"]` against
`["New York, NY", "Pittsburgh, PA"]`. Only the sort in `normalized_locations` catches it. This is the
empirical justification for design §2.1's sort + case-fold, and it explains the shipped 186 exceeding the
raw-grouped 174: **the delta is real duplicates, not over-suppression.** The pre-registered baseline
looked "safer" only because it was blind to this class.

**Alternatives rejected.** A random sample. Reproducibility matters more than statistical purity for an
audit that a later session may need to re-run against a changed algorithm version — and with 147 groups
and a uniform failure mode, a systematic sample is no weaker here.

**Gate P6 now stands at two of four clauses met** (this one and the injected hash-collision test, D-100).
The remaining two — 7-day duplicate leakage ≤ 5%, and 0 dead postings reaching the lead list — need a
running system and liveness (Slice 3) respectively. Neither is a build gap in Slice 1.

---

## D-102 — D-072 (model-tier benchmark) is deferred indefinitely

*2026-08-10, ruled by Mit.*

**Context.** D-072 agreed a benchmark to compare model tiers on the 173-row eligibility answer key, which
would also have picked the final gate's default judge model. It has been carried as an owed next-action
since 2026-08-08 across several sessions.

**Choice.** **Deferred indefinitely.** It is no longer an owed item and must not be carried forward as
one, listed as a next action, or treated as blocking any phase.

**Consequences, stated so nobody re-derives them as blockers.** The final eligibility gate keeps whatever
default judge model it currently ships with, chosen without benchmark evidence; that is now an accepted
condition rather than a gap. Gate P5 is unaffected — it is MET on the deterministic engine (D-073) and the
agent-lane gate is additive (D-074).

**Alternatives rejected.** Keeping it as a low-priority backlog item. A perpetually-deferred "next
action" in a read-first document is worse than no entry: it costs every future session the same triage and
makes the real next action harder to find. Recorded as closed-by-decision instead.

---

## D-103 — P6 Slice 2: the ledger is a current-state row per job, `seen` suppresses on a TTL, and the policy stamp never auto-reopens

*2026-08-10. Design at `.superpowers/sdd/2026-08-10-p6-slice2-ledger/design.md` (gitignored — hence this
entry). Spec: PROGRAM §3.P6 item 4.*

**One row per job, upserted — not an append-only events table.** The spec asks for *monotonic upserts*, and
an append-only log cannot be upserted; "monotonic upsert" describes a current-state row. The append-only
trail exists where it is actually needed: `job_grouping_events` (D-104), the half that mutates a key
another table reads. Recorded so a later session does not re-derive a `job_disposition_events` table and
report it as missing.

**Rank is `seen` 0 < `skipped` 1 < `built` 2.** Against a **live** row an upsert may raise or hold, never
lower. Against a non-live row (expired or reopened) any disposition may be recorded, which is what makes an
expiry or a reopen mean anything. The one case that reads like a breach and is not: re-recording `seen` on a
live `seen` row refreshes `expires_at` — monotonicity is over the rank, not the timestamp.

**One liveness predicate, shared by the reader and the writer.** `core.ledger.is_live` is the only
definition, and `plan_upsert` calls it rather than trusting the caller to pre-filter. A reader that thinks a
row is expired while the writer thinks it is live both hides a job and refuses to re-decide it — a job that
can never be surfaced again. Lazy read-time expiry throughout: nothing sweeps, nothing deletes, and the
drain sets `reopened_at` instead of deleting, so a drained decision is still on record.

**`seen` suppresses for a TTL — ruled by Mit**, from three options put to him with the measured evidence.
Every job the ranker surfaces as a lead is recorded `seen` with `expires_at = now + seen_ttl_days` (7), so
the daily queue advances past what was already shown and re-enters after the TTL in case it was missed or
the JD moved. **The alternatives rejected:** a non-suppressing bookkeeping `seen` (safer and less
surprising, but it would have had no reader in this slice and the spec's TTL machinery would be exercised
only by tests), and `seen` written only on an aborted run (narrowest, but it would almost never fire, which
this program treats as a monitoring failure in itself).

**Measured consequence of that ruling, stated because it is real and reversible.** The ranker is the
`seen` writer — one writer, so `top` and the pipeline cannot drift on what "surfaced" means — which makes
`top` mutate suppression state. Two `top` invocations inside the TTL therefore show different rows. The full
gate quantified the blast radius: **four tests in three modules** broke, every one a caller that ranks twice
against the same corpus. Each was isolating a different mechanism and now opts out with
`--include-handled`; one could not, because it asserts full `RankedResults` equality and a drained row
carries `handled_as='seen'`, so it releases the ledger between calls via the drain's own reopen path. If
`top`'s behaviour turns out to be surprising in practice, the cheap reversal is to move the `seen` write
from `rank_open_postings` into the pipeline only; the disjointness guarantee does not depend on it, because
`built` alone carries that.

**The policy stamp is reused, and a mismatch is reported rather than acted on.** `policy_version` is a
digest of the run manifest's own five components (`code_fingerprint`, `config_hash`, `profile_row_hash`,
`profile_facts_hash`, `rules_hash`) — nothing new is hashed, because "what would make us re-decide this" and
"what makes two runs comparable" are the same question and P0 item 4 already answered it. **A stamp
mismatch never re-opens a disposition automatically.** Auto-expiry on mismatch would rebuild the entire
shortlist on any settings tweak — the 465-item-queue failure in a different costume — and an automatic
re-open cannot be reviewed before it happens. `ledger show --stale` lists them; `ledger reopen --stale`
releases them. Accepted cost, stated plainly: a `built` lead whose résumé has since been rewritten stays
suppressed until somebody runs the drain.

**Enforced twice, per CLAUDE.md.** Typed at the write site (`UnknownDisposition`,
`UnknownDispositionReason`, `MalformedDisposition`) and again as three CHECK constraints, so a direct INSERT
cannot invent a bucket or store a permanent decision with no stamp. The permanence CHECK states **both
tiers explicitly**, because the obvious biconditional `(disposition IN permanent) = (policy_version IS NOT NULL AND expires_at IS NULL)` looks equivalent and is not. It admits two shapes, and both are worse than they look: `(seen, NULL, NULL)` — a `seen` row with no TTL, i.e. **permanent suppression that no expiry will ever lapse and that `stale_dispositions` cannot list, because that read keys on a non-NULL `policy_version`** — and `(seen, stamp, TTL)`. The store tests caught
that before it shipped.

**Corrected 2026-08-10 by the Slice 2 review.** This paragraph originally named the admitted shape as "a
`seen` row carrying a policy stamp *and* no TTL … (0 = 0)". That shape is **rejected** by the naive form —
LHS 0, RHS `(1 AND 1)` = 1, so `0 = 1` fails — as a truth table run against a real naive-CHECK table
confirms. The shipped constraint was correct all along; only the reasoning was wrong, and it was wrong in a
sentence whose whole job is to stop a later session from "simplifying" the CHECK back. Recorded rather than
silently edited, because an unchallengeable-looking justification for a correct decision is exactly what
this log exists to make checkable.

**Three reasons, not one per ranker filter** (`lead_built`, `unshippable_artifact`, `surfaced`).
`hidden_hard_filter`, `hidden_non_swe`, `hidden_ineligible`, `hidden_below_cutoff` and `hidden_duplicate`
are recomputed deterministically every run and already counted in the funnel; persisting them would be
~20,000 writes a run with no reader.

---

## D-104 — Job regrouping: the survivor's job wins, and a tracked group is refused whole

**Context.** D-079 deferred the projection of dedup onto `postings.job_id` out of Slice 1, because
`applications.job_id` is the tracking key. This is that projection.

**Why it is worth doing at all**, since read-time suppression already collapses duplicates: that
suppression is completeness-gated, and D-098 established completeness is the *exceptional* state. Discover
one new posting and suppression switches off — at which point a duplicate of an already-built job carries no
disposition of its own and is built again. Regrouping makes the grouping durable in the data, so a
disposition covers the group whether or not the read-time gate is open. It is also the only thing that makes
D-081's "one application decision" claim true of the store rather than only of the read path.

**Choice.** The canonical job is the job of the survivor `resolve_duplicates` already elected under D-086
`(host_class, first_seen_at, posting_id)`. **No second election**, so a regrouping can never disagree with a
suppression about which row is authoritative.

**The refusal guard, and why it refuses the whole group.** A group is left ungrouped when any
**non-survivor** member's job carries an `applications` or `artifacts` row.
`store/run_funnel_queries.py:472` joins `applications.job_id == postings.job_id` and
`reports/export.py:73` selects `applications.job_id` as its tracked set, so a merged loser job keeps its
application row and loses every posting pointing at it — **a real applied count silently becoming wrong**,
this program's worst failure shape. `UNIQUE(job_id, attempt_no)` also means a future "move the application
too" collides the moment two members each have an attempt 1. Refusing the *whole* group rather than the
offending member is deliberate: a partially-merged group is a third state nothing downstream understands and
it makes the outcome iteration-order-dependent. A tracked **survivor** job refuses nothing, since nothing
moves off it — that is the common good case (you applied via the row dedup already elected).

Measured 2026-08-10: `applications` = 0 rows, and all 44 `artifacts` rows have `job_id IS NULL`
(`record_artifact`'s three call sites in `src/` never pass it). The guard is therefore **latent, not
unreachable** — the distinction the "dead for bundled ≠ unreachable" lesson turns on — and it ships with
tests.

**Write order.** `job_grouping_events` INSERT first, `postings.job_id` UPDATE second, one transaction: the
projection can be rebuilt from the trail, never the reverse. The UPDATE is guarded on `from_job_id`, so a
plan built against a stale read moves nothing rather than overwriting an anchor somebody else set. Loser
`jobs` rows are not deleted — `job_grouping_events.from_job_id` is a real FK to them.

**Completeness-gated for a stronger reason than the ranker's** (D-090): survivor election over a partial
corpus is backfill-order-dependent, and unlike the read path this writes that order-dependence to disk
permanently.

---

## D-105 — Identity writes move into the scan path, closing D-098 — and D-098's cost argument did not apply

**Context.** D-098: `write_identities` had exactly one caller in `src/`, the manual `identities backfill`.
Any run that discovered one new posting left it uncovered, `identities_complete()` went False, and
duplicate suppression silently switched off corpus-wide. Mit ruled the wiring was Slice 2's job.

**Choice.** Identities are computed and upserted **per posting, inside the board's existing transaction**,
in `scan/apply.py::_apply_listed`.

**D-098 priced this work at "a second corpus-wide `body_text` load beside the one `count_by_source`
already does". That price belongs to the design D-098 had in mind** — a sweep bolted onto the pipeline —
and not to this one. `_apply_listed` already holds every field `IdentityInputs` needs, so the cost is
O(postings this board listed) and no body is loaded that was not already in memory. Recording this because
D-098 has already had to correct one wrong cost figure in the same paragraph; a deferral justified by a
number deserves re-checking when the design changes.

**Not wrapped in a try/except.** A failure fails the board's transaction, so a posting and its identity
commit or vanish together — the D16 property the module is built on. A posting stored without its identity
is exactly the state that disables suppression.

**The stale-key half needs no extra work.** `_apply_listed` calls the writer on every positive
observation, which is the same trigger that refreshes title and locations, and `write_identities`' contract
is already upsert-and-delete (D-089). A retitle with an unchanged body moves the key with no revision, and
the test asserts exactly that: the stored `exact_quad` changes while `posting_versions` gains no `revised`
row.

`identities backfill` remains, for the pre-existing corpus and after an `IDENTITY_ALGORITHM_VERSION` bump.
What changed is that it is no longer the only writer.

---

## D-106 — Two consequences the build forced: what earns a permanent `skipped`, and the zero-output guard

**Only a deterministic refusal earns `skipped`.** `LeadArtifactError` — the résumé gate refusing a
shippable artifact — is deterministic: the same résumé against the same JD under the same settings refuses
identically, so re-attempting it every run costs a render and produces the same answer. The generic
`except Exception` branch in the tailor loop deliberately does **not** write a disposition: an unclassified
failure may be transient (a provider blip, an interrupted render), and a permanent disposition on a
transient fault silently deletes a real lead. This is the precision-over-recall direction the phase has
applied throughout: a leaked duplicate is counted and recoverable, a suppressed real lead is neither.

**The zero-output guard had to learn about the ledger, and this is a widening the ledger forces rather
than a weakening.** `_zero_output_guard` held that 0 leads is provably right iff
`eligible_judged_this_run == 0`. Under the ledger a run can judge genuinely new eligible postings and still
produce 0 leads because every candidate carries a live disposition — an honest empty day with a reason it
can name. Without a `hidden_handled` clause the daily driver's exit status would be **1 every day** once the
queue is caught up, which is precisely the signal destruction `PipelineSummary`'s own docstring exists to
prevent. New condition: fire iff `eligible_judged_this_run > 0 **and** hidden_handled == 0`. A run with no
handled candidates still cannot explain itself and still fires; **both directions are tested**, because
weakening a guard without a test that it still fires is how a guard becomes decoration.

**`hidden_handled` is not gated on identity completeness**, unlike `hidden_duplicate`. A stored disposition
records a decision this program already made, so it governs whether or not dedup happens to be running that
minute. Consequently `hidden_handled == 0` means zero, with none of `hidden_duplicate`'s ambiguity.

---

## D-107 — P6 Slice 2 BUILT and verified on real data; `cross_host` dereference deferred by measured absence

*2026-08-10.*

**What shipped.** `job_dispositions` + the `p6_job_dispositions` migration (now the Alembic head);
`core/ledger.py` (closed catalogs, `is_live`, `plan_upsert`); `store/ledger_queries.py` (monotonic upsert,
lazy-expiring reads, stale detection, reopen); `core/regroup.py` + `store/regroup.py` (pure planner, refusal
guard, trail-then-projection writer); identity writes in `scan/apply.py`; `seen_ttl_days`;
`pipeline/policy.py`'s `run_policy_version`; the ranker's `hidden_handled` bucket, `--include-handled` drain
and `seen` write; the pipeline's `built`/`skipped` writes and regrouping call; `boardwatch ledger
show|reopen`; `boardwatch identities regroup [--dry-run]`; and `hidden_handled` in the funnel's shortlist
stage and reconciliation identity.

**The headline claim is falsifiable and was falsified before the fix.** Measured on the live store: postings
2011, 2012, 10947, 15498 and 15499 each carry a `resume_tailored` artifact from **four separate runs**
(5, 6, 7, 9); 6 of the 18 postings ever tailored were tailored more than once, because nothing suppressed an
already-built lead. `test_a_second_run_builds_a_DISJOINT_set_of_leads` asserts the opposite end to end.
**Mutation-checked:** disabling the ranker's ledger check turns 4 of that module's 6 tests red, including
this one. Caveat kept: runs 5–7 and 9 were the Gate-P0 repeat-run evidence over one store on one day, so the
*mechanism* is measured and the daily frequency is inferred.

**Verified on an isolated COPY of the live store; the live store was never written to.**
`identities regroup` planned **186 merges across 147 groups, 0 refusals**, matching D-081/D-101's
147 groups / 186 surplus rows exactly. After applying: SQL grouping over `postings.job_id` — the
projection, whereas the planner worked from `posting_identities` + `resolve_duplicates` — reports **147 jobs
anchoring 2+ open postings, 186 surplus open postings, 186 events, 186 distinct postings moved, 0
self-merges**, and `count(distinct job_id)` fell 24,073 → 23,887, exactly 186. A second pass moved **0**
(idempotence). What that agreement does and does not show: the group *count* matching an independently
measured figure, and the exact −186 with zero self-merges, is real evidence that no merge collapsed two
groups or moved a posting twice; it is **not** evidence that the right postings were grouped, which rests on
D-101's by-eye audit.

**`cross_host` dereference is deferred by measured absence, not by judgement.** D-077 filed it under Slice
2 and D-082 left it as "the Slice 2 design question". Measured 2026-08-10 over 23,455 open postings:
**15,217 `ats`, 8,238 `unknown`, 0 `aggregator`.** There is no aggregator posting in the corpus to
dereference, so the work has no population and no test that could fail for the right reason. D-082's
re-entry path is unchanged and still correct; its trigger is an aggregator lane, which is P7, and breadth is
last.

**Gate P6 is still NOT met, and this slice was not designed to meet it.** It moves the 7-day-leakage clause
from *unmeasurable in practice* to *measurable*, because D-105 stops a single newly-discovered posting from
silently disabling suppression — without which `unique` was `None` on essentially every real run. Clauses 3
and 4 remain MET (D-100, D-101). Zero-dead-postings still needs liveness, which is Slice 3 (items 5 and 6).

**Not done, deliberately.** Slice 3's applied-state suppression and liveness. Note that item 5 has no live
population either: `applications` = 0 rows.

---

## D-108 — the decision log and the metrics log are archive-split; the reading protocol moves into the index

**2026-08-10 · a documentation-structure session, no code touched.** Mit: *"decisions.md is getting too
long I think… ingesting a long file like that every session or turn is going to fill up context and take up
more tokens than what might be needed for that task."* Measured before acting: `DECISIONS.md` 4,369 lines /
333,846 bytes (~80k tokens, 107 entries), `METRICS.md` 1,547 lines / 96,063 bytes (~24k tokens, 29 sections,
no index at all). Both grow by append and neither is ever read end to end on purpose, so the cost is paid by
every session that opens one to answer a single question. The previous session had already cut `STATE.md`
from 1,387 lines to 169 and prepended a 107-row index to `DECISIONS.md`; the index made the file navigable
but did not make it smaller.

**Choice.** Split each log into a live file and a closed archive, at the boundary where the program's
current work begins.

- `DECISIONS.md` keeps **D-077 … D-107** (P6 onward) — 1,235 lines. **D-001 … D-076** move to
  `DECISIONS-ARCHIVE.md` — 3,221 lines.
- `METRICS.md` keeps the **live** tables and the P6-era session records — 465 lines. The baseline, the
  superseded per-rule abstain table, and every session record from P0 through Gate P2 move to
  `METRICS-ARCHIVE.md` — 1,148 lines.

**`METRICS.md` is split by kind, not by position.** A positional cut at the P6 boundary would have archived
the run log and the acceptance-run table, which sit near the top of the file but are still appended to — the
acceptance run has not even started yet. Order is preserved *within* each file; only the interleaving
between them is broken, which any split does.

**The reading protocol now lives in the index, and the index spans both files** — one row per entry or
section, carrying a file column and a line number. Cross-references stay **by number** (`D-028`), never by
file, so every existing reference keeps resolving across the split without being touched.

**Both moves are byte-for-byte.** Entry and section bodies were copied, never reworded or summarised: a
summary has already discarded the details worth transferring, and `DECISIONS.md` is append-only, so an
archive-split is the only structural change permitted to it. This entry is the record that it happened.

**Proved, not asserted.** For each file, the halves were concatenated back into the original order and
diffed: `DECISIONS` 322,260 bytes, SHA-1 `472dec65…` both sides; `METRICS` 96,063 bytes, SHA-1 `adcca125…`
both sides. Entry counts reconcile — 76 + 31 = 107, and 23 + 6 = 29 sections. Every generated line number was
then read back with `sed` and checked against the heading it claimed to point at: 108/108 and 29/29 correct,
zero mismatches. The check matters because the index this replaces was itself generated once with the
positions of the pre-index file, leaving all 107 rows off by 118 — a generated number nobody checked is
exactly the kind of unchallengeable-looking figure this repo has been bitten by.

**Alternatives rejected.** *Summarise the old entries instead of moving them* — forbidden by the append-only
rule and self-defeating, since the detail is the reason the log exists. *One file per decision* — 107 files,
and a grep across them is worse than a grep within one. *Move the index into its own file* — adds a hop to
every lookup for ~2k tokens saved. *Leave `METRICS.md` alone* — same growth shape, no index, and it is where
gates are checked.

**Consequence.** A session that opens the live decision log pays ~21k tokens instead of ~80k, and the live
metrics log ~7k instead of ~24k. The archives are opened only when an old decision is actually needed. Both
archives are **closed**: new entries and new measurements go in the live files. `CLAUDE.md`'s program-document
table names all four files and points at the index, so a cold session learns the archives exist before it
learns it wanted them.

**Not done, deliberately.** `CHANGELOG.md` is 863 lines for one reason — its `[Unreleased]` section has never
been cut to a release. That is the same growth shape, but cutting a release is the owner's call, not a
documentation-hygiene decision, so it is recommended to Mit rather than taken here.

---

## D-109 — Index drift fails the gate, and the fixer lives in `tools/`

**Context.** D-108 left `DECISIONS.md` and `METRICS.md` each opening with an index spanning themselves and a
closed archive. Those line numbers are generated, and they drift on *any* edit above a heading — not only on
an append. Editing two preamble paragraphs in a single commit moved 32 decision rows and 6 metrics rows at
once. The regenerator that fixes this existed and worked, but lived in `.agent/`, which is gitignored: it was
local-only and would die with a fresh clone. So the read-first navigation aid carried numbers that nobody
checked and no clone could repair — the exact shape this repo has been bitten by before.

**Choice — the tool ships as `tools/program_index`, and drift fails the gate three ways.** `make reindex`
repairs; `make index-check` reports and exits 1 without writing; `check` gains `index-check` as a
prerequisite; and `tests/unit/test_program_index.py::test_the_real_program_indexes_are_current` asserts the
same thing under plain `uv run pytest`.

**Should drift fail a gate at all?** The options were named rather than picked silently:

1. *Fixer only, no gate.* Cheapest. Rejected: it is exactly the status quo that produced 38 drifted rows in
   one commit, minus the gitignore problem.
2. *Gate inside `make check` only.* Rejected as insufficient on its own, because drift is caused almost
   entirely by docs-only commits and it is not certain those run `make check`. **The repo contradicts itself
   here and this entry does not resolve it**: D-014 rules that "a docs-only commit is not exempt — run
   `make check` before any commit, including docs", while `STATE.md` records the practice of running
   `make generalization` alone, which is what the D-108 commits actually did. Under D-014's reading a
   `make check`-only gate would suffice; under the practice it never fires on the commit that caused the
   drift, and blames a later unrelated code commit instead.
3. *A rule inside the generalization checker.* Rejected: that checker's stated job is keeping personal and
   private content out of the repo, and `CONTRIBUTING.md` calls weakening one of its checks
   security-sensitive. Folding documentation hygiene into a security gate blurs both.
4. *A standalone `index-check` target, in `check` and runnable alone.* **Chosen, because it is correct under
   either reading of that contradiction.** It is in `check` for D-014's reading, and cheap enough (0.05 s
   warm, 0.20 s cold) to sit in the docs-only path for the practice's.

The argument against gating — that it trains people to run a fixer reflexively without reading it — is real
and is not fully answered. It is mitigated by the checker printing every row it would change
(`DECISIONS.md:D-103: 970 -> 972`) rather than a bare pass/fail, so the reflexive fix at least shows its work.

**Carrying the assertion in both a make target and a test is deliberate, not an oversight.** They share one
pure function. The target is what a docs-only commit can run in a twentieth of a second without pytest; the
test is what makes the checker mutation-checkable and what fires for anyone running the suite without `make`.

**Two conditions are reported but never repaired**: a heading with no index row, and a row naming a heading
that does not exist. Both are exit 1 in *fix* mode as well as check mode, because repairing them means
inventing a title a human owes. Drift alone is exit 0 in fix mode — repairing it is the fixer doing its job.
A duplicate heading key is likewise an error rather than a silent last-wins, which is what the prior script
did.

**Verified by mutation, derived from each test's claim, not from the implementation.** Four mutations, four
caught: never noticing a wrong number (4 tests red); dropping the rule that the index's own heading owes no
index row (3 red, including the real-docs test); never reporting an unindexed heading (2 red); and
perturbing a real index row in `DECISIONS.md` to `D-103 | 970` (the real-docs test red, `index-check` exit 1,
and `make reindex` restored the file to a byte-identical state — empty `git diff`).

**Reviewed, and the review found five defects — three of them the same root cause.** The scan had no notion
of fenced code blocks, and **these logs quote their own index rows and their own `grep -n '^## '` output
inside fences**, which the index preambles above actively instruct the reader to run. So: an illustrative row
inside a fence was rewritten as though it were a real entry, and `index-check` then demanded that edit
forever; a fenced `## ` heading became a phantom duplicate that failed the gate unrepairably *and* shadowed
the real heading's position; and because the index block was anchored to the last row-shaped line **anywhere**
in the file, one such stray line switched the missing-index-row check off for everything above it — the check
this tool exists to provide, silently disabled by the tool's own documentation style. Two more: a duplicate
heading key kept first-wins, so `reindex` could write a line nobody chose into the index before reporting the
ambiguity; and `main` printed "index is current" on a run that had just reported a problem in that file.

Fixed by reading only lines outside fences, and by defining the index as the **first unbroken run** of index
rows. Four more mutations, four caught. The row-in-a-fence test survives either single mutation because the
two defences are independent, so it was proved non-vacuous by mutating both at once (3 red). The reviewer's
original reproduction was then re-run against a copy of the real `DECISIONS.md`: the quoted example row is
untouched, and the genuinely-unindexed heading below it is now reported instead of suppressed.

**The lesson generalizes past this tool.** A tool that reads the repo's own documentation must model that
documentation's conventions, and the convention most likely to break it is the one the document uses to
explain itself.

**Consequence.** `STATE.md`'s carried-gap row for this is closed. `.agent/tools/reindex_program_docs.py` is
deleted, so there is one copy rather than two that can diverge.

---

## D-110 — The Slice 2 review: only a caller that delivers a lead may consume the queue

*2026-08-10. The owed fresh-context review of `origin/main..main` (Slice 2, D-108 and D-109), run before
anything was pushed. Four independent reviewers — a diff reviewer, a docs-only reviewer, a ranker-callers
tracer and a schema/hot-path auditor — plus this session's own reading. Every finding was checked against the
code before being acted on.*

**The root cause, stated once.** D-103 records Mit's ruling that a surfaced lead is recorded `seen` and
suppresses for a TTL. That ruling was implemented by making **every** `rank_open_postings` call consume the
queue — and three of the four production callers deliver nothing to anybody. The ruling is not being
re-litigated; it is being applied to the act of *delivering a lead* rather than to the act of ranking.
`rank_open_postings` gains `record_surfaced` (default unchanged, so a caller that forgets is still the noisy
direction) and now always reports `surfaced_job_ids`, so a caller that opts out can record the decision at
the point it genuinely takes one.

**Three callers were consuming a queue they had no business consuming.**

- `eligibility gate request` suppressed the whole shortlist it had just built for judging. The skill doc's
  stated next step is `boardwatch run`, which then shortlisted **0** for the whole TTL, so the verdicts never
  reached an artifact. The handshake silently defeated itself, and the widened zero-output guard reported no
  fatal. Now `record_surfaced=False`.
- The pipeline wrote `seen` **before** the tailor loop, putting the suppression on the wrong side of the
  render. A missing `tectonic`, an invalid persona or a Ctrl-C between the two hid every shortlisted lead for
  seven days with nothing built, and the unattended runner's documented retry re-ranked into an empty
  shortlist and called it an honest empty day. `runner.py`'s own comment asserted the opposite — "a crash
  between the render and this write leaves the job undisposed, which over-shows it next run. That is the safe
  direction" — which was false the moment the ranker became the writer. All three tiers are now written after
  the loop by `_record_shortlist_dispositions`, and the `seen` tier is gated on the stage completing. The
  permanent tiers are not, because each names work that actually happened.
- `bwd` ranks twice a day — once to display, once as `--json` to drive the build — so the display call
  suppressed the rows the build call was about to request. It printed "nothing new to build" and built **zero
  folders**, every day for seven days. `top --no-record` is the operator-facing escape hatch and `bw-daily`
  uses it for the display call. (`.agent/` is gitignored, so that edit ships with nothing; it is recorded
  here because the *defect* was in shipped behaviour.)

**A transient render failure was permanently deleting real leads.** D-106 justified the permanent `skipped`
with "the same résumé against the same JD under the same settings refuses identically". That is true of
`PAGE_LIMIT_EXCEEDED` and false of `COMPILE_FAILED` and `BINARY_MISSING`, which `evaluate_compile` maps to
`shippable=False` *identically* to the page limit. A non-zero `tectonic` exit — cold support-file cache with
no network, disk full, OOM, killed subprocess — therefore buried every lead on the shortlist forever. Two
things made it unrecoverable rather than merely wrong: the drain cannot find these rows, because **no
`policy_version` component covers the résumé or `resume_max_pages`** (the stamp is the run manifest's five
fields, and `profile_row_hash` hashes only the five columns the *ranker* reads), so D-103's stated accepted
cost — "stays suppressed until somebody runs the drain" — was false; and `LeadArtifactError` carried only a
formatted message, which CLAUDE.md forbids classifying by string-matching. Fixed by typing both gate reasons
onto the exception at the raise site and gating the disposition on a closed
`DETERMINISTIC_GATE_REFUSALS` catalog. Out-of-catalog is treated as environmental — the fail-open direction
for a real lead.

**Regrouping was reintroducing the very defect this slice removes.** A disposition is keyed on a job.
Regrouping moves postings *off* a job onto the survivor's, and nothing moved the decision, so a `built` row
was left governing a job nothing anchors while the canonical job carried nothing — and the already-built lead
was surfaced and tailored again. Reproduced in an isolated store before the fix and after. `protected_job_ids`
could not catch it: it checks `applications` and `artifacts`, and `artifacts.job_id` is NULL on all 44 live
rows. `apply_merges` now carries the decision forward through the monotonic upsert (so the strongest decision
in the group wins and a canonical job already `built` is untouched) and stamps the emptied row `reopened_at`
rather than leaving a live row on a job with no postings — a quarantine with no re-entry path, which CLAUDE.md
forbids outright.

**Alternative rejected:** refusing the merge whenever a member carries a disposition, mirroring the
`tracked_job` guard. Rejected because it would permanently refuse exactly the groups the projection exists to
fix (D-104's motivation is a duplicate of an *already-built* job), whereas a disposition — unlike an
`applications` row — has no `UNIQUE(job_id, attempt_no)` to collide and corrupts no applied count.

**One reviewer argued this was unreachable and was half right.** The argument: `exact_quad` is keyed on
`company_id`, a company's postings share a host, so survivor election reduces to earliest `first_seen_at` —
which is the member most likely to hold the disposition, and it survives. That holds for the common case and
breaks on a reopen: a posting that was closed when its duplicate was built re-opens, wins election on the
earlier `first_seen_at`, and the built member becomes the loser. The fix is taken regardless, because the
stranded live row is a leak in *both* directions.

**Two display defects that turn a legitimately empty day back into a silent one.** `_shortlist_line` omitted
`hidden_handled` while `_zero_output_guard` had been widened to stop fataling on it, so the operator's one-line
summary read "0 shortlisted of 400 considered (0, 0, 0, 0)" and exited 0 — counts that visibly fail to
reconcile. And `top --json` returned before every notice, so a script got `[]` with no reason at all. Both
named now; the funnel artifact already carried the bucket, which is why this survived to a review.

**D-103's own justification for the permanence CHECK was wrong, in three places.** It claimed the naive
biconditional `(disposition IN permanent) = (policy_version IS NOT NULL AND expires_at IS NULL)` admits "a
`seen` row carrying a policy stamp and no TTL (0 = 0)". A truth table run against a real naive-CHECK table
shows that shape is **rejected** (LHS 0, RHS `1 AND 1` = 1). What it actually admits is `(seen, NULL, NULL)` —
a `seen` row with no TTL, which suppresses **forever** and which `stale_dispositions` cannot even list,
because that read keys on a non-NULL `policy_version` — and `(seen, stamp, TTL)`. The shipped constraint was
correct all along and rejects all 12 malformed shapes on both an Alembic-migrated and a `create_all` database,
verified by raw `INSERT`. Only the reasoning was wrong, and it was wrong in the sentence whose job is to stop
a later session from simplifying the CHECK back. Corrected in `DECISIONS.md`, `tables.py` and the migration's
prose (the frozen SQL literals are untouched — correcting a comment changes no history).

**Also enforced flat, and now said so:** the DB checks the reason catalog as a *union*, so a direct `INSERT`
can pair `built` with `surfaced`. `core.ledger.validate` rejects it and no code path bypasses that, so
"enforced twice" holds for inventing a bucket and not for mispairing. Left as-is rather than tightened, which
would cost a migration for a hole no caller can reach.

**Accepted without change, with the reason recorded.** `record_disposition` is a read-modify-write with no
lock, so two simultaneous processes can race; SQLite/WAL rolls one back rather than silently losing an update,
and single-writer is the program's standing assumption (P3 item 8 owns the two-writer question).
`reopen_jobs` passes an unbounded `IN` list where `load_dispositions` documents the 32,766-parameter cap — 
unreachable at 24,073 jobs, and worth knowing before the corpus grows. `NoResultFound` from the new
per-board company-name query would abort the whole scan rather than one board, but nothing in `src/` deletes a
company.

**Three tests were passing for the wrong reason** and are reconciled: two ranked twice and had their
assertions satisfied by the ledger hiding a row rather than by the mechanism under test (one of them
explicitly comments "same three postings both times", which had become false), and the perf benchmark ranked
seven times, measuring a mutating sliding window plus 10 ledger writes per iteration inside the measured
region. All three now rank with `record_surfaced=False`.

**Mutation-checked, not assumed.** Ignoring the fatal in the `seen` gate, restoring `gate request`'s consume,
and recording `skipped` for every `LeadArtifactError` each turn the corresponding new test red. Also: this
session lost four uncommitted `runner.py` fixes to a `git checkout` during mutation testing — the exact trap
already recorded — and re-applied them. **Commit before mutating; the note is there because it keeps happening.**

**Not resolved here, still Mit's:** the funnel-write swallow, and whether any family beyond `work_auth`
defaults to `blocker`. Untouched deliberately.

---

## D-111 — P6 Slice 3: applied-state suppression, and liveness sized to what the corpus actually is

*2026-08-10. `PROGRAM.md` §3.P6 items 5 and 6, the last two items of P6's build. Both were measured
against the live store before being designed, and one of the two shipped smaller than the spec because
the measurement falsified the spec's premise.*

**Item 5 — applied-state suppression — is a mechanism with no live population, and that is recorded
rather than hidden.** `applications` and `application_events` are both 0 rows; `track` has never been
used. So the tests are the evidence for this item, and they are written against the boundary that
decides it rather than the happy path.

The ranker gains a `hidden_applied` bucket, read straight from `applications` and keyed on the canonical
job, exactly as `protected_job_ids` already reads it for regrouping. **Not mirrored into a ledger
disposition:** an application is the operator's own record, taken outside the program, and giving one
fact two homes creates a pair that can disagree — with only one of them carrying a drain the operator
knows about.

**The suppressing set is `APPLIED_STATUSES`, reused rather than re-declared**, and moved to
`store/applications.py` beside `ApplicationStatus` so the catalog has one home. The two callers ask the
same question: the funnel counts these as conversions, the ranker suppresses them, and a status that
should not count as a conversion is exactly one that should not suppress a lead. `interested` therefore
does not suppress — it is `track add`'s default, so suppressing it would mean *tracking a lead hid it* —
and neither does `withdrawn`, which is what makes `track status <id> withdrawn` the drain, on both sides
of the gate as the standing invariant requires.

**Applied is checked BEFORE the ledger.** A job that is both applied-to and `built` is counted as
applied. Not cosmetic: `ledger reopen --job` releases the ledger row and nothing releases the
application, so the funnel reports the count that survives the drain a reader is deciding whether to run.

**Item 6 — liveness — ships the re-fetch and NOT the closed-phrase catalog, because the corpus
falsified it.** PROGRAM item 6 names "a saved body containing a closed phrase" as the AUTHORITATIVE
signal. That premise is inherited from job-apps, which scraped HTML pages. boardwatch reads structured
ATS APIs, and every provider assembles `body_text` **only from employer-authored description fields of
a JSON payload** — one field for greenhouse, ashby, workable and workday; two joined for lever
(`descriptionPlain` + `additionalPlain`); three for smartrecruiters (`jobDescription`, `qualifications`,
`additionalInformation`). No provider ever sees the rendered careers page, so page chrome — the "no
longer accepting applications" banner a scraper would read — is **structurally incapable** of reaching
that column. (An earlier draft of this entry said "the description field alone", which the docs review
falsified on lever and smartrecruiters; the conclusion is unchanged because what matters is *payload
field, never page chrome*, not the field count.)

Corroborated by measurement, not left as an argument. A nine-phrase candidate catalog run against the
live store matched **11 of 23,455** open postings and **all 11 were false positives**: two Workday
boilerplate conditionals ("If the job posting is no longer available then all roles have been filled"),
one location restriction ("we are not accepting applications of candidates outside of New York"), and
eight job descriptions for roles that process purchase requisitions. A high-precision catalog would match
**0** rows. So the choice was between shipping a catalog that suppresses 11 live leads to catch none, and
shipping one with no population at all; both fail CLAUDE.md, and the reasoning plus the re-derivation
query live in `core/liveness.py`'s docstring where the next session will find them.

The earlier "3 open postings contain a closed phrase" figure is **superseded**, not merely
unreproducible: it was recorded without its catalog, and the number that matters was never its size but
its precision.

**One provider does expose a native liveness flag, and it is NOT coverage for this gate.**
`providers/smartrecruiters.py` drops a posting whose detail payload says `active is False`. That is what
"authoritative" would look like on an API corpus — but it fetches detail payloads only for postings **not
already in the store**, and only within `detail_fetch_budget`, so for the entire population liveness is
about (postings already stored and being ranked) the flag is never re-read. A first-discovery filter on
1 of 6 providers. An earlier draft of this entry cited it as though the authoritative signal were already
covered; the docs review corrected that.

**What ships: a re-fetch at the lead list, 404/410 only.** `core/liveness.py` holds the pure decision and
its two closed catalogs; `pipeline/liveness.py` probes through the existing politeness `Fetcher`
(identifying UA, per-host pacing, host locks) with `retry_attempts=1`, because a retry buys nothing when
the unknown answer is already safe. The stage sits between the ranker and the tailor loop — the last
point at which a posting is still only a candidate, and the point Gate P6's clause is about.

**Fail-open is the design, and 403 is why.** A 12-URL probe on 2026-08-10: `pinterestcareers.com`
answered **403** to an unfamiliar user agent for a perfectly live posting, so reading 403 as gone would
silently blacklist whole employers. Only an explicit gone-status withholds; timeout, 403, 5xx, redirect
and a NULL URL are all served. The cost of a dead lead is one wasted résumé; the cost of a withheld live
one is a job nobody can know they missed.

**Recall is low and that is stated rather than discovered.** Of 8 already-closed postings, only **1**
answered 404 — Workday and Ashby serve 200 for a requisition dropped from the listing. The probe is a
supplement to the scanner's board-absence rule (`CLOSE_AFTER_MISSES = 2`), never a replacement: **0**
open postings are stale beyond even 7 days, which is direct evidence that rule already works. What the
probe covers is the window between a requisition closing and the next complete scan — the 216 open
postings sitting at `consecutive_missing = 1`. The same probe did find a genuinely dead OPEN posting
(`jobs.lever.co/palantir/…`), which is the case the window is about.

**Liveness is never cached, and "never" includes `postings.status`.** A `dead` result withholds the lead
from that run only. Writing the status would let one 404 from a flaky CDN retire a live requisition
permanently — and irreversibly, because a closed posting stops being ranked and so stops being probed.
That is a quarantine with no drain, which CLAUDE.md forbids outright. The scanner reopens on its own; the
probe must not compete with it.

**Three seams handled during the build — and the review found two more, so the "handled rather than
found" framing was wrong and is corrected here rather than left standing.** A withheld posting is (1) dropped from
`surfaced_job_ids`, because it was delivered to nobody and must not consume the queue — the D-110 rule
applied to a new filter; (2) subtracted before the "every lead failed to tailor" fatal, which would
otherwise report a dead board as a broken résumé path; and (3) removed from `_cohort_guard`'s cohort
rather than added to its accounted set, because it is a **third** terminal state and folding it into
either "lead" or "render failure" makes one of those counts a lie. `_zero_output_guard` gains a
`dead_leads` clause for the same reason it gained `hidden_handled` (D-105): liveness working perfectly
must not read as the silent empty day it exists to prevent. The widening stays narrow — a run with
nothing handled and nothing dead still cannot explain itself, and still fires.

**The prober is injected, and `None` means UNMEASURED.** The funnel emits nulls and
`instrumented: false`, never `0 dead` — the D-022/D-023 rule. Injecting it makes *which URLs get probed*
the caller's decision; `run --no-check-liveness` is the operator's opt-out. It does **not** make the
pipeline offline — the scan stage fetches every configured board and is by far its largest network
consumer, so `--no-scan` is the offline switch, not this. (An earlier draft claimed `run_pipeline` "does
no network I/O of its own"; the docs review falsified it.) `unknown` is
reported beside `dead` rather than folded into `alive`, because a run whose probe learned nothing looks
identical to a healthy one if you read only `dead`. Artifact version **4**.

**Alternative rejected: probing in `rank_open_postings`.** It would put network I/O in a path that is
pure DB by design and is called by `top` and by `eligibility gate request`, neither of which delivers a
lead — the same category error D-110 corrected for the `seen` write. It would also probe the whole
shortlist on every interactive `top`.

**Alternative rejected: a new `Settings` field for the probe.** A settings field would have to be
classified in `reports/manifest.py` and pinned in `snapshots.py`, and if classified config-relevant it
would move `config_hash` and stale every permanent disposition. Injecting the prober costs none of that,
and the CLI flag covers the only case an operator has.

**Mutation-checked, not assumed.** Widening `GONE_STATUSES` to include 403, dropping the gone-status
branch from the `FetchFailure` path (which is the path that actually runs, since `Fetcher` raises for
every non-200), leaving a withheld lead in `surfaced_job_ids`, and writing `status='closed'` on a dead
probe each turn the corresponding test red. On the item 5 side: disabling the lookup, widening
`APPLIED_STATUSES` to include `interested`/`withdrawn`, moving the applied check after the ledger, and
dropping the funnel `Drop` all turn a test red.

**The review, and what it caught.** Three in-session reviewers — a diff reviewer, a test-quality auditor
and a docs-only reviewer. **Two BLOCKERs, both found by RUNNING the code rather than reading it**, which is
the transferable lesson.

1. **The funnel stopped reconciling whenever liveness did its job.** The tailor stage enters at
   `shortlist.shortlisted`, advances at `tailored`, and its only drop was `tailor_failed`. A withheld lead
   left a gap in a stage that is deliberately not `derived`, so any run that withheld anything emitted an
   artifact stamped DOES NOT RECONCILE — the feature working correctly would have broken **Gate P0's**
   "three consecutive runs that reconcile to 100%" clause. Fixed with a `withheld_not_live` drop. The
   lesson generalises: a filter added *after* ranking has to be mirrored into the funnel stage it removes
   rows from, not only into the stage that produced them.
2. **An all-applied day re-armed the zero-output guard**, above. A regression this slice introduced, not a
   pre-existing gap.
3. **`build_prober` — the whole production probe path — had no test.** Every other liveness test injects a
   fake, so the URL was unasserted and, worse, anything that stopped `FetchFailure.status_code` arriving as
   an `int` would have made `status_code in GONE_STATUSES` permanently False: the probe finds nothing,
   forever, with the suite green. That is this repo's silent-None class. Now driven through respx against a
   real `Fetcher`, asserting the URL, the no-retry claim, and 404/403/500/transport-error handling.
4. **`run --check-liveness`'s wiring had no test**, so flipping its default would have shipped liveness dead
   on arrival. Likewise `_shortlist_line`, the operator's one-line summary, which had never had one.
5. **A new drop bucket has SIX hand-maintained mirror sites, not three** — two successive reviews corrected
   that number upward. Only three are checked by anything; `_shortlist_line` is checked by nothing, and is
   now covered by a test instead.
6. **Four documentation claims were false and are corrected in place** rather than quietly edited: the
   provider `body_text` absolute, the SmartRecruiters coverage claim, "`run_pipeline` does no network I/O
   of its own", and a `runner.py` comment asserting the zero-output guard is only reachable when
   `shortlisted == 0` — which this slice itself made false.

**The `git checkout` trap fired again, and the recorded lesson was too narrow.** "Commit before
mutation-testing" was followed for the first round; the review fixes were then written, mutation-tested,
and two of them were destroyed by the `git checkout` that reverts each mutation. The rule is not "commit
before you start mutating" but **"commit before every mutation round"** — any uncommitted edit is in the
blast radius, including one written five minutes earlier. Caught because the suite went red immediately
afterwards; had the fixes been less well covered it would have shipped a reverted fix under a green gate.

**Gate P6 is unchanged by this entry on its own.** The "0 dead postings reaching the lead list" clause is
now *buildable* and *measurable*, which it was not; meeting it needs a real run whose leads are probed.
Duplicate leakage still needs its 7 days.

**Not resolved here, still Mit's:** the funnel-write swallow, whether any family beyond `work_auth`
defaults to `blocker`, and whether docs-only commits owe a full `make check`.

---

## D-112 — 0.3.0 is cut, the changelog gets ONE triple, and the tag is the owner's to push

*2026-08-10. Release mechanics, recorded because two of the three parts are conventions a later session
will otherwise re-break.*

**`[Unreleased]` had accreted 14 subsections** — `Added` ×5, `Changed` ×5, `Fixed` ×4 — because each
session appended a fresh triple rather than adding to the existing one. Nothing was lost, but the section
was unreadable and would have shipped that way. **The convention from here: one `Added` / `Changed` /
`Fixed` triple per release section, newest bullet first within each. Add to the existing subsection; never
append a new one.**

**How the merge was verified, because "I read it and it looked right" is the failure mode this program
keeps paying for.** Split on the `###` headers, re-concatenate per category preserving order, then assert
the count of top-level bullets is **identical before and after** (70), and refuse outright if any content
sat outside a subsection where the merge would silently drop it. Boundaries were located by content
(`## [Unreleased]`, the next `## [`), never by hardcoded line numbers, which drift.

**Release-readiness was checked through a different path than the one that produced it** (CLAUDE.md).
`make check` proves the source tree; it does not prove the artifact. So the wheel was built, installed into
a **fresh isolated venv**, and asked its own version (`0.3.0`) and for the two new flags
(`top --include-applied`, `run --no-check-liveness`) — which is how you learn that what ships is what was
written, rather than trusting the build.

**The tag is NOT pushed, and that is deliberate.** `.github/workflows/release.yml` fires on `v*` and
publishes to **PyPI, GHCR and GitHub Releases** in one step. A PyPI version, once taken, cannot be reused
even after deletion, so the tag push is the single irreversible act in this repo and belongs to the owner.
Preparing the release and performing it are separate, and only the first is automatable.

**A prediction made here was wrong, and the correction is the useful part.** This entry originally said
`release.yml` would "queue forever rather than publish", reasoning that it runs `make check` on
`ubuntu-latest` — the same pool the standing CI failure names. Mit pushed the tag and **the release
workflow acquired a runner within seconds**. So the CI failure is specific to `ci.yml`, not repo-wide, and
generalising it was an inference from one workflow presented as a property of the account. The tag
(`v0.3.0` → `426f45c`) was still in `build + smoke test` ~13 minutes later with PyPI answering 404, so the
*outcome* remained unconfirmed when the session ended.

What survives the correction is the verification rule, which was right for a different reason:
**verify a release on PyPI, GHCR and the Releases page — never in the Actions tab**, and never read a
silent or still-running workflow as a successful publish. Check `status`, not mere presence.

**And the release then FAILED, which is the most useful thing this session produced.** Run `31412535583`
died in `build + smoke test` with **33 failures**, every one `tectonic binary not found on PATH` or
`_pdf_page_count` returning None (it shells `pdfinfo`). The three publish jobs were correctly **skipped**,
so nothing uploaded and no PyPI version is burned — the gate on the most irreversible action did exactly
its job.

**The cause is a three-day-old hole that only a working runner could reveal.** Tectonic became a hard
dependency in D-058/D-060 (`e9c0393`, 2026-08-07), *after* v0.2.0 was tagged on 2026-08-04. The
`Dockerfile` installs `tectonic@0.17.0` and `poppler-utils`; **no workflow installs either**. It stayed
invisible because CI was not acquiring runners, so `make check` on a machine where Mit has tectonic
installed was the only thing ever run. `ci.yml` runs on `5f0150d` and `101bc67` — both predating this
session — fail identically, which is the proof it is not a Slice 3 regression.

**The standing lesson, sharpened.** "The local gate is the only authority" was recorded as a temporary
inconvenience of the runner outage. It was also *hiding a real defect for three days*: an
environment-dependency gap is precisely the class a local gate cannot catch, because the local
environment is the thing that differs. When CI is dark, the risk is not just "less signal" — it is that
the missing signal is systematically the environment-shaped kind.

**Not fixed here, deliberately, because it is a scope decision and not a typo.** `ci.yml` runs a 3-OS
matrix (ubuntu/macos/windows × py3.11–3.13) and tectonic + poppler on Windows is awkward. The options are
(a) install on all three, (b) install in `release.yml` and an ubuntu-only test lane, or (c) skip the
tectonic-dependent tests when the binary is absent. **(c) must not be taken by default**: it would leave
CI green while silently no longer verifying P1a's hard résumé gate, which is the exact "a check that does
not run must report *not measured*, never pass" rule this program is built on.

**Cutting the release is what surfaced that the user-facing docs still described Typst.** D-058/D-060
replaced Typst with tectonic eleven decisions ago, and the program docs were updated — but `README.md`
still told users the renderer "shells out to a local Typst install if present", offered a `--format typst`
flag that **does not exist** (the real value is `latex`, and it is the only adapter), described the PDF as
"best-effort" when P1a made it a hard gate, and named the output pair `.{typ,pdf}` when it is `.{tex,pdf}`.
`docs/configuration.md` repeated the same path. The 0.3.0 changelog also described the P1a gate in Typst
terms — an interim state **no user ever saw**, since 0.2.0 shipped Typst and 0.3.0 ships tectonic.

This is [[retracting-a-claim-means-grepping]] again in a new place: the retraction swept `src/` and
`docs/program/`, and stopped at the two files a *user* actually reads. **A release is the moment those
files are republished** — PyPI renders `README.md` as the project description — so "does the README still
describe the shipped system?" belongs in the release procedure, not in the changelog pass. The remaining
`typst` strings are deliberate: the *Changed* entry explaining the swap, and the persisted meta key
`typst_pdf_built`, whose legacy name is documented rather than renamed.

**And checking one README claim found a real defect: `config show` did not print every key.**
`_SCALAR_KEYS` in `cli/config_cmd.py` is a hand-maintained mirror of `Settings`, and it covered **4 of
10** scalar fields. `show` did not print the other six and `set` rejected them as unknown, so the only
way to change them was to hand-edit `config.toml` — precisely what P11's settings surface exists to
avoid. The worst of them is **`seen_ttl_days`**, which P6 ships in this very release as the knob
governing how long a surfaced lead stays suppressed. Fixed, and **a test now asserts the registry equals
the scalar `Settings` fields** — which immediately found a sixth (`busy_timeout_ms`) that I had missed
after listing five by hand.

That is the **third hand-maintained mirror to bite in one session**, after the ranker's drop buckets
(six sites, three checked) and the funnel's tailor stage. The pattern is worth naming: this repo
repeatedly pairs a closed catalog with a second list that must agree with it and has no detector.
`reports/manifest.py` already gets this right with `_assert_exhaustive`; the fix each time is to copy
that, not to be more careful.

**The README roadmap's "Next" list was fully ticked**, so it promised nothing while looking like a plan —
the same defect the 0.2.0 release commit fixed once already, which is why it is recorded this time.
Replaced with the three genuinely-next items, and breadth is stated as **conditional** on the other two
rather than as a queued feature, because CLAUDE.md's "breadth is last" is a constraint on the roadmap and
not only on the code.

---

## D-113 — The Slice 3 external review: a followed redirect can forge a gone-status

*2026-08-10. Mit ran the fresh-context review of Slice 3 through Codex, against the real
`5f0150d..18bfecc` range. Three findings, all real, all fixed here. Recorded because one of them is a
class this program will meet again — a fail-open contract stated in a docstring and quietly voided by a
library default two modules away.*

**The finding that mattered: `Fetcher` is constructed with `follow_redirects=True`.** `core/liveness.py`
says only an explicit gone-status withholds a lead and lists "a redirect to a careers homepage" among the
outcomes that are served. That was true of the redirect *itself* and false of where it leads. The client
follows the chain and reports the **final** status, so a stored posting URL answering `302 → 404` arrives
at `verdict_for_failure` as a bare 404 with no trace of the hop — indistinguishable from the posting
itself being gone, and withheld. The realistic shape is an employer migrating ATS: old links point at a
new host whose deep-link path 404s while the requisition is live at a new URL. Every one of that
employer's leads disappears, and the 404 in the detail string looks conclusive to whoever checks.

**Fixed by carrying the fact, not by guessing at it.** `FetchFailure` gained `redirected`, set from
`response.history` at the only raise site that can carry a gone-status (the retry-exhausted raise carries
only 429/5xx, and the two transport paths carry no status at all); the probe forwards it; and a gone-status
that arrives redirected is `unknown` under its own signal, **`refetch_gone_after_redirect`**. A separate
signal rather than folding it into `refetch_error` — the two answer different questions, and a bucket
that cannot be counted cannot be audited. The parameter is keyword-only and defaults to `False`, so a
caller that cannot establish a redirect gets the stricter reading of its own evidence rather than a
fail-open it never earned ([[defaulted-param-backfills-every-caller]] is about the opposite default, and
the direction was chosen with it in mind).

**Only the real client could have caught this.** Every other liveness test injects a fake prober, and a
fake prober never redirects. Reading `verdict_for_failure` in isolation shows a flag with no evidence
anything ever sets it. The new test drives the actual `Fetcher` through respx with a two-hop chain and
asserts the second route was called — otherwise it would pass while proving nothing. That is D-111's
lesson arriving a third time: **reviewers and tests that RUN the code find what reading cannot.**

**Second finding: `Liveness` validated its two catalogued fields independently.** `verdict` had to be in
`VERDICTS` and `signal` in `SIGNALS`, and nothing checked that they agreed — so
`Liveness(42, "dead", "refetch_error")` constructed happily and withheld a posting that merely timed out,
inverting the fail-open direction at a call site while every membership check passed. The pair is fully
determined, so it is now expressed that way: `SIGNAL_VERDICTS` maps each signal to the one verdict it
carries, `__post_init__` rejects anything else, and `ContradictoryLiveness` is its own exception class
because "the catalog is missing an entry" and "a call site built something the catalog forbids" need
different answers. `test_only_dead_withholds` now iterates the mapping rather than the verdict tuple —
a verdict no signal carries can no longer be built at all.

**Third finding, and it was wider than reported.** `top` returned immediately after "no open postings
match your filters" whenever nothing was visible and the ineligible and non-software buckets were empty —
before the notices, which all sit after the table. Codex named the applied bucket; the same early return
swallowed **`hidden_duplicate` and `hidden_handled` identically**, so fixing only what was reported would
have left two silent drains. Suppression that empties the list is precisely when the operator needs the
reason, and what they got instead asserts the corpus is empty. The notices are now extracted and called
from both exits.

**And the `--json` path was NOT already correct, which this entry originally claimed.** It printed its
notices *before* returning — the half the human path got wrong — but named only the handled and applied
buckets, so a script whose array was emptied by duplicate suppression got `[]` with no reason and no
drain. Two paths, opposite halves of one defect, each fixed once and separately. Both now call the same
helper, so a bucket added in one place reaches both.

**The reusable shape of all three: a rule stated in one module, enforced nowhere.** Fail-open lived in a
docstring while `follow_redirects` lived in another file; the verdict/signal pairing lived in a comment
while validation checked the fields apart; the drain contract lived in `CLAUDE.md` while the early return
decided it. Each fix moves the rule into something that fails — a forwarded flag, a total mapping, a
single call site.

**One limitation, measured and accepted.** The rule keys off "a redirect happened", not "a *different
resource* answered", because `response.history` is what the client exposes. So an `http→https`,
trailing-slash or `www.` canonicalization also forgives a 404 that was authoritative. Measured against the
live corpus (24,073 postings) there is **no host today that both redirects and 404s**: `jobs.lever.co`
(655 open) 404s directly and still withholds, `boards.greenhouse.io` (673 open) redirects but answers 200
for dead requisitions, workday and ashby answer 200. So this is a latent coverage loss with no instance,
and it errs in the direction this gate has chosen. Comparing the final URL to the requested one modulo
scheme/host/slash would close it and is not worth the machinery until a counter says otherwise — which is
now possible, because there is a counter.

**Verification.** Four mutations, one per claim, each derived from the test's stated claim and run after
committing ([[mutation-testing-lies-two-ways]]): the redirect rule ignored, `redirected` never set by the
Fetcher, the coherence check disabled, and the empty-result notice call deleted. All four CAUGHT. The
second is the one that matters — it is the only one that proves the plumbing rather than the decision.

**Then two in-session reviewers, run on the fix itself, found three more things** — which is the argument
for reviewing a review's fixes. Both independently flagged that the new signal was counted nowhere (fixed
above). The code reviewer additionally reproduced, by building a real sdist, that the CI action's first
form wrote tectonic's ~43 MB bundle cache **inside the workspace**, where `release.yml`'s `uv build` would
have swept it into the published source distribution — irreversible on PyPI, and caught only because a
reviewer built the artifact instead of reading the YAML. The docs reviewer found that re-pushing `v0.3.0`
unmoved would re-run the identical failure, since that tag names a commit without the fix, and that
`doctor` probed for `tectonic` while `pdfinfo` — equally fatal, and silently so — went unchecked.

---

## D-114 — CI installs tectonic and pdfinfo on all three OSes; skipping the gate was refused

*2026-08-10. The scope decision D-112 left open, taken by Mit. Recorded because the reasoning generalizes
past this one dependency.*

**The choice was between three options and the cheap one was disqualified on principle.** (a) install on
ubuntu, macOS and Windows; (b) install in `release.yml` plus an ubuntu-only test lane, narrowing the
matrix; (c) mark the 33 tectonic-dependent tests to skip when the binary is absent. **Mit chose (a).**
(c) is a one-liner and would have turned CI green immediately — while P1a's hard résumé PDF gate stopped
being verified anywhere except Mit's laptop, and CI reported success for a suite that no longer ran it.
"A check that did not run must report *not measured*, never *pass*" is the rule the whole instrumentation
phase was built on; it does not stop applying at the CI boundary. (b) was a real option and was rejected
for coverage: `tectonic` and `pdfinfo` are the two places where behaviour is most plausibly
platform-dependent, so an ubuntu-only lane would drop the check exactly where it earns its keep.

**One composite action, `.github/actions/setup-typesetting`, not three copied blocks.** It is used by
`ci.yml`'s matrix job and `release.yml`'s build job — the second is why the release failed at all — and
keeps the version pin in one place. Note it is nonetheless the **fourth** hand-maintained mirror this
week: `TECTONIC_VERSION` in the `Dockerfile` and the action's default input are one fact in two files with
no detector. Benign if they drift (both versions work) and called out in the action so the next person
sees it.

**Four things were verified rather than assumed, and three of the four contradicted the obvious guess.**
The Linux **gnu** build is dynamically linked against `libgraphite2.so.3` and would not start on a bare
`ubuntu:24.04` container; the **musl** asset ran there with no extra packages. Stated precisely because
the runner image's package set was never enumerated — the gnu build might well work there. musl makes
the question moot, which is why it was chosen over answering it. Chocolatey's `poppler` package ships the poppler **source tarball**, 891 files
with zero executables, so it cannot put `pdfinfo` on PATH at all; Windows takes prebuilt binaries from a
pinned `poppler-windows` release instead. That release's tag (`v26.02.0-0`) and the directory inside its
zip (`poppler-26.02.0`) **do not match**, so the bin path is globbed rather than derived by string
surgery. And tectonic's own source comments give the wrong cache directory for at least two of the three
platforms — disproved by running the binary — so `TECTONIC_CACHE_DIR` is set instead, collapsing three
uncertain paths into one the cache step can name.

**The install step ends by compiling a real document and reading its page count back.** A `--version`
check proves a file exists and is executable; it does not prove tectonic can fetch its bundle and produce
a PDF, which is the thing 33 tests depend on. Compiling proves the deliverable through a different path
than the one that produced it, and it converts a broken install from 33 puzzling failures deep in the
suite into one red step that names the cause.

**It has now run, and option (a) is validated on all three OSes.** Run `31421520836` on `cefd13e`:
ubuntu ×3 and macOS ×3 fully green, and on Windows ×3 the install step **succeeded** — 3,922 tests
passed there, including every tectonic and `pdfinfo` test. The 33 failures are gone everywhere. The
research that preceded it earned its keep twice: the musl-over-gnu choice on Linux and the refusal of
Chocolatey's executable-free `poppler` were both discovered by running things, not by reading asset names.

**And clearing it revealed the next failure, which is the point of a gate that had been dark.** Windows
failed one test — `test_the_real_program_indexes_are_current` — reporting all 114 index rows as having no
heading. The index was fine. `read_text()` with no encoding uses the locale's, cp1252 on that runner, and
decision headings are matched on `## D-113 — `; the em-dash decoded to mojibake so nothing matched. A
decoder fault wearing a corrupt-index message. Fixed with explicit `encoding="utf-8"` on both reads and
`newline="\n"` on the write, and pinned by running the tool under `-X warn_default_encoding -W
error::EncodingWarning` — which catches any unencoded access added later, on any platform, rather than
today's two call sites.

This is the environment-shaped defect class exactly as predicted in D-112: **three days of a dark CI hid
the tectonic gap, and the tectonic gap in turn hid this one.** A local gate cannot find either, because
the local environment is the thing that differs. Two layers deep is worth noticing — clearing one
environment failure does not mean the next signal is clean, it means the next one is finally visible.

**What the first push did NOT prove.** Asset layouts, checksums and
the Linux and macOS binaries were verified locally; the Windows commands are constructed from a verified
zip layout, not from a green run. **The first push is the experiment**, and the release must not be
re-tagged until `ci.yml` is green on all three OSes — re-tagging on the strength of a plausible-looking
YAML diff would repeat, with more confidence, exactly the mistake that produced the failed 0.3.0 build.

---

## D-115 — Gate A of the canonical career-profile bundle: 9 of 19 slices, and a rule for checks that cannot fire

**Context.** A separate design and implementation plan for a *canonical career-profile bundle* live
untracked under `docs/superpowers/` (spec + plan, both dated 2026-08-10, both marked
READY-FOR-IMPLEMENTATION). This is not a P0–P7 phase; it is a parallel track, and its Gate A is the
**generalized mechanism only** — Gate B, the private canonical baseline, is prohibited until Gate A is
implemented *and independently reviewed*. Role-family projection, persona/claim selection, taxonomy
integration, rendering, and JD/tailoring evaluation are all later designs.

**What was built:** slices T1–T9 of 19, one commit each, in dependency order. `src/boardwatch/profile_bundle/`
now holds the typed outcome catalog, a restricted YAML loader, the closed 33-document file grammar, every
record model, the JSON Schema export, a 33-file synthetic example shipped as package data, an isolated
canonical serializer with the §7 bundle/candidate identity algorithm, the global record index, structural
and referential validation, the content-addressed blob store, and versioned secret scanning.
**T10–T19 are not built:** semantics, owner-gate derivation and approval stamps, deterministic import,
completeness/digest/reports, storage, rebase, promotion, migrations, the CLI, and the docs/audit pass.

**Gate A is NOT met and the bundle is not wired to anything.** There is no `profile-bundle` CLI command
yet, and there is deliberately **no bundle-to-`Resume` bridge**: `tailor_cmd._resume_path` still returns
`settings.config_dir / "resume.yaml"`, and nothing under `src/boardwatch/tailor/` imports the package. No
SQLite schema, store-head, or Alembic change. A test asserts the isolation in both directions.

### The rule this slice establishes: a check that cannot fire is deleted, not shipped

Design §20.1–20.2 list conditions as validation checks that the **Pydantic models already refuse at parse
time**: `required_metric_ids` is a `MetricId`, so pointing it at a fact is a pattern failure;
`ConflictRecord._resolved_groups_name_their_ruling` and `RulingRecord._selection_matches_the_decision`
enforce their own shapes. Implementing those a second time in a validation layer produces code that can
never run, which is the same defect class as a never-resolving eligibility rule reporting 100% abstain.

**So the duplicates were removed, and the tests say where each guarantee actually lands** —
`test_typed_reference_fields_refuse_the_wrong_kind_before_this_layer` asserts the parse-time refusal
rather than leaving a §20 row looking uncovered. `record_kind_mismatch` is the one exception kept: §20.1
names it, its docstring states plainly that authored YAML cannot reach it, and `prefix_matches_kind` is
tested directly so the guard still has teeth if a field is ever widened to a bare `RecordId`.

**This is a departure from the plan's task list and is deliberate.** It is not a contradiction in the
design — the guarantee is *stronger* where it lands, just not where §20 implies. A reviewer comparing
the code against §20 will find rows with no check beside them, and this entry is the reason.

### Three findings the work itself produced

**Dispatch by record TYPE, never by field name.** The first index keyed off attribute names, so
`policy/relations.yaml`'s `relations` field of `RelationSpec` catalog rows was indexed as relation
records, and `policy/sources.yaml` and `imports/source-ledger.yaml` both having a `sources` field made a
**correct** bundle report duplicate IDs and a wrong owning file. Name-based dispatch cannot tell a
catalog row from a record; a type map can.

**Evidence link symmetry compares the union of all three relationship sets.** §12 makes the relationship
a closed choice of `supports` / `contradicts` / `contextualizes`, and §12.1 separately says a contextual
source cannot satisfy a verification requirement. Comparing `fact.evidence_ids` against
`supports_record_ids` alone would force every legitimate contextual attachment to overstate itself. The
verification question is semantic and belongs to T10, not to referential validation.

**A by-name import of a version set defeats the versioning mechanism it implements.** §12.2 requires a
newer installed secret-scan catalog to rescan an older revision and report hits as *blockers*, never
errors. `validation/evidence.py` first bound `SUPPORTED_RULESET_VERSIONS` at import, which snapshots it —
the stronger-ruleset path was structurally unable to observe a newly retained version, i.e. the one
mechanism that must work the day a v2 ships would have failed on that day and no test would have said so.
Fixed by importing `secret_scan` as a **module** and reading the set at call time.

### `make check` caught what ruff, mypy and pytest could not

ruff, `mypy --strict`, and 838 profile-bundle tests were all green while `make check` exited **2**: the
new test fixtures tripped R1/R2 of the generalization gate with literal home paths and an `example.test`
address. The first fix reached for the checker's `HOME_PATH_EXCEPTIONS` table — wrong twice over, because
an entry excuses the string **repo-wide**, and because 31 shape tests assume that table is empty and
report unused entries as stale. The repo already had the answer, stated in `tests/generalization/test_shape.py`'s
own docstring: **violating fixtures are assembled at runtime so the literals never exist on disk.** The
rule protects the repo's *bytes* — git history, a `grep` over a clone, the published wheel — not just the
checker's opinion. `allowlists.py` was reverted to unchanged.

**Alternatives rejected.** Building the bundle inside a fresh worktree — the authoritative design and plan
are untracked under `docs/superpowers/` and would have disappeared. Consolidating the bundle's canonical
serializer with `eligibility/hashing.py` or the three `_version_of` helpers — those bytes feed stored
identities behind BEFORE UPDATE/DELETE triggers, and a characterization test now pins all four against
accidental merging. Adding a redaction to the packaged example to close a fixture gap — it would move
`evidence_set_digest` and every digest pinned against it, so it is left for a deliberate fixture change
and the gap is asserted, not hidden.

---

## D-116 — A docs-only commit owes the two fast gates, not the full suite; and the tectonic pin gets a detector

*2026-08-10. Open question 3 in `STATE.md`, taken by Mit. Closes the standing contradiction between D-014
and three months of practice, and records a mirror-site fix taken in the same session.*

**The contradiction.** D-014 ruled that every commit owes a full `make check`. Practice has been
`make generalization index-check` — 1.3 s against roughly 6 minutes — and nobody re-litigated it, so the
written rule and the followed rule diverged silently. D-109 chose an index design that is correct either
way rather than resolve it, which kept the question alive without cost until this session relied on the
relaxed form to publish `1cdcd66`. **Mit's ruling: ratify the practice and amend D-014.**

**The rule.** A diff touching **only `*.md`** owes `make generalization index-check`. Any diff touching
`src/`, `tests/`, `tools/`, `pyproject.toml`, `uv.lock`, a migration, or anything under `.github/` owes the
full `make check`. The boundary is the file extension, deliberately — a rule that requires judgement about
whether a change is "really" documentation is a rule that gets argued with at the moment it is least
convenient.

**Why those two targets are sufficient, and not merely cheap.** They are the only checks a markdown-only
diff can break. `generalization` scans repo *bytes*, so a home path or a real address pasted into prose is
exactly what it exists to catch — and prose is where that happens, not code. `index-check` runs the same
checker as `tests/unit/test_program_index.py::test_the_real_program_indexes_are_current`, so the one test in
the suite that reads the real `docs/program/` files is already covered by it. ruff does not lint markdown,
mypy does not type it, and no other test opens it. The relaxation is therefore *coverage-preserving* rather
than a tolerated risk — which is the only ground this program accepts for making a gate cheaper.

**What would falsify this.** A new test that reads a `docs/` file and is not the program-index checker. If
one is ever added, this decision is void and the full gate returns; the fast set is defined by what the
suite actually reads, not by a preference for speed.

**Separately: the tectonic version pin now has a drift detector.** `Dockerfile`'s `ARG TECTONIC_VERSION`
and `.github/actions/setup-typesetting`'s `tectonic-version` input default are two sites for one fact, each
building a release-tarball URL from it (D-114). The action's own comment admitted "nothing detects drift
between them" — a hand-maintained mirror that documents its own absence of a check, which is the fourth
such mirror this program has been bitten by. `tests/unit/test_typesetting_pin.py` parses both and fails if
they disagree; it was confirmed to fail by mutating the `Dockerfile` pin to `0.18.0`, not merely observed to
pass. Divergence here is benign while both versions happen to work, which is precisely why it would have
been found late.

**Alternatives rejected.** Deriving the action's default *from* the Dockerfile at runtime — a composite
action cannot read a file before its inputs are resolved, and a shell step that parses the Dockerfile trades
a detectable mirror for an undetectable coupling. Deleting the Dockerfile's `ARG` and passing the version in
from the workflow — it must stay buildable standalone. Asserting on the version in the action's *prose*
comments as well: a stale comment is a real defect but pinning prose to a literal makes every wording change
a test failure.

---

## D-117 — 0.3.0's tag MOVES rather than 0.3.1 being cut; and gitleaks was fixed by cleaning bytes, not by allowlisting

*2026-08-10. The release-form question D-112 left open and D-114 deferred until the fix was verified,
taken by Mit once it was. Also records the first time `gitleaks` went red on `main`, found by pushing.*

**Mit chose to move `v0.3.0`, not to cut `v0.3.1`.** The tag is deleted on `origin` and locally and
re-created on a commit that contains the CI fix. The reasoning that decided it: **nothing was ever
published for 0.3.0** — PyPI 404s, no GHCR image, no GitHub Release, all three publish jobs correctly
skipped — so the tag has no consumers and immutability protects nobody. Against that, cutting 0.3.1 would
burn a version number on a build-infrastructure bug and leave two permanent artifacts of it: a tag pointing
at a commit that never built, and a `## [0.3.0]` changelog section that never shipped. The `[Unreleased]`
entries fold into the existing `## [0.3.0] - 2026-08-10` section, which is now the only one.

**The precondition is unchanged and is not a formality.** `v0.3.0` named `426f45c`, whose tree has no
`.github/actions/setup-typesetting` at all (`git ls-tree -r v0.3.0 --name-only -- .github/actions` is
empty), so deleting and re-pushing the tag *where it already pointed* would have re-run the identical
33-test failure with more confidence behind it. The tag must land on a commit containing the fix, and
`ci.yml` must be green on all three OSes first.

**What pushing actually revealed, which reading the diff had not.** `ci.yml` on `cefd13e` was red on all
three Windows jobs — `1 failed, 3922 passed`, the failure being the program-index gate decoding its logs as
cp1252 and reporting all 114 rows as headless. That was already fixed locally and unpushed, which is the
whole reason the held commits mattered. But the push also turned **`gitleaks` red for the first time in the
project's history**, and nothing local had predicted it: the Gate A commits put two synthetic fixtures on
disk as literals — a PEM header whose body is the word `filler`, and a 40-character token typed by hand for
a test asserting that ruleset v1 has *no* entropy heuristic and therefore matches nothing.

**Fixed by assembling both at runtime, which is the rule this repo already had.** D-115 had just paid for
the same lesson against the generalization checker and stated it: the rule protects the repo's **bytes** —
git history, a `grep` over a clone, the published wheel — so the fix is to keep the literal off disk, not to
teach the scanner to forgive it. The same file was *already* following the pattern for its AWS fixtures
(`"AKIA" + "A" * 16`); it simply had not been applied to these two. Confirmed by `gitleaks dir` going from
2 findings to **no leaks found**.

**`.gitleaksignore` covers only what history already contains, pinned by fingerprint.** A fingerprint is
`commit:file:rule:line`, so each entry excuses exactly one blob in one commit. A rule-level or path-level
allowlist was rejected for the reason D-115 gives: it would stop this repository's own secret-scanning
fixtures from ever being caught again, permanently, which is the `HOME_PATH_EXCEPTIONS` mistake with a
different file name. Verified to fire rather than assumed — the same commit range scanned 2 findings before
the file existed and 0 after.

**A process note worth keeping.** `ci.yml` runs `gitleaks`, `perf` and `generalization` as separate jobs;
`make check` runs none of them, and `gitleaks` is not installed by any project tooling. So **a green
`make check` is not a green CI**, which is a narrower claim than "`make check` is the only gate" and does
not contradict it: `make check` remains the only gate for *this repo's own correctness*, while three CI jobs
check properties the local gate has never covered. The cheap mitigation, not yet taken, is to run
`gitleaks git --log-opts=origin/main..HEAD` before a push.

---

## D-118 — Gate A slice T10: effectiveness derived in one place, and two more §20.4 rows with no check

*2026-08-10. Continues the parallel career-profile-bundle track from D-115. Slice T10 of 19 —
semantic validation, design §20.4. Gate A remains NOT met and NOT reviewed.*

**What was built.** `src/boardwatch/profile_bundle/effective.py` and
`validation/semantic.py`, plus four test files. `make check` in a detached worktree pinned to
`08d5c96`: exit **0**, **4,866 passed**, **95.20%** coverage. Thirteen error checks and one
completeness check, using the semantic `IssueCode` block T1 had already declared and left unused.

### Effectiveness is derived once, because four rules have to agree about it

§10.3 says "downstream eligibility is derived" and never stores it. Four separate rules then depend
on that derivation: predicate cardinality, the skill surface union, the claim surface intersection,
and §15's assertion-tag authorizations. Each re-deriving it would let them disagree — and the
disagreement would be invisible, because every one of them would still pass its own tests.
`effective.py` is therefore the single definition, and it splits two words the design keeps apart:
**effective** is §10.4's exact three conditions (state `verified`/`owner_confirmed`, not superseded
by an active edge, not conflict-blocked), while **eligible for a surface** adds the fact's declared
surfaces, the predicate row's maximum, and the `application_only` collapse.

**Evidence validity and expiry are deliberately NOT folded into eligibility.** §10.3 lists both as
reasons a fact is unavailable, but the evidence layer already reports missing blobs, unmet contracts
and unreviewed sufficiency, and §20 runs the layers in dependency order rather than having each
restate the previous one's findings. Folding them in would turn one unreviewed evidence record into a
cascade of surface errors on every fact, skill and claim downstream, and an operator would have to
work backwards to the single cause. Expiry stays out for a stronger reason: §20 requires validation
to be a pure function of content, so it belongs to completeness against an explicit `--as-of` date.

### Two more §20.4 rows have no check, and the tests say where the guarantee lands

Extending D-115's rule, now applied twice more.

**"Entity statuses come from the correct catalog"** cannot fire. `EntityRecord` is a discriminated
union on `entity_type` and each member declares its own status enum, so a project status cannot
validate against an award; the ID prefix is typed too, so `entity_id: project.x` with
`entity_type: award` fails `AwardId`'s pattern. Authored YAML never becomes a wrong-catalog model.
**The reachable defect is one step away and is now checked:** `policy/assertion-tags.yaml` carries
`subject_statuses` as bare `LowerToken`s, so `shipped_privately` parses cleanly and then matches
nothing forever — a high-risk tag silently unauthorizable, which is the eligibility-rule-that-cannot-
fire defect wearing a different hat. `ENTITY_STATUS_ILLEGAL` reports exactly that.

**`METRIC_PHRASING_MISSING` was redefined rather than left dead.** `allowed_phrasings` has
`min_length=1`, so "a metric with no phrasing" does not parse. The code now means the reachable
thing: a claim declares it *renders* a metric and none of that metric's allowed phrasings appears in
the text.

**Cardinality and exclusivity were kept from restating each other.** Every shipped row pairing
`one_effective_value` with cardinality `one` makes exclusivity's count clause redundant, so that
clause is scoped to cardinality `many` — two findings for one mistake is noise. It is still
reachable, because `policy/predicates.yaml` is revision-owned *data*: a user's `many` +
`one_effective_value` row is authorable, and a test edits one and watches the clause fire. This is
the ["dead for bundled" ≠ unreachable] distinction, applied deliberately.

### One interpretation, recorded as an interpretation

§14 requires a verified skill to have "a supporting `technology.used` fact whose predicate contract
allows skill grounding" and does **not** say the fact's own `skill_id` must name the skill it
grounds. Implemented as if it does, because without it a fact recording that one technology was used
would ground a record for a different one — which is the substance of §14's "referencing a skill only
in an old résumé … is insufficient". Flagged in `effective.grounding_facts`' docstring and to Mit
rather than presented as a quotation. **If this reading is wrong, the check is the thing to remove.**

### The claim figure scanner is strict on purpose

§15 requires every numeral in claim text to trace to a referenced metric's allowed rendering. The
implementation takes that literally: a figure traces only when a referenced metric whose mention is
`rendered` has an allowed phrasing appearing verbatim in the text *and* containing that figure. So a
year, a version number and a "24/7" are all untraceable figures. A scanner that tried to tell a
"real" measurement from an incidental number would be making exactly the informal judgement §11
opens by refusing, and a test states the strictness so it is a decision rather than a surprise.

**A second carried fixture gap, asserted rather than hidden.** The packaged example declares only
`qualitative_only` metric mentions, so every `rendered` path is exercised by constructed cases;
`test_the_example_declares_no_rendered_metric_mention` asserts the absence so closing it is
deliberate. Adding one would move `evidence_set_digest` and every digest pinned against it — the same
reason D-115 left the redaction gap open.

### The mutation discipline was run, and the layer's own trap was found first

All fourteen checks were disabled one at a time and confirmed to take at least one test with them —
7/3/4/1/2/1/5/2/2/2/6/10/11/1 failures, **zero missed** — with the slice committed first so the
restore was safe. Separately, an import cycle was designed out before it could bite:
`validation/__init__.py` imports `semantic`, which imports `effective`, so `effective` reading
anything from the `validation` package at module scope would make
`import boardwatch.profile_bundle.effective` re-enter a half-initialised module. The context type is
`TYPE_CHECKING`-only and the one runtime helper is imported inside its function — the deferred-import
shape `validation/evidence.py` already used.

**Alternatives rejected.** Implementing the entity-status row anyway "for completeness" — that is the
defect D-115 named. Folding evidence eligibility into `eligible_fact_surfaces` — cascades, above.
Reporting exclusivity's count clause regardless of cardinality — redundant against cardinality on
every shipped row. A figure scanner with a heuristic for "real" measurements — it would decide the
thing the bundle exists to stop being decided informally.

---

## D-119 — 0.3.0 is PUBLISHED: the tag moved onto a CI-green commit, and it ships two known BLOCKERs deliberately

*2026-08-11. Executes D-117's decision and records the two rulings Mit gave while it was in flight. The
release is the whole of it; the interesting part is what was known at the moment of publishing.*

**Done.** `v0.3.0` was deleted on `origin` and locally and re-created — **lightweight**, matching `v0.1.0`
and `v0.2.0` and the convention `release.yml`'s own header documents — on **`dc1ffec`**, replacing
`426f45c`. `release.yml` then went green on all four jobs and 0.3.0 exists on PyPI, GHCR and GitHub
Releases. `[Unreleased]` had already been folded into the single `## [0.3.0] - 2026-08-10` section, so the
tag names a commit that describes itself.

**The precondition was met in full, not approximately.** `ci.yml` run `31442555052` on `dc1ffec`:
**12 of 12 jobs green** — `gitleaks`, `perf`, `generalization`, and `test` across ubuntu/macOS/Windows ×
3.11/3.12/3.13. This is the first fully green `ci.yml` in the project's history; the tectonic/poppler gap
(D-114) and the cp1252 program-index defect were the last two things standing in the way.

**Publishing was verified through three paths independent of the workflow's own report**, because a
component's self-report is not verification: PyPI's JSON API lists `['0.1.0','0.2.0','0.3.0']` with a
618,554-byte wheel and a 1,395,850-byte sdist; `gh release view v0.3.0` shows not-draft, not-prerelease,
with both assets at **byte sizes matching PyPI exactly**; and the GHCR manifest for `:0.3.0` and `:latest`
answers 200 as an OCI index over **amd64 + arm64**, read anonymously from the registry because this
machine's `gh` token lacks `read:packages`.

**Mit ruled ship-as-is TWICE, and the second time is the one that matters.** The first ruling was made once
it was measured that the wheel carries Gate A: 65 `profile_bundle` entries — 31 modules, 33 synthetic YAML
documents, one JSON Schema — while the changelog does not enumerate them. No commit on `main` carries the CI
fix *without* Gate A (its commits sit **below** the fix in history), so excluding it would have needed a
cherry-pick branch matching no commit on `main`. He was offered "hold 0.3.0 until Gate A is reviewed" and
declined it.

Then, before the publish jobs fired, the partial Gate A review found **two BLOCKERs in the restricted YAML
loader that break content addressing** — four byte-different spellings of one record producing the identical
`bundle_digest`. He was asked again, with the window still open and the option to cancel the run, and ruled
publish again. **The basis of the ruling was unchanged and that is why it held:** the package is inert. No
CLI command, no bundle-to-`Resume` bridge, a test asserting both directions, and nothing in a shipped code
path reaches the loader. It is a defect in code that ships but never runs. Holding would have punished the CI
fix — the thing 0.3.0 exists to release — for an unrelated subsystem's bug.

**What publishing did NOT change.** The Gate A review is still **owed**, its scope is **T1–T10** (not T1–T9;
a slice landed after the wheel was measured), and **Gate B remains prohibited**. A partial review is not a
review: the 3-wide dispatch became 11 agents through nesting and was stopped, so roughly two thirds never
ran. Findings landing on already-published code is a consequence of the ruling, not a defect in it, and they
are fixed in a later version rather than by unpublishing anything.

**Two measurement traps this paid for, both of which produced a confident wrong answer.**

1. **PyPI's HTML route lies.** `https://pypi.org/project/boardwatch/0.3.0/` returned **HTTP 200 for a version
   that did not exist**, and was reported as "already published" on the strength of it. The JSON API
   (`/pypi/boardwatch/0.3.0/json`) returned **404**, and `/pypi/boardwatch/json` listed only `0.1.0` and
   `0.2.0`. Use the JSON API. Had the HTML 200 been trusted, Mit would never have been given the second
   decision, because the window would have looked closed.
2. **A polling watcher's exit 0 means only that the loop ended.** Both CI watchers exhausted their iteration
   count and exited 0 with the run still `in_progress`. This is the same defect class as
   `background-command-exit-code-masking`, and the narrower phrasing there ("end a backgrounded gate with
   `exit $ec`") does not cover it: the exit code was *correct*, the **intent** was unfinished. A poll loop
   must report whether its predicate was met, not merely that it stopped.

**Also observed: GitHub's job-summary API lags its own step list.** Windows 3.13 ran 70 minutes against ~40
for its siblings, and for the last 30 the run summary reported it `in_progress` while its step list already
showed `pytest` and `Complete job` as `success`. Query steps
(`gh api repos/:owner/:repo/actions/jobs/<id>`) before concluding a job is slow, hung, or red.

**Alternatives rejected.** Adding a changelog line disclosing the inert bundle: `main` had already advanced
past `dc1ffec`, so a docs commit on the tip would have dragged unreviewed T10 code into the release, and
keeping it clean would have meant tagging a commit not on `main` — worse practice than the problem it fixed.
Annotating the tag: all three prior tags are lightweight and `release.yml` reads no tag metadata, so 0.3.0
would have been the odd one out for nothing.

## D-120 — Gate A slice T12: the résumé emission order is fixed, and three more checks that cannot fire

*2026-08-11. Continues the parallel career-profile-bundle track from D-115 and D-118. Slice T12 of
19 — deterministic enumeration, candidate identity, and idempotent import, design §18/§18.1. Gate A
remains NOT met, and T12 itself is **not independently reviewed**.*

**What was built.** `enumerators.py`, `imports.py`, `validation/imports.py`, and two test files. The
four approved adapters, locator normalization, derived source-record and candidate IDs,
predicate-authorized value canonicalization, idempotent package merging, and the import validation
layer. 59 mutations were applied one at a time and every one was caught by a narrow test.

### The résumé adapter's emission order is stages, not per-entry interleaving

§18.1 numbers seven emission stages and lists entry metadata as (5) and complete bullet objects as
(6). With one entry, "all metadata then all bullets" and "each entry's metadata then its bullets"
are the same sequence, so the sentence never had to disambiguate itself. With two, they differ — and
`sources[].source_record_ids` must equal the adapter's order **exactly**, so the reading is part of
stored identity, not a formatting preference.

The literal reading wins: stage 5 emits every entry's metadata, then stage 6 emits every bullet.
A test with two entries pins it. Changing it later does not merely reorder a list — it changes which
IDs the ledger declares and in what order, and every consumer comparing the two sides would fail at
once. Recorded here so a future session does not "tidy" the two loops into one.

### `~N` survives re-normalization, and that is what makes a selected scope matchable

§18 leaves `~` outside the unreserved set, and §18.1 applies the duplicate suffix **after** encoding,
so a resolved heading path legitimately contains a literal `~2`. An owner writes that resolved path
into `approved_scope.locators`. `normalize_locator` therefore preserves a trailing `~2`/`~3` on any
segment instead of encoding it to `%7E2`, or a correct scope would stop matching the section it
names. The cost is explicit: a heading whose body literally ends in `~2` cannot be distinguished
from the second occurrence of that heading. Adapters encode their own bodies through
`encode_locator_segment`, which has no suffix rule, so only owner-authored scope locators are
affected.

### The two import blocker codes are given their conditions

`IMPORT_RECORD_UNDISPOSITIONED` is `review_required`, which §18 names outright.
`IMPORT_UNEXPLAINED_RECORD` had no stated condition, and now has one: **a source registered in
`policy/sources.yaml` that `imports/source-ledger.yaml` never enumerates.** §18's staged migration
registers a source *and* enumerates it, so a registered-but-unenumerated source is approved material
that contributes nothing to the denominator — exactly the "zero unexplained records" Gate B
measures. It is a blocker rather than an error, which is why the packaged example, which ships one
such source deliberately, stays structurally valid.

### `owner_excluded` gating is NOT re-implemented in the import layer

§18 requires an `approve_source_record_exclusion` sub-approval for `owner_excluded`. T11 already
derives it in `approvals.py` and enforces it in `validate_history`, bound to the promotion diff and
the target-content digest. A second copy inside `validate_imports` would report the same missing
approval twice and could disagree about which digest the approval binds. The test therefore asserts
the gate **where it lands** — `required_approval_decisions` produces the decision for an
`owner_excluded` exclusion and none for a closed-reason one.

### Three more checks that cannot fire were deleted, per D-115's rule

Mutation testing is what found them: each was inverted, and its test still passed, because something
else was already the thing that refused the input.

- `normalize_locator`'s absolute-path guard — `/a` splits to an empty leading segment, which
  `encode_locator_segment` refuses;
- `normalize_locator`'s empty-locator guard — `""` splits to one empty segment, same refusal;
- `is_normalized_locator`'s emptiness/NFC guard — the encoded-segment grammar requires at least one
  character and admits no unencoded non-ASCII in any Unicode form;
- the Markdown adapter's blank-heading-body guard — a blank body encodes to an empty segment.

A fifth, the blank skill-group label, **was kept**: an empty group emits no record, so the locator
encoder never sees its label, and the check is the only thing that refuses it. A test with an
item-less blank-labelled group now makes it fire.

`validate_imports` is scoped by the same rule. `SourceLedger` already refuses duplicate record IDs,
unenumerated sources, and any `source_record_ids`/`records` disagreement including order;
`SourceLedgerRecord` already refuses `imported` with no candidate; `ExclusionLedger` already refuses
a double exclusion; `validate_referential` already resolves the cross-references. The layer checks
only what needs two documents at once or a recomputation: the source-kind/enumerator pairing, the
approved-scope discriminant, derived record identity, one record per `(source, locator)` pair, the
exclusion-document reconciliation, and whether an imported record owns any of the candidates it
names. The disposition counts summing to the denominator is **structural** — three branches over a
closed enum — so it is asserted by test rather than checked at runtime.

**Consequence.** T12 is implemented and mutation-verified locally. It is **not** independently
reviewed, Gate A is **not** met, Gate B stays prohibited, and T13 is the next slice.

## D-121 — The T12 review: a green gate and a perfect mutation score hid five BLOCKING defects

*2026-08-11. Independent review of `b817709` (Gate A slice T12) by an external reviewer, and the
fix `ce0a8de`. Gate A remains NOT met; T12's re-review is in flight and is NOT yet signed off.*

**What happened.** T12 shipped with `make check` exit 0 (5,086 tests, 95.39%), 179 targeted tests,
and 59 of 59 mutations caught. The independent review reproduced **five BLOCKING** defects anyway.

### The headline defect: repository Markdown could not be imported at all

`# Alpha Beta` resolves to the heading path `Alpha%20Beta`. §18.1 says a `selected_sections` scope
locator "refers to these resolved paths", so an owner writes `Alpha%20Beta` — and `_selected` ran it
through `normalize_locator`, which encoded the `%` again into `Alpha%2520Beta` and refused it. Only
the *invalid* raw spelling `Alpha Beta` worked. **There was no valid import route for any heading
containing a space**, which is nearly all of them.

D-120 recorded the reasoning for making `normalize_locator` preserve a `~N` suffix so a resolved
path survives re-normalization. That reasoning was right and was applied to exactly one of the two
things that make a path "already normalized". The percent-escapes were left re-encodable, and a
decision record was written confidently around the half that had been done.

**The fix is structural, not a patch.** A resolved path is validated, never re-encoded: `_selected`
NFC-normalises, trims, and looks the locator up. And `is_normalized_locator` is now defined as the
**encoder's exact inverse** — decode each segment, re-encode it, require equality — rather than as a
hand-written grammar. The old grammar merely *admitted* percent escapes, so `%41` for `A` passed
although no adapter can emit it. A grammar drifts from the encoder; a round trip cannot, because it
is the encoder.

### Identity was derived on the way in and taken on trust ever after

`validate_imports` never rederived a stored candidate ID, so `candidate.ffff…` passed every layer
and would have reached promotion. This was a deliberate omission: no `IssueCode` fit, so the check
was skipped. That is not a reason to leave a slice's central contract unchecked — the code catalog
is ours to extend, and `IMPORT_CANDIDATE_IDENTITY_MISMATCH` now exists. Validation rederives every
candidate ID, requires the predicate to exist in the revision's own catalog, and requires the stored
value to be the canonical form that predicate authorizes. `merge_candidate_package` refuses a value
that was never canonicalised, because a self-consistent hash over an uncollapsed string is a second
identity for an assertion that already has one.

The ownership check used `any`, so a record could name another record's candidate as long as it
also named one of its own. Owning one candidate does not license the claim; every named candidate
must be the record's own.

### What this costs the program's confidence in its own evidence

**Mutation testing proves the tests notice changes to the code that was written. It cannot find a
contract that was never encoded.** Every Markdown fixture in T12 used single-word headings, so
nothing exercised encoding, and 59 of 59 mutations were caught by tests that all agreed with an
implementation nobody had used. The reviewer found the defect by *using the feature*.

Two further checks were deleted during the fix, extending D-115: the `is_normalized_locator` guard
added inside `_selected` (a non-normalized locator always misses the membership test, so the guard
could never be the thing that fired) and, earlier, four more in T12 itself. A "value is not
canonical" test was also found to be passing for the wrong reason — the predicate-*independent*
whitespace check caught it first, leaving the predicate-*dependent* comparison unexercised until a
set-like list stored out of order was added.

**Consequence.** 67 of 67 mutations caught, `make check` exit 0 (5,111 tests, 95.40%). The fix is
**not** signed off: a retraction commit reintroduces the class it cures, so it owes its own review,
and that review is in flight. Gate B stays prohibited.

## D-122 — The T12 re-review: one defect the fix created, two contracts never enforced, and a decline that was wrong

*2026-08-11. Independent re-review of `ce0a8de` (the D-121 fix) by the same external reviewer at
high reasoning effort, a fresh-context verification agent against the same commit, and a separate
docs reviewer against the draft of this entry. Gate A remains NOT met.*

**Verdict: REWORK.** Six of the seven D-121 findings were confirmed closed. Four BLOCKING findings
remained: **one created by the fix**, one only partly closed, and **two contracts never enforced**,
one of which the code had documented. A verification agent added a fifth.

### `_selected` repaired its input, and a test locked the repair in

This is the one the fix created. D-121 changed `_selected` to "NFC-normalise, trim, and look the
locator up". The trim is the defect: `" Overview "` is not a normalized locator and no enumeration
can emit it, but trimming made it match, so the ledger's scope and the ledger's records stopped
being the same string. A test named `test_a_selected_scope_locator_is_normalized_before_matching`
asserted exactly that behaviour, and no round-2 mutation removed the `.strip()`, so nothing
contradicted it.

`_selected` now compares the locator **as given**. That also makes D-121's stated D-115 reasoning
true for the first time: a separate "is it normalized?" guard genuinely cannot fire, because
`known` holds resolved paths and a non-normalized locator always misses membership.

### The round trip did not round-trip — and the hole predates the fix

`is_normalized_locator` re-encoded the decoded segment directly, while the encoder NFC-normalises
and trims **before** encoding. So `e%CC%81` (a decomposed `é`), `%20a`, `a%20` and `%E2%80%82x` all
validated, and each derives its own `source-record.<hex>`. A verification agent used this to add a
fifth record to a four-record bundle with no finding from any layer.

**This was not introduced by the fix.** The `b817709` grammar `(?:[A-Za-z0-9._-]|%[0-9A-F]{2})+`
admits all four spellings too. What `ce0a8de` created was a *new false justification* for an old
hole — a docstring asserting that "a decomposed character re-encodes to its escaped bytes and fails
the comparison", which is exactly backwards for an already-escaped one. The predicate now compares
against `_canonical_encoding`, which applies the encoder's own NFC and trim; the false docstring is
corrected rather than deleted, because the reasoning it records is the reasoning that produced the
bug.

### Repository records were not bound to the sections their owner approved

§18 binds a repository approval to "the ledger's exact scope object", and an approval that does not
constrain which records may appear constrains nothing: the scope could name one section while the
records enumerate a whole checkout. Records are now required to lie inside an approved section, a
`_root` scope locator is refused (it names pre-heading content, which no section can contain), and
a candidate no record names is reported — it existed, derived correctly, and sat in no denominator.

### A locator no adapter could emit — a decline that was wrong

The reviewer also asked that a record's locator be checkable against its declared adapter. **The
first draft of this entry declined that, claiming it needs the source bytes. The docs reviewer
showed the claim is false and the decline self-serving.** Half of it needs bytes — which heading or
key exists is a fact about the file. The other half does not: `_locator` emits `<path>/heading` or
`<path>/<kind>-<N>` for a closed `kind`, the résumé adapter emits seven fixed stage shapes, and the
structured adapter emits exactly `objects/<key>`. Every adapter now declares `emits_locator`, kept
beside its emitter so the grammar cannot drift from it, and validation reports
`IMPORT_ENUMERATOR_MISMATCH` for a record whose locator no enumeration could have produced. This
closes the relabelling forgery, where a source's kind and enumerator are both changed and every
record it owns is silently reinterpreted under a different grammar.

The grammar is tested by enumerating a real source and requiring the predicate to accept every
locator that came out, rather than against hand-picked good spellings — a predicate checked against
examples only proves it agrees with whoever wrote the examples.

### `merge_candidate_package` had no predicate authority

D-121 said merge "refuses a value that was never canonicalised". It refused only the
predicate-*independent* half — NFC and whitespace — because it had no catalog. Unknown predicates,
predicate-illegal types, and set-like values stored out of order all merged cleanly. `predicates`
is now a **required keyword-only** argument, never an optional one: an optional catalog is a check
that silently does not run. Note the blast radius is smaller than the finding implies — the
function has no production caller yet, so this is a contract fixed before its first use.

### `portable_locator` was a documented guarantee that landed nowhere

`SourceSpec`'s docstring says the absolute machine-local root lives only in the non-revisioned
`local-sources.yaml`, "which is why `portable_locator` is relative and validation rejects a home
path inside it". The field was `NonBlankStr`. **Both halves of that sentence were false** — the
personal-path scan only walks evidence records, and `portable_locator` appeared nowhere in
`validation/`. `/absolute/source.md` and `../escape/source.md` passed all four layers. The locator
is resolved beneath an approved root, so a traversing spelling reads outside the tree the owner
approved. The refusal is now a parse-time field validator covering absolute paths, `.`/`..`
segments, backslashes and drive qualifiers.

**Known gap, accepted:** a Pydantic `field_validator` contributes nothing to the exported JSON
Schema, so `career-profile.schema.json` still under-describes this constraint. A single regex would
land in the schema but would collapse four distinct refusals into one message and one branch. The
diagnostics and the four independently-mutated branches are worth more than the schema line.

### One finding judged and NOT fixed

**Occurrence lineage is not reconciled with the ledger's source digest.** `SourceLedgerSource`
carries a single `source_content_digest` — the source's *current* one — and `SourceLedgerRecord`
carries no digest at all, so there is nothing to reconcile a `record_content_digest` against.

The weaker check that *is* expressible — "at least one occurrence must carry the ledger's current
source digest" — rests on a load-bearing assumption that must be stated rather than assumed:
**`record.candidate_ids` accumulates.** §21 says a changed source yields "a new candidate only when
the canonical typed value changes; no canonical mutation", and this same change requires every
candidate to be named by its own record. Together those force a record to keep naming the
candidates its earlier versions produced. A candidate observed at an older digest and not
re-observed since therefore has no occurrence at the current digest, and the weaker check would
refuse it. Inventing a check that refuses correct history is worse than the gap. Revisit if a
source-digest history is ever stored — no task currently plans one.

### What this round says about review evidence

D-121 recorded that mutation testing cannot find a contract that was never encoded. This round adds
the sharper version: **a fix authored by the same context that produced the defect inherits its
blind spot.** The `_selected` trim is the same mistake as the original — repairing an input instead
of validating it — reintroduced two functions away while writing a decision record about not doing
that. And the first draft of *this* entry declined a finding on a false technical premise; a
separate docs reviewer, not the author, caught it.

It also corrects a claim this entry nearly shipped. The first draft said "13 of 13 mutations
caught". The driver's list held 13 entries but **12 distinct mutations** — one was duplicated
byte-for-byte and counted twice. The duplicate was noticed when the output was read and dismissed
as harmless instead of corrected, which is the same defect class this entry is about: a number
inflated by a duplicate, presented as evidence.

**Consequence.** 20 distinct mutations across this round, all caught (12 for the review fixes, 8
for the adapter grammar). Gate result recorded in METRICS. The fix is **not** signed off: a third
review is owed before Gate B, and T12 is the block every later task trusts.

## D-123 — A recurring trigger holding a one-shot prompt re-fires a task that already shipped

*2026-08-11, 03:10, unattended. The scheduled run declined to execute its own prompt. No code was
written; no branch was created. Recorded because the misfire recurs nightly until the trigger is
changed, and because the next session to hit it will otherwise re-derive this from scratch.*

**Context.** `~/Library/LaunchAgents/com.mitsheth.boardwatch-p6.plist` uses
`StartCalendarInterval` at 03:10 with no terminating condition, so it is a *daily* job. The command
it runs, `~/.claude/scheduled/p6-slice1-run.sh`, passes a *one-shot* prompt,
`~/.claude/scheduled/p6-slice1-prompt.md`, whose task is "P6 Slice 1 — execute the plan, starting at
Task 1". That prompt asserts a starting state of `main` at `fb0386a` with only `AGENTS.md` untracked.

Slice 1 was executed by the **2026-08-10** occurrence of this same job, on branch `p6-slice1`, and has
since been reviewed (D-095), merged, and followed by Slices 2 and 3 (D-103…D-107, D-110, D-111,
D-113) and twelve Gate A slices. At tonight's occurrence `fb0386a` was an **ancestor of `HEAD`, 110
commits back**; `AGENTS.md` was tracked; and every module the plan's nine tasks create already
existed — `core/identity_kinds.py`, `core/posting_identity.py`, `store/identity_queries.py`,
`cli/identities_cmd.py`, migration `p6_posting_identities`, the root `tests/conftest.py`, and six
test modules. The Alembic head has moved twice past what the plan targets, to `p6_job_dispositions`.

**Choice.** Execute nothing. CLAUDE.md's session-start ritual says the repo wins over a document that
disagrees with it, and that governs a *prompt* at least as strongly as it governs `STATE.md`: a prompt
is a document written at a past commit. Following it would have created a duplicate migration, a
second identity catalog, and a `p6-slice1` branch off a tree that already contains the merged
original — a merge conflict with itself, in a session with nobody awake to arbitrate.

**Alternatives rejected.** *Unload the launchd job.* Reversible and it stops the waste, but the plist
is Mit's automation and the same job is the vehicle for the standing unattended-run pattern; silently
disabling it at 3am substitutes our judgement for theirs on a schedule we were not asked to own.
*Rewrite the prompt to point at the next real task.* Worse — it picks the next task by fiat, which is
exactly the decision the owner reserves, and it hides the misfire instead of surfacing it. *Treat the
prompt's rule 4 ("do not stop at the first failure — route around it") as licence to do other work.*
Rule 4 routes around a failed **task within this plan**; it is not a mandate to invent a scope, and
rule 8 of the same prompt forbids starting anything the task does not ask for.

**Consequence.** The failure mode is **self-detecting and benign**: any session that performs the
session-start ritual reaches this conclusion in a handful of read-only commands, so the recurrence
costs one short window per night and cannot corrupt the tree. It is not self-*correcting* — the
trigger must change. Two fixes, either sufficient: `launchctl bootout gui/$UID/com.mitsheth.boardwatch-p6`
to retire the job, or repoint `p6-slice1-run.sh` at a fresh prompt for the actual next task. The
general lesson for this program's automation: **a prompt that names a starting sha is a one-shot
artifact, and pairing one with a recurring trigger guarantees it eventually executes against a tree
it was not written for.** An unattended prompt should either state its own precondition as a check
that aborts (`git merge-base --is-ancestor`), or be deleted by the run that consumes it.

## D-124 — The third T12 review: the locator grammar keeps failing because it restates the emitter instead of deriving from it

*2026-08-11. Third independent review of the T12 locator work, against `126a268` (the D-122 fix), by
the same external reviewer at high reasoning effort in a fresh worktree. Gate A remains NOT met.
Round-three fixes are **NOT started**.*

**Verdict: REWORK — the third in a row.** Four BLOCKING findings, each reproduced against all four
validation layers. Every previous round's finding was confirmed closed, and every new one is in code
this program wrote to close the previous round.

### The headline: `_root` is not reserved, so a legitimate document became unimportable

`ROOT_SEGMENT` is `_root`, and `_` is an unreserved character, so `encode_locator_segment("_root")`
returns `_root` unchanged. Pre-heading content and a heading literally named `_root` therefore share
one namespace:

```
_root/paragraph-1   <- genuinely pre-heading content
_root/heading       <- a heading named "_root"
_root/paragraph-2   <- a paragraph inside that heading
```

D-122 then added a check refusing `_root` as an approved scope locator, reasoning that no heading can
ever resolve to it. That reasoning was wrong, and the result is that a repository source containing a
heading named `_root` enumerates successfully and then fails import validation.

**This is the same defect class as round one's headline** — a legitimate Markdown source made
unimportable by a locator rule — reintroduced in the commit whose own decision record is about not
doing that. The emitter's ambiguity is the deeper half: two different logical sections collapsing
into one namespace is a defect independent of any validation check.

### The other three, all in the round-two additions

| Finding | Cause |
|---|---|
| `emits_locator` accepts arbitrarily deep heading paths, but `_HEADING_RE` caps headings at six levels. A seven-level forged record passes every layer. | The grammar was written **looser** than the emitter it claims to mirror. |
| The raw `~N` duplicate-suffix exception is adapter-blind. A structured-object key can only be emitted as `synthetic%7E2`, yet `synthetic~2` validates as a normalized locator and passes all four layers. | A Markdown-specific dedup rule was applied to locators in general. |
| `portable_locator` accepts an embedded NUL, producing a structurally valid bundle whose source path cannot be opened. | The validator enumerated the spellings a reviewer had shown, not the character classes that break a path. |

The exported `career-profile.schema.json` gap was rated SHOULD-FIX rather than the accepted gap D-122
called it. **D-122's judgement is overridden:** a schema admitting `../escape/source.md` while the
model refuses it misleads every authoring tool that reads it.

### The cause, which is none of the four

Three rounds have produced the same shape of defect: a locator rule looser or stricter than the
emitter it is supposed to describe. D-122 credited itself with deriving `emits_locator`'s tests from
the emitter — enumerate a real source, require the predicate to accept every locator it produced.
That was the right instinct and it was not enough, because **the property was only tested over
sources the fixtures happened to contain.** No fixture had a seven-level heading, a `~`-bearing
structured key, or a heading named `_root`, so the grammar's disagreements with the emitter stayed
invisible to a test derived from the emitter.

The fix that addresses the cause rather than the instances: the grammar must **read the emitter's own
constants** — the heading-level cap out of `_HEADING_RE`, the block-kind set, the per-adapter question
of whether `~N` is meaningful — instead of restating them in a second place. Two pieces of code that
agree only by inspection drift on the first input nobody thought of. A generative property test over
adversarial documents is the second half; the derived-from-fixtures version cannot find what the
fixtures omit.

**Consequence.** T12 is **not signed off** and owes a third fix. Gate B stays prohibited. The next
round is deliberately starting in **fresh context**: both previous fix rounds were authored by the
same context that produced the defects being fixed, which is the pattern D-122 named and then
repeated.

## D-125 — The T12 round-three fix, and two more reviews of it: a forbidden segment is escaped, never refused

*2026-08-11, fresh context. Closes D-124's four BLOCKING findings and the SHOULD-FIX that overrode
D-122's accepted gap, then the findings of a fourth and fifth review of that fix. Gate A remains NOT
met.*

D-124 named the cause; this entry records the shape of the answer. **Every rule that describes the
emitter now reads the emitter's own constants**, so one restatement is removed per finding rather
than one instance patched per finding.

### `_root` is reserved by the encoder, not refused by validation

`ROOT_SEGMENT` is `_root` and `_` is unreserved, so `encode_locator_segment("_root")` returned
`_root` unchanged and pre-heading content shared a namespace — and derived record IDs — with a
heading literally named `_root`. D-122's scope refusal then made such a source unimportable.

`_encode_text` now escapes the **first character** of any body that lands on a forbidden whole
segment, so that heading resolves to `%5Froot`. **Escaping rather than refusing is the whole point.**
Refusing `_root` as a heading body would relocate round one's defect, not close it: a legitimate
Markdown document would become unenumerable instead of unimportable.

**The same mechanism now covers `.` and `..`, which it did not.** `# .` and `# ..` were hard
`EnumerationError`s — the identical defect, sitting four lines from the docstring giving the reason
for not doing that. They encode to `%2E` and `%2E.`; §18 forbids a `.` *segment*, and `%2E` is not
one, so the escape satisfies the rule the refusal was serving.

`normalize_locator` keeps its own `.`/`..` **path-component** guard, restored here. D-120 deleted it
because `encode_locator_segment` refused those bodies; that reason has now inverted. A `.` in a raw
path means traversal, and silently encoding it would turn "this directory" into a literal segment.

### The reservation is deliberately GLOBAL, and the design is silent on all of it

The collision is Markdown's alone, but the escape lives in the shared encoder. `is_emitted_segment`
and `is_normalized_locator` are adapter-blind by necessity — they also serve owner-authored scope
locators — so a per-adapter reservation would mean two encoders and precisely the drift this round
removes. **The cost is explicit:** a `structured-objects-v1` key or a résumé `entry_id` literally
named `_root` is escaped too, which moves it in §18.1's encoded-key sort order. Deterministic and
reproducible, so §18's byte-identical re-enumeration still holds — but it is a behaviour change to
two adapters made to fix a third, and it is pinned by test rather than left to inference.

**§18 names no reserved segments** and says nothing about a heading body colliding with `_root`. It
constrains which characters *may* remain unescaped, not which *must*, so `%5Froot` is a spelling its
own grammar admits. *Alternative rejected:* change `ROOT_SEGMENT` to a token no encoded body can
produce (one carrying a `%` escape), which needs no reservation and no encoder special case — but it
rewrites every stored `_root/…` locator and therefore every record ID derived from one, including
the packaged example's own ledger.

### The depth cap and the `~N` rule stop being restatements

- `_MAX_HEADING_LEVEL` **builds** `_HEADING_RE` and is **read** by `emits_locator`. The grammar
  accepted any depth while the parser capped nesting at six, and a seven-level forged record passed
  all four validation layers.
- `is_emitted_segment` is the encoder's exact inverse **with no duplicate-suffix exception**. The
  résumé and structured grammars call it directly, so `objects/synthetic~2` is refused although the
  adapter-blind predicate accepts it. `~N` is applied by the Markdown adapter to a resolved heading
  path *after* encoding, so it is meaningful there and nowhere else, while §18.1 requires the
  adapter-blind predicate to keep admitting the resolved paths an owner writes into a selected
  scope. **The module therefore has two predicates where the design has one notion**, and the weaker
  one now says so in its own docstring rather than claiming to be the strong one.
- **`is_resolved_heading_path` closes the sibling gap both later reviewers found independently.** The
  byte-free grammar reached `records[].normalized_locator` and stopped, so an approved scope could
  name `a/b/c/d/e/f/g` or `Overview/_root` — shapes no heading stack resolves to — validate clean,
  and then fail every re-enumeration with a hard error. That is the argument the `_root` scope
  refusal directly above it already rested on. Two checks became one that asks the emitter's
  question.

### `portable_locator`: the sentence is made true, and the schema stops disagreeing with the model

A NUL produced a structurally valid bundle whose source path `open()` refuses before any filesystem
call. The validator enumerated the spellings a reviewer had shown rather than the character classes
that break a path; it now refuses every C0 control character and DEL.

**`SourceSpec`'s docstring claimed "validation rejects a home path inside it". D-122 recorded that
sentence as false and fixed only its other half.** `~/notes/x.md` is *relative*, so the absolute
branch never saw it, and nothing else reads the field — the personal-path scan walks evidence records
only. A leading `~` is now refused, and the docstring enumerates exactly what the validator does
instead of describing a guarantee that lands nowhere.

**D-122's accepted schema gap is overridden.** `PORTABLE_LOCATOR_PATTERN` carries the whole
constraint into `career-profile.schema.json` while the six validator branches keep their separate
diagnostics — the two coexist rather than one replacing the other. D-122 declined this because a
single regex collapses four refusals into one message; that trade was real, but the schema is what
every external authoring tool validates against and it was admitting `../escape/source.md`. A
parametrized corpus asserts the pattern and the model agree spelling by spelling, and an independent
run put that agreement at **124,497 inputs, zero divergences**. The pattern is ECMA-262-valid, which
is the dialect a JSON-Schema consumer uses.

**The other two locator fields stay `\S`, deliberately.** `SelectedSectionsScope.locators` and
`SourceLedgerRecord.normalized_locator` are constrained by a percent-encoding grammar, and writing
that grammar as a schema regex would be *a restatement of the encoder that cannot be kept in sync* —
the defect class of this entire round. `portable_locator` differs in kind: its constraint is a
character-class rule with no encoder behind it, so one regex is the whole contract rather than a
second copy of one. Revisit only if the schema gains a generated-from-the-encoder route.

### What mutation testing found that the tests did not

**Twenty-eight distinct mutations, checked for byte-identical duplicates before the run** — D-122
reported "13 of 13 caught" when the driver held 12 distinct mutations and one repeat. The driver now
aborts on a duplicate rather than trusting the count.

Two rounds were needed, and each survivor was a real defect:

- **`_MAX_HEADING_LEVEL = 5` survived.** Every assertion about the cap read the same constant it was
  checking, so the constant and its tests agreed with each other while both disagreed with
  CommonMark. This is the **self-referential** form of the defect D-124 described: deriving a test
  from the emitter fixes drift between two pieces of code and does nothing about a shared wrong
  premise. The replacement enumerates six- and seven-hash sources and asserts what Markdown does.
- **`is_emitted_segment`'s `.`/`..` guard survived**, because escaping those bodies had made it
  unreachable — `_canonical_encoding(".")` is now `%2E`, so the round trip already refuses the bare
  spelling. Deleted under D-115 rather than kept as coverage it no longer provides. The
  empty-segment guard stays: `""` does encode to itself.

**28 of 28 after both.**

### What the fourth and fifth reviews say about review evidence

Two reviewers ran against the same commit with deliberately different lenses — one hunting runtime
forgeries, one checking conformance against the design's own words — and **both independently found
the scope-locator gap**, which neither the fix's author nor a 20-mutation suite reached. The
conformance lens alone found the false `SourceSpec` docstring that had already survived D-122 naming
it. Two lenses on one commit is cheaper than two sequential rounds and finds things one lens does
not; a second reviewer is not redundancy.

A property test over ~14,000 generated sources and ~580,000 encoder inputs found **zero** cases where
an adapter emits a locator its own strict predicate refuses — round one's defect class is not back —
and zero collisions in the reservation. That is evidence the previous three rounds could not produce,
because their properties ran only over what the fixtures contained.

**Consequence.** Every finding from five reviews is fixed. T12 is **still not signed off**: a
retraction commit reintroduces the defect class it cures, so the round-four/five fix owes its own
independent review, in fresh context, before Gate B. Gate A remains **not met**. Nothing is pushed.

## D-126 — T12's review loop is CLOSED, with a stated exit criterion

*2026-08-11. A process decision, no code. Mit: "we're stuck on the same stuff for a while… we need to
move ahead."*

**T12's review loop is closed. It has met the Gate A review requirement and no sixth round is owed.**

**Context.** Five independent reviews, five REWORK verdicts, every finding fixed (D-121, D-122,
D-124, D-125). Gate exit 0, 5,260 tests, 95.41%, 28 of 28 distinct mutations caught.

**The problem was never the findings — it was that nobody set a stopping rule.** "Review until
APPROVE" does not terminate. A reviewer briefed to find defects finds defects, and the tail is
inexhaustible: dead code, stale comments, spellings no adapter emits, NOTEs about a helper with no
production caller. Each round consumed a full context window and a 30-minute gate. That cost is only
worth paying while the findings are still *load-bearing*, and they have stopped being so.

**The severity curve, which is the actual evidence:**

| Round | BLOCKING | The worst one |
|---|---|---|
| 1 (D-121) | 5 | Repository Markdown unimportable for any heading containing a space |
| 2 (D-122) | 4 | `_selected` repaired its input; records not bound to approved sections |
| 3 (D-124) | 4 | `_root` unreserved — a namespace collision producing identical record IDs |
| 4 + 5 | 1 | A **docstring** asserting a guarantee that landed nowhere |

Round four's single BLOCKING was a false comment, not a data defect. Rounds one through three each
found something that silently corrupted identity or stranded a legitimate source; round four found
nothing of that kind, and its reviewers between them ran ~14,000 generated sources, ~580,000 encoder
inputs and 124,497 schema inputs **without finding one forgery that passed all four layers or one
locator an adapter emits that its own predicate refuses.**

**The exit criterion, stated so it can be applied rather than felt.** A slice's review loop ends when
a round produces **no BLOCKING finding that is either (a) a silent identity or data-integrity
defect, or (b) a legitimate input the system refuses.** Those two classes are what Gate B's
denominator depends on. Everything else — a false comment, dead code, an unreachable branch, a schema
that under-describes — is fixed when found and is **not** grounds for another round.

**What is explicitly NOT claimed.** Not that T12 is defect-free; a sixth reviewer would find
something. Not that reviews are optional: rounds one through three each paid for themselves many
times over, and Gate A as a whole still requires independent review before Gate B. The claim is
narrower — **the marginal round has stopped returning defects of the kind the gate depends on**, so
the next one is worth less than the slice it displaces.

**Alternatives rejected.** *One more round to get a clean APPROVE* — that is the unbounded loop
restated; five rounds produced five REWORKs and a sixth would most likely produce a sixth.
*Stop reviewing Gate A slices generally* — no; T13 has **never** been reviewed and one round is
running now. The rule is per-slice and evidence-based, not a blanket exemption.

**This is my call and it is Mit's to override.** It is recorded here rather than acted on silently
precisely because a future session reading "five REWORKs" will otherwise reopen the loop by reflex.

**Consequence.** T12 is done. **Next: T14 onward**, with T13's first review in flight. Gate B stays
prohibited until Gate A is complete.

---

## D-127 — Gate A slices T13 and T14: an approval bound to nothing, and the first code that WRITES a bundle

*2026-08-11, overnight autonomous run. T13 (reports, digest validation, completeness, the validation
run) and T14 (one-read storage, drafts, inspection, the production YAML emitter). Gate A remains NOT
met; T15–T19 follow.*

### T13's review found an approval that bound to nothing

The §20.6 clause tying an owner's approval to promoted content — the revision's inverse candidate view
must recompute the digest carried by both its manifest and its appended stamp — was **skipped for every
revision from 2 onward**. `_the_candidate_view_recomputes_its_approved_digest` returned early whenever
the manifest declared a parent and no `ParentSnapshot` had been supplied, and `validate_bundle` never
constructs one.

**Consequence, reproduced:** re-seal a revision-2 tree around documents nobody approved — recompute the
bundle digest, rename the directory, rewrite `COMPLETE` and `CURRENT` — and every remaining digest check
passes, because every remaining digest is recomputed from the new bytes. The one comparison standing
between that forgery and a clean report was the one that returned early.

**The early return's justification was wrong**, and that is the transferable part. It cited §20.6's
"validating an already-selected revision does not deep-parse ancestors". But the candidate view reads
only the parent's `revision` and `bundle_digest` — what the `StableManifestEnvelope` in §7 explicitly
permits history traversal to read — and `completeness._ancestor_manifest` **already read exactly that
from disk on the same code path**. The check could always have run.

**Fix: one reader, not two.** `completeness._ancestor_manifest` was extracted verbatim into
`digest.read_ancestor_manifest`, with `AncestorFault` and `AncestorUnverifiable` moving with it; the
completeness function became a four-line wrapper keeping its typed reasons and its opt-in byte audit. A
second ancestor reader would have been the defect class D-125 is about. `_parent_envelope` raises rather
than returning `None` for an unreadable parent, because `None` is a real answer — revision 1 has no
parent — and conflating the two would compare a child against a parentless candidate view and report
every child revision as a forgery.

**Verified three ways by the orchestrating session, not by the author.** A probe written from the
finding's CLAIM rather than from the fix, run in a worktree pinned to each commit:

| Run | revision-1 control | revision-2 forged |
|---|---|---|
| pre-fix `2e6f667` | fires (2) | **0** |
| post-fix `353debb` | fires (2) | **2** |
| fix mutated (parent never resolved from disk) | fires (2) | **0** |

The control firing in all three runs is what makes the revision-2 silence mean "the check did not run"
rather than "the forgery failed". The mutation restoring the exact pre-fix output is what makes the fix
load-bearing rather than incidental.

### The expiry ruling: the EARLIER of the two declared dates wins

`fact_value_expired` keyed only on the `expires_at` column, but §10.4's row for `certification.expiry`
is "block active use after **value date**" and the fact's value IS that date. A credential that lapsed
years ago with `expires_at: null` stayed `verified`, kept `resume` in its allowed surfaces, and was
counted in surface coverage — a résumé built from the bundle would assert it.

`_declared_expiry` now returns the **earlier** of the two, with `details["declared_by"]` typed as
`value | expires_at | both`. **Earlier, not later**, because a rule where the later date wins lets an
author revive a lapsed credential by writing a column date past the one the credential itself carries.
The packaged example sets both dates identically, which is exactly why no existing test distinguished
them.

The follow-up round then closed the hole at its source rather than at the reader: `models/facts.py`
gained `VALUE_DATE_KINDS`, and `PredicateSpec` now **refuses** `block_active_use_after_value_date` when
any legal value type lies outside it. The admitted set is defined as *the kinds the expiry check
actually reads* — not the kinds a date is *derivable* from, which would have admitted `year_month` and
`date_range` and left the hole exactly where it was. One constant, two readers.

### An unmeasured digest is not a clean one

The candidate-digest comparison is skipped when the parent is absent. That silence was byte-identical to
"compared and clean". `IssueCode.CANDIDATE_DIGEST_UNVERIFIED` was added — a **widening of a closed
catalog**, which this program treats as a contract change needing justification, and the justification
is that without it the two states cannot be told apart from the report. It reports at information tier
and changes no exit code. Three existing tests asserted the silence and now assert the visible form.

### T14 is the first code in this package that WRITES

`init_draft` cannot be built on `yaml.safe_dump`: measured, it emits plain scalars the restricted loader
refuses for **6 of the 33** packaged example documents. `yaml_writer.document_bytes` force-quotes
strings and then **verifies rather than restates** — it reads its own bytes back through
`load_yaml_bytes` and compares, so the loader's grammar exists in one place. Verified independently: 33
of 33 round-trip.

**`init` writes a deliberately invalid draft, and that is the right shape.** `IdentityDocument.person`
requires a display name and dates, and this package reads no clock, so `init` cannot author
`facts/identity.yaml` without inventing a person. Verified: a fresh `init` writes 30 files, exits 0, and
`validate --draft` reports **exactly one** finding, `missing_required_file (facts/identity.yaml)`. A
placeholder person that survived to promotion would be a fact nobody authored. **T18 owes the operator
a human translation of that message** — it currently reads as corruption rather than "author your
identity here".

**`init` writes the installed secret-scan ruleset, not an empty one** — an empty
`policy/secret-scan.yaml` would make the first revision claim a scan it never ran. Read from the module
at call time, never by-name import; that snapshotting defect has bitten this repo before.

### T14's two reviews: four BLOCKING, and one of them is class-level

Both lenses returned REWORK. The findings are recorded in full in
`scratchpad/T14-REVIEW-FINDINGS.md`; the two that generalize:

**The symlink confinement escape is not about `drafts/`.** The conformance lens found that a symlinked
`drafts/` escapes the bundle root while `init` still returns clean, exit 0. Extending it, **every**
declared root member does: `drafts`, `blobs`, `approvals`, `revisions`. `approvals/` and `revisions/`
show zero escaped files today only because `init` writes nothing into them **yet** — T16's promotion
writes both. `paths.py`'s own docstring says derivation IS the confinement boundary. The fix must be
**one check applied to every member of `ROOT_MEMBERS`**, at the point the root is resolved, so every
present and future writer inherits it. Four per-directory guards would be the restated-rule defect class
this program has spent five review rounds on.

**A test that asserts the defect it guards against.** `_referenced` returns `None` for "could not read"
and its docstring says "`None` is distinct from empty on purpose"; one function up, both
`referenced_blobs` and `unreferenced_blobs` collapse `None` to `()`. The guarding test is docstringed
"Empty and unmeasured are different answers" and then asserts they are byte-identical. It cannot fail
when the distinction is absent. Same class as the mutation survivor in D-125.

### Consequence and standing

T13 is merged at `c0020e8`; its follow-up (`t13-followup`, `4bd3c49`) is green and **ungated**. T14's
build is at `d681653` and its fix round at `d441e2d` is **UNVERIFIED** — the author was terminated
mid-round by a usage limit and never reported, so no account of the mapping from findings to changes
exists and it must be re-derived from the diff before merge. **Neither is pushed.** Gate A is NOT met;
Gate B stays prohibited.

## D-128 — Gate A T14 round 2, T15 and T17: what three green suites could not see

> **Corrected by D-130.** Two claims below are wrong as written: this entry's account of the fix
> rounds' verification omits a caveat STATE carries, and its SHOULD-FIX counts are overstated. Read
> D-130 with it.

*2026-08-11. T14's unreviewed fix round reviewed and repaired, T15 reviewed by two concurrent lenses
and repaired, T17 reviewed and approved. Gate A remains NOT met; T16, T18, T19 follow. Nothing on
this track is pushed.*

### The branches are stacked on T14, not on `main` — one merge, not two

`git branch --contains d681653` returns `t14-storage`, `t15-rebase`, `t16-promotion` and
`t17-schema`. All three downstream branches fork from **T14's base commits**, so merging
`t14-storage` into each brings T14's fix round **and** `main` transitively. The prior instruction to
merge `main` in first was wrong in a costly direction: it forces the same conflicts to be resolved
twice.

**The forward merge breaks callers without producing a conflict, and this was measured, not
predicted.** T14 made `conftest.quoted_yaml`'s `logical_path` required and fixed its own callers;
`t17-schema`'s `test_profile_bundle_schema_head.py:34` is a **new file T14 never saw**, so the two
never textually collide. A trial merge in a throwaway worktree reported `Automatic merge went well`
and then failed at runtime with `TypeError: quoted_yaml() missing 1 required keyword-only argument:
'logical_path'`. **Sweep every call of a signature the incoming branch changed; `git merge`'s silence
is not evidence.** This is the third instance of the same class on this track, after the two
byte-identical `OSError` helpers T13 and T14 each added independently.

**What the real merge of `main` into `t15-rebase` produced**, for the next slice to expect: two
conflicts, both in `inspection.py` and its test, and **four** `quoted_yaml` call sites needing repair
in T15's own new `test_profile_bundle_rebase.py`. Neither conflict was a logic conflict.

- The `inspection.py` conflict was **docstring-only**, and both sides were kept: T14 explains how a
  stray `NOTES.txt` is told apart from an interrupted install by reading the prefix from the writer,
  T15 adds why the classification needs the segment grammar. Complementary, not competing.
- The test conflict was the more dangerous shape: **`main` deleted a test that T15 kept.** Resolved by
  confirming T14 had *replaced* it with a strictly better one
  (`test_inventory_tells_an_interrupted_install_apart_from_a_file_that_does_not_belong`, which reads
  `DRAFT_TEMP_PREFIX` from the writer rather than hardcoding `.tmp-draft-abc123` and adds the
  `NOTES.txt` negative case) before dropping the superseded copy. **A deletion on one side of a merge
  has to be checked for a rename on the other**, or resolving it "safely" by keeping both restores the
  exact hardcoded-constant test the incoming fix removed.
- A line-based grep for the broken signature reports **false positives**: multi-line calls carry
  `logical_path` on a following line. Only the suite settles it.

The mirror also holds: some downstream findings are **fixed by** that merge and must not be patched
locally. `migrations.py` passes `str(exc)` into a diagnostic, which leaks an absolute path on
`t17-schema`; T14 fixed it at the raise site by dropping `bundle_root` from the message. Patching it
downstream would have been a duplicate guard.

### Confinement is an equality against the derived location, NOT `is_relative_to`

T14's round-2 BLOCKING was in the check its own audit had blessed as "the right shape". The shape was
right — one refusal over the closed grammar, not four per-directory guards — but it iterated
`ROOT_MEMBERS`, a set of **top-level names**, while the blob store is `paths.blobs_dir()` =
`blobs/sha256`, one component below the member named `blobs`. Symlinking the store, or one blob file,
out of the root passed the check, and those outside bytes were hashed into `evidence_set_digest` and
therefore `bundle_digest` while `validate`, `inventory` and `checkout` all reported **exit 0, clean**.
Design §6/§24's "self-contained under one root" was enforced by nothing.

**The root cause is the restated rule, not the missing component.** A check written over names can
never reach a path `paths` derives. The set of checked paths is now derived from `paths` —
`ROOT_MEMBERS` for the root's entries, `paths.blobs_dir` for the store, and the store's entries
individually, since one blob file is enough to decide `bundle_digest`.

**The predicate was specified wrongly by the orchestrator and corrected by the implementer.** The
brief said to pin the outside fact as `path.resolve().is_relative_to(bundle_root.resolve())`. That
admits a second escape: a member resolving to *another member inside* the root, under which
`drafts/` → `revisions/` makes `inventory` report a revision directory as a draft. What shipped is
the strictly stronger equality `path.resolve() == resolved_root / path.relative_to(bundle_root)` —
"must resolve to exactly where the layout derived it". Verified by weakening it back and watching
`test_a_member_that_aliases_another_member_inside_the_root_is_refused` go red (`DID NOT RAISE`), and
by re-running the reviewer's own probes: the escape cases flip to `symlink_refused`, the
inside-the-root alias stays refused where `is_relative_to` would have regressed it, and a symlinked
**bundle root** stays correctly allowed. **Do not "simplify" this back to `is_relative_to`.**

Residual risk stated in the code and deliberately not closed: the check is path-based and therefore
TOCTOU: a symlink created after it returns is not seen, and the write lands where the new link
points. Closing it needs `openat`/`O_NOFOLLOW` per component. A **bind mount was never tested**
because it needs root — untested, not a negative result.

### A green suite is not the signal; a mutation that stays green is

Across T14 and T15 the reviews found **7 BLOCKING and 12 SHOULD-FIX in code whose own suites were
green** — T15's 54 tests covered none of its six. The recurring shape is not a missing test but a
test that cannot fail:

- T14's guarding tests for the confinement check read the same `BLOBS_DIR`/`ROOT_MEMBERS` constants
  the check reads, so both agreed `blobs/` was the store. The replacements locate the store **by
  content** — the one file whose name is the sha256 of its own bytes — so they hold wherever the
  layout puts it.
- Three separate mutations to `inspection.py` (`:190-198`, `:412-413`, `:569-579`) left the suite
  entirely green, meaning two-thirds of an earlier BLOCKING fix could have been deleted silently.

**Both fix rounds were therefore held to: revert the check, watch the test go red, restore it.** That
standard, not the suite's colour, is what closed these.

### T15: one root defect wearing several masks, found by two lenses at once

Two lenses run concurrently on one commit both landed on `rebase.py:294-310` from different angles,
which is what identified it as one cause rather than two symptoms: a one-sided document deletion
silently discards the other side's work. The runtime lens found it for the six record-free
`policy/*.yaml` catalogs, which the record-ID overlap gate structurally cannot see; the conformance
lens found it for **additions** in the record-bearing case, where the worse half silently **reverts a
promoted record** with no change-ledger entry. The module already agreed this shape is a refusal —
`_rebased_manifest` refuses exactly it for `evidence/records.yaml` — and simply did not apply that
judgement generally.

The other five: a symlinked **backup root** was accepted as byte-identical (the entry check never
examined the root it was handed), after which the original draft was `rmtree`d unrecoverably at exit
0; the append-only history ledgers were merged as ordinary record lists, **deleting an approval
stamp** the selected revision carried; a merged document failing its own validator escaped as an
uncaught `pydantic.ValidationError` rather than a typed outcome; a **shadowed record ID** made an
edit invisible and the merge dropped one of the two records, with `BundleIndex.collisions` being the
exact available signal that `diff.py` never read; and a legal **14-character draft name could never
be rebased**, stranding the draft forever, because `paths.py`'s claim that "96 characters leaves room
for the longest derived suffix" was arithmetically wrong — the real cap is 13.

Confirmed sound and closed to re-litigation: the crash matrix at three boundaries the author did not
pick, injected with real `SIGKILL`; the lock contract under real subprocesses (contention → exit 3
`bundle_lock_held` with a whole-tree hash unchanged, a SIGKILLed holder's lockfile reacquirable,
nothing reading or ageing the lockfile); and `_install`'s no-writes claim under a whole-tree hash.
One author-declared gap was **refuted** (`rebase.py:354-355` is reachable end to end) and one
confirmed **dead** (`diff.py:175`, deleted per D-115).

### T15's fix, and the four judgement calls inside it

All six BLOCKING fixed, each pinned by a test watched red without its fix. The shapes worth carrying
forward:

- **The one-sided deletion refusal is now conditional on the base**, not on record identity: a
  document only one side has is dropped only when the other side left it exactly as the base had it;
  otherwise `draft_rebase_conflict` names the records that would be lost. That covers the record-free
  catalogs the overlap gate structurally could not see.
- **The append-only ledgers get their own merge** (`_merge_append_only`): the selected revision's
  sequence must be the result's **prefix**, our additions follow, and a draft-side removal *or*
  rewrite of an inherited entry refuses. This also removed the uncaught-`ValidationError` crash,
  because the ledger contiguity validator was what the raw merge was tripping.
- **A shadowed record ID now refuses** (`record_contents` raises `RecordIdCollision`, one
  `duplicate_record_id` per collision attributed to the tree holding it) rather than letting `_by_id`
  collapse duplicates last-wins.

**Judgement call 1 — the draft-name cap was made honest rather than the grammar changed.**
`MAX_DRAFT_NAME_LENGTH` stays 96 for operator-supplied names; a new `MAX_DRAFT_SEGMENT_LENGTH` =
96 + the derived suffix governs on-disk draft *directory* names. Changing the derivation would have
broken §19's pinned on-disk grammar and everything in T16 that depends on it. Consequence handled:
`inspection._draft_names` classifies with the segment grammar, or a long draft's backup would have
been reported as a stray artefact.

**Judgement call 2 — the backup-reuse `rmtree` was KEPT, against the literal text of §21/§6.** What
it removes is a copy the same command made two statements earlier under `DRAFT_TEMP_PREFIX`, proved
byte-identical to the retained backup first. Leaving it would strand a full-size `.tmp-draft-` tree
with **no drain**, which `inventory` then reports forever. That trades a provably lossless delete for
a permanent leak, and this repo's standing rule is that every quarantine needs a drain designed in the
same change — a bucket with no re-entry path is the worse outcome. Recorded as a deliberate departure
rather than silently taken.

**Judgement call 3 — `record_ids` is populated wherever the conflicting unit has record identity**,
and the contract is pinned in `_merge_conflict`'s docstring: empty means the unit has no addressable
records, where `path` + `details.field` is the locator.

**Judgement call 4 — the record-list permutation is documented as a known limit, not made a check.**
Detecting it would refuse the ordinary case where only the revision reordered. The claim at
`diff_records` was narrowed instead, since a permutation is not a reformatting. This is the one Lens A
probe (`m1`) that still fails by design, confirmed independently after the fix: 18 of 19 merge/stamp
probes pass and all 9 crash/lock probes pass.

**Two design sentences the code now deliberately departs from, and nobody has amended**, because
`docs/superpowers/` is untracked working material that must never be staged: §19 should permit an
empty `record_ids` for a field- or document-level conflict, and §21 should carve out "a draft the
command has proved byte-identical to a retained backup". Left for whoever holds the design text — if
it is not amended, judgement call 2 will be re-litigated.

### T17 is APPROVED, and `migrate` takes no `--draft`

One light pass, no BLOCKING and no SHOULD-FIX in its own diff. Its D-115 claim — that an
`if found != CURRENT_SCHEMA_VERSION` branch could never execute, because `load_documents` gates every
revision through `require_supported_schema` — is pinned by a tripwire rather than a comment, and the
pin is not self-agreeing: growing `SUPPORTED_SCHEMA_VERSIONS` to `{1, 2}` turns **three** tests red.
T18 must **not** add `--draft`/`--draft-name` to `migrate`: at v1 nothing is written, so the argument
could only be accepted and silently ignored, discarding operator intent. Design §7's bare form is
right and the plan's Task 18 CLI list is wrong.

### T16 is gated behind T15's fix

`t16-promotion` is byte-identical to the reviewed-REWORK `t15-rebase`, so it carries all six of
T15's BLOCKING defects, takes the same lock, computes the same digest over the same blob store, and
needs `_identical_trees`/`_tree_contents` — the function defect 1 lives in — for its own step 7.
Starting it before T15's fix lands would build on a known-broken foundation.

## D-129 — The two Gate A design departures are RULED: the design text was wrong, not the code

> **Corrected by D-130.** The §21 half of this ruling misdescribes what the code deletes. The
> ruling's *outcome* stands; its stated reason does not. Read D-130 before relying on it.

*2026-08-11, ruled by Mit ("we should do what is best for the project"). Both sentences amended in
`docs/superpowers/`, which is untracked, so this entry is the durable record. Closes the two items
D-128 left owed.*

T15's fix round deliberately departed from two sentences of the design and could not amend them. Both
departures are **upheld** and the design text is corrected, because in both cases the sentence was an
over-general statement of a narrower true rule.

### §21/§6: "no command deletes drafts" keeps its teeth, and gains one carve-out

The rebase's backup-reuse path `rmtree`s a `DRAFT_TEMP_PREFIX` directory. Literally that is a command
deleting a draft directory; in substance it is not, and the literal reading is the worse outcome.

What it deletes is a copy **the same command created two statements earlier** and has **proved
byte-identical** to the backup it retains. The prohibition exists to protect *the owner's work*, and
this is the command's own scratch. Keeping it loses on both of the project's own rules:

- It strands a full-size tree with **no drain**. Every quarantine owes a drain designed in the same
  change; a bucket with no re-entry path is a leak, and this one would never be collected.
- `DRAFT_TEMP_PREFIX` is precisely the marker `inventory` reads as **"an interrupted draft
  installation"**. So the residue would not merely sit there — it would assert, on every subsequent
  `inventory`, that an installation was interrupted when none was. **A false diagnostic is worse than a
  deletion**, and this project has repeatedly paid for reports that claim something that did not happen.

The amended text carves out exactly this and nothing wider: a staging directory the running command
created itself, under `DRAFT_TEMP_PREFIX`, within the same operation, and has proved byte-identical to
what it retains. **A command may never delete a draft it did not create, and never one it has not
proved redundant.** Both halves are load-bearing — drop either and the carve-out becomes a licence.

**Alternative rejected:** never create the redundant copy when reuse is detected. Cleaner in principle
and it would need no carve-out, but it restructures the install path — which the review verified holds
under real `SIGKILL` at three boundaries — to remove a provably lossless delete. Not worth
destabilising a crash-consistent path for a wording problem. Revisit only if that path is rewritten for
another reason.

### §19: an empty `record_ids` is a statement about shape, never a missing value

§19 promised `draft_rebase_conflict` carries "the exact record IDs". A field-level or whole-document
conflict **has** no addressable records — that is what the six `policy/*.yaml` catalogs are — so the
promise was unkeepable for a legitimate conflict class rather than merely unmet.

Ruled: `record_ids` is empty **exactly** when the conflicting unit has no addressable records, and then
`path` plus `details.field` (where the conflict has one) is the locator. The emptiness is now a typed
fact a consumer can rely on, not an absence it has to guess about, and the design says so.

**This is settled before T18 consumes it, deliberately.** T18 renders these diagnostics to an operator.
Had the contract stayed ambiguous, T18 would have had to choose a reading, and the wrong one — "no
records were affected" — reads as reassurance about the exact case where a whole document is in
conflict. The design now forbids that reading outright.

### The transferable rule

Both departures were reported as conformance defects and both turned out to be defects **in the
prose**. The lens that found them was right to raise them and right not to resolve them. The general
form: when code and design disagree, the question is which one states the narrower true rule — a
design sentence that forbids a provably lossless act, or promises a field that cannot exist for a legal
input, is the thing to fix. Amend the text in the same change that establishes the departure, or the
next reviewer re-raises it and the round is spent twice.


## D-130 — Correcting D-128 and D-129: what the fix rounds actually established, and what the rebase actually deletes

*2026-08-11, from a docs-only review of this session's own program records (5 BLOCKING, 5 SHOULD-FIX).
Dispatched because this program has repeatedly shipped documentation asserting a guarantee that landed
nowhere, and because the records below are what future sessions trust without re-deriving.*

### D-129's §21 carve-out described the wrong mechanism

D-129 upheld the rebase's backup-reuse deletion on the grounds that "what it deletes is a copy **the
same command created two statements earlier**", and concluded: "**A command may never delete a draft it
did not create**, and never one it has not proved redundant. Both halves are load-bearing."

**The first half is false, and so is that conclusion.** `rebase.py` does:

```
vacated = drafts_dir(bundle_root) / f"{DRAFT_TEMP_PREFIX}{uuid4().hex}" if reuse else backup
os.rename(draft_dir, vacated)   # the operator's OWN draft is renamed to the temp name
os.rename(staging, draft_dir)
shutil.rmtree(vacated, ignore_errors=True)
```

No copy is made. **The operator's own pre-rebase draft is renamed to a `DRAFT_TEMP_PREFIX` name and
then deleted.** The temporary prefix is applied *by the deletion path itself*, moments before deleting —
it does not mark a directory the command authored.

**The ruling's outcome is unchanged and still correct**, but for one reason only: `reuse` is set only
after `_identical_trees` has proved the retained backup holds those exact bytes. The honest rule is
therefore weaker and narrower than D-129 claimed:

> A command may delete a draft directory **only** when it has proved, by content comparison, that those
> exact bytes are retained elsewhere in the bundle. Provenance is irrelevant; the proof is everything.

That matters because D-129's version would license deleting anything wearing a temp prefix, and would
forbid exactly the deletion the code performs. **The misdescription originates in the source comment at
`rebase.py:494-499`, which is the load-bearing error** — D-129 restated the comment instead of reading
the four lines beneath it. This is the same defect class the program keeps paying for: a rule restated
from prose rather than derived from the code it governs.

### D-128 stated the fix rounds' verification more strongly than the evidence supports

D-128 says "All six BLOCKING fixed, each pinned by a test watched red without its fix" and "Both fix
rounds were therefore held to: revert the check, watch the test go red, restore it." Those are the
*agents'* reports plus the orchestrator's spot checks. **What was actually established** is narrower and
STATE says so: the fix rounds got targeted verification — mutating each predicate, re-running the
reviewers' archived probes — and **not an independent review round of their own**.

DECISIONS is the permanent file and STATE is rewritten every session, so the caveat lived only in the
half that disappears. It belongs here: **an independent review of the T14 and T15 fix rounds is OWED**,
and until it lands, "each pinned by a test watched red" is an author's claim, not a verified fact.

An independent review begun immediately after has already returned one confirmed regression the fix
round introduced: a symlink **loop** in the checked set makes `require_confined_root` raise an uncaught
`RuntimeError`, where the pre-fix check refused it cleanly with `symlink_refused`.

### Count and scope corrections

- **T15's SHOULD-FIX count was 6, not 8** (2 in the runtime lens, 4 in the conformance lens; that lens's
  §8 is a table of confirmed-true claims, not findings). The session total is therefore **7 BLOCKING and
  10 SHOULD-FIX**, not 12. BLOCKING counts were correct.
- **Gate A is 16 of 19 slices merged, not 15** — T1–T15 and T17, with T16, T18 and T19 remaining.
- **"Nothing on this track is pushed" is false.** T1–T12 are on `origin/main` and shipped inside the
  0.3.0 wheel. What is unpushed is everything from T13 onward. The distinction is the whole subject of
  [[gate-a-t1-t10-ship-in-the-0-3-0-wheel]]: unreviewed Gate A code already went out under an
  irreversible version.

### The transferable rule

**Dispatch a docs-only reviewer against the records a session writes, in that session.** These were not
subtle: a stale paragraph contradicting a table 45 lines above it in the same file, a retracted cause
still asserted in bold 56 lines before its own retraction, and three merged items still listed as live
blockers. All survived two passes by the session that wrote them, because an author re-reads for what
they meant rather than for what they said. The review cost one agent and caught five statements a later
session would have acted on.


## D-131 — The T14/T15 fix-round review's findings are fixed: a merge short-cut that skipped the append-only rule, and five residues

*2026-08-11. Acting on the independent review recorded in D-130 as OWED and delivered as REWORK
(1 BLOCKING + 5 SHOULD-FIX). Evidence: `.agent/T14-T15-FIXROUND-REVIEW.md`. Five commits on `main` —
not one per finding: `d99b677` carries three of them, because they are three clauses of one
check, and a sixth commit corrects `d99b677` rather than closing a finding of its own.*

### The BLOCKING one: an optimisation that disabled the rule it was optimising

`_merge_plan` took the draft's document wholesale whenever the selected revision had left it
byte-identical to the base. For an ordinary document that is right — a merge could only reproduce
it. For an **append-only** ledger it is not, because the draft's copy may have *dropped* an
inherited entry, and the whole point of §17's rule is that it cannot.

That is not an exotic path. A promotion appends a change record and an approval stamp; it almost
never appends a **ruling**. So `conflicts/rulings.yaml` is byte-identical across an ordinary
promotion, the short-cut fires, and a draft that deleted an owner's ruling installed at **exit 0
with no diagnostic** — the selected revision's sequence no longer a prefix of the result, which is
the exact property T15's fix commit claimed in three places.

The fix is one condition in `_merge_plan`, not a change to `_merge_append_only`, which the review
confirmed correct for all three of its document types wherever it actually runs. `is_append_only`
reads the same mapping `merge_document` dispatches on, so the list of append-only documents is not
written down twice — the defect class this subsystem has already paid five review rounds for.

**Why the suite could not see it.** The only test of the positive prefix property survived deleting
the entire `_merge_append_only` dispatch, because for an untouched draft ledger the old record-wise
merge produced the same answer. The suite pinned the two refusals and not the property they exist to
protect. The new test states the scene it needs — it asserts the revision's bytes are unchanged from
the parent's — rather than assuming the fixture happens to provide it.

### An unresolvable path is a refusal, not an exception

`Path.resolve()` raises `RuntimeError` on a symlink loop. That is neither a `ProfileBundleError` nor
an `OSError`, so it escaped `inventory`, `validate` and `checkout` uncaught, carrying the absolute
bundle path in its message. The check T14's fix round replaced had refused the same input cleanly
with `symlink_refused`. **A fix that strengthens a predicate inherits every way the new predicate can
fail**, and `resolve()` fails in a way the old one could not.

### Deletion is licensed by proof of retained bytes, never by provenance

D-130 corrected D-129's account of what the rebase's backup-reuse path deletes. The load-bearing
error was the **source comment**, which D-129 restated instead of reading the four lines beneath it.
The comment now says what the code does: the operator's own draft is renamed under the temporary
prefix by the deletion path itself, moments before deleting, and the only licence is `identical_trees`
having proved those bytes are retained at the backup.

### `record_ids` is a statement about the conflicting unit

D-129 made an empty `record_ids` a typed fact: the unit has no addressable records. The
whole-document refusal broke it, reporting `[]` on a ledger holding twelve. A document-level
invariant's unit **is** the document, so the IDs are attached at the raise site — where the failing
unit is known — rather than re-derived by the caller from a field name. Settled before T18 renders
it, because "no records were affected" is the reading D-129 forbids and the whole-document case is
exactly where it would be reassuring and wrong.

### A report that names something no command accepts

`inventory` classified drafts with the 179-character segment grammar while `draft_root` and
`rebase_draft` still used the 96-character operator-facing one, so a long draft's rebase backup was
listed and then refused — as an uncaught `BundlePathError` out of functions typed to return an
outcome, on the one directory that is the only copy of a pre-rebase draft. **Addressing an existing
directory** now uses the segment grammar; **requesting a new name** still uses the shorter cap, which
`init_draft` and `checkout_current` apply themselves. A name that is already derived cannot yield
another suffix inside the per-component limit, so that is a typed refusal naming the way out.

**Alternative rejected:** have `inventory` report backups as a category of their own. It would close
the asymmetry by making the names unaddressable on purpose, and re-parenting a backup is the one
recovery available when a rebase went wrong.

### The confinement check no longer walks the store once per blob

`require_confined_root` called `resolve()` on every stored blob, on every command that reads the
bundle, at a cost linear in the store (measured below). For a store *entry* the equality is equivalent to
`is_symlink()`, because every ancestor is checked one loop earlier, so an entry can only fail it by
being a link itself. One `lstat` replaces the walk, and the same `lstat` closes the FIFO hole: a
named pipe resolved to exactly its own place, satisfied the equality, and then blocked `open()`
forever with no timeout and nothing reported.

That widened the refusal to any non-regular entry, which changed one existing test: it had made a
blob unreadable by replacing it with a **directory**, and confinement now refuses that one layer
earlier. The claim it pins — an unreadable blob is exit 3 and installs no draft — is unchanged; its
mechanism is now permission rather than kind.

**Re-measured, and the review's two figures are both corrected.** Its "~6×" was a micro-benchmark of
the two predicates alone; end to end through `require_confined_root` the gain is **2.3×**, because
the walk either predicate sits inside is shared. And its absolute costs were inflated about ninefold
by the load average of 16–21 it honestly flagged as an upper bound: on an idle machine the *same
pre-fix code* costs 976 ms at 20,000 blobs, not 8.7 s. Both predicates measured on this machine at
load 3.1, minutes apart, with the pre-fix one restored into a copy of `src/` selected by
`PYTHONPATH` — a figure taken under one load and compared against one taken under another is not a
comparison.

| blobs in the store | `resolve()` per entry | one `lstat` per entry |
|---|---|---|
| 100 | 4.9 ms | 2.3 ms |
| 1,000 | 46.1 ms | 19.5 ms |
| 5,000 | 240.0 ms | 101.2 ms |
| 20,000 | 975.8 ms | 430.3 ms |

### The symlink-loop fix was itself wrong on one of the three interpreters CI runs

Translating `resolve()`'s `RuntimeError` into a typed refusal closes the hole only where the
exception exists. Measured on all three interpreters in CI's matrix:

| Interpreter | `Path.resolve()` on a self-referential symlink |
|---|---|
| CPython 3.11.14 | raises `RuntimeError` |
| CPython 3.12.12 | raises `RuntimeError` |
| CPython 3.13.12 | returns the loop's **own path** — which then satisfies the equality |

So on 3.13 the loop was not merely reported badly, it was **admitted**. The local venv was 3.12, so
the first fix's test passed here and would have gone red in CI — the third distinct form D-117's
"green locally is not green CI" has taken in this program, and the first where the *behaviour* rather
than the tooling differed. The clause is now stated over what all three agree on: the path is a link.
Every path in the checked set has had its ancestors checked one loop earlier, so a member being a
link at all is already a refusal.

**This was found only because a fresh worktree resolved a different interpreter than the repo's own
venv** — `requires-python = ">=3.11"` with no `.python-version`, so `uv` picks the newest available.
That accident is worth keeping: a worktree on a different matrix entry is free cross-version coverage
for a gate that otherwise only ever runs one. **`uv run --python X` inside the repo root silently
replaces `.venv`** and left it on 3.11; repair is `uv venv --clear --python 3.12 && uv sync
--reinstall --all-groups`, never `--reinstall-package`.

### The transferable rule

**Two of these six are the same shape: a fix that moved a boundary rather than closing a gap.** The
draft-name cap moved from 13 characters to 96; the confinement predicate got stronger and acquired a
new failure mode. When a fix changes *which* inputs a rule applies to, the question to ask is not
"does the reported input now pass" but "what is on the other side of the new boundary" — which is
the question the reviewer's mutation of each predicate answers and the author's own reproduction
does not.


## D-132 — Gate A slice T16 reviewed by three lenses: the highest-risk slice, and the one defect two of them found separately

*2026-08-11. Three concurrent reviewers against the same four commits, per `BRIEF-REVIEW-COMMON.md`'s
effort table, which allots T16 "two lenses plus a concurrency-specific pass" because promotion is
where an owner's approval becomes an immutable revision. Verdicts: **REWORK, REWORK, APPROVE**.
Reports at `.agent/T16-REVIEW-LENS-A.md`, `-LENS-B.md`, `-CONCURRENCY.md`.*

T16's own gate was **exit 0, 5,729 passed, 95.84%**, and its build ran a 23-mutation sweep. That is
the third proof this session that **a green gate is not sign-off**: the reviews found a silent
identity fault underneath it.

### The BLOCKING, found independently by both lenses

`promotion.py:426`. `_parent` guards the parent's `bundle_digest` recomputation with
`if not quarantined:`. §6 waives **only** blob-integrity and completeness checks for a quarantined
blob; this waives the whole recomputation. So a parent whose **non-ledger** documents were edited
after promotion is silently extended, and the child cements a `parent_bundle_digest` naming a
directory that demonstrably holds different content — exit 0, no diagnostic. `_parent`'s own
docstring promises the opposite.

All that survives the skip is the ledger-prefix check, covering 3 of ~27 documents. **The shipped
test written for exactly this — `test_a_broken_blob_does_not_excuse_an_edited_parent_document` —
edits `history/changes.yaml`, which that check catches with no blob bytes at all.** The arm the test
covers is not the arm that is open. Both lenses reached it from different directions: one by
tampering with `policy/units.yaml` (record-free, so it moves no record digest and needs no approval),
one by reading the docstring as a claim to be falsified.

**No command distinguishes the two worlds.** `validate --completeness` on the child returns
byte-identical code sets either way, and `validate` on the parent cannot recompute the digest because
the blob it needs is the missing one. That is D-126 clause (a) — a silent identity fault — so the
review loop does not stop here.

The fix is feasible literally: both blob-reading sites key the leaf by the *recomputed* hash, which
for an intact blob equals the declared digest, so substituting the declared digest for the
quarantined blob alone reproduces the parent's digest on the legitimate recovery path and diverges on
the forged one.

### What the concurrency pass established, and why it still cost the least

APPROVE, 0 BLOCKING, 1 SHOULD-FIX. It enumerated **20 write boundaries from `promotion.py` itself
rather than from the author's test list** — adding seven the test list lacks — and drove a real
`SIGKILL` at every one against a fresh bundle. **No boundary produced a `CURRENT` pointing at an
incomplete tree, a half-written store, or a revision without `COMPLETE`.** Its negative control is
the load-bearing part: the same kills against a mutant with steps 7 and 8 swapped leave
`current_pointer_mismatch`, and a reader hammering across that mutant reported 690 bad reads of 842,
against **0 of 148** on the real thing. It also confirmed §6 recapture recovery now runs end to end,
with a control showing that reverting only T16's `approval_id` scope fix reintroduces
`duplicate_approval_id` — so that fix really is what unblocks it.

Its one finding: `tree_contents` type-checks symlinks but nothing else, so a FIFO reaches
`read_bytes()` and blocks `open()` forever — newly reachable from `_install` → `identical_trees`,
**while holding the bundle lock**. The same class D-131 closed in `require_confined_root` hours
earlier, in the function T16 *moved* rather than wrote.

### The rest

Four ordinary operator inputs escape `promote` as an uncaught `pydantic.ValidationError` from two
raise sites, and a third arm escapes only when there is no parent — the identical input *with* a
parent is a typed refusal. `str(BundleIoError)` puts an absolute `$HOME` path in a
`Diagnostic.message`, which T18 is about to render as JSON. `build_approval_stamp`'s ids are not
"unique by construction" as its docstring claims — a collision was reproduced. And a test asserts a
value equals itself, inside the test that exists to prove a retry does not reuse torn bytes.

Lens B also attacked commit `9adc068`'s claim to have removed a check that could not fire and
**could not falsify it**, three ways. A removal justified by D-115 is exactly the kind of claim that
should be checked by someone other than its author, and this one held.

### The transferable rule

**Three lenses on one commit cost about the same wall-clock as one, and the two that overlapped did
not duplicate each other — they corroborated.** The BLOCKING was found twice, from a runtime probe
and from a docstring read, which is much stronger evidence than one finding it twice as thoroughly.
The concurrency pass, which shared no ground with either, returned the cheapest verdict and the most
durable artefact: a boundary table derived from the code rather than from the tests, which is the
thing a later session can re-run.


## D-133 — Correcting D-130 and D-131: what is actually pushed, and five statements a docs review caught in this session's own records

*2026-08-11, from a docs-only reviewer dispatched against the records written earlier in the same
session — the practice D-130 established after the last one found five acted-upon falsehoods.
Verdict REWORK: 2 BLOCKING, 4 SHOULD-FIX. It also verified 37 claims true, including the whole
interpreter-divergence story, which it reproduced independently.*

### D-130's push correction over-corrected, and this session propagated it

D-130 retracted "nothing on this track is pushed" and replaced it with "**T1–T12 are on `origin/main`
and shipped inside the 0.3.0 wheel**". That replacement is false on both halves, and it was asserted
without checking:

```
$ git log --oneline -1 origin/main
88c5857 docs(program): record T11 completion
$ git cat-file -e origin/main:src/boardwatch/profile_bundle/imports.py
fatal: path ... exists on disk, but not in 'origin/main'
$ git ls-tree --name-only v0.3.0:src/boardwatch/profile_bundle/
__init__.py blobs.py canonical.py errors.py examples index.py layout.py models
paths.py resources schema.py secret_scan.py validation yaml_loader.py
```

**`origin/main` carries T11. The wheel carries less — T1–T10 — because `dc1ffec` predates
`approvals.py`, `effective.py`, `imports.py` and `enumerators.py`. Everything from T12 onward is
unpushed.** The project's own earlier note said T1–T10 and was right; D-130 escalated it to T12 while
correcting a *different* error in the same sentence, and D-131 and STATE inherited it.

The unchanged conclusion: **unreviewed Gate A code did go out under an irreversible version**, which
is what that sentence exists to record. Only the extent was wrong. But the extent is the part a later
session would act on — "T12 is already public" and "T12 is unpushed" imply opposite things about
whether a defect in it is a release problem.

### `main` was not gated, and STATE did not say so

STATE carried a combined-gate figure that predated the fix commits while marking the fixes complete,
with every other row in the same table carrying its own gate. The fixes had `tests/profile_bundle/`,
ruff and mypy only — which **this repo explicitly does not count as green**, and a narrow run is
precisely what cannot see the cross-suite conftest collision STATE warns about thirty lines later.
Stating the deferral is the difference between a deliberate choice and a gate nobody notices did not
run.

### The 8.7 s figure outlived its own retraction by sixteen lines

The corrected measurement was **appended** to D-131 without grepping for the number it replaced, so
the retracted figure survived in the entry's own prose sixteen lines above the table correcting it —
and, worse, in a **shipped docstring** in `storage.py`. This is [[retracting-a-claim-means-grepping]]
recurring inside the very entry that was performing a retraction. A correction is not complete until
the old number is gone from every file, source included.

### The FIFO fix was reported complete when one of its two sites was still open

STATE listed the FIFO hang as fixed. `require_confined_root` was fixed; `rebase._tree_contents` — the
same defect, in the other place the rule lives — was not, and the reviewer reproduced it still
blocking under the bundle lock. It is fixed now. The T16 review had reported the same shape in the
copy T16 *moved* into `storage.py`, so the class was named twice and the instance on `main` was
missed both times.

### Three counting errors

"Four commits, one per finding" (D-131) and "six commits" (STATE) described the same five commits, of
which one carries three findings and one corrects another. "**16 of 16 mutations RED**" contradicted
its own parenthetical, which enumerates fifteen plus one green. All are stated correctly now.

### The transferable rule

**A count and an extent are the two things a reviewer can check that an author cannot.** Every finding
here is of that kind — a number, a scope, a "complete" — and not one is a matter of judgement. The
author had re-read all of it. What separates the reviewer is that it ran `git cat-file` instead of
reading the sentence that said what `git cat-file` would return.


## D-134 — A finding's tier is a property of the operation, not of the code alone

*2026-08-12. Lens B's T16 review asked for a formal ruling rather than a fix on `promotion._parent`
emitting `CORRUPT_BLOB_QUARANTINE` at `tier="warning"` when the closed catalog in `errors.py`
declares it `blocker`. Ruled by Mit. The ruling ratifies the mechanism; the finding's own premise was
false and is corrected below.*

### The premise was wrong in two ways, and both were checked before ruling

Lens B reported the override as "the only tier downgrade in the package that crosses two levels", and
the session handoff carried that forward. `_TIER_RANK` is `error: 0, blocker: 1, warning: 2,
information: 3`, so `blocker → warning` is **one** level. The two-level downgrade is a different site
entirely. And there are **three** overrides now, not two — T18 added one after lens B ran:

| Site | Code | Declared → emitted | Move |
|---|---|---|---|
| `promotion.py:459` | `corrupt_blob_quarantine` | `blocker` → `warning` | down 1 |
| `authoring.py` (approve's quarantine diagnostic) | `corrupt_blob_quarantine` | `blocker` → `error` | **up** 1 |
| `validation/referential.py:371` | `broken_reference` | `error` → `warning` | down 2 |

That table is the argument. **One code appears at three different tiers in three operations**, and the
third override moves in the opposite direction from the one that prompted the question — so a rule
phrased as "call sites may soften the catalog" would not describe the code either.

### The ruling

`tier_of(code)` is the catalog's **default** severity. The tier a *`Diagnostic`* carries is a
statement about **the operation that produced it**, and `outcome_with` deriving the outcome category
from `finding.tier` rather than from `tier_of(finding.code)` is therefore correct, not a bug.

The same physical condition legitimately means different things to different commands. An unreadable
evidence blob is: the thing `checkout` was asked to deliver, so the draft is unusable — `blocker`; a
condition `promote`'s §6 recovery path exists to carry, where refusing would strand an owner with a
bundle no supported command repairs — `warning`; and bytes an owner is being asked to *approve*,
where approval of what cannot be read is not an approval — `error`.

**Every call-site override must carry a comment naming the operation-specific reason.** All three
already do. An override without one is a defect, because the whole basis of this ruling is that the
tier encodes something the code alone cannot.

### Alternative rejected: forbid overrides and split the codes

Give each operation its own `IssueCode` (`corrupt_blob_quarantine_promote`, …) so `tier_of` is the
sole authority. Rejected because `IssueCode` membership is a contract and T18 now renders these codes
in a JSON envelope, so this trades a documented per-operation tier for a permanent widening of the
emitted surface — and it would restate the *operation* in the code name, which is the "same thing
written down twice" class this program has already paid five review rounds for.

### The transferable rule

**Verify a finding's premise before ruling on it, including a reviewer's.** Every claim in lens B's
finding was checkable in two commands, and the count and the extent were both wrong — the same pair
D-133 identified as "the two things a reviewer can check that an author cannot", here failing in the
reviewer's own direction. A ruling inherits the authority of whatever it is written against.

---

## D-135 — The Gate A integration gate is green on all nineteen slices, and the 03:10 job misfired a second time

*2026-08-12, the 03:10 unattended run. This entry exists because the session that started the gate
did not live to read it, and because a scheduled job carrying a one-shot prompt fired again.*

### The gate result

`make check` on `t18-cli` **`a64e6fa`** — the integration branch carrying all nineteen Gate A
slices — finished **GATE_EXIT=0 · 5,906 passed · 1 deselected · 95.63% · 16m42s**, on Python
**3.13.12**. Full evidence, including how the log was bound to that sha rather than assumed to
match it, is at `.agent/GATE-A-FINAL-GATE.md`. Progression: `e4d79aa` 5,831/95.59% → `d64af3c`
5,811/95.55% → `a64e6fa` **5,906/95.63%**.

The gate the previous session started was recovered, not re-run. Re-running it would have cost
seventeen minutes to reproduce a verdict already written to disk, and the four facts that bind the
log to the sha are cheaper to check than the suite is to run.

**One caveat stated precisely, because a slightly-wrong containment claim has cost this program two
correction entries already (D-130, D-133).** `main` is **not** an ancestor of `a64e6fa`. `main`
carries three commits the gate did not see — `26176c9`, `e30da5e`, `d3a3127` — and all three are
docs-only, which per D-116 owe `generalization` + `index-check` rather than a full gate. The gate
therefore covers all of Gate A's **code** and none of those three commits, which is sufficient.

### `t19-authoring-guide` held nothing

The handoff flagged an agent mid-flight on the authoring guide when the session was killed — the
"killing a mid-mutation agent breaks the tree" class. It did not fire here: the branch has no
commits beyond the integration base, its worktree is clean, there is no stash, and
`docs/profile-bundle-authoring.md` does not exist. The branch is an alias for an ancestor of
`a64e6fa` and is safe to delete. The guide is entirely unwritten.

### The 03:10 job misfired a second time, and the self-check caught it in five commands

`com.mitsheth.boardwatch-p6.plist` is a daily `StartCalendarInterval` job carrying the **one-shot**
"execute P6 Slice 1" prompt. It asserts `main` at `fb0386a`, now **hundreds of commits** back and drifting daily; P6 Slice 1,
2 and 3 all shipped long ago. D-123 recorded the first misfire on 2026-08-11 and ruled that such a
prompt must self-check or be deleted after it runs. **The self-check worked** — `git merge-base
--is-ancestor`, the presence of `identity_queries.py`, `identities_cmd.py`, both migrations and the
root `tests/conftest.py` settled it before any code was touched. It is still not self-*correcting*,
and it will fire again tomorrow at 03:10.

**Not fixed here by design.** The remedy is a `launchctl bootout` or a repointed prompt, the
standing table assigns it to Mit, and the run's own rules forbid starting work the prompt does not
ask for. The exact command is in tonight's status file.

### Four choices this run made that the situation left open

1. **Recorded rather than built.** The prompt's task was void, so the governing instruction became
   CLAUDE.md's session-start ritual. The ritual's next action is Gate A, whose owed items are three
   reviews and a design-blocked doc — none of which is appropriate work for an unattended 3am run.
2. **Dispatched no review.** T18's fix-round review is Gate A's true next step and it was
   deliberately **not** started. A "next=X" line in a state file is not approval for an expensive
   fan-out; review agents spawn nested sub-agents; and the immediately preceding session had already
   ended on usage roughly ninety minutes earlier. Burning the remaining window on a review would
   have risked losing the one deliverable an unattended run can always produce — the record.
3. **Left the authoring guide unwritten.** It is the last Gate A deliverable and is documentation, so
   it looks like ideal unattended work. It is not: §19's authoring flow is the subject of the open
   `evidence_link_asymmetry` question, which is Mit's and explicitly not to be resolved by fiat.
   Documenting a flow that cannot end clean would produce a guide that must be rewritten once the
   owner rules.
4. **Committed docs-only work to `main`.** The run's rules say never merge to `main`, on the basis
   that nothing is reviewed at 3am. That basis is about code; this session produced no code. The
   precedent is D-123's own entry, which the first misfire committed straight to `main`. **No Gate A
   branch was merged, and `main` is still not pushed past `88c5857`.**

### The transferable rule

**A scheduled job is a standing claim about the repo, and it decays.** A prompt that names a
starting sha is falsifiable in one command, which is what makes the misfire benign — but a job that
re-asserts a completed task nightly will keep spending a real window on a self-check until someone
unloads it. Cheap to detect, cheap to fix, and it has now cost two sessions.


## D-136 — Gate A slices T18 and T19: two lenses, a ten-commit fix round, and an integration merge where two green branches wrote one rule twice

*2026-08-12. T18 (the CLI) reviewed per `BRIEF-COMMON.md`'s effort table — "two lenses, one on the
boundary", because T18 is the package's first non-inert surface. Verdicts **REWORK, REWORK**. Reports
at `.agent/T18-REVIEW-LENS-A.md` and `.agent/T18-REVIEW-BOUNDARY.md`. The gate that closes this work
is D-135.*

### Each lens found a BLOCKING, and neither found the other's

**Lens A (adversarial runtime), 7 findings.** Its BLOCKING: `authoring.add_evidence` appended to
`evidence/records.yaml` and never restated `manifest.evidence_set_digest`, which is a real digest —
not one of §19's four sentinels — and is validated for drafts. So **100% of successful captures**
ended reporting `evidence_set_digest_mismatch`, §21's *"evidence mutated after promotion"* row, and
no command repaired it. The tool told an owner their evidence had been tampered with every time they
used it correctly. `drafts.py:427` and `rebase.py:463` both recompute it; only the new module did not.

**The boundary lens, 4 findings plus a clean-verification pass.** Its BLOCKING: `validate --draft`
probed `tree.is_dir()` **outside** `_guarded`, so an `EACCES` on `drafts/` escaped as a raw traceback
printing the operator's `$HOME`, at exit **1** where §21 requires **3**, emitting no JSON even under
`--json`. Its negative control is what makes it airtight: `inventory`, which does the same work
*inside* the guard, answers the identical permission state with `{"code":"io_error"}` at exit 3 and no
path. The machinery was right; one line sat outside it.

**Neither suite could see either.** Lens A's was invisible because
`test_add_evidence_records_the_capture_and_revalidates` asserted the written file and the payload but
never `exit_code` — and its docstring, *"one answer says both 'the change landed' and 'the draft is
still promotable'"*, was false as written, since the answer always said not-promotable.

### Both lenses independently upheld the design call, and ruled the design text wrong

T18 flagged for overturn that it emits a **uniform JSON envelope on all twelve commands**, leaving
`reports.report_json`/`report_text` production-unused. Both lenses upheld it, from different
arguments: §19's `--json` list is illustrative while §21's exit contract is normative and
family-wide, and several of §21's sharpest failure rows arise only in commands §19 does not list.
`report_text` also cannot carry the candidate digest §19 step 7 binds the approval to. **The code is
right and the design text is wrong** — §19 is what changes.

The measurable consequence was the finding: the orphaned renderers had **already diverged** from the
live path, and deleting the candidate digest from *both* live renderings passed every test, because
the thirty tests that looked like they covered §19 step 7 could not fire. They are deleted (D-115).

### The fix round: ten commits, and four declines that were arguments rather than silence

One fix per commit, each quoting its red-without-fix output. Mit accepted two declines: recomputing
the evidence digest in `resolve_conflict` (a ruling touches neither the evidence document nor the
blobs, so the recompute **could not fire** — D-115, and the guarantee is pinned where it actually
lands, on the manifest being byte-identical after a ruling), and `rebase._conflict`'s `record_id`
slot (inside T16's already-reviewed slice, and changing it moves `Diagnostic.sort_key`).

Two design judgements inside the round are worth not re-deriving. `_with_revalidation` and `promote`'s
read-back compose with `OperationOutcome.from_diagnostics` rather than `outcome_with`, because
`outcome_with`'s could-not-complete precedence is right for a command's own work and **wrong after it
has committed** — exit 3 tells a caller nothing happened, and the retry then lands on
`duplicate_record_id`. And `promote` re-reads the manifest from the promoted tree rather than
returning a richer type, which is the program's own "count the deliverable through a different path"
rule; a failed read-back reports `null`, never `""`, which is a *draft's* sentinel and would claim a
revision was promoted without an approval.

### The integration merge: three traps, all previously recorded, all fired again

1. **A deletion on one side was a rename on the other.** `main` fixed the FIFO hang in
   `rebase._tree_contents`; T16 fixed the same defect in the `storage.tree_contents` copy it had
   *moved*. One rule, two homes — resolved to the new home, with `main`'s now-dangling test removed
   rather than repointed, because T16's covers the same claim and additionally pins `identical_trees`
   in both directions.
2. **A byte-identical hunk arrived from both sides.** `bace523` and `c112aad` share blob `dc01606`,
   so the merge saw one change. Confirmed by blob hash rather than assumed, as `c112aad`'s message
   asked.
3. **Two independently-green branches wrote the same rule twice.** The T18 fix round and T19 both
   rewrote `test_profile_bundle_hash_isolation.py` after the boundary lens found the guard grepping
   for a literal that `from boardwatch.profile_bundle import canonical` never contains. **Neither was
   a superset**: the fix round kept a dotted-substring lens catching an `importlib`-assembled name but
   wrote its own `ast.walk`; T19 resolved through the shared `tests/profile_bundle/import_graph.py`
   the tailor-isolation test also uses, but dropped the substring lens. Resolved as the **union**, so
   there is one AST walker in the repository rather than two — and passing the containing package
   closed a **relative**-import arm neither branch covered.

### `validate` could not distinguish a forged revision from a recovering one, and the gap had two arms

T16 closed the promotion half of lens A's T16 finding 2 — `promote` refuses, so nothing is cemented —
and left the read-only half open: `bundle_digest` raised on the unreadable blob, `_computed` returned
`None`, and the check said nothing. `validation/digest.py::_bundle_digest_of` now passes the same
keyword-only `quarantined=` seam, classified by the store's own `quarantined_blobs`.

Mutation-checked by reverting only that function against a `PYTHONPATH`-selected copy of `src/`. The
gap turned out to have **two** arms, and only one was reported:

| scene | pre-fix | post-fix |
|---|---|---|
| forged document, **missing** blob | **silently unreported** | reported |
| forged document, digest-mismatch blob | reported | unchanged |
| untampered, missing blob | clean | unchanged |
| untampered, **digest-mismatch** blob | **accused of forgery** | clean |

The false positive on the last row was reported by nobody: `validate` told an owner on the supported
recapture path that their revision had been tampered with. The substitution is exact — `write_blob`
verifies before a blob becomes visible, so an intact blob's computed hash *is* its declared one —
which is why the untampered rows report nothing and the broken blob stays
`validation/evidence.py`'s finding alone, as `_computed`'s docstring requires.

### A late commit silently invalidated a running gate

The fix agent reported **ten** commits after nine had been merged and the final gate started; the
tenth was not in the tree being measured. Killed at 42% and restarted rather than spend thirteen more
minutes producing a verdict for something that was not the deliverable. **Re-check an agent's branch
for late commits immediately before gating** — an agent that has stopped emitting output has not
necessarily stopped committing.

### The transferable rule

**A reviewer's premise is a claim, not a given.** Ruling on lens B's tier-override finding (D-134)
required checking it, and both its count and its extent were wrong. This is D-133's lesson —
a count and an extent are what a reviewer can check that an author cannot — **running in the
reviewer's own direction**, which is the direction nobody thinks to check.


## D-137 — Gate A's review loop CLOSES at round five, and a two-document write is named rather than made atomic

*2026-08-12. Rounds four and five of T18's review chain, and the design ruling the fourth round
forced. Reports: `.agent/GATE-A-CLOSING-REVIEW.md`, `.agent/GATE-A-ROUND5-REVIEW.md`. Mit delegated
the path forward; this entry is that decision.*

### The loop closes, and the criterion was stated before the round that closed it

D-126 ends a slice's review loop when a round finds no BLOCKING that is either **(a)** a silent
identity/data-integrity fault or **(b)** a legitimate input the system refuses. Round four found
**two** BLOCKINGs in a two-commit diff, so the loop stayed open. Before running round five the exit
rule was written down: **one more round; if it finds no BLOCKING the loop closes, and if it finds one
the fix ships but no further round is dispatched**, because at that point the evidence says the
subsystem needs a design decision rather than another patch. Round five returned **APPROVE**, with 14
claims verified true and **11 of 12 mutations red**.

Stating the rule first is the whole point. "Review until APPROVE" does not terminate, and by round
four the severity curve was not decaying — the temptation was to keep dispatching until the answer
was the desired one, which is how a review becomes a formality.

### The BLOCKING that matters most: the fix that quoted the lesson made the mistake

D-131 named it and this entry's predecessor D-136 quoted it: **a fix that moves a boundary rather
than closing a gap inherits every way the new boundary can fail.** The staging fix for `add_evidence`
staged both documents before renaming either — and left the rename loop bare. `os.replace` is a
reportable failure: `mkstemp` needs the *directory* writable, the rename additionally needs the
existing target *unlinkable*, so an immutable file separates them. The result was the exact state the
fix existed to prevent, reported as `could_not_complete` — "nothing was written" — which is **less**
than the pre-fix code said.

Its second half was worse in a quieter way. The leaked `.tmp-authoring-*` files are not inert: an
undeclared entry inside a draft makes the loader refuse the whole draft *before* it reads anything, so
the residue **masked** the torn state behind a dotfile no diagnostic named — and `inventory` reported
the same shape one directory up while reporting nothing for this one. A quarantine with no drain,
which `CLAUDE.md` forbids in the same change as the quarantine.

### The ruling: the window is named, not closed

**Two documents at different paths cannot be renamed as one operation on POSIX, so no design closes
this.** The alternatives were weighed and rejected:

- **A write-ahead journal** for a filesystem-only subsystem is substantial new machinery, and it moves
  the crash window rather than removing it — a journal replay is itself interruptible.
- **Merging the two documents** so one rename suffices would change the closed 33-document grammar,
  which is a contract, and would put a digest inside the file it describes.
- **Compensating renames on failure** are what §21 already refuses elsewhere, for the reason that a
  killed process cannot run compensation, so an exception and a `SIGKILL` would leave two different
  recovery shapes and the operator would have to know which happened.

So the window stays and is **named**: `PARTIAL_EDIT_APPLIED`, deliberately not a member of
`COULD_NOT_COMPLETE_CODES`, because exit 3 invites a retry that is guaranteed to refuse — the part
that landed is already there. `details.applied` lists what was written. The residue now has a reader
in `inspection._authoring_residue`, which imports the prefix from the writer that produces it rather
than spelling it a second time.

**The docstring's appeal to `rebase-draft`'s two renames is withdrawn.** Those rename *directories*
and stage no temporary files, so neither the half-applied document set nor the residue was covered by
what §21 accepts there. A precedent that does not actually cover the case is worse than none, because
it stops the next reader looking.

### Two counts of "asserted rather than checked", both mine

The commit fixing the typed-code finding justified keeping `from_diagnostics` by naming
`unsupported_schema_version` as the code that could still reach it. **It cannot** —
`authoring._load` refuses an unsupported schema before either write. The override's real beneficiary
is `unsupported_secret_scan_ruleset_version`, which was therefore never assessed. It is assessed now
(exit 1 is right: the recheck *ran* and reported a real finding about a draft that really changed) and
recorded in the code rather than in a commit message nobody greps.

And the test written to pin that same fix asserted `details.cause`, the absence of `error_type`, and
the absence of an absolute path — but never the **code**, which is the one field a consumer branches
on. The arm could report `io_error` with 63 tests green. **A pin that omits the field the fix exists
to set is not a pin.**

### The transferable rule

**The reviewer that finds the most is the one reviewing the previous reviewer's fix.** Four rounds ran
on this slice and every round found something in the round before it — not because the fixes were
careless, but because a fix is written by someone who has just convinced themselves of one failure
mode and is therefore the worst-placed person to enumerate the others. The cost is real and the
alternative is worse: every one of these defects was a silent data-integrity fault reported as
success.

---

## D-138 — A missing bundle root is its own fact, and `inventory` reporting it as clean was the defect

*2026-08-12. Found while enumerating what the twelve commands do with a mistyped `--bundle`, in the
bonus window after the Gate A integration merge. Commit `29233c3`. Review:
`.agent/BUNDLE-NOT-FOUND-REVIEW.md`.*

### Context

A path that is not a bundle got four different answers. `inventory` reported it as a **clean, empty
bundle at exit 0**. `validate`, `conflicts` and `migrate` reported `no_current_revision` — "there is
no CURRENT in this bundle; no revision has been promoted yet" — about a directory that does not
exist. `promote` reported `draft_not_found` and `rebase-draft` `no_current_revision`, each from an
explicit `is_dir()` check that already knew the real reason and borrowed a neighbour's code to say
it.

The `inventory` arm is the one that matters. This program's keystone treats "no flags" as distinct
from cleared, and a clean exit 0 on a nonexistent path is that failure in its purest form: the
operator is told the bundle holds nothing, which is true, because there is no bundle. Nothing in the
report distinguishes it from a freshly initialised one.

### Decision

`IssueCode.BUNDLE_NOT_FOUND`, a state refusal at exit 1 alongside `DRAFT_NOT_FOUND`, raised from
`require_confined_root` — the function every reading surface already enters, whose docstring already
claimed to be written once so that a member or writer added later inherits the check instead of
restating it. A keyword-only `must_exist` carries the one real distinction, between reading a bundle
and creating one; it defaults to refusing, so a reading surface added later inherits the refusal and
a writer that forgets the argument gets the safe answer. `init_draft` is the single opt-out, an
absent root being the normal input to the command whose job is to create it.

`promote` and `rebase-draft` keep their own pre-lock `is_dir()` checks — they must, because
`filelock` would create the directory to hold the lockfile, and that check has to precede it — and
only their codes changed.

### Alternatives rejected

- **A new call site per command.** Restating the rule eleven times is how the confinement check
  would have drifted; the existing shared entry point is the reason a one-line change reaches ten
  commands.
- **Exit 3 / `COULD_NOT_COMPLETE_CODES`.** Rejected for the reason D-137 gives for
  `PARTIAL_EDIT_APPLIED`: exit 3 says nothing happened and the caller may retry, and a retry against
  the same mistyped path is guaranteed to refuse again.
- **Leaving `promote` and `rebase-draft` alone**, since their messages were already accurate prose.
  Rejected because the code is what a consumer branches on, and two commands answering one question
  with two codes is exactly the drift a closed catalog exists to prevent.

### Consequence

Two existing tests asserted the borrowed codes; both keep their real claim, which was never about
the code — that a mistyped path is refused **without being created**. A command run with `--bundle`
omitted, against a default bundle path that has never been initialised, now refuses instead of
reporting an empty bundle.

---

## D-139 — `STATE.md` splits its standing facts out, because a read-first file at twice its stated length is read past

*2026-08-12. The trim `STATE.md` had owed since D-108 set its target, done in the bonus window after the
Gate A merge.*

### Context

`STATE.md` declared "keep it near 170 lines" in its own header and stood at **340**. The overflow was not
padding: two sections — "standing facts a fresh session should not re-derive" and "process lessons this
program paid real time for" — were 168 lines between them, and every line in them was load-bearing. But
they are *reference*, consulted when you are about to touch a subsystem, while the rest of the file is
*standing*, needed on the first screen of every session. Mixing them meant the standing part was 200 lines
deep, and three rows in it were false: T18's fix round was recorded as unreviewed after five rounds had
closed it, the authoring guide as unwritten after it was written and reviewed, and a gate's evidence cited
a superseded sha.

That is the failure mode a read-first file has: it is not that a long file is unpleasant, it is that a
long file stops being corrected, and an uncorrected read-first file is worse than none.

### Decision

`docs/program/STANDING-FACTS.md`, holding both sections verbatim under six headings — gates and process,
Gate A internals, liveness and the ledger, the live store, environment, process lessons — behind a table
saying **when** to read each. `STATE.md` keeps current standing, the phase table, Gate P6's clauses, the
open questions and the live blockers, and points at the new file from its header. 149 lines and 230.

This is D-108's pattern applied a third time: the `DECISIONS`/`METRICS` archive split solved the same
problem the same way, by putting the long tail behind an index rather than deleting it.

### Alternatives rejected

- **Compress in place.** Every candidate line was a fact that had already cost the program time; shortening
  them is how a claim loses the qualifier that made it true.
- **Delete the process lessons.** They are the cheapest thing in the program and the reason several traps
  fired only once.
- **Fold them into `CLAUDE.md`.** That file states rules, not findings, and its own header forbids
  narrating history there.

### Consequence

Nothing is dropped — the moved bullet count went **140 → 174**, the increase being facts this session
added. `CLAUDE.md`'s document table gains a row, since a document nothing points at is a document nobody
reads. The risk taken on is real: a session that reads `STATE.md` and stops will now miss facts that used
to be in front of it, which is why the pointer is in the header rather than at the bottom, and why each
section says what it gates.

---

## D-140 — D-116's conclusion survives, its premise does not: two tests do read the real `docs/` tree

*2026-08-12. Found by checking a claim rather than repeating it, immediately after D-139 moved that claim
into `STANDING-FACTS.md`.*

### Context

D-116 gave docs-only diffs a short gate — `generalization` + `index-check` instead of full `make check` —
and rested it on the measured claim that **no test reads a `docs/` file**, with a stated expiry: "void if a
new test ever reads one". That claim was repeated in `STATE.md` for as long as D-116 existed, was cited in
this session's own reasoning, and is **false**, and was already false when D-116 was written:

- `tests/generalization/test_real_tree.py` asserts `run(REPO_ROOT) == []` — the generalization gate against
  the actual repository, which is how a `$HOME` path in a tracked `.md` file fails.
- `tests/unit/test_program_index.py::test_the_tool_never_relies_on_the_LOCALE_encoding` runs
  `python -m tools.program_index --check` with `cwd` at the repo root and asserts it exits 0 — so it reads
  the real `DECISIONS.md` and `METRICS.md`, and a stale index fails it.

### Decision

Keep the short gate; replace the reason. Each of those two tests asserts **exactly** what one of the two
owed commands asserts — the same tool, the same argument, the same expected exit — so running
`generalization` and `index-check` on a docs-only diff subsumes both rather than skipping them. The
conclusion was right by luck of construction, not by the absence it claimed.

The expiry condition is restated so that it can actually be checked: **the discount breaks the day a test
asserts something about a doc that neither command covers** — a link checker, a line-count cap on
`STATE.md`, a spell check, a test reading a doc as a fixture. That is a question you can answer by
grepping `tests/` for `REPO_ROOT` and `docs/`; "no test reads a doc" is a question whose true answer had
been available the whole time and was never asked.

### Alternatives rejected

- **Revoke the discount and require full `make check` for docs.** Nothing is unguarded, so this would buy
  16 minutes of nothing per docs commit.
- **Leave the premise and note it as approximate.** A premise carrying its own expiry test is load-bearing:
  a future session would have checked the wrong condition and concluded the discount still held for the
  wrong reason.

### Consequence

Two facts in `STANDING-FACTS.md` are corrected. The general lesson is the one this program keeps paying
for: **a claim with a stated expiry condition invites you to check the expiry and never re-check the
claim.** This one had been carried, cited and moved between files without anyone running the two-second
grep that falsifies it.

---

## D-141 — The third site of the blocking-`open()` class is closed, at the layout boundary

*2026-08-12. Bonus window after the Gate A merge. Commit `6edb721`, merged as `ece19cd`.*

### Context

`STATE.md` had carried, as a recorded-but-unchased fact, that a FIFO in place of a bundle **document** made
`validate --draft` and `promote` block in `open()` forever — no timeout, nothing reported, and for `promote`
while holding the bundle lock, so every other writer is refused for as long as nobody notices. Measured
before the fix: `timeout 20` on both commands returned **124** with no output.

Two sites of the same class were already closed — `storage._require_stored_blob` for a blob store entry and
`storage.identical_trees` for a compared tree — each with a docstring explaining that a path proven not to
be a symlink still has to be proven to be *content*. The document path had no such check: the loop in
`layout.discover_source_files` classified each entry as symlink, directory or `COMPLETE`, and reached
"ordinary readable document" **by elimination**.

### Decision

One `lstat`-based `stat.S_ISREG` check in `discover_source_files`, raising `BundleLayoutError`, which
`parse_error_diagnostics` already maps to `IssueCode.UNKNOWN_FILE` — the same code the blob-store case uses,
whose message already frames the honest reason. No new catalog member and no new call site.

The guard belongs at `discover_source_files` and not at each reader because **every** reader downstream of
it opens what it returns: `validation/context.load_documents`, promotion's verbatim copy at
`promotion.py:856`, and `drafts._copy_tree`'s `shutil.copyfile` for `checkout`. None takes a timeout. A
per-command check would have restated the rule three times and missed `checkout`, which is not one of the
two commands the original report named.

### Consequence

After the fix, both commands report `unknown_file` at exit 1 in about a second. Verified twice by different
routes: the implementing agent used promote/checkout/approve over the packaged example, and this session
re-checked it through `init` + `validate --draft` on a different document (`facts/certifications.yaml`),
because a component's self-report is not verification. Mutation RED — deleting the guard makes the new test
fail with `DID NOT RAISE`, and it fails *fast*, since `discover_source_files` never opens the file.

Classification by elimination is the general defect here, and it is worth naming: the loop's last branch
answered "everything else is a document", so every filesystem object nobody had thought of became content.
The remaining exposure is any future code that opens a path the layout did not hand it.

---

## D-142 — D-138 delivered eight of twelve commands, and said twelve. The review that caught it, and what the surviving mutation cost

*2026-08-12. Adversarial review of `29233c3`, fresh context, read-only lens. Report:
`.agent/BUNDLE-NOT-FOUND-REVIEW.md`. Fix: `9cb197a`.*

### What the review found

**REWORK: 0 BLOCKING, 1 MAJOR, 3 MINOR, 7 checks clean.** The MAJOR is that `add-evidence`,
`resolve-conflict`, `approve` (through `authoring._draft`) and `validate --draft` (through the CLI's
`_draft_tree`) enter **no** function that confines the root, so none of them inherited D-138's refusal.
They kept answering `draft_not_found`, whose remedy — "check out a draft" — sends the owner to
`checkout` for a bundle they never created. That is the defect D-138 exists to remove, one round trip
further along.

D-138's error was not the code; it was the **claim**. `require_confined_root`'s docstring said it was
written once so every reading surface inherits the check, and D-138 repeated that sentence as though it
were a property of the system rather than an aspiration of one function. Eight of twelve commands is
what "across the surface" actually meant.

### The lesson this one is worth recording for

The session that wrote D-138 had, an hour earlier, written down: *enumerate the arms from the code's own
catalog, not from the reproduction you were handed.* It then probed eight commands, found them
consistent, and generalised — because the three unprobed commands took mandatory `FILE` arguments and
its probe died at argument parsing before reaching the bundle. **A probe that cannot reach an arm reads
identically to an arm that passes.** The reviewer built the fixture files and reached them.

### The surviving mutation

Of five mutations, one came back **GREEN**: weakening `is_dir()` to `exists()` left the whole suite
passing, and under it `inventory` reports a **regular-file root** as a clean, empty bundle at exit 0 —
D-138's own defect, restored, with 1,954 tests green. Both of D-138's new tests used a *nonexistent*
path, so neither reached the not-a-directory arm that its message and this log both describe.

A second mutation was a **behavioural no-op**, and that is a finding of its own: removing
`BUNDLE_NOT_FOUND` from `STATE_REFUSAL_CODES` changes nothing, because **that set has no production
reader**. All thirteen members are documentation. A set that looks like a mechanism and is not is worth
knowing about before someone relies on it.

### Decision

Extend rather than narrow: state the refusal at the two additional sites, restating the check the way
`promote` and `rebase-draft` already do rather than routing four commands through a function they do not
otherwise enter. The standing fact is corrected to say **three** statement sites and to say why, since
"one shared entry point" is the belief that produced the gap.

Also fixed: the `exists()` arm is pinned over a file root and a symlink-loop root; the test docstring's
miscount is corrected to the measured counts (three commands named a missing revision, none named a
missing draft — that was `promote`, which the test did not run); and the refusal message no longer tells
the operator to check an argument they may never have passed, `--bundle` being optional, while never
naming `init`, which is the drain for exactly this state.

### An unclaimed fix, recorded so it is not re-found

At D-138's parent, a symlink loop at the bundle root escaped `inventory` as `RuntimeError: Symlink loop
from '/private/tmp/…'` — a type `_guarded` does not catch, so it reached the operator as a traceback
**carrying an absolute path**. The new guard precedes `resolve()` and refuses it. On 3.13, where
`resolve()` returns the loop's own path, this also changes the answer from `symlink_refused` to
`bundle_not_found`.

### Process cost

The review lens had **no write tool**, so the instruction to append each finding on confirmation was
unfollowable; it ran 56 minutes with nothing on disk, and D-138 shipped citing a report path that did
not yet exist. **Confirm a read-only reviewer can write before telling it to.** Its findings were
returned in-report and transcribed by the orchestrator.

---

## D-143 — `add-evidence` writes the back-citation, closing Gate A's last open question

*2026-08-12. Mit's ruling on STATE open question 3, asked and answered at session start. Build:
`cc489ac`. The question was explicitly not to be resolved by fiat, and was not.*

### Context

§12 requires record-to-evidence and evidence-to-record links to agree exactly. `add_evidence` wrote
only the evidence side, so a capture supporting a **fact** or a **metric** — the only two kinds
carrying `evidence_ids` — ended at exit 1 with `evidence_link_asymmetry` standing until the owner
hand-edited the record. A correct operation leaving a standing error behind it: the same class as the
BLOCKING T18's fix round closed, and the last item between Gate A and "met".

### The premise the question was framed on was false

The question was posed as "should a single-document write become a multi-document one". It was
**already** multi-document. `add_evidence` writes `EVIDENCE_PATH` *and* `MANIFEST_PATH`
unconditionally (`_manifest_restating_the_evidence_set` recomputes `evidence_set_digest`), plus a blob
for a blob capture, all through `_write_documents` — whose half-applied case is already named
`PARTIAL_EDIT_APPLIED`. `docs/profile-bundle-authoring.md` §10 asserted it "appends to
`evidence/records.yaml` and nothing else", contradicting the same guide's Editing section 300 lines
earlier, which correctly lists `add-evidence` as one of the two commands that touch more than one
document at once. The guide, not the Editing section, was wrong; both are now corrected.

So the ruling's cost is a third document under machinery that already exists and already names the
failure it can produce — not a new risk class.

### Decision

**Write it, default on.** Every fact and metric the captured record names is cited back in the same
operation.

Three things a narrower fix would have missed, each pinned by a test that fails without it:

- **The union of all three relationships.** `_evidence_links_are_symmetric` compares against
  `supports | contradicts | contextualizes`; linking only `supports` leaves the other two arms
  reporting the very asymmetry this closes.
- **Both citing kinds.** Evidence naming a skill or a claim is a legitimate one-way link, and citing
  back into either would invent an error.
- **Any of the twelve fact-bearing documents**, asked by `isinstance(document, FactBearingDocument)`
  rather than by path. That class is public precisely so this does not become a list that goes stale,
  and reaching only the documents a probe happened to touch is how D-142 happened.

A target the draft does not hold is left alone — a broken reference, already reported as one.

**Write order: evidence, then the record documents, then the manifest** — the pointer target before
the pointer, the same rule `resolve_conflict` states for its ruling. A rename failing between the
first two leaves exactly the repairable asymmetry this used to leave *always*; the other order would
leave a fact citing an evidence ID no document holds, which is strictly worse.

### The consequence worth stating

`owner_gates` now derives from the record documents too, so a capture supporting a fact reports a
**`confirm_fact`** gate it did not report before. That is not burden auto-linking invented: the hand
edit it replaces changed the same field of the same fact and owed the same stamp at promotion. What
changed is that the owner is told when they incur it rather than at promotion — which is what `_gates`
exists for.

### Alternatives rejected

- **Keep the two-step flow.** Documented and measured, but leaves a correct operation exiting 1.
- **An opt-in `--link-back` flag.** Unrequested configurability; the default path still exits 1.
- **Refuse until the record already cites the evidence.** Moves the asymmetry window rather than
  closing it: the owner must author a forward reference to an evidence ID that does not exist yet, so
  the intermediate draft is invalid in the other direction.

### One mutation survived, and it is a finding

Five mutations, four caught. **Removing the `prefix_of(target) in ("fact", "metric")` filter changed
nothing — 29 passed.** It cannot: fact-bearing documents hold only `fact.*` IDs and the metrics
document only `metric.*`, so filtering the target set by those prefixes cannot alter any membership
test. It only short-circuits a scan that returns empty anyway. By this program's own rule a check that
cannot fire is deleted, and the guarantee is already tested where it lands (the skill/claim case
rewrites no document). Left in place in `cc489ac` rather than invalidating a gate already running on
that sha.

**Closed.** Deleted in `f06fa67`, after a third confirmation independent of both the mutation and the
reviewer's reading: `FactId` and `MetricId` are `id_pattern("fact")` and `id_pattern("metric")`, so
the prefix is enforced by the model and a fact-bearing document cannot hold anything else. The rule it
expressed stays in the docstring.

---

## D-144 — Grounding reads `supports` alone; citing a source is not being backed by it

*2026-08-12. Found by adversarial review of `cd76bb8`'s parent, fresh context, as a MAJOR beside the
`add-evidence` back-citation. Mit ruled on the remedy. Build: `d39d369`.*

### Context

§12 makes the evidence relationship a closed choice of three and requires record-to-evidence and
evidence-to-record links to agree over **all three**, so `fact.evidence_ids` legitimately holds the
source that *contradicts* the fact and the one that merely *contextualizes* it. It is a citation
list, not a claim of support.

Two checks read it as a claim of support:

- `semantic._effective_facts_meet_their_predicate_evidence_contract` — a predicate's
  `minimum_evidence`;
- `evidence._verification_bases_are_supported_by_their_evidence` — whether a class can carry the
  declared basis.

Neither can tell the relationships apart. Measured on the packaged example: one `add-evidence` whose
record only *contextualizes* `fact.example.name.001` cleared that fact's `evidence_contract_unmet`,
and **no compensating diagnostic** took its place. §12.1 says a contextual source "cannot satisfy a
verification requirement", so the behaviour contradicted the design in writing.

**This was always reachable — by a hand edit satisfying §12's symmetry.** D-143 removed the friction
that made it a deliberate act, which is what surfaced it. The defect predates D-143.

### Decision

Mit's ruling, chosen over "link only `supports`" and over "ship it and record the weakening":
**keep the union for referential symmetry, and make the grounding checks read `supports` alone.**
The alternatives left the conflation in place for hand edits; grounding is the point of the bundle.

`validation.evidence.supporting_evidence` is the single definition both checks call. Two
restatements of "cited *and* supporting" is how they come to disagree about which facts are verified.

### Closing one hole opened another, and that is the part worth remembering

`_verification_bases_...` skipped a fact whose citations do not resolve, as a referential finding.
Narrowing the list to supporting citations would have folded a *second* case into that same silent
skip: a fact that cites only contextualizing evidence has no supporting citations, so it would have
claimed `public_record_verified` and reported **nothing at all** — a worse silent success than the
one being fixed. The resolvable check now runs first and the supporting check second, and each has
its own test. Both were mutation-checked: removing the `supports` filter fails exactly one test per
arm.

### Two fixtures were resting on the conflation

Corrected rather than worked around, because each was asserting something it did not establish:

- The conforming-fact sweep picked example evidence **by class** and cited it from a synthetic fact
  those records never name. That is an asymmetric §12 link, so it was never a conforming fact; it
  passed only because the contract read the citation without the relationship.
- The secondary-summary test now makes its summary *support* the fact, which is what "cites only a
  summary" means under §12. The purely contextual case it used to rely on became its own test.

---

## D-145 — The Gate A subsystem never ran on Windows, and one `write_text` hid it

*2026-08-12. Surfaced by pushing the Gate A range, which is the first time CI executed it on the
Windows matrix. Fixes: `32a109f` (collection), `dbb57ef` (the rest).*

### Context

`origin/main` sat at `88c5857` (T11) for the whole Gate A build, and that commit was **green on all
nine `test` jobs**. Everything from T12 to T19 was developed, reviewed six times, and gated locally on
macOS. The local gate is one interpreter on one OS; CI is three OSes times three Pythons.

The first push exposed two layers, one behind the other.

**Layer one — collection.** Three `@pytest.mark.skipif(os.geteuid() == 0, ...)` decorators evaluate at
import, and `os.geteuid` does not exist on Windows. All three Windows jobs reported
`1 deselected, 2 errors in 14.96s`: **no test ran at all.** That is why the second layer was invisible
for ~180 commits — the platform never got far enough to disagree with anything.

**Layer two — about 130 failures**, in four classes, of which one line caused roughly a hundred:

- `conftest._seal_revision` wrote `CURRENT` and `COMPLETE` with `write_text`, which translates the
  trailing `\n` to `\r\n` on Windows. Both are compared **byte for byte** against
  `current_pointer_bytes`, so every fixture-promoted bundle carried a pointer no reader would accept
  and `current_pointer_mismatch` cascaded through storage, drafts, inspection, rebase, digest
  validation, schema migration and validation-run. **Production was never affected** — promotion
  writes through `open("wb")`, and the reader uses `read_bytes()`. The defect was entirely in the
  fixture, which is the only reason this is a test fix rather than a portability bug in the product.
- `signal.SIGKILL`, `os.mkfifo`, and mode-bit denial: POSIX-only mechanisms Windows cannot express.
  Skipped, not weakened — a crash-consistency test that stopped killing a process would pass while
  exercising nothing.
- One was introduced by this session: a `_tree` helper keyed on `str(relative_path)` yields
  `drafts\baseline\manifest.yaml` there. Keyed on `as_posix()` now.

### Decision

Fix the fixture and guard the POSIX-only tests; change nothing in production, because nothing in
production was wrong. **Do not claim Windows is green from here** — the run that produced this list
was cancelled at 72%, several failures were masked by the pointer cascade, and this machine cannot
execute the matrix. CI is the only thing that can close it.

### What this says about the local gate

`make check` is the only gate for *correctness*, and it remains blind to two thirds of the support
matrix by construction. This is a second instance of the same shape as D-117's `gitleaks`/`perf`
finding, and worse: those two can be run by hand here, and Windows cannot. **A long-unpushed range
should expect its first CI run to be a discovery, not a confirmation.**

### Measured outcome of the first fix round

A Windows job then ran to completion for the first time: **5,881 passed, 47 skipped, 2 failed, in
1:05:37.** So the suite is genuinely slow there — roughly four times the 16m23s local run — and was
never hanging. From ~130 failures to two.

Both survivors were the same two classes again, which is the useful part:

- `test_a_retained_temporary_does_not_block_a_later_promotion` wrote a COMPLETE marker with
  `write_text`. Promotion compares the retained directory against the staged one **byte for byte**, so
  the `\r\n` made them differ and the later promotion refused with `promotion_target_conflict`. The
  fixture fix had closed one instance of this; the class had eighteen. All eighteen marker and pointer
  writes in the suite are now `write_bytes` (`f8d89e6`) — the transform is identical on POSIX, and the
  sites that were *passing* are the reason for doing it, because a negative test expecting a byte
  mismatch was getting one from CRLF rather than from the defect it was written for.
- `test_checkout_that_cannot_read_a_blob_installs_no_draft` chmods a blob to `0o000`, which Windows
  still reads. Skipped on non-POSIX, like the other mode-bit tests.

**Fix the class, not the instance.** Both rounds here found one failing site of a pattern that had
many, and in both the passing sites were the dangerous ones.

---

## D-146 — LLM lane-death is one typed error, classified at the raise site, latched per invocation — scoped to the two lanes that call out

*2026-08-12. P3 slice 5, scoped to the two lanes that construct an LLM client. Commits `566050a`,
`72924aa`, `58e61cf`, `8bb444a`, `39bd307`, `4d822dc`, `a7b504e`, `185a66b`, `ced1b90` on
`p3-slice5-llm-lane-death`, merged at `ba13dea`. Reviewed each round; see the design's own §10 for
the record.*

### Context

`eligibility/extract_llm.py` caught **every** exception from `client.complete()` and returned `None`;
its caller, `cli/eligibility_cmd.py`, ignored the return value, incremented one counter
unconditionally, and printed `"extracted N postings"` at exit 0. With a dead credential and a cold
cache over ≥50 open postings this meant up to `max_calls_per_run` doomed HTTP calls, zero eligibility
rows written, a report claiming success, and exit 0 — the "no flags ≠ cleared" silent-success class
the program has already paid for three times (D-138, D-141, D-142). `tailor/rewrite/lane.py` has the
same shape at lower volume: two bare `except Exception` boundaries recorded the undifferentiated
`drop_reason="error"` on a dead credential exactly as they would on an ordinary transient fault.

### The design's stated justification was falsified during implementation

The design spec (§5.1) justified raise-site classification with: "Anthropic returns HTTP 403 for both
`billing_error` and `permission_error`, which mean different things... so any classifier keyed on the
status code conflates them." **This is false.** Provider-error-body research done during this slice
(`.superpowers/sdd/2026-08-12-p3-slice5-llm-lane-death/provider-error-bodies.md`) reconfirmed, by
quoting Anthropic's current official error-codes page in full, that `billing_error` is paired with
**402** and `permission_error` with **403** — each exactly once, on two different statuses, never both
on 403. No source found anywhere pairs `billing_error` with 403. The code originally shipped with the
false pairing (`billing_error`/403) and was corrected in-slice (`a7b504e`, before `185a66b`); the
mapping now live in `llm/anthropic.py` is `billing_error`/402 → `CREDIT_EXHAUSTED`,
`authentication_error`/401 → `CREDENTIAL_INVALID`, `permission_error`/403 → `MODEL_FORBIDDEN`.

**The true justification for reading the error body instead of the status** does not depend on the
403 double-meaning at all: `error.type` is the provider's own typed signal, carried in a contract
Anthropic documents and versions, whereas the HTTP status is a coarser channel that an intermediary
(a gateway, a corporate proxy, a load balancer) can rewrite without touching the JSON body underneath
it. A classifier keyed on status alone inherits whatever the network path between boardwatch and the
provider does to that status; a classifier keyed on the documented body field does not. This is
recorded here because a quietly corrected document would leave the false claim as the only rationale
anyone re-reads; the correction is the more useful fact to carry forward, and the spec and plan
themselves are left as authored — this entry is where the true position lives.

### Decision

**One error class, not three.** A dead quota, a revoked key, and a key lacking model access all fail
every remaining call identically; they differ only in why. `LaneDeathReason` is a closed `StrEnum`
(`CREDIT_EXHAUSTED`, `CREDENTIAL_INVALID`, `MODEL_FORBIDDEN`); `LLMLaneDeadError(LLMError)` carries
one in a typed field.

**Classification happens at the raise site, from the response body's `error.type` — never from the
HTTP status alone and never by string-matching a message downstream** (CLAUDE.md), because the body
is the provider's own typed signal and the status is a channel an intermediary can rewrite (see
above). Anthropic maps `billing_error`/402 → `CREDIT_EXHAUSTED`, `authentication_error`/401 →
`CREDENTIAL_INVALID`, `permission_error`/403 → `MODEL_FORBIDDEN`, checked **before** the
retryable-status branch (locked by a direct test after a surviving mutant showed the ordering was
unverified). The openai-compat catalog is deliberately **narrower**, admitting only unambiguous
signals: HTTP 401 → `CREDENTIAL_INVALID`, HTTP 402 → `CREDIT_EXHAUSTED`, and body `code`/`type` ==
`insufficient_quota` **or** `credit_balance_exhausted` at **any** status → `CREDIT_EXHAUSTED` (checked
ahead of the retryable-status branch too, because OpenAI signals an exhausted balance as 429 with
that code — left to the status check alone, the commonest death mode would be classified transient,
retried, and swallowed at 4× the call volume). `credit_balance_exhausted` was added alongside
`insufficient_quota`, not in place of it: OpenAI's docs now lead with the newer code, but real
captured error bodies people quote still carry `insufficient_quota` verbatim, so both tokens are
live and the change is verified additive. **Bare HTTP 403 is deliberately unmapped for
openai-compat** — on an arbitrary proxy it is not proof of credential death, and mis-latching would
suppress a lane that is merely misrouted. An unrecognized `error.type` stays a plain `LLMError`:
out-of-catalog is a failure, never a new bucket (CLAUDE.md).

**The classifier is total, never the thing that raises.** Every malformed shape — invalid JSON, empty
body, non-object root, `error` as a string, missing `type`, non-string `type` — degrades to `None`
(plain `LLMError`) rather than raising, because a `TypeError` escaping the classifier would land in
`extract_llm.py`'s blanket `except` and reproduce the very silent success this removes.

**A wrapper, not threaded state.** `RunScopedClient` (`llm/run_client.py`) implements `ModelClient`
and wraps a real adapter: once a death reason is recorded, every later `complete()` raises without
touching the network. It is installed by `build_client` (`llm/factory.py`), the single construction
point both consumers already call once per invocation, so the wrapper's lifetime is exactly one
invocation and **no call site changes**. `build_client`'s annotation stays `-> ModelClient | None`.

**The two lanes reach the reason by different routes, and that is not an inconsistency.**
`cli/tailor_cmd.py` narrows the client with `isinstance(client, RunScopedClient)` to read
`dead_reason` off the wrapper, because Tier B's containment boundaries swallow the exception into a
`drop_reason="lane_dead"` row — by the time the CLI is printing, no exception is left to read.
`cli/eligibility_cmd.py` never imports `RunScopedClient` at all: nothing in its loop swallows the
error, so it catches `LLMLaneDeadError` directly and reads `exc.reason`. Reading the typed attribute
off the propagated exception is the better route where it is available; the wrapper property exists
for the lane where the exception does not survive.

**Consumers keep two counters, not one.** `cli/eligibility_cmd.py`'s `attempted` increments once per
posting sent to extraction and is what the loop caps at `max_calls_per_run` — it must keep advancing
even when every call fails unclassified, or the cap silently disappears. `extracted` increments only
on a landed evaluation and is what the exit condition reads. `tailor/rewrite/lane.py`'s two
containment boundaries record `drop_reason="lane_dead"` instead of `"error"`.

**Exit 1 only under death observed ∧ zero landed** — zero `extracted` in the eligibility lane, zero
rewrites kept in the tailor lane — never zero-landed alone: `lane.py` has thirteen `kept=False` paths
against one `kept=True`, so a healthy credential legitimately keeps zero rewrites whenever every
candidate is not-entailed, echoed `unchanged`, or filtered, and an eligibility run whose calls all
fail unclassified (network, malformed body) must also keep exiting 0.

**Deliberately not built:** a run-scoped call ceiling — the eligibility lane already has a working
per-invocation cap, and `boardwatch tailor` handles one posting so per-lead and per-run coincide
there; only the misleading `max_calls_per_run` **name** is fixed, by docstring. And wiring Tier B into
`pipeline/runner.py` — an owner decision, recorded as a gap (design §8), not fixed by fiat.

### Accepted limitation: the Azure false-latch

Azure OpenAI returns HTTP 429 with `error.type == error.code == "insufficient_quota"` for a
**recoverable** per-deployment TPM/RPM throttle — a rate limit, not billing exhaustion — and this body
is structurally indistinguishable from genuine OpenAI credit exhaustion under the mapping above.
Provider research (`provider-error-bodies.md` §3) looked for a discriminator and found none
established: no `Retry-After` header and no `innererror` field is reported anywhere in the sourced
material as reliably present on the throttle case, and Microsoft's own explanation states plainly that
Azure quota is scoped separately from Azure credit balance, so a live $5,000 credit balance does not
prevent this 429. **The mapping was deliberately kept as-is.** Removing `insufficient_quota` from the
openai-compat catalog to avoid this false-latch would restore the worse defect this slice exists to
fix — OpenAI's own commonest death mode (credit exhaustion signaled the same way) would go back to
being retried four times per call and then silently swallowed. The blast radius of keeping it is
bounded: this is the advisory Tier-B/eligibility-LLM lane only, Tier A (the deterministic engine) is
untouched, and the effect is confined to one invocation — a transient Azure throttle latches the lane
dead for the rest of that one run and can make it exit 1 reporting the credential unusable, but the
next invocation starts clean. Recorded as an accepted, owner-gated limitation with its evidence, not
as a resolved question — if Azure's contract ever documents a discriminator, add it then.

### Gap: `lane_dead` is not in the funnel's closed drop-reason catalog

`reports/run_funnel.py`'s `FabricationCounters` catalog (five mirror sites: the `:295`-area docstring,
the dataclass fields, the `elif reason == ...` fold, the JSON serialization, and the markdown render)
does not have a `lane_dead` branch, so a `drop_reason="lane_dead"` row would fall into `other` and
trigger the literal `**FAILURE — N rewrite rows carried a drop_reason the closed catalog does not
name**` line — this project's rule that an out-of-catalog value is a failure, never a new bucket,
working exactly as designed against an omission rather than a real defect.

**It is unreachable today, independently verified**, not merely assumed: `pipeline/runner.py`
(`:522`-`:529`) calls `run_tailor` with no `client`, `cache`, or `tb_override` argument, so
`reports/tailor.py`'s `tb = TierBResult(accepted=[], rows=[], calls_made=0)` sentinel is never
replaced — `llm_rows` stays `None` and the `if result.rewrites is not None` guard (`runner.py:590`)
never fires, so the pipeline's funnel never sees a `lane_dead` row. The only other caller that can
produce rewrites is the agent lane (`boardwatch tailor rewrite`, no API client, no funnel write). So
today, no code path reaches the gap.

**Whoever wires Tier B into `pipeline/runner.py` must add the `lane_dead` catalog row and its test in
the same change** — this is not deferred as a nice-to-have, it is a precondition of that wiring, and
is recorded here alongside the wiring gap itself (design §8) so the two are not discovered separately.

### Deferred, evidence-backed follow-up

A status-fallback table for Anthropic — 401/402/403 each mapping to exactly one `error.type` per the
corrected documentation above — would close the known gap that a non-JSON or malformed error body
(the classifier's total-not-raising fallback path) never latches even when the status alone would be
sufficient to know a 401 is `CREDENTIAL_INVALID`. Deliberately not built in this slice: it adds a
second classification path with its own correctness burden for a case (malformed body) that provider
research did not surface as commonly observed. Recorded here so the evidence is attached when someone
picks it up.

### Alternatives rejected

- **Three separate exception types**, one per reason. Rejected: all three fail every remaining call
  identically and differ only in why, so one class carrying a typed `reason` field says the same
  thing with less machinery for every catch site to handle.
- **Threading run-scoped state through `run_tailor`** (a parameter or context object passed down the
  call graph). Rejected: `ModelClient` is already a `Protocol`, so a wrapper is a drop-in requiring no
  signature changes anywhere; threaded state would touch every function between the CLI and the
  network call for no guarantee the wrapper doesn't already give.
- **Provider-specific classification tables with provider identity plumbed into the adapter.**
  Rejected in this narrower form: `openai_compat.py` serves an arbitrary endpoint by design
  (`settings.provider` free-form, `base_url` arbitrary), so a per-provider table needs provider
  identity threaded into an adapter that currently carries none, to catalogue a signal (bare 403)
  whose own justification argues against cataloguing it — an arbitrary proxy's 403 proves nothing,
  which argues for leaving it unmapped rather than tabulating it. If a future provider's documented
  contract justifies more, add it then with the evidence.

---

## D-147 — Slice 5 merges as-is: four known residuals, recorded rather than fixed

*2026-08-12. P3 slice 5 (`p3-slice5-llm-lane-death`), decided at merge time. Owner reviewed the whole
branch and chose to ship it with these four findings open rather than hold for a sixth round. None was
in scope for D-146's fix wave, which named only `eligibility extract`.*

### Context

The branch was green (`make check` exit 0, 5978 passed), gitleaks clean, every task individually
reviewed, and the whole-branch review's verdict was "I would merge this branch." Four residuals
surfaced along the way and were, deliberately, not folded into the fix wave. None is behavioural
except R1's ledger row, and R1 is invisible to `boardwatch run` because `pipeline/runner.py` never
constructs an LLM client (D-146, design §8) — so the defect exists in the code today but nothing
currently reachable trips it.

### Decision: merge now, fix these later — and here is each one

**R1 — the load-bearing one: `tailor run --tier-b` has the same durable-ledger defect D-146 just
fixed for `eligibility extract`.** `reports/tailor.py:727-728` reads:

```
727:        if owns_run:
728:            finish_run(engine, run_id)
```

`finish_run`'s `status` parameter (`store/queries.py:111-113`) defaults to `RUN_OK`
(`store/queries.py:48`), and `store/queries.py:49` already defines `RUN_FAILED` — but this call site
never passes it. The exit-1 decision happens later and in a different module entirely:
`cli/tailor_cmd.py:265-266`'s `if lane_death_fatal: raise typer.Exit(code=1)` runs after
`run_tailor` (and its `finish_run` call) has already returned. So a tailor invocation that exits 1 on
a dead credential still leaves a durable `runs` row reading `ok` — the exact "the ephemeral report is
honest and the durable one still claims success" shape D-146 removed from the eligibility lane, now
sitting one command over. This is an internal inconsistency in a slice whose stated purpose is to
stop reporting success falsely, and the fix is the same one-branch change D-146 describes: thread
`lane_death_fatal` (or an equivalent signal) down to the `finish_run` call and pass
`status=RUN_FAILED` when it is set. Out of scope here only because the fix wave named
`eligibility extract` and not `tailor run`.

**R2 — `README.md:503-504` over-claims.** It reads "The Tier A résumé is still produced and on disk
either way, and so is the Tier B artifact." False on two real paths through `reports/tailor.py`: a
`LayoutViolation` (`:620`) leaves `llm_uri` `None` (the `except` branch at `:620-628` never reaches
the `else` that sets it at `:629-630`), and `reports/tailor.py:679`'s `if llm_uri is not None:` gates
the only `resume_tailored_llm` insert — so no Tier B row is written at all. Separately, a compiled but
non-shippable Tier-B render (`:635-637`) does write the row but leaves `llm_pdf_path` `None`, so no
`tier B pdf:` line ever prints for it. The claim is true on the realistic lane-death path — every
bullet falls back to Tier A text, so layout validation passes and the row is written — which is why
the test suite sees the line and nothing caught this. The fix is to trim the clause, not to change
behaviour.

**R3 — `reports/run_funnel.py:61-63`'s `ARTIFACT_VERSION` comment under-lists, and mis-cites.** The
comment enumerates the additive keys that justified holding the version at 4 and names only D-113's
`liveness.gone_after_redirect`; `fabrication.lane_dead` (this slice) is a second instance and belongs
in the same list. Separately, the fix-wave report that discussed holding at 4 cited both D-031 and
D-113 as precedent — **D-031 does not support it**: D-031 declines a version bump because
`boardwatch verify` "consumes the artifact, it does not extend it," which is precedent for a
*non-extending* change, not for adding a key. D-113 is the real precedent, and is the same shape as
`lane_dead`. Holding at 4 is independently correct anyway: no consumer reads the fabrication block
strictly — `cli/verify_cmd.py:114-125` pulls four named keys out of the frozen JSON by name and
tolerates whatever else is present, and there is no schema, no golden fixture, and no full-dict
equality anywhere on `fabrication`.

**R4 — the derived catalog test hard-codes its module list.** `tests/unit/test_run_funnel.py`
AST-parses the emitters for `drop_reason=` literals so a new one without a funnel branch fails the
test, but line 1003's `for module in (lane, verb_diversity):` is a hard-coded pair. Complete today —
those are the only two producers — but the hard-coding has moved up one level rather than away: a
third emitter module would escape a test whose name promises coverage of every drop reason. The
better end state is a shared frozen `DropReason` catalog constant that both the lane modules and the
funnel read from, so there is nothing left to enumerate by hand; deferred because it rewrites all
thirteen existing call sites and was not worth doing inside this slice's scope.

### Alternatives rejected

- **Fold R1 into this slice and fix it now.** Rejected by the owner: the fix wave's stated scope was
  `eligibility extract`, and widening it during merge review re-opens a branch already gated and
  reviewed six times, trading a bounded, documented gap for another review round.
- **Leave all four undocumented, trusting `.superpowers/sdd/...` notes to carry them.** Rejected: that
  ledger is gitignored working material and is being deleted; anything not moved into `DECISIONS.md`
  before then does not survive the session boundary.
- **Fix R2–R4 now since they are small.** Rejected: "docs only, change no behaviour" was the stated
  constraint for closing this branch out; R2 touches `README.md`, R3 and R4 touch `src/`/`tests/`, and
  mixing a doc-recording commit with source edits reopens exactly the gate this session was scoped to
  avoid.

---

## D-148 — D-147's R1 closed: one flag drives the tailor lane's ledger row and its exit code

*2026-08-12. Closes D-147 R1, R2 and R3. R4 is deliberately still open — see below.*

### Context

D-146 removed a specific defect from `boardwatch eligibility extract`: the exit-1 decision and the
durable `runs` row were computed in two places, so a dead-credential run exited 1 while its own ledger
row said `ok`. D-147 recorded that the sibling lane still had it. `reports/tailor.py` closed the run it
owns with `finish_run(engine, run_id)` — `status` defaulting to `RUN_OK` — and the exit decision was
made later, in a different module, by `cli/tailor_cmd.py` recomputing the same predicate off
`result.rewrites`. Two computations of one fact, in two modules, with a database write between them.

`boardwatch run` never reached it (`pipeline/runner.py` constructs no LLM client, and passes its own
`run_id`, so `owns_run` is False there), which is why nothing observable tripped it. That does not make
it hypothetical: `tailor run <id> --tier-b` is a shipped command and owns its run on every invocation.

### Decision

**The flag is computed once, in `run_tailor`, above the ledger write, and the CLI reads it back off
`TailorResult` rather than recomputing it.** `lane_death_fatal` and `lane_death_reason` are now fields
on `TailorResult`. `finish_run` gets `status=RUN_FAILED` and an `errors` entry naming the typed reason
when the flag is set. `cli/tailor_cmd.py` no longer derives the predicate at all — it reads
`result.lane_death_fatal` for the exit and `result.lane_death_reason` for the message it prints. The
two cannot disagree, because there is only one of them. This is D-146's shape, applied verbatim.

Three arms, and all three are what D-146 chose deliberately:

| Arm | Ledger | Exit |
|---|---|---|
| lane death observed **and** zero rewrites kept | `failed` + the typed reason in `errors_json` | 1 |
| lane death observed, at least one rewrite kept | `ok` | 0 |
| unclassified provider failure (`drop_reason="error"`), zero kept | `ok` | 0 |

The third is the one most likely to be "fixed" into a regression, and it now has a test of its own
(`test_unclassified_provider_failure_keeps_the_run_ok`). A flaky provider is not a dead credential;
making it a failed run is a change D-146 declined and this does not revisit.

**The reason is read off the run-scoped client, never out of `drop_reason`.** `drop_reason` is a
free-form string that proves death *occurred* and cannot say *which* reason; putting the typed reason
into it would classify behaviour by string content. The `isinstance(client, RunScopedClient)` guard is
about the TYPE — only the wrapper carries `dead_reason` — not about the lane. The agent lane cannot
reach the branch at all: `agent_lane.py`'s `propose`/`judge` are dict lookups over the agent's JSON and
cannot raise `LLMLaneDeadError`, so no `tb_override` row is ever `lane_dead`. Checked in the code, not
assumed, because a reachable-looking `else None` invites someone to "handle" it later.

**R2** trims `README.md`'s "and so is the Tier B artifact" — false on a `LayoutViolation`, where
`llm_uri` stays `None` and no `resume_tailored_llm` row is written at all. Trimmed, not explained: the
paragraph is about the exit code, and the Tier A guarantee is the part that matters there.

**R3** extends `reports/run_funnel.py`'s `ARTIFACT_VERSION` comment to name `fabrication.lane_dead`
alongside D-113's `liveness.gone_after_redirect`, and **retracts the D-031 citation**: D-031 declines a
bump for a change that does not extend the artifact, which is not this. D-113 is the precedent. The
comment now also records *why* holding at 4 is safe rather than merely asserting it — no consumer reads
these blocks strictly.

### Verification

`make check` green on the result. The three arms were mutation-tested, each against the assertion that
is supposed to catch it:

| Mutation | Caught by |
|---|---|
| `status=RUN_OK` unconditionally (the pre-fix behaviour) | the `RUN_FAILED` assertion — reproduces the defect exactly: `'ok' == 'failed'` on an exit-1 run |
| `lane_death_fatal = True` (drop the zero-kept conjunct) | the partial-success **exit code** assertion, which already existed |
| `status=RUN_FAILED if lane_death_reason is not None` (ledger disagrees with exit, exit stays right) | the partial-success **ledger** assertion, and nothing else |

The third mutation is the one worth keeping: it is the disagreement class this decision exists to
close, it leaves every exit code correct, and only the new assertion sees it. The second shows the
pre-existing exit assertion masks its own arm — a ledger assertion added without it would have looked
redundant.

### Alternatives rejected

- **Thread `lane_death_fatal` into `run_tailor` as a parameter from the CLI.** Backwards: the CLI cannot
  know it before `run_tailor` returns, and `run_tailor` writes the row.
- **Leave the CLI's own computation in place and add the ledger write beside it.** That is two
  computations of one predicate again, one module apart — the defect, with a test.
- **Read the typed reason out of `drop_reason`.** Classifying behaviour by string content; forbidden.
- **Fix R4 in the same change.** R4's real fix is a shared frozen `DropReason` catalog that
  `tailor/rewrite/lane.py` and `reports/run_funnel.py` both read, which rewrites ~13 call sites and
  removes the hand-maintained enumeration rather than moving it. That is a design change and owes its
  own decision and its own review; folding it into a ledger fix would bury it. **R4 stays open.**

---

## D-149 — The `STATE.md` trim is BLOCKED: three Gate A records disagree with the code or with each other

*2026-08-12. Found while verifying, not while trimming. Records the findings and leaves two of them
for the track that owns them — it does not resolve them.*

### Context

`STATE.md` is 200 lines against a stated target near 170. A docs reviewer named the Gate A narration as
the trim candidates on the premise that all of it is **already held in D-137…D-145**. Before deleting
anything, each candidate block was checked against the entry that supposedly holds it. **The premise is
false in three places.** Deleting on it would have destroyed the only true record of two facts and made
a third contradiction harder to see.

### The three findings, each confirmed by reading the code, not a summary

**1. D-143's stated write order contradicts the shipped code, and `STATE.md` is the only prose that is
right.** `DECISIONS.md:4197` says "**Write order: evidence, then the record documents, then the
manifest** — the pointer target before the pointer." The code writes the manifest **second**:
`authoring.py:251` is `_write_documents(tree, {EVIDENCE_PATH: appended, MANIFEST_PATH: restated,
**citing_back})`, and `authoring.py:236` says so in as many words — "The manifest goes SECOND rather
than last, which is the part that is easy to get wrong." The review that changed it is recorded in
METRICS only as *manifest-last was wrong*, never as what replaced it. So the decision log's only
statement on write order is the falsified one, and `STATE.md:115-116` ("The manifest now goes second")
is the only place the truth is written down. **D-143 is append-only and is not edited**; the correction
owes its own entry.

**2. D-145 forbids the claim that D-145 is cited for.** `STATE.md` says CI is green on all twelve jobs
"— measured, and it is the first time this range has ever passed there (D-145)." D-145 says the
opposite: "**Do not claim Windows is green from here** — the run that produced this list was cancelled
at 72%, several failures were masked by the pointer cascade, and this machine cannot execute the
matrix. CI is the only thing that can close it." D-145's own measured outcome stops at 2 failures. The
green is real and is recorded in `METRICS.md` against `8475319`; what is wrong is the citation, and
trimming the block would leave METRICS as the sole record while D-145 still prohibits the claim.
**Which is right is not in doubt — CI closed it, exactly as D-145 required.** The log needs to say so.

**3. `cited_back` is shipped, user-visible, and `CHANGELOG.md` never mentions it.** `grep -rn cited_back
docs/ CHANGELOG.md` returns `docs/profile-bundle-authoring.md:631` (added by the same commit,
`3cd5e87`) and `STATE.md:130` — zero hits in `CHANGELOG.md`. Outside the authoring doc, `STATE.md` is the
only prose record. The behaviour is real (`authoring.py:188,262`, `cli/profile_bundle_cmd.py:808,815-816`,
four tests, commit `3cd5e87`), and `CHANGELOG.md`'s `[Unreleased]` bundle entry enumerates the twelve
commands and the `--json` envelope without mentioning it. CHANGELOG is authoritative for what shipped, so
this is a gap in the authoritative file, not only a trim hazard. *(Corrected before merge: this finding
originally claimed `cited_back` was "recorded nowhere but `STATE.md`" — the grep behind that was scoped
to miss `profile-bundle-authoring.md`'s own pre-existing hit.)*

### Decision

**The trim does not happen in this session.** Blocks A (the four-gate table) and B (the Windows
narration) are individually safe — every number in A is verbatim in `METRICS.md`, and B is held there
and in D-145 — but B must not go while finding 2 stands, because removing it hides the contradiction
instead of resolving it. Trimming A alone recovers nine lines of twenty-nine and leaves the file over
target anyway, so it buys nothing worth a Gate A edit inside a P3 session.

**What the trim owes first**, and none of it is a cleanup:

1. A correction entry for D-143's write order.
2. A correction entry for D-145's Windows prohibition, citing the CI run that closed it.
3. A CHANGELOG bullet for `cited_back`.
4. Carrying **"Treat the closed review loop as evidence about the slices reviewed, not about the
   subsystem being defect-free"** into `STANDING-FACTS.md` §"Gate A internals". It is the standing
   qualification on the "Gate A MET / review loop CLOSED" verdict and it has no other home —
   `DECISIONS.md:2805` carries the same sentence scoped to T12 alone, which does not cover the
   subsystem.

### Fixed here, because a read-first file may not carry a false claim

`STATE.md` said the twelve-document catalog "is now read off `FactBearingDocument.__subclasses__()` at
run time." Production does not: it asks `isinstance(document, FactBearingDocument)`
(`authoring.py:628`), which is what D-143 already records. `__subclasses__()` appears only in
`tests/profile_bundle/test_profile_bundle_authoring.py:587,593`. The bullet's point — that the catalog
is no longer a hand-maintained list — survives; the mechanism named was the test's. Corrected in place,
per the session ritual's "if STATE and the repo disagree, the repo wins."

### Alternatives rejected

- **Trim on the reviewer's list as given.** It would have deleted the only correct statement of the
  write order and the only record of `cited_back`, in service of a line count.
- **Fix D-143 and D-145 by editing them.** Both logs are append-only; a decision that turned out wrong
  is corrected by a later entry that cites it, never by rewriting history (D-108's split rule).
- **Resolve findings 1 and 2 here.** They are Gate A track, they are corrections to a *closed* review
  loop's records, and each wants the context of the subsystem it describes. Recording them costs a
  session boundary; guessing at them costs the log's credibility.
- **Say nothing and leave `STATE.md` long.** The overrun is the visible symptom; the reason it cannot
  be trimmed safely is the thing worth knowing, and it does not survive a context reset unwritten.

---

## D-150 — The suite runs across worker processes; `-n auto` lives at the call sites, not in `addopts`

*2026-08-13. Prompted by Mit asking why every session spends 17 minutes in the gate, several times over,
on a machine that is barely working.*

### Context

`make check` took 16–18 minutes and this program runs it repeatedly per session, making it the single
largest wall-clock cost in the workflow. The assumption had been that this is simply what ~6,000 tests
cost. **It was not.** Timed from the gate log's own phase ordering, on an M4 Mac mini (`Mac16,10`,
**10 cores** — 4 performance + 6 efficiency — 16 GB):

| Phase | Cost |
|---|---|
| `generalization`, `index-check`, `ruff`, `mypy --strict` (249 files, warm cache) | **~2 s combined** |
| `pytest` | **973 s** |

`pytest` was **~99% of the gate** and strictly serial: `addopts` carried no `-n`, **`pytest-xdist` was
not installed at all**, `MAKEFLAGS` was empty, and the loaded plugins were only `cov`, `respx`, `anyio`.
A `ps` against a live gate showed one pytest process at 98.5% CPU — one core of ten. **Optimising the
other four phases was worth at most two seconds; the whole opportunity was pytest.**

### Decision

`pytest-xdist` is a dev dependency and **`-n auto` is passed at the invocation sites**, not in
`addopts`: `Makefile`'s `test:` target and `.github/workflows/ci.yml`'s test job. `make check` goes
**16m13s → ~4m20s**.

**Not in `addopts`**, though that is the only single edit reaching both local and CI (CI's test job runs
`uv run pytest` directly, not `make check`): the `perf` job runs `uv run pytest tests/perf -m perf
--no-cov -s` against the same config, and **it measures wall-clock timings** — distributing performance
tests across workers would corrupt the numbers that job exists to produce. Keeping it at the call sites
also leaves ad-hoc narrow runs serial and readable.

**A third path inherits it and is left that way deliberately:** `release.yml:31` runs `make check`, so
tag-driven publishing now gates in parallel. Consistent with `make check` being the gate; the `perf`
job stays the only pytest invocation protected from workers.

### The evidence, because a fast gate that lies is worse than a slow one

`make check` is this repo's only gate for correctness, so **an intermittently flaky gate is strictly
worse than a slow reliable one.** One green run does not establish that.

| Run | Result |
|---|---|
| serial baseline @ `5c28e8c` | exit 0 · 5,979 passed · 1 deselected · **95.71%** · 973s |
| `-n 8` | exit 0 · 5,979 passed · **95.71%** · 255s |
| `-n auto` (10 workers) | exit 0 · 5,979 passed · **95.71%** · 225s |
| `-n auto` repeat | exit 0 · 5,979 passed · **95.71%** · 252s |
| `-n auto` + `COVERAGE_CORE=sysmon` (fell back — a fourth sample) | exit 0 · 5,979 passed · **95.71%** · 219s |
| full `make check`, change wired in | exit 0 · 5,979 passed · **95.71%** · 254s |
| full `make check`, after the politeness fix below | exit 0 · 5,979 passed · **95.71%** · 279s |

**Every run exactly 5,979 and 95.71%** — not "about the same". The pass count matching serial exactly
rules out silently skipped tests; coverage matching to two decimals indicates the workers' data
combines rather than one worker's being reported. An independent check confirmed the combination is
genuine rather than coincidental, and partial combination is not a silent-green risk in any case:
dropped worker data lowers the number into `--cov-fail-under=85`, which fails loudly.

xdist's default `--dist load` distributes tests dynamically, so order differs run to run — which is why
repeats are the right test. This suite has no `pytest-randomly`, so **order-dependence had never been
exercised: hidden rather than absent.** Six varying orders finding nothing is real evidence, not proof.
The fallback if a flake ever appears is `--dist loadfile`, keeping a module's tests on one worker.

### What the review found, and the one thing it changed

An independent review of the change confirmed no fixed-path writes (every store/config/bundle path
routes through `tmp_path`/`tmp_path_factory`, and xdist gives each worker its own basetemp), no
`os.environ` mutation outside function-scoped `monkeypatch`, no port binding, and that the two
repo-tree readers only read. It found **one assertion whose margin was smaller than the scheduling
noise parallelism introduces**: `tests/unit/test_politeness.py`'s host-overlap test asserted
`elapsed < 0.7` against a 0.4 s floor and a 0.8 s serialized time — biased toward the serialized end,
the smallest margin of any wall-clock assertion left in the parallel lane.

**Fixed by sizing, not by loosening**: the sleep scales to 1.0 s and the threshold sits at the
*midpoint* of the two outcomes (1.5 s), doubling headroom on both sides for 0.6 s of runtime. Mutating
the per-host lock into a global one still fails it at 2.009 s, so it has not become vacuous.

**Recorded honestly: the predicted flake was never reproduced.** Thirty runs of that test against a
concurrent full `-n auto` suite spanned **1.0022–1.0128 s** — about 11 ms of spread, which the *old*
threshold would also have survived. The margin is insurance for the 3–4 core CI runners this 10-core
machine cannot imitate; it is not a fix for an observed failure, and should not be cited as one.

### Alternatives rejected

- **`COVERAGE_CORE=sysmon`.** Measured, not assumed, and it does nothing here: with `branch = true`,
  coverage 7.14.1 on Python 3.12 reports `Can't use core=sysmon: sys.monitoring can't measure branches
  in this version, using default core (no-sysmon)` and **silently falls back**, adding eleven warnings
  for no gain. Do not re-try without a Python whose `sys.monitoring` supports branch coverage.
- **`-n auto` in `addopts`.** Corrupts the `perf` job, above.
- **A fixed worker count.** `-n 8` measured 255s against `auto`'s 225s, so the efficiency cores earn
  their keep locally, and `auto` adapts to CI runners (~4 cores) without a second knob.
- **Marking the politeness test `perf`.** It would leave the parallel lane, but it asserts a
  *correctness* property (different hosts are not serialised by a global lock) and would lose its
  cross-OS and cross-Python coverage. Sizing the margin keeps both.
- **Leaving the gate alone.** Defensible on the "a flaky gate is worse" argument — which is why the
  evidence bar above was set before the change was made rather than after.

### Carried

**xdist's summary line drops the `1 deselected` tally** — serial prints `5979 passed, 1 deselected`;
xdist prints `5979 passed` with `10 workers [5979 items]`. The deselection still happens (5,980 − 1 =
5,979 selected, and `perf` appears nowhere in the log); xdist's controller short-circuits its own
collection so worker `pytest_deselected` events never reach the terminal reporter. This program
reconciles counts against that line as a habit, so **the habit now reads the `[N items]` figure**,
which still moves if the filter is ever dropped.

---

## D-151 — Windows leaves the per-push path for a nightly schedule; it is not dropped

*2026-08-13. Mit: "I just don't want to be waiting for 30-100 minutes on that Windows CI, it's been
really slowing us down." Priority stated in the same breath: finish and release, on macOS.*

### Context

Every push to `main` ran the full 3-OS × 3-Python matrix. The twelve jobs run **concurrently**, so the
run's wall clock is its slowest job — and that was always Windows. Measured per step on run
`31663735766` (`8c1b78f`), the 3.12 jobs:

| Step | Windows | Ubuntu |
|---|---|---|
| checkout + uv + typesetting + sync + ruff + mypy | ~38 s | ~44 s |
| `uv run pytest` | **4,610 s** | **2,822 s** |

Setup is negligible; it is all pytest. Windows is only **1.63×** Ubuntu — the larger factor is that a
4-vCPU runner is ~3× slower than the dev machine. D-150 addressed the pytest side for every OS.
**This entry addresses cadence, which is the part D-150 cannot touch.**

### Decision

| Trigger | OSes |
|---|---|
| push to `main` | ubuntu + **macos** |
| nightly `schedule` (07:00 UTC ≈ 03:00 ET) + `workflow_dispatch` | all three |
| pull request | ubuntu only (unchanged) |

macOS stays on the push path because it is the platform boardwatch is actually run on.

**Windows is NOT dropped, and that restraint is the whole point.** The rot is the expensive failure
mode, not the runtime: D-145 records Windows not running for ~180 commits and silently accumulating
~130 failures, which then cost two fix rounds to clear. A nightly run caps a Windows regression at
about 24 hours of drift. Deleting the jobs would re-create exactly the debt this program already paid
off once, and the code's portability is deliberate (D-150's review and the platform investigation both
found `filelock` over `flock`, `platformdirs`, `as_posix()` normalization, and no `fcntl`/`pwd`/
`os.fork` anywhere in `src/`) — worth a canary to keep.

### Honest accounting of the gain

**D-150 had already taken most of it.** Windows should fall from ~77 min to roughly 25–30 with
`-n auto`; this change removes it from the push path, taking a push from about 30 minutes to ~20.
It is not a 100 → 20 improvement, and should not be described as one. **Both figures are predictions
until the first post-D-150 run reports** — the run carrying that measurement was in flight when this
was written.

### Alternatives rejected

- **Drop Windows from the matrix entirely.** What Mit's framing pointed at, and refused for the D-145
  rot argument above. The nightly gets the wall-clock relief without the debt.
- **Cut Windows to one Python version.** Saves runner minutes, **not wall clock** — the jobs are
  concurrent, so one 77-minute job still sets the duration. Addresses cost, which was not the complaint.
- **Windows Defender exclusions on the runner.** Plausibly worth 1.63× and untested. Deliberately not
  stacked on top of an unmeasured D-150: each Windows measurement costs a full CI run, and landing both
  at once makes neither attributable.
- **Weekly instead of nightly.** Seven days of drift is closer to the D-145 failure than to a canary.

### Carried

GitHub **disables scheduled workflows after 60 days of repository inactivity**, and scheduled runs
execute on the default branch only. If Windows coverage ever matters again, confirm the nightly is
still firing rather than assuming it — a schedule that silently stopped reads exactly like a green one.

---

## D-152 — Retraction: the archived CGPA claim is inverted; job-apps was never the stale copy

*2026-08-13. Ruled by Mit. Short entry, but owed: the archives state a fact that is false, and both are
closed.*

### Context

`DECISIONS-ARCHIVE.md:2453-2455` and `METRICS-ARCHIVE.md:901-902` record that job-apps'
`resume_base.tex` "carries a stale `CGPA: 8.5/10`" and that `{config_dir}/resume_template.tex` "was
corrected to `CGPA: 8.81/10`", concluding "the job-apps copy is the stale one." Nothing at the time
checked 8.81 against a source; the log then became the reason later sessions believed it, including
this one until Mit was asked.

### The correction

**Mit ruled: 8.5/10 is correct.** The evidence he supplied is the job-apps build of 2026-08-12, which
he can date and vouch for, and which reads `CGPA: 8.5/10` — matching `resume_base.tex`. So the archived
claim is **inverted in both directions**: job-apps was never stale, and 8.81 was not a correction but a
defect that would have printed an **inflated GPA on every résumé boardwatch rendered**.

Fixed in the two live source files (`{config_dir}/resume_template.tex:98`,
`{config_dir}/resume.yaml:6`), backups retained as `*.bak-8.81`. One stale generated artifact,
`{config_dir}/tailored/tailored-2012.typ`, deliberately left: it is prior tailor output that may
correspond to a real submission, so deleting it would destroy a record. It regenerates.

**Both archives are closed and are not edited** (D-108's split rule) — this entry is the correction of
record, in the same shape D-149 required for D-143 and D-145.

### What generalises

- **The repo never carried the value.** `grep` for `CGPA`/`8.81` across the tree hits only the two
  archive narrations. Mit's GPA lives in his config, never in shipped code — the multi-tenancy
  principle holding under a real test rather than in principle.
- **A value asserted as a "correction" was never checked against the thing it claimed to correct.**
  That is the same shape as D-149 finding 1, arrived at independently, and it is the argument for
  citing a source in the entry that makes a correction rather than only naming the outcome.
- **What settled it was an artifact the owner could date and vouch for**, not a file comparison. Two
  files disagreeing tells you nothing about which is right; newest-wins would have picked the defect.

## D-153 — A rich table's width can ignore `COLUMNS`, so terminal env is pinned for the whole suite

*2026-08-13. Found by measurement, not by reading the diff: the gate was red on CI and green locally.*

### Context

`make check` was green locally seven times running (D-150) while CI failed on **one** of nine matrix
jobs — `test (3.12, ubuntu-latest)` — on two different commits (`e629ea1`, `c633b33`). The failure was
`tests/unit/test_eligibility_cmd.py::test_abstain_names_rules_that_have_never_been_detected`, which
monkeypatches `COLUMNS=160` and then asserts `work_auth:eu_authorization_required` appears in the
`eligibility abstain` table.

Two things were ruled out before the cause was found. The catalog is **not** polluted: it holds exactly
44 patterns across six families, matching the report's own "44 rules · 44 never fired", and the rule is
present. Dependency drift is **not** possible: CI installs with `uv sync --frozen`.

### The cause

The failing output is padded and wrapped to exactly **80** columns despite `COLUMNS=160`. Rich has one
path that ignores `COLUMNS`: `Console.size` returns a hard-coded `(80, 25)` when `is_dumb_terminal`, and
that branch sits **above** the `COLUMNS` lookup. `is_dumb_terminal` is `TERM in ("dumb", "unknown")` AND
`is_terminal` — and `is_terminal` is true whenever `FORCE_COLOR` is set or `TTY_COMPATIBLE=1`, neither of
which requires anything to actually be a tty. At 80 columns the column's `overflow="fold"` (pinned by the
sibling test, correctly) folds the rule_id across a line break, so the substring assertion fails while
**no ellipsis appears** — the report is not abbreviating, which is why the sibling test still passed.

Reproduced locally, byte-for-byte identical to the CI assertion, with
`TERM=dumb FORCE_COLOR=1 uv run pytest -k abstain`.

### The choice

Normalise **`is_terminal`** — `os.environ.pop("FORCE_COLOR")`, `os.environ.pop("TTY_COMPATIBLE")`, plus
`TERM=xterm` as defence — at **conftest import time** in `tests/conftest.py`, not in a fixture.
Repo-wide: that conftest is an ancestor of every collected test.

**The first attempt at this was wrong and a review caught it before the push.** It pinned only
`TERM=xterm` in an autouse fixture. That fixed the width failure and *caused three new ones*, because
`is_dumb_terminal` gates **colour as well as width**: with a colour system resolved, `ReprHighlighter`
(on by default, and **not** disabled by `markup=False`) wraps leading integers in escape codes. Under
`TERM=xterm FORCE_COLOR=1` that broke `tests/pipeline/test_applied_state_suppression.py:124` and `:142`
on substring assertions and killed `test_the_JSON_path_names_every_bucket_too` with a
**`JSONDecodeError`** — ANSI codes inside `--json` output. The review named the first two; the JSON arm
was found by running it.

**A fixture cannot fix this, which is the load-bearing detail.** `Console.__init__` resolves
`_color_system` **eagerly**, and this program builds module-level consoles at import
(`cli/eligibility_cmd.py:66`, `cli/top_cmd.py:50`). Under ambient `TERM=xterm FORCE_COLOR=1` those bake
colour in before any fixture runs, so deleting the env later cannot undo it — measured: 4 failures with
the env deleted in a fixture, 0 with it deleted at import.

Verified across **five** hostile environments, all 47 relevant tests passing in each:
`TERM=xterm FORCE_COLOR=1`, `TERM=dumb FORCE_COLOR=1`, `TTY_COMPATIBLE=1 TERM=dumb`,
`TTY_COMPATIBLE=1 TERM=xterm`, `FORCE_COLOR=true`.

Alternatives rejected:

- **Fix only the three `COLUMNS`-setting tests.** The exposure is not theirs — *every* assertion over
  rich-rendered CLI output inherits it, and the next one written would be equally fragile.
- **Construct the command's `Console` with an explicit width in the test.** `Console(width=160)` alone
  does **not** work: the early return needs width *and* height, so the dumb-terminal branch still wins.
- **Pin `TERM` alone.** Tried, and red — see above. Recorded because it is the obvious fix and the one a
  future session would reach for.
- ~~**Clear `FORCE_COLOR`/`TTY_COMPATIBLE` instead** — two variables to chase, and it would suppress
  colour behaviour other tests may want.~~ **Retracted: this was the correct fix all along.** The stated
  reason had no test behind it — a grep for `ANSI`/`no_color`/`NO_COLOR`/`FORCE_COLOR`/`TTY_COMPATIBLE`
  finds no test in the repo asserting on ANSI output at all. `is_terminal` is the single root of both
  axes, so normalising it is one decision, not two.

### What generalises

- **A test that reads ambient terminal env is not deterministic, and xdist is not the suspect.** The
  first hypothesis was `--dist load` scheduling, since it makes worker composition timing-dependent. It
  was wrong. The evidence that redirected it was arithmetic on the failure message: the output was
  padded to 80, so the question became "what ignores `COLUMNS`", not "what ran alongside it".
- **A green local gate says nothing about a matrix job whose env differs.** Local is the same Python
  (3.12.12) as the failing job; only the environment differed.
- **One env property gated two unrelated behaviours, and fixing the first broke the second.** The
  author's fix passed the full gate locally because the hostile variable was not set locally — the same
  blind spot this very entry describes, walked into while writing it. What caught it was a review with a
  different lens, and what completed it was enumerating the arms: the review named two failures, running
  it found a third (the `--json` `JSONDecodeError`).
- **Eager resolution defeats fixture-time repair.** Anything a library computes in `__init__` is fixed
  before any fixture runs, so module-level singletons must be normalised at import time.
- **The exact env var that runner set is still unread.** The deduction is sound — the padding proves
  width 80, and only `is_dumb_terminal` yields 80 against `COLUMNS=160` — but which of `FORCE_COLOR` or
  `TTY_COMPATIBLE` it supplied was never confirmed, and the fix is immune to both.

## D-154 — `eligibility_inputs` gains an identity index; `top`'s pending anti-join cost 141 s per run

*2026-08-13. Pure performance. No semantics change, no backfill.*

### Context

`boardwatch top` was unusable as a daily driver: it printed `evaluating eligibility for 19855 postings…`
and then produced nothing for over ten minutes before being killed. It is also the command whose `#`
column the résumé flow needs, so this blocked the first render of a boardwatch résumé.

`top` calls `run_eligibility` (`cli/top_cmd.py:186`) before it ranks or prints anything, whose `_pending`
anti-join (`eligibility/preflight.py:53-95`) correlates on `eligibility_inputs.posting_version_id` and
filters `profile_hash`/`rules_hash`. That table carried **only** its primary key and the
`input_fingerprint` unique index — nothing on the correlated column. SQLite therefore satisfied the
`EXISTS` from the other side: re-scan `uq_eligibility_deterministic`, rowid-probe into
`eligibility_inputs`, once per open posting.

### The measurement

Against a **copy** of the live 24,073-posting store (Mit's database was not mutated), timing the real
`_pending` through the project's own `current_identity`:

| | Time | Rows |
|---|---|---|
| before | **141.54 s** | 4,655 pending |
| `CREATE INDEX` | 0.21 s | — |
| after | **0.14 s** | 4,655 pending |

**1,011x.** Identical row counts on both sides, which is the check that the index changed speed and not
results.

### The choice

One composite index, `(posting_version_id, profile_hash, rules_hash)`, column order matching the
subquery's predicates — correlated equality first, then the two identity hashes. Declared in
`tables.py` *and* in migration `perf_eligibility_inputs_identity` because
`test_migrations_match_metadata` holds the two in agreement; the head pin in
`tests/unit/test_schema_head.py` was bumped, which that test exists to force.

Deliberately **not** done in this change:

- **`ANALYZE`.** `sqlite_stat1` has never existed on this store, so every plan is chosen on defaults.
  Worth doing, but statistics go stale and where they are refreshed is a separate decision.
- **The wasted `body_text` read.** `top_cmd.py:219` pulls `body_text` for all ~23,455 current versions
  (~160 MB) when only `posting_version_id` is ever used. Measured at 0.27 s warm — real waste, but not
  a latency cause, so it does not belong in a fix justified by latency.
- **`current_gate_verdicts`' full scan** of `eligibility_evaluations` (no index on
  `(engine_kind, engine_version)`). Measured 0.37 s warm.
- **Whether `top` should backfill eligibility inline at all.** The index removes the pathological floor,
  but ~4,655 pending postings are still evaluated and written before the first line prints. That is real
  work, not a defect, and making ranking a read-only operation is a design decision.

### What generalises

- **A hard floor can hide behind a plausible progress message.** "evaluating eligibility for 19855
  postings…" reads as work proportional to a queue; 141 s of it was paid even with the queue empty.
- **A missing index is invisible to every gate this program has.** `make check` is green, and no perf
  test covers `top` — the `perf` job measures the top path only (0.245-0.268 s).
- **The corpus is the test fixture that does not exist.** The pathology needs ~24,000 postings to show
  up at all; nothing in `tests/` approaches that, so it could only be found by running the real command
  against the real store.

---

## D-155 — The program reorients onto the bundle-to-résumé path; `resume.yaml` becomes an import source, not an artifact to hand-fix

*2026-08-13. Mit's call, during the broad roadmap review. Changes what gets built next, not any shipped
behaviour.*

### Context

The roadmap review found the program in one shape: build largely complete, operation almost absent. P0,
P1, P2 and P5 gates MET; P3, P4 and P6 gates NOT MET and all three waiting on the same thing — daily runs
that never accumulated because three `resume.yaml` bullets (245 / 234 / 232 characters against a 220-char
layout gate) force an untailored degrade on every posting.

The obvious move was to fix those bullets and unblock three gates with one content edit. Mit rejected it:
the canonical career-profile bundle was built **for exactly this purpose** — to be the source résumé
tailoring reads — so time spent repairing a file the bundle is meant to replace is time spent on the wrong
artifact.

### The premise that was false

`STANDING-FACTS.md` carried *"Nothing is generating Mit's résumés daily right now,"* and the ordering
argument in `PROGRAM.md` §2 (output-side work first, because Mit gets zero résumés a day) rested on it.
Measured against the filesystem instead of recalled:

| Date | job-apps folders | PDFs |
|---|---:|---:|
| 2026-08-09 | 3 | 8 |
| 2026-08-10 | 3 | 28 |
| 2026-08-11 | 5 | 24 |
| 2026-08-12 | 4 | 18 |

`STAGE1_ONLY=1` **is** in the launchd plist, so the automated 08:30 run does stop after discovery — but
résumés are being produced anyway. **job-apps is delivering Mit's daily minimum.** The line is corrected in
`STANDING-FACTS.md`; the "LIVE GAP" urgency it fed is retired.

This matters beyond bookkeeping: with no live gap, freezing P3, P6 and the 14-day acceptance clock costs
nothing, which is what makes the reorientation affordable.

### The choice

**1. `resume.yaml` is not hand-fixed. It is imported.** The design's §18.1 already names it a first-class
source: `source_kind: boardwatch_resume`, adapter `boardwatch-resume-v1`, version 1, scope `complete_file`
— one of exactly four kinds in the closed catalog, reading *"exactly Boardwatch's current logical résumé
shape."* Verified against Mit's real file through the shipped enumerator, not inferred:

```
SOURCE RECORDS ENUMERATED: 81
  header: 2 · education: 2 · skill-groups: 58 · entries/metadata: 6 · entries/bullets: 13
```

81 is Gate B's source-record denominator for that one source. The content problems (over-long bullets,
missing Knowledge Forge, stale `skill_groups`) get fixed **in the bundle**, where a bullet is an approved
claim candidate carrying facts, metrics and evidence — not in a flat YAML list that structurally cannot
hold them.

**2. The projection is designed BEFORE Gate B is populated**, inverting §23's stated order. Gate B is the
expensive, human-bottlenecked phase; entering hundreds of facts, metrics and claims without knowing what
the projection needs to read risks doing the slow part twice. The design half-concedes this —
*"Gate B may expose schema defects."* The projection design runs against the synthetic example bundle that
already ships as package data, so no personal data is entered to produce it.

**3. P3, P6 and the 14-day acceptance run are frozen deliberately**, not blocked. Recorded so the freeze is
a decision rather than drift.

### Alternatives rejected

- **Fix `resume.yaml` first anyway, to unblock three gates cheaply.** Recommended in-session and
  overruled. The recommendation was built on the false premise above; once job-apps is known to be
  delivering, the unblock buys operational data for a pipeline whose input is being replaced.
- **Populate Gate B first, per the design's own ordering.** Defensible, and it is what §23 says. Rejected
  for the schema-churn risk: the projection is the only consumer, and a producer designed without its
  consumer is a hypothesis.
- **Build the projection against the frozen `Resume` model without the bundle.** That is what `resume.yaml`
  already is. It reproduces today's system with more steps.

### What generalises

- **An ordering argument outlives the fact it rested on.** `PROGRAM.md` §2's whole output-side-first
  rationale was "Mit gets zero résumés a day." That stopped being true and nothing re-checked it, because
  the sentence had been promoted to a standing fact. **A standing fact about the outside world needs a
  re-measurement date, not just a citation.**
- **The cheapest unblock is not automatically the right one.** Three gates for one content edit is a real
  argument; it is still wrong when it buys throughput for the component being replaced.
- **A wall built for isolation is a wall to take down later, and that cost is part of the design.**
  `profile_bundle` never importing `tailor` (and a test holding it) was correct for Gate A and is exactly
  what the projection must now dismantle.

---

## D-156 — v1 projection is not authoritative for header, education or summary, because the renderer never reads them

*2026-08-13. Scope decision forced by external review. Changes the design under construction, no shipped
behaviour.*

### Context

The projection design (revision 1, `ce1efde`) specified projecting `header`, `education`,
`skill_groups`, `entries` and `extracurricular` from the career-profile bundle into a document the
existing tailor loader reads. Two external reviewers ran against it in-repo, independently, with the same
brief. Both returned **REWORK**.

All seven of the design's own "measured facts" were confirmed by both reviewers. The defects were in what
the design built on top of them — which is the useful shape of this entry.

### The finding that forced the scope change

**`LatexRenderer.emit` never reads `Resume.header` or `Resume.education`.** It builds sections from
skills, entries, projects and extracurriculars only. The layout gate states it verbatim
(`reports/resume_gate.py:237-242`):

> "Header/education are NOT asserted here: Increment 1's template hardcodes them (never model-rendered),
> and `_validate_template` guards the rendered header/education at template-resolve time instead."

So projecting them could not change the PDF. Change the owner's name or GPA in the bundle and the
compiled résumé keeps the template's hardcoded values, **while the golden test and the round-trip
equality both pass** — a faithfulness design failing silently on identity, catchable by no proposed gate.

This is the same failure class as D-155's own lesson, one working day later: an argument resting on a
premise nobody measured. `Resume.header` exists on the model, so it was assumed to reach the page.

### The choice

**v1 projects only `skill_groups`, `entries` and `extracurricular` — the fields the renderer consumes.**
`header`, `education` and the summary are declared **template-hardcoded and out of scope**, the same
reasoning already accepted for the summary alone.

Stated so it is never assumed otherwise: **after v1 the bundle is not the source of truth for the owner's
name, contact details, or education.** Those stay hand-edited in the LaTeX template. Renderer ownership of
them is a separate design.

The narrowing dissolves two further review findings at no cost: the contact-channel grammar (email, phone
and profile URL are `ContactRecord`s, not facts, and the synthetic phone is `application`-only, so a naive
fix would have leaked an application-only surface onto a résumé) and a template-smuggling example the
design itself committed (`{education.result}/10` against a 4.0-scale GPA renders "3.85/10").

### Alternatives rejected

- **Wire `header`/`education`/summary into the renderer in v1.** Delivers full authority but breaks the
  "nothing downstream changes" property that makes v1 a discardable experiment, requires new layout-gate
  assertions where the gate currently documents their absence, and drags in the contact grammar. Deferred,
  not refused.
- **Leave revision 1 as written and fix only the other findings.** Rejected: it would ship a faithfulness
  guarantee that provably cannot land, which is worse than not claiming it.

### Fifteen further findings, all dispositioned in the spec's §13

Fixed in revision 2: a typed `ProjectionPool` (a serialized `Resume` has no `pinned` field, so stage 2
could not tell the fixed core from swappable projects); tailor owns persona shaping (stage 2 trimming for
budget made `apply_persona` raise `PersonaError` on the missing id — latent only because both bundled
personas ship `entries: null`); a closed placeholder grammar plus a typed-value rendering table; claim
`subject_id` and skill-surface checks (an approved claim belonging to another entity passed every rule and
would have printed one project's accomplishment under another employer); an **admission floor** — without
it a roomy budget admitted zero-score candidates, so a mobile JD and a data JD produced identical résumés
and v1 decided nothing; a manifest sidecar (`yaml.safe_load` discards the comments revision 1 stored
provenance in); a shared `effective_skills` primitive; a digest-bound owner approval stamp for template
literals; **mean per-bullet scoring** after a probe showed a shallow four-bullet entry beating a focused
one-bullet entry 4 to 2 under the unnormalized metric; and the compile gate's four arms — only
`PAGE_LIMIT_EXCEEDED` drops a candidate, because a missing `pdfinfo` returns `None`
(`reports/tailor.py:167-171`) laundered into `COMPILE_FAILED` and would otherwise have dropped every
candidate and blamed the owner's pinned content.

Recorded as an open question rather than assumed: **nothing wires projection into `boardwatch run`**
(`run_cmd.py:80` reads static `resume.yaml`), so the mechanism would never adjust anything in the flow the
owner actually runs. Gated at delivery slice P5 as an explicit owner ruling.

### What generalises

- **A field existing on a model is not evidence it reaches the output.** Trace the consumer, not the
  schema. Three fields on the frozen `Resume` are decorative with respect to the PDF, and only the layout
  gate's docstring says so.
- **The premise list you hand a reviewer bounds what they check.** Both reviewers verified the seven
  claims asked of them and both passed all seven; the fatal defect was in an eighth claim the design made
  implicitly and never wrote down. One reviewer found it anyway. **Ask reviewers to enumerate the
  premises the design relies on, not only to check the ones it states.**
- **Two reviewers with one brief beat one reviewer.** They disagreed three times and the disagreements
  were the highest-value output: `tech_tags` lineage significance, the private `_applicable_swaps`
  contradiction, and whether the two-stage split was real. All three resolved against the code, all three
  in the same reviewer's favour — but the *disagreement* is what marked them as worth checking.
- **A design can contradict itself across sections and read fine.** Revision 1 said entry scoring
  "inherits `build_plan`'s behaviour" and that `plan.py` is unchanged. Both sentences are reasonable; only
  together are they impossible.

---

## D-157 — Corrections that unblock D-149: the manifest write order, and Windows closed by CI

*2026-08-13. Two corrections to append-only entries, plus the CHANGELOG gap D-149 named. Clears the
prerequisites D-149 set for the `STATE.md` trim. No code changes.*

### Context

D-149 blocked the `STATE.md` Gate A trim because three of its narration blocks held facts that the
decision log had wrong or did not hold at all. Deleting them would have destroyed the only true record
of two facts. D-149 listed four prerequisites and deliberately did not resolve them. This entry resolves
the first three; the fourth is a carry, satisfied by the rewritten `STATE.md`.

### Correction 1 — D-143's stated write order is wrong; the manifest goes SECOND

D-143 says: *"Write order: evidence, then the record documents, then the manifest — the pointer target
before the pointer."* **The shipped code does not do that**, and has not since the review that changed
it:

```
authoring.py:251  _write_documents(tree, {EVIDENCE_PATH: appended, MANIFEST_PATH: restated, **citing_back})
authoring.py:236  "The manifest goes SECOND rather than last, which is the part that is easy to get wrong."
```

Written last, the manifest gave every citing document a failure position carrying
`evidence_set_digest_mismatch`. The order is evidence → **manifest** → the citing documents.

`DECISIONS.md` is append-only, so D-143 is not edited. **This entry is the record of the correct order**,
and it is now held somewhere other than `STATE.md`.

### Correction 2 — D-145's Windows prohibition is discharged; CI closed it

D-145 says: *"Do not claim Windows is green from here — the run that produced this list was cancelled at
72%, several failures were masked by the pointer cascade, and this machine cannot execute the matrix. CI
is the only thing that can close it."* That prohibition was correct **when written**: D-145's own measured
outcome stops at 2 failures.

**CI closed it exactly as D-145 required.** The Gate A range is green on all twelve jobs at `8475319`,
Windows included, recorded in `METRICS.md` against that sha. The Windows suite runs **5,883 passed / 48
skipped in 1:18:03** — roughly four to five times the local gate, which is slow, not hanging.

So the claim "green on all twelve jobs, Windows included" is **true and may be made**, citing the CI run
and this entry — **not** D-145, which prohibits it. That mis-citation was D-149's finding 2 and is what
made the trim unsafe.

### Correction 3 — `cited_back` now appears in CHANGELOG

D-149 found `cited_back` shipped, user-visible, and absent from `CHANGELOG.md`, which is authoritative for
what shipped. Added to the `[Unreleased]` bundle entry in this change. *(D-149's original claim that it was
"recorded nowhere but `STATE.md`" was itself corrected before merge — `docs/profile-bundle-authoring.md:631`
had it. Only CHANGELOG lacked it.)*

### The fourth prerequisite, carried not resolved

D-149 required that this be carried into whatever survives the trim, and the rewritten `STATE.md` carries
it verbatim:

> **Treat the closed review loop as evidence about the slices reviewed, not about the subsystem being
> defect-free.**

It is earned: two silent-success defects (D-138/D-142, D-141) were found *after* the loop closed, in code
six reviews and four gates had passed.

### Consequence

**The `STATE.md` Gate A trim is UNBLOCKED.** Every fact the narration uniquely held is now recorded
elsewhere: the write order here, the Windows green in `METRICS.md` plus here, `cited_back` in `CHANGELOG`
and the authoring guide, and the review-loop caveat in `STATE.md` itself.

### What generalises

- **An append-only log makes a wrong entry permanent, so the correction must be findable from the wrong
  one.** D-143 still says the wrong thing; what makes that survivable is that D-149 names it and D-157
  corrects it, and the index carries all three. A retraction that is not linked from the claim it retracts
  is not a retraction ([[retracting-a-claim-means-grepping]] in kind).
- **A prohibition can expire, and nothing expires it automatically.** D-145's "do not claim Windows is
  green" was right when written and wrong three days later, because the thing it demanded actually
  happened. A standing prohibition needs a stated discharge condition, or it outlives its reason and
  starts contradicting the truth.
- **Trimming a read-first file is not editing — it is deciding which record survives.** D-149's real
  finding was that three blocks were load-bearing, not verbose. Check what a line uniquely holds before
  deleting it.

---

## D-158 — The projection scorer is chosen by measurement, because two design rounds picked two scorers and a probe falsified both

*2026-08-13. Round-2 external review of the projection design. Changes how a decision gets made, not what
the decision is.*

### Context

Revision 2 of the projection design went back to GPT with an improved brief (D-156's lesson: ask the
reviewer to **derive** the premises rather than check a supplied list). It derived **24 premises of its
own and failed 8 — five of them premises the design never wrote down.** VERDICT: REWORK, 8 BLOCKING.

**Three of the eight defects were created by revision 2's own fixes.** That is D-137's five-round pattern
reproduced, by an author who had just written a warning about exactly it into the reviewer's brief.

The worst was a direct consequence of D-156's scope narrowing: `Resume.header` and `Resume.education` are
**required fields with no default** (`tailor/model.py:45-48`) and `load_resume` rejects a header with no
valid email (`load.py:59`). Revision 2 stopped sourcing them without noticing the model demands them, so
**no projected document was constructible or loadable at all.** Fixed by an explicitly inert shell copied
from the authored `resume.yaml`, model-only and never authoritative for the PDF.

### The decision

**The deterministic entry scorer is not named by the design. The design names the procedure that picks
it.**

| Round | Scorer chosen analytically | Falsified by |
|---|---|---|
| 1 | `\|skills(entry) ∩ jd_skills\|` | shallow 4-bullet entry beats focused 1-bullet, **4 > 2** |
| 2 | mean per-bullet coverage | focused 1-bullet beats 6-bullet covering **nine** JD skills, **2.0 > 1.5**; also scores bullets `MAX_BULLETS_PER_ENTRY` deletes |

Both were picked by the same author reasoning on paper, and both fell to a probe in the next round. A
third formula would fall to a third probe.

So a new delivery slice **PM** lands *before* P4: an **owner-labeled selection matrix** — ten real
postings spanning the owner's role families, each with the owner's own ranked expected candidate entries,
**recorded before any scorer is tuned against it.** Candidate scorers (mean coverage, total distinct
matched, mean over the top-`MAX_BULLETS_PER_ENTRY` bullets only, and a lexicographic
`(coverage, density)`) are scored by rank agreement; the winner ships with its number in `METRICS.md`.
The same matrix becomes the baseline the v2 model re-ranker must beat.

The admission threshold moves with it. `score > 0` is a zero filter, not a relevance threshold — an
incidental "documentation in Python" bullet scores 1.0 and suppresses the owner-declared fallback.
Picking a number here would repeat the mistake of picking a formula here.

### Also fixed in revision 3

`approve-projection` ships in P1 — revision 2 specified an approval gate with **no command able to create
the stamp**, a quarantine with no drain, which this project's own rules forbid in the same change that
creates the quarantine. The typed-value table now defines projection-owned renderings for all ten
`FactValueKind` members (revision 2 said nine, and invented a display form for `DateRangeValue`, which has
only `type`/`start`/`end`). The fidelity contract gained an **effectiveness** row: surface permission plus
conflict-freedom does *not* mean a fact is usable, and a fact can expire with no bundle bytes changing.
Non-null `persona.entries` is refused by preflight, because moving persona application downstream did not
remove the `PersonaError` collision, only relocated it. `resume project --posting` moves out of the
`profile-bundle` family, which deliberately never opens the database.

**One finding is accepted rather than fixed:** the manifest does not close stale lineage, because
`tailor run` never reads it. Revision 2 scored that "Fixed" and was wrong. The real fix belongs to slice
P5, where the pipeline — which already knows the store, the posting and the artifact ledger — validates it
without `tailor` learning about the bundle.

### Alternatives rejected

- **Pick a third scorer and run round 3.** The exit criterion says the loop ends when a round finds no
  BLOCKING defect, and rounds are cheap. But the scorer question is not a defect to be reviewed out; two
  rounds of evidence say analysis is the wrong instrument for it.
- **Ship `> 0` and tune later.** It reads as a relevance threshold and is not one. Shipping a placeholder
  that looks like a decision is how a heuristic becomes permanent.
- **Defer the matrix to P6 as originally written.** It was already the P6 gate; moving it before P4 costs
  the same owner session and makes v1's own choice measurable instead of asserted.

### What generalises

- **A question that keeps being answered wrongly on paper does not belong on paper.** Two analytic
  answers, two probes, two falsifications. The fix was not a better formula but a labeled corpus — and the
  tell was that each round's *reasoning* was sound while each round's *answer* was wrong.
- **A fix round creates defects at roughly the rate it removes them, and scope changes are the worst
  offenders.** D-156 narrowed scope to remove an inert projection and thereby removed the source of two
  mandatory fields. Narrowing is not free: it deletes suppliers as well as consumers.
- **Improving the reviewer's brief measurably improved the review.** Round 1 checked 7 supplied premises
  and passed all 7. Round 2, told to derive its own, produced 24 and failed 8 — five of them unstated.
  **The instruction "if your derived list matches the design's stated one, you have not done this task"
  did the work.**
- **Label the ground truth before building the thing it judges.** A matrix labeled after seeing a scorer's
  output is a test that agrees with itself.

---

## D-159 — `COLUMNS` is baked into a `Console` at import, so three width-controlling tests never controlled anything

*2026-08-13. Root cause of the ubuntu/3.12 CI failure D-153 tried and failed to fix. Corrects D-153's
scope. Test-only change; no production behaviour moves.*

### Context

`test (3.12, ubuntu-latest)` failed **six consecutive runs** — never 3.11, never 3.13, never macOS, on the
same runner image — while `make check` was green locally every time. D-153 diagnosed rich's
`is_dumb_terminal` branch and normalised `is_terminal` at conftest import. **That fix did not close it**,
and a first attempt before it traded one failure for three. Two wrong fixes, two sessions.

### The root cause

Since **rich 15.0.0**, `Console.__init__` resolves width **eagerly**:

```python
if width is None:
    columns = self._environ.get("COLUMNS")
    if columns is not None and columns.isdigit():
        width = int(columns) - self.legacy_windows
self._width = width
```

`Console.size` then returns `self._width` **verbatim and never re-reads the environment**.
`cli/eligibility_cmd.py:66` builds `console = Console()` at **module import**.

So a console built under an ambient `COLUMNS` is frozen at that width for the life of the process, and
`monkeypatch.setenv("COLUMNS", ...)` inside a test body is a **no-op**.

**Three width-controlling tests in `tests/unit/test_eligibility_cmd.py` had therefore never controlled
anything.** They passed only because `COLUMNS` happened to be absent at import — the single state that
leaves `_width = None` and keeps `Console.size`'s live lookup reachable. Their real input was whatever the
runner supplied.

At width 80 the `rule` column is 25 characters: `clearance:doe_q_required` (24) renders whole,
`work_auth:eu_authorization_required` (35) folds. **The first id passing is what proves the failure is
width and not enumeration** — and it is why only one assertion in the loop ever tripped.

### The measurement

```
COLUMNS=80 uv run pytest tests/unit/test_eligibility_cmd.py -k abstain --no-cov -n 0
```

reproduces CI's assertion **byte-for-byte** — the 80-wide title padding, the footer wrapping after
`0 rows `, and 1 failed / 3 passed. After two sessions of CI-only failure, the bug reproduces in 1.5
seconds.

### The fix

`os.environ.pop("COLUMNS", None)` and `pop("LINES", None)` added to the existing D-153 import-time block
in `tests/conftest.py` — same layer, same reasoning, second independent property. Plus
`test_setting_COLUMNS_reaches_the_module_level_console`, which pins the premise the other three rest on
(`setenv COLUMNS=137` ⇒ `console.width == 137`) so the pops cannot be removed silently.

Verified both directions. **Without the fix under `COLUMNS=80`, two tests fail and the named assertions
are the premise test (`assert 80 == 137`, the repr showing `_width` baked to 80) and the CI one** — naming
which assertion trips matters, because a pre-existing assertion firing first would have proved nothing
(D-148). With it: 29/29 across seven hostile environments, and `tests/unit tests/cli` 1,826 passed under
three.

### What was falsified, by running rather than reasoning

- **The `--json` hypothesis** (assert against JSON instead of a rendered table): `eligibility abstain` has
  **no `--json` mode**. `abstain_cmd(ctx)` takes no options. It was never available.
- **Dependency drift:** the three ubuntu jobs' installed package lists are **md5-identical**, `rich==15.0.0`
  in each.
- **The interpreter difference** — the one real 3.12/ubuntu asymmetry, since that job uses the runner's own
  `/usr/bin/python3` (3.12.3) while 3.11/3.13 get uv-downloaded builds. Tested directly in `ubuntu:24.04`
  under Docker: passes. Dead.
- **Cross-test console mutation:** nothing in `src/` or `tests/` sets `console.width`; the only `COLUMNS`
  writers are the three tests, all via `monkeypatch`.

### Correcting D-153

**D-153 is not wrong, it is partial.** Its `is_terminal` arms are genuinely closed — `TERM=dumb
FORCE_COLOR=1`, `TTY_COMPATIBLE=1 TERM=dumb`, and `FORCE_COLOR=true` all pass. It fixed one arm of two and
was written as though it had fixed the failure. Read it as a real finding about colour and the
dumb-terminal branch, not as the resolution of this CI job.

### The residual, unclosed and stated as such

**What supplies `COLUMNS≈80` to that one job is unknown.** CI went red at exactly `e629ea1`, the commit
that added pytest-xdist and `-n auto` (D-150), and was green on the commit before. Every candidate
testable from this machine is excluded above; no diagnostic was pushed to CI. **The fix does not depend on
the answer** — popping removes the ambient dependency entirely, so whatever that job carries can no longer
reach the assertion.

### What generalises

- **A test that sets an environment variable to control a library must prove the setting arrives.** Three
  tests asserted on rendered width for months while controlling nothing, and all three were green. The
  remedy is the premise test: pin the mechanism the other tests rest on, separately, so it fails loudly
  instead of silently disabling them.
- **"Eager at construction" beats "read at use" as a failure shape, and import time is the worst case.**
  D-153 found the same shape for colour (`Console.__init__` resolves `_color_system` eagerly) and did not
  generalise it to width. **When a library is found to bake one property at construction, check every
  other property it exposes.**
- **A single-job CI failure across two sessions is worth a full reproduction, not a third guess.** Two
  fixes were shipped on deduction. The reproduction took one environment variable, and it should have been
  the first move after the second failure, not after the sixth.

---

## D-160 — Preflighting a thrice-reviewed spec still found four false claims, and the plan argues from the preflight

*2026-08-13, writing the projection implementation plan in fresh context. Preflight record:
`docs/superpowers/research/2026-08-13-projection-plan-preflight.md`. Plan:
`docs/superpowers/plans/2026-08-13-career-profile-projection.md`.*

### Context

The projection spec reached revision 3 after three external review rounds, all REWORK (D-156, D-158).
Its §2 opens *"Verified against the code on 2026-08-13."* The plan was nevertheless preflighted
against the code before task 1, on the strength of one prior result: a spec-reviewed 1208-line plan in
this repo still carried six defects plus one repo-wide issue, and preflighting is what found them.

About sixty claims were checked. **The load-bearing premise held** — `LatexRenderer.emit` never reads
`Resume.header` or `Resume.education`, re-verified through every helper *and* the template
(`resume_base.tex:72-80`, `:87-93`), so D-156's scope narrowing stands. **Four other claims are
false, twelve citations have drifted or name a path that does not exist, and nine facts the plan
needs are absent from the spec.**

### Choice

**Where the spec and the preflight disagree, the preflight wins**, and the plan carries a correction
table naming every instance rather than silently implementing the corrected version. Eight
corrections are load-bearing enough to record here:

1. **An out-of-catalog `Entry.kind` is silently dropped from the PDF, not routed to Experience.**
   Both section filters are equality tests (`tailor/render/latex.py:155`, `:170`), so a third value
   matches neither and the entry and all its bullets vanish with no error. The spec argued the
   weaker "renders silently". The closed catalog is therefore more load-bearing than it claimed, and
   the test asserts **absence from the rendered source**.
2. **No `Resume` serializer exists anywhere in the repo.** Verified three ways. `model_dump_json()`
   appears at exactly two sites, both hashing; `scaffold_template()` writes a static string. The
   spec's `resume.projected.yaml` needs new code, routed through `yaml_writer.document_bytes`
   because `yaml.safe_dump` emits documents the restricted loader refuses.
3. **The projection approval stamp gets its own type; `ApprovalStamp` may not be reused.**
   `test_profile_bundle_cli_approval.py:427-447` asserts by `rglob` over `src/` that exactly two
   files call `approval_stamp_bytes(`, `ApprovedVia` is a closed one-member enum in the shipped JSON
   schema, and `candidate_content_digest` means *bundle candidate* — reusing it would let a bundle
   approval satisfy a projection gate. Keep the properties, not the type.
4. **The effectiveness gate passes vacuously if the surface gate runs through
   `eligible_fact_surfaces`**, which returns `frozenset()` for a non-effective fact. Use
   `effective_fact_ids` for effectiveness and the predicate catalog for surfaces, separately. Expiry
   is a third gate and needs `completeness._declared_expiry` promoted to public — `effective.py` has
   **no `as_of` parameter on any function**, deliberately.
5. **`effective_skills`'s signature is `(text, jd_skills, table, taxonomy)`** — the repo calls it
   `table`, and `build_plan`'s order puts `taxonomy` last. The spec had both name and order wrong.
6. **The drift test cannot claim the shared callable is the repo's only coverage implementation.**
   There are four, and they are not equivalent: only `plan.py:77` unions the equivalence-swap
   images. Folding `reports/tailor.py:255`/`:271` in would change their emitted audit values.
7. **The package must live at `src/boardwatch/projection/`, top level.** Under `boardwatch/tailor/`
   it would join `TAILOR_ROOTS` and fail the wall on its first import. And because the walk is
   transitive, **no module in the 58-module tailor closure may import it** — notably
   `reports/tailor.py`, `core/settings.py`, `cli/context.py`. `cli/app.py` is outside the closure,
   which is what makes the CLI registration legal and what makes slice P5 the risk.
8. **The spec's §9 expiry before/after control is impossible with the fact it has in mind.**
   `fact.packet-pantry.legacy-language.001` is genuinely stale, résumé-surfaced and conflict-free —
   the claim checks out — but it fails on `verification_state`, so no choice of `as_of` moves it. The
   fact that can is `fact.example-credential.expiry.001`. Two fixtures, two code paths.

Two miscited records are also corrected: §8's D-141 is a silent *hang*, not a silent success (D-138
fits); §9's "98 tests / 5 of 13" figure is `METRICS.md:2266` and says **documents**, not "classes"
— D-149 is the blocked STATE trim and is unrelated.

### Alternatives rejected

- **Trust §2's "verified" line and write the plan from the spec.** Rejected on the prior result, and
  the preflight then falsified two claims that sentence covered.
- **Revise the spec to revision 4.** Rejected: D-158 closed the design loop deliberately, and three
  of round 2's eight defects were created by round 1's fixes. A correction table in the plan gives
  the executor the right facts without reopening a loop that was stopped on purpose. The plan states
  that where the two disagree, the preflight wins.
- **Fold the corrections silently into the tasks.** Rejected — an executor reading the spec alongside
  the plan, as `writing-plans` intends, would hit the contradiction with no way to resolve it.

### Consequence

The plan is 23 tasks over P0–P4, with PM as the owner's one-session task and P5/P6 declared but not
decomposed. Two tasks exist purely because of gate mechanics the spec could not have known: the
example declaration is registered as pinned `SHIPPED_DATA` **before** the code that reads it, because
R7 fails the build on any new data file without a reviewed entry and two hardcoded counters break on
the first one added; and R5 bans a `resume` or `cv` path segment on any data file, including a
directory segment, so fixtures are named `master_resume.yaml` and `projection.golden.txt`.

**P4 names no winning scorer.** It builds four candidates behind one interface, and both falsifying
probes (`4 > 2`, `2.0 > 1.5`) are **authored as fixtures rather than cited**, because neither exists
anywhere in the repo — they lived in external reviewers' contexts.

### What generalises

- **A spec's own "verified against the code" line is a claim, not evidence, and review rounds do not
  audit it.** Three reviewers passed §2's premises; the four false claims were mostly *outside* the
  premise list, which is the D-156 lesson recurring one level up. Preflight the citations, not just
  the reasoning.
- **Line numbers in a spec rot faster than its arguments.** Twelve of about sixty citations had
  drifted or named a path that never existed (`render/latex.py`), while the surrounding claims were
  true. Confirm one with `grep -n` before copying it into anything executable.
- **A test the design specifies can be impossible while the fact it rests on is real.** The stale
  fact exists exactly as promised and still cannot demonstrate the transition asked of it. Check that
  a specified fixture can *exercise the arm*, not just that it exists — the same shape as D-142's
  probe that could not reach its arm.
- **Fan-out cost is model choice times width, and subagents inherit the parent model silently.**
  Five preflight agents were dispatched on the parent's model when four were mechanical retrieval.
  Under a budget, set the model per agent at dispatch; there is no second chance once they are running.

## D-161 — A third import wall guards the bundle serializer, and projection digests through the YAML writer instead

### Context

Executing the career-profile projection plan, Task 3 (`projection_digest`) follows the plan's literal
code and imports `from boardwatch.profile_bundle.canonical import digest_of`. That turns
`tests/profile_bundle/test_profile_bundle_hash_isolation.py::test_no_existing_module_imports_the_bundle_serializer`
red immediately.

That test forbids **any** module under `src/boardwatch/` outside `profile_bundle/` from reaching
`boardwatch.profile_bundle.canonical`, by any spelling — it applies a dotted-substring lens *and*
resolves imports through `tests/profile_bundle/import_graph.py`, so deferred, aliased and relative
forms are all caught. Its assertion is `offenders == []`: there is **no allowlist mechanism at all**.
Its stated reason is that the serializer's bytes are identity, and "a second caller elsewhere is how a
shared hash quietly acquires a second meaning." It carries its own positive controls, so unlike the
version it replaced it cannot go blind.

**The plan, its eight-row correction table, and its preflight all fail to mention this test.** The plan's
Global Constraints section discusses the import wall at length and names *two* assertions, both from
`test_profile_bundle_tailor_isolation.py`. This is a third wall in a different file. The mechanical pass
that preceded execution (D-160) verified every pre-existing symbol the plan imports exists with the
signature used — and `digest_of` does exist, and the call is correct. No symbol check can see that a
test forbids the import.

### Decision

`projection_digest` hashes `yaml_writer.document_bytes(...)` output rather than calling `digest_of`:
`"sha256:" + sha256(document_bytes(declaration.model_dump(mode="json"), logical_path=...)).hexdigest()`.

Verified before ruling: `document_bytes` is imported today by exactly five modules, **all inside
`profile_bundle`** (`approvals`, `rebase`, `authoring`, `promotion`, `drafts`); **no test anywhere under
`tests/` even mentions `yaml_writer`**, so no analogous guard exists; and it does not reference
`canonical` at all. The projection plan already routes Tasks 9, 11 and 13 through `document_bytes`, and
the preflight independently recommends it for the `Resume` serializer — so projection joins an existing
convention rather than acquiring an exemption.

### Alternatives rejected

- **Exempt `projection` in the isolation test.** Rejected. The test has no allowlist *by design*, it is a
  Gate A invariant that survived five review rounds, and this repo's own rule is that an exception keyed
  on matched text is repo-wide — never added to excuse one caller.
- **Give `projection` its own canonicaliser.** Rejected. That is a fifth serializer of the same shape,
  and duplication of a hashing rule is what this package has already paid several review rounds for.

### Consequence

The projection digest is coupled to `document_bytes`' emit style, not to `canonical`'s. If that emitter's
style ever changes, every existing owner approval stops matching and the approval gate reopens. That
direction is **fail-safe** — the owner re-approves — which is what makes the coupling acceptable.

Two properties the plan asserts of this digest are true of `digest_of` and **false** of the route now
used, and must not be restated: `document_bytes` runs with `sort_keys=False` and performs **no NFC
normalisation**. Determinism survives for a different reason than the plan gives — the digest is taken
over the **parsed model**, whose field order is pydantic declaration order, so reflowing the input YAML
cannot move it. Lacking NFC, a composed and a decomposed spelling digest differently, which is strictly
*stricter* for an approval gate than the plan intended.

### What generalises

- **A symbol-existence check cannot find a prohibition.** D-160's mechanical pass confirmed every
  imported name resolves with the signature used, and was right. The defect was not a missing symbol
  but a test asserting that a present, correct, public symbol must not be imported. Preflighting a plan
  needs a pass that asks *what forbids this*, not only *does this exist* — grep the test suite for the
  module you are about to import, not just the module's own definition.
- **Count the walls before trusting a section that names them.** A Global Constraints section titled
  "The import wall — non-negotiable" enumerating two assertions reads as exhaustive and is not. The
  guarded resources here are `profile_bundle.canonical`, `boardwatch.tailor`, `boardwatch.store` and
  `boardwatch.profile_bundle`, spread across two test files. Enumerate from the tests, the way the
  catalog rule requires deriving from the emitter's own constants.
- **An escalation that refuses to guess is worth more than a workaround.** The implementer stopped at
  `NEEDS_CONTEXT` with the two fixes it could see named as architecture decisions outside its scope,
  and proved the attribution with `git stash` rather than asserting it. Either fix it might have chosen
  unilaterally would have been wrong.

## D-162 — A fourth import wall guards the CLI command module against the store, found only by tripping it

### Context

D-161 recorded a third import wall and drew the lesson that a symbol-existence check cannot find a
prohibition. Executing Task 10 of the projection plan — registering `approve-projection` on the
`profile-bundle` command group — turned a **fourth** wall red:
`tests/profile_bundle/test_profile_bundle_cli.py:174::test_the_command_module_imports_no_store_module`
asserts that `src/boardwatch/cli/profile_bundle_cmd.py` imports **no store module** at all.

Wiring the new command in pulled `boardwatch.store` into that module's transitive closure, through a
pre-existing chain in the already-shipped `pool.py` and `shell.py`. The implementer fixed it with the
same `TYPE_CHECKING` / deferred-import idiom `cli/app.py` already uses for the identical problem.

This is the third consecutive instance of the same shape. The plan's Global Constraints enumerated
**two** wall assertions, both in `test_profile_bundle_tailor_isolation.py`. D-161 found a third in
`test_profile_bundle_hash_isolation.py`. This is a fourth, in a **third file**, guarding a **different
resource** — the store, not the serializer. Each was discovered by tripping it, never by reading the plan,
the spec, or the preflight.

### Decision

The wall is respected rather than relaxed: the projection CLI defers its imports. `pool.py` and `shell.py`
keep their store dependency, which is legitimate for library code; only the command module is constrained.

**The preflight rule from D-161 is widened, and this is the durable part:** before wiring a new module
into an existing package, **grep `tests/` for what constrains that package's imports** — not just for the
symbol you intend to use. The walls are not enumerated in any document; each is a test in a different
file, guarding a different resource, and the only reliable inventory is the test suite itself.

### Alternatives rejected

- **Allowlisting the new import.** These guards have no allowlist mechanism by design, and adding one
  would defeat the point — the constraint exists so a command module cannot quietly acquire a database
  dependency.
- **Registering the command on a different group to dodge the guard.** That would scatter the projection
  commands across two groups for a reason no user could infer.

## D-163 — The plan's four candidate scorers are two behavioural families, and none survives both probes

### Context

D-158 stopped the projection spec's review loop after two rounds each picked a scorer and a probe
falsified both, and ruled the winner would be chosen by measurement rather than by argument. Task 21 then
built all four candidates behind one interface.

Before execution the controller ruled (R12) that the task's two probe tests, which each `xfail` exactly
one named scorer, were arithmetically wrong — **two** scorers fail each probe — and required a derived
`KNOWN_BIASES` table plus a non-vacuity assertion that *at least one scorer survives both probes*.

**That non-vacuity assertion was itself false, and the implementer proved it before writing any test.**
Recomputed independently by the reviewer, by running the fixtures through the real `SCORERS`:

| Probe | Fails | Survives |
|---|---|---|
| 1 — focused (2 distinct / 2.0 mean) vs shallow (4 / 1.0) | `total_distinct`, `coverage_then_density` | `mean_per_bullet`, `mean_top_k` |
| 2 — comprehensive (9 / 1.5) vs focused (2 / 2.0) | `mean_per_bullet`, `mean_top_k` | `total_distinct`, `coverage_then_density` |

The intersection is **empty**, and empty *by construction*: `coverage_then_density`'s primary key **is**
`total_distinct`, so it inherits probe 1's loss; and `mean_top_k` degenerates into `mean_per_bullet`
whenever an entry has at most `MAX_BULLETS_PER_ENTRY` bullets — that constant is **6**
(`tailor/plan.py:48`) and the comprehensive fixture has exactly 6. Neither probe ties, so neither partner
can escape the other's failure.

### Decision

The four candidates are recorded as **two behavioural families**, not four independent options, and the
weaker-but-true non-vacuity check ships instead: no *individual* probe may mark every scorer biased, plus
a separate explicitly-labelled test pinning the real finding that no scorer escapes both biases. No
formula was weakened and no fixture was bent — either would have destroyed the probes' meaning.

**This strengthens D-158 rather than softening it.** The four candidates cannot break their own tie under
these probes, which makes **Slice PM (Task 20), the owner-labeled selection matrix, the only arbiter that
exists.** Task 22's rank-agreement harness is built and reports agreement; it asserts no winner. Task 23's
selection takes a scorer as a parameter and chooses none.

### Alternatives rejected

- **Adjusting a fixture so some scorer survives both probes.** It would have satisfied the assertion and
  proved nothing; the probes exist to expose bias, not to be passed.
- **Adding a fifth scorer designed to survive both.** Inventing a candidate to satisfy a test written
  before the measurement is exactly the ordering D-158 ruled against.

## D-164 — Where the closed `ProjectionIssue` catalog is extended, and where a foreign error may escape

### Context

The projection package raises typed violations from a closed `StrEnum` catalog. Three separate tasks hit
the same question: a dependency raises its own exception type — wrap it into a `ProjectionIssue`, or let
it escape? The answers initially diverged, and two of the controller's rulings contradicted each other
until a reviewer drew the line properly.

### Decision

**Infra-level failures from foundational helpers escape unwrapped.** `DocumentEmitError` from the YAML
writer and `BundlePathError` from the path validator are not outcomes a caller branches on; they mean a
primitive broke. `declaration.py` and `stamp.py` let both through, and that stands.

**First-class business outcomes of a documented entry point get a typed member.** "Posting is closed",
"posting has no current version" and "the bundle has never been promoted" are routine, expected states
that a caller is expected to handle. These gained `POSTING_NOT_OPEN`, `POSTING_NO_CURRENT_VERSION` and
`BUNDLE_UNREADABLE`.

The deciding test is **not** which package the exception came from — it is whether the condition is a
routine outcome of the function's contract or a primitive failing underneath it. `pool.py` made the
inconsistency visible: it gave `MISSING_PROJECTION_APPROVAL` a typed member while letting `SelectionError`
escape, though both are prerequisite-not-met states of the same function, and its own docstring claimed
every refusal was a `ProjectionError`.

**The catalog is closed against silent invention, not against deliberate extension.** Its only repo-wide
test asserts a **floor** (`len >= 12`), not an exact count and not an exhaustive mapping — which is what
makes a recorded extension cheap while still failing if the catalog is emptied. `errors.py`'s own
docstring already said an un-enumerated condition is "a defect in this file, not a new bucket."

One residual is carried deliberately: **`projection_candidate` still propagates `SelectionError`
unwrapped.** It is safe only because its single caller's except tuple is `(ProjectionError,
ProfileBundleError)`. Any new caller catching `ProjectionError` alone must also catch `ProfileBundleError`
or call `project_pool`, which wraps.

### Alternatives rejected

- **Wrapping everything.** It would bury genuine primitive failures behind a projection-shaped code and
  add a catalog member per dependency error, which is invention by another name.
- **Wrapping nothing, for consistency.** That was the initial instinct and it produced a module whose
  docstring was false on a reachable path.
- **Splitting `BUNDLE_UNREADABLE` into two members** mirroring the posting split. `SelectionError` escapes
  that call site under **7 distinct** underlying `IssueCode`s, so a two-way split would still have needed
  a third bucket or would have mis-filed corruption as "not promoted."

## D-165 — A consent control gets one definition, because the rationale for copying it was false

### Context

Task 10 added `profile-bundle approve-projection`, the owner-confirmation gate for a projection. Its
brief instructed the executor to **copy** four units from `cli/profile_bundle_cmd.py` —
`CONFIRMATION_WORD`, `ApprovalTerminal`, `_StandardTerminal`, `approval_terminal` — and both the brief
and the resulting module docstring justified the copy as *forced* by the one-way registration import
direction: `profile_bundle_cmd` imports `projection_cmd` to register the command, so importing back
would close a cycle.

The task review accepted the code but flagged the duplication, and falsified the justification:
`cli/context.py` is an existing **shared leaf module** imported by roughly 17 command modules with no
cycle. A third leaf imported by *both* sides satisfies the one-way constraint exactly.

### Decision

**The four units live once, in `cli/_approval.py`, imported by both command modules.** The plan's
instruction to copy rested on a false premise and therefore did not bind.

The deciding factor is *what* was being duplicated. This is the owner-confirmation gate — the control
that decides whether a résumé may carry the literal words a person approved. **Silent drift between two
copies of a consent control is its worst failure mode**: a later fix to the `(AttributeError, ValueError)`
catch, or to the stderr-versus-stdout choice, would land in one copy and no test would notice.

Two `import sys` re-imports and one `_StandardTerminal` re-import remain in the command modules behind
`# noqa: F401`, because existing tests monkeypatch `sys.stdin`/`sys.stdout` **by module attribute**.
These are a real constraint, not defensive caution — removing either raises `AttributeError` at
monkeypatch time, loudly. They are documented inline and must not be "tidied" without re-reading those
tests.

### Alternatives rejected

- **Keeping the copy, as the brief instructed.** A plan instruction whose stated reason is false is not
  authority; and the review rubric independently calls verbatim duplication of a logic block a defect.
- **Importing from `profile_bundle_cmd` into `projection_cmd`.** This genuinely would close the cycle.
  The leaf avoids it; the premise was never that no cycle existed, only that a *third* module was never
  considered.
- **Parameterising one command to serve both.** The two approvals stamp different artifacts against
  different digests; merging them would couple two owner gates to save one file.

## D-166 — Projection maps its issues onto the bundle's catalog at the boundary, rather than inverting the dependency

### Context

`profile-bundle project` joins a command family whose machine surface is a seven-key JSON envelope built
from `profile_bundle`'s closed `IssueCode` catalog, with `tier_of` asserted **total** by a test. Projection
has its own closed catalog, `ProjectionIssue`, with roughly 30 members. The task brief named two routes and
forbade doing both: extend `IssueCode` with projection's diagnostics, or keep `ProjectionIssue` and map at
the boundary.

### Decision

**Map at the boundary.** Teaching `profile_bundle.errors` projection's 30 members would invert the
dependency direction permanently — projection depends on the bundle, never the reverse — and
`ProjectionIssue` is already the authoritative catalog for projection's business outcomes (D-164).

The fold adds exactly **one** new bundle code, `PROJECTION_REFUSED`, in `STATE_REFUSAL_CODES` only so
tier disjointness and totality hold; reuses `STALE_APPROVAL_STAMP` for the stale-bundle case, which is
genuinely the same failure shape (an approval's bound content diverged); and carries the specific
projection member in `details.projection_issue`, so the machine surface loses no information.

**One residual is carried and named: the fold site is also the sanitization site.** The family owes "no
absolute path in any diagnostic," and which `ProjectionIssue` members can leak a path is knowledge that
lives in the mapping function. That set is now derived by a test rather than restated in a docstring — a
docstring enumerating audited files was already wrong once on this branch, having omitted `shell.py`.

### Alternatives rejected

- **Extending `IssueCode` with projection's vocabulary.** Permanent dependency inversion to save one
  mapping function.
- **Emitting `ProjectionIssue` values directly in the envelope.** `tier_of` is total over `IssueCode`;
  a foreign value would have no tier and no exit code.
- **A generic "internal error" for every projection refusal.** It would collapse ~30 distinguishable
  owner-actionable states into one, which is the opposite of a typed catalog's purpose.

## D-167 — A projection approval binds the bundle it was made against, and the check is unconditional

### Context

`approve-projection` justifies itself by showing the owner every declared entry **with its templates
already resolved against the bundle's current revision** — approving means having seen the literal words
a résumé would carry. But `ProjectionStamp` bound only `projection_digest`, which hashes the *declaration*
alone. So when the bundle's current revision changed, the resolved words changed and nothing noticed: the
owner's approval silently came to cover words they never saw. The bundle package already carries
`STALE_APPROVAL_STAMP` for exactly this class of problem; projection had no equivalent.

This surfaced while resolving an underdetermined `--check` flag on `profile-bundle project`. Because only
`project_pool` yields a `Resume` for the serializer, and `project_pool` enforces the owner gate, a
declaration edit **already** exits non-zero without the flag — so under the narrow reading `--check` was
redundant with the gate and could never fire.

### Decision

**`ProjectionStamp` and `ProjectionCandidate` carry `bundle_digest`; `approve-projection` records it; and
`project_pool` compares it unconditionally.** A stale approval refuses on every path, including
`resume project`, which is the command that actually writes a résumé.

**`--check` is deleted.** The first ruling gave it the bundle comparison as a job; the whole-branch review
showed that was the wrong knob, and it was right. *An opt-in flag on a consent control is the wrong shape
regardless of what it checks — the owner who forgets the flag is exactly the owner the gate exists for.*
Once the binding is unconditional the flag has no remaining behaviour, and this repo's standing rule is
that **a check that cannot fire is deleted, because a never-firing check reads as coverage.** The same
principle that rejected the narrow reading also rejects the flag; applying it to one and not the other was
the inconsistency.

`read_stamp` is guarded so a stamp that fails to validate against the current schema becomes a typed
diagnostic with a valid envelope rather than a traceback with empty stdout — the migration case, since
this change made a persisted field required.

**Carried, and not closed by this decision: the shell's *content* is bound by nothing.** `shell_source` is
hashed as a `Path` — the filename, not the bytes — and the shell lives in `config_dir`, outside the bundle.
Editing it changes the projected `header`/`education` with no digest movement. Blast radius is small
because the renderer never reads either field (D-156), so only the serialized YAML sees it; `shell.py`'s
docstring now states this plainly rather than claiming a coverage nothing provides.

### Alternatives rejected

- **Leaving the binding opt-in behind `--check`.** Ships a consent control the owner must remember to ask
  for.
- **Persisting an artifact for `--check` to diff against.** Invents a filename and staleness semantics for
  a review command, colliding with the artifacts `resume project` already writes.
- **Reusing the bundle's `ApprovalStamp`.** It is schema-bound with a closed one-member `ApprovedVia`, and
  a repo-wide substring scan enforces a two-caller limit on its writer (a preflight correction).
- **Doing nothing, since no real stamps exist yet.** True today and irrelevant: the defect is in the
  approval's meaning, not in the migration cost.

## D-168 — Stage 2's scorer is a required parameter with no default, because the plan is forbidden to pick one

### Context

Selection needs a scorer. D-163 established that all four candidates are falsified by one probe or the
other and are really **two behavioural families** — `coverage_then_density`'s primary key *is*
`total_distinct`, and `mean_top_k` degenerates into `mean_per_bullet` at or below `MAX_BULLETS_PER_ENTRY`
(6). No scorer survives both probes, so the four cannot break their own tie, and the owner-labeled matrix
is the only arbiter that exists. It does not exist yet.

### Decision

**`select` takes an `EntryScorer` as a required parameter with no default, and `resume project` takes a
required `--scorer` whose choices are derived from `SCORERS` at call time.** An unknown name is a typed
refusal, not a traceback. The derivation is pinned by a test that monkeypatches the mapping and asserts the
*old* name disappears, plus a non-vacuity assertion.

A **default** would silently pick the winner the plan is explicitly forbidden to pick — the choice would
survive as a default long after everyone forgot it was arbitrary. Requiring the operator to name one keeps
the choice visible until measurement rules.

A hardcoded choice list is banned for a reason this repo already paid for: a hardcoded catalog once passed
98 tests while covering 5 of 13 documents. A runtime-derived `click.Choice` is also wrong, because it
snapshots the mapping at import.

### Alternatives rejected

- **Defaulting to any of the four.** Picks a winner by fiat, which is the entire thing D-158 and D-163
  forbid.
- **Defaulting to the alphabetically first.** The mapping is ordered alphabetically *precisely so that its
  order carries no ranking signal*; reading a winner off it inverts that intent.
- **Blocking Stage 2 until the matrix exists.** The code is independently useful and testable; only the
  *selection* of a scorer was ever blocked, never the machinery.

## D-169 — A plan can ship an artifact no task consumes, and only a whole-branch lens sees it

### Context

Task 15 built `projection/persona_preflight.py` — a guard that refuses a persona declaring `entries`
before any selection runs, so the owner gets a diagnosis instead of a crash deep inside `apply_persona`.
It was built correctly and reviewed clean. Task 19 built the command that would need it. **Neither brief
mentioned wiring one to the other.**

The result passed 22 task reviews: a shipped safety mechanism called from **no production code path** —
grepping for callers returned exactly one hit, a *comment* — while a CLI docstring asserted it was
"reached by `resume_project`". The failure it existed to prevent remained fully reachable.

### Decision

The guard is wired at its cheapest refusal point — in `resume_project`, after `config_dir` resolves and
before `project_pool`, needing neither bundle nor database — and the false docstring corrected. More
durably:

**Every task's output needs a named consumer, and the plan should say which task provides it.** A task
that produces a module, and a later task that should call it, are two tasks whose *seam* no task-scoped
review can see — each is individually complete and correct. This is cheap to check when writing a plan
and expensive to find afterwards.

This is the third instance of the same lesson in this program: **a closed review loop is evidence about
the slices reviewed, not about the subsystem being defect-free.** Two silent-success defects previously
surfaced after a loop closed, in code six reviews and four gates had passed.

It also sharpens the standing rule: *a check that cannot fire is deleted.* The rule is usually applied to
a condition that can never be true. This case is the other shape — **a check nobody calls** — and it reads
as coverage just as convincingly.

### Alternatives rejected

- **Deleting the module.** Legitimate under the same rule, and it was the explicit fallback if wiring
  proved unwanted. The guard is cheap, needs neither bundle nor database, and prevents a real crash — so
  wiring beat deleting.
- **Wiring it inside `project_pool`.** Persona data is presentation-lens configuration; the pool is
  JD-blind bundle resolution. The CLI is the right seam.
- **Treating it as an implementer error.** No implementer was told to wire it, and no task review could
  have seen the gap. It is a plan defect and is recorded as one.

---

## D-170 — `profile-bundle import` writes the ledger and nothing else, and derives no disposition

**Context.** Gate B could not start. `{config_dir}/career-profile` does not exist, and the import
machinery that shipped with Gate A — `enumerators.py` plus `imports.py` — had **no CLI command** and no
production caller at all: `enumerate_source`, `build_candidate_package` and `build_source_ledger` were
reachable only from tests. `docs/profile-bundle-authoring.md` §16 told the owner to hand-author
`imports/source-ledger.yaml`, which for the live `resume.yaml` means transcribing 81 deterministic
records and their digests by hand. Nothing in the repo could put a real career into a bundle.

**Choice.** A fifteenth command, `profile-bundle import --draft --source [--from PATH]`, that enumerates
one owner-approved source into the draft's `imports/source-ledger.yaml` — **and writes no other
document**.

Four rulings inside that, each of which could reasonably have gone the other way:

1. **Candidates and exclusions stay owner-authored.** `build_candidate_package` needs *proposals*, and
   nothing produces them; `imports.py`'s own docstring says the module never "performs Gate B
   extraction". So the command cannot import a candidate, and every enumerated record a draft does not
   otherwise account for is `review_required`. **A first import of a real source therefore reports every
   record as undispositioned, and that is the correct first state** — dispositioning them is the Gate B
   work, not a defect to be designed away.
2. **Disposition is read from the draft, never carried over from the previous ledger.**
   `build_source_ledger` derives it from the candidates and exclusions present, so an exclusion the owner
   wrote survives a re-import. The failure this avoids is silent: a command that rebuilt rows from the
   enumerator alone would reset every decision the owner had made, and the ledger would still validate,
   because `review_required` is a legal disposition.
3. **The approved scope is reused from the ledger, and a first import may only derive `complete_file`.**
   §18 prices widening a scope at a new owner approval because the scope is a property of the ledger, not
   of the enumerator. A `selected_sections` source's locators are the owner's statement of what may be
   read, so deriving them would be the command approving its own input.
4. **The splice replaces a source's block in place.** The ledger is a document an owner reads; a
   re-import that moved one source to the end would produce a diff across two sources for a change that
   touched one.

The sidecar resolves the personal path. `--from` names the document, or `local-sources.yaml` maps the
source to a machine-local root and the document is found beneath it at the source's `portable_locator`.
§18's rule that the importer must not resolve a personal path binds the **adapter**, which still only
ever sees bytes; the sidecar is the file designed to hold exactly that path, excluded from every revision
and both digests.

**A consequence worth stating, because it is easy to expect otherwise.** `import` exits **0** on a draft
full of undispositioned records. `import_record_undispositioned` is a *completeness* finding, and the
revalidation every authoring command ends with does not run that tier. The count is therefore carried in
the command's own result (`counts_by_disposition`, every member present including the zeroes), and
`validate --completeness` is what reports them individually. Both paths are asserted, against each other,
because a component's self-report is not verification.

### Alternatives rejected

- **Having `import` also write candidates.** It cannot: no extractor exists. Inventing one inside a CLI
  command would have been the largest unrequested design decision available.
- **Defaulting the disposition to `imported` for records that look substantive.** This is the whole
  failure mode the ledger exists to prevent — a denominator whose numerator was filled in by a heuristic.
- **Deriving a `selected_sections` scope from the document's headings.** Rejected under §18: it converts
  an owner approval into a parse.
- **Rebuilding the whole ledger from every declared source on each run.** Simpler, and wrong: sources
  without a resolvable local path would silently vanish from the denominator.

### How it was verified

Thirteen tests, and three mutations run against a **copy** of `src`, not the worktree. Mutation 1
(derive dispositions with no exclusions) and mutation 3 (ignore the ledger's approved scope) were each
killed by the assertion stating that test's own claim. **Mutation 2 (replace the in-place splice with
remove-and-append) initially SURVIVED** — once a source is last in the ledger the two are identical, so
no arrangement of the existing tests could reach the branch. A second source was added purely so a
re-import could be exercised against a source that is not last; it kills the mutation on the sources-order
assertion. The green mutation row was treated as a finding, which is the only reason the gap was closed.

One test was also reordered after a mutation: the disposition-preservation test asserted the exit code
before the counts, and under mutation 1 it tripped on a *consequential* validation error instead of on
the disposition it is named for. Asserting which assertion fires is what surfaced that.

---

## D-171 — A CI-only failure was a lazy-import race in typer, not an OS difference and not a regression

**2026-08-14 · Session opened to re-check run 31774640890, whose outcome the previous session left
genuinely unknown. It had failed. Fixed before any other work, per the session's own instruction.**

### Context

Run 31774640890 (`64cf63c`) failed on **all three ubuntu test jobs** while all three macOS jobs passed.
One test: `tests/pipeline/test_top_show.py::test_top_help_lists_the_new_flag`, which asserts
`"--new" in result.stdout` over a `--help` render. The previous session recorded the run as UNKNOWN
because the `gh` REST quota was exhausted mid-watch; the quota was irrelevant — **GraphQL was untouched
(4,999 of 5,000 points) and answered immediately.** A rate-limited REST endpoint is not a missing
measurement when a second route exists.

### What was actually wrong

`typer/rich_utils.py` bakes a module constant:

```
FORCE_TERMINAL = True if getenv("GITHUB_ACTIONS") or getenv("FORCE_COLOR") or getenv("PY_COLORS") else None
```

and passes it as `force_terminal=` to the console it builds for every help render. Forced on, rich's
`ReprHighlighter` splits an option name across escape codes, so the literal substring `--new` never
appears even though the flag renders perfectly. `tests/conftest.py` already popped `FORCE_COLOR` and
`TTY_COMPATIBLE` at import for precisely this class of problem — it was missing `GITHUB_ACTIONS` and
`PY_COLORS`, **two of typer's three triggers.** The normalisation was two-thirds complete.

### The choice

Pop `GITHUB_ACTIONS` and `PY_COLORS` in the same conftest import-time block, and pin the outcome with
`typer.rich_utils.FORCE_TERMINAL is not True` rather than pinning the environment. Nothing in `src/`
reads `GITHUB_ACTIONS`, so this takes no behaviour away, and a dozen test modules already
`monkeypatch.delenv` it one fixture at a time for the same reason.

**Why the assertion is on the outcome, not the env:** every reference to `rich_utils` inside typer is a
**function-local** import (`typer/core.py:978`, `:1207`). The constant therefore bakes at the *first help
render in that xdist worker*, under whatever environment exists at that instant — not at collection. So
the conftest pop works only because it precedes the first render, an ordering nothing else pins, and one
rich never needed because it reads `FORCE_COLOR` live in `is_terminal`. That asymmetry is the trap.

### Two claims this retracts

- **It is not OS-determined**, though three-for-three on each side looks conclusive. The same
  `3.12-ubuntu` job **failed at `64cf63c` and passed at `2324a49`** over identical tests. It is a race
  whose outcome follows xdist sharding; a dozen fixtures had been winning it by luck.
- **It is not a regression from `e3f8fa9`.** That commit added 13 tests, which changed sharding, which
  changed which test imports `rich_utils` first. The code it "broke" was untouched and green three
  commits earlier.

### The hypothesis that was falsified first

The panel renders at 80 columns and the failure looked exactly like the width class already recorded in
this log. **Measured: at width 80, `--new` is present.** Four `COLUMNS=` runs all passed and all rendered
identically — because `COLUMNS` was a no-op, which is the trap that class is already known for. A fix
shipped on that hypothesis would have changed nothing and claimed the failure.

### How it was verified

`GITHUB_ACTIONS=true uv run pytest -k top_help_lists` reproduces the CI assertion **byte-for-byte**
locally, so the diagnosis rests on a reproduction rather than on log reading. Under a mutation removing
the two pops, both the original test and the new pinning test fail — the new one **on its own named
assertion** (`assert True is not True` on `FORCE_TERMINAL`), not on a pre-existing assertion firing
first. Gate green four ways at the fixed tree: exit 0, all five stage banners, 6232 passed / 4 xfailed,
coverage 95.76%.

**A green CI run alone could not have verified this fix**, because the bug passed by luck before. What
makes a green run meaningful now is the pinning test, which fails in any job where the constant baked
true.

### Corrections recorded with it

- **`STANDING-FACTS.md` claimed `docs/superpowers/` is untracked. It is tracked** — 12 files under
  `git ls-files`. The untracked directory is the dotfile `.superpowers/`, excluded via
  `.git/info/exclude`. The bullet conflated two paths; the copy-into-a-worktree instruction it carried
  applies only to the dotfile.
- **`STATE.md` carried `main is at 64cf63c`**, one commit stale on arrival — the exact failure its own
  header forbids. Removed rather than updated.
- **`All checks passed!` is the `generalization` stage's banner, not the gate's.** It appears while
  pytest is still running, so on its own it reads as a green gate roughly four minutes early. The
  captured exit code is the only one of the four checks that cannot be read early.

---

## D-172 — Gate B is met at a promoted revision, and the extraction mapping lives inside the bundle

**2026-08-14 · Mit's two rulings on the candidate-extraction design, taken after an external review returned
NOT READY on revision 1. Also discharges the entry D-170 ruling 1's narrowing has owed since the write-path
call.**

### Context

`docs/superpowers/specs/2026-08-14-gate-b-candidate-extraction-design.md` reached revision 2 with four of six
review findings applied and two left open because they were the owner's. Both are now decided.

### Ruling 1 — Gate B is met at a promoted revision, not at a clean draft

`build_source_ledger` derives `imported` from the mere presence of a candidate (`imports.py:430-452`). Under
the one-step write (below), a deterministic extractor that emits something for every mapped locator drives
`review_required` to **zero by itself**. Read off that number, Gate B measures extractor coverage and calls it
owner disposition — the review's first blocker, and the risk named when the two-step was recommended and
declined.

**Chosen:** bind Gate B to a promoted revision. `approve` already runs on a controlling terminal, binds to the
draft's exact content digest, and `promote` is refused without a matching stamp — so machine-written
candidates already require the owner's sign-off before becoming a revision. The gate now points at the thing
that requires it. `import_record_undispositioned` remains what *lists* the work, not what certifies it.

**Rejected: a fourth disposition, or an acceptance flag on the ledger record.** Disposition is derived by
construction; an authored acceptance field would give the ledger a second source of truth about the one
number Gate B is measured against — exactly what `record_count` is deliberately not a field to avoid
(`models/imports.py:15-16`).

**Carried, and not resolved by this:** in a draft a record still flips to `imported` on candidate presence
alone; what changed is that a draft's counts are a working state rather than the gate. And approval means "I
approve this exact content", never "I read all 81 candidates" — no bundle mechanism proves reading, for any
document. Raising that bar means sampling (audit N, require all N correct), which is a separate and heavier
decision.

### Ruling 2 — the locator→predicate mapping is a `SourceSpec` field, inside the bundle

Something must say "a bullet under an `experience` entry means `employment.accomplishment`". CLAUDE.md
requires it be versioned **data**, not code, or the taxonomy is what fails to port to a second user — the one
thing job-apps proved empirically. No such mapping exists today: `predicate_id` appears in exactly two source
files and `enumerators.py` never references it.

**Chosen:** a field on `SourceSpec` in `policy/sources.yaml`, so the mapping is part of the approved,
digest-bound content.

**Rejected: package data beside the starter catalog.** It is versioned with *boardwatch* rather than with the
bundle, so upgrading the program would silently change the rules an existing revision was built under, and
that revision could no longer be explained from the bundle alone. A content-addressed store whose revisions
cannot account for how they were produced has given up the property it exists for.

**Costs, both accepted:** a `schema_version` bump owing a migration, affordable precisely because Gate A is
not declared met and the grammar is still allowed to change (`docs/profile-bundle-authoring.md:24-26`); and
**no new document**, so the closed grammar is untouched.

### Ruling 3 — D-170 ruling 1 is narrowed, not overturned

D-170 said candidates and exclusions stay owner-authored. Its stated reason was *"It cannot: no extractor
exists."* That reason expires the moment one does. The extractor writes `imports/candidates.yaml` directly
(no separate acceptance file), which is the owner's call; what survives from D-170 unchanged is that identity
is derived and never proposed, disposition is derived and never carried over, scope is reused and never
widened, and the splice is in place. Exclusions remain owner-authored.

### What the review changed that was not a decision

Recorded here because the spec's own revision table will eventually be compressed: revision 1 claimed a skill
candidate carries an evidenced-versus-`incidental` context. **It cannot** — `CandidateRecord` has no
`usage_context`, subject, verification state, evidence or surfaces; those are fact-layer properties. The
claim was written in a session that had already read the model contradicting it. Revision 1 also left
`review_required` as a quarantine with no drain, gave Slice A a gate proving the catalog was *present* rather
than *audited*, and justified widening a predicate contract by "it revives a dead guard" — unsound, since a
dead check can equally mean an obsolete rule.

Also found and left open (§9.5): **a candidate's `skill_ref` is not referentially validated at all.** The
import validators check identity, naming, scope, locator shape, dispositions and enumeration; none checks a
candidate's `skill_id` against the skill inventory. Referential validation covers canonical facts only.

---

## D-173 — Gate B gets a mechanical predicate, the drain gets a digest-bound carrier, and the mapping's carrier is questioned

**2026-08-14 · Round 2 of the external review on the candidate-extraction design returned NOT READY with the
loop told to CONTINUE. Amends D-172. Revision 4 of the spec.**

### Why an amendment so soon

D-172 was taken an hour earlier. Round 2 confirmed its *boundary* is mechanically real — approval is
digest-bound, promotion refuses content without a matching stamp (`promotion.py:555`,
`profile_bundle_cmd.py:997`), and promotion runs full validation and refuses blockers (`promotion.py:862`), so
**a promoted revision cannot contain `review_required` records.** What it lacked was a falsifiable predicate,
and the fix round introduced a false claim while removing one.

### Ruling 1 — Gate B's predicate, stated mechanically

Met, for a source, when: a **selected promoted revision** exists; **full validation is clean**; the ledger's
**declared denominator for that source is 81**; **`review_required` is zero**; the **approval and candidate
digest binding validates**; and the **extraction report accounts for every non-`imported` record**.

**Revision-level approval is reported as a BOOLEAN.** Revision 2's "records the owner has accepted" is
**withdrawn** — approval is one digest decision over a whole revision, not a per-record quantity, and Slice B
defined no such count. Inventing it while fixing a conflation was the same error one layer over.

### Ruling 2 — the drain's carrier is a bundle document, not a command report

Revision 2 put the `review_required` reason in a regenerated `--json` report. That is visibility, not durable
state: it sits outside the digest-bound revision and cannot later prove why *that promoted draft* left a
record unresolved.

**Chosen: `imports/extraction-report.yaml`, inside the bundle, keyed by `source_record_id`, bound into the
candidate digest.** Validated as exactly one closed reason per `review_required` record and none for an
`imported` or `excluded` one. **This is not a second source of truth about disposition** — disposition stays
derived solely from candidates and exclusions (`imports.py:430-452`); the report explains only the resulting
unresolved state, and the validator ties it to that state rather than letting it assert one.

Accepted cost: a **new document**, so the closed grammar widens. Affordable only because §6.2's change bumps
`schema_version` anyway and the two ride in one bump.

### Ruling 3 — extraction is authoritative per source, and stale candidates retire

Revision 2 claimed re-extraction is safe "by construction, the same IDs". **False**: identity includes
predicate and canonicalized value, so corrected material yields a *different* `candidate_id` while
`merge_candidate_packages` is append-only (`imports.py:359+`) — the superseded candidate would survive and a
record could name both.

`extract` **rebuilds the candidate set for the source it extracts**, replacing rather than merging, preserving
`occurrences` for surviving IDs, and touching no other source. Justified by grain rather than convenience:
D-170 ruling 4 already replaces a source's ledger block **in place**; occurrence lineage records the same
assertion seen again, not a withdrawn one; and `merge_candidate_packages` has **no production caller**
(verified — `src/` holds only its definition), so this defines the extraction path without changing live
behaviour.

### Ruling 4 — grounding is against a parsed field, not bytes

`EnumeratedSourceRecord` carries a parsed, adapter-normalised `atomic_value` and a digest over it
(`enumerators.py:309-321`) — **no raw substrate and no byte range.** So "the record's own bytes" was wrong;
the guarantee is that `original_display_value` occurs in the parsed atomic field the rule names, never in
`str(atomic_value)`. Extending enumeration to retain bytes was **rejected**: it would change the Gate A
adapter contract and the digest basis to serve a check the parsed field already supports.

### Proposed, and needing the owner's assent — the mapping's carrier

**D-172 ruling 2's location (inside the bundle) stands. Its carrier — a `SourceSpec` field — is questioned.**
`SourceSpec` is keyed per *source* (`source_id`, `source_kind`, `portable_locator`; three fields,
`policy.py:356+`), while a mapping is inherently per *adapter*: every source of kind `boardwatch_resume`
shares one locator grammar. A per-source field duplicates one mapping across every source of a kind — the
trap `SourceLedgerSource`'s own docstring names, *"two homes for one field is two chances to disagree"* — and
has no seeding point, since `init` declares no sources, so a fresh bundle would have no mapping and reproduce
the empty-catalog defect one layer over.

**Proposed instead: `policy/extraction-mappings.yaml`, keyed by adapter id, seeded non-empty at `init` from a
builtin**, exactly the `policy/secret-scan.yaml` pattern (`drafts.py:321-329`). Content in the bundle, so
reproducibility holds; seeded, so extraction works out of the box; one home per mapping; and package-level
builtins make the catalog-reachability invariant evaluable, which the `SourceSpec` shape could not.

### Two claims corrected, both introduced by the previous fix round

- **The schema bump is feasible but was understated.** `migrate_bundle` loads the selected revision through
  *current* document models before transforming (`migrations.py:83`), and parsing is not
  schema-version-dispatched (`validation/context.py:130`), so new required content makes v1 fail parsing
  before the 1→2 transform runs. The plan owes a restricted raw-v1 loader or version-aware dispatch, the v1
  fixture, and migration that creates a v2 draft **without rewriting v1 revisions**.
- **Slice A's invariant 4 was incoherent** — a package-wide catalog checked against a bundle-owned mapping.
  Seeding a builtin mapping makes both artifacts package-level and the check well-defined.

### The loop's own state

Round 1: 2 blockers, 3 majors, 1 minor. Round 2: 1 partially resolved blocker, 1 new blocker, 5 majors, 2
resolved. **Severity did not fall**, which is the signature of an underspecified design rather than a
converging loop — hence revision 4 specifies the mapping's data contract (§6.2a) rather than only its
location. The line held against the review: the *model and interpreter rules* belong in the design; the
`dates` string grammar and skill-id derivation are plan tasks, because writing them into a design is how a
spec acquires false precision. **The predicate audit is task 1 of the plan and the plan stops after it** for a
replan checkpoint — the review's condition, accepted.

---

## D-174 — The extraction mapping's carrier is `policy/extraction-mappings.yaml`, not a `SourceSpec` field

**2026-08-14 · Mit's assent to the departure D-173 proposed. Amends D-172 ruling 2's carrier. Recorded as its
own entry because D-173 states the change as *proposed, pending assent*, and a later session reading only
D-173 would not know it was granted.**

D-172 ruling 2 decided the mapping lives **inside the bundle**, versioned with it, so a revision can explain
how it was produced. **That location is unchanged and was never in question.** Only the carrier moves.

**Chosen: `policy/extraction-mappings.yaml`, keyed by adapter id, seeded non-empty at `init` from a versioned
builtin** — the `policy/secret-scan.yaml` pattern (`drafts.py:321-329`), which writes catalog *content* into
the bundle rather than a reference to whatever the installed program currently means by a name.

**Rejected: the `SourceSpec` field D-172 named**, for three reasons that are about shape rather than taste:

1. **Wrong key.** `SourceSpec` is per *source* (`source_id`, `source_kind`, `portable_locator` — three fields,
   `policy.py:356+`); a mapping is per *adapter*, since every source of kind `boardwatch_resume` shares one
   locator grammar. A per-source field duplicates one mapping across every source of a kind, which is exactly
   the trap `SourceLedgerSource`'s docstring names — *"two homes for one field is two chances to disagree."*
2. **No seeding point.** `init` declares no sources, so a per-source field cannot be seeded, and a fresh
   bundle would hold no mapping — reproducing D-172's own empty-catalog defect one layer up.
3. **It made a gate uncheckable.** Slice A's catalog-reachability invariant compares predicates a mapping
   names against the catalog. With the mapping bundle-owned and the catalog package-wide there is nothing to
   compare; with a package-level builtin mapping both artifacts are package-level and the check is
   well-defined.

Cost, accepted: this is the **second** new document in the v2 bump (with `imports/extraction-report.yaml`,
D-173 ruling 2), so the closed grammar widens by two. Affordable only because both ride one bump and Gate A is
not declared met (`docs/profile-bundle-authoring.md:24-26`). The migration mechanics D-173 records still apply
and are still owed by the plan.

**Also settled with it:** review round 3 runs, **scoped** to whether revision 4's four corrections hold and
whether §6.2a's mapping contract is sufficient to plan from — not a fresh sweep. The reason to run it at all
is that four of round 2's findings were defects revision 2's *own fixes* introduced, so revision 4 should not
be assumed clean; the reason to scope it is that re-sweeping settled ground re-derives instead of converging.

## D-175 — Review round 3 outcome: 7 findings, all accepted; the schema bump needs a real migrator, not a raw-v1 loader

**2026-08-14 · The scoped round-3 review (D-174) ran externally and returned NOT READY / CONTINUE.** Its two
questions and the in-session triage: revision 4's corrections **b, c, d** hold and the promotion-slice
bounding (§6.8) is sufficient — but **seven defects remain, and all seven were accepted**, each verified
against the code rather than by deference. Rounds 1–2 were 12/12 accepted; round 3 is 7/7. Three of the seven
are defects revision 4's *own fixes* introduced — the same signature as round 2.

**The seven, each with the check that confirmed it:**

1. **Predicate 6 (§7a) contradicts §6.3a.** §6.3a validates a report reason for every `review_required`
   record and *none* for `imported`/`excluded`; §7a predicate 6 demanded the report account for every
   *non-`imported`* record, which includes `excluded`. Fix: predicate 6 reads "every `review_required`
   record." A rev-4-introduced defect.
2. **§6.7 overstated the schema-bump requirement — the ruling reversal.** §6.7 (and D-173's migration
   mechanics, and STATE) claimed the plan "owes a restricted raw-v1 loader or version-aware dispatch."
   **False for this bump.** `load_documents` parses only files that are present and does not reject
   declared-but-absent documents (`validation/context.py:95`, docstring `:102-104`); the missing-file check
   is validation-layer (`validation/structural.py:88`), which `migrate_bundle` never runs. Since v2 only
   *adds* two documents and changes no v1 model, a v1 tree parses fine under v2 models. The real residual is
   narrower: `migrate_bundle` (`migrations.py:83`) is a **stub** returning `already_current` and needs a real
   transform that seeds the two new documents and bumps the manifest, and the supported-versions set widens
   to {1,2}. **Narrows D-173's migration-mechanics claim.**
3.–7. **§6.2a is not yet sufficient to plan from.** Bullets: `Bullet` carries no `kind` (`tailor/model.py:12-16`);
   the entry-kind predicate split needs a cross-record lookup the contract cannot express, and the rule shape
   has no `condition` member. Entry metadata: one locator must emit four candidates, which the "ties are a
   validation error" rule forbids — multi-output emission is undefined. Precedence: "longest-literal-prefix,
   then declaration order" makes a genuine tie impossible, so "ties are an error" is a dead branch —
   incoherent with the multi-output need. Education: the record is one scalar (`enumerators.py:511`) but yields
   three agent-extracted predicates, which §6.2a's "constructed from the named field" cannot model. Header:
   distinguishing `header/1` from the email at `header/2` needs a literal non-head segment, but the stated
   grammar ("a literal head, `*` for one segment") does not grant one, and its citation to `emits_locator`
   (`enumerators.py:463-490`, a per-head shape validator) is loose.

**Choice: revision 5 is authored in a FRESH context, not by patching in place.** Fix rounds inherit the
author's blind spot, and three of seven are rev-4-introduced. **No new owner decision** — every fix sits
inside D-170/172/173/174. Two internal design forks revision 5 decides: how a bullet reaches its parent
entry's `kind`, and whether the agent lane gets its own proposal contract (education out of §6.2a's
deterministic contract) — neither is owner policy.

**Alternatives rejected:** the author patches in place (blind-spot risk, and the §6.2a fix is model-level, not
a patch); rejecting any finding (all seven verified in code).

**Consequence:** a round-4 review is owed; revision 5 does not get to declare itself clean. STATE's
"restricted raw-v1 loader or version-aware dispatch" line is corrected to match this entry.

## D-176 — Review round 4 outcome: 4 blocking findings accepted; the kind→subject→predicate relation gets modelled once

**2026-08-14 · The scoped round-4 review of revision 5 returned NOT READY / CONTINUE with four blocking
findings, all accepted after verification against code. Three of the four were defects revision 5's own fixes
introduced — the same signature as rounds 2 and 3.** Count is falling (12 → 7 → 4) but severity is not, and
two of the four are one root cause.

**The four:**

1. **Entry metadata mapped as employment even for projects.** Revision 5's multi-output rule sent every
   `entries/*/metadata` record to `employment.organization/title/date_range` unconditionally. Those admit
   only an `employment` subject (`legal_subject_kinds: [employment]`,
   `examples/comprehensive/policy/predicates.yaml:215,241,270`); a `kind: project` entry needs
   `project.summary/start_date/end_date` (`[project]`, `:380,410,443`), and `semantic.py:149-164` raises
   `PREDICATE_SUBJECT_KIND_ILLEGAL` otherwise — so a project entry's candidates fail promotion and Gate B
   predicate 2 can never hold. Rev-5-introduced: rev 5 split *bullets* by kind but left *metadata* unsplit.
2. **The bullet `condition` assumed a closed `kind` domain the code does not enforce.** Revision 5 asserted
   `kind` is `"experience" | "project"`, but `Entry.kind` is an open `str` (`tailor/model.py:38`, default
   only). An entry with any other kind matches the bullet locator, fires neither condition, and hits **no
   closed report reason** in §6.3a. **Owner decision (Mit, 2026-08-14): a typed failure with a drain — a new
   `unsupported_entry_kind` report reason — NOT closing `Entry.kind` to an enum**, because that would change
   the Gate A adapter/résumé model, which is out of bounds. Consistent with "closed catalogs; out-of-catalog
   is a failure, never a silent bucket."
3. **§6.7's residual omitted advancing the schema head.** Dropping the raw-v1-loader mandate (D-175) was
   right, but "transform + widen `SUPPORTED_SCHEMA_VERSIONS` to {1,2}" is two of three: `CURRENT_SCHEMA_VERSION`
   is still `1` (`schema.py:80`) and is written into every fresh `init` manifest (`drafts.py` `_initial_manifest`),
   so a fresh bundle stays v1 unless it is bumped to **2**. D-174 requires `init` to seed the new mapping
   document, so `init` must be born v2. **Extends D-175's residual from two items to three.**
4. **§6.2a claimed §8 holds a proposal contract it does not.** §8 is "declared, not decomposed" — it cites
   the rewrite handshake only as precedent, with no education request/response model, multiplicity,
   typed-value, or ingest command. Fix: §6.2a says the education lane's contract is *deferred to Slice C*
   (Slice C stays undesigned — education is last), and §7a states plainly that **Gate B cannot be met until
   Slice C ships**, since predicate 4 requires zero `review_required` and the 2 education records stay
   `free_text_deferred`.

**Root cause of 1 and 2: entry `kind` → subject kind → legal predicate was never modelled, only patched per
case.** Revision 6 introduces it as a first-class, catalog-grounded relation from which *both* metadata and
bullet predicates derive, rather than adding more per-case rules — the fix that stops the loop reproducing the
same class.

**Choice: revision 6 authored in a FRESH context with the root-cause framing** (rounds 3 and 4 each showed the
prior fix reintroduces the class). **Alternatives rejected:** patching findings 1–4 as four independent rules
(invites a round-5 third instance); the author patching in place; rejecting any finding (all four verified in
code). **Consequence:** a round-5 review is owed; revision 6 does not declare itself clean.

## D-177 — Review round 5: the rule interface is under-designed; revision 7 redesigns it completely, not by patch

**2026-08-14 · Round 5 of revision 6 returned NOT READY / CONTINUE with five blocking findings, all accepted
after verification against code. The count rose (4 → 5) and the external reviewer named one class twice:
"modelled in prose, unrepresentable in the rule interface."** This is the decision that the incremental
prose-revision strategy is not converging, and changes it.

**The five:**

1. **Project identity mapped to the wrong field — fact corruption, not approximation.** `latex.py:110-122`
   displays a project's `title` as its name and *ignores* `heading` (a fallback only when `title is None`,
   `tailor/model.py:35-38`; fixture `heading="ignored", title="Knowledge Forge"`). Revision 6 mapped
   `title`→nothing and `heading`→`project.summary` — backwards. Fix: add a `project.name` predicate (a
   **Slice-A catalog-audit item**), map `title`→`project.name`, `heading` only as a null-fallback.
2. **The "one model" bullet lookup is not representable.** The rule is a flat 6-tuple with a *scalar*
   `predicate`; rev 6's prose says the bullet predicate "is the contribution cell of the model," but no rule
   element expresses that lookup. So implementation must hard-code or materialise bespoke per-kind rules — the
   recurrence rev 6 claimed to kill. The consolidation was documentation, not interface.
3. **Project dates cannot yield two values.** `YearMonthValue` holds one scalar (`facts.py:100`); two rules
   sharing `value_from:dates`/`value_type:year_month` cannot pick start vs end. Confirmed from round 4; the
   reviewer is right it **must** change the §6.2a interface (a component selector), not stay a plan task.
4. **Rev-6's new Gate-B/Slice-C claim is incomplete and imprecise (rev-6-introduced).** `header/2` (the email)
   is `no_predicate_exists` with no exclusion → `review_required` (`imports.py:422-427`) → a Gate-B blocker
   (`validation/imports.py:507`), a third unresolved record Slice C never touches; and owner exclusions could
   clear the 2 education records without Slice C. So "Gate B cannot be met until Slice C" is both incomplete
   and overstated.
5. **§6.7 understates the v2 doc-add work.** The version trio (real transform, `SUPPORTED={1,2}`,
   `CURRENT_SCHEMA_VERSION=2`) is correct but adding two documents also needs `DocumentKind` members +
   `FIXED_DOCUMENTS` paths (`layout.py:38,74`), `DOCUMENT_MODELS` registrations (`schema.py:89`), and
   `_empty_documents` seeds (`drafts.py:321`).

**Root cause: the rule interface `{locator_pattern, predicate, value_from, value_type, display_from,
condition}` has been designed reactively.** Each round surfaces an operation the flat schema cannot express
(predicate-from-a-kind-model; a value-component selector; field coalesce for the project name), the author
patches prose or adds one element, and the next round finds the next unrepresentable case. Findings 2 and 3
are that class explicitly.

**Choice (Mit, 2026-08-14): revision 7 is a COMPLETE rule-interface redesign, authored fresh** — enumerate the
closed set of extraction operations, give each a schema element (predicate: literal or model reference; value:
field, parsed-component selector, or field coalesce; condition), make the kind→subject→predicate model a real
object rules reference rather than a prose table, and **prove completeness** by expressing every bucket as
concrete rules with nothing left to Python. That completeness proof is the anti-loop check. Plus finding 1's
`project.name` mapping (audit-sanctioned) and the finding-4/5 corrections. **The declarative in-bundle premise
(D-172/D-174) is kept, not reopened** — the fix is an expressive schema, not moving logic into code.

**Alternatives rejected:** reconsidering the declarative-mapping premise (Mit kept it); patching the five in
prose (invites a round-6 sixth instance of the same class); rejecting any finding (all five verified in code).

**Consequence:** a round-6 review is owed; revision 7 does not declare itself clean. **Exit criterion set now:
if round 6 again returns a same-class "unrepresentable in the rule interface" blocker, stop the prose-revision
loop and reconsider the strategy (premise, or fold interface design into the build plan's task-1 replan).**

*(Superseded before round 6 ran — see D-178: the exit criterion was met early and the loop was paused for a build.)*

## D-178 — Stop the spec-review loop as the gate to building; de-risk the rule interface with a thin TDD slice

**2026-08-14 · Mit's call, after five external review rounds (D-172…D-177) all returned NOT READY with
findings 12 → 7 → 4 → 5 — not converging.** Every finding was verified real, but the recurring class — round 5
named it twice, *"modelled in prose, unrepresentable in the rule interface"* — is precisely the question a
spec is worst at settling and executable code is best at. Five rounds produced **zero lines of production
code**; the headline number is still **0 applications**; job-apps carries Mit's résumés daily, so the
opportunity cost of pausing review is low and the cost of a tenth round is real. This program's rigor is
executable (`make check`, the generalization checker, the keystone invariant), not prose review.

**Choice: stop treating "zero external-review findings" as the gate to build.** Revision 7 — the completed
interface redesign — becomes the design we build **from**, not a review target. De-risk the interface with a
thin TDD slice:
1. the **Task-1 predicate audit** (§9, with its replan checkpoint) — settles the starter catalog,
   `project.name`, and the `incidental` admission as real rows;
2. the **rule-interface schema + the two easiest buckets** (`skill-groups` → `technology.used`, `header/1` →
   `person.professional_name`) end-to-end against the 81 real records, proving candidates land, **counted
   through the ledger, not a self-report**;
3. let the **hard buckets** (project dates, bullet-by-kind) settle their interface needs *in code*, gated by
   `make check` + the keystone invariant.

**"No production code until the review closes" (the plan's prior condition) is reversed.**

**Alternatives rejected:** more review rounds (the death-spiral risk); reopening the declarative-mapping
premise (kept — D-172/D-174; the fix is an expressive schema proven by code, not moving logic into code);
building the whole extractor at once (thin-slice-first surfaces interface gaps in ~200 lines, not ~2,000).

**Consequence:** the review loop is paused (D-177's round-6 expectation superseded). Building begins. The
spec is directional input; **where it and the code disagree, the code and its tests win.**

## D-179 — The Task-1 predicate audit: seed the audited starter catalog, and roster three dead verification bases

**2026-08-14 · the §9 Task-1 replan checkpoint of the extraction build (D-178).** Slice A seeds the builtin
starter predicate catalog into every fresh bundle, exactly as `init` already seeds the secret-scan ruleset —
because an empty predicate vocabulary leaves every enumerated record `review_required` forever, a denominator
the bundle can never disposition (`build_candidate_package` raises on an out-of-catalog predicate). The builtin
(`resources/predicate-catalog-v1.yaml`, content-addressed, read at seed time by `predicate_catalog.builtin_catalog`)
is the 41-row comprehensive-example catalog, audited row by row (`docs/profile-bundle-predicate-catalog-audit.md`),
plus the two sanctioned changes: `technology.used` admits `incidental` (a familiarity-level skill must stay
effective yet never ground verification — §5.1, and `effective.py`'s guard becomes reachable), and a new
`project.name` predicate (string, card. one; `render/latex.py` shows `title` is a project's displayed name).

**The audit found what §5.2 invariant 1 missed.** The spec claimed invariant 1 ("every `VerificationBasis`
member admitted by ≥1 predicate") fails today *only* because of `incidental`, and that admitting `incidental`
repairs it. **False:** `measured`, `secondary_only` and `multiple_sources` are admitted by **0 of 42**
predicates — a fact-only résumé starter establishes nothing by measurement or multi-source corroboration — so
the invariant as written could never pass.

**Choice (Mit, 2026-08-14): roster the three bases with a reason** (`NOT_ADMITTED_VERIFICATION_BASES`) and make
invariant 1 "admitted OR rostered", mirroring §5.2 invariant 4's `not_reachable_from_builtin_mappings`
precedent. A NEW accidental orphan still fails; a rostered basis a predicate later admits must leave the roster
(a second test enforces disjointness).

**Alternatives rejected:** dropping `VerificationBasis` from invariant 1 (silently loses the dead-basis
bug-catch); adding metric/multi-source predicates a résumé starter has no bucket for.

**Scope of this slice (Option A).** The seeded catalog is a **pure schema-v1 change** — `policy/predicates.yaml`
already exists as a v1 document, so only its seed content changed; **no schema bump.** §5.2 invariants 1, 2 and
5 ship as mechanical tests; **invariant 3 (§5.1 behavioural grounding) and invariant 4 (catalog↔builtin-mapping
reachability) are OWED** — the first needs a builtin-catalog-backed grounding context (the synthetic fixture
uses the un-amended example catalog), the second needs the builtin extraction mapping Slice B seeds. The
example catalog is left un-amended so its comprehensive-bundle tests stay pinned; **builtin and example are now
independent artifacts.** No record reaches `imported` yet — that is Slice B (the mapping + the extract wiring).

## D-180 — The skill-id derivation scheme, and the easy buckets proven in code

**2026-08-14 · Slice B, library level (D-178 build).** The two literal-rule buckets now produce candidates end
to end at the library level (`extraction_mapping.py`'s builtin `boardwatch-resume-v1` rules → `extract_proposals`
→ `build_candidate_package` against the *seeded* catalog): `header/1` → `person.professional_name` (string), and
each skill item → `technology.used` (skill_ref). No bundle document, no CLI, no schema bump — the interface is
settled in code (D-178) before it is persisted (schema v2) and wired to a command.

**`technology.used` is `skill_ref`, not string**, so the skill bucket needs a `skill_id` derived from the item
string — a plan task the spec deferred. **Choice (Mit, 2026-08-14): a human-readable slug `skill.<slug>`**
(lowercase; non-alphanumerics → hyphens, stripped and collapsed: `Python`→`skill.python`,
`React.js`→`skill.react-js`, `C++`→`skill.c`), **and keep the verbatim item as `original_display_value`.** Lossy
on purpose — `C++` and `C#` both slug to `skill.c` — which is safe here because identity is content-addressed
(each item is its own record, so a slug collision does not merge candidates), the real name survives in the
display value, and referential validation of the id against the inventory is the promotion slice's job (§6.4),
not this layer's.

**Alternatives rejected:** a sha-based opaque id (a candidate id would tell you nothing, and two spellings of
one skill would relate invisibly); a bare slug with no preserved display (loses the real name on a lossy slug).

**Consequence:** 59 of the 81 records (1 name + 58 skills) now have a proven candidate path. The remaining
buckets (entry metadata, bullets, project dates, education, `header/2`) need the `entry_kind_model` / agent lane
and are next. The builtin mapping is deliberately incomplete until they land, so §5.2 invariant 4 stays owed.

## D-181 — Gate B extraction ships end to end: the `entry_kind_model` interpreter, the schema-v2 bump, the `extract` command, and the first records that reach `imported`

**2026-08-14 · Slice B complete (D-178 build).** The deterministic extraction lane is built, integrated, and
suite-green (`make check` EXIT=0, 6294 passed). Against the live `resume.yaml` on a fresh v2 bundle, counted
through a separate ledger parse: **78 of 81 records reach `imported`** (header/1 name, 58 skill items, 6 entry
metadata records → 19 entry-head candidates with the 13 bullets, i.e. every metadata and bullet record), and
**3 stay `review_required`** with exactly the designed drain — 2 education lines `free_text_deferred`, the email
`no_predicate_exists`. **This is the first time any record has ever reached `imported` (was 0, always).**

What shipped, in four commits on `gate-b-extraction-slice-a` (`160ad63`, `e8831ef`, `d341d8a`, `7df6cd9`…`ae1e34c`):
1. **The `entry_kind_model` interpreter** (`extraction.py`): the closed operation set O1–O6 as code — model-routed
   metadata/bullet rules resolving predicate+value through one `entry_kind_model` object (so a `project` entry can
   never land an `employment.*` predicate — the round-5 misrouting, now a *caught class* via
   `validate_mapping_against_catalog`), O3b range-component selection, O3c coalesce (`project.name` = title else
   heading), O6 parent-kind lookup for bullets, the résumé `dates` grammar, and typed per-record drain reasons.
2. **Two new bundle documents**: `imports/extraction-report.yaml` (the §6.3a drain — one closed reason per
   `review_required` record, none for others) and `policy/extraction-mappings.yaml` (the persisted mapping, seeded
   NON-EMPTY from the builtin; a round-trip converter reconstructs the interpreter dataclasses exactly).
3. **The schema-v2 bump**: both documents registered in every required site (DocumentKind / FIXED_DOCUMENTS /
   DOCUMENT_MODELS / schema-root / DocumentModel-union / `_empty_documents` seed); the comprehensive example
   regenerated to v2; `career-profile.schema.json` regenerated and re-pinned in SHIPPED_DATA.
4. **`profile-bundle extract --draft NAME --source SOURCE_ID`**: enumerates the source, runs the interpreter
   against the seeded mapping+catalog, writes candidates + report + re-derived ledger (multi-write →
   `PARTIAL_EDIT_APPLIED`, D-137), authoritative per-source (§6.6, `rebuild_source_candidates`), inside the store
   import wall.

**Departure from D-176, taken deliberately: `SUPPORTED_SCHEMA_VERSIONS` stays `{2}`, not `{1,2}`, and no `1 → 2`
migration transform is shipped.** No v1 bundle exists yet, so a v1 tree is refused fail-safe
(`unsupported_schema_version`, exit 3) rather than migrated by a transform whose only exerciser would be a
fabricated previous-version fixture — the same argument `schema.py`'s own bootstrap docstring makes against a
v0→v1 migration, and Mit's "minimum code, no speculative abstraction" default. Widening to `{1,2}` is now the
additive change owed when a real v1 bundle first needs upgrading; the tripwire
`test_a_previous_schema_fixture_and_a_forward_migration_are_owed_at_v2` still pins that obligation.

**Two seams found by the live run and the branch review, both owed (not this slice's to close):**
- **The builtin catalog and the example catalog are independent (D-179), so the *example* bundle is not a valid
  extraction host for a résumé *with projects*** — its `predicates.yaml` lacks `project.name`, so `extract`
  against it fails `unknown predicate`. A fresh `init` bundle seeds the builtin catalog+mapping consistently and
  is the correct host. Anyone extracting into a hand-authored bundle must ensure its catalog admits the mapping's
  predicates.
- **`validate_extraction_report` is not yet wired into the aggregate `validate_imports` lane** (the report's
  drain invariant is enforced only when a caller invokes it directly, as `extract` does; promotion-time
  enforcement is owed, and wiring it forces the example's empty report to explain its own `review_required`
  records — a ripple to do carefully). And a **degenerate** all-empty-metadata record of a supported kind would
  drain as `no_mapping_for_locator` (a real résumé never emits one — headings are authored).

**Alternatives rejected:** building the `1→2` migration + a v1 fixture now (speculative — no v1 bundle exists);
extracting into the comprehensive example (catalog mismatch on `project.name`); widening `Entry.kind` to a closed
enum to make `unsupported_entry_kind` a type error (out of bounds — touches the Gate A résumé model; the drain
reason is the escape hatch instead).

## D-182 — The §6.8 promotion slice: candidates become entities, facts, and grounded skills — deterministic, owner-mediated, one-shot

**2026-08-14 · Slice B follow-on, built as a thin TDD slice (D-178 doctrine).** `extract` lands candidates and
stops; a record reaches `imported` on candidates alone. Promotion (`profile-bundle promote-candidates --draft
NAME --source SOURCE_ID`) is the only place those candidates become the renderable graph — the `FactRecord`s,
the entities they attach to, and the `SkillRecord`s whose `skill_id` is a real reference (§6.4). Against the live
`resume.yaml` on a fresh v2 bundle, counted through a separate disk parse: **6 entities (3 employment, 3 project),
47 facts, 10 grounded skills, 4 categories** — the first time any candidate has become a fact/skill. New module
`candidate_promotion.py` (import-wall pure — no `store`, no `tailor`), orchestrated by `authoring.promote_candidates`
and the CLI handler mirroring `extract`.

**The fork §6.8 left open, decided by Mit (owner ruling, 2026-08-14): grounded + owner-mediated.** `technology.used`
is illegal on `person`, so a flat skills-list item has no legal entity subject; a skill renders only through an
*effective* `technology.used` fact bound to an employment/project/education/course/publication entity, and an
effective fact needs owner-attested evidence + approval. Synthesising those automatically would be fabrication —
the one thing the architecture exists to prevent. So:
1. **The one grounded skill→entity signal a résumé carries is a bullet's authored `tech_tags`.** A skill named
   exactly by a bullet's `tech_tags` gets a `technology.used` fact on that bullet's entry entity (10 of 58 skills
   on Mit's résumé; the other 48 are pure familiarity with no entity and stay candidates — **not** an error, and
   **not** a blanket "every candidate `skill_id` resolves" check, which would force 48 invalid `SkillRecord`s;
   §6.4's owed check is satisfied at the *fact* layer, where `referential.py` already resolves `skill_ref`).
   Sanctioned as a new binding mechanism beyond §6.1's mapping.
2. **Every fact is born `unresolved`, `evidence_ids=()`, no fabricated attestation.** `verification_basis`,
   `usage_context`, and `allowed_surfaces` are each chosen deterministically from the predicate's own legal set
   (so `PREDICATE_*_ILLEGAL` can never fire); `import_lineage` points at the grounding locator. A skill's
   `allowed_surfaces` is `()` until the owner confirms its facts. The owner's confirm/attest/approve step is what
   promotes and renders — proven by a test that makes one fact effective and sees the skill reach a grounded,
   résumé-surfaced, validating state.
3. **Skill categories are derived from the résumé's skill-group labels** and written into
   `policy/skill-categories.yaml` (empty at `init`), because a `SkillRecord.category` must resolve and the label
   is the faithful, grounded taxonomy. Owner-editable before promotion.
4. **One-shot: promotion refuses (`duplicate_record_id`) if the draft already holds entities or skills**, rather
   than clobbering the owner's edits with a deterministic rebuild. Re-promotion means clearing first.

Entity/fact/skill IDs are deterministic and catalog-driven: entity kind is the singleton intersection of the
entry's candidate predicates' `legal_subject_kinds` (no hard-coding); `entity_id = <kind>.<entry-slug>`; employment
status derives from date openness, project status from whether an end date is present.

**Alternatives rejected:** rendering flat familiarity skills by inventing a synthetic host entity (fabrication of
data with no grounding); an authoritative rebuild that preserves owner edits (more code, deferred — one-shot is the
minimum that is safe); a candidate-level `skill_id`-resolves check (would reject the 48 legitimate familiarity
candidates); promoting `header/1`'s `person.professional_name` (its subject is the `person` entity from
`facts/identity.yaml`, Mit's prerequisite — deferred until identity exists). Not built here: the actual LaTeX
emission (projection-v1's tested domain, D-165…170), the aggregate `validate_extraction_report` wiring, and the
education agent lane (Slice C).

## D-183 — Two owed Gate B gates ship: §5.2 invariant 4 reachability, and the drain reconciliation wired at the completeness tier, not validity

**Context.** STATE's "Owed next" carried two gate items from D-181/D-182: §5.2 audit invariant 4
(catalog↔mapping reachability), now evaluable because Slice B seeds a builtin mapping (D-181); and wiring the
pure `validate_extraction_report` into an aggregate lane (it had a `TODO(schema-v2)` and was only called
directly by `extract`). Both are gate-hardening, no new user surface. Mit approved building them on the branch
before any merge review (2026-08-14).

**Choice 1 — invariant 4's reverse direction ships beside its forward half.** The forward half already
existed (`validate_mapping_against_catalog` proves every predicate the builtin mapping names is catalog-legal;
`test_the_builtin_mapping_is_catalog_legal`). The reverse half is new: `named_predicates(mapping)` enumerates
the predicates a mapping's producing rules name (literal rules + every `entry_kind_model` slot; deferrals name
none), and `NOT_REACHABLE_FROM_BUILTIN_MAPPINGS` rosters the **31** catalog predicates the `boardwatch-resume-v1`
mapping does not reach, each with a reason (career surfaces with no résumé bucket, education's agent-lane
predicates, the two application-only work-auth facts). Three gate tests pin it to exactly those 31: coverage
(every catalog predicate named or rostered), and two honesty checks (the roster names no reached predicate, and
only catalog predicates). This turns "a new predicate nobody wires" — §2.1's defect one layer over — into a
caught class instead of a row sitting silently present.

**Choice 2 — the drain reconciliation is a COMPLETENESS check, not a validity one. This corrects STATE's
wording ("the aggregate `validate_imports` lane") — the repo wins.** Wiring the whole `validate_extraction_report`
into `validate_imports` (validity) broke the `import` command: `import` ends by revalidating at the *validity*
tier (`_with_revalidation` → `validate_bundle` with no `completeness`), and a freshly imported, not-yet-extracted
bundle legitimately has `review_required` records and an empty report, so every one was flagged and `import`
exited 1. That is wrong: a post-import bundle is **valid-but-incomplete** — its records are the
`_undispositioned_records` *completeness* blocker (`test_the_seven_records_are_undispositioned_to_the_completeness_tier`).
So the reconciliation lives in `imports_completeness`, beside `_undispositioned_records`, over a new
`ctx.index.extraction_report` accessor (the `imports/extraction-report.yaml` document kind was already registered
in `layout.py`; only the index accessor was missing). This matches the invariant's nature — "every quarantined
record carries a closed, auditable reason" is a property of a *finished* extraction — and it binds where Gate B
is measured (the completeness tier), which is exactly STATE's stated purpose ("enforces the drain invariant at
promotion"). The two completeness findings are **not** redundant: `_undispositioned_records` says "unresolved,"
the reconciliation says "unresolved AND unexplained," and they diverge the moment the report explains a drained
record (post-extract, a drained `review_required` record is undispositioned but explained). An absent report is
read as empty, the same fail-safe as an absent exclusions document.

**Ripple, as STATE anticipated.** The comprehensive example bundle's one `review_required` record
(`_root/paragraph-1`, the deliberate `import_record_undispositioned` demonstrator) had an empty report; under the
new check its drain was unexplained. Fixed by adding a `no_mapping_for_locator` entry (a root paragraph no rule
maps) to `examples/comprehensive/imports/extraction-report.yaml`, and bumping that file's `_BUNDLE_EXAMPLE_PINS`
sha256 in `tools/generalization/allowlists.py`. The example manifest's `approved_candidate_digest` is `''`, so no
digest match broke; the packaging inventory count (35) is unchanged.

**Alternatives rejected:** the literal STATE wording (validity lane) — breaks `import`, and a post-import bundle
is genuinely valid; splitting arms 2&3 (report must not lie about dispositions) into validity while arm 1 goes to
completeness — the two report-lie arms are vacuous post-import anyway, so keeping the pure function whole in one
lane is simpler and loses nothing; dropping arm 1 as redundant with `_undispositioned_records` — rejected once the
two were shown to diverge post-extract, so the drain's auditability is real added coverage. Invariant 3 (§5.1's
behavioural grounding assertion against the builtin catalog) stays owed — it needs a builtin-catalog-backed
grounding `ValidationContext`, a heavier fixture than this session built.

## D-184 — The Gate B merge review: the catalog check was never wired, and is now the gate D-181 said it was

**2026-08-14 · the pre-merge whole-branch review of `gate-b-extraction-slice-a` (21 commits, +6366).**
Mit's standing preference is a fresh-context Opus-5 whole-branch review for a checkpoint this size. That
review was attempted as four concurrent reviewers and **aborted deliberately**: each inherited the global
throughput doctrine ("fan out 3–5 wide by default") and began spawning its own subagents, turning four
reviewers into sixteen against a usage ceiling. Killed at ~2 minutes, before any had produced findings; the
repo was untouched (read-only agents, clean tree, unchanged head). **A reviewer prompt for a big diff must
forbid further delegation explicitly** — the doctrine is inherited, and a review is not the place for it.
The review was then done in-session by one reviewer. Scope is therefore narrower than four lenses and is
recorded honestly below.

**Finding 1 (blocker, fixed here): `validate_mapping_against_catalog` had no production call site.** It was
referenced only from two test files and a docstring. `extract_source` loaded the mapping from
`policy/extraction-mappings.yaml` — **owner-editable bundle data** — and ran it unvalidated. Proven by
repro: a `project` entry kind whose slot names `employment.organization` extracted **clean, exit 0, 5 records
imported**, landing a fact on a subject the catalog does not admit. This **falsified D-181's claim** that the
revision-5 misrouting is "a *caught class* via `validate_mapping_against_catalog`" — it was a caught class
for the builtin, in a unit test, and nowhere else. The claim is not retracted but *made true*: `_checked_mapping`
now runs the check between `_mapping_for` and `run_extraction`, and `ExtractionMappingError` carries the
`IssueCode` its violation *is*, typed at the raise site (`UNKNOWN_PREDICATE`,
`PREDICATE_SUBJECT_KIND_ILLEGAL`, `MODEL_VALIDATION_ERROR`), so the refusal classifies no message text.

**The check is scoped by `require_known_predicates=False` at the host call site, and that is the load-bearing
sub-decision.** Validating the *whole* mapping up front refused the comprehensive example bundle, whose
catalog is a deliberate **subset** of the builtin's (D-179) — five existing tests went red. A host catalog
legitimately need not carry every predicate a builtin mapping names; a rule that cannot fire there is not this
gate's business, and typing a proposal refuses downstream if a record ever reaches one. **The misrouting arm —
a predicate the catalog *does* carry, on a subject kind it does not admit — is enforced either way**, because
that is the guarantee §6.2a exists to make. The standalone function keeps its strict default for the
builtin-vs-builtin gate tests.

**Also closed here, same gate:** the mapping's non-predicate fields are now checked against their closed
vocabularies (`value_type`, `group`, `kind_source`, `emits_group`, `value_selector`, and a deferral's
`reason`, the last read from the interpreter's own `DRAIN_REASONS` rather than a restatement of them).
Unchecked, an owner-authored `value_type` reached `_build_value` and surfaced as an unhandled
`NotImplementedError` **partway through a multi-write command** — a crash where a refusal belongs.

**Two tests pin it, and both were confirmed to fail without the fix** (mutation run against a `src` copy, never
the worktree): unfixed, the misrouting test's `extract` returns exit 0 with `imported: 5`.

**Finding 2 (owed, Mit's design call): a partial emission silently drops fields with no drain entry.**
`run_extraction` records a failure only `if not produced`, so a record that emits *some* candidates and fails
others discards the reason entirely and reaches `imported`. Proven: an `experience` metadata record with
`dates: "Summer 2024"` emits organization, title and location, silently omits `employment.date_range`, and
`failures == ()`. **This means "78 of 81 imported" cannot by itself mean 78 records fully extracted.** It is a
leak in the CLAUDE.md sense — the quarantine has no drain because the record was never quarantined. **Not
fixed here because it is not a bug with an obvious fix:** the report model attaches reasons only to
`review_required` records, so a partial loss on an `imported` record has nowhere to go without a design
change. **Verified latent, not live:** all six of Mit's live entries parse, so D-181's 78/81 and D-182's
6/47/10 are not hiding losses today.

**Finding 3 (owed, latent): a skill-id slug collision silently merges two skills.**
`candidate_promotion.py`'s `skill_id_to_display` / `skill_id_to_label` are bare dict assignments, so `C++` and
`C#` — which `_derive_skill_id` both slugs to `skill.c` (D-180, lossy on purpose) — collapse to one
`SkillRecord` whose `canonical_name` is whichever came last, and the other skill leaves the graph with no
diagnostic. **Verified latent:** Mit's 58 skill items yield 58 distinct slugs. It is a multi-tenancy defect,
not a Mit defect, which is exactly the class CLAUDE.md says fails first when a second user appears.

**Finding 4 (fixed here): `CHANGELOG.md` did not describe the branch, and asserted something false.** It
enumerated *"These fifteen commands"* — `extract` and `promote-candidates` made it seventeen (verified against
`profile-bundle --help`, not counted by hand). Both now have entries.

**Reviewed clean:** the extract→promote seam, the mapping round-trip converters, D-183's completeness-lane
wiring (the two findings do diverge as claimed), §5.2 invariant 4's arithmetic (42 = 11 named + 31 rostered,
recomputed), and `gitleaks` over all 21 commits.

**Not covered by this review, and owed if it is ever wanted:** a test-honesty/mutation audit of the ~1700 new
test lines, the generalization sha pins, a schema-v2 registration-site sweep, and a multi-tenancy sweep of
`src/`. **Alternatives rejected:** merging on `make check` + `gitleaks` alone (breaks the standing rule that a
merge needs *both* confident and reviewed); fixing findings 2 and 3 in this session (both need an owner
design call, and neither is live); relaxing the misrouting arm to keep the example bundle strict-clean
(would discard the one guarantee the gate exists for).

## D-185 — boardwatch's first promoted revision: the bundle becomes a real résumé source, and Gate B's remaining nine are evidence, not code

**2026-08-14 · the first revision this program has ever cut.** `revision 1`,
`sha256:9d8a202dcd97c2220a37214191af1e68594432a3af941cee802a6f5876d465f0`, authorised by
`approval-stamp.000001` binding candidate `sha256:05c1c1b9…`. Verified through a path other than the command's
self-report: `revisions/sha256-9d8a202d…` exists on disk, `CURRENT` names revision 1 with the matching digest,
and `validate` against the *selected revision* (no `--draft`) is **0 error, 0 blocker**.

**The whole lane ran against Mit's live `resume.yaml`, on the real bundle at `{config_dir}/career-profile`** —
not a scratch tree, which every previous Gate B measurement used. `init` → `facts/identity.yaml` →
`policy/sources.yaml` → `import` (**exit 0**, the first clean import ever — the `missing_required_file` finding
that D-181 recorded is gone) → `extract` (**78 of 81 imported**) → `promote-candidates` (**6 entities, 47 facts,
10 skills**, recounted by a separate disk parse). D-181's and D-182's numbers reproduce exactly on the real
bundle.

**Gate B is NOT mechanically MET, and what remains is evidence, not code: 9 `missing_review_state` blockers.**
The catalog sorts the 47 promoted facts into three bases, and only one of them is owner-satisfiable:
**38 `owner_attested`** (titles, dates, locations, accomplishments, project names, all 14 `technology.used`),
**3 `private_document_verified`** (`employment.organization` — an employer record to say where he worked), and
**6 `repository_verified`** (`project.contribution` — whose *only* legal basis is repository-verified, so the
owner's word is inadmissible there by construction). The 38 were confirmed against one
`owner_attestation` evidence record; the 9 stay `unresolved` pending documents Mit has to produce.

**Evidence is mandatory, proven not assumed.** Flipping all 47 to `owner_confirmed` while citing nothing yielded
**47 `evidence_contract_unmet` errors** — run on a throwaway copy of the bundle, not the real one. So a decided
review state is not an edit; it is a citation.

**The three drained records were excluded with the accurate reason rather than the convenient one.** `header/2`
(the contact line) is `no_candidate_assertion` — genuinely true, the catalog has no contact predicate and the
same channels are typed contacts on the person entity. The two education lines are `owner_excluded`, which costs
an `approve_source_record_exclusion` sub-approval each, rather than `no_candidate_assertion`, which would have
been free and false: an education line *does* assert institution and credential; it is deferred to the agent
lane (Slice C), not meaningless. `review_required` is now **0**.

**Correction — authoring `facts/identity.yaml` does NOT unblock `person.professional_name`, and STATE said it
would. The repo wins.** `candidate_promotion.py:180` skips `header/*` unconditionally and never reads
identity.yaml; the comment there says person facts need the file, but no code consults it. Identity fixed the
*exit codes* (import/extract/promote-candidates now exit 0), not the name fact. The count is therefore 47, not
48. Harmless today: the person entity carries `display_name` directly, and `LatexRenderer.emit` never reads
`Resume.header` (D-156). Promoting the header candidate is a small unbuilt slice, now owed.

**Two friction findings, both owed.** (1) **A promoted skill can never surface.** `promote-candidates` writes
`allowed_surfaces=()` while the facts are unresolved and is one-shot, so nothing widens it when they become
effective; setting the field by hand kept validity clean but `surface_coverage` still counts **0 skills**, so
surfacing derives from something further in. D-182's claim that the graph is "one owner step from a
résumé-surfaced skill" is not reachable through the CLI as shipped. (2) **`add-evidence` cannot take an inline
capture** — it requires `--capture FILE`, which suits a blob but not an owner attestation, whose capture *is*
its text. Authoring `evidence/records.yaml` directly works but leaves `manifest.yaml`'s `evidence_set_digest`
stale (`evidence_set_digest_mismatch`), repaired by hand here. Either `add-evidence` should accept inline text
or the repair should be a documented step.

**Alternatives rejected:** widening `employment.organization` / `project.contribution` to `owner_attested` to
reach Gate B today (the catalog is versioned data and this is a legitimate future change, but weakening a claim
to pass a gate is the failure mode this architecture exists to prevent — raised with Mit and deliberately not
taken); labelling the education exclusions `no_candidate_assertion` to skip two sub-approvals (false); building
the education agent lane now (STATE and D-181 both put Slice C last).

## D-186 — Revision 2: the skills surface, D-185's "not reachable" claim is retracted, and the bootstrap draft is a one-time dead end

**2026-08-14 · `revision 2`, `sha256:9917b67b…`, stamp `approval-stamp.000002`.** The résumé surface now carries
**38 facts, 10 skills and 5 contacts**; validity is clean and completeness still reports exactly the 9
evidence-gated blockers of D-185. `CURRENT` names revision 2 and both revisions are on disk.

**Root cause of the skill-surfacing gap, found by reading the counter rather than guessing.** A `SkillRecord`
carries its **own** `verification_state`, independent of its supporting facts. `promote-candidates` births it
`unresolved`, and confirming the 14 `technology.used` facts never touches it. `_surface_coverage`
(`validation/completeness.py:491`) counts a skill only when `verification_state in EFFECTIVE_STATES`
(`{verified, owner_confirmed}`) **and** the surface is declared — so setting `allowed_surfaces` alone could never
move the number.

**D-185's claim that D-182's stop condition "is not reachable through the CLI as shipped" is RETRACTED.** It is
reachable, and `test_the_owner_confirmation_step_reaches_a_grounded_resume_skill` has always set *both* fields
(lines 298-302). The earlier finding was a half-completed owner step misread as a defect in the machinery. What
survives is narrower and real: **no CLI command confirms a skill**, so it is a hand edit on
`skills/inventory.yaml`, and `promote-candidates` is one-shot so it cannot redo it. Skills are absent from the
closed `ApprovalAction` catalog, so the edit is *not* owner-gated — confirmed empirically, `approve` reported
**zero** additional transitions.

**A transition is a delta from the parent, not a re-listing.** Revision 1 already held every fact and contact
`owner_confirmed`, so revision 2's stamp authorised the candidate itself with no sub-approvals. An expectation
of ~37 transitions was wrong and is recorded so the next session does not read a zero as a failure.

**The bootstrap draft is a one-time dead end, and this is worth knowing before it wastes a session.** `baseline`
was checked out of *no revision*; revision 1 was then promoted from it. `rebase-draft` compares each side
against the old parent, and with **no** parent every one of the 244 records reads as changed on both sides, so
it refuses with `draft_rebase_conflict` — correctly, since a rebase never resolves a record conflict for the
owner. `approve` equally refuses it with `stale_draft_parent`. The draft is therefore unusable by any route and
the only exit is `checkout` of a fresh draft (here `skills-surfaced`). This is reachable **only** for the very
first draft of a bundle, exactly once. Not fixed: the remedy is one command and the failure is loud, but a
`checkout`-suggesting hint in the `stale_draft_parent` message would cost nothing.

**Alternatives rejected:** editing `baseline` further (it can be neither approved nor rebased); making
`promote-candidates` re-runnable so it could set the skill state after fact confirmation (it is deliberately
one-shot, D-182, and re-running would clobber owner edits); widening `_surface_coverage` to infer a skill's state
from its supporting facts (a `SkillRecord`'s state is its own owner decision, and inferring it would surface a
skill the owner never confirmed).

## D-187 — Projection `skill_groups` are optional and synthesized from the bundle catalog when omitted

**2026-08-14 · Mit's ruling, then built test-first.** `promote-candidates` already derives the owner's skill
taxonomy *inside* the revisioned, digest-bound bundle (`policy/skill-categories.yaml` + each `SkillRecord.category`).
But `projection.yaml` lives *outside* the bundle and its `SkillGroupDeclaration` restates grouping inline as
`(label, [skill_id…])`. Authoring it by hand would put the groupings in **two** places with only one versioned,
and nothing checked they agreed (`contract.check_references` validates only that each declared skill id exists and
is résumé-surfaced — never that its group matches its bundle category). For Mit's revision-2 bundle the projection
copy would have carried **zero** new editorial decisions: the four groups (Languages / Frameworks / Databases &
Networking / Tools) and their membership are 1:1 with what promotion already derived.

**Choice (Mit, of three options offered):** make `skill_groups` optional in `projection.yaml`. When present, it is
the owner taking full control of grouping/order/inclusion (unchanged path). When **omitted**, `project_pool`
synthesizes one group per category that has a résumé-surfaced skill — labelled by the category `display_name`, in
the catalog's own order; within a group, skills keep inventory order; only résumé-surfaced skills appear; an empty
category is dropped (no empty section). The taxonomy then lives in exactly **one** versioned place, and the
synthesized content is bound by the bundle digest the approval stamp already pins (`stamp.bundle_digest`), so no
new versioning surface is added. `_synthesized_skill_groups` (`projection/pool.py`) is a pure helper unit-tested for
order/filter/empty-drop; a `project_pool` integration test proves the wiring against the example bundle.
`categories is None` is unreachable for a promoted bundle — `policy/skill-categories.yaml` is a required document
(`validation/structural.py`) — so the None arm only narrows the optional type, mirroring semantic validation's own
`if categories is not None` guard. `projection_candidate` (the approve preview) is untouched: it never showed
`skill_groups` (they carry no template placeholder), and now they are simply derived at render time.

**Alternatives rejected:** hand-author the duplicate now (fastest, but two-places/one-versioned with silent drift —
the exact failure the bundle design forbids); author inline **and** add a contract check that each group label
equals its skill's bundle category (still duplicated, drift merely becomes fatal rather than silent — more code for
a copy that carries no new decision).

**Two render-status facts found while confirming the path, neither owed to this change.** (1) **`profile-bundle
project` is JD-blind and needs no `--scorer`** — it serializes the Stage-1 master résumé document; only `resume
project` (posting-aware Stage 2) needs the scorer Task 20 still gates (D-168). So a *master* résumé is reachable
without Task 20. (2) **The bundle holds zero claims** (`claims/bullet-candidates.yaml` and `summary-candidates.yaml`
are both `claims: []`): promotion (D-182) built entities + facts + skills but **no `ClaimRecord`s**, and
`contract.py` requires an entry's `claims` to be approved + résumé-surfaced. So a projected résumé today would carry
the synthesized skills section and entry headings/titles/dates but **no accomplishment bullets** — a claims-promotion
slice (bullets → `ClaimRecord`s) is unbuilt work standing between the graph and a real résumé, distinct from Gate
B's evidence blockers.

## D-188 — An entry's bullets can come from facts, not only claims: `bullet_predicates`

**2026-08-14 · Mit's ruling ("Path 2"), built test-first.** The projection rendered entry bullets **only** from
`ClaimRecord`s (`_build_entry` read `entry_decl.claims`), but D-155's reorientation put Mit's résumé bullets into the
bundle as **facts** — `employment.accomplishment` / `project.contribution`, multi-valued, string-typed,
owner-confirmed and résumé-surfaced, full text including numerals. The bundle holds **zero** `ClaimRecord`s (D-187),
so those accomplishments had no path to the page. Two ways to bridge facts→bullets were weighed: **Path 1**, promote
facts into `ClaimRecord`s (uses the designed claims/metric apparatus, but `ClaimRecord` validation requires every
numeral to trace to a referenced `MetricRecord`, so it needs a metric-extraction design and has spec-loop risk — a
design session, not a solo build); **Path 2**, let the projection render the facts directly as bullets. **Mit chose
Path 2.**

**Choice:** a new optional `EntryDeclaration.bullet_predicates: tuple[str, ...] = ()` names which predicate(s)
supply an entry's bullets — **declared, never derived** (like `EntryKind`), and catalog-agnostic, so a non-software
user's field names its own bullet predicate without code. In `_build_entry`, after the claim-derived bullets, each
declared predicate's résumé-citable facts render as bullets in predicate-declaration order then index order. Bullet
text is the fact's rendered value (`grammar.render_value`), `bullet_id` is the `fact_id`, `tech_tags` stay `[]` — the
same shape as claim bullets. Gathering is `effectiveness.resume_bullet_facts_for`, which shares its four gates
(effective · résumé-surfaced · not application-only · unexpired) with `resume_facts_for` through a new private
`_resume_facts` generator, differing only in keeping ALL of one predicate's facts as a list rather than the
first-wins mapping the `{predicate}` grammar needs. Two fidelity refusals, both fail-safe because the projected
document becomes Tier A's ground truth: a declared predicate resolving to **no** fact is `BULLET_PREDICATE_NO_FACTS`
(a mistyped predicate fails loudly, never a silently bulletless entry), and a non-line value kind (a `skill_ref` such
as `technology.used`, a list) is refused by the existing `FACT_VALUE_KIND_NOT_ADMITTED` gate in `render_value`.
`claims` and `bullet_predicates` are independent and concatenated, so the `ClaimRecord` path is untouched and Path 1
remains available later if tailoring needs wording control or metric grounding.

**Consequences.** The example declaration and its digest are unaffected (`bullet_predicates` defaults to `()`); the
new field is part of `projection_digest`'s `model_dump`, so an owner's bullet-source choice is inside what they
approve, while the fact CONTENT stays bound by the bundle digest the stamp pins. The D-166 boundary needs no change:
the bundle maps the whole `ProjectionIssue` enum to one catch-all member, so the new `BULLET_PREDICATE_NO_FACTS`
requires no per-issue wiring. This departs from the projection design's built-in assumption that bullets are
`ClaimRecord`s (the spec's §7 and examples), but contradicts no ruling — it extends the renderer to the shape D-155
gave the data.

**Alternatives rejected:** Path 1 now (design-heavy, needs Mit's numeral→metric rulings, spec-loop risk); inferring
"bullet-bearing" from `cardinality`+value-type instead of declaring it (magic, and `technology.used` is also
multi-valued — inference would misclassify); allowing a declared predicate to resolve to zero bullets silently
(a fidelity failure on a Tier-A-ground-truth document).

## D-189 — The master is a reservoir sourced from the wiki, and `project.contribution` is widened to owner_attested in Mit's bundle

**Context.** The career-profile bundle had only ever been fed `{config_dir}/resume.yaml` (a thin, ~8-entry
per-JD résumé), so the promoted graph was thin. Mit's north star is per-JD tailoring — Stage 2
(`resume project --posting --scorer`, gated on Task 20) SELECTS a one-page output from the graph, swapping in
iOS projects for a mobile role and backend ones for an SDE role. That only works if the graph is the SUPERSET.
The canonical superset already existed as a human knowledge base at `~/dev/portfolio-website/wiki`
(`00-profile/` + `01-projects/`, 17 rich per-project pages); `resume.yaml` and job-apps' `sections.tex` are
thin OUTPUTS of it, not the source. Separately, project bullets would not render: the builtin catalog gives
`project.contribution` basis `repository_verified` (only a repo is admissible evidence), while
`employment.accomplishment` is `owner_attested` — so job bullets render on the owner attestation but project
bullets stay `unresolved` and invisible.

**Choice.** (1) **The master is a reservoir, rebuilt from the wiki.** The live bundle is an 11-entity master —
4 experiences + 7 projects (SDE ∪ iOS: Hookrail, Knowledge Forge, StreakSync, Random Forest, FlickSwiper,
BirthdayQuest, Fond) — carrying each entry's FULL wiki-grounded bullet set (33 bullets), not the 1–2 a
one-pager shows. `resume.yaml` remains the mechanical import source, but its CONTENT is now sourced from the
wiki, not `sections.tex`. (2) **`project.contribution` is widened to `owner_attested`** (Mit's "Option A"):
in *his bundle's* `policy/predicates.yaml` only — `minimum_evidence→owner_attestation`,
`legal_verification_bases→[owner_attested]`, `owner_attestation_authority→owner_confirmed`, mirroring
`employment.accomplishment`. The shipped builtin catalog stays strict, so this is versioned bundle data, not a
code change ([[boardwatch-program-generalized-vs-personal]]). Mit's résumé project bullets are his own claims,
attestable exactly like his job bullets.

**Consequences.** The full loop is closed: wiki → master bundle → promoted revision → approved
`projection.yaml` → `project` renders a 2-page reservoir with every bullet showing (a reservoir is *meant* to
exceed one page; Stage 2 trims it). Gate B dropped from ~18 completeness blockers to **7** (4
`employment.organization` `private_document` + 3 `review_required` import items); the 11 project contributions
are resolved. Mit supplied the **Stage-2 selection ground truth** (SDE = {Hookrail, Knowledge Forge,
StreakSync, Random Forest}; iOS = {StreakSync, FlickSwiper, BirthdayQuest, Fond}; Nakshatra = drop-if-space) —
the Task-20 answer key. A real workflow debt surfaced: **one-shot `promote-candidates` forces a full bundle
rebuild + a fresh TTY `approve` for ANY content change** (~six rebuilds this session); an incremental
`checkout → edit one fact → approve` path is owed before Mit iterates on metrics. Full operational detail and
the rebuild recipe live in memory `master-reservoir-built-from-wiki`.

**Alternatives rejected.** Match `sections.tex` exactly (it is a thin, JD-tailored OUTPUT — the wrong source
for a reservoir; tried first, corrected). Keep `project.contribution` strict (blocks project bullets on a
résumé where they are owner claims like everything else). Supply repository evidence now to clear the
contributions the strict way ("Option B" — deferred to a later session, where the repos will ALSO be used to
sharpen the bullets, so it is an upgrade, not a detour). Widen `employment.organization` too (not needed for
rendering — its heading uses `{@display_name}`; the overflow there is a separate data-value fix).

## D-190 — Content edits are incremental: `edit-fact` files a correction as an edge, and no rebuild is needed

**Context.** Every content change to the promoted bundle was costing a full rebuild — `init`, `import`,
`extract`, `promote-candidates`, a fresh TTY `approve` — because `promote-candidates` is one-shot
(`authoring._refuse_if_already_promoted`) and refuses the moment any entity document exists. Six rebuilds
happened in the 2026-08-14 session alone, and D-189 named the incremental path as the top workflow debt,
to be built *before* Mit starts iterating on bullet metrics. Investigation found the capability was never
missing: `checkout` has always copied the selected revision into a writable draft, and a hand-edited fact
value validates clean. What was missing was a writer for the documents an edit touches together, and any
documentation that the loop existed at all — which is the actual reason it went unused.

An edit is not one write. §12 compares the two evidence-citation directions exactly, so a new fact citing
an existing evidence record leaves `evidence_link_asymmetry` until that record names it back; and changing
the evidence document makes the manifest's `evidence_set_digest` stale, which is
`evidence_set_digest_mismatch` — the code §21 reserves for evidence mutated after promotion, which no
command repairs. Both were reproduced by hand before either command was written. This is the same
three-document shape `add-evidence` already had, and `docs/profile-bundle-authoring.md` states the rule: a
command exists exactly for the operations that must touch more than one document at once.

**Choice.** Two commands, `profile-bundle edit-fact` and `add-fact`, in `authoring.py` beside
`add_evidence`/`resolve_conflict`. No new model fields, no new validation rules, no new issue codes — both
are orchestration over machinery that already shipped.

**A correction is an edge, not a mutation**, which is what `FactRecord` was designed for and what
`supersedes_fact_ids` has been carrying, unused, since schema v1. `edit-fact` files a successor `<id>.r2`
(then `.r3`) and flips the original to `superseded`, leaving it immutable. Three consequences follow from
shipped code rather than from anything new: `semantic.py` fails a draft whose superseded fact stays
effective *or* whose `superseded` state has no superseder; `referential.py` rejects supersession cycles; and
`effective.py` drops `SUPERSEDED` via `UNAVAILABLE_STATES`, so the old wording leaves every projection with
no render-side change. Measured on the live bundle: after correcting one BirthdayQuest bullet, the effective
set holds `contribution.001.r2` and not `contribution.001`, and BirthdayQuest still renders three bullets,
not four.

**The successor claims no import lineage.** Carrying the parent's `source_content_digest` forward would
assert a match against source bytes that no longer contain the text — a provenance claim no layer checks and
no command repairs. It was verified that a hand-edited value validates *clean* today, so this failure is
silent, which is precisely why the command owns it. Three refusals follow the same reasoning: a
`verification_basis` other than `owner_attested` is refused rather than inherited (a document read or a
repository checked is not re-established by the owner retyping the wording) or silently downgraded (that
would drop a verification nobody asked to drop); an already-superseded fact is refused (correcting it would
branch the chain and leave "the current value" without an answer); and a non-string value is refused because
`--value` is text. On `add-fact`, `--verification-state` and `--verification-basis` are required and never
defaulted — a default would assert how strongly the bundle believes a fact on the owner's behalf.

**Consequences.** A wording change is now `checkout → edit-fact → validate → approve → promote`, with
`promote-candidates` out of the loop entirely. The TTY `approve` is unchanged and deliberately kept: it binds
consent to an exact content digest and `promote` refuses without a stamp for that digest. What changes is its
frequency — one approval per batch of edits rather than one per rebuild. The `profile-bundle` surface goes
from 17 leaf commands to 19.

Two findings are worth carrying. **A mutation that deleted the lineage drop survived its test**: every fact
in the packaged example either holds no `import_lineage` or is refused for its basis, so the assertion passed
whether or not the successor dropped anything. The test now seeds a parent with lineage to lose. And
**`mypy --strict` rejected the first shape**: `FactBearingDocument` is the shared base of the twelve
fact-bearing documents but is *not* a member of the `DocumentModel` union the writers take, so narrowing to
it discards which concrete document a value is and it can no longer be handed to `_write_documents`.
`_fact_position` therefore returns the record it already found alongside a union-typed document, which avoids
a `cast` and removes a second lookup.

**Review, and five defects it found in the first cut.** An adversarial read of the branch before merge
found that the first implementation broke the module's own header contract — "every check runs before the
first byte is written" — in the one place it matters most. All five were reproduced before being fixed.

1. **`add_fact` wrote all three documents before any predicate contract was checked.** `_revalidated` runs
   the MODEL tier only, and `PredicateId` is a bare regex, so an unknown predicate, an illegal value type,
   surface, usage context or subject kind all parsed and were renamed to disk; the CLI's closing
   revalidation then reported them, too late. Measured: `add-fact --predicate employment.date_range --value
   "2024-01 to 2025-06"` returned **`clean`**, rewrote all three documents, and only afterwards reported
   `predicate_value_type_illegal`. That fact could then never be removed — facts are append-only, no command
   deletes one, and `edit-fact` swaps a string for a string without touching a value type or predicate. Now
   `_catalog_admits` runs the semantic layer over the prospective tree and refuses anything it reports that
   the current tree does not. Written as a **diff, not a list of checks**, for the reason `_gates` derives
   owner gates rather than restating them: five hand-named codes would be a second statement of the
   catalog's rules, free to drift from the one `promote` enforces. It reads the *bundle's* catalog, so Mit's
   D-189 widening of `project.contribution` is honoured rather than second-guessed.
2. **`_document_owning` resolved to `application/gated-facts.yaml`.** It took the first fact-bearing
   document mentioning the subject, and `BundleDocuments.items()` sorts, so `application/` beat
   `facts/identity.yaml` for every person fact — filing it among the application-only records, where
   `effective.is_application_only` classifies by **file membership**, making a §16 decision the operator
   never asked for. It now asks `BundleIndex.path_of`, which indexes entities independently of the facts
   about them. That also fixes the second half: an entity with **zero** facts — every entity in a freshly
   `init`-ed draft — used to read as absent, and the refusal told the operator to "promote the entity",
   which `promote-candidates` refuses outright once entities exist.
3. **`_evidence_naming` rewrote contradicting and contextualizing citations as `supports`.** `edit_fact`
   passes the parent's whole `evidence_ids`, and every named record had the successor written into
   `supports_record_ids` regardless of which of §12's three relationships actually held. Only `supports`
   counts toward a predicate's evidence contract, so a rewording could silently clear an
   `evidence_contract_unmet` nobody re-established — D-144's defect arriving through a new writer. The
   relationship is now mirrored per record from the parent.
4. **A successor escaped an unresolved conflict group.** `conflict_group_id: None` was justified in the
   first cut as "joining a group is a ruling", but a group blocks its candidates *by membership*, so the
   ungrouped successor became effective immediately — the disputed value reaching a résumé unruled — while
   `competing_values_outside_conflict` blocked `promote` with no command able to repair it. `edit-fact` now
   refuses a fact carrying a `conflict_group_id`.
5. **A derived successor ID could dead-end.** `.r<digits>` is read as a counter, so an ID that ends that way
   for an unrelated reason (`fact.lab.room.r2`) yields a sibling, and a collision used to refuse with
   `duplicate_record_id` naming an ID the operator never typed — leaving that fact permanently
   uncorrectable. The counter now advances past whatever the draft holds.

Two claims in the first cut's own prose were also false and are corrected: `_revalidated`'s docstring said it
caught predicate errors (it cannot), and the write-ordering comment named `evidence_link_asymmetry` as the
residual failure class when it is `broken_reference` — `_evidence_links_are_symmetric` skips a target already
reported as a broken reference. **The lesson worth carrying: three of the five were invisible to a green
`make check`, because the tests and the code shared the author's assumption about where validation runs.**

**Second review, of the fix round.** A fix round inherits its author's blind spot, so the fixes above were
reviewed in fresh context. Three defects survived the first round, all narrower variants of what it found —
a declining severity curve, which is the stated reason the loop stops here rather than running a third time.

1. **`_catalog_admits` consulted one layer, and the basis contract lives in another.**
   `verification_basis_unsupported` is raised by `validate_evidence_structural`, not
   `validate_semantic` — so `add-fact --verification-state verified --verification-basis
   private_document_verified` citing an `owner_attestation` record returned **`clean`**, wrote all three
   documents, and reported the error only afterwards. The fact was then doubly stuck: append-only, and
   `edit-fact` refuses to correct a fact whose basis is not `owner_attested`. The check now runs the four
   layers that judge a RECORD, and a test reads `validate_bundle`'s own list out of `run.py` and asserts
   the consulted set plus the three deliberately excluded (`history` and `imports` read ledgers; `digest`
   compares a manifest to bytes not yet written) is exactly it — so an eighth layer cannot be added there
   and silently skipped here. That test is the guard the first version lacked.
2. **The relationship fallback re-created the defect it fixed.** When the parent was named in *none* of a
   record's three lists — an asymmetric draft, the state `evidence_link_asymmetry` exists to report — the
   successor was still written into `supports_record_ids`, handing it supporting evidence its parent never
   had. `_catalog_admits` is blind to it by construction: the parent's findings are unchanged and so read
   as pre-existing, and the successor has none. An asymmetric parent now yields an asymmetric successor.
3. **Two docstrings outlived their code** in the same commit that corrected two others.

The reviewer independently reached the conflict-guard defect already fixed above, by the same route
(key on the group's state, not on membership), which is corroboration rather than a new finding.

**Cost.** `edit-fact` on the 11-entity master measures **1.2s warm against a 1.14s interpreter-startup
floor** — the pre-write check is ~0.1s, and the before-pass is computed only when the after-pass reports
something, so a clean write validates once.

## D-191 — Repository evidence grounds the project bullets, and the verification basis deliberately does not change

**Context.** D-189 named Mit's "Option B" — supply repository evidence per project *and* use the repos to
sharpen the bullets — and deferred it to a later session. Run 2026-08-15 against every repository that
exists: hookrail, StreakSync, FlickSwiper, BirthdayQuest, Fond. Knowledge Forge has no repository (the
wiki traces its "99% uptime" and "30% login time" to an earlier résumé, not to an artifact), and Crop-RF
is an IEEE publication, so `public_record` — not `repository_artifact` — is its class. Five of seven.

**What the measurement found.** Every one of the five carried at least one false claim, so this was a
correctness pass, not a polish pass. Twelve bullets were corrected. Two numbers were wrong in the
understating direction (StreakSync had 446 tests, not 335), which matters because it means the drift is
not bias, it is staleness. The most exposed was Fond's "five widget families across iOS, iPadOS, macOS and
watchOS": all eight build configurations are iPhone/iPad only, and the macOS and visionOS targets were
deliberately dropped in commits that are ancestors of HEAD.

**Choice.** Five `repository_artifact` evidence records, one per repository, each pinned to a full 40-hex
commit and capturing the file that *proves* the corrected claim — BirthdayQuest's `DataSeeder.swift` is
where 13/4/3 is actually decided, so it is the capture. The contribution facts stay `owner_attested`.

**The basis is not flipped to `repository_verified`, and that is the load-bearing decision.** `edit-fact`
refuses any basis other than `owner_attested` (D-190). Flipping would permanently forfeit the incremental
edit path for exactly the records that get iterated most — the résumé bullets — to gain a label. The
evidence grounds the claim and is re-checkable from `path` + `repository_commit` either way; the basis
records how a claim is *authorised*, not how it is *checked*.

**Alternatives rejected.**
- *Flip to `repository_verified` and narrow the catalog back to the shipped strict row.* Forfeits
  `edit-fact`, and cannot cover Knowledge Forge or Crop-RF, so the widening would have to stay anyway —
  paying the whole cost for none of the benefit.
- *Register no sources.* Measured: an evidence record citing a `source_id` that exists in no document
  validates clean under both plain and `--completeness` validation. Rejected because it relies on a gap.
  Sources are registered per the shipped example's precedent (`repository_markdown`, a relative locator
  naming the repository entry point, with the evidence record's `path` naming the artifact within it); a
  registered-but-unenumerated source validates clean, so this creates no import obligation.
- *Add the strongest unclaimed material.* Hookrail's CI chaos suite — seven failure scenarios including
  jobs that kill the Postgres primary and Redis master under load asserting RPO=0 — is the best material
  found and was **not** added. `add-fact` requires citing an evidence record, and Mit's catalog admits only
  `owner_attested` for `project.contribution`, so a new bullet would have to cite an owner attestation
  dated 2026-08-14 that covers only statements he has actually read. A correction of a false number is
  mandated; a new claim asserted on the owner's behalf is not.

**Two claims falsified in passing.**
1. STATE and the `master-reservoir-built-from-wiki` memory both said revision 3 renders with "zero overfull
   and zero underfull hboxes". Re-rendering revision 3 through the identical code path emits **two
   underfull hboxes**, in the Skills block, from a trailing `\\` before the closing brace. Zero *overfull*
   is correct. The claim was believed because the underfull warnings were never the thing being looked for.
2. Evidence `source_id` has **no referential check** against `policy/sources.yaml` — unlike a relation's
   `source_id`, which does. Latent, not exercised here.

**A spec tension this exposed, and the mistake that found it.** Registering the five repositories in
`policy/sources.yaml` was validated with a plain `validate` — **clean** — and promoted as revision 4. The
completeness tier then reported five `import_unexplained_record` blockers ("an approved source that
`imports/source-ledger.yaml` never enumerates"), taking Gate B from 7 to 17. Revision 5 removes the
registrations and marks the five captures `owner_approved`, restoring 7. The cost is five permanent
`broken_reference` *warnings*: revision 4's change entry names sources revision 5 removes, which is
exactly what the validator says a removal looks like.

The underlying tension is not the mistake. `RepositoryArtifactEvidence.source_id` is **required** by the
model, and registering that source obliges the ledger to enumerate it. So **repository evidence for a
repository the bundle does not import is unrepresentable** — either the `source_id` dangles, or Gate B
takes a blocker. The dangling option is silent only because **no validation layer checks an evidence
record's `source_id` against `policy/sources.yaml`** at either tier (a relation's `source_id` *is*
checked). Revision 5 takes the dangling option knowingly. Closing that referential gap without first
giving `repository_artifact` a way to name a non-imported repository would turn five silent references
into five errors, so the two must move together.

**Method note worth keeping.** A plain `validate` and `validate --completeness` answer different
questions, and an authoring command's closing revalidation runs the validity tier only. Any change that
touches `policy/`, the ledger, or the import documents must be checked at the **completeness** tier before
promotion — the tier that owns Gate B is the tier that can see Gate B regress.

## D-192 — `exclude-record` ships, and both documents re-derived from one ledger are guarded

**Context.** Gate B's three `import_record_undispositioned` blockers (`education/1`, `education/2`,
`header/2`) can only clear by an owner exclusion: disposition is **derived, never authored** — a record
with candidates is `imported`, one the owner excluded is `excluded`, everything else is `review_required`
(`imports.py`, `build_source_ledger`). Nothing in `src/` wrote `imports/exclusions.yaml` at all.

**A premise this started from was wrong, and correcting it changed the work.** `source_exclusion_target_digest`
had zero callers in `src/` and `tests/`, which was read as "the `owner_excluded` sub-approval the schema
promises is unenforced". It is enforced: `approvals.py::_exclusion_decisions` derives an
`APPROVE_SOURCE_RECORD_EXCLUSION` decision, `validate_history` reports `missing_owner_approval`, and
D-115's ruling forbids a second copy in `validate_imports`. **Zero callers meant something else.** The
real defect was **two spellings of one join**: `approvals.py` computed `digest_of([record, exclusion])`
inline while `canonical.py` published `digest_of({"record": …, "exclusion": …})`. The documented binding
and the enforced one were free to drift, and nothing could notice, because the published one was dead.

**Choice.** Ship `profile-bundle exclude-record` in `edit-fact`'s shape (pre-write check, then write, then
revalidate). Move the published helper onto the **enforced** positional spelling and have `approvals.py`
call it — one home. Not the reverse: the list spelling is what any promoted revision's stamp already
binds, so re-keying it would re-spell a digest nothing can re-approve. `approve` needed no change; §13
allows exactly one stamp per candidate, so a sibling command is structurally impossible.

**What three review rounds found, and why the third was still worth running.** Round 1 (whole-commit):
two Majors — a diff-based pre-write check that cannot see removals, and digest tests that agree with
themselves (mutating the spelling gave *2115 passed, zero failures*). Round 2 (fix delta): one Major, a
**narrower instance of the first** — the fix guarded ledger rows, but `imports/extraction-report.yaml` is
re-derived from the same rebuilt ledger by a *different* rule (`_report_without_dispositioned` retires by
a record's disposition **now**, not by whether this write moved it), so a stale drain entry on an already
`imported` record was retired with **zero ledger drift**, silently clearing an
`import_denominator_mismatch`. That is the declining severity curve the loop was watching for: same class,
second document, smaller blast radius.

**The generalisable finding is about `_catalog_admits` itself (D-190's pre-write check), not about this
command.** It is a DIFF keyed on `(code, record_id, message)` that returns early when the prospective tree
is clean, so its guarantee is *"this write introduces no new finding"* — **not** *"every consequence of
this write is checked"*. A write that silently REMOVES findings passes every layer. That is safe for a
narrow append (`edit-fact`, `add-fact`, `add-evidence` each append one record) and the wrong shape for any
command that **re-derives a whole document**, which must additionally assert that only the named record
moved. Both re-derived documents are now guarded.

**Alternatives rejected.** *Let the command repair a drifted ledger.* Rejected: the operator asked about
one record, and a silent Gate B movement is invisible; fail-safe here is to refuse and let the repair be a
decision made on purpose. *Pin the digest with a test comparing against the function under test.* That was
the defect. It is now a frozen hex literal computed outside the function, verified by an independent
recomputation from the canonical-JSON rules and confirmed to match what `approvals.py` enforced before the
change.

**Not merged.** Three commits sit on `worktree-agent-af5fde0288e79b376` with `make check` green at exit 0
(6381 passed), verified by re-running the gate rather than reading the builder's report. The last commit —
the drain guard — is the one change no fresh reviewer has seen, and every round so far found something
real, so the merge waits on one more review. **Still open, same class, deliberately out of scope:**
`source_scope_target_digest` has the identical dict/list divergence with zero callers and no pinning test,
on the `approve_source_scope` gate.

---

## D-193 — Task 20's matrix is recorded unlabeled, and Stage 2 is blocked by a pinning decision underneath it

*2026-08-15. Records a measurement and a blocker found while taking it. Decides nothing the owner owns.*

### Context

Task 20 — the owner-labeled selection matrix — is the only arbiter that can pick Stage 2's scorer
(D-158, D-163, D-168). It has been the named binding constraint on a sendable per-JD résumé since the
projection track merged, and it had not been started because it reads as an owner task end to end.

It is not. Its four steps split cleanly: **steps 1 and 2 are mechanical** (pick ten real postings, record
each one's extracted JD skills), **step 3 is the owner's alone** (rank the entries, draw the cut line),
step 4 is a commit. Doing 1 and 2 removes the setup cost from the owner's session without touching the
labeling that must stay his.

### The decision

`docs/program/projection-selection-matrix.md` is committed with steps 1–2 filled in and **step 3 blank**,
stated as blank in the document's own first line. No scorer has been run against it, per Task 20 step 4.
Ten real, currently-open, `role=swe` postings, spanning backend ×2, distributed systems, infrastructure,
platform, iOS ×2, Android, ML/data and frontend.

Two choices inside it are load-bearing:

- **JD skills come from `posting_context(...).jd_skills`, not from `boardwatch show`.** `show` reports
  only `covers 7/9 skills` and never enumerates them, so transcribing from it was impossible anyway — but
  the deeper reason is that `posting_context` is the call `resume project` itself makes. Recording the
  skills through a different path than Stage 2 reads would let the matrix and the scorer disagree about
  what the JD says, and that disagreement would present as scorer error.
- **Ids are written `entry.project.fond`, not `project.fond`.** The plan's template sketched the bare
  `entity_id`, but `rank_agreement` compares against a scorer's output keyed by `Entry.entry_id` and
  raises `ValueError` unless both sides name exactly the same ids. The plan's spelling would have failed
  at transcription time, after the labeling session was over.

`top` was called with `--no-record` so assembling the document did not advance the dedup queue, which is
directly relevant to Gate P6's clean seven-day window.

### The blocker found while measuring: every entry is pinned

| Fact | Value | Measured by |
|---|---|---|
| entries declared in `projection.yaml` | 11 | `project_pool(...).resume.entries` |
| `pinned_entry_ids` | all 11 | every row carries `pinned: true` |
| `candidate_entry_ids` | **empty** | `project_pool(...).candidate_entry_ids` |
| reservoir render | 2 pages | `pdfinfo` on the revision-5 preview |
| `page_budget` | 1 | `profile.resume_max_pages` |

`select` compiles the pinned-only set first (`select.py:188`) and raises `PINNED_SET_EXCEEDS_BUDGET` at
`:190-197` when it alone overflows the budget — before scoring, which does not start until `:203`. The
pinned-only set *is* the whole reservoir. So `resume project --posting --scorer` cannot return a résumé
for **any** posting and **any** scorer today, and no scorer choice changes that.

**Task 20 was never the only thing between here and a sendable per-JD résumé. It was the visible one.**
Pinning all 11 was correct for Stage 1, whose job was to render the whole reservoir as a master; it makes
Stage 2 inert. Which entries stay pinned is a data decision — one edit to `projection.yaml`, no rebuild,
no promotion — and it is the owner's, though his own ground truth already constrains it: "work experience
is largely fixed", but "Nakshatra = drop-if-space" says at least one *experience* entry is a candidate.

### Alternatives rejected

- **Ranking the entries myself to finish the matrix.** The entire point of D-158 is that the ranking is
  owner-labeled ground truth; a matrix labeled by the same agent that will read it is a test that agrees
  with itself.
- **Choosing the pinned/candidate split from the owner's SDE/iOS sets.** They constrain it but do not
  determine it, and the split silently sets which entries can ever be dropped from a résumé he sends.
- **Deferring the whole task until the owner has a session free.** Steps 1–2 need no judgement and were
  the reason the task kept not starting.

### What generalises

- **A task labeled "the owner's" can still have mechanical halves worth doing in advance.** Task 20 sat
  unstarted for two days because its owner-only step was read as covering all four.
- **A gate nobody has run can be blocked by something upstream of the gate.** The matrix would have been
  labeled, transcribed and measured before anyone discovered `select` refuses on every input. The probe
  that found it — reading `candidate_entry_ids` off a real `project_pool` — cost one command.

---

## D-194 — `approve_source_scope` binds the spelling already on disk, and the helper is the side that moves

*2026-08-15. Closes the twin of D-192's divergence, and fixes three review findings on the drain guard.*

### Context

D-192 found that `source_exclusion_target_digest` shipped with zero callers while `approvals.py` computed
the same join inline, so §13's documented target and the enforced one could drift with nothing able to
notice. The review that released `exclude-record` confirmed the fix and, being scoped to that commit,
explicitly left the identical case alone: `source_scope_target_digest`, same shape, zero callers, no
pinning test, on the `approve_source_scope` gate.

### The decision

**The helper moves onto the enforced spelling; the enforced join is never re-spelled to match the helper.**

The two genuinely disagreed — `digest_of({"source": ..., "ledger": ...})` in the helper against
`digest_of([...])` in `approvals.py`. Which one is "right" is not an aesthetic question, and it was
settled by measurement rather than by analogy with D-192: recomputing both spellings for the real
`source.mit-resume` pair against all five promoted revisions of a live bundle, the on-disk
`approve_source_scope` stamp binds the **list** value and the keyed value matches nothing. That bundle
already carries two such stamps.

So the natural-looking fix — wire the published helper into enforcement — would have **silently
invalidated approvals already stamped**. A promoted stamp cannot be re-approved retroactively; it can
only be superseded. The helper is therefore the side that changes.

Pinned three ways, because equality alone would still hold in the state this removes (both sides
re-deriving the same join independently): a frozen hex literal computed from two authored records rather
than read back off the function under test; an equality between the enforced join and the named helper;
and a monkeypatch proving `_joined_source_digest` actually *delegates*. All three fail before the change,
the third with `AttributeError` — there was no call to patch.

### Also in this change: three review findings on the drain guard

All three were message-and-claim defects, not correctness holes — every case was already refused.

1. **The "exactly the named record moves" claim excluded the named record.** Both guards skip it by
   construction, and `_disposition_for` tries `candidates ⇒ imported` **before** `an exclusion ⇒
   excluded`, so a row recorded `review_required` whose candidate is still in `candidates.yaml` derives
   as `imported` *even with its exclusion filed* — and the caller reports that derived value, so an
   *exclude* reported `imported`. `_catalog_admits` refused it downstream as `import_missing_exclusion` +
   `import_denominator_mismatch`: two findings about `imports/exclusions.yaml`, neither naming the ledger
   drift that produced them. Confirmed by running the pre-fix code against a mutated `src` copy.
2. **The drain refusal inherited the ledger refusal's remedy verbatim**, and for that condition the
   ledger is the document that is *correct*. For an entry naming a record no source enumerates, *both*
   suggested remedies are no-ops — `_rebuild_report` keeps every entry outside the source it re-extracts.
3. **One code covered three conditions separable only by `path`**, which cannot separate the
   named-record case from the unnamed-row one since both are the ledger. They now carry a typed
   `drift_kind`.

### Alternatives rejected

- **Re-keying `approvals.py` to the mapping spelling.** Reads as the tidier fix and breaks stamps on disk.
- **Amending the reviewed commits.** The review is evidence about the commits as reviewed; rewriting them
  discards that.
- **A fourth review round before merging.** The exit criterion was set in advance and the severity curve
  had flattened — round 1 and round 2 each found a real defect, round 3 found nothing above minor.

### What generalises

- **A dead symbol is not an absent check** (D-192), and its corollary here: when two spellings of one
  value disagree, the one already written to disk wins, whatever the documentation says. Ask what is
  *stamped*, not what is *named*.
- **A reviewer's declared out-of-scope item is a lead, not a closed question.** This one came with the
  defect class already identified and cost one measurement to confirm.

---

## D-195 — The pinned set is the three fixed jobs, and the one-page ceiling is 16 bullets

*2026-08-15. Unblocks Stage 2 at the data level, and measures the capacity that bounds every later
selection decision.*

D-193 established that all 11 declared entries carried `pinned: true`, so `candidate_entry_ids` was empty
and `select` raised `PINNED_SET_EXCEEDS_BUDGET` before scoring — for any posting and any scorer. The fix is
one edit to `{config_dir}/projection.yaml`, but **which** entries stay pinned is the owner's data decision,
not an engineering one.

**The capacity was measured before the owner was asked**, by compiling hand-named subsets through the same
`compile_prefix` path `select` builds (`LatexRenderer.emit` → `to_pdf` → `evaluate_compile`, `max_pages=1`).
No scorer was run; the growth orders below are probe orders, not rankings.

| Base | Base bullets | SDE order survives | iOS order survives |
|---|---|---|---|
| all four jobs | 9 | 2 of 4 (hookrail, knowledge-forge) | **1** of 4 (streaksync) |
| three jobs, no Nakshatra | 7 | 2 of 4 (hookrail, knowledge-forge) | 2 of 4 (streaksync, flickswiper) |
| two jobs (Saayam + NIO) | 5 | 3 of 4 | 3 of 4 |

**The ceiling is 16 bullets, not a number of entries.** 16 fits in every configuration tested; 17 overflows
in every one. Two different 6-entry sets landed on opposite sides of the budget, so entry count does not
predict fit and must not be used as a proxy.

**The consequence the owner needed before choosing:** his stated per-JD sets — SDE = {Hookrail, Knowledge
Forge, StreakSync, Random Forest}, iOS = {StreakSync, FlickSwiper, BirthdayQuest, Fond}, four projects each
— **do not fit on one page under any split**. The most that ever fits is three, and only when just two jobs
are pinned.

**Choice (the owner's):** pinned = `employment.saayam`, `employment.nio-coop`, `employment.sakec`;
candidates = `employment.nakshatra` plus all seven projects. Measured after the edit: pinned 3 / candidates
8, pinned set alone 7 bullets → 1 page, so `select` clears its own gate and proceeds to scoring.

### Alternatives rejected

- **Pin only Saayam + NIO.** Yields three projects per JD, the closest reachable version of the stated sets,
  but makes SAKEC droppable — and "work experience is largely fixed" named only Nakshatra as drop-if-space.
- **Pin all four jobs.** Leaves room for exactly one project on an iOS JD, which defeats per-JD swapping.
- **Pin nothing.** For a thin-extraction JD ranking is near-degenerate, so the admission threshold alone
  would decide whether the current role appears at all.
- **Raise `resume_max_pages` to 2.** The owner pins it at 1; the budget is the constraint being designed
  against, not an obstacle to route around.

### What generalises

- **A budget denominated in pages is really a budget in bullets.** The page count is what the gate reads,
  but it is not the knob anyone can reason with. Convert a gate's units into the units of the decision
  before asking a person to make it.
- **Measure the consequence of each option before presenting the options.** The owner's own ground truth
  turned out to be unsatisfiable, and no amount of discussion would have surfaced that — one compile per
  option did.
- **Bounds the Task 20 threshold.** With three jobs pinned, at most two candidates can ever be admitted, so
  cut lines placed deeper than that in the matrix describe a résumé the budget cannot emit.

---

## D-196 — Gate B's three undispositioned import records are excluded as `owner_excluded`, 7 blockers → 4

*2026-08-15. First use of `exclude-record` (D-192) against the live bundle.*

`validate --completeness` carried three `import_record_undispositioned` blockers — the two education rows
and the header contact line from `source.mit-resume`, each `disposition: review_required` with
`candidate_ids: []`. Disposition is derived, never authored, so no document could clear them; only an owner
exclusion can.

**Choice:** all three excluded with reason `owner_excluded`, each rationale citing D-156 — `LatexRenderer.emit`
never reads `Resume.header` or `Resume.education`, both of which come from `{config_dir}/resume_template.tex`.
The material has no consumer in the bundle, so declining to import it is a policy call, not an extraction gap.

**Measured on draft `gate-b-imports`, at the completeness tier before any approval** (a plain `validate`
cannot see Gate B): blockers **7 → 4**, errors 0 both sides, warnings 10 both sides (the permanent
revision-4 residue), ledger `review_required` 3 → 0, `excluded` 0 → 3, denominator unchanged at 106,
`exclusions_by_reason.owner_excluded` = 3. The four survivors are the `employment.organization` facts, which
have no CLI path at all and need the owner's employment documents.

### Alternatives rejected

- **`no_candidate_assertion`.** Descriptively true — the extractor produced no candidate — but it names the
  extractor's silence as the cause when the actual cause is the owner's decision that the template owns this
  material. The catalog reason is a claim about *why*, and picking the one that avoids an approval would be
  choosing a reason for its cost.
- **Importing them as facts instead.** They would render nowhere, and a fact with no consumer is exactly
  what the disposition check exists to surface.

### What generalises

- **Pre-flighting a guarded command against live data is worth its cost.** Both drain guards were verified
  non-firing (106 records, exactly 3 `review_required`, 3 matching report entries, zero drift) before the
  command touched the bundle, so a refusal would have meant a real defect rather than an unknown.

## D-197 — Task 20's matrix is owner-labeled, unblocking scorer selection (Task 23)

*2026-08-15. Resolves D-193's "recorded unlabeled" and consumes D-195's pinning decision.*

D-193 recorded the ten postings and their JD skills but left the rankings blank; D-195 fixed the pin
(3 jobs) underneath it. Both preconditions met, the owner supplied the rankings this session and they were
transcribed verbatim into `docs/program/projection-selection-matrix.md`.

**The owner's heuristic:** most postings are general SDE →
`hookrail → knowledge-forge → streaksync → crop-rf` (Random Forest for the published-research signal);
mobile/iOS → `streaksync → flickswiper`, then `fond` or `birthdayquest` by JD keyword; experience is the
fixed pinned three. **Five rows needed a keyword call, resolved with the owner:** Ramp iOS 1372 → `fond`
(only iOS project with TypeScript); Snap 19754 → `hookrail` third (JD names distributed systems +
observability); Spotify 13160 (Android, matches none) → `crop-rf` leads on its Flutter build, iOS apps kept
as mobile-craft evidence; Zillow 17187 → `crop-rf` promoted (ML/research); Ramp frontend 1370 →
`knowledge-forge` promoted (the only React/TS/Tailwind web project).

**Structural choice:** the pinned three are excluded from ranking and each below-the-line block lists only
the **rejected candidates**, never the pinned jobs. This follows from the code, not preference:
`agreement.score_all` runs the scorer over exactly the ids `case.expected` names
(`_rank_by_scorer` → `_flatten(case.expected)`), so listing a pinned entry under "should NOT appear" would
be both false (it always appears) and useless to the Task-23 threshold derivation. Each posting was verified
to cover exactly the eight candidates with no id in both zones. Docs-only change: `generalization` OK,
`index-check` current.

### Alternatives rejected

- **Labeling by inspecting a scorer's output.** The one thing the matrix exists to prevent (D-158): a
  ranking chosen to match a scorer is a test that agrees with itself. No scorer was run before this commit.
- **Claude choosing the rankings.** The rankings are the independent arbiter; if the agent originates them
  they measure nothing. The agent proposed keyword calls for five rows and transcribed; the owner decided.

### What generalises

- **The arbiter must be committed before any scorer number is seen.** Landing the labeled matrix first makes
  the ground truth immutable and tamper-evident, so the Task-23 rank-agreement measurement reads a fixed
  input rather than one that could be nudged toward a preferred scorer.

## D-198 — Task 23: `mean_per_bullet` is adopted as the CLI scorer default, threshold stays `Decimal(0)`

*2026-08-15. Consumes D-197's labeled matrix; supersedes D-168's "no default" for the CLI only. D-163's
library-level invariant (no scorer chosen by inspection) is unchanged.*

**Context.** With Task 20's matrix owner-labeled (D-197), the arbiter for choosing a scorer existed for
the first time. Task 23 ran `agreement.score_all` over the ten labeled postings — `jd_skills` resolved
through `posting_context(...)`, never the matrix's annotated display strings — and read each registered
scorer's mean Kendall tau-b against the owner's rankings. No new code was needed; there is no CLI, so the
ten cases were transcribed into `MatrixCase`s and scored in a throwaway script.

**What the measurement actually showed.** The scorers barely separate, and agreement is weak in absolute
terms. Two transcription readings were computed because the matrix docs disagree on whether `case.expected`
is the above-cut ids only or all eight (the "candidate menu" says above-cut; STATE frames it as "over the
eight candidates"):

- **Above-cut ids only:** a flat four-way tie at tau-b ≈ **+0.10**. No winner.
- **All eight (rejects as one tied last group):** `mean_per_bullet` = `mean_top_k` = **+0.159**;
  `coverage_then_density` = `total_distinct` = **+0.150**. The *mean* family edges ahead by ~0.009 — a
  within-noise margin — for a principled reason: normalizing by bullet count stops it being fooled by a
  bullet-heavy off-topic entry (it correctly demotes `hookrail`, which `total_distinct` ranks #1 on the
  Ramp-iOS JD). `mean_per_bullet` and `mean_top_k` produce *identical* scores on this pool and cannot be
  told apart by it.

**Choice.** Adopt `mean_per_bullet` as the default for `resume project --scorer` (`projection_cmd.py`'s
`SCORER_OPTION`), the more standard of the tied mean pair. The default lives at the **CLI boundary only**;
`select()` keeps `scorer` a required parameter with no default, so D-163's library invariant holds. The
admission threshold `ADMISSION_FLOOR = Decimal(0)` (`select.py:64`) is **kept unchanged**: the owner's cut
lines do not correspond to *any* score threshold (above-cut entries routinely score 0; below-cut entries
routinely score higher than accepted ones), so there is nothing to "set it to" from the cut lines — 0
(reject only genuine zero-overlap) stays the least-bad floor. The owner made the adoption call; the agent
ran the measurement and recommended.

**Alternatives rejected.**

- **"Read off the highest and adopt it as objective."** The plan assumed Task 23 would mechanically pick a
  clear winner. The measurement falsified that: under the above-cut reading there is no winner at all, and
  under the all-eight reading the margin is ~0.009 tau-b. The pick is a judgement on a near-tie, not a
  reading-off — so `--scorer` stays overridable rather than silent.
- **Inventing a fifth/third scorer, or raising the floor to fit the cut lines.** Forbidden by D-163 and
  unsupported by the data respectively — no threshold reproduces the owner's cut, because the owner's
  selection is largely orthogonal to JD-skill overlap.

**Consequence — a real, recorded limitation.** Skill-overlap scoring is a weak proxy for the owner's
selection (exactly what D-158/D-163 predicted, now measured). With `ADMISSION_FLOOR = Decimal(0)` and the
2-candidate page budget (D-195), postings where the owner's picks share no extracted JD skill will drop
them or fire the `no_match_fallback` path — **Spotify Android 13160 is the live example: every candidate
scores 0, so nothing is admitted and the curated fallback runs.** This is a property of the pipeline, not
a bug to fix by fiat; widening the reservoir's bullets (STATE open Q5) is the lever that would change it.

### What generalises

- **A labeled arbiter can return "no clean answer," and that is itself the finding.** The value of running
  the measurement was not the winner it named but the weak agreement it exposed — a near-tie among proxies
  that all measure the wrong thing. Adopting the thin winner while keeping it overridable records the
  weakness instead of hiding it behind a hardcoded default.
- **Adopt a policy default at the boundary that owns the policy.** The scorer default belongs at the CLI,
  where the owner's matrix ruling lives, not inside the pure `select()` function, which must stay
  policy-free so the "no scorer by inspection" invariant is enforceable in isolation.

---

## D-199 — `resume project`'s manifest maps bullets by their own id, not by re-parsing the declaration's `claims`

*2026-08-15. Fixes a latent crash surfaced by the first real emission (D-198's newly-unblocked "emit a
real projected résumé"). Reverses the `claim_to_bullet` derivation design that shipped with Task 19,
because it was structurally incompatible with the `bullet_predicates` path added by D-188.*

**Context.** The very first attempt to emit a real projected résumé — `resume project --posting 349`
against the live master-reservoir bundle — crashed with `ValueError: zip() argument 2 is longer than
argument 1` at `projection_cmd.py`. It had never run against the live declaration: every test in
`test_projection_cli_resume_project.py` used the packaged example declaration, which declares bullets via
explicit `claims:`, while the live declaration (and the whole D-188 reservoir design) declares them via
`bullet_predicates:`.

**Root cause.** The manifest's `claim_to_bullet` field was built (Task 19) by re-parsing the declaration
file, keying each entry's `entry_decl.claims`, and zipping that against the rendered `entry.bullets` with
`strict=True` — a deliberate choice, documented in a code comment, to avoid a self-agreeing
`(bullet.bullet_id, bullet.bullet_id)` tuple by cross-checking against an "independent" second parse.
That premise held only for the claims path. `pool._build_entry` builds bullets from **two** sources: the
enumerated `claims` (`bullet_id=claim_id`) *and*, since D-188, each declared `bullet_predicate`'s
résumé-surfaced facts (`bullet_id=fact.fact_id`). A `bullet_predicates` entry lists no per-bullet ids in
the declaration at all, so `entry_decl.claims` is empty while `entry.bullets` is non-empty — the strict
zip mismatched on the first such entry. The live declaration is entirely predicate-based, so the path was
unreachable in tests yet certain to crash in production.

**Choice.** Read each bullet's source id off the bullet itself:
`claim_to_bullet = ((b.bullet_id, b.bullet_id) for entry in selection.resume.entries for b in
entry.bullets)`. `_build_entry` already sets `bullet_id` to the source id in *both* paths, so this is the
honest identity map the field documents, works for claims and predicates alike, and cannot desync from the
rendered résumé. The `load_declaration` re-parse and its `_entry_id` import are deleted. `manifest.py`'s
field comment is corrected to say the source id is a claim id **or** a fact id.

**Alternatives rejected.**

- **Keep the "independent oracle" by re-resolving facts for the predicate path.** That would duplicate
  `_build_entry`'s fact-resolution logic purely to re-derive ids the bullets already carry — more code for
  a field **nothing at runtime reads** (manifest.py: "Nothing reads this yet… makes staleness inspectable,
  not detected"). The cross-check the original comment wanted is unimplementable for predicates, because
  the declaration holds no per-bullet id to check against.
- **Rename the field to `source_to_bullet` / bump `MANIFEST_SCHEMA_VERSION`.** Scope creep: no consumer
  exists, v1's schema is frozen, and the name is clarified in the comment instead.

**Consequence.** `resume project` now runs end-to-end against the live bundle; `--posting 349` emits a
one-page résumé (pinned 3 + 3 project candidates) with a fully-populated manifest. A regression test with a
predicate-based declaration over the synthetic bundle (`test_a_predicate_declarations_bullets_map_to_their_source_fact_ids`)
reproduces the crash before the fix and pins the mapping to the bundle's own fact ids after. The downstream
`tailor run` still degrades to the untailored fallback (`reason=bullet_too_long`) — a separate, pre-existing
content matter (STATE open Q5), not part of this fix.

### What generalises

- **A green suite over one fixture shape is blind to every other shape.** The claims-path fixture agreed
  with itself; the predicate path — the only one production uses — had zero coverage. The first real input
  is the real test. (Mirrors `a-behaviour-change-needs-a-test-it-did-not-edit`.)
- **An "independent oracle" cross-check is worth nothing if it can only be built for the case that already
  works.** Task 19's re-parse guarded the claims path elaborately and left the predicate path — added
  later, by D-188 — to crash. When a second code path appears, the invariants written for the first must be
  re-checked against it, not assumed to extend.

---

## D-200 — Résumé heading formatting is declaration-driven; clickable project links are an optional code feature

*2026-08-15. Prompted by the owner reviewing the first emitted résumé and rejecting its formatting. The
owner pointed at job-apps' LaTeX as the reference. No change to the crash fix (D-199).*

**Context.** The first emitted résumé (D-199) rendered Experience as a single crammed bold line while
Education used the template's proper two-line macro — a documented "last cosmetic gap." Root cause was
**not** the template or the emitter: `latex.py:_subheading` already emits the correct
`\resumeSubheading{title}{dates}{company}{location}` (experience) and
`\resumeProjectHeading{...}{dates}` (project) macros **when the `Entry` carries structured fields**. The
live `projection.yaml` set only `heading: '{@display_name}'` per entry, so every entry hit the
`e.title is None` fallback (`\resumeSubheading{heading}{}{}{}`).

**Choice — populate the declaration, not the code (mostly).** Experience entries now set
`title`/`dates`/`subtitle`/`location`; projects set `title`/`subtitle`(tech)/`dates`. What is
fact-referenced vs literal is forced by what the bundle can render, not by preference:

- **Fact-referenced:** `title` (`{employment.title}`), `location` (`{entity.location}`), and — after D-201
  — company (`{employment.organization}`). All `owner_confirmed`, so `resolve_template` admits them.
- **Literal, of necessity:** **tech** (`technology.used` facts are `skill_ref`, which `render_value`
  refuses in a heading — `ADMITTED_KINDS` excludes it, and `resume_facts_for` returns only one fact per
  predicate anyway, never a joined list) and **dates** (`{employment.date_range}`/`project.start_date`
  render as raw ISO `2025-10-01`, not "Oct. 2025"). Literals are taken from the owner's job-apps résumé,
  his own ground truth. `projection.yaml` is config, never tracked, so employer/tech literals carry no
  generalization risk.

**Clickable project links — the one code change.** `Entry`/`EntryDeclaration` gain optional
`link_url`/`link_label`; `_build_entry` threads them; `_subheading`'s project branch composes arg 1 from
only the non-empty segments (`\textbf{name}`, `\emph{tech}`, `\href{url}{\underline{label}}`) joined by
` $|$ ` — which also fixed a latent wart (a subtitle-less project used to emit a stray empty `\emph{}` and
dangling `$|$`). The URL is emitted **verbatim** (escaping it would corrupt it); the label is escaped.
URLs with LaTeX specials are unhandled — fine for the github.com/apps.apple.com URLs in use. Reviewed
clean, `make check` green. **Links come from declaration literals** — no `entity.url` facts exist, and that
predicate is not owner-attestable, so fact-grounding links would need verified repository/public-record
evidence (deferred).

**Alternatives rejected.** (a) Editing the template macros — unnecessary, the macros were already correct.
(b) Fact-grounding tech/dates now — blocked by the `skill_ref`/ISO-rendering facts above; would need a
grammar change (a `technology.used`→joined-string expander and a month formatter), tracked but not done.
(c) Emitting per-tech bold or a link through the declaration — impossible, `_subheading` escapes those
fields, so injected `\textbf`/`\href` become literal text.

**Consequence.** `resume project` produces a résumé whose Experience matches Education's layout and whose
Projects read `Name | tech | link · dates`, matching the job-apps reference (minus per-tech bold). The
template's `\resumeProjectHeading` `\vspace` was loosened `-9pt`→`-5pt` to match job-apps spacing. Owner
re-approves `projection.yaml` (`approve-projection`) to make it live.

---

## D-201 — `employment.organization` is owner-attestable; the four org facts are resolved by a scoped owner attestation — Gate B 4 → 0

*2026-08-15. The owner directed this ("no employment docs needed. i am approving it") when the formatting
work (D-200) exposed that the company name was trapped in the four blocked org facts. The owner performed
the `approve` + `promote`; the agent staged and validated the draft. **This is the first time Gate B has
read 0 blockers since it was defined.***

**Context.** D-200's Experience `subtitle: '{employment.organization}'` refused with
`unresolved_placeholder`: the four `employment.organization` facts were `verification_state: unresolved` —
precisely the four `missing_review_state` Gate B blockers. Their predicate was `private_document`-only
(`owner_attestation_authority: none`), so the owner could not attest them, unlike the sibling predicates
`employment.title`/`date_range`/`team_size`, which already permit owner attestation.

**Choice.** Two hand-edits to a draft (there is no CLI for either — `edit-fact` only changes wording and
refuses a non-`owner_attested` basis; nothing sets `verification_state`): (1) **widen the
`employment.organization` predicate** in the owner's `policy/predicates.yaml` to mirror its siblings (add
the `owner_attestation` evidence class + `owner_attested` basis + `owner_attestation_authority:
owner_confirmed`); (2) **flip the four org facts** to `owner_confirmed` / `owner_attested`, citing a **new,
scoped** owner-attestation evidence record (`evidence.mit.employer-names.001`) created via `add-evidence`
(which recomputes the `evidence_set_digest` cleanly). Empirically validated: blockers **4 → 0**,
`0 error`; promoted as **revision 7** (`sha256:23ff1ef9…`).

**Why a fresh attestation, not the existing one.** `evidence.mit.owner-attestation.001`'s own text says it
"does not verify an employer record," so reusing it for the employer names was in tension. The new record
is scoped exactly to the four names ("…that these employer names are accurate. No third-party document is
relied upon."), authored to wording the owner explicitly confirmed (D-191 — no attestation is filed on the
owner's behalf that he has not read).

**Why this is legitimate, not a keystone bypass.** An employer *name* is owner-attestable personal history,
not an independently-verified employer *record*; the widen brings `organization` into line with its
siblings rather than inventing a weaker rule, and only four org facts exist in the bundle, so there is no
collateral effect. The keystone invariant is unweakened: the facts are now genuinely owner-confirmed with
evidence, not force-cleared.

**Consequence.** **Gate B is MET (0 blockers) on the live revision 7.** The company name is now
fact-grounded in the résumé rather than a declaration literal. The 10 `broken_reference` warnings on
`history/changes.yaml` (removed-source residue) persist, unchanged and non-blocking.

### What generalises

- **A cosmetic task can be the thing that finally forces a data-completeness fix.** Gate B sat at 4
  blockers for the whole program; wanting the company name to render is what made resolving them concrete
  and owner-authorised.
- **When a predicate is the odd one out among its siblings, that asymmetry is usually the bug.**
  `employment.organization` alone forbade owner attestation while `title`/`date_range`/`team_size` allowed
  it; the fix was consistency, and consistency is a defensible authority for relaxing a rule.

## D-202 — The skill-id slug collision (D-184 finding 3) is fixed: promotion refuses a grounded id built from more than one item, rather than silently merging

*2026-08-15. The owner chose "a deferred engineering item" over the résumé track's remaining owner-gated
levers; of the five listed, this was picked — the one confirmed correctness defect in the class CLAUDE.md
says fails first when a second user appears.*

**Context.** `_derive_skill_id` is lossy on purpose (D-180): `C++` and `C#` both slug to `skill.c`, on the
premise that identity is content-addressed, the verbatim item is kept as `original_display_value`, and
referential validation "is the promotion slice's job." D-184 finding 3 proved the promotion slice never did
that job: in `build_promotion`, `skill_id_to_display[skill_id] = …` and `skill_id_to_label[skill_id] = …`
are bare last-write-wins assignments, so two distinct items sharing one id collapse to a single
`SkillRecord` whose `canonical_name` is whichever came last, and the other leaves the graph with no
diagnostic. Two failure arms: both items grounded (a silent merge), or only one grounded (the surviving
skill silently takes the wrong name). Latent for Mit (his 58 items yield 58 distinct slugs); a
multi-tenancy defect, not a Mit defect.

**Choice.** Track the set of distinct `original_display_value`s per skill id, and in the skills loop — which
iterates only *grounded* ids (`supporting_by_skill`) — raise `PromotionError` when a grounded id was built
from more than one item, naming the id and every colliding item so the owner can rename or merge them in the
source. This mirrors the ambiguity refusal already a few lines away in the same function (`_entry_subject_kind`
raises rather than silently picking one of several legal subject kinds). `PromotionError` surfaces through
its single existing handler as `MODEL_VALIDATION_ERROR` — no new `IssueCode`, because the violation *is* "a
candidate set the deterministic promotion contract cannot represent," which is exactly that code's meaning.
Nothing is written: the raise precedes `_write_documents`.

**Why refuse, not the alternatives.** (a) *Disambiguate the slug* so `C++`/`C#` get distinct ids — reverses
D-180's content-addressing design and ripples into fact ids (`fact.….tech.<slug>`) and §6.4 referential
validation; a decision reversal, not a bug fix. (b) *Diagnose-and-drop* the loser with a recorded reason — a
quarantine, and the keystone requires every quarantine ship a drain, machinery an interactive authoring
command with the owner present does not need. Refusing loudly is the minimal fix and matches the surrounding
code. **Scoped to grounded ids on purpose:** two colliding items neither of which a bullet tags produce no
`SkillRecord` at all (like any untagged skill), so there is no loss to refuse — refusing there would be a
behaviour change beyond the finding.

**Evidence.** Two tests, one per arm (both-grounded merge; one-grounded corruption), each asserting exit ≠ 0
and a diagnostic naming `skill.c`, `C++` and `C#`. Both confirmed load-bearing by a mutation run (threshold
`> 1` → `> 2`: both fail with `skill_count=1`, the silent merge). The résumé track and every phase gate are
unmoved; this closes one of the two D-184 latent findings (finding 2, the partial-emission drop, remains —
it needs a report-model change, not a refusal).

### What generalises

- **"Referential validation is a later slice's job" is only true if that slice actually does it.** D-180
  delegated collision-handling to promotion; promotion's bare dict assignment silently didn't. A delegated
  guarantee needs a test that lands *where it was delegated to*.
- **A deliberately lossy function is safe only if every consumer treats the loss as ambiguity.** The slug's
  lossiness was fine in the abstract; the defect was a consumer that resolved the ambiguity by
  last-write-wins instead of refusing it.

## D-203 — The other two promotion slug-collision sites (entity_id, category_id) are closed the same way; a fourth (fact_id) is found open, not closed

*2026-08-15. The owner asked for a scope of autonomous work; a whole-tree multi-tenancy sweep (a ~156k-token
Explore agent) established that `src/boardwatch/` handles slug/derived-key collisions correctly almost
everywhere — `providers/registry.py`, `eligibility/{catalog,engine}.py`, `extract/taxonomy.py`,
`enumerators.py` all raise on collision, and every content-addressed id collides only on identical content
(intended dedup). **Every lossy-id-*creation* site in the whole tree is in `candidate_promotion.py`.** D-202
closed one (skill_id); this closes two more (entity_id, category_id). **Corrected at review time, before the
push: the sweep reported "three lines", but `grep -n "_slug(" candidate_promotion.py` returns FOUR id-building
lines. The fourth is a real, reachable collision and is left OPEN below — which is why this entry no longer
claims the class is closed.***

**The two defects (same class as D-202, one field over each):**

- **`entity_id` (`candidate_promotion.py`, `build_promotion`'s entry loop) — HIGH.** `entity_id =
  f"{kind.value}.{_slug(entry_id)}"`.
  Authored entry ids are deduped only case/punctuation-sensitively (`enumerators.py`), so `"Acme"`/`"acme"`
  or `"proj.alpha"`/`"proj-alpha"` or `"acme-2021"`/`"acme_2021"` pass dedup but `_slug` folds them to one
  `entity_id` → one document path → bare `employment_docs[path]=` last-write-wins → **a whole entity and all
  its facts silently vanish**, while `entity_count` still reports both (the CLAUDE.md "self-report is not
  verification / count through a different path" trap). Not caught downstream: the bundle dup-detector needs
  the id in two *different* documents, but here they merge to one path before anything is written.
- **`category_id` (`build_promotion`'s skills loop) — MED.** `_slug(label)` folds two distinct skill-group labels (`"Front End"`/
  `"Front-End"`) to one category id; the last label wins as `display_name` and both groups' skills merge into
  one category. Milder — the `SkillRecord`s survive (own `skill_id`); only the taxonomy grouping is lost.

**Choice.** Refuse both, mirroring D-202 and `_entry_subject_kind`: track the inverse map (`entry_by_entity_id`;
`used_categories` doubles as the category tracker) and raise `PromotionError` → `MODEL_VALIDATION_ERROR` when a
second distinct input maps to an existing id, naming both inputs and the shared id. Both raises precede
`_write_documents`, so nothing is written.

**Why no separate over-count guard.** The entity over-count (`entity_count` says 2, one doc on disk) was the
*mask*, not a second bug: once the collision is refused, each `entry_id` yields a unique `entity_id` → a
unique path → one doc, so `entity_count` equals what reaches disk by construction. Adding a count-integrity
assertion would be error handling for a now-impossible case (against the minimum-code rule), so it was not
added.

**Residuals, not fixed here.** (a) A `fact_id` slug collision on the *predicate local* (in `_entry_facts`,
where `counters` is keyed on raw `local` while the id uses `_slug(local)`) is unreachable with the seeded
catalog — it needs an adversarial predicate override. *(The original text also claimed "any such entity is
already subject to the entity-id refusal" — false, per (a2); retracted.)* (a2) **The missed fourth site,
found by the pre-push review rather than the sweep.** Both `fact_id` builders drop the entity **kind**:
`_entry_facts` uses `_slug(entity_id.split('.', 1)[1])` and `_tech_fact` uses `_slug(entry_id)`. So two entries of
*different* kinds whose ids slug-collide (`"alpha"`/experience vs `"Alpha"`/project) get **distinct**
`entity_id`s, **pass the new entity guard**, and then collide in the global fact-id namespace. No catalog
override needed — this is strictly more reachable than (a). It surfaces as an unhandled pydantic
`ValidationError` traceback (`UniqueSorted` on `supporting_fact_ids`, since neither `PromotionError` handler
catches it) or, in the weaker arm, as a `DUPLICATE_RECORD_ID` at a later `validate` — **never as a typed
refusal**. Left open here. (b) `_merge_categories`
(its `if category_id not in known`) still silently files skills under an *existing* catalog category whose `display_name` differs from
the user's slug-colliding label (`if category_id not in known`) — a rarer collision-with-the-pre-existing-
catalog case, left as a noted residual rather than expanded into `_merge_categories`.

**Alternatives rejected** (same as D-202): disambiguating the slug reverses D-180's content-addressing and
ripples into fact ids / §6.4; diagnose-and-drop is a quarantine the keystone would require a drain for.

**Evidence.** Two tests, each reproducing its silent defect before the guard (entity: exit 0 with
`entity_count=2` but one document on disk; category: `skill_count=2` with `category_count=1`), then refused.
All five `make check` components green — run component-wise because a game at ~447% CPU (load ~18-20) timed
out the monolithic gate twice: `generalization`/`index-check`/`lint`/`type` (mypy --strict, 273 files) fast,
`test` **6399 passed / 4 xfailed / 0 failed**, coverage 95.55%.

### What generalises

- **A defect found once is worth sweeping for its whole class before moving on.** D-202 fixed one slug
  collision; the sweep found two more of the identical shape in the same file — and, as valuable, proved the
  rest of the tree already refuses collisions, so the class is now fully contained in one file.
- **A sweep's enumeration is a claim, not a census — re-derive it mechanically before believing it.** The
  sweep asserted "three lines"; a one-second `grep -n "_slug("` returns four, and the missed one is *more*
  reachable than either residual the sweep did record. The pre-push review found it by running that grep.
  An enumeration asserted in prose and never re-run against the code is the "a component's self-report is
  not verification" trap one level up — the component here being a prior agent's summary.
- **The mask and the bug are not two bugs.** The entity over-count looked like a second integrity defect;
  it was the *symptom* of the collision, and refusing the collision removes it — no separate guard belongs.

## D-204 — A missing `pdfinfo` is a run-level fatal, not a laundered `COMPILE_FAILED`; the tool identity travels as typed data

*2026-08-15. First item of the autonomous engineering backlog STATE scoped after the Gate B track went
shippable. No owner input: the fail-safe direction was already settled doctrine, and the defect is a
correctness gap, not a product choice.*

**Context.** `_pdf_page_count` (`reports/tailor.py`) returned `None` for **three** causes — the `pdfinfo`
binary absent, `pdfinfo` exiting non-zero, output with no parseable `Pages:` line — and `_default_runner`
folded all three into `CompileOutcome(COMPILE_FAILED)`. So a machine with `tectonic` but without poppler
produced a degraded-or-empty run **every morning**, with the actual cause ("you never installed poppler")
named nowhere on the run path. One function above, the *same* class of fault was already handled correctly:
a missing `tectonic` returns `BINARY_MISSING`, which `evaluate_compile` carries to three `raise
RenderToolMissingError` sites as a run-level fatal with an install message. `doctor_cmd.check_pdfinfo`
already documented the hazard verbatim ("a hard dependency wearing a soft failure") — but `doctor` is
opt-in, so naming it in a diagnostic never fixed the run path. Stage 2's budget loop compiles once per
candidate, so `projection/select.py` read the same laundering (its module docstring said so).

**Choice.** Lift the `shutil.which("pdfinfo")` check out of `_pdf_page_count` and into `_default_runner`,
beside the tectonic preflight, returning the **existing** `BINARY_MISSING`. Every consumer of
`CompileReason`/`GateReason` was enumerated first: `evaluate_compile`'s if/elif chain, the
`DETERMINISTIC_GATE_REFUSALS` frozenset (correctly excludes it — environmental either way), the three raise
sites, and `projection/select.py`'s `_fatal_if_infrastructure`/`_reject_unless_ok`. **Not one of them
discriminates *which* binary is missing** — they all treat it as fatal — so a new enum member would have
bought nothing and cost an arm in every exhaustive match. The only thing that genuinely differed was the
human-readable install route, so **the tool identity travels as typed data**: a defaulted `tool: str | None`
on `CompileOutcome` and `GateResult`, set explicitly at both producers, read by a helper that selects the
message. The remaining two `None` causes stay `COMPILE_FAILED` — those really are compile failures.

**Fatal, not degrade.** CLAUDE.md chooses fail-safe direction per gate, and "systemic outage ⇒ fatal
(prevents the silent empty day)" is exactly this case. A missing render binary is not one bad posting; it is
the toolchain being absent, and degrading would reproduce the very silence the change exists to end.

**Alternatives rejected.** (a) *A new `CompileReason`/`GateReason` member* — ripples into every exhaustive
match for a distinction no consumer makes. (b) *Carry the message in the existing `log` string* — smaller
diff, but overloads a log field as a message channel, and the project forbids classifying behaviour by
message content. (c) *Warn and continue without a page count* — a résumé shipped without a measured page
count defeats P1a's whole gate, and Mit pins `resume_max_pages=1`.

**On the default.** `tool=None` falls back to the **tectonic** message, because that was this error's entire
meaning before the poppler preflight existed. Stated explicitly rather than left implicit, since a defaulted
field silently backfilling every caller has cost this project a real defect before.

**Evidence.** Seven tests; four failed before the change, the first of them asserting the literal defect
(`assert <CompileReason.COMPILE_FAILED> is <CompileReason.BINARY_MISSING>`). Includes the regression that a
missing *tectonic* still names tectonic — the arm a defaulted field would have broken — and pins that the
two remaining `None` causes still read `COMPILE_FAILED`, so the guard is narrow rather than a blanket. Two
docstrings that narrated the old laundering (`projection/select.py`, `doctor_cmd.check_pdfinfo`) were
corrected in the same change.

**Follow-up, from the pre-push review: `tool` is a closed catalog, not an open string.** The review filed it
as a non-defect note — no wrong-message path exists, since both producers sit in `_default_runner` and both
are tested — but the field was `str | None` while its reader maps *anything* that is not `"pdfinfo"` to the
tectonic message, so a third render binary passing an unlisted name would silently receive the wrong install
guidance. That is precisely the open-bucket shape CLAUDE.md rules out ("closed, versioned catalogs;
out-of-catalog is a failure, never a new bucket"). It is now
`RenderTool = Literal["tectonic", "pdfinfo"]`, declared beside `CompileReason` and used on both dataclasses
and the selector, so a third binary is a **type error at the call site** rather than a mis-worded runtime
message. Confirmed the constraint binds rather than merely being declared: `mypy --strict` rejects
`tool="poppler"` and `tool="xelatex"` on both dataclasses and still accepts `"pdfinfo"`.

### What generalises

- **Naming a hazard in a diagnostic command is not fixing it.** `doctor` had described this exact failure,
  in prose, for months. A check the user must think to run is not a guard; the run path needed its own.
- **Three causes collapsing into one outcome is laundering, and the environmental cause is the one that
  matters.** Two of `_pdf_page_count`'s `None`s were honest compile failures; the third was an install
  problem wearing their clothes. Separating them was the whole fix.

## D-205 — The fourth promotion slug-collision site (`fact_id`) is refused; the guard sits on the derived id, not on each builder

*2026-08-15. Found by the pre-push review of D-203, not by the sweep that wrote it. Same class, same shape
of fix; this one closes it.*

**Context.** D-203 recorded that `candidate_promotion.py` had **three** lossy-id-creation lines and that
refusing all three closed the class. `grep -n "_slug("` returns **four**. The missed one is the fact-id
namespace, and it is *more* reachable than either residual D-203 did record. Both builders drop the entity
**kind**: `_entry_facts` uses `_slug(entity_id.split('.', 1)[1])`, `_tech_fact` uses `_slug(entry_id)`.
So two entries of *different* kinds whose ids slug-collide — `"alpha"`/experience and `"Alpha"`/project —
survive the case-sensitive entry dedup, receive **distinct** `entity_id`s (`employment.alpha` vs
`project.alpha`), **clear the D-203 entity guard**, and then collide anyway. The tech fact is the reachable
arm because `.tech.` is hardcoded regardless of kind, whereas metadata and bullet facts carry kind-specific
predicate locals that differ. No catalog override is required.

Nothing merges silently at this layer, but nothing is *typed* either: the duplicate reaches `UniqueSorted`
on `supporting_fact_ids` as a bare `pydantic_core.ValidationError` that neither `PromotionError` handler
catches — an unhandled traceback — or, in the weaker arm, surfaces much later as `DUPLICATE_RECORD_ID` at a
subsequent `validate`, far from the cause.

**Choice.** One uniqueness pass over **every fact the run built**, placed after the tech-tag loop and before
document assembly, raising `PromotionError` → `MODEL_VALIDATION_ERROR` and naming the shared fact id and
both colliding subjects. **The guard sits on the derived artifact, not on each builder** — which is why it
also closes D-203's residual (a), the within-entry arm where `counters` keys on the raw predicate local
while the id slugs it. A per-builder guard would have required enumerating the builders correctly, which is
precisely what the sweep got wrong. The raise precedes `_write_documents`, so nothing is written.

**Alternative rejected: put the kind back into the fact id.** It would make the ids genuinely unique instead
of merely refusing ambiguity — but it changes **every existing fact id in every promoted bundle**, including
Mit's live revision 7 (107 facts, 33 bullets, an approved projection stamped against them). That is the
content-addressing reversal D-202 already rejected, at a far larger blast radius, for a collision no real
bundle has hit.

**Evidence.** One test, red first with the real defect — `ValidationError: duplicate list item
'fact.alpha.tech.python'` propagating out of `promote_candidates` — then refused with a diagnostic naming
`fact.alpha.tech.python`, `employment.alpha` and `project.alpha`. The promotion suite is 12 tests, 5 of them
collision refusals. D-203's entry and STATE were corrected before the push rather than after: the "whole
class is closed" claim retracted, residual (a)'s false "already subject to the entity-id refusal" clause
retracted, and a mis-stated test count fixed.

### What generalises

- **A sweep's enumeration is a claim, not a census.** "Three lines, all in one file" read like a measurement
  and was a summary. One `grep` refuted it in a second. This is "a component's self-report is not
  verification" one level up, where the component is a prior agent's prose — and the reviewer that caught it
  did so by re-deriving the list mechanically instead of reading the claim.
- **Guard the derived value, not each producer.** Keying the refusal on the fact id itself made the guard
  independent of how many builders exist — so it covered a residual nobody had connected to it, and cannot
  be defeated by adding a fifth builder later.
- **Cite code by symbol, not by line number — a fix invalidates its own entry's citations.** This change
  inserted ~23 lines near the top of `candidate_promotion.py`, silently shifting every line D-203 cited
  below it: `:289` → 326, `:377`/`:402` → 425, `:432` → 455, `:499` → 547. The claims stayed true; only the
  pointers rotted, and the D-203 entry ended up mixing citations from **two different snapshots** of the
  same file. The worst case is not a dead link but a live one — at HEAD, `:499` lands inside `_fact()`, so a
  session that trusts it reads plausible, unrelated code. CLAUDE.md already tells *readers* to confirm a
  line with `grep -n`; the writer's half of that rule is to cite a greppable symbol so there is nothing to
  confirm. Every citation in D-203 and D-205 was converted to a function name plus the distinguishing
  expression.

## D-206 — CSV export to stdout is written UTF-8 through a locally-wrapped stream

*2026-08-15. Autonomous backlog item; a pure encoding correctness fix that takes no position on the open
Windows-support question (Q3).*

**Context.** `export --format csv` wrote rows to bare `sys.stdout` while the `--out` path four lines below
already opened its file `encoding="utf-8", newline=""`. On Windows a *redirected* stdout's encoding is the
ANSI codepage, so any non-ASCII company name raised `UnicodeEncodeError` and killed the export. CI cannot
see it: every runner on the per-push path defaults to UTF-8.

**Choice.** Wrap the data stream **locally** — `io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
newline="")` — then flush and **detach** before returning. Detaching is load-bearing, not tidiness: letting
the wrapper fall out of scope closes the shared buffer in `__del__` and breaks every later write in the
process, including the command's own `console.print`. Global stdout is never mutated, so nothing else on the
process is affected; a substitute stdout with no `.buffer` falls back to the raw stream.

**Evidence.** The regression drives the command through a stdout whose text encoding is `ascii` and asserts
UTF-8 bytes reach the buffer; it failed before the change with the literal
`UnicodeEncodeError('ascii', '1,1,Société Générale,…')`. A second test proves stdout is still usable after
the export returns — the detach hazard — and a third covers the no-`.buffer` path.

### What generalises

- **A correct sibling four lines away is the strongest evidence a line is wrong.** `--out` had carried the
  right encoding and newline arguments all along; the stdout branch was not a hard problem, just an
  unexamined asymmetry. Inconsistency between two branches of one `if` is worth a look on sight.

## D-207 — The `STATE.md` trim executes D-149, and the fact-check that gated it corrects six stale figures

*2026-08-15. D-149 gated this trim on four prerequisites; all four had landed by 2026-08-15k, the last being
the review-loop caveat's carry into `STANDING-FACTS.md`. No owner input: the file's own header sets the
~170-line target and the "rewrite it, never prepend" rule, so executing it is not a new choice.*

**Context.** `STATE.md` had reached **231 lines** against a stated target of ~170. The overage was not
uniform — it was two seams of *narration*: the settled Gate A story, and the day-by-day 2026-08-15
résumé-track story (Gate B 7 → 4 → 0, the crash and its fix, the formatting rework, the four slug-collision
sites). Each is a past event with its own decision entry, and a read-first file that narrates its own history
stops being read.

**Choice.** Cut narration, keep standing fact. Three rules, applied in this order:

1. **A closed row is not a live blocker.** Three of the "Live blockers" table's eleven rows read `DONE` /
   `FIXED` (`resume project`'s crash, `pdfinfo`, CSV-to-stdout). A table whose rows are mostly closed teaches
   a fresh session to skim it. All three deleted; each is in `DECISIONS.md`, `METRICS.md` and `CHANGELOG.md`.
   The table now reads **5 rows, all genuinely open.**
2. **A standing fact belongs in `STANDING-FACTS.md`, not in STATE's blocker table.** Three rows were marked
   `standing fact` in their own Owner column. All three were *relocated*, not deleted — see below.
3. **Cite by symbol.** The one line citation the file carried, `store/queries.py:183-186`, became the symbol
   `reap_stale_runs`, verified with `grep -n` before the edit. `ci.yml:21-33` and `pyproject.toml:23` were
   retired the same way.

**Alternative rejected: cut to 170 exactly.** The file landed at **194**. What remains is standing fact, and
**no test reads `STATE.md`** (`grep -rn "STATE.md" tests/ tools/ Makefile` → nothing), so ~170 is a target,
not a gate. Cutting further would mean deleting facts to hit a number — D-149's failure, inverted.

**The three relocated facts, and why relocation rather than deletion.** A uniqueness census over the removed
text returned **0 lost** but flagged three claims as *demoted*: their only surviving copies sat inside dated
per-session `METRICS.md` records, and `CLAUDE.md` says neither log is read end to end. Demotion is one step
short of D-149's original failure, so all three moved into `STANDING-FACTS.md` §Gates and process:

- **"A push run is 9 CI jobs, not 12"** (D-151) — it existed in *no* other file, verified by grep. It now
  sits three bullets above the Gate A line reading "green on all twelve CI jobs", the claim it disambiguates.
- **"A contended gate produces FALSE failures."** §Process lessons already had a *weaker* neighbour —
  contention makes a gate slow and can SIGTERM it. It did not say a contended gate can go falsely **red**,
  which is the half that sends you debugging code that is fine.
- **"`generalization` scans git-TRACKED files only."** `DECISIONS-ARCHIVE.md` states the mechanism but draws
  the *opposite* consequence ("docs are scanned"), so it did not serve as a surviving copy.

**Six corrections, found by fact-checking what the trim KEPT.** The census checked what was removed; a
second, concurrent lens re-derived every number that survived. Everything below was already wrong at
`0a700d3` — the trim carried it forward, and the review is what caught it:

| Claim | Was | Is | Re-derived by |
|---|---|---|---|
| Live projection / bundle pair | projection `c5b237d9…`, bundle `0f794d81…` | projection `aa023678…`, bundle `23ff1ef9…` | `profile-bundle project` |
| Effective facts | 99 of 107 | **95** of 107 | the rule in `effective_fact_ids`, applied to revision 7 |
| Test count | 6,411 | **6,415** (6,411 pass + 4 xfail) | `pytest --collect-only -q --no-cov -n 0` |
| Spent draft names | 6 | **9** (`fmt-inspect`, `orgfix`, `orgfix-probe` missing) | `profile-bundle inventory` |
| Source size | ~46k lines | **~53k** (52,968) | `find src -name '*.py' \| xargs wc -l` |
| "'Windows' appears zero times in the docs" | as written, refutable by one grep | true of the **user-facing** docs only | `grep -rli windows docs/ README.md` |

The digest pair is the one that mattered. Both hashes were real and both were wrong: `c5b237d9…` is a
genuine approval stamp from 14:31 bound to `0f794d81…`, the *parent* of the selected revision. Six stamps
exist and only the newest binds, so STATE has been changed to name the live pair **and** to say that the
pair must be read off `profile-bundle project`, never off a stamp filename.

### What generalises

- **A trim is a deletion, and a deletion needs the evidence a code change needs.** "This is also in
  DECISIONS" is a claim; `grep` is the census. The mechanical form — `comm -23` over sorted identifier
  tokens between the old and new file, 257 removed tokens each traced to a home — is what a bullet count
  cannot do.
- **The dangerous line in a read-first file is the one with exactly one home**, and it is never the long
  paragraph. All three relocated facts were single-sentence cautions; everything verbose was already
  recorded three times over.
- **A line citation is not the only pointer that rots — a digest is one too.** `c5b237d9…` failed exactly
  as `:499` did in D-205: still resolving, still plausible, silently naming the wrong thing. Any identifier
  copied into prose from a mutable store needs a "re-derive it with *this* command" note beside it.
- **Two lenses find disjoint defects, again.** The census (what was removed) returned 0 lost and 3 demoted;
  the fact-checker (what was kept) returned 6 stale figures and 0 losses. Neither brief would have surfaced
  the other's findings, and the six corrections were invisible to the one actually editing the file.
- **A target is not a gate.** Ask what enforces a number before optimising toward it.

## D-208 — Dates render at month precision, and a projection may declare a two-fact range so an open-ended project is renderable at all

*2026-08-15. Mit's call to do the whole job: "i don't mind however much work/effort it takes. just do it
right." Format chosen by him from measured options: `Oct 2025 – Present`.*

**Context.** Dates were the last résumé field that could not be fact-grounded, and the reason was one
function arm. `grammar.render_value` emitted `value.start.isoformat()` for `date_range` and `value.value`
for `year_month`, so `{employment.date_range}` produced `2025-10-01 – Present`. Nobody puts that on a
résumé, so D-200 made dates **literal "of necessity"** and recorded the fix as owed: *"would need a grammar
change (a `technology.used`→joined-string expander and a month formatter), tracked but not done."* The cost
was three copies of every date — the fact, the `projection.yaml` literal, and the entity `display_name` —
of which only the literal rendered. Editing a date in the bundle changed nothing on the page, silently.
The eleven literals had also drifted into three typographies at once (`Oct. 2025`, `July 2024`,
`September 2023`).

**This is new work extending D-200, not a reversal of it.** A human-readable format was never rejected:
`Feb 2025 – Present` appears in the spec, the plan and `grammar.py`'s docstring only as the *illustration
of the hazard of deferring the choice*. Spec §4.1 rules the direction outright — **"Date *formatting* is
not authoring; the word for 'still going' is"** — so the format is ours and `open_range_label` stays the
owner's, with no default.

**Choice.**

1. **Month precision, locale-independent.** `format_month_year` renders from a hardcoded English tuple,
   **not** `strftime("%b")`. `%b` reads `LC_TIME`, so the same bundle would emit `Okt` or `oct.` on another
   machine — and boardwatch is built to run on its user's own machine, whoever that is. A rendering that
   reaches a live job application cannot depend on the environment.
2. **`dates` admits a declared two-fact range, not just a template string.** The bundle holds dates in two
   shapes and that is deliberate: employment carries one `date_range`, while `project.*` and `education.*`
   carry a `year_month` **pair**, because (D-177 finding 3) `YearMonthValue` holds one scalar and an
   extraction rule cannot yield both halves. Spec §4.1's answer for the pair was
   `'{project.start_date} – {project.end_date}'`, which has two defects: it makes the owner retype the
   separator per entry — so `RANGE_SEPARATOR` was never actually the single source it claims to be — and
   because an unresolved placeholder is fatal, **it cannot express an open range at all.** Two of Mit's own
   projects (Hookrail, StreakSync) have a `start_date` and no `end_date` fact, so before this they were
   renderable only by hand-typing "Present" beside an `open_range_label` that then governed nothing.
3. **An omitted `end` declares the range open; a NAMED `end` whose fact is missing stays fatal.** This is
   the fabrication guard and it is the whole reason the two cases are kept apart. Folding them would print
   "Present" over work that has finished — a false claim of ongoing employment, on a document that becomes
   Tier A's ground truth. Absence of a fact is not the owner saying "still going".
4. **`date` alone stays ISO.** No catalog predicate carries a `date`, so giving it a month rendering would
   invent a convention for a case that does not exist. `RANGE_ENDPOINT_KINDS` is likewise `{year_month}`
   only — exactly what the catalog's four paired date predicates carry — and excludes `date_range`, which
   as an endpoint would nest a range inside a range.

**Alternatives rejected.**

- **(a) Add a `project.date_range` predicate and migrate the seven projects.** Rejected: it fights D-177's
  deliberate pair design, leaves `education.*` inconsistent anyway, and would store a fabricated
  day-of-month, since a `date_range` holds full dates while the source facts are month-precision. Adding a
  predicate is cheap on paper (D-201's hand-edit precedent, no schema bump, no re-import) — the objection is
  not cost, it is that presentation would be pushed into the fact catalog.
- **(b) Format only `date_range` and leave projects on the two-placeholder template.** Rejected: it fixes
  nine of eleven entries and leaves the two open-ended projects unrenderable, which is the case that
  actually blocked fact-grounding.
- **(c) Let a missing end fact fall back to `open_range_label`.** Rejected as (3) above.

**Consequences.**

- The eleven live `projection.yaml` entries are now fact-referenced. Every rendered value is **semantically
  identical to the literal it replaced** — verified entry by entry against the facts before the change — so
  this alters provenance and typography, not content. Backup: `projection.yaml.bak-preground-20260815`.
- **The projection digest moved to `sha256:3de65ba5…`** (from `aa023678…`), so the owner gate has reopened
  by design (D-167) and Mit must re-run `approve-projection` on a controlling terminal before
  `profile-bundle project` or `resume project` will emit anything.
- The example declaration now demonstrates the open-range form, so the golden covers the new path end to
  end rather than only the arm that changed. Both its pin and the golden's needed updating —
  `make generalization` caught the one that was missed, which is what that check is for.
- **Spec §4.1's rendering table is superseded on two rows** (`year_month`, `date_range`). The table's
  reasoning still stands; only its chosen output moved.

**Lessons.**

- **A "literal of necessity" is a deferred defect wearing a justification.** D-200's literals were correctly
  reasoned given the renderer of the day, and the reasoning outlived the constraint — the entry even named
  the fix. Re-read what a decision said was *blocking* it before treating the decision as settled.
- **A recursive `grep` can silently reach a fraction of the tree.** Verifying a subagent's finding about
  job-apps, `grep -rl "" --include='*.tex' .` matched **7 files where `find` saw 14,693**, and a claimed
  date conflict looked refuted. It was real. `find -print0 | xargs -0 grep` restored it. A zero result from
  a recursive grep is not a negative result until the search's own reach is checked.

## D-209 — A fact that is simply wrong is retired by flipping its verification state to `rejected`; there is no delete, and `year_month` has no null form

*2026-08-15. Forced by Mit's ruling that FlickSwiper is ongoing: "im adding present because its live on
the app store and im maintaining it."*

**Context.** `fact.flickswiper.end-date.001` asserted `project.end_date = 2026-03`. The owner ruled the
project has not ended. Three things made this awkward and the combination is the reason this is written
down: there is **no `remove-fact` command** (`profile-bundle` offers `edit-fact`, `add-fact`,
`exclude-record`, `resolve-conflict` and nothing that deletes); **`edit-fact` cannot express "no end"**,
because a `year_month` value is regex-pinned to `YYYY-MM` and has no null form; and `exclude-record`
operates on an enumerated *source* record, not on a promoted fact.

**Choice.** Flip `verification_state` to **`rejected`**. `EFFECTIVE_STATES` is `{verified,
owner_confirmed}` (`models/base.py`), and `effective_fact_ids` filters on it, so a rejected fact is not
effective and therefore not résumé-citable — `projection.effectiveness._resume_facts` never yields it.
The record survives, which is what an append-only store should do with a corrected claim. This is the
pattern the shipped example bundle already models (`fact.packet-pantry.start-date.001` is `rejected`
beside an `owner_confirmed` successor), so it is a use of the existing design, not a new mechanism.

**No CLI does this** — it is a hand-edit to a draft, exactly as the four `employment.organization` flips
in D-201 were. `verification_state` has no setter, by design.

**The declaration change is NOT a substitute for the fact change, and this is the point.** Omitting
`end` in `projection.yaml` alone would have rendered `Jan 2026 – Present` correctly while leaving a fact
inside the bundle asserting the project ended in March. That is precisely the defect D-208 removed —
a copy of a date that nothing reads and nothing keeps honest. **Both had to move.**

**Consequences.** Draft `flickswiper-open` off revision 7; validation unchanged at **0 error, 0 blocker,
10 warning, 1 information** (candidate digest `5ef06a54…` → `674824ec…`, proving the edit landed while
Gate B stayed MET). Owner still owes `approve` → `promote` → `approve-projection`, in that order: the
projection stamp binds the bundle digest, so it can only be written after revision 8 exists.

**Lesson.** *A store with no delete needs a documented way to say "this is not true".* The absence of a
delete command is a deliberate property of a content-addressed, append-only bundle, but nothing recorded
how to retract a plain factual error under it — which is why this looked like a missing feature for a
moment rather than a use of `verification_state`. Reach for the state machine before the file.

## D-210 — A skill listed under two skill groups is refused, because a skill has exactly one category and arrival order must not pick it

*2026-08-16. Owner-gated since the D-202 sweep; ruled by Mit this session ("build the skill-refuse").*

**Context.** `candidate_promotion.py`'s skill-item loop built `skill_id_to_label[skill_id]` by bare
assignment over an **unsorted** `candidates`. A résumé listing one item under two groups — `Python`
under both `Languages` and `Backend` — grounds a single `skill.python`, and `SkillRecord.category` is
singular, so the record took whichever group arrived last. Silently: the promotion returned
`category='clean'`, `exit_code=0`, **zero diagnostics**, `skill_count=1`, `category_count=1`.

**This is reachable from an entirely ordinary résumé**, which is what separates it from its four
siblings. The enumerator refuses duplicate group *labels* but not duplicate *items*, and listing a
language under both a "Languages" and a framework/domain group is a normal thing to write.

**It is NOT the lossy-slug class of D-202/D-203/D-205.** No id is lost and no record is dropped. The
ambiguity is *which single category* the one record belongs to, so **some** choice is forced — which is
exactly why it was owner-gated rather than fixed in the sweep.

**The decisive argument is that neither existing guard can fire, by construction.** D-202's guard is
built on the adjacent line and looks like it covers this; it does not. It keys on
`original_display_value`, which is the **same string** in both groups, so its set has size 1. The D-203
category guard cannot fire either: `Languages` and `Backend` are distinct labels that never collide.
Only the label map observed the difference, and it was the one map never checked. *A guard one line away
from a defect is not evidence the defect is guarded.*

**Choice.** **Refuse**, naming the item, its id, and every group claiming it. The owner picks the
category; arrival order does not.

**Rejected: pick deterministically and document the rule** (e.g. first group in document order, or
lexicographically first). It is defensible and needs no author action, but it silently discards the
author's intent — the record would land in a category they did not choose, and nothing would ever say
so. Consistent with every sibling in this file, ambiguity the data cannot resolve is returned to the
owner rather than resolved by fiat.

**Implementation — the scalar map is gone, not guarded.** `skill_id_to_label: dict[str, str]` was
replaced by `skill_id_to_labels: dict[str, set[str]]`, the refusal reads its length, and the survivor is
unpacked (`(label,) = labels`). The defective construct is therefore **unrepresentable** rather than
merely detected. The unpack is total: a `skill_id` reaches this loop only via `skill_display_to_id`,
populated in the same branch as the labels, so the set is never empty; `> 1` is refused just above.

**Departure from the recommendation as delivered.** It proposed naming "the first-listed group". The
refusal names **all** groups, `sorted(...)`, exactly as its D-202 sibling does — strictly more
informative, and deterministic despite the unsorted iteration, which "first-listed" would not have been.

**Evidence.** TDD, red first: `test_promotion_refuses_a_skill_listed_under_two_skill_groups` failed
against the pre-fix tree with `OperationOutcome(category='clean', ..., exit_code=0)` and zero
diagnostics — the silent last-write-wins, observed rather than argued. Promotion suite 12 → 13 tests,
6 collision/ambiguity refusals.

**Cost to Mit today: zero.** His live `resume.yaml` holds 58 items across 4 groups (`Languages`,
`Frameworks`, `Tools`, `Databases & Networking`) with **no item in more than one group** (measured).
The guard changes nothing about his current bundle; it closes the path for the next user.

**Still open, deliberately.** `_merge_categories`'s `if category_id not in known` is a *different*
question — whether the seeded catalog or the author owns a category's `display_name` — and is not
settled by this entry.

**Lesson.** *A sibling guard is an argument that the case was considered, not that it is covered.* The
tell here was structural: two maps built on adjacent lines from the same match, one collected as a set
and checked, one overwritten and never checked. When guards are asymmetric, the asymmetry is the finding.

## D-211 — Correction: Windows runs only on the scheduled CI build, and that build has been red since 2026-08-14

*2026-08-16. A session-start ritual correction — STATE and the repo disagreed, so the repo won.*

**What STATE claimed.** Open question 3 held that "the one real bug is fixed (D-206), so what is left is
purely the support-posture claim, which no code change can settle." That is false.

**What the repo says.** `.github/workflows/ci.yml` builds its `os` matrix conditionally:

```yaml
os: >-
  ${{ (github.event_name == 'schedule' || github.event_name == 'workflow_dispatch')
      && fromJSON('["ubuntu-latest", "macos-latest", "windows-latest"]')
```

So a **push** run is 6 test jobs (ubuntu + macos × 3 Pythons) plus `gitleaks`, `perf` and
`generalization` — **9 jobs, none of them Windows**. Only `schedule`/`workflow_dispatch` gets the full
3-OS matrix, at 12 jobs. **This is the reconciliation for the familiar "all 9 per-push jobs green"**:
nine *is* the Windows-free count, and reading it as full-matrix coverage is the error.

**The split itself is not the defect — it is `D-151`, deliberate and owner-requested** ("I just don't
want to be waiting for 30-100 minutes on that Windows CI"), and it remains the right call. What D-151
did not establish is **who reads the nightly**. A cadence decision silently became a coverage decision
because nothing consumed the result: the corrective is watching the scheduled run, not restoring
Windows to every push. `workflow_dispatch` is a declared trigger, so Windows can also be run on demand.

**Measured standing.** The scheduled build has failed **three consecutive days** — `31934224040`
(`39f608a`), `31872269792` (`78f3021`), `31783422159` (`af1b524`) — always all three Windows jobs,
never any ubuntu/macos job, and never `gitleaks`/`perf`/`generalization`. The signature is stable
across days, so this is a standing breakage rather than a flake:

Resolved to test **names**, it is **two defects, not three** — two of the three sites are the same test
in two suites:

- **`test_setting_COLUMNS_reaches_the_module_level_console`** (`tests/unit/test_eligibility_cmd.py`) —
  `assert console.width == 137` gets **136**. An off-by-one in a test's own assumption about terminal
  width, and squarely the class of "a test that sets an env var must prove the setting arrives".
  Almost certainly a test defect, not a product bug.
- **`test_a_persistent_lockfile_left_by_a_killed_process_is_not_a_held_lock`** — present in **both**
  `tests/profile_bundle/test_profile_bundle_promotion.py` *and*
  `tests/profile_bundle/test_profile_bundle_rebase.py`. A command returns `bundle_lock_held` (exit 3)
  after the test SIGKILLs the holder, i.e. **the stale-lock reclaim does not recognise an abandoned
  lock on Windows**. This one may be a real product defect, and it is the one that matters: a user
  whose machine dies mid-authoring would be locked out of their own bundle with no documented drain.

**No fix attempted, deliberately.** Whether these are worth fixing depends entirely on the unanswered
support-posture question, which is the owner's. Fixing them first would answer it by fiat.

**How this was missed.** Every session checks the CI run *its own push* created, which by construction
is the Windows-free one, and reports "green". Nothing was watching the scheduled build. **A per-push
status check cannot observe a matrix its event does not instantiate** — so "CI is green" needs the
event named, or the job count checked, before it means what it sounds like.

**Lesson.** *A status check answers only for the matrix its trigger built.* The nine-job success was
true every time it was reported, and simultaneously never evidence about Windows. When a signal is
scoped by its trigger, the scope belongs in the claim.

---

## D-212 — Windows is a best-effort platform, the nightly gets a consumer, and D-211's "not a flake" is corrected

*2026-08-16. Answers STATE open question 3, open since 2026-08-13 and owner-gated. Executes D-211.*

**Mit's ruling: best-effort, tested, not fixed.** Windows stays in the nightly matrix so the signal
keeps accruing; the deterministic test defect is fixed; the Windows-only product race is marked and
documented rather than fixed; and the `OS Independent` claim is retired for something true.

**The correction D-211 owed.** D-211 read three days of red as one stable signature and concluded
"standing breakage rather than a flake". Pulling the actual job logs — nine Windows jobs, three runs
× three Pythons — shows that is right about one test and wrong about the other:

| Run | 3.11 | 3.12 | 3.13 | Lock test |
|---|---|---|---|---|
| `31783422159` | — | — | promotion | 1 of 3 |
| `31872269792` | promotion | **rebase** | promotion | 3 of 3 |
| `31934224040` | — | promotion | promotion | 2 of 3 |

`test_setting_COLUMNS_reaches_the_module_level_console` failed **9 of 9** — deterministic.
`test_a_persistent_lockfile_left_by_a_killed_process_is_not_a_held_lock` failed **6 of 9**, and
landed in the *promotion* suite five times and the *rebase* suite once. **A defect that moves
between suites and skips runs is a race**, not standing breakage. D-211 also said the test is
"present in both suites" and implied both were failing; it is present in both as source, and fails
in one or the other nondeterministically.

That distinction is not pedantry — it chose the tool. `strict=True` on a test that passes 3 times in
9 turns each XPASS into a fresh red nightly, so the marker is **deliberately non-strict**, and
conditional on `win32` so Linux and macOS — where the guarantee is actually claimed — keep running it
as an ordinary test that must pass. A non-strict xfail can never fail, which is normally the trap; it
is the right instrument only because the platform predicate quarantines it.

**Defect 1 — a test defect, fixed.** `rich`'s `Console.size` returns `width - self.legacy_windows`
on both the eager `COLUMNS` read and the live-lookup path: a legacy Windows console reports one
column fewer than `COLUMNS` names, reserving the cell that would otherwise auto-wrap. The assertion
was the bare literal `137`, so it read `136`. It now derives from `console.legacy_windows` — the
emitter's own attribute — rather than restating the platform test, because what the test exists to
pin is that **the env var arrives**, not what rich then subtracts from it. Reproduced locally by
constructing `Console(legacy_windows=True)`, which yields exactly the `136` the runners reported: the
diagnosis is by reproduction, not inference.

**Defect 2 — real, Windows-only, not fixed.** `locking.py`'s docstring rests the whole contract on
"the operating system is the only authority… the kernel drops a dead process's `flock` immediately".
**That premise is POSIX-shaped.** On Windows, `filelock`'s `WindowsFileLock._acquire` swallows
`EACCES` from `os.open` without setting the fd, so an acquire landing inside the killed holder's
handle-teardown window raises `Timeout` and is reported as `bundle_lock_held` — a lock nobody holds.
Blast radius is the two `bundle_lock` callers, `promotion.promote` and `rebase.rebase_draft`.
Because it is a race and not a lockout, **the drain is retrying the command**, which the README now
says in the same breath as the standing prohibition on deleting the lockfile as a repair — so the
keystone "every quarantine needs a drain" is satisfied by documentation rather than by code, which is
honest for a platform nothing is blocked on.

**The claim, retired.** `pyproject.toml` published `Operating System :: OS Independent` while
"Windows" appeared zero times in `README.md`, `SECURITY.md` and `docs/*.md` — its one occurrence
anywhere user-facing was a `CHANGELOG.md` line about the D-206 *bug fix*, which states no posture. It
is now `MacOS` + `POSIX :: Linux`, both verified against the official trove list. Windows is
**deliberately absent from the classifiers** rather than listed with an asterisk: a classifier cannot
carry the asterisk, and re-stating support that a red nightly contradicts is exactly the drift being
corrected. The qualification lives in `README.md`, which now names four caveats — no `pdfinfo` route
so résumé PDFs are unavailable, no desktop notifications, no Task Scheduler recipe, and the lock
race — and invites an issue, since the constraint is attention rather than a ruling that it should
not work.

**The actual corrective: `nightly-watch`.** D-211 diagnosed that nothing consumed the scheduled run's
result, so D-151's **cadence** decision silently became a **coverage** decision. A new job files a
GitHub issue naming the failed jobs when a scheduled run fails, comments on it on subsequent
failures, and **closes it when the nightly recovers** — an alert with no off-switch becomes a
permanently-open issue everyone scrolls past, which fails the same way as no alert. It reads per-job
conclusions from the API rather than from `needs`, because `needs` collapses a 3-OS matrix into one
result and *which* os/python failed is the entire diagnostic. Scoped to `schedule`: a
`workflow_dispatch` run is somebody already investigating.

**D-151 is untouched and still right.** Windows is not going back on the per-push path. The defect
was never the split.

**Lesson.** *A cross-platform contract written as prose is untested until the platform it excludes
runs it.* `locking.py` argued its portability at length — `filelock` over `flock`, explicitly for
Windows — and still rested on a POSIX guarantee in the sentence that mattered. The prose named the
right dependency and the wrong kernel.

---

## D-213 — Résumé bullets state what was built with metrics, never a story; and a bullet is parked by surface, not by an extra fact

*2026-08-16. Executes STATE "Owed next" item 2 for the first entity (FlickSwiper). Owner-ruled
wording; the mechanism findings are ours. Bundle revision 8 → 9.*

**Context.** Item 2 reserved bullet refinement for "a dedicated attended session … to figure out
what is the best way to showcase it". FlickSwiper went first: 4 bullets, 872 chars, two over the
220 ceiling, and — per this session's repo verification — one claim the repository contradicted.

**The owner's ruling on voice, stated over four corrections.** Bullets are for recruiters, not
readers: *"Resume is only for recruiters who wont have the time to understand what you have done,
just recognize keywords, metrics and so on wrt the job."* Therefore:

- **No storytelling, even when the narrative is true and verified.** The rejected phrasing was
  *"preventing a schema defect from wiping user libraries on upgrade"* — owner: **"this is
  storytelling. No need for it."** This retires the framing this session's own research argued
  for at length.
- **State what was built, with metrics.** Every clause names an artefact or a number.
- **Match the owner's existing résumé voice** (`~/Downloads/_Organized/Documents_PDF/Mit Sheth
  Resume_final.pdf`): verb-first past tense, natural prose clauses, metrics woven in. Parenthetical
  keyword dumps were rejected as *"dont make much sense at all, language wise"*.
- **Never repeat what the entry line already carries** — `projection.yaml` holds the entry's
  `subtitle` (tech stack) and `link_url`/`link_label`. No LOC counts.

**Alternatives rejected.** A 3-bullet default with a fourth fact "Stage 2 can admit when the JD
justifies it" — proposed by a peer session for another entity and endorsed by the owner as a
pattern — **is unrepresentable**: `select.py`'s `_subset_resume` filters `pool.resume.entries`, and
`pool.py:370` emits a bullet for *every* effective, résumé-surfaced fact matching the entry's
`bullet_predicates`. Selection is per **entry**; an extra fact renders unconditionally.
`conflict_group_id` is not the lever either — an unresolved group holds its candidates out of the
effective set entirely (`authoring.py:1922`), which is a disputed-values mechanism.

**The mechanism that does work: park by surface.** `effective.py:144` gates rendering on
`allowed_surfaces & legal_surfaces`, so dropping `'resume'` leaves a fact effective, attested and
validated while keeping it off the résumé; re-adding it restores the bullet. **No CLI does this** —
`edit-fact` takes only `--draft/--fact-id/--value` — so it is a surgical hand-edit of the draft
YAML. Never re-dump the file (`yaml.safe_dump` breaks the restricted loader); note the keys are
quoted (`'fact_id': 'fact…'`), which defeats a naive grep. This supersedes nothing in D-209 —
`rejected` is still how a *wrong* fact is retired; parking is for a *correct* fact not currently
wanted.

**Bold inside a bullet is a code change, not a wording change — deferred.** `latex.py`'s `escape()`
escapes `\ { }` and bullets pass through it verbatim (`latex.py:162`), so both `\textbf{}` and `**`
render literally. Enabling it needs a markup pass before escaping **plus** an update to
`_assert_escaped_round_trip` (`resume_gate.py:278`), the fabrication belt that compares
escaped-vs-escaped. The owner chose to ship plain text now and add markup in a later `edit-fact`
round rather than couple a settled wording decision to an unreviewed change to that belt.
`BULLET_MAX_LENGTH` measures **raw** `bullet.text` (`resume_gate.py:269`), so markers would count
against the 220 budget when it ships.

**Outcome.** FlickSwiper renders 2 bullets / 408 chars (from 4 / 872) on revision 9
(`sha256:566e7cf6…`), zero over ceiling, `profile-bundle project` exit 0. It is now the cheapest
entry in the pool. **The gate is not clear:** 7 bullets across 5 entries remain over 220, and
`nio-coop` (241) is in the **pinned** set, so the fallback still trips on every render.

**Amendment, same day — the rule had a cost nobody measured.** "Never restate what the entry line
carries" is right for character economy and **wrong for scoring**. Every scorer routes through
`effective_skills(bullet.text, …)` (`scoring.py`); `subtitle` appears nowhere in it, so a declared tech
stack earns **zero**. The taxonomy does not know `Firebase`, `Firestore` or `SwiftData` (all extract
`[]`), while `Swift` and `iOS` resolve. FlickSwiper's first two-bullet set therefore shipped at revision 9
having **lost `Swift` and `iOS/Swift (mobile)`** — its flagship iOS entity carrying no iOS signal into a
scorer that decides admission. Revision 10 restored both for **+11 characters**, giving a union that is a
**superset** of what the original four bullets earned at half the length. Two operational rules follow:
**re-measure extraction after any length trim**, and **check a candidate entity's skill union is
non-empty** — a bullet can be entirely score-invisible and nothing warns you. (Found by the hookrail
session on its own entity and confirmed here on shipped text.) For **pinned** entries the scoring
argument is void — `select.py`: pinned entries are *"emitted in declared order, never scored, never
dropped"* — but the keyword case still holds on ATS grounds, and their characters gate how many
candidates are admitted at all.

**Lesson.** *A verified finding is not automatically a résumé claim.* This session spent its
depth establishing that the migration defect was caught pre-release rather than in production —
a correction worth making — and the owner then removed the entire clause as narrative. The
research was still necessary (it stopped a contradicted claim shipping), but "what is true" and
"what belongs on the page" are separate questions with separate owners.

---

## D-214 — Hookrail's bullets: a merged perf-plus-chaos claim, a keyword measured back in after a length trim, and a correct-but-unwanted bullet parked

*2026-08-16. Executes STATE "Owed next" item 2 for the second entity (Hookrail). Bundle revision
10 → 11. Follows D-213, which established the voice and the parking mechanism.*

**Context.** Hookrail rendered 4 bullets / 848 chars with one at 251 (over the 220 ceiling) — the
second most expensive entity in the pool. It is the owner's non-mobile SDE anchor, so the brief was
to decide how it is best showcased, not to trim it to length. Research is in
`~/dev/portfolio-website/wiki/reporesearch/hookrail/` (8 files).

**The performance claim was the risk, and it survived.** The NIO pass found bullets citing
technologies absent from the codebase and percentages that appeared only in résumé `.tex` files
citing themselves, so `200 events/s, ~58 ms p95, 0 lost / 0 duplicate` was treated as unverified.
It is backed by `docs/baseline/2026-06-11.md`: two physical machines (M1 generator → M4 target),
600 s sustained, versions pinned at `1a4130b`, and a committed reproducible harness
(`scripts/baseline/run.sh <fanout> <rate>` + `report.sql` + `deploy/k6/ingest.js`). `report.sql`
counts duplicates from the **receiver's own ledger**, calling the Postgres-side count a proxy —
the deliverable counted through a different path than the one that produced it.

**But a real artifact does not make a claim whole.** `58 ms` is the **fan-out 1** row; fan-out 3 at
the same rate is **1.094 s p95**, published in the same table. `0 lost / 0 duplicate` holds at both.
The numbers are also **308 commits behind HEAD** and have never been re-run. *A metric can be true
and selectively quoted; verify the number, then read the whole table.* The owner kept the figure
under D-213's scanning-surface rule — a real number for a real configuration outweighs a nuance only
an interviewer would raise — reversing this session's own recommendation to drop it.

**The largest finding was unclaimed work, not a false claim.** D-191 parked Hookrail's CI-chaos
suite for want of approved wording. It is 12 test functions / 2,618 lines including `k8schaos`
experiments that kill the CloudNativePG primary and the Redis Sentinel master mid-load and assert
RPO=0. Verified green **at the job level** on HEAD (`ae6ef46`, run `29769046246`): jobs `chaos`,
`pg-failover` and `redis-failover` all `success`. Job-level checking was necessary — those jobs are
`if: github.ref == 'refs/heads/main'`, so a green PR run contains none of them, and that run's own
workflow conclusion reads `cancelled` (only the GHCR push was). The implementation exceeded its
spec: `SPEC.md` §11 says *"single node — no failover claimed at this tier"*.

**A length trim silently deleted a scoreable keyword.** Measured against the real taxonomy
(`load_taxonomy` + `load_equivalences`, not a fixture), the old `.003` extracted `[]` — no
scoreable skill at all. A draft of its replacement said "automated **Kubernetes** chaos tests"; the
trim pass removed "Kubernetes" purely for characters, deleting the only route by which that skill
reached the scorer, since D-213's amendment established `subtitle` is never scored. Restored at
**zero net cost** by trading "under load". **Re-measure extraction after any length trim** — this is
the second entity where the rule paid, and the first where the loss was self-inflicted.

**Parking is one-time when the bullet is dropped, recurring when it is toggled.** The fourth bullet
(Python SDK / React dashboard / OTel / Grafana / GitHub Actions) was first proposed as a per-JD
toggle. Under `mean_per_bullet` a fourth bullet divides by a larger denominator, so it **dilutes**
on a Go/Postgres/Redis JD (2.00 → 1.75) and **lifts** on a Python/React one (0.33 → 1.00) — a real
trade, but one costing a hand-edit of draft YAML on every flip, because no CLI writes
`allowed_surfaces`. The owner chose to drop it outright, which makes the same hand-edit **one-time**.
`.004` is therefore **parked, not rejected**: every claim in it is verified true, and D-209's
`rejected` is for a fact that is *wrong*.

**Alternatives rejected.** Qualifying `58 ms` with "(single subscriber)" — spends characters on a
distinction a recruiter will not parse and invites the fan-out-3 question anyway. Keeping "218 Go
files" — true but double-counting, since **132 of the 218 files are the test files** (86 are source);
`361 tests` is the figure that survives scrutiny. Buying `Docker` for 11 characters — leaves 1
character of headroom and reads against the owner's voice.

**Outcome.** Hookrail renders **3 bullets / 626 chars** (from 4 / 848), zero over ceiling, on
revision 11 (`sha256:ccd4d741…`), projection digest `sha256:950fbd47…`, `profile-bundle project`
exit 0. Skill union `Go, Kubernetes, PostgreSQL, Redis` (was `Go, PostgreSQL, Redis` across four
bullets). Pool-wide: **7 of 30 bullets over 220**, down from 8 of 31. **The gate is still not
clear** — `nio-coop` (241) remains pinned, so the fallback trips on every render.

**Corrections this session made to its own earlier reasoning.** Three, all recorded in the wiki
folder: `58 ms` drop → keep; narrative framing → keyword density; and "author a fourth fact Stage 2
admits per JD" → unrepresentable, park by surface (independently verified here against
`select.py`/`pool.py` before adoption, per D-213).

---

## D-215 — StreakSync ships two bullets; and a working-tree control cannot validate a historical absence

*2026-08-16. Executes STATE "Owed next" item 2 for the third entity. Owner-ruled wording under D-213's
house style. Bundle revision 11 → 12. A follow-up keyword fix is staged, not promoted.*

**Context.** StreakSync was the most expensive entity in the bundle: 4 bullets, 1,012 chars, **3 of them
over the 220 ceiling** (233/285/289). Its four claims were audited against the canonical repo before any
wording was drafted.

**The owner's ruling.** *"we'll go with two bullets"*, and — rejecting the metrics this session had
proposed — *"i dont need to advertise loc, commits across months etc."*, with the wording directed to
follow the shape of his existing résumé entry. Shipped at **2 bullets / 415 chars, zero over ceiling**:
a modular-SwiftUI-architecture bullet (`@Observable`/`NavigationCoordinator`/`AppContainer` DI, 446
XCTest tests) and a Share-Extension bullet (a dedicated parser for each of 15 games, App Group queue,
Darwin notifications, iOS 26 transitions). Bullets 3 and 4 are **parked by surface** per D-213, not
deleted; the Firestore-security theme was ceded to FlickSwiper, whose 76-case count is correct where
StreakSync's "110-case" was not (measured: **109**).

**The method finding, which cost a wrong published claim.** This session reported "Heardle" — a game on
the owner's résumé — as a fabrication of the SensorKit class, having run **two controls that both
passed** (`quordle` 75 hits; `wordhurdle` 3, a game defined in the catalog but *not* shipped, which
appeared to prove the instrument reached even obscure content). It proved nothing of the kind.
`git log --all -S'eardle'` returns 6 commits: Heardle was a full implementation (`parseHeardle`,
`Game.heardle`, a `#?Heardle\s+#?` regex) present from the first commit and removed 2025-10-15. The
résumé PDF is dated 2025-10-05, so the claim was **accurate when written**.

> **A control test is only evidence about the corpus it ran against.** A working-tree control cannot
> validate a claim about history, because it answers a different question. For any "X is absent" claim
> against a repo with history, the pickaxe is not optional. This generalises D-213's sibling finding and
> the NIO session's "the working tree is not the repo" (unmerged branches): both are the same error with
> different corpora — deleted code, and never-merged code.

Two further absence claims here needed the same correction (`GameResultIngestionActor`: 0 at HEAD, 10
commits in history; `glassEffect`: 0 at HEAD, 5 in history). Only `backgroundExtensionEffect` was
genuinely never present.

**Authorship must be verified, not assumed — and the check discriminates.** The NIO session found its
bullet crediting the owner with a colleague's never-merged feature (18 of 18 commits by another author).
The same check here: `git log --all --format='%an' | sort | uniq -c` returns **259 of 259 commits by
Mit**, across three of his own identities, with the repo's first commit his own. So "Designed and built"
is literally true on StreakSync where it overclaims on NIO. **Run the check per entity; do not
generalise either result.**

**Owed, staged, not promoted.** Re-measuring extraction after the trim (per STATE's standing warning)
found the new set **lost the bare `Swift` token**: the replaced bullet carried "Swift 6/SwiftUI" and
extracted `{Swift, iOS/Swift (mobile)}`; the new pair extracts only `{iOS/Swift (mobile)}`, because
`SwiftUI` does not resolve to `Swift`. This is the identical regression D-213 recorded for FlickSwiper's
first 2-bullet set, reintroduced by a different route — evidence the warning needs to be a step, not a
note. Draft **`streaksync-swift-keyword`** restored it for **+11 chars** ("Built a Share Extension **in
Swift 6** with…", 214 chars). **Approved and promoted the same session — revision 13
`sha256:ab48d3f7…`, `project` exit 0**, entity union back to `{Swift, iOS/Swift (mobile)}` verified
from the rendered output. StreakSync final: **2 bullets / 426 chars, zero over ceiling.**

**Alternatives rejected.** Putting `Swift 6` in bullet 1 instead — lands the bullet at exactly 220, which
passes the strict `>` but leaves no margin for any later edit.

---

## D-216 — SAKEC's bullets are ruled and worded but NOT promoted; a private repo makes a disk sweep's negative worthless; and keywords are chosen by diffing the résumé's own Skills section

*2026-08-16/17. Executes STATE "Owed next" item 2 for the fourth entity, and the first one that is
**pinned**. Owner-ruled wording under D-213's house style. **Bundle unchanged — still revision 13.**
Research: `~/dev/portfolio-website/wiki/reporesearch/sakec/README.md`.*

**Context.** SAKEC was briefed as a documentary entity: "a repo search has already been run and found no
SAKEC source code." That was correct about local disk and wrong about the world. The code is
`github.com/Sakec-Marathon/Sakec-Marathon-app` — **private**, Flutter/Dart, 256 commits, 11
contributors, first commit 2021-02-21. Two prior sweeps across `/Volumes/mit` (931 GB) and `/Volumes/T9`
(181,776 files, control passed) had returned clean negatives, and both were right within their scope.

**The first method finding: a private GitHub org reports itself empty.** The org's public page renders
*"This organization has no public repositories"* and *"no public members"* — indistinguishable, to a web
fetch, from a genuinely empty org. `gh repo list Sakec-Marathon` returned both repos in one call. So a
disk negative plus a public-page negative can look like two independent confirmations of absence while
being one permissions artifact. **Establish the canonical repo through `gh` before reading any
filesystem silence as evidence** — this generalises D-215's pickaxe finding from "the working tree is
not the repo" to "the machine is not the account."

**What the code showed.** Measured at `95fb84b` (2021-04-23, the end of his tenure — **not** `HEAD`,
which is a 2022 rewrite that would understate him), Mit authored 1,052 of 7,862 Dart lines, 4th of 6, and
was the **top iOS contributor** (10 of 21 `ios/` commits, sole `Podfile` author, vs 3 `android/`). But
`git log -S` put **every** claimed feature on other authors: `pedometer` and the accelerometer speed
sensor on Miloni Gada (2021-02-23/24), `addOffense` and the distance/step checker likewise. A `Scaffold`
control confirmed the pickaxe does attribute code to Mit, so the negatives were real.

**Corroborated independently, which is the result worth keeping.** Tracing the dated résumé lineage
2022→2026 *without* reference to the git history reproduced the git history: Mit's own **2022** résumé
describes him as a *"Front-End developer"* on a *"flutter"* app. "Android" first appears Aug 2023,
the sensors Aug 2023, **"over 1,000 active users" Jan 2024** — ~3 years after the work. **The arrival
date of a claim is itself cheap evidence**; an unbacked number that first appears years late is the
signature. Two other entity sessions reached the same technique independently.

**The owner's rulings — all four, and they close the attribution question.** *"this is fine. it was a
team effort so I can own it too."* Team ownership of a shipped team feature is accepted, so §5's
authorship split is context, **not a defect list**. Also: the title stays *"Software Engineer Intern"*
(*"acceptable even if the cert says otherwise"*) despite the 2021 certificate and the app's own credits
screen both reading **"App Developer"**; **"over 1,000 active users" stays** (*"this is accurate, take my
word for it"*) — which is exactly what `owner_attested` encodes, so no basis change was needed; and
**two bullets**.

**"offense" is vindicated, not a typo.** The app ships a three-part **offence** taxonomy — location,
speed, and distance-to-step — because the marathon is *virtual*, so anti-cheat is the product. Mit wrote
the participant-facing rules (`rules.dart`, 250/398 lines his). The one claim changed on evidence and
**not** covered by any ruling is **`gyroscope`, dropped: 0 occurrences in the repo by any author**, so it
is wrong for the team, not merely misattributed.

**The second method finding: pinned entries are never scored, which inverts the keyword argument.**
`select.py:4` — *"Pinned entries are emitted in declared order, never scored, never dropped."* So
`_bullet_coverage` (`scoring.py:57`, bullet text only, never `subtitle`) is **irrelevant** to a pinned
entity: its keywords cannot move any score. Their value is entirely **external ATS and human
recruiters**. Meanwhile `select.py:7-8` grows candidates into the pinned set one at a time, stopping at
the first that overflows the page — so **pinned characters are spent before any project competes**.
Shortening a pinned entry never helps that entry; it buys candidate-admission headroom on every posting.
A corollary for triage: `nio-coop`'s 241-char bullet breaks **every** render because it is pinned, while
the other over-ceiling bullets only bite when their candidate happens to be admitted.

**The third method finding: choose keywords by diffing the résumé's own Skills section.** Asked to spend
the ceiling headroom on keywords, the obvious additions were worthless: *Flutter*, *Dart*,
*Android Studio* and **Firebase** are **already in the Skills line**, so repeating them buys an ATS
nothing. The four added — **accelerometer, pedometer, GPS, Google Maps** — appear nowhere else on the
résumé and are all verified in code (`sensors_plus`, `pedometer`, `location` in 4 Dart files,
`google_maps_flutter` in 17). "accelerometer and pedometer APIs" also replaced "sensor-based algorithms"
for **accuracy**: step count comes from `pedometer`, speed from the accelerometer.

**Final wording, owner-selected: 2 bullets / 161 + 187 = 348 chars** (from 355), zero over ceiling.
Bullet 1 delivers the Flutter Android+iOS app with the sensor APIs and the attested user count; bullet 2
carries offence detection via GPS and Google Maps. **The saving comes entirely from deleting the
duplicated measurement list** old-`.002` restated — the two bullets had named the same three
measurements and ended in the same fairness clause, ~one bullet of information across 355 chars.

**Authored on the owner's instruction, after research finished read-only.** The brief scoped the session
read-only because **the bundle takes no lock** and three sibling refinement sessions were live against it;
research therefore ran entirely read-only, and the constraint was lifted only by an explicit *"promote the
bullets now too"*. Draft `sakec-bullets` was cut from revision 13, took the two `edit-fact` calls, and
**validated identically to the pre-edit baseline at both tiers — 0 error / 0 blocker / 10 warnings / 1
information** (baseline captured *before* the edits, because `_catalog_admits` is a diff and cannot see
removals). `.001.r2` and `.002.r2` supersede the originals per D-190. **No fact is retired** — the bullet
count is unchanged, so no `allowed_surfaces` parking (D-213) and no `rejected` ruling (D-209); this is the
cheapest authoring shape the bundle admits.

**Extraction was re-measured, the step STATE flags as having already fired twice.** Entity skill union
**`{Android (mobile)}` → `{Android (mobile), Flutter, iOS/Swift (mobile)}`** — **nothing lost, two
gained**, so unlike D-213's FlickSwiper and D-215's StreakSync this trim introduced no keyword
regression. Note bullet 2 extracts `[]` both before and after: *GPS* and *Google Maps* are not among the
taxonomy's 115 patterns, so those two additions are external-ATS value only and move nothing internally —
which is consistent with the pinned finding above, where nothing internal was ever at stake.

**`approve` and `approve-projection` were deliberately left to the owner**, because they record *his*
attestation of exact content on a controlling terminal; an agent running them would be manufacturing the
owner approval the whole `owner_attested` basis rests on.

**PROMOTED by the owner: revision 13 → 14 `sha256:b72158a9…`, projection re-approved, `project` exit 0**
(new projection digest `sha256:950fbd47…`). Verified through the **rendered `project` output rather than
the draft that produced it**: SAKEC ships **2 bullets / 161 + 187 = 348 chars, zero over ceiling**, with
`.001`/`.002` superseded and dropping out of the render on their own. **SAKEC is closed; the wording is
final and must not be re-derived.**

**Alternatives rejected.** *One merged bullet* (~200 chars, −155) — the redundancy argument survived, but
the original case for it rested on bullet 002's distinct content being someone else's work, which the
owner's team-ownership ruling voided; he chose two. *Adding `Cloud Firestore`* (novel, 18 Dart files) —
would push the pair to 375, past the 355 status quo, and on a pinned entity that is paid in
candidate-admission headroom. *Claiming iOS ownership* (*"and owned the iOS build"*, 338) — the
strongest verifiable claim in the entity, but it displaces the *Android* keyword; hold it for iOS-targeted
variants. *Correcting the title to "App Developer"* — owner declined. *Deleting the user count* — owner
attested it.

## D-217 — Crop-RF's numbers all verify against the paper, but its award count, its host and its authorship do not; and `grep` here silently honours `.gitignore`

*2026-08-16/17. Executes STATE "Owed next" item 2 for the fifth entity. Owner-ruled wording under
D-213's house style. **PROMOTED: revision 16 → 17 `sha256:1e4c2420…`.** Research:
`~/dev/portfolio-website/wiki/reporesearch/crop-rf/README.md`.*

**Context.** crop-rf is the bundle's only peer-reviewed and only ML entity, so it is never
interchangeable, and it was the only entity briefed with a **primary published source**: the 5-page
ICACTA 2023 paper. That inverted the usual outcome. Unlike NIO (SwiftUI/SensorKit contradicted) and
unlike SAKEC (every feature attributable to teammates), **every technical number in the bullets checked
out**: 99.54 / 98.90 / 97.45 (Table 3, p.4), 676,425 and 2,200 samples and "three government datasets"
(§3.1, p.2), and **FastAPI is named in the paper itself** (p.3 §IV). Mit is 4th of 5 authors. The
failures were all in the *non-technical* claims — exactly where nobody was looking.

**The award count is contradicted by an institutional source, which is a different kind of evidence.**
"Best Paper among 300 presentations" appears in Mit's résumé, `professional-summary.md` (3×),
`certifications-and-awards.md`, `crop-recommendation.md` (2×), `v1-content-archive.md` (2×) and the
bundle fact — every occurrence one of his own documents citing another. The host college's official
report (`djsce.ac.in/docs/Report on ICACTA 2023.pdf`) states **511 papers submitted, 288 reviewers, 206
selected, 120 registered**. Nothing is 300; the field was **120**. **The join that makes this
admissible is the IEEE Catalogue Number**: the report's banner reads *"IEEE Catalogue Number 58201"* and
the paper's DOI is `10.1109/ICACTA58201.2023.10393121` — same conference, provably, not a
similarly-named one. **Prefer a source outside the owner's own document lineage; a catalogue number or
DOI fragment is often the cheapest way to bind one.** The replacement, *"among 120 papers presented from
511 submitted"*, is stronger than the claim it replaces because it is checkable.

**The award itself was NOT disproved, and the owner attested it.** The conference report never
enumerates awards, and a sweep of **145,853 PDFs/images** found no ICACTA certificate (the certificates
folder holds SIH22, Nakshatra, SAKEC Marathon, Blockchain, Ethical Hacking, Coursera — not this).
`mdfind "ICACTA"` and `mdfind "Best Paper"` returned only his own résumés, `sections.tex` files, wiki
pages and bundle YAML. Ruled: *"Yes — I have proof."* So **Best Paper stays**, and the distinction
between *contradicted* and *unsubstantiated* did real work here — the count died, the award lived.
**CLOSED 2026-08-17: the owner holds the certificate and ruled the question resolved** (*"that's fine and
resolved. i have it."*). It was not handed over and no evidence record was cut, deliberately — the claim
stands on `owner_attested`, which is what that basis is for. **Do not re-open this or re-run the
certificate sweep**; the searches recorded above are history, not an open lead.

**"on AWS" is contradicted twice, from independent directions.** The project poster
(`Fasal_Poster_FINAL.pdf`) states **"SERVER: Heroku"** under a technology stack that also names Flutter,
Firebase and Cloud Firestore. And in the Flutter client, `uurl` has **exactly one distinct value across
all 67 commits** — `http://10.0.2.2:8000`, the Android emulator's loopback alias to the dev machine,
matching `uvicorn.run(app, host='127.0.0.1', port=8000)` in `soilAPI.py`. `keys.dart` exists in **62 of
67** commits and never held an EC2, ngrok or Heroku host. The backend has no Dockerfile, no
`requirements.txt`, no Procfile. A precise grep over all 67 commits returned zero cloud-host hits with a
`10.0.2.2` control returning hits. **A bare `aws` substring grep is useless** — it matches inside
`styles.xml` ("draws") and raw JPEG bytes.

**The attribution was inverted, and the client is public.** The brief called `APIS-main` a *candidate*
backend; six independent joins make it conclusive (route names `/recommend` + `/predictRainfall` match
the Dart client exactly; 2 pickles for the paper's "2 machine learning models"; `predict_proba` → top 5
matching p.4 §5.2). The **client** is `github.com/NotKashish/fasal` — public, Dart 157,891 B, 67
commits — where **Mit is the top contributor, 24 of 67 (36%)**, his best ownership position on any
collaborative artifact examined. But his commits are UI, auth, profile, the **four-step input form**
(`form_page.dart`, 5 commits) and **EN/HI/TA localisation** (`+1,527/−153`); the ML-integration commit is
Miloni's, and **no training code exists anywhere**. So bullet 002's *"Trained Random Forest models"* was
unattributable while bullet 003 — the app he led — was worded as a delivery afterthought. **The fix was
to swap which claim carries the weight**, not to add anything.

**Method finding 1 — `grep` in this environment is a shell function execing `ugrep --ignore-files`,
which silently honours `.gitignore`.** This produced a wrong finding that was published before it was
caught: the "300 presentations" blast radius was first reported as **7 places**. Re-measured with
`command grep`: **8,891 of 14,719 `.tex` files** under `~/dev/Job apps` — the shim returned **2,263**, a
**4× undercount, exit 0, no warning**. `type grep` confirms the shim. Already recorded in memory
`recursive-grep-can-silently-truncate.md` with the same root cause (`Job apps/.gitignore` contains
`/APPLY_QUEUE/`), and it has now bitten **at least three sessions independently** — so the brief a
session receives is not enough; **use `command grep` or `rg --no-ignore` for any count you intend to
quote, and print the denominator beside it.**

**Method finding 2 — the correction does not land in boardwatch alone.** Of those 8,891 files, exactly
**3 are git-tracked source templates** — `Job apps/sections_ios_base.tex:56`,
`sections_ios_template.tex:57` (which also says the wrong *"IEEE Journal"*), `summary_sde.tex:4` — and
job-apps renders Mit's résumés **daily** from them. Downstream: 6,536 in `resumes/`, **1,112 in the live
`APPLY_QUEUE`**, 1,148 skipped, 87 archived. **Fixing a bundle fact does not stop a claim shipping while
job-apps is the live path.** Owner ruled this out of scope: *"ideally we want to retire job apps once
boardwatch is finalized. So this is fine, not to worry about."* Recorded so no session re-raises it.

**Method finding 3 — read the résumé he actually sends before proposing a bullet count.** `Mit Sheth
Resume_final.pdf` uses **two** bullets for crop-rf, and **the accuracy comparison appears on no résumé
he has ever sent** — 99.54/98.90/97.45 is a bundle-era addition. So the bundle had drifted *up* from the
résumé, and the burden of proof was on keeping the third bullet, not on cutting it. That résumé also
ends the entry with a hyperlinked **"DOI Link"**, so crop-rf having no `link_url` was an **import
regression to undo**, not a new idea to evaluate. Relayed to the sibling sessions and adopted as standing
guidance.

**Method finding 4 — two independent measurement routes lied, in opposite ways.** (a) The 2022-era model
pickles need **two** pins to load: `scikit-learn==1.0.2` alone fails on a scipy `dlopen`, which reads
exactly like a corrupt artifact; `scikit-learn==1.2.2` + `scipy==1.11.4` + `numpy<2` works, and confirms
`soil_rfc.pkl` is a **RandomForestClassifier, 100 trees, 7 features, 22 classes** and `soil_dt.pkl` a
DecisionTreeClassifier with the same shape — so Table 3's comparison is real work, verified through a
path that does not run through the paper's prose. (b) Post-promotion verification first read
`projected/349/resume.projected.yaml`, which was **two days stale** — `profile-bundle project` prints to
**stdout** and does not write that file. Caught by the file's mtime, not by its contents. **Check the
mtime of any artifact you are about to treat as a render.**

**The paper contradicts itself, and the resolution is cheaper than either number.** Table 3 (p.4) says
**99.54%**; Fig 1 (p.3) says **99.45%**, as does the poster's block diagram — so the "wrong" figure has
two occurrences and neither can be recomputed (the 2,200-row CSV is not on disk). **Ruled: write
`99.5%`** — true under both readings, survives a reviewer who opens the PDF at Fig 1, and **shorter**.

**A provenance caveat that is inherited, not introduced.** `soil_rfc.pkl`'s 22 classes are *exactly* the
22 crops of the Kaggle "Crop Recommendation Dataset" (2,200 rows, same 7 features), whose documented
origin is agricultural/weather-station data, not an Indian government portal — while the paper calls all
three datasets *"obtained from the official government website"* (p.2). The other two are well
supported: the rainfall CSV's header matches §3.1 word for word, and `keys.py` holds a **`data.gov.in`**
API key. The bullet said what its peer-reviewed source said, so this is a risk to brief Mit on, **not a
résumé defect** — and the final wording drops "government" anyway.

**Owner rulings.** (1) **Best Paper stays** — he holds proof off-disk. (2) **Two bullets.** (3)
**`fact.crop-rf.tech.aws` STAYS** — it is the bundle's *only* source of the AWS skill (1 of 20 fact
files) and therefore why "AWS" renders under Skills → Tools; parking it was offered and **declined**:
he knows AWS from elsewhere. So the AWS *bullet* claim is gone while the AWS *skill* remains,
**deliberately — do not "fix" this apparent inconsistency.** (4) job-apps out of scope, above.

**Final wording, owner-approved: 2 bullets / 174 + 198 = 372 chars** (from 3 / 439, **−67**), zero over
ceiling. Bullet 1 carries the publication and the corrected award count; bullet 2 carries the trilingual
client, the sample scale, the probability-ranked top five and the accuracy. **Nothing was lost to the
cut**: "Random Forest" is already the entry title (so restating it would violate D-213's no-repeat
rule), the headline accuracy folded into bullet 2 as *"99.5% model accuracy"* — attribution-neutral, so
it describes the system without asserting he trained it — and the stack and DOI live in `subtitle` and
`link_url`.

**Authoring shape.** Draft `crop-rf-bullets` cut from revision 16; two `edit-fact` calls produced
`.001.r2` and `.003.r2` per D-190; **`…contribution.002` was parked by surface** — `'resume'` dropped
from `allowed_surfaces`, leaving `['public']` — per D-213, since the bullet is *correct* but surplus,
which is not D-209's `rejected`. No CLI does this, so it was a surgical hand-edit anchored on the fact's
unique value line (the three-line surfaces block repeats throughout the file), and a per-fact dump
confirmed **exactly one** of eleven facts changed surface. Validated **identically to a baseline
captured before the edits** at both tiers — 0 error / 0 blocker / 10 warning / 1 information — because
`_catalog_admits` is a diff and cannot see removals. `approve`, `promote` and `approve-projection` were
left to the owner: they record *his* attestation on a controlling terminal, and an agent running them
would manufacture the approval the whole `owner_attested` basis rests on.

**`projection.yaml:12` corrected in the same change.** `subtitle` `'Python, Flutter, AWS'` →
`'Python, scikit-learn, FastAPI, Flutter, Firebase'` (drops the contradicted host, adds the two
keywords an ML/SDE screen actually looks for, all verified), and **`link_url` restored** to the DOI with
`link_label: 'DOI'`. crop-rf now joins hookrail/streaksync/flickswiper as a linked entry; it had been
the only project holding a permanent identifier and rendering no link.

**Verified through the rendered `project` output, not the draft that produced it.** Revision 17,
`project` exit 0 clean, new projection digest `sha256:c070a5a7…`: crop-rf ships **2 bullets, 174 + 198
chars**, `.001`/`.003` superseded and dropping out on their own, `.002` absent by surface. **crop-rf is
closed; the wording is final and must not be re-derived.**

**Alternatives rejected.** *Three bullets keeping a slimmed accuracy comparison* (~501 chars) — the
comparators exist to flatter 99.54, and a 1.09-point margin over a decision tree is not itself
impressive; owner chose two. *Dropping the award and leading on selectivity alone* (127 chars) — moot
once he attested the award, but it was the stronger option had he not. *Leading with the app to match
his résumé's order* — bullets sort by fact id, so this would have required swapping content between
`.001` and `.003` and scrambling `import_lineage`; each fact was instead edited in place, and the
credential leads. *Naming Heroku in the subtitle* — accurate per the poster but a far weaker keyword
than what replaced it. *Retiring `fact.crop-rf.tech.aws`* — owner declined, above.

---

## D-218 — Nakshatra's bullets are rewritten; both percentages stay, as client-supplied estimates

**Context.** Attended bullet-refinement session for `employment.nakshatra` (STATE "Owed next" item 2).
Research established: the repo is **public** — `github.com/mit112/nakshatra_hospital_management`, 121
commits, 7 contributors, Mit 2nd at 26% of commits and 25% of surviving lines, but author of both the
first and last commit and outright owner of the foundation layer (`constants.dart` and
`data_controller.dart` 100%, `auth.dart` 96%, `main.dart` 85%). An **employer certificate** exists
designating him *"Android Application Developer"* for *28 Mar 2021 – 19 Feb 2022*, co-signed by an eye
surgeon. The app is a **Flutter client on Firebase, Android-only**: no `GoogleService-Info.plist`, no
`Podfile.lock`, `project.pbxproj` names `GoogleService` zero times, so the iOS target could never have
initialised Firebase. Both bullets' `import_lineage` was `source.mit-resume` — they cited themselves.
Full research: `~/dev/portfolio-website/wiki/reporesearch/nakshatra/README.md`.

**Choice.** Four owner rulings, all 2026-08-17.

1. **Title stays `Software Developer Intern`.** The certificate's *"Android Application Developer"* was
   declined **on accuracy grounds** — the app is Flutter, not native Android. `fact.nakshatra.title.001`
   unchanged. Settles `conflicts-and-flags.md` item 5 for this role.
2. **"Led" is true and is kept.** Blame share measures code authored, not leadership; LinkedIn's
   *"Android Application Team Lead"* corroborates. This session's earlier "contradicted as stated" is
   **withdrawn** — it conflated authorship volume with leadership.
3. **Both percentages are kept.** Mit: *"93% was their assumption, theres no stat for it"*; *"same
   assumption by them for 78"*. They are **client-supplied estimates** — not measurements, not
   inventions. That is a real provenance chain (clinic estimate → owner attestation), which is what
   `owner_attested` exists for, and §8.3 of the research shows no artifact could ever have existed: the
   app has **zero** instrumentation (`logEvent|Analytics` → 0 hits; `firebase_analytics` declared and
   never imported). Deliberately **not** hedged as *"an estimated 93%"* — his other percentages are
   unhedged estimates too — and **not rounded**, which would desynchronise ~9,300 sent résumés and
   `summary_sde.tex`'s "93% fewer errors".
4. **Two bullets**, rewritten to drop only what the code contradicts — *distributed*, *scalable*,
   *automated workflows*, *optimized data handling* — and to name the real stack, which per D-213's
   split is where an **experience** entry must carry it (`kind: experience` rows declare
   `subtitle: '{employment.organization}'`, so no stack is printed anywhere else, and all four scorers
   read `bullet.text` only). The pre-edit bullets extracted **zero** skills, which is the mechanical
   reason this entry sat below the cut line in **10 of 10** postings of the selection matrix; the new
   pair matches Flutter, Android and NoSQL.

**Alternatives rejected.** *Dropping the percentages* — an entry with no number competes badly on a
scanning surface (D-213), and the figures turned out to be sourced. *Parking them via
`allowed_surfaces: ['public']`* (D-213/D-214's mechanism) — correct tool for a correct-but-unwanted
fact, unnecessary once both were ruled keepable. *Matching the certificate's title* — recommended by
this session and **overruled by the owner with the better argument**. *Claiming Android **and** iOS* —
cut after checking platform config rather than the folder list; it would have introduced a **new** false
claim while fixing old ones. *Attaching the 78% to the OT sterilisation register alone* — cut, because an
infection-control log affects theatre turnaround, not patient throughput; the clinic's estimate covered
the paper→digital move generally, so the register is named as an exemplar instead. A draft that tried to
say both broke the 220 ceiling at 226.

**Also recorded.** `accomplishment.002`'s pre-edit text appeared on **0 of 69** distinct sent variants
across 14,719 `.tex` files — an import artifact, not wording Mit wrote, so replacing it removes an
unattested string. Separately, **29 sent résumés render this entry in the first person** (*"At Nakshatra
Eye Care, I led…"*) — a Job-apps tailoring escape, not a bundle defect, and unowned.

**Two method notes worth keeping.** (a) Comparing bundle text to the sent corpus returned 0 for *both*
bullets at first, reading as total drift. The sent `.tex` carries inline `\textbf{}` **inside** bullet
text and escapes `93\%`, so no literal match is possible — strip markup before comparing. Bullet 1's
"drift" evaporated on the corrected run; only bullet 2's survived. (b) The local
`/Volumes/mit/.../nakshatra_hospital_management-master` copy is a zip export with **no `.git`**;
researching it alone would have reported "no history exists". Run `gh repo view` before calling a repo
historyless. This complements D-217's `grep`/`.gitignore` finding — same class, different instrument.

**State — PROMOTED AND LIVE.** Authored as draft `nakshatra-bullets` on revision 17 (`sha256:1e4c2420`;
the bundle moved 9 → 17 mid-session as eight sibling promotions landed, and all six Nakshatra facts were
re-verified byte-identical before editing). Both `.r2` edges filed; `validate --draft` and `validate
--draft --completeness` each **0 error, 0 blocker**, completeness blocker count identical to the
revision-17 baseline. The owner then ran `approve`, `promote` and `approve-projection`, producing
**revision 18, `sha256:669ad874`**. Verified through `profile-bundle project` (exit 0): both `.r2` facts
render at **176 and 195 chars, 371 total**, matching `Flutter`, `Android (mobile)` and `NoSQL (word)`
where the pre-edit pair matched nothing; the originals read `superseded`.

**One trap this produced, worth the line.** Immediately after approval the bundle read revision 18 /
`669ad874`, which did **not** match the draft's candidate digest `f513247f`, and revision 18 had modified
`employment.nakshatra.yaml` — the exact signature of a sibling session having edited the same entity.
Promotion was halted and `rebase-draft` located before acting. It was a false alarm: **promotion appends
to `history/changes.yaml`, `history/approvals.yaml` and `manifest.yaml`, so a draft's candidate digest is
never the digest of the revision it becomes.** A candidate-vs-CURRENT digest mismatch is therefore not
evidence of a concurrent write; inspect the records to tell the two apart.

---

## D-219 — The one-page budget is a character budget, not a bullet count; D-195's two-candidate ceiling is retired

*2026-08-17. Re-measures the capacity D-195 established, and supersedes two of its conclusions.*

**Context.** D-195 measured the one-page budget by compiling hand-named subsets and concluded "the
ceiling is 16 bullets, not a number of entries", that with three jobs pinned "at most two candidates can
ever be admitted", and that the owner's stated per-JD sets of four projects "do not fit on one page under
any split". That was measured against a pool whose bullets averaged ~250 characters.

Re-measured through the same path (`LatexRenderer.emit` → `to_pdf` → `evaluate_compile`, `max_pages=1`),
first at revision 8 and again after the bullet refinement, substituting bullet text **in memory only** —
no bundle write, nothing attested.

At the revision-8 pool, **bullet count did not predict fit**: 17 bullets fit at both 6 and 7 entries, and
two different **18-bullet / 7-entry** sets landed on opposite sides of the limit (`3 jobs + SS3 FS3 BQ3
FO2` overflowed at 3,702 chars; `4 jobs + HR3 KF3 CR3` fit at 2,944). Sorting all sixteen probes by total
bullet characters separated them perfectly: **every set ≤ 3,439 chars fit; every set ≥ 3,528 overflowed.**
A wrapped-line model also separated them at every column width tested, which is the underlying mechanism —
characters are a proxy for rendered lines.

**Choice.** The budget is denominated in **characters** (proxying rendered lines), not bullets. D-195's
"16 bullets" is retained only as a rule of thumb for uniformly long bullets. Two of its conclusions are
**retired as artifacts of the then-current bullet lengths**:

- "At most two candidates can ever be admitted" — false after refinement.
- The four-project sets "do not fit under any split" — false after refinement.

Measured at revision 21 (pinned = 1,180 chars): **both** stated per-JD four-project sets fit on one page
(SDE 3,131 chars / iOS 2,968), and **five** projects fit (3,347); six overflows (3,973). Candidate room is
**2,259 characters**. Keeping `nio-coop` at three bullets rather than two admits **identical** project
sets, so the third bullet costs no project.

### Alternatives rejected

- **Keep reasoning in bullets.** It is the unit the gate's error names, but two equal-bullet-count sets
  can straddle the limit, so it cannot support a decision.
- **Model rendered lines directly.** Strictly more accurate and it does separate the data, but it needs
  the column width and the wrap algorithm; characters separate the same probes with no such dependency.
- **Raise `resume_max_pages` to 2.** The owner pins it at 1 (D-195); unchanged.

### What generalises

- **A capacity claim is only valid for the inputs it was measured on.** D-195 was correct when written
  and wrong eight days later, because the thing it measured — bullet length — was the thing the next
  phase of work changed. Re-measure a capacity before reusing its conclusion, especially a *negative*
  one ("cannot fit"), which is the kind most likely to foreclose work.
- **Convert a gate's units into the units of the decision** (D-195's own lesson, extended): pages → 
  bullets was the first conversion, bullets → characters the second. Each one made the budget more
  actionable and each was only found by measuring.
- Substituting candidate text in memory to measure layout is not authoring: it touches no draft, files no
  fact and attests nothing, so it is available before the owner has approved any wording.

---

## D-220 — NIO's bullets drop the SwiftUI and SensorKit-authorship claims and add the VPN lifecycle work; the owner attests SensorKit shipped

*2026-08-17. Promoted at revision 20 (`sha256:c828f34b…`). Research:
`~/dev/portfolio-website/wiki/reporesearch/nio-coop/README.md`.*

**Context.** The co-op's source is on disk at `~/cosmos` (Northeastern GitLab
`achtung-gitlab.ccs.neu.edu:midscale/cosmos`, 679 commits, 87 Swift files, ~12.2k LOC). Mit's share is
real and substantial: **90 commits, +8,052 / −5,526**, 2024-07-09 → 2025-02-13, matching the stated role
dates exactly. He joined a codebase ~17 months old as **one of six contributors, 4th by commit count**,
while the bullet said "Designed, built, and maintained".

Three claims did not survive:

- **SwiftUI** — the production app is **UIKit + Storyboards**: 0 of 87 files import SwiftUI, 26 import
  UIKit, verified with `command grep` *and* `rg --no-ignore` against a `find` denominator. The only
  SwiftUI is `cosmos_ui_swiftui` on an external drive: one commit, solo, dated six days *before* his
  first Cosmos commit, 63 files of which 4 import SwiftUI.
- **SensorKit** — real, but **not his**: 10 commits in `*.swift`, **all Abby Wisnewski**, Mit 0, across
  four branches never merged to `merge_vpn_plus_flows`, 2024-12-17 → 2025-02-13.
- **40% / 75%** — no source artifact. A consistency sweep of every résumé variant, three outreach
  packets, both summaries and ~20 tailored variants found the figures never migrate — but that corpus is
  wholly downstream of one `sections.tex`, so it measures faithful copying, not corroboration (D-217's
  converse; see *What generalises*).

Also overstated: "custom caching strategies" is **23 inserted lines** caching attributed strings for
`UILabel`s (COSMOS-36), and `BackgroundTasksManager.swift` was authored by Aditya Pathak in Oct 2023.

**Owner attestation, accepted.** Mit: *"since I dont work there anymore, we dont see the new progress. but
you have to take my word for it that it was shipped to the app."* The clone ends 2025-02-20 and his access
ended with the co-op, so shipping is unobservable here; all three release tags predate the SensorKit work
entirely. **The attestation reaches shipping but not authorship**, because his tenure is *fully* observed
by this clone — both facts hold at once, and that is what shaped the wording.

**Choice.** Three bullets, 632 chars, none over the 220 ceiling:

1. `.001.r2` (218) — scope: Swift + **UIKit**, NSF-funded research app whose VPN network extension and
   **SensorKit** pipeline captured packet-, flow- and device-usage data. SensorKit is retained **as a
   keyword describing the app's pipeline**, at the owner's explicit request (*"it was part of the project
   and having it as a keyword in the resume is important"*), with the `by integrating SensorKit`
   authorship construction removed.
2. `.002.r2` (216) — the **VPN tunnel lifecycle** work: reconnects, app updates and fresh installs,
   duplicate `PacketTunnel` elimination, paused-VPN state propagated through location upload, device-info
   collection and UI. His largest verified contribution (`VPNManager.swift` reworked 196 lines,
   COSMOS-25/30/31/63) and **previously unclaimed anywhere**.
3. `.003.r2` (198) — **40%** retained, on the mechanism that does verify: background task scheduling,
   concurrency tuning, and the controlled battery-measurement harness he built (COSMOS-24 — fixed 80%
   start, 50% brightness, 30-min stream + 15-min idle, auto-logged).

The **75% is retired** — welded to a mechanism that is not his, and unsourced. Validation was identical
to baseline at both tiers (error 0, blocker 0, warning 10, +1 information) with no new finding kinds.
`nio-coop` was the last over-ceiling bullet in the pinned set, so **the pool now has zero over-ceiling
bullets** and `bullet_too_long` can no longer trip on any render.

### Alternatives rejected

- **Keep the 75% re-worded onto the shipped pipeline** ("richness grew 75% as SensorKit collection
  shipped"). Fits in 203 chars and makes no authorship claim, but it is the one figure with no
  reconstructable source, and bullet 1 already wins the SensorKit keyword — so it added risk, not scan value.
- **Drop the 40% too.** Its mechanism is verified and the owner can describe how it was measured; treating
  an unsourced-but-defensible metric as equivalent to a misattributed one would be a false equivalence.
- **Cut to two bullets** to match every other entity. Measured (D-219) to admit identical project sets, so
  it would have surrendered the 40% for nothing.
- **Promote "sole iOS developer"** from `application-qa.md` into a bullet. Contradicted by six
  contributors. It remains uncorrected *in that file*, which is the source the live application form-fills
  of 2026-07-23/24 drew from — still owed.

### What generalises

- **The working tree is not the repo.** "SensorKit is absent" was published — into the wiki, to the owner,
  and as the worked example in six sibling session prompts — on a `grep -r` of one checked-out branch that
  *passed a control test*. **A control test is only evidence about the corpus it ran against** (D-215
  reached the same rule from deleted rather than unmerged code). Before calling anything absent, run
  `git log --all -S`, `git branch -a`, and `git branch -a --merged`.
- **Restrict the pickaxe to source.** Unrestricted, `git log --all -S "SensorKit"` returns **18** commits
  reaching back to 2023-03 — 8 of them a colleague's binary `.xcuserstate` churn, which contains the
  string and rewrites every Xcode session. It fabricated both the count and the date range. Always
  `-- '*.swift'`.
- **Existence is not authorship.** Finding the code only reframes the question; `git log --author`/`-S`
  answers it, and it **discriminates** — the same check that convicted this bullet exonerated StreakSync
  at 259 of 259 (D-215). Match the owner's whole identity set: he commits here as `Mit Sheth`,
  `Mit Kamal Sheth` and `MiT`, so one spelling undercounts him by 12 commits.
- **Consistency across a copied corpus is not corroboration.** D-217 found a figure riding three
  incompatible stacks, which *is* positive evidence of an ungrounded number. The converse does not hold:
  a clean sweep returns a claim to "unsubstantiated" and cannot upgrade it. Only an artifact outside the
  résumé lineage can.
- **Being wrong toward "absent" felt safe and was not** — the corrected finding (a colleague's
  never-merged work, claimed as his) was *worse* for the résumé than the mistake. Publish negatives more
  slowly than positives.

---

## D-221 — Saayam keeps its entry with one role-scoped bullet, because "role + org + dates only" is unrepresentable today

*2026-08-17. Promoted at revision 21 (`sha256:abed3cab…`). Completes STATE "Owed next" item 2 — all
eleven entities.*

**Context.** `employment.saayam` is **pinned**, so its bullets render on every résumé. Its two bullets
claimed contributions to the org's LLM microservice. The owner's own working file
(`~/dev/Saayam For All/README.md`) states the governing rule and the status:

> **Hard rule (same as the resume pipeline):** No bullet goes on the resume unless it describes work
> actually shipped (a merged PR). Until there are merged PRs, the resume lists the *role + org + dates*
> only.

> **Honest status as of 2026-06-30:** offer letter in hand, but **0 commits / 0 PRs** so far.

Verified against GitHub, every query control-tested (controls found 10 PRs and 3 commits in his own
repos): **0 PRs** by `mit112` in `saayam-for-all` (merged, open and closed queried separately), **0
commits** in the org, and he is **not among the 8 contributors** to `saayam-for-all/ai` — his chosen
track, a public repo actively developed (last push 2026-08-07). He *is* an org member, and private org
repos are visible to him, so nothing hides behind visibility. The role began Oct 2025.

**The owner's constraint:** *"but i need to put that entry in so there is no gap in my resume. its
known."* This does not conflict with his rule — the rule keeps the entry and drops the bullets.

**But the rule cannot be expressed in boardwatch.** Two independent gates refuse a bullet-less entry:

- `pool.py:367` — Saayam's declaration carries `bullet_predicates: ['employment.accomplishment']`, and a
  predicate resolving to no résumé-surfaced fact raises **`BULLET_PREDICATE_NO_FACTS`**: *"a predicate
  resolving to nothing is a loud refusal rather than a dropped bullet."* `profile-bundle project` would
  exit 1 and Stage 2 could not run at all.
- `resume_gate.py:145` — `validate_slots`, on the tailor render path, raises *"entry X has no bullets"*.

So parking **both** bullets does not yield a role-only entry; it breaks the pipeline.

**Choice (the owner's, "A now and C later").**

- **One role-scoped bullet**, `fact.saayam.accomplishment.001.r2` (200 chars): *"Volunteer on the AI/GenAI
  track at a 501(c)(3) non-profit aid platform whose Python/Flask LLM microservice on AWS Lambda routes
  zero-shot-classified aid requests across Gemini, OpenAI, Llama and Grok."* Every clause is checkable —
  the role and track from his offer letter and notes, the service from the org's **public** repo — and
  **nothing is predicated of him but the position he holds.** The originals opened "Contribute to…" and
  "Work across…"; the replacement has no delivery verb about him at all.
- **`fact.saayam.accomplishment.002` parked by surface** (D-213): `allowed_surfaces` `['public','resume']`
  → `['public']`. It stays effective, `owner_confirmed` and attested, but never reaches the résumé.
  Reversible by re-adding `'resume'` to one line when a PR merges. No CLI does this; done as a surgical
  text edit, not a `yaml.safe_dump` round-trip, which would break the restricted loader.
- **C is deferred, not dropped:** make the rule representable by having a declared predicate with no facts
  drop the bullet rather than refuse, and letting `validate_slots` accept a bullet-less entry.

Result: Saayam 2 bullets / 328 chars → **1 / 200**; pinned 1,308 → **1,180**; candidate room **2,259**;
over-ceiling **0**. Title, organization, date-range and location facts are untouched, so the entry renders
in full and the timeline gap is covered. Validation identical to baseline at both tiers, no new finding
kinds; exactly one `resume` surface removed of nine.

### Alternatives rejected

- **Keep both bullets.** The `ai` repo is public and its contributor list is checkable in seconds — a
  materially different exposure from an unverifiable percentage.
- **Park both and render role + org + dates.** What the owner's rule actually prescribes, and currently
  impossible (above). Recorded as C rather than attempted.
- **Change the two gates now.** Correct long-term fix, but it alters a render gate and a projection
  refusal during an attended wording session; sequenced as C.
- **A more conservative "Selected for the AI/GenAI track…"** (197 chars). Unmistakably an assignment
  rather than delivered work, at the cost of the provider keywords; the owner chose the keyword-carrying
  variant.

### What generalises

- **A policy the tooling cannot express will be violated silently.** The no-fabrication rule was written
  down, agreed, and then quietly broken for ~10 months on a *pinned* entity — not by disagreement, but
  because the only representable options were "claim something" or "break the render". When a rule can't
  be encoded, expect drift toward whatever the tool permits.
- **Two gates, opposite fail directions, same subject.** `BULLET_PREDICATE_NO_FACTS` fails loud so a
  declaration silently losing its content is caught; `validate_slots` fails loud so an empty entry never
  renders. Both are right individually and jointly foreclose a legitimate third state. Fail-safe direction
  is chosen per gate; the *interaction* needs choosing too.
- **"Not on disk" ≠ "does not exist", and "exists" ≠ "is his"** (D-216, D-220). Here the org, the repo and
  the described architecture are all real and public; only the contribution is absent — which is why the
  honest fix was to describe the system and state the position, never to delete the entry.

---

## D-222 — Correction: D-212 marked two of the three tests exercising the Windows stale-lock race, and the third turned the nightly red

*2026-08-17. Corrects D-212's scope. Found by checking CI at session close, not by a failing local gate.*

**Context.** D-211/D-212 established that Windows runs **only** on the `schedule`/`workflow_dispatch` CI
build, ruled Windows best-effort, and accepted the stale-lock reclaim as a Windows-only **race** rather
than fixing it — marking it `@pytest.mark.xfail(sys.platform == "win32", reason=WINDOWS_STALE_LOCK_RACE,
strict=False)`.

Two things were then checked at this session's close, both by reading CI rather than trusting the docs:

1. **D-212's fix IS verified.** Dispatch run `31954948210` (`4593d04`) completed **success**. STATE had
   carried "the fix is NECESSARY, NOT VERIFIED" since that run was still in flight; that caveat is now
   resolved and removed.
2. **The nightly is red again for a different reason.** Scheduled run `32007953224` (`aeb87d9`,
   2026-08-17 07:55Z) failed on exactly **one** of thirteen jobs — `test (3.11, windows-latest)`. Windows
   **3.12 and 3.13 passed**, as did every macOS/Linux job. `nightly-watch` filed issue **#76**.

**The cause is D-212's scope, not a new defect.** Three tests exercise the identical scenario — kill a
lock holder, then assert the leftover lockfile is not treated as held. D-212 marked two:

| Test | Marked by D-212? |
|---|---|
| `test_profile_bundle_promotion.py:915` `…persistent_lockfile_left_by_a_killed_process…` | yes |
| `test_profile_bundle_rebase.py:1412` `…persistent_lockfile_left_by_a_killed_process…` | yes |
| `test_profile_bundle_promotion_concurrency.py:233` `test_a_lockfile_left_by_a_killed_promoter_is_not_a_held_lock` | **NO** |

The unmarked third fails with the same `bundle_lock_held` diagnostic (`assert 3 == 0`). No `xfail` marker
had ever existed in that file — `git log -S "xfail"` on it returns nothing — so this was never a
regression; the instance was simply never enumerated.

**Choice.** Add the same marker to the third test, in the same form, importing the shared
`WINDOWS_STALE_LOCK_RACE` constant (`tests/profile_bundle/conftest.py:77`) exactly as the other two files
do. No new reason string, `strict=False` as before, no bare `pytest.xfail()` call.

**This suppresses the race rather than fixing it** — deliberately, and only because D-212 already ruled
that trade for the same race in the same session. It is a consistency fix, not a new judgement. If the
race is ever to be fixed, all three markers come off together.

### Alternatives rejected

- **Fix the underlying race now.** Correct, but it reopens a ruling made eight days earlier at session
  close, on a platform the local gate cannot exercise. Reverting a red nightly to the owner's already-stated
  position is the smaller change.
- **Mark it `strict=True`.** Would fail the moment the race stops reproducing, on a platform nobody can
  observe locally — the opposite of useful.
- **Skip rather than xfail.** Loses the signal that the test would pass when the race does not fire.

### What generalises

- **An enumeration is a claim, not a census.** D-212 scoped its fix to the two instances in hand rather
  than searching for every test exercising the race. The correct move was
  `command grep -rn "killed" tests/` — or better, grepping for the *shared reason constant* and asking
  which tests should reference it. **When a fix is "mark every instance of X", find X by symbol, not by
  memory** — the same failure mode recorded in D-142 and D-220.
- **A green local gate is not evidence about Windows.** `make check` passed on this change and says nothing
  about it. The verification route is a `workflow_dispatch` or the next 07:00 UTC nightly, and **issue #76
  closing is the signal** — `nightly-watch` closes it on recovery.
- **Check CI at session close, not only at session start.** STATE already said to look for an open
  "Nightly CI is failing" issue at session *start*; this defect was introduced and detected inside a single
  day, so a start-only habit would have carried it a full cycle.

## D-223 — Correction: D-222's own census was short one, and instance 4 is marked by mechanism

*2026-08-17. Corrects D-222's scope, which corrected D-212's. Found while verifying D-222, not by a
failing job — the instance has never been observed failing.*

**Context.** D-212 marked two of the tests exercising the Windows stale-lock race; D-222 found a third
after the nightly went red on it, and its "what generalises" section prescribed the remedy: *find X by
symbol, not by memory.* D-222 then enumerated by grepping `"killed"`. The fourth instance is named
`test_the_lock_helper_refuses_a_second_holder_and_releases_on_exit` — no "killed" anywhere in it — so
the prescribed lesson was written and violated in the same entry.

**The census, done properly.** The discriminating predicate is not a word in a name but a *shape*:
`process.kill()` in a test **body** (fixture teardown does not count), followed by an acquire.

| Test | Acquire after kill | Marked before D-223 |
|---|---|---|
| `test_profile_bundle_promotion.py:919` | `promote` | yes (D-212) |
| `test_profile_bundle_rebase.py:1416` | `rebase_draft` | yes (D-212) |
| `test_profile_bundle_promotion_concurrency.py:243` | `promote` | yes (D-222) |
| `test_profile_bundle_rebase.py:1432` `…refuses_a_second_holder_and_releases_on_exit` | `bundle_lock` direct | **NO** |

Instance 4 kills its holder, `wait()`s, then re-acquires — which is precisely the
"killed holder's handle-teardown window" that `WINDOWS_STALE_LOCK_RACE`
(`tests/profile_bundle/conftest.py:77`) documents. It differs from the other three only in surfacing the
race as a raised `BundleLockHeldError` instead of exit code 3, which is why a search for the
`bundle_lock_held` *diagnostic* would also have missed it.

**Sites deliberately NOT marked, and why the absence is correct.** `promotion.py:883,902`,
`rebase.py:1380,1399,1467` hold the lock with the holder **alive** and assert refusal. There the race
produces the expected `bundle_lock_held` for the wrong reason — a spurious **pass**, never a red. And
`concurrency.py:176,200-216,315` let promoters exit **naturally**, which releases the lock cleanly, so no
teardown window exists. Marking either group would suppress signal for no reason.

**Choice.** Mark instance 4 in the same form — shared constant, `strict=False`, conditional on `win32` —
and record in a comment above it that it is marked **by mechanism, not by observation**. Rewrite the
`conftest.py` comment that said *"Both … promotion.py and … rebase.py carry a copy"* (true when written,
wrong at three files) to state the count and, more usefully, the census predicate.

**This is pre-emptive suppression, and that is the weakest part of it.** `strict=False` means if instance
4 ever breaks for a real reason on Windows, nobody learns. Accepted because Mit has now ruled this same
trade for this same race twice (D-212, D-222), and a fourth latent red nightly costs a session each time
it fires; but it is a consistency call on an unobserved instance, not evidence the test races.

### Alternatives rejected

- **Wait for it to go red, then mark it.** The honest option, and it keeps `strict=False` meaningful. Rejected
  because the cost of being right is one more red nightly, one more `nightly-watch` issue, and one more
  session spent rediscovering a race already ruled twice.
- **Fix the race in `locking.py`.** Still the correct long-term answer — `filelock`'s
  `WindowsFileLock._acquire` swallowing `EACCES` is the actual defect. Out of scope for a verification pass,
  and D-212 ruled Windows best-effort.
- **Mark by a shared pytest marker applied to the whole holder-kill class.** Tempting, but it would sweep in
  the holder-stays-alive tests above, whose lack of a marker is load-bearing.

### What generalises

- **A census needs a predicate, not a keyword.** D-222 searched for a *word* ("killed"); the property that
  actually matters was a *shape* (`kill()` in a body, then an acquire). When the lesson is "find every
  instance", write down the discriminating predicate first and grep for that — a name is metadata and drifts
  away from behaviour.
- **The same lesson recorded three times is not a learned lesson.** D-142, D-220 and D-222 all end in "an
  enumeration is a claim, not a census", and the next enumeration was still short. The durable fix is the
  predicate written **into the code** beside the constant, where the next person reads it — which is what
  the `conftest.py` comment now does.
- **A negative case belongs in the census too.** Half this entry is *why five other sites stay unmarked*.
  Without that, the next reader re-derives it, and the cheapest wrong answer is to mark them all.
- **The root defect is stated in the design's own words, and it is a contradiction.** `locking.py`'s module
  docstring lists two contractual properties within thirty lines of each other: *"**`filelock`, not
  `flock`.** §6 names Boardwatch's existing cross-platform dependency… introducing a POSIX-only primitive
  here would contradict the portability contract"*, and *"**The operating system is the only authority.**
  The kernel drops a dead process's `flock` immediately."* The module chose `filelock` **for** portability
  and then rested its correctness argument on a guarantee only POSIX makes. Windows is not an unlucky
  platform here — it is the case that reads the second property literally. Confirmed through source rather
  than the reason string: `bundle_lock` catches `filelock.Timeout` and raises `BundleLockHeldError`
  (`locking.py:71-76`), which is why instance 4 surfaces the race as an exception. **If the race is ever
  fixed, this docstring is the thing to fix first** — the four markers come off together after it, and any
  fix that leaves both sentences standing has not addressed the defect.

## D-224 — The Windows stale-lock race is fixed by re-asking the OS, and the four markers come off

*2026-08-17. The root fix D-223 named as "still the correct long-term answer". Closes D-212/D-222/D-223's
suppression track.*

**Context.** `locking.py`'s module docstring made two contractual claims within thirty lines of each other:
that it chose `filelock` **for** cross-platform portability, and that "the kernel drops a dead process's
`flock` immediately", on which the whole stale-lockfile safety argument rested. The second is a POSIX
guarantee. Four tests kill a lock holder and then acquire; on Windows all four could report
`bundle_lock_held` for a lock nobody held, and D-212/D-222/D-223 answered each discovery with another
`xfail(win32, strict=False)`.

**Verified before designing, through source rather than the reason string.** `filelock` 3.29.3:
`WindowsFileLock._acquire` catches `EACCES` from **both** `os.open` and `msvcrt.locking` and returns
without setting `lock_file_fd`; `_poll_until_acquired` then sees `is_locked` false and, under
`blocking=False`, `_check_give_up` returns immediately and raises `Timeout` — which this module maps to
`BundleLockHeldError`. So a transient `EACCES` is *indistinguishable from real contention at our call site*.
Two further facts came out of the same read: the **Unix** backend has the same swallowed-transient shape
(FUSE/NFS `FileNotFoundError`, and an unlinked inode's `st_nlink == 0`), so POSIX is not immune but lucky on
local disk; and `_try_break_expired_lock` is inert unless `lifetime` is set, which defaults to `None` and
is already reached once per acquire today — so a polling acquire adds no new lock-breaking exposure, and §6's
"never break a lock" stands either way. `lifetime` postdates the declared floor `filelock>=3.13` and is
therefore not passed.

**The defect, restated.** The property "the operating system is the only authority" is *correct* and
survives. What was POSIX-only was an unstated corollary: **that the OS answers correctly on the first ask.**

**Choice.** On Windows, ask the OS **again** for a bounded window instead of believing one refusal.
`RECLAIM_WINDOW_SECONDS` is `1.0` on `win32` and `0.0` everywhere else; `bundle_lock` loops over the same
`acquire(blocking=False)` call it always made, until a deadline. Re-asking keeps the kernel the sole
authority — ageing or unlinking the file would move that authority into Boardwatch, which §6 forbids. The
docstring's POSIX sentence is gone, replaced by the platform asymmetry stated explicitly, and all four
markers are removed in the same change.

**This is a departure from §21's "no wait or mutation", and it is Windows-only.** On POSIX the window is
zero and behaviour is bit-identical: one ask, no wait. On Windows a *genuine* refusal now costs up to a
second first. Bounded by a deadline on purpose — an unbounded retry is the hung terminal the non-blocking
property exists to prevent.

**1.0s is a judgement, not a measurement.** No number for the real handle-teardown window exists. The
failure mode of too short a window is exactly the status quo — a false refusal — so the window is a strict
improvement at any value, and can be widened on evidence without changing what any property means. The bet
being taken is the **markers coming off**; only a `workflow_dispatch` of `ci.yml` settles it, and a red
Windows job afterwards would be *new information* (the window's true size), never grounds to re-mark blind.

**Three deliberately-unmarked sites needed their timing budgets changed, which is how the departure was
found.** `promotion.py`, `rebase.py` and `concurrency.py` each assert `elapsed < 2.0` on a *genuine*
contention path — the holder stays alive, so the window is paid in full. Each now reads
`RECLAIM_WINDOW_SECONDS + 2.0` from the emitter rather than restating a number, which leaves POSIX's budget
at 2.0 unchanged. Left alone, they would have turned a correct fix into three flaky Windows tests. The
refusal message also lost "nothing was waited for", which the window makes false on Windows; the one doc
quoting it verbatim was updated with it.

**Verification.** Six new tests in `tests/profile_bundle/test_profile_bundle_locking.py`, all runnable on
POSIX — which matters, because the four Windows tests can never verify their own fix. Five mutations, all
killed, none green: believe-the-first-refusal (2 tests), deadline dropped (1, in 1.56s), window opened on
every platform (1), `except` order swapped (1), spurious release on refusal (1). The stand-in refuses to be
asked past a ceiling, so "bounded" fails loudly instead of hanging — a hang is not a failure, and
`pytest-timeout` is not installed.

### Alternatives rejected

- **Open the window on every platform.** ~~It changes behaviour on the platform where nothing is broken~~ —
  **this reasoning was falsified within the session and the correction is below: something *is* broken
  there.** The option was still declined, on the narrower and surviving grounds that it widens the §21
  departure to the platforms Boardwatch is actually run on, costs a wait on every genuine refusal there, and
  is the owner's call rather than a reviewer's. Ruled by Mit: **record it, do not widen.**
- **Docstring-only: delete the POSIX claim and keep the markers.** Honest and zero-risk, and it was a real
  option. Rejected because the race would remain and the markers with it, so nothing would be repaired.
- **Delegate the wait to `filelock`'s own `timeout=`/`poll_interval=`.** Fewer lines, but it puts the wait
  inside the library where no test here can reach either arm of it, and adopts its timeout semantics and
  deadlock registry as load-bearing. A fake that reimplemented the polling would only test the fake.
- **Probe `os.open` ourselves on Windows to tell a teardown `EACCES` from a live `msvcrt` lock.** This
  discriminates *precisely* and would skip the wait on genuine contention, since a live holder's file is
  still openable. Rejected as disproportionate on a best-effort platform (D-212): ~25 lines of `msvcrt`
  code under a platform branch, unverifiable locally, duplicating the backend. **This is the upgrade path**
  if the one-second wait on genuine Windows contention ever bites.
- **Wait for the next nightly before removing the markers.** A green run proves nothing while
  `strict=False` markers are on, so it defers the same bet by a day and costs a session.

### What generalises

- **A portability contract is only as portable as its correctness argument.** The module named `filelock`
  over `flock` *for* portability and then rested its safety case on a POSIX guarantee. Both sentences read
  fine alone; the contradiction only appears when they are read together, which is why it survived three
  decision entries that were each looking at a test instead.
- **A suppression track ends when someone reads the dependency's source.** D-212, D-222 and D-223 each
  marked a test from the *reason string*. The mechanism was thirty lines of `_windows.py` and one `if` in
  `_api.py`, and reading them turned "an unlucky platform" into a named, fixable defect.
- **A fix's real blast radius is the sites that were deliberately left alone.** The three unmarked
  contention tests were correct before and would have gone flaky after, because they restated a timing
  budget as a literal. A derived check must read the emitter's constant — and the emitter changing is
  exactly when that stops being a style preference.
- **When a hang is the failure mode, make the double refuse.** An unbounded wait cannot be asserted against
  with a wall clock, because the test never returns to make the assertion. Capping the stand-in's answers
  converts it into an ordinary failing test with no new dependency.

### Corrected within the session, by review — and two exposures left standing on purpose

Two reviewers ran concurrently on the finished branch, one on runtime correctness and one on conformance to
D-223's census. Both cleared the retry loop itself (no path exits it without a held lock; the deadline is
checked after every attempt; `filelock`'s `lock_counter` is decremented under `except BaseException`, so N
failed asks cannot inflate it and defeat the later `release`). Three things they found are recorded here
because the entry above was wrong or silent about them.

**1. POSIX is not exempt, and "lucky on local disk" was wrong.** The runtime reviewer showed the *same class*
of false refusal on Linux and macOS, by a different mechanism, and it was **reproduced independently before
being accepted** — the first attempt at reproduction was itself wrong and is worth recording: hooking
`os.fstat` proves nothing, because when `flock` fails the `fstat` arm is never reached, so the `Timeout`
observed was a *correct* refusal wearing a wrong label. Forcing the interleaving at `os.open` reproduces it
properly: `UnixFileLock._release` unlinks the lockfile **before** it releases the `flock`, and `_acquire`
discards a lock whose inode is already unlinked (`st_nlink == 0`) by returning without setting its
descriptor. So a second writer that opened the inode before the holder released it wins the `flock`, finds
the inode doomed, and is reported as contention while **nobody holds the lock**. Verified by a third
acquirer taking it immediately afterwards. This is a **live-holder handoff** race, needs no dead process and
no network filesystem, and is therefore live on the supported platforms today. **Ruled by Mit: record it, do
not widen the window.** Closing it means a wait where §21 grants none on the platforms boardwatch is
actually run on; the fail-safe direction is at least right, since the symptom is a refusal and never a
corruption. `test_two_promotions_from_one_parent_produce_exactly_one_winner` cannot detect it, because it
accepts `bundle_lock_held` as a legitimate way to lose.

**2. `scan/coordinator.py:151-155` has the identical single-ask shape and did not get a window.** It builds a
`FileLock`, asks once with `blocking=False`, and maps `Timeout` to `ScanLockHeldError` → exit 2. On Windows a
scan killed mid-run leaves `scan.lock`, and the next `boardwatch scan` inside the teardown window is refused
with "another scan is already running" and writes nothing — on the unattended path that is the silent empty
day this codebase treats as fatal. Deliberately **not** fixed here: it is a different subsystem, and sharing
the constant would either duplicate it or make `scan` import from `profile_bundle`, which is the wrong
dependency direction. Named so it is a known gap rather than a discovery. `bundle_lock` is confirmed to be
the *only* acquire path inside `profile_bundle` — `promotion.py` and `rebase.py` mention `filelock` in
comments only.

**3. Three sibling statements of the "no wait" contract survived the docstring rewrite**, which is exactly the
D-223 pattern this entry closes: a guarantee asserted where the code no longer makes it.
`promotion.py`'s "the nine steps are the contract" and `docs/profile-bundle-authoring.md`'s promotion
sequence both now qualify it and point at this entry rather than restating the window. **`README.md` was the
real defect**: its "Supported platforms" block listed *four* Windows caveats "known and unfixed", and the
fourth was this exact bug, telling the operator to retry — which after the fix would have taught a Windows
user that a *genuine* post-fix refusal is expected behaviour, suppressing the one report that would prove the
window too small. Now three caveats, with the fourth recorded as fixed, its residual stated, and a request to
report it. The design spec's §21 table (`2026-08-10-…-design.md:1775`) is left as the source the departure is
measured against.

**What generalises from the review itself.** A reviewer's finding is a claim, not a result: the load-bearing
one here was confirmed only after the first reproduction of it turned out to be measuring nothing. And **the
doc that states a behaviour is not the doc that quotes a message** — the sweep that correctly found the one
verbatim quotation of the refusal string missed the README paragraph that described the bug in its own words,
which was the only user-facing copy that mattered.

### The Windows verdict: repair, not suppression — and 3.13 is what proves it

Dispatch **`32047384310`** on `0ab16e9`, **conclusion `success`**, all 12 jobs including three
`windows-latest`. The job conclusions alone would not have settled anything, so the pytest summaries were
read out of the logs and compared against the **pre-fix** dispatch `32039875198` (`8573f50`, all four
markers present) — a second path to the same claim.

| Windows job | Pre-fix, markers on | Post-fix, markers off |
|---|---|---|
| 3.11 | 4 xfailed, **4 xpassed** | 4 xfailed, **0 xpassed** |
| 3.12 | 4 xfailed, **4 xpassed** | 4 xfailed, **0 xpassed** |
| 3.13 | **5 xfailed, 3 xpassed** | 4 xfailed, **0 xpassed** |

**The 3.13 column is the whole argument.** Pre-fix it reports *five* xfailed and only *three* xpassed —
so one of the four marked tests **genuinely failed**, which is the race firing under a marker that hid
it. Post-fix, on the same platform and interpreter, there is nothing left to hide: 4 xfailed (the
unrelated `strict=True` projection scorers, on every version), **0 xpassed, 0 failed**. 3.11 and 3.12
had all four xpass both times, which is exactly why `strict=False` was chosen and exactly why a green
run could never have been read as repair on its own.

**The totals reconcile to the test, not approximately.** Pre-fix `6381 passed + 4 xpassed = 6385`
effectively-passing; add this change's 6 new tests and the post-fix run must report **6391 passed**, and
it does, on all three versions, with `50 skipped` unchanged (the POSIX-only modules). So the four tests
did not vanish, get skipped, or get weakened — they moved from *suppressed* to *passing*, and the count
proves which.

**`nightly-watch` skipped, as designed** (`ci.yml:99` gates it to `schedule`), so issue #76 is untouched
by this and closes on the next 07:00 UTC nightly. A still-open #76 is not evidence about this fix.

**Confirmed again on the final tip.** Dispatch **`32049743593`** (`f0515e6`), **success on every job**,
because run 1 predated the review fixes and the seventh test — a *threaded* handover against the real
`FileLock` — rested on an assumption worth evidence rather than reasoning: that two handles in one
process contend on Windows through `msvcrt.locking` the way two file descriptions do through `flock`.
They do. All three Windows jobs report **6,392 passed, 50 skipped, 4 xfailed, 0 failed** — exactly one
more pass than run 1, which is that test and nothing else.

So the count reconciles across three runs and two platforms without a residue: pre-fix
`6,381 passed + 4 xpassed = 6,385` effectively passing, `+6` new tests = **6,391** (run 1), `+7` =
**6,392** (run 2), with `50 skipped` fixed throughout. **A green Windows run was never going to prove
repair; the arithmetic is what proves it.**


## D-225 — The daily pipeline gets projection behind an opt-in `--project`, fail-closed before any lead earns a disposition

*2026-08-17. Slice **P5a** of the projection spec's P5 (pipeline integration), built across eleven reviewed
tasks on `projection-pipeline-p5a`. **Parent P5 is NOT met by this slice** and must not be marked met.*

**Which P5 this is.** The projection design's own phase table
(`2026-08-13-career-profile-projection-design.md:633`) numbers its phases independently of `PROGRAM.md`.
This entry is about **that** P5 — "Pipeline integration" — and not about the program's *P5 Eligibility
decides*, which is a different phase and is already MET. The labels `P5a`/`P5b` were also used in 2026-08
for **eligibility** work (D-064, D-065, D-068); those are unrelated. Read `P5a` here as
*projection-pipeline-integration, part a*. STATE names the phase explicitly for this reason rather than
writing a bare "P5", which would read as a contradiction of the phase table.

**Context — projection reached no unattended run.** Eleven sessions refined bullets, Gate B went to 0
blockers, and the pool renders one page with zero overfull, but none of it reached `boardwatch run`.
Measured rather than recalled: `projection|profile_bundle|project_pool` returned **zero hits** across
`src/boardwatch/pipeline/`, and `runner.py` passed one `resume_path` that `run_cmd.py` defaulted to
`{config_dir}/resume.yaml`. So the résumé an unattended run produced was **not** the résumé the bundle
work produced.

### The choice

- **Opt-in `boardwatch run --project`.** `resume.yaml` stays the unattended default. §8 of the parent
  design requires that until projection is proven on real JDs, and hand-running one posting at a time is
  not that proof.
- **A run-level preflight that refuses before any lead earns a ledger disposition.** `resolve_projection_run`
  is called after the scan outcome and **before** the ranker, which is invoked with `record_surfaced=False`;
  every shortlist disposition is deferred to `_record_shortlist_dispositions` after the tailor loop. The
  position is the guarantee, not a preference. Stated with its honest limit: *no LEAD DISPOSITION* is
  achievable, *nothing recorded at all* is not — the `runs` row already exists and a scan that ran has
  written posting versions and events.
- **One configuration snapshot per run.** `as_of` is read once, from the same clock the `runs` row uses,
  because it feeds effective-fact resolution and therefore decides *which facts render*. Re-read per lead, a
  run crossing midnight UTC would render two leads from two different fact sets and no digest over either
  résumé could detect it. Verified through the store: all ten rows of the benchmark run carry
  `projection_bundle_revision = 21`, one distinct value.
- **Content *and* transformation lineage on the artifact row.** Document identity (`projection_resume_sha256`,
  `projection_resume_model_sha256`, `projection_posting_version_id`, `master_content_hash`) *and*
  transformation identity (`projection_as_of`, `projection_scorer_id`, `projection_taxonomy_version`,
  `projection_equivalence_version`, `projection_persona_registry_version`, `projection_projection_digest`).
  A hash over the bytes cannot detect that the same bytes were produced under a different scorer or taxonomy.
- **Projection gets its own balanced funnel stage**, entered at the ranker's shortlist rather than at the
  leads projection actually attempted, so leads liveness withheld keep a named bucket instead of vanishing
  between two stages. Folding a projection drop into `tailor_failed` would both make that count a lie and
  hide the loss under a reason naming the wrong stage. Funnel `ARTIFACT_VERSION` **4 → 5**, **globally** —
  see the correction below.
- **A closed run-scoped / per-lead outcome catalog**, with an enum-totality test over every
  `ProjectionIssue` member plus the foreign exception families. Out-of-catalog is a failure, never a new
  bucket: `classify_availability` raises on an unmapped type, so an unrecognised failure aborts the run
  loudly instead of becoming a silent wrong bucket.

### Alternatives rejected

- **Per-lead fallback to the authored résumé.** This is the one that matters, and it is rejected because it
  *succeeds*: every lead enters `summary.tailored`, `built_ids` is derived from exactly that set, and each
  lead earns a **permanent `built`** that the ledger suppresses on every later run. Re-approving projection
  could never recover them, so the fallback would silently convert a configuration problem into permanent
  lead loss. Refusing first is what makes re-approval a real drain.
- **Making projection the default stage.** Flips before the proof condition. Deferred to **P5b**, whose
  criteria are owner-gated and deliberately not inferred here: how many clean projected runs, over how many
  distinct postings, at what defect budget.

### Why differential attribution does not contradict `reports/resume_gate.py`

`resume_gate.py` reasons that a non-zero `tectonic` exit is **environmental** — *"cold support-file cache
with no network, disk full, OOM, killed subprocess"* — and deliberately omits `COMPILE_FAILED` and
`BINARY_MISSING` from `DETERMINISTIC_GATE_REFUSALS`, because burying a lead permanently on that evidence
would delete a real opportunity on the strength of a bad afternoon. An earlier revision of this work
asserted the opposite — that a failing compile means owner content — and an external review caught the
contradiction. **The sibling catalog is right and stands unchanged.**

The resolution is that scope is decided by **attributability, not by cause**, and the two catalogs are
answering different questions:

| | Pinned-base compile | Candidate-loop compile |
|---|---|---|
| What compiled OK just before | nothing — no smaller prefix exists | the same document **minus this candidate**, seconds earlier |
| What can be blamed | nothing; environment and pinned content are equally implicated | the one entry just added |
| Scope | **run-scoped, fatal** (`PINNED_SET_COMPILE_FAILED`) | **per-lead** (`CANDIDATE_COMPILE_FAILED`) |

Neither member asserts a *cause*. `CANDIDATE_COMPILE_FAILED` claims only that the failure is attributable to
one entry, which is an observation about a difference between two compiles rather than a diagnosis — and
because the outcome is per-lead and non-permanent, an environmental failure costs that lead on that run and
nothing more. `PINNED_SET_COMPILE_FAILED` is its own member rather than `COMPILE_INFRASTRUCTURE_FAILURE`
precisely so a working `tectonic` is never misdiagnosed as absent; the remedy it names is to read the
compile log and then look at the pinned entries. The reasoning is written into
`projection/errors.py` beside both members, citing `resume_gate.py`, so the next reader inherits it instead
of re-litigating it.

### Corrections from the whole-branch review, applied before merge

A final whole-branch review (`...-final-review.md`, verdict DO NOT SHIP) found four Important seam defects
and one Minor. All five are fixed on this branch; the two that change what this entry claims are recorded
here rather than in a new entry, because nothing had merged yet and the slice is one decision.

- **The `artifact_version` 4 → 5 bump is GLOBAL, and "byte-identical no-flag output" was an over-claim.**
  Both were recorded as met and both cannot hold: a run without `--project` emits a funnel whose
  `artifact_version` reads 5 where it read 4, so the JSON is not byte-identical. **Ruled by Mit
  (2026-08-17): keep the global bump, narrow the claim.** One emitter with one schema version is right —
  versioning per run type would force every consumer to handle both, for a field whose whole job is to tell
  a consumer which shape it is reading. The guarantee was always about *behaviour*: **no projection stage,
  no lineage keys, unchanged lead outcomes and unchanged dispositions**, and it should never have extended
  to the artifact's own schema-version field. `artifact_version` therefore advances to 5 for **every** run,
  authored ones included. Corrected in the design's §2/§4.5/§5/§6 and beside `ARTIFACT_VERSION` itself.
- **A new per-lead terminal bucket, `ProjectionLeadOutcome.NOT_ATTEMPTED`.** A run-scoped cause can surface
  *inside* the per-lead loop — `select()` raises three, and `compile_prefix` can raise
  `TemplateArtifactError` — and the loop set `fatal` and broke, leaving the current lead and every lead
  behind it counted nowhere while the funnel stage still declared it entered at the ranker's shortlist. The
  stage reported **DOES NOT RECONCILE**: a *fourth* case outside the three the design promises are
  exhaustive (flag absent / preflight refused / balanced run). The bucket names no cause — the typed cause
  stays `projection_availability` and `fatal`, said once for the run — and earns no ledger disposition,
  since `stage_completed=False` on any fatal path. **Hoisting** the pinned-set compile into the preflight
  was the alternative and was rejected: it cannot cover an environment that dies mid-run, so the accounting
  would still be needed, and removing `select`'s per-lead pinned-only compile would delete
  `_fatal_if_infrastructure`'s documented escalation — the very next lead's unattributable pinned failure
  is what turns a real outage from N misattributed content failures into a stopped run.
- **`boardwatch run --project --resume custom.yaml` now refuses** with a `typer.BadParameter` at the CLI
  boundary, before any `runs` row exists. Both options describe an active choice of document source and the
  projected path overwrote the résumé path for every lead, so `--resume` had no effect and said nothing.
  What the combination should mean is P5b's, and silent precedence was the worst of the three answers.
- **`run_tailor` now compares its own resolved transformation dependencies against the recorded lineage**
  and raises `ResumeLineageMismatch` before parsing or rendering, closing the design's §4.1 requirement.
  `_plan_tier_a` reloads the taxonomy, the persona registry and the equivalence table, so a configuration
  edit between projection and tailoring wrote an artifact claiming the frozen snapshot while the transform
  applied a different one — and a document hash cannot see it. Comparing was chosen over threading the
  frozen objects in: it keeps `run_tailor`'s contract at the single optional lineage argument §4.3 ruled
  for, and keeps `ProjectionRunContext` carrying the persona registry's *version* rather than the object.
  The check lands **before** the extraction lookup, which coalesces a taxonomy miss to an empty skill set
  and would otherwise have hidden exactly this.

### Residuals — recorded, not fixed

- **`cli/profile_bundle_cmd.py:990,1042,1111` still use `date.today()`** for three *authoring* `as_of`
  values, while the projection/render path was unified on `utcnow().date()`. Authoring is interactive TTY
  work where a local date is defensible, so scope was deliberately not expanded — but it is a real
  consistency gap, and a local-date authoring decision can disagree with a UTC render decision either side
  of midnight.
- **`store/run_funnel_queries.py:324` hardcodes the field name** in `json_extract(..., "$.projection_kind")`.
  The independent store recount drops the value literal but keeps the *field name*, so a rename of
  `ResumeSourceLineage.kind` breaks it. The fail direction is safe — disagreement surfaces as
  `reconciles: false` — but the docstring's claim about not copying the emitter's constant is only half true.
- **`run_preflight` still loads its own taxonomy per `posting_context` call**, leaving a residual gap in the
  §4.1 freeze. Accepted: a mid-run `taxonomy.yaml` edit makes a later lead raise `NO_JD_EXTRACTION`, routed
  to the per-lead `extraction_unavailable` outcome — the lead is skipped and counted, never rendered under
  mixed rules. Refusing the lead is the fail-safe direction; silently rendering under a second taxonomy is
  not.
- **`projection_ran: bool = False` fails in the omission direction** — a forgetful caller silently claims
  projection never ran. Wrong fail direction for a reporting flag, but bounded, and one caller already
  relies on the default.
- **The run-scoped sibling message still doubles for `bundle_unreadable`**, and five test comments quote the
  old fatal text inexactly.

### What generalises

- **A fallback that succeeds is more dangerous than a refusal that fails.** The per-lead fallback would have
  passed every correctness test — it produces a résumé for every lead — while permanently consuming the
  leads it was meant to protect. When a degraded path writes a permanent record, "graceful" is the failure
  mode, not the mitigation.
- **Two catalogs can give opposite answers about the same exit code without contradicting each other**, if
  one is asking *what caused this* and the other *what can I attribute this to*. Writing the distinction
  into the code beside both members is what stops the third session from "fixing" one of them.
- **Compile cost had to be known before merge, not after.** A serial stage can be operationally broken while
  every correctness test passes; the acceptance criterion was therefore a measurement with a *declared
  ceiling*, recorded in `METRICS.md`, and the ceiling is stated against the **structural** worst case rather
  than the day's observation.

## D-226 — A bullet-less entry is legal only when it is DECLARED; a bullet source that resolves to nothing stays fatal

*2026-08-17. Closes D-221's deferred item "C". Runs on branch `bulletless-entry-representable`, beside two
other live lanes.*

**Context.** D-221 accepted a workaround it labelled temporary: `employment.saayam` carries one
role-scoped bullet it does not want, because the owner's own rule — *"until there are merged PRs, the
resume lists the role + org + dates only"* — could not be expressed. Two gates forbade it jointly, and on
two different paths:

- `pool.py:373` raises `BULLET_PREDICATE_NO_FACTS` when a declared `bullet_predicates` entry resolves to
  no résumé-surfaced fact. This bites on `profile-bundle project`.
- `resume_gate.py:145`, inside `validate_slots`, raises *"entry X has no bullets"*. Its only caller is
  `reports/tailor.py:618`, so it bites on the per-JD **tailor** path, never on the projection path.

**The question this had to answer before any code changed:** what distinguishes an entry that is
*deliberately* bullet-less from one whose bullets *failed to resolve*? Deleting either check answers it by
fiat — a mistyped predicate would begin rendering as a bullet-less entry, trading a loud refusal for a
silent omission of the owner's accomplishments. `errors.py:47-49` had already rejected exactly that
outcome in prose: *"A silently bulletless entry would drop the owner's accomplishments into a document
that becomes Tier A's ground truth."*

**Choice: the distinction is a DECLARATION, carried on the document.** Absence cannot carry intent, so
intent is written down.

- **`EntryDeclaration.bulletless: bool = False`** (`declaration.py`). The declaration is already the
  editorial surface, it is `extra="forbid"` so the key was refused until it existed, and it lands inside
  `projection_digest` — the flag is *inside what the owner approves*, not a switch that bypasses a gate.
- **A model validator refuses `bulletless` together with `claims` or `bullet_predicates`**, mirroring
  `_link_fields_are_paired`. One asserts there are no bullets, the others name where bullets come from;
  the pair is a contradiction and is refused rather than given a precedence order.
- **`BULLET_PREDICATE_NO_FACTS` is untouched.** A declared predicate that matches nothing is still fatal.
  This is the deliberate departure from how STATE.md and D-221 phrased item C (*"should drop the bullet,
  not raise"*): that phrasing is the silent-omission trade, and the flag forbids declaring a bullet source
  precisely so it never has to excuse one that came up empty.
- **`Entry.bulletless: bool | None = None`** (`tailor/model.py`), set by `pool._build_entry` and read by
  `validate_slots`: `if not entry.bullets and not entry.bulletless`. The signature of `validate_slots` is
  unchanged, which was a hard constraint — its only call site is in another live lane's file.

**`None` rather than `False`, and the reason is byte-level.** `serialize.resume_document_bytes` passes
`exclude_none=True`, and its output is what `tailor run` loads back and what the pinned projection golden
compares against. A plain `bool = False` would have serialized onto **every** entry of every résumé,
moving the golden, its generalization sha pin, and every content-addressed document hash. Unset-as-`None`
keeps every existing document byte-identical; only a declared entry emits `bulletless: true`. The flag
must still round-trip — `resume project` writes the document and `tailor run` loads it, and the gate that
reads the flag runs on the **loaded** model — so a test pins `load_resume(resume_document_bytes(r)) == r`
with a bullet-less entry.

**One hash does move, and it is a dedupe key rather than a label.** `Resume.model_dump_json()`
(`tailor.py:485`) does **not** exclude None, so adding the field changes `master_hash` for every master —
and that value is passed as `content_hash` into `get_or_create_master_artifact` at `tailor.py:737`, which
content-addresses the row under `(kind='resume_master', content_hash)` (`store/artifacts.py:54`). So the
first tailor run after this lands finds no row at the new address and creates one: **one extra
`resume_master` row per distinct authored master, once.** Historical tailored artifacts keep pointing at
their original parent, which is correct — those really were derived from the old model shape. Nothing
reconciles or counts `resume_master` rows (no reference in `run_funnel.py`, `pipeline/` or
`store/queries.py`), and no test pins the absolute value; the two assertions over it compare two
*different* masters, which still differ. This is content addressing working as designed rather than a
cost to accept: the hash exists so two masters that merely look alike do not collapse onto one artifact,
and the model's content genuinely changed. **Reaching for `exclude_none=True` to avoid it would be a
mistake** — `Entry` already carries six `X | None = None` fields, so excluding None would drop all of
them from the hash and change it far more than this one field does.

**The change is additive: no existing test was edited.** The three tests that pin today's refusals all
construct entries without the flag, so all three pass untouched — and they are the proof that the
accidental arm still fails: `test_validate_slots_rejects_entry_with_no_bullets`,
`test_slot_validation_failure_falls_back_like_compile_failed` (an empty-bullets `resume.yaml` still
degrades to untailored), and `test_a_bullet_predicate_the_entity_has_no_fact_for_is_refused`.
`test_emit_zero_bullet_entry_omits_its_item_list` already proved a bullet-less entry renders compilable
LaTeX — the renderer needed no change, and its comment had anticipated this state.

Five new tests, each confirmed to fail without its fix, by mutating a **copy** of `src/` under
`PYTHONPATH` (the override proved live before use, so silence was not read as a pass): dropping the
declaration field trips `MALFORMED_DECLARATION`; dropping the validator trips `DID NOT RAISE` on both
contradiction arms; dropping the pool passthrough trips `assert entry.bulletless is True`; restoring the
unconditional refusal trips `ResumeValidationError`; excluding the field from the document trips
`assert loaded == original`.

### Alternatives rejected

- **Omission is the declaration** — an entry naming neither `claims` nor `bullet_predicates` renders
  bare. This has real precedent: `DateRangeDeclaration` rules that *"omitting `end` declares the range
  OPEN"*. Rejected because the two cases are not symmetric. An open range renders a visible word
  (`Present`); a missing bullet list renders **nothing**, so a typo that deletes one line produces a
  quietly shorter résumé with no artifact on the page to reveal it.
- **Infer intent from parked surfaces** — treat "the entity has facts for the predicate but none are
  résumé-surfaced" as deliberate, reusing D-213's parking idiom. Rejected on mechanism: `_resume_facts`
  filters on **four** gates (effective, résumé-surfaced, not application-only, unexpired), so an empty
  result conflates deliberate parking with expiry and application-only scope. It would also site the
  intent two files away from the declaration that renders it.
- **Make `BULLET_PREDICATE_NO_FACTS` conditional on the flag** (keep the predicate declared, let it
  resolve to nothing). Convenient — unparking a fact would restore the bullet with no `projection.yaml`
  edit. Rejected: it converts a typed refusal into an opt-in-gated one, the pattern `errors.py:61-62`
  explicitly refused for `STALE_PROJECTION_APPROVAL`; and the convenience is largely illusory, because
  unparking a fact moves the bundle digest and forces re-approval anyway (D-167).
- **A new `ProjectionIssue` member.** Unnecessary — the deliberate case raises nothing. It would also
  have collided with the P5a lane, which adds a closed `ISSUE_SCOPE` mapping over the whole enum with a
  totality test.

### Consequences, stated rather than discovered later

- **A bullet-less entry is only meaningful when PINNED.** Every scorer returns `Decimal(0)` for an empty
  bullet list (`scoring.py:61-64` guards the division; there is no `ZeroDivisionError` anywhere), and
  `select.py:140` drops candidates scoring `<= ADMISSION_FLOOR`, which is `Decimal(0)`. So a bullet-less
  **candidate** can never be admitted — silently, exactly as a bulleted entry with no JD overlap is
  dropped. Noted, not refused: `no_match_fallback` grows ids **without** scoring (`select.py:211`), so
  the same entry is admissible by that route, and an entry's pinned status is editorial and changes.
- **A shipped bullet-less entry leaves a thin audit trail.** It contributes no row to `meta_json`'s
  `bullets[]` (`tailor.py:277-278`) and no pair to the manifest's `claim_to_bullet`
  (`projection_cmd.py:512-515`). What proves it rendered is the heading round-trip assertion at
  `resume_gate.py:286-287`, which still fires because `_entry_block` always emits `_subheading(e)`.
- **An argument for the change that was not in D-221:** today a bullet-less entry raises
  `ResumeValidationError`, which `tailor.py:624-630` maps to `COMPILE_FAILED` — classified
  **environmental**, not among `DETERMINISTIC_GATE_REFUSALS`. The lead was therefore retry-shaped rather
  than permanently skipped.
- **Gate P1 is narrowed in letter, not in direction.** `PROGRAM.md` item 4 is amended in place. The
  "≥1 bullet per entry" phrasing lives in `DECISIONS-ARCHIVE.md:1126`, which is closed and was not
  edited — this entry supersedes it by number.

### What generalises

- **An absence cannot carry intent.** Two gates can each be correct and still jointly forbid a legitimate
  state, and the fix is never to weaken whichever one is in the way — it is to find the signal that
  separates the deliberate case from the accidental one, and to require that signal be *written*. Where
  no such signal exists, one has to be added to the schema; inferring it from a downstream absence
  reintroduces exactly the silence the gate existed to prevent.
- **A "default" is a serialization decision too.** `bool = False` and `bool | None = None` are equivalent
  to every reader of the model and are *not* equivalent on disk: one of them rewrites every
  content-addressed document in the system. Check what serializes a model before choosing a field's
  default.
- **The owner's data was never touched.** The capability is code; whether `saayam` uses it is a content
  decision, and the `projection.yaml` edit plus its re-approval were handed over rather than made.

## D-227 — The scan lock gets the same reclaim window, and the constant moves to `core/`

*2026-08-17. Closes the second exposure D-224 named and left standing. Taken after D-226; D-225 is the
P5a lane's.*

**Context.** D-224 fixed the bundle writer lock's Windows false-refusal and recorded that
`scan/coordinator.py` had the identical shape — `FileLock`, one `acquire(blocking=False)`, `Timeout`
mapped to a typed refusal — with no window. It was left unfixed there for two stated reasons: a
different subsystem, and no way to share the constant without `scan` importing from `profile_bundle`,
which is the wrong dependency direction. Mit asked for it after seeing the cost.

**Why it is worth more than the lock D-224 fixed, despite never having been observed.** The bundle lock
is driven by hand: an operator sees `bundle_lock_held`, retries, and moves on. **Scanning runs
unattended.** A scan killed mid-run — sleep, reboot, a hard Ctrl-C — leaves Windows tearing its handles
down, and the next *scheduled* scan landing in that window is refused with "another scan is already
running" and returns before schema setup, the runs insert, or any fetch. No error, no crash, no row:
**a silent empty day**, which this codebase's own fail-safe table calls fatal. The refusal is also
`exit 2` and correct-looking, so nothing downstream distinguishes it from real contention.

**Choice.** The window moves to a new `core/lock_reclaim.py` and both locks bind it from there. `core/`
is where this belongs on the existing pattern (`clock.py`, `politeness.py`, `secrets.py`) and it
imports nothing from `scan` or `profile_bundle`, so there is no cycle — verified rather than assumed.
`profile_bundle/locking.py` imports and **re-exports**, so the three test modules that read
`locking.RECLAIM_WINDOW_SECONDS` and my seven tests that patch it needed no changes: the diff stays in
the two lock modules and one test file.

**The known footgun, documented at the source.** Both consumers bind the constants **by name**, so
patching `core.lock_reclaim.RECLAIM_WINDOW_SECONDS` reaches *neither* of them. That is stated in the
new module's docstring, and a test compares both bindings against the source so they cannot silently
drift. Making the modules read `lock_reclaim.X` at call time instead would give one binding, but it
would move each lock's behaviour out of the module where it is documented, and churn every existing
patch site.

**Verification, and its honest limit.** Four new tests in `tests/pipeline/test_scan_lock.py`, all
runnable on POSIX by driving the window directly. Three mutations, all killed: believe-the-first-refusal
(2 tests), deadline dropped (1, via the stand-in's ceiling, in 1.55s — a hang is not a failure), and the
two locks given separate literals (**6** tests, including `test_j`'s fail-fast budget). `test_j`'s
`elapsed < 2.0` became `elapsed < RECLAIM_WINDOW_SECONDS + 2.0`: it is a live-holder path, so on Windows
it pays the window in full, and left as a literal it would have gone flaky exactly as three bundle-lock
tests would have. **The limit: unlike D-224, no failing test ever pointed here.** D-224 had pre-fix
Python 3.13 reporting 5 xfailed / 3 xpassed — a race caught firing. This is a fix by *mechanism*, the
thing D-223 called the weakest part of its own reasoning; what makes it defensible is that the mechanism
is now proven rather than hypothesised, on the same library version, by the same argument, two modules
apart.

### Alternatives rejected

- **Import the constant from `profile_bundle/locking.py`.** Two lines and no new file, but it makes the
  scanner depend on the résumé-bundle subsystem for a platform constant. The dependency would be
  invisible until someone tried to split the packages.
- **Duplicate the literal in `coordinator.py`.** No new module and no dependency at all — and the two
  locks would then agree only by coincidence. M3 is exactly this mutation, and it is the one that broke
  the most tests.
- **Leave it, as D-224 did.** Still defensible on the D-212 best-effort ruling, and it was the standing
  position for several hours. Overturned because the unattended path makes this the more consequential
  of the two locks, and the fix was an hour with the mechanism already in hand.

### What generalises

- **The same defect in two subsystems is one defect with two addresses.** D-224 fixed one and *named*
  the other, which is what made this hour cheap: the second fix needed no diagnosis, only a decision
  about where the constant lives.
- **Severity is set by who is watching, not by the code.** These two acquires are line-for-line the
  same and their consequences are not: one interrupts a person who retries, the other silently skips a
  night's work. A defect's blast radius is a property of its *caller's* supervision.

### The first Windows run was RED, and the defect was in the test, not the lock

Dispatch `32055596667` (`c916423`) failed on **`test (3.11, windows-latest)`** and
**`test (3.12, windows-latest)`** — deterministically, both jobs, one test:
`test_a_refusal_that_stands_is_reported_after_the_window_and_the_wait_is_bounded`, on
`assert elapsed < 1.0`.

**Cause: the assertion timed the wrong span.** Its helper did `get_engine` + `ensure_schema` *inside*
the timed region — creating a SQLite file and running the whole DDL. That is ~50 ms on this Mac and
**over a second on a Windows runner**, so the assertion was measuring the filesystem and comparing it
to a budget meant for the lock wait. The window logic was never involved. Setup is now hoisted into a
`_prepared` helper, the timed region contains the acquire and nothing else, and the budget derives
from the window (`_WINDOW + 1.0`) rather than restating a number.

**Reproduced on macOS before being fixed, then verified against the cause.** A throwaway probe ran both
structures with schema creation slowed to 2 s: the old structure's timed region measured **2.095 s**
against its 1.0 s budget — the Windows failure, on this machine — and the new one measured **0.050 s**,
exactly the window, against 1.05 s. Mutation coverage survives the restructure: no-retry still kills two
tests, and the unbounded mutation still dies in 1.58 s on the stand-in's ceiling rather than hanging.

**What this cost, and what it teaches.** Three hypotheses were falsified by measurement before the log
arrived — the widened `test_j` budget (measured 1.4–1.6 s against 3.0 s), every other timing bound (all
616 test files swept, all already window-derived), and `raise_on_not_writable_file`. A local
"reproduction" also had to be **retracted**: forcing the window on under macOS only re-fails
`test_the_window_is_asked_for_on_windows_only`, which is the simulation's own artifact, and the full
window-on suite passes (6,445 tests). **Forcing a platform's *constant* does not simulate its
*backend*** — `msvcrt` versus `flock`, and a filesystem an order of magnitude slower, are exactly what
was left out, and the second is what broke.

**The log was reachable the whole time.** `gh run view --log` refuses while any job in the run is still
running, which cost most of the delay; **`gh api repos/{owner}/{repo}/actions/jobs/{id}/logs
--allow-escape-sequences` serves a completed job's log immediately.** Use it when one job fails and
others are still going.

**Green on the re-dispatch.** Run `32065805682` (`655c474`): every job success or skipped, and all three
Windows jobs report **6,397 passed, 50 skipped, 4 xfailed, 0 failed**. The red run reported `1 failed,
6,396 passed` on the same three, so `6,396 + 1 = 6,397` — the one failing test passes and **nothing else
moved**, which is what distinguishes a fix from a suppression here just as the xfail arithmetic did for
D-224.

## D-228 — Fixture drift is three separate gates, and the staleness one enforces a review deadline rather than freshness

*2026-08-17. Closes the "fixture + corpus drift" line that has sat under STATE's owner-gated list as
"needs live network / a missing generator". The generator half is built here; the network half is not,
and stays Mit's.*

**Context.** `CLAUDE.md` requires that *"fixtures must be derived from live config or fingerprinted so
drift fails the test"*. The task brief asserted there was **no fixture drift tooling at all**. That is
false for one of the four drifts, and the correction reshaped the whole design: `SHIPPED_DATA`
(`tools/generalization/allowlists.py`) already pins **all 31 fixture `.json` files** with sha256, and R7
(`inventory.py:195-212`) hashes their bytes and fails on mismatch, inside both `make check` and the CI
`generalization` job. Confirmed live, not recalled: the greenhouse `normal.json` pin `sha256:26dced45…`
equals the hash on disk. Building a second manifest would have duplicated a working gate.

**What was actually missing**, each verified first-hand:

| Gap | Why R7 cannot see it |
|---|---|
| Fixture set vs the provider registry | A missing directory has no bytes to pin |
| The six `README.md` files | `.md` ∉ `DATA_SUFFIXES`, so they are outside `inventory_scope` |
| The 987-row eligibility corpus | It is a `.py`, likewise outside scope |
| Capture age | No hash detects it, by construction |

**Choice — three rules appended to `ALL_RULES`, not a new gate.** R13 coverage, R14 pins, R15 review
deadlines, in `tools/generalization/fixtures.py`; the write side is a separate `tools/fixture_refresh`.
A standalone `Makefile` target was rejected on evidence: **`index-check` runs in `make check` but has no
CI job**, and the only `tools.` invocation in CI is `python -m tools.generalization`. A new target would
have been locally-green and CI-blind. Cost measured at 26.3 ms (R13 0.97, R14 25.31, R15 0.01).

**R15 fails rather than warns, and the drain is what makes that defensible.** A warning loses to a
6,439-test run. A single global max-age constant was rejected because bumping one number silences six
providers at once. Instead each provider declares `review_by` (captured + 90 days), and red is
actionable **without network**: `--extend <provider> --days N --reason "…"` appends a dated, reasoned
rollover, so a capture on its fourth extension is visibly a different fact from one on its first. This
lands green today; the first red is 2026-09-11 (greenhouse, whose `review_by` is 2026-09-10 — the
deadline is the last **green** day, `today > review_by`).

**It is named honestly.** `--extend` restores green with a reason and no evidence anyone checked the
live API, so R15 enforces *"somebody looked on schedule"*, **not** *"this matches production"*. Calling
it a freshness gate would be a lie, and the module docstring says so.

**Two findings recorded, neither fixed here.** The corpus docstring says *"Regenerate with
`scratchpad/gen_corpus.py`"*; that file has **never been committed** (`git log --all -S'gen_corpus'` hits
only the docstring) and `scratchpad/` is gitignored, so it never could be — **the 987-row oracle is
unregenerable**. And four fixtures are read by no test: `workable/dead_404.json`,
`workable/normal_response_headers.json`, `smartrecruiters/normal_response_headers.json`,
`workday/normal_response_headers.json`.

### Alternatives rejected

- **A second fingerprint manifest (`tests/fixtures/MANIFEST.json`).** The brief's sketch. Rejected once
  R7 was found to already pin all 31 JSONs — it would have been a parallel, divergeable copy.
- **A digest over the parsed `CASES` literal instead of the whole corpus file.** Rejected after external
  review falsified it: `CASES` is a **mutable list** consumed by `parametrize` further down, so
  `CASES[0] = (...)` appended below the literal rewrites the oracle while a literal-only digest stays
  green. Proven in `test_appending_a_mutation_line_to_the_corpus_fails`. Whole-file hashing is also
  simpler and moots `repr()` canonicality; `.gitattributes` already pins `eol=lf` **for R7's sake**, so
  it is byte-stable cross-platform.
- **Enumerating fixture directories with `Path.iterdir()`.** Rejected: untracked scratch would fail the
  gate locally and vanish in CI. Enumeration reads `repo.files` (git-tracked), pinned by a test that
  asserts `repo.mode == "git"` so it cannot pass vacuously in walk mode.
- **Letting `fixture_refresh --record` rewrite `CORPUS_ROWS`.** Written that way, then removed in the
  same change after code review. `--record` derived the pin AND the row count from one read of the
  corpus and wrote both, so a corpus truncated to 500 rows satisfied each of them at once — the "second
  path" was the same path, and the only flow in which the two were independent was a monkeypatch no
  operator uses. `--record` now prints the measured count and **refuses** (exit 2) when it disagrees
  with the constant, directing the operator to a hand edit. **The independence is the human, not the
  ast.** Also bucketing a provider's files by **basename**: `ashby/docs/README.md` satisfied R13's
  presence check while the pinned `ashby/README.md` was deleted, and R14 skipped the absent file to
  defer to the R13 that had just been fooled — all fifteen rules green with the pinned document
  replaced. Fixed three ways: relative paths not basenames, subdirectories refused outright, and R14
  reporting its own missing pin.
- **A rolling global `max_age_days`.** One edit erasing six independent signals.
- **Warn locally, fail only in CI.** Manufactures the "green `make check` is not green CI" split this
  repo has already been bitten by.
- **Storing provenance as a JSON/TOML data file.** Kept as a typed Python dict because it is tools
  *code*, so it needs no pin of its own and `mypy --strict` checks it. An earlier draft justified this
  as avoiding a "recursion" with R7 — **that reasoning was wrong** (a data file would simply need one
  more hand-maintained pin) and is recorded so it is not re-derived.
- **Automated orphan-fixture detection.** Needs source-grepping for filenames, which false-fires on
  dynamically built names, and `workday/normal_response_headers.json` is deliberately unread — its
  README records `{"etag": null, "last_modified": null}` so the absence of validators reads as
  deliberate. Reported as a finding instead.
- **Corpus rule-coverage checking.** The 987 cases already execute production `evaluate` against the
  live catalog every run, so a catalog change that invalidates the corpus already fails 987 tests
  loudly. Only tamper-evidence was missing.

### What generalises

- **"There is no tooling for X" is a claim to measure, not a premise to build on.** The brief said no
  fixture drift tooling existed; a working sha256 gate over all 31 fixtures had been running in
  `make check` the whole time. One `grep` for the path prefix in `allowlists.py` settled it, and the
  answer deleted an entire planned deliverable.
- **A tamper-evidence digest must cover everything that can change the value, not the value's
  declaration.** Hashing the literal was intuitive and wrong, because the consumer reads a *mutable*
  object built from it. The question to ask is "what does the consumer actually read?", not "where is
  the data written?".
- **A gate that enumerates the filesystem directly and a gate that enumerates git are different gates.**
  The difference is invisible until it produces a local red that CI cannot reproduce.
- **Name the guarantee you actually provide.** The gap between "fixtures are fresh" and "someone was due
  to look" is the whole value of the check, and a name that oversells it converts a useful signal into
  a false assurance.
- **A "second path" is only second if the REMEDY cannot move both ends.** The corpus row count was
  argued independent because it is read by `ast` and the pin by bytes. But the documented repair
  recomputed both from one read, so in the only flow anyone runs they moved together. Ask what the
  fixing command writes, not just what the checking code reads.
- **Two rules that defer to each other are one rule with a hole.** R14 skipped a missing file "because
  R13 owns that report", and the bypass was precisely to satisfy R13's report while defeating R14's.
  A rule that owns a pin must report that pin's absence itself, even at the cost of a duplicate line.
- **Mutation tests inherit the shape of the author's imagination.** Twenty-one mutations all changed
  file *contents*; the bypass changed the *directory structure*, and nothing in the suite could see it.
  When enumerating mutations, walk the categories — content, structure, absence, ordering, encoding —
  rather than listing the ones that come to mind.

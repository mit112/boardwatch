# Starter predicate catalog — Task-1 audit (Gate B, Slice A)

**Artifact audited:** `src/boardwatch/profile_bundle/resources/predicate-catalog-v1.yaml`, the builtin
starter vocabulary `init` now seeds into every fresh bundle (`predicate_catalog.builtin_catalog(1)`).

**Why this document exists.** §5.2 of the extraction design makes the predicate audit Task 1 with a
replan checkpoint, because an unaudited catalog is exactly the class of defect the review kept
finding. The mechanical invariants (`tests/profile_bundle/test_predicate_catalog.py`) catch a *class*
of error — a dead enum member, an unreachable grounding guard, an unavailable version. They do **not**
substitute for reading each row. This is that reading: for each of the 42 rows, "unchanged from the
comprehensive example, reviewed" or a stated change with its reason.

**Provenance.** The 41 rows are the comprehensive-example catalog
(`examples/comprehensive/policy/predicates.yaml`) transcribed verbatim, then two sanctioned changes
(§9 Task 1) applied. From this point the builtin and the example are independent artifacts: the
example stays un-amended so its own comprehensive-bundle tests stay pinned, and the builtin is what
ships and what the §5.2 gate runs over.

## The changes from the example

| Change | Row | Reason |
|---|---|---|
| **Amended** | `technology.used` | Added `incidental` to `legal_usage_contexts`. A familiarity-level skill is a legitimate career state that must remain *effective* yet never ground verification (§5.1); `grounding_facts` already excludes `incidental`, so grounding stays clean, and `effective.py`'s `may_ground_skill and usage_context != INCIDENTAL` guard becomes reachable. |
| **Added** | `project.name` | New predicate — string, cardinality one, `project` subject, mirroring `project.summary`'s subject/surface/evidence shape. `render/latex.py` shows `title` is a project's displayed name (`heading` is only its null-fallback); project identity had no predicate. |
| **Rostered** | `measured`, `secondary_only`, `multiple_sources` | Not a row change — a `VerificationBasis` roster (`NOT_ADMITTED_VERIFICATION_BASES`). These three enum members are admitted by 0 of 42 predicates: a fact-only résumé starter establishes nothing by measurement or multi-source corroboration. Rostering them with a reason keeps §5.2 invariant 1 honest (a NEW accidental orphan still fails) without adding metric/multi-source predicates the starter has no bucket for. **Owner-decided 2026-08-14** (chose "roster them, with reasons" over dropping `VerificationBasis` from the invariant or adding predicates). |

Also decided at the mapping layer (not a catalog change): `project.summary` leaves the builtin
extraction mapping (it is no longer `heading`'s target) and joins the mapping's
`not_reachable_from_builtin_mappings` roster when that mapping is seeded (Slice B).

## Per-row account (42 rows)

All rows below are **unchanged from the comprehensive example, reviewed** — each is field-agnostic and
appropriate for a multi-tenant starter (no Mit-specific or single-field content) — **except** the two
marked, which carry the changes above.

| # | predicate_id | Verdict |
|---|---|---|
| 1 | `person.professional_name` | unchanged, reviewed |
| 2 | `person.professional_headline` | unchanged, reviewed |
| 3 | `education.institution` | unchanged, reviewed |
| 4 | `education.credential` | unchanged, reviewed |
| 5 | `education.field` | unchanged, reviewed |
| 6 | `education.start_date` | unchanged, reviewed |
| 7 | `education.end_date` | unchanged, reviewed |
| 8 | `education.result` | unchanged, reviewed |
| 9 | `employment.organization` | unchanged, reviewed |
| 10 | `employment.title` | unchanged, reviewed |
| 11 | `employment.date_range` | unchanged, reviewed |
| 12 | `employment.responsibility` | unchanged, reviewed |
| 13 | `employment.accomplishment` | unchanged, reviewed |
| 14 | `employment.team_size` | unchanged, reviewed |
| 15 | `project.summary` | unchanged, reviewed (leaves the builtin *mapping*, not the catalog) |
| 16 | `project.name` | **NEW** — see table above |
| 17 | `project.start_date` | unchanged, reviewed |
| 18 | `project.end_date` | unchanged, reviewed |
| 19 | `project.contribution` | unchanged, reviewed |
| 20 | `deployment.environment` | unchanged, reviewed (software-flavoured but optional and harmless) |
| 21 | `technology.used` | **AMENDED** — added `incidental`; see table above |
| 22 | `publication.title` | unchanged, reviewed |
| 23 | `publication.venue` | unchanged, reviewed |
| 24 | `publication.date` | unchanged, reviewed |
| 25 | `entity.location` | unchanged, reviewed |
| 26 | `entity.url` | unchanged, reviewed |
| 27 | `recognition.name` | unchanged, reviewed |
| 28 | `recognition.issuer` | unchanged, reviewed |
| 29 | `award.date` | unchanged, reviewed |
| 30 | `certification.issue_date` | unchanged, reviewed |
| 31 | `certification.expiry` | unchanged, reviewed |
| 32 | `affiliation.role` | unchanged, reviewed |
| 33 | `affiliation.date_range` | unchanged, reviewed |
| 34 | `course.title` | unchanged, reviewed |
| 35 | `presentation.title` | unchanged, reviewed |
| 36 | `presentation.date` | unchanged, reviewed |
| 37 | `presentation.venue` | unchanged, reviewed |
| 38 | `patent.title` | unchanged, reviewed |
| 39 | `patent.filing_date` | unchanged, reviewed |
| 40 | `patent.grant_date` | unchanged, reviewed |
| 41 | `application.requires_sponsorship` | unchanged, reviewed |
| 42 | `application.authorized_regions` | unchanged, reviewed |

## §5.2 gate status

| Invariant | Status |
|---|---|
| 1 — no dead enum member (Surface, UsageContext, VerificationBasis) | **MET** — all Surface and UsageContext members admitted; the three orphan bases rostered. |
| 2 — no unreachable grounding guard | **MET** — the one `may_ground_skill` predicate (`technology.used`) admits `incidental`. |
| 3 — §5.1 behavioural (incidental fact is effective, does not ground; professional does) | **OWED** — needs a builtin-catalog-backed grounding context; the existing synthetic fixture uses the un-amended example catalog. Tracked in STATE. |
| 4 — package-level reachability (catalog ↔ builtin mapping) | **OWED** — the builtin extraction mapping does not exist yet (Slice B). Tracked in STATE. |
| 5 — version handling (unavailable version → exit 3) | **MET** — `builtin_catalog(unsupported)` raises `UnsupportedPredicateCatalogError`. |

# Pre-flight — career-profile projection implementation plan

Read-only verification of `docs/superpowers/specs/2026-08-13-career-profile-projection-design.md`
(revision 3, 716 lines) against the code at `f8991c6`, run **before** writing the implementation
plan. Nothing in `src/` was edited.

Why it exists: a spec-reviewed 1208-line plan in this repo still carried 6 defects plus 1 repo-wide
issue, and preflighting is what found them. Revision 3 had already survived three external review
rounds, all REWORK.

**Score: the load-bearing premise HOLDS. 4 spec claims are FALSE, 12 citations have drifted, and
7 facts the plan needs are absent from the spec entirely.**

---

## 1. The premise the whole design rests on — CONFIRMED

**`LatexRenderer.emit` never reads `Resume.header` or `Resume.education`.** Verified independently,
including every helper and the template itself:

- `emit` (`tailor/render/latex.py:201-241`) reads `resume.skill_groups` (via `_skills`, `:126-136`),
  `resume.entries` (via `_experience` `:150-165` → `_subheading` `:110-123` → `_bullet_lines`
  `:139-147`; `_projects` `:168-180`), `resume.extracurricular` (`:183-190`), `resume.title`
  (`:211-215`). No helper touches `.header` or `.education`.
- `resume_base.tex:72-80` hardcodes the name/contact block and `:87-93` hardcodes Education. The
  only substituted slots are `%%TITLE_*%%` (`:74-75`) and `%%SECTIONS_*%%` (`:95-96`).
- A user template override cannot change this: `emit` substitutes no other marker.

So §3's scope decision (v1 projects only `skill_groups`, `entries`, `extracurricular`) stands, and
D-156 is correct.

---

## 2. FALSE claims — the plan must not carry these forward

### 2.1 An out-of-catalog `kind` does not fall through to Experience. It vanishes.

§4.1 says *"the renderer routes on `== "project"` with everything else falling through to
Experience, so a typo would render silently."* Both section filters are **equality** tests:

- `tailor/render/latex.py:155` — `matching = [e for e in entries if e.kind == "experience"]`
- `tailor/render/latex.py:170` — `matching = [e for e in entries if e.kind == "project"]`

A `kind` that is neither matches **neither section**, so the entry and every bullet in it are
**silently omitted from the PDF**. Nothing in `src/` validates `Entry.kind` — not `validate_slots`,
not `validate_layout`. Only `_subheading` (`:115`) falls through, and only for heading *style*.

**Consequence for the plan:** §4.1/§7's closed-catalog rule is more load-bearing than the spec
argues, and the test must assert the entry is **absent from the rendered source**, not
mis-sectioned.

### 2.2 Artifact metadata is already rich; only bundle lineage is missing.

§4.2 says artifact metadata *"records only master kind and validator version"*
(`reports/tailor.py:685-708`). That describes the **master** artifact alone (`:690`). The
**tailored** artifact (`:694-705`) passes a `meta` built at `:669-676` from `_trace` (`:279-310`),
carrying at least: `validator_version`, `equivalences_version`, `master_content_hash`, `posting_id`,
`posting_version_id`, `jd_skills`, `format`, `persona_id`, `resolved_title`, `typst_pdf_built`,
`pdf_uri`, `dropped`, `bullets`, `coverage`, `degraded`, `degrade_reason`, `compile_log_uri`,
`master_artifact_id`.

The spec's *conclusion* survives — no bundle revision is recorded, so staleness is undetected — but
slice P5 must be scoped as **"add bundle-lineage keys to an already-rich meta dict"**, not "there is
no metadata to speak of."

### 2.3 The effectiveness gate can pass vacuously.

§7 cites `effective.py:76-147` for *"effectiveness is derived separately"*. Wrong range, and it
undercuts its own sentence: `76-147` spans five functions, and `103-147` **is** the surface-permission
logic effectiveness is claimed to be separate from. The derivation is `effective_fact_ids`
(`effective.py:76-95`), which depends on `superseded_fact_ids` (`:60-73`, outside the range) and on
`records_blocked_by_unresolved_conflicts` (`validation/referential.py:708-721`, a different file).

**The substantive defect:** `eligible_fact_surfaces` (`effective.py:121-129`) returns `frozenset()`
for a non-effective fact. So if the plan implements §7's *surface* row through the public API, the
*effectiveness* row is not independent of it and its test **passes without testing anything**. The
two rows diverge only for **expiry**, which `effective.py:29-32` deliberately excludes.

The plan must state which API each row uses.

### 2.4 §4.1 contradicts itself on the value-kind count.

Spec line 264 says `FactValue` has **nine** typed shapes; line 267 says **ten** and corrects
revision 2 for saying nine. Revision 3 fixed the table and left the sentence standing. The code has
ten (`profile_bundle/models/facts.py:52-61`), and the spec's names and order are exactly right.

---

## 3. Facts the plan needs that the spec does not state

1. **There is no `Resume` serializer anywhere in the repo.** Verified three ways.
   `model_dump_json()` is used at exactly two sites (`reports/tailor.py:433`, `:503`), both for
   SHA-256 hashing. `scaffold_template()` writes a static string constant. `Resume` is **load-only**
   — §4.2's `resume.projected.yaml` needs a serializer built from scratch, and `yaml.safe_dump` is
   forbidden (it emits documents the restricted loader refuses). Route it through
   `profile_bundle/yaml_writer.document_bytes(payload, logical_path=...)`, which additionally
   **refuses floats, tuples and non-string keys**.

2. **`SkillGroup` has `label` + `items: list[str]`, not `skills`** (`tailor/model.py:6-9`). The
   spec's `projection.yaml` declares `skills: [skill.python, ...]` — bundle **ids**. Nothing
   specifies how an id becomes the display string in `items`. Unspecified mapping; the plan defines
   it (`SkillRecord.canonical_name`, `profile_bundle/models/skills.py:32`).

3. **`effective_skills` is harder to extract than §4 claims.** The logic is a closure
   `cover(b: Bullet) -> int` (`plan.py:76-78`) taking a `Bullet`, not a `str`, because it keys into a
   `swaps_by_bullet` memo that `build_plan` reuses at `:97` for op emission. It returns a **count**,
   never a set — there is no set-returning callable to promote. The spec's signature also has the
   wrong parameter name and order: `build_plan(resume, jd_skills, table, taxonomy)` — `table`, not
   `equivalences`, and `taxonomy` last.

4. **§9's "the shared callable is the only implementation" test is built on a false premise.**
   There are **four** inline coverage implementations and they are **not equivalent**: only
   `plan.py:77` unions the equivalence-swap images; `reports/tailor.py:255` and `:271` omit swaps;
   `tailor/coverage.py:55-61` uses a different corpus (bullets + skill items, master-only, no
   `jd_skills` argument). Folding 255/271 in would **change their emitted audit values**. Narrow the
   test to *"`build_plan` and projection call the same callable."*

5. **The JD skill set has no producing function.** It is an inline SQLAlchemy `SELECT` on
   `extractions`, duplicated in **five** places (`reports/tailor.py:342-355`, `cli/top_cmd.py:204`,
   `:471`, `cli/show_cmd.py:121`, `reports/notify.py:94`), keyed on `taxonomy.version`, and **a cache
   miss silently yields `set()`**. The posting-context seam must extract it — otherwise it is the
   sixth copy and exactly the duplicated query §4 warns about. And "no extraction row" must be a
   named fatal, not a silent slide into `no_match_fallback`.

6. **There is no single public bundle loader.** It is three calls, and every consumer in `src/` does
   all three: `storage.read_current_once(bundle_root)` → `storage.selected_documents(selection)` →
   `validation.context.context_from_documents(documents, root=…, mode=…)`. The fused private form is
   `inspection.py:604 _selected`.

7. **The packaged example bundle is a DRAFT** with `bundle_digest: ''` and no blobs, so
   `read_current_once` cannot reach it. Every test must go through
   `tests/profile_bundle/conftest.py`'s `synthetic_bundle` fixture (`:202-208`) or `materialise`
   (`:179-188`), which copies it to `drafts/baseline/` and writes the one blob.

8. **`resume_max_pages` is not per-posting.** It is a single column on the singleton `profile` table
   (`store/tables.py:203`, `CheckConstraint("id = 1")`). The floor lives at the call site, not in the
   accessor: `max(1, row.resume_max_pages) if row is not None else 1` (`reports/tailor.py:555`). A
   reader that skips it re-introduces the 0-page bug that comment describes.

9. **`Entry.kind` is an open `str` with a default** (`tailor/model.py:38`), and `Resume.title`
   already exists for the persona headline (`:55`) — projection must leave it `None`, since `tailor`
   owns persona.

---

## 4. The import wall — where the package must live

`tests/profile_bundle/test_profile_bundle_tailor_isolation.py` walks the import graph **outward from**
`TAILOR_ROOTS`, which is `glob("boardwatch/tailor/**/*.py")` + `cli/tailor_cmd.py` (`:41-44`).

- A top-level `src/boardwatch/projection/` is **not** a tailor root and **not** a `profile_bundle`
  root, so it may import both sides. Both wall tests still pass.
- `src/boardwatch/tailor/projection/` would be a tailor root and would break
  `test_no_production_tailor_module_reaches_the_profile_bundle` (`:107-115`) **and**
  `test_no_production_tailor_file_names_the_bundle_package_in_text_either` (`:135-144`) immediately.
- The root-set floors (`len(TAILOR_ROOTS) >= 25`, `len(roots) >= 40`) are floors; adding files is safe.

**Slice P5 must re-verify the closure.** Wiring projection into `pipeline/runner.py` is the one way
an edge could reappear, and the test would only catch it if a tailor root transitively reaches the
runner.

---

## 5. Corrected citations

Every one of these is quoted or relied on by the spec and would otherwise be copied into the plan.

| Spec claim | Spec cites | Actual |
|---|---|---|
| `_ALLOWED_MARKERS`, `emit` | `render/latex.py:54-55` | **`tailor/render/latex.py:55`** — `src/boardwatch/render/` does not exist. §11 inherits the same wrong path. `:54` is `_MARKER_RE` |
| `build_plan` emits only Reorder/Delete/EquivalenceSwap | `plan.py:87-103` | `plan.py:65-104`. Cited range omits the signature and **both early returns** (`:69`, `:82`) that §10's P0 gate depends on preserving |
| `evaluate_compile` | `resume_gate.py:115-131` | `resume_gate.py:115-127` (`:128+` is `validate_slots`) |
| master hash | `reports/tailor.py:430` | `reports/tailor.py:433` (`:430-432` is the comment) |
| `taxonomy.extract` public and pure | `extract/taxonomy.py:47-48` | `extract/taxonomy.py:49-50` — and it is a **method on a frozen dataclass**, not a module function |
| header has no valid email | `tailor/load.py:59` | Check at `load.py:56`, pattern at `:37`, inside `validate_master` (`:40-67`), reached from `load_resume` at `:85`. `:59` is the message string |
| effectiveness derived separately | `effective.py:76-147` | `effective.py:60-95` **+ `validation/referential.py:708-721`** |
| expiry checked by dated completeness | `completeness.py:219-293` | `completeness.py:219-318` — the range cuts off `_declared_expiry` (`:296-318`), which selects the governing date. The value-date check is **inert** without it |
| `evaluate_compile`'s four arms | — | Returns a frozen dataclass `GateResult` (`resume_gate.py:106-112`) whose `reason` is a `GateReason` **StrEnum with ten members** (`:66-79`). The four are what `evaluate_compile` alone returns; `page_count` is the attribute |
| `pdfinfo` returns `None` | `reports/tailor.py:167-171` | `_pdf_page_count` is `:165-176` with **three** `None` returns (`:171` missing binary, `:174` non-zero exit, `:176` unparseable). Laundered at `:193-197` |

### Miscited decision records

- **§8's D-141 is not the silent-success class.** D-141 (`DECISIONS.md:4051`) is a blocking `open()`
  that hung with no output (`timeout 20` → exit 124) — a silent *hang*. D-138 fits; D-141 does not.
- **§9's D-149 does not support the "98 tests / 5 of 13" figure.** The real source is
  `METRICS.md:2266`, and it says **documents**, not "classes". D-149 (`:4718`) is the blocked
  `STATE.md` trim. Cite `METRICS.md:2266` plus D-142 for the shape.

---

## 6. Two spec tests that cannot work as written

1. **§9's effectiveness before/after control is impossible with the fact the spec has in mind.**
   `fact.packet-pantry.legacy-language.001`
   (`examples/comprehensive/facts/projects/project.packet-pantry.yaml:214-233`) is the stale,
   résumé-surfaced, conflict-group-free fact §7 promises exists — **confirmed, it is there** — but it
   fails on `verification_state: stale`, so it can never demonstrate a *date-driven* before/after
   transition. The fact that can is `fact.example-credential.expiry.001`
   (`examples/comprehensive/facts/certifications.yaml:73-93`): `verified`,
   `expires_at: '2026-07-01'`, and still **effective** by `effective_fact_ids`. The plan needs both
   fixtures and must know they exercise different code paths.

2. **§5's "reuse the bundle's own owner-gate pattern" breaks a repo-wide test.**
   `tests/profile_bundle/test_profile_bundle_cli_approval.py:427-447` asserts by `rglob` over `src/`
   that **exactly two files** call `approval_stamp_bytes(`. Worse, `ApprovedVia` is a closed
   single-member enum (`models/history.py:180-184`) baked into the shipped JSON schema
   (`resources/career-profile.schema.json:187,207`), and `ApprovalStamp.candidate_content_digest`
   means *bundle candidate*, not projection. So `approve-projection` must define a **separate**
   projection-stamp type with its own storage, not reuse `ApprovalStamp`.

Also note: adding diagnostics to the profile-bundle family means editing the **closed** `IssueCode`
catalog (`profile_bundle/errors.py:49-221`) plus `STATE_REFUSAL_CODES` / `COULD_NOT_COMPLETE_CODES` /
`_BLOCKER_CODES` / `_INFORMATION_CODES` — and `tier_of` is asserted total by a test.

---

## 7. Two things worth arguing before P0

- **`{@status}` is not a uniform field.** `display_name` is on `_EntityBase`
  (`models/entities.py:137`) so it is universal, but `status` is declared per subclass with **ten
  different enums** (`:151-205`) and is **absent on `PersonEntity`** (`:143-145`), deliberately. The
  §4.1 grammar table needs the caveat, and P1's validator needs a per-entity-type check rather than
  one field lookup.
- **§6's termination argument is true but not proved by its own evidence.** `resume_base.tex` does
  contain none of `table`/`figure`/`float`/`minipage`/`multicol` — but it loads `tabularx` (`:14`)
  and uses `\begin{tabular*}` three times (`:42`, `:50`, `:59`). `tabular*` is non-floating so the
  conclusion holds; the plan must not restate the five-word grep as the proof.
- **§6's two falsifying probes (`4 > 2`, `2.0 > 1.5`) have no fixture, script or log in the repo.**
  They lived in external reviewers' contexts. The arithmetic is self-consistent and §9's tests are
  constructible from the numbers, but the plan must **author** those fixtures rather than name them.

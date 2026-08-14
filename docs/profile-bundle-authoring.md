# Authoring and recovering the career-profile bundle

`boardwatch profile-bundle` is a private, revisioned, filesystem-only store for the career facts a
résumé is assembled from. This document is the authoring contract: what the format admits, what each
command does, what every exit code means, and how to get out of the states that go wrong.

Every example here is synthetic. No command in this family submits an application, fills a form, or
drives a browser.

---

## 1. What this is, and what it is not

The bundle exists so that a professional fact has one place to live, one identity, and one auditable
chain from the fact to the evidence for it. It has three delivery gates and they are not the same
thing.

| | Status | What it covers |
|---|---|---|
| **Gate A** | **Implemented, not met** | The generalized mechanism: typed models, the closed file grammar, validation, digests, drafts, approval, promotion, recovery. Reachable from a terminal. |
| **Gate B** | **Prohibited until Gate A is met and independently reviewed** | A real person's canonical baseline, and the bundle-to-`Resume` bridge. |
| Later gates | Deferred by design | Role-family projection, persona selection, claim selection, taxonomy integration, rendering, JD evaluation. |

**Gate A being implemented is not Gate A being met.** The acceptance gate has not been declared met,
so the on-disk grammar, the digests and the JSON reports are all still allowed to change. Nothing
outside `boardwatch.profile_bundle` should depend on them yet.

**There is no bundle-to-`Resume` bridge, deliberately.** `boardwatch tailor` still reads
`{config_dir}/resume.yaml` and knows nothing about this package; a test over the import graph holds
that boundary in both directions. Building the bridge is Gate B's job and it is out of scope here.

---

## 2. Where it lives

The bundle root is resolved at the command boundary, not stored as a setting:

| | Path |
|---|---|
| Default | `{config_dir}/career-profile` |
| Override | `--bundle PATH`, accepted by every command in the group |

`config_dir` is `BOARDWATCH_CONFIG_DIR` if set, else the platform config directory — on macOS,
`~/Library/Application Support/boardwatch`. So the default macOS root is
`~/Library/Application Support/boardwatch/career-profile/`.

The path is machine-local. It is not a `Settings` field, it does not affect lead selection, and it
does not change `policy_version`. A bundle derives its identity from its validated content, so it can
be moved or restored into an encrypted backup location and addressed with `--bundle`.

`boardwatch profile-bundle init` creates the root's closed member list:

```text
career-profile/
  approvals/          one approval stamp per approved candidate digest
  blobs/sha256/       content-addressed evidence captures, shared across revisions
  drafts/             writable working copies
  revisions/          immutable, digest-named revisions
  local-sources.yaml  the private sidecar (see §5)
```

Two more root members appear once they are needed and are never created by `init`:
`CURRENT` (written by the first `promote`) and `career-profile.lock` (the exclusive writer lock).
Anything else at the root is reported by `inventory` as an orphan and is never deleted.

**A path that is not a bundle is refused, by name.** Every command that reads a bundle answers
`bundle_not_found` at exit 1 if the root is not a directory — whether you mistyped `--bundle`, or
omitted it and the default root has never been initialised. No command creates the root as a side
effect of failing, and the two that take the writer lock check before taking it, because the lock
file's own creation would otherwise leave a new empty directory as the only trace of the mistake.
`init` is the drain: it is the one command for which an absent root is normal input.

```console
$ boardwatch profile-bundle inventory --bundle ~/career-profil
profile-bundle inventory: findings
error: bundle_not_found: there is no bundle at this path; nothing was read and nothing was created. `init` creates one, and --bundle names an existing one somewhere else
EXIT=1
```

---

## 3. The closed tree, and the closed file grammar

A revision's logical content is exactly 31 declared documents plus two entity-owned directories.
The grammar is closed **in both directions**:

- **An undeclared file is a validation error.** This is what keeps a later projection design from
  becoming authority by dropping `policy/persona.yaml` into a revision.
- **A declared file is required.** Without that half, "the predicate catalog is empty" and "the
  predicate catalog is gone" would be the same observation.

```console
$ boardwatch profile-bundle validate --bundle <root> --draft demo
profile-bundle validate: findings
1 error, 0 blocker, 0 warning, 0 information
candidate digest: not computed by this run
error: unknown_file: policy/persona.yaml: not a declared bundle document
```

The tree:

```text
manifest.yaml
facts/
  identity.yaml            one person entity and its contact records
  education.yaml
  experience/<employment-id>.yaml   entity-owned, basename == entity ID
  projects/<project-id>.yaml        entity-owned, basename == entity ID
  publications.yaml  awards.yaml  certifications.yaml
  affiliations.yaml  courses.yaml  presentations.yaml  patents.yaml
claims/
  bullet-candidates.yaml  summary-candidates.yaml
skills/inventory.yaml
metrics/records.yaml
evidence/records.yaml
conflicts/
  groups.yaml  rulings.yaml
policy/
  predicates.yaml  units.yaml  relations.yaml  sources.yaml
  skill-categories.yaml  assertion-tags.yaml  secret-scan.yaml
relations/records.yaml
imports/
  source-ledger.yaml  candidates.yaml  exclusions.yaml
application/gated-facts.yaml
history/
  changes.yaml  approvals.yaml
```

Files under `facts/experience/` must be named `employment.<tail>.yaml` and files under
`facts/projects/` must be named `project.<tail>.yaml`; the basename must equal the entity ID the
file contains, checked both syntactically and against the parsed content. An entity-owned file also
owns its subject's atomic facts — except application-only facts, which live in
`application/gated-facts.yaml`.

`init` writes 30 of the 31 documents. `facts/identity.yaml` is deliberately left out, and validation
says so in as many words:

```console
$ boardwatch profile-bundle validate --bundle <root> --draft baseline
profile-bundle validate: findings
1 error, 0 blocker, 0 warning, 0 information
candidate digest: sha256:d3bce8e8...
error: missing_required_file (facts/identity.yaml): facts/identity.yaml is declared by the grammar but absent; an absent catalog is not an empty one
    -> facts/identity.yaml is yours to author. A new bundle is created without it on purpose: a person needs a display name and review dates that only you have, and a placeholder that survived to promotion would be a fact nobody wrote. Add the file to the draft and validate again.
```

A revision directory also holds `COMPLETE`, the only declared non-source file. It carries the full
bundle digest, is excluded from the logical-tree digest, and must agree with the digest-named
directory, the manifest and `CURRENT`.

---

## 4. Writing YAML the loader accepts

Documents are parsed by a restricted loader built on PyYAML's `SafeLoader`. It refuses duplicate
mapping keys, merge keys, anchors, aliases, and **every** explicitly written tag:

```console
error: restricted_yaml_violation (skills/inventory.yaml): skills/inventory.yaml: YAML anchor 'anchor' is not permitted: an anchor is the first half of an alias
error: restricted_yaml_violation (skills/inventory.yaml): skills/inventory.yaml: explicit YAML tag 'tag:yaml.org,2002:seq' is not permitted: the restricted loader alone decides scalar and collection types
```

For plain (unquoted) scalars the loader keeps SafeLoader's YAML 1.1 implicit resolvers and consults
them as an **ambiguity oracle**: anything the resolver would coerce outside the narrow allowlist is
refused rather than constructed. Measured behaviour of the shipped loader:

| Written as | Result |
|---|---|
| `k: 12` | integer `12` |
| `k: true` / `k: false` | boolean |
| `k:` / `k: null` / `k: ~` | null |
| `k: hello world` | string — a plain string must begin with an ASCII letter or `_` |
| `k: '2026-08-10'` | string `'2026-08-10'` |
| `k: 2026-08-10` | **refused** — "would be read as `timestamp` under YAML 1.1" |
| `k: 1.5` | **refused** — "would be read as `float`" |
| `k: 007` | **refused** — "would be read as `int`" (ambiguous leading zero) |
| `k: yes` / `k: on` | **refused** — "would be read as `bool`" |
| `k: .nan` | **refused** — non-finite numbers are forbidden |
| `k: 1:30` | **refused** — sexagesimal |
| `k: 2026-08` | **refused** — outside the plain-string grammar |
| `k: -dash` | **refused** — outside the plain-string grammar |
| duplicate `k:` twice | **refused** — "duplicate mapping key 'k'" |

So the rule to author by is short: **quote every date, year-month, decimal, ID, punctuation-leading
string, and any string that could be read as a boolean, null, or number.** Leave unquoted only
base-10 integers, `true`/`false`, `null`/`~`, and plain strings that start with a letter or
underscore.

Formatting is not identity. Canonical identity is computed after typed parsing, from a canonical
JSON serialization with sorted mapping keys and NFC-normalized strings, so mapping order and YAML
layout are free. **List order is significant.**

---

## 5. Stable IDs

Every record carries an explicit stable ID whose prefix is part of its type, not a naming
convention:

```text
^(profile|source|source-record|candidate|person|education|employment|project|publication|award
 |certification|affiliation|course|presentation|patent|contact|relation|fact|metric|evidence
 |conflict|ruling|skill|claim|approval|approval-stamp|change)\.[a-z0-9]+(?:[._-][a-z0-9]+)*$
```

Synthetic examples: `project.packet-pantry`, `fact.packet-pantry.status.001`,
`metric.packet-pantry.throughput.001`, `evidence.packet-pantry.benchmark.001`,
`conflict.packet-pantry.launch-date`.

Every reference field is typed to its target kind, so an evidence ID cannot satisfy a metric
reference just because the string exists. **An ID is never regenerated** because a display name
changed. A corrected fact gets a **new** fact ID plus a `supersedes_fact_ids` edge; the old record
stays immutable and its superseded state is derived from the edge rather than by mutating history.

---

## 6. `local-sources.yaml` — the one root-only file

`local-sources.yaml` maps logical source IDs to machine-local absolute roots, so an owner can reopen
an original document. It sits at the bundle **root**, never inside a revision, and it is:

- **excluded from every revision**, so it is not one of the 31 declared documents;
- **excluded from the bundle and evidence digests**;
- **never exported** — `inventory` reports the resolved source *IDs*, never the absolute roots.

`init` writes it as an empty mapping (`{}`). Its shape is a flat source-ID → absolute-path mapping:

```yaml
'source.synthetic-repository': '/srv/example-fixtures/packet-pantry'
```

Proof that it takes no part in identity — a sidecar that will not even parse leaves the selected
revision clean:

```console
$ boardwatch profile-bundle inventory --bundle <root>
profile-bundle inventory: findings
...
error: model_validation_error (local-sources.yaml): local-sources.yaml is not a source-ID to absolute-root mapping: 2 field error(s)

$ boardwatch profile-bundle validate --bundle <root>
profile-bundle validate: clean
0 error, 0 blocker, 0 warning, 0 information
```

A mapping naming a source the selected revision does not declare is reported by `inventory` as an
`information` finding, which never changes an exit code:

```console
information: orphaned_artefact (local-sources.yaml source.not-in-catalog): local-sources.yaml maps source.not-in-catalog, which the source catalog of revision 3 does not declare; the mapping cannot reopen anything
```

The revisioned `policy/sources.yaml` holds only portable source metadata and relative locators.
Nothing machine-local goes in it.

---

## 7. The working loop

```text
init | checkout  →  edit the draft  →  validate  →  approve  →  promote
```

Everything is edited in a **draft** under `drafts/<name>/`. An immutable revision is never edited in
place; a direct edit to one is detected by digest verification and makes that revision invalid rather
than silently changing its identity.

### Starting

```bash
# a bundle with no revision yet: one empty, parentless revision-1 draft
boardwatch profile-bundle init --draft baseline

# a bundle that already selects a revision: copy it into a writable draft
boardwatch profile-bundle checkout --draft work
```

`init` refuses to run twice on a promoted bundle, and says what to run instead:

```console
$ boardwatch profile-bundle init --bundle <root> --draft fresh
profile-bundle init: findings
error: current_already_exists: this bundle already selects a revision; use checkout to create a draft from it
```

`--draft` defaults to `baseline` on both commands. A draft's manifest carries `state: draft`,
`draft_of_revision`, `parent_bundle_digest`, and empty-string sentinels for `bundle_digest`,
`approved_candidate_digest`, `approval_stamp_id` and `change_id`; it has no `revision`, `created_at`
or `created_by`, because those are promotion-derived.

### Editing

Direct editing of the draft's YAML is supported and expected. Two commands exist for the operations
that have to touch more than one document at once — `add-evidence` (§9) and `resolve-conflict`
(§10) — and both end by revalidating the draft they changed, so the exit code answers "did the change
land *and* is the draft still promotable" in one number.

### Validating

```bash
boardwatch profile-bundle validate --draft work
boardwatch profile-bundle validate --draft work --completeness --as-of 2026-08-12
boardwatch profile-bundle validate --json          # the selected revision
```

`validate --draft` checks the full content, the evidence digest, the parent and the candidate-content
digest; it skips only final bundle-digest equality and the promotion-approval requirement, and it
reports pending owner gates as blockers rather than as structural errors.

### Reading

```bash
boardwatch profile-bundle inspect <record-id>   # one record, plus what cites it
boardwatch profile-bundle inventory             # drafts, revisions, stamps, blobs, orphans
boardwatch profile-bundle conflicts             # conflict groups and which are still open
boardwatch profile-bundle migrate               # schema state (no write at schema v1)
```

`inspect` reports the record, its evidence IDs and its conflict IDs, and names the document that owns
it:

```console
$ boardwatch profile-bundle inspect --bundle <root> metric.packet-pantry.throughput.001
profile-bundle inspect: clean
metric.packet-pantry.throughput.001 (metric) in metrics/records.yaml, revision 1
evidence: evidence.packet-pantry.benchmark.001
conflicts: none
{ ...the record as JSON... }
```

---

## 8. Validation tiers, and the exit contract

Four tiers are reported, **always separately and never folded into each other**. This is the same
discipline the eligibility engine applies to `ABSTAIN`: a count that gets absorbed into a neighbour
stops being visible, and an unmeasured thing then reads as a measured one.

| Tier | Meaning | Affects exit code |
|---|---|---|
| `error` | The revision is invalid — structural, referential, evidential, semantic or digest. | yes |
| `blocker` | The revision is valid, but a named record cannot be used downstream. Reported only when completeness is requested. | yes |
| `warning` | Advisory. | no |
| `information` | A report about the bundle root, a run's own arithmetic, or a check that did **not** happen. | no |

The tier comes from the issue code, which is a **closed catalog**: a code cannot be invented at the
call site, and out-of-catalog is a failure rather than a new bucket. `errors.IssueCode` is the
catalog and `errors.tier_of` assigns every member a tier; no exact membership count is quoted here,
because a number in this file cannot be pinned by a test — a test that read this document would void
the rule that lets documentation ship without the full gate — so it could only go stale silently.

The tier is a property of the **operation** as well as the code: the same condition is an error
during promotion and a blocker during read-only completeness (a broken ancestor is the standing
example). Only that case may override a code's declared tier.

Every command prints all four counts:

```console
0 error, 8 blocker, 0 warning, 1 information
```

### The exit codes

Read out of `errors._CATEGORY_EXIT`:

| Exit | Category | When |
|---|---|---|
| `0` | `clean` | The check completed with no violation at a requested tier. |
| `1` | `findings` | The check completed and found errors, blockers, or a typed state refusal. |
| `2` | `usage_error` | A command-line usage error, produced **before** the command executes. |
| `3` | `could_not_complete` | I/O failure, lock contention, internal failure, or an unsupported schema or secret-scan ruleset. |

Exit 3 takes precedence: a run that could not read the bundle has not found one error, it has found
nothing at all, and reporting exit 1 would let a caller treat an unreadable bundle as a bundle with a
small problem.

Measured examples of each:

```console
$ boardwatch profile-bundle validate --bundle <root>                       # clean
EXIT=0
$ boardwatch profile-bundle inspect --bundle <root> fact.nope.001
error: record_not_found (fact.nope.001): fact.nope.001 is not a record in revision 1
EXIT=1
$ boardwatch profile-bundle validate --bundle <root> --as-of 2026-08-12    # no --completeness
Invalid value for --as-of: --as-of dates the completeness checks, so it needs --completeness
EXIT=2
$ boardwatch profile-bundle promote --bundle <root> --draft demo2 --summary "..."
profile-bundle promote: could_not_complete
error: bundle_lock_held: this bundle's career-profile.lock is already held, by another command or by this one holding it twice; nothing was waited for and nothing was changed
EXIT=3
```

An unknown option, a draft name outside the segment grammar, and a malformed `--as-of` all exit 2,
because Typer refuses them before the command body runs.

**This contract is scoped to the `profile-bundle` family.** `scan` and `run` use exit 2 for lock
contention and an eligibility worksheet command uses exit 2 for a missing directory; those are
unchanged and are not a repository-wide contract.

### The JSON contract

Every command in the group accepts `--json` and emits one line: a deterministic document with
sorted keys and no spaces. The one exception is `approve-projection`, which is a live
question-and-answer at a terminal and specifies no JSON schema for that exchange.

```json
{
  "report_schema": 1,
  "command": "validate",
  "outcome": "clean",
  "exit_code": 0,
  "as_of": null,
  "result": {
    "bundle_digest": "sha256:9d380da3...",
    "candidate_digest": "sha256:09d4b637...",
    "counts": {"blocker": 0, "error": 0, "information": 0, "warning": 0},
    "schema_version": 1
  },
  "diagnostics": []
}
```

- `outcome` carries the category **explicitly**, so a caller never has to infer it from `exit_code`.
- `as_of` is the completeness date, and is `null` when the run was not dated.
- Each diagnostic is `{tier, code, path, record_id, message, details}`. `path` is always a **logical**
  path inside the bundle or the name of the option that carried the input — never an absolute path on
  your machine. Neither `message` nor `details` ever contains a contact value, a captured byte, or
  matched secret text.

The generated JSON Schema for the typed models ships as package data and can be read without running
anything:

```python
from importlib import resources
schema = resources.files("boardwatch.profile_bundle.resources") \
    .joinpath("career-profile.schema.json").read_text()
```

A complete synthetic example bundle ships alongside it at
`boardwatch/profile_bundle/examples/comprehensive/`.

---

## 9. Completeness and `--as-of`

Structural, referential, evidence, semantic and digest validity are **pure functions of content**:
wall-clock time cannot turn the same bytes from valid to invalid. Everything time-sensitive lives in
completeness, is off by default, and is dated:

```bash
boardwatch profile-bundle validate --completeness --as-of 2026-08-12
```

`--as-of` requires `--completeness` (exit 2 otherwise) and defaults to the **local** current date —
"today" for an operator is the day they are having, and a UTC default would report a different one
for anybody west of Greenwich after their afternoon. The effective date is echoed in both renderings
(`as-of: 2026-08-12`, and `"as_of"` in JSON), so a completeness result is never quotable without the
date it was taken at.

The same bundle, at two dates, differs only in the dated blockers:

```console
$ ... --completeness --as-of 2026-08-12
0 error, 8 blocker, 0 warning, 1 information

$ ... --completeness --as-of 2030-01-01
0 error, 10 blocker, 0 warning, 1 information
blocker: expired_review (application/gated-facts.yaml fact.example.regions.001): fact.example.regions.001 was last reviewed on 2026-08-10 and application.authorized_regions requires review every 90 days, so it was due on 2026-11-08
```

Completeness also emits one `completeness_counts` **information** finding carrying record counts,
surface coverage, entity status distribution, evidence coverage, metric review coverage, conflict
totals, and the import ledger's denominator/imported/excluded/review-required split with exclusions
broken out by closed reason. It is `information` on purpose: a run whose only finding is a count is a
clean run, and any other tier would make every complete bundle exit 1.

`--deep-history` recomputes every intact ancestor rather than just the envelope. It is the ancestor
audit *inside* completeness, so it also requires `--completeness` (exit 2 otherwise).

---

## 10. Evidence

An evidence record names what it supports, contradicts or contextualizes, and carries the captured
material itself. Six closed classes, each with its own required fields:

| Class | Required record fields |
|---|---|
| `public_record` | portable origin, locator, capture, capture date |
| `private_document` | logical source ID, locator, capture, capture date |
| `repository_artifact` | logical source ID, relative path, full repository commit, capture |
| `measured_result` | capture plus at least one supported metric ID |
| `owner_attestation` | `attested_at`, capture, and at least one supported `owner_confirmed` fact whose stamp carries `confirm_fact` |
| `secondary_summary` | source ID, locator, capture, and `authoritative: false` |

They are a discriminated union, so a field illegal for a class is rejected rather than ignored.

### Captures

`capture` is a closed two-variant union — `inline` (UTF-8 text stored in `evidence/records.yaml`) or
`blob` (bytes stored once under `blobs/sha256/<full-digest>`). Both are hashed; an inline capture has
no separate blob leaf. The captured material must be enough to evaluate the linked fact **without**
resolving its origin.

Hard limits, enforced by validation rather than advised:

- media type is one of `text/plain`, `text/markdown`, `application/json`, `text/csv`;
- each capture is at most 1 MiB;
- one active revision's inline bytes plus its unique referenced blob bytes total at most
  50 MiB (`blobs.MAX_REVISION_EVIDENCE_BYTES`, so the figure has one owner rather than two).

```console
$ ... add-evidence --evidence-file <file> --capture <big-file>
error: capture_too_large (--evidence-file evidence.example.big.001): the capture is 1048577 bytes, over the 1048576-byte per-capture limit; store the excerpt that matters and cite the whole

$ ... add-evidence --evidence-file <file-declaring-image-png> --capture <file>
error: model_validation_error (--evidence-file): --evidence-file is not a valid record: 1 problem(s); first at 'public_record.capture.inline.media_type': Input should be 'text/plain', 'text/markdown', 'application/json' or 'text/csv'
```

For an **inline** capture the record's `text` must be byte-identical to the `--capture` file. The
scan has to run over real bytes; scanning only the text a record *claims* would approve a redaction
nobody performed:

```console
error: evidence_contract_unmet: the inline capture the record quotes is not the capture file's text; an inline record IS its capture, so the two cannot differ
```

For a **blob** capture the record's declared `sha256` must be the capture's actual digest, and
nothing is stored until it is:

```console
error: blob_digest_mismatch (--evidence-file evidence.example.blob-capture.001): the capture hashes to sha256:4cea44e1..., not the sha256:0000... the record declares; nothing was stored
```

The blob store is content-addressed and idempotent — capturing the same bytes twice reports
`"blob_outcome": "reused"` rather than writing a second copy.

### Secrets, personal paths, redaction

Captures are scanned with the manifest's closed, versioned secret-detection ruleset, and the scan
fails closed. Nothing is written on a hit:

```console
error: secret_detected (--evidence-file evidence.example.secret.001): the capture matches secret-scan rule aws-access-key-id at bytes 9-29; redact it and capture again — nothing was written
error: secret_detected (--evidence-file evidence.example.secret.001): the capture matches secret-scan rule generic-secret-assignment at bytes 0-29; redact it and capture again — nothing was written
```

`policy/secret-scan.yaml` records the exact rule IDs and version the revision passed, so an old
revision is always rescanned with the ruleset it recorded and the same content gets the same verdict.
A newer, stronger installed ruleset scans older revisions **additionally**, and reports hits as
blockers requiring recapture — it never retroactively invalidates the revision or rewrites the old
manifest's assertion. A recorded ruleset version this build does not retain is exit 3
(`unsupported_secret_scan_ruleset_version`), never a clean scan.

**As shipped, only one ruleset version exists, so the stronger-ruleset comparison cannot currently
fire.** It is described because the manifest records the version precisely so that it can, and
because a reader who found the code and not this sentence would reasonably wonder whether it had ever
run. It has not.

Absolute home and user-directory paths are rejected in all revision YAML and in every decoded
capture. Note the difference from a secret hit — this one is found by the **revalidation** that
follows the write, so the record does land in the draft and the draft is then reported unpromotable:

```console
$ ... add-evidence --draft recovery --evidence-file <file> --capture <file-with-a-home-path>
profile-bundle add-evidence: findings
added evidence.example.homepath.001 to drafts/recovery (inline capture)
error: absolute_personal_path (evidence/records.yaml evidence.example.homepath.001): evidence.example.homepath.001: the capture contains an absolute home or user-directory path at bytes [13, 35); redact it as `personal_path` or recapture with a portable locator
```

A redaction is `{start, end, reason}` over the UTF-8 bytes of the **stored, post-redaction** capture,
with a closed reason from `credential`, `unrelated_personal`, `demographic`, `health`, `financial`,
`third_party_private`, `personal_path`. Ranges must be valid, non-overlapping, and contain exactly the
ASCII marker `[REDACTED:<reason>]` — so two removed regions mean two markers and two entries. Get the
offsets wrong and the validator says so precisely:

```console
error: redaction_invalid (evidence/records.yaml evidence.example.redacted.001): evidence.example.redacted.001: redaction [31, 61) does not contain exactly the marker [REDACTED:unrelated_personal]
```

Redaction may remove unrelated sensitive content, but it may not remove the portion needed to
evaluate the fact.

### Sufficiency review

`sufficiency_review.state` is a closed two-value catalog: `unreviewed` or `owner_approved`. Unreviewed
evidence is structurally **valid** but a completeness **blocker** for every record depending on it:

```console
blocker: evidence_unreviewed (evidence/records.yaml evidence.packet-pantry.legacy-score.001): evidence.packet-pantry.legacy-score.001 has an unreviewed sufficiency state; 1 dependent record(s) cannot be used until an owner approves it
    dependents: ["metric.packet-pantry.legacy-score.001"]
```

Each `owner_approved` state must match one approval-stamp sub-entry bound to the evidence record's
target-content digest. Because the evidence record embeds no approval ID, that binding is acyclic.
There is no numeric confidence score anywhere in the model: the system records the evidence class and
whether it meets the fact's explicit contract, and leaves adequacy to the owner's review.

### `add-evidence` writes the back-citation for you

```bash
boardwatch profile-bundle add-evidence \
  --draft work \
  --evidence-file <a strict evidence record, as YAML> \
  --capture <the bytes the record describes>
```

Section 12 requires record-to-evidence and evidence-to-record links to agree **exactly**, and only
facts and metrics carry `evidence_ids`. `add_evidence` writes **both directions in one operation**:
it appends to `evidence/records.yaml`, restates the manifest's `evidence_set_digest` over the
evidence set that makes, and cites the new evidence back from every fact and metric the record
names. A capture supporting a fact is therefore clean at exit 0 (D-143):

```console
$ ... add-evidence --draft work --evidence-file <attestation> --capture <capture>
profile-bundle add-evidence: clean
added evidence.example-labs.location.002 to drafts/work (inline capture)
cited back from: facts/experience/employment.example-labs.yaml
owner approval required:
  confirm_fact fact.example-labs.location.001 -> owner_confirmed
EXIT=0

$ boardwatch profile-bundle validate --bundle <root> --draft work
profile-bundle validate: clean
0 error, 0 blocker, 0 warning, 0 information
candidate digest: sha256:0af6d246...
EXIT=0
```

**`cited back from:` names every document the capture rewrote**, and `--json` carries the same list as
`cited_back`. You asked to add one evidence record; this may rewrite up to thirteen other documents,
and the owner gates below do not cover them — a fact that is not `owner_confirmed` is rewritten
without incurring one.

**The `confirm_fact` gate is the thing to notice.** The back-citation changes the fact, and a changed
fact owes an owner confirmation at promotion. That is not a cost auto-linking introduced — the hand
edit this replaces changed the same field of the same fact and owed the same stamp — but you are now
told at the moment you incur it rather than at promotion.

Three boundaries, each measured rather than assumed:

- **All three relationships are linked**, not just `supports`. Validation compares against the union
  of `supports`, `contradicts` and `contextualizes`, so a record that contradicts or contextualizes a
  fact is cited back from it too.
- **Only facts and metrics are touched.** Evidence naming a **skill** or a **claim** is a legitimate
  one-way link under §12 — those kinds carry no `evidence_ids` — so nothing is rewritten and the
  capture is clean:

```console
$ ... add-evidence --draft recovery --evidence-file <supports skill.example-language> --capture <file>
profile-bundle add-evidence: clean
added evidence.example-language.repository.001 to drafts/recovery (inline capture)
owner approval required: none
EXIT=0
```

- **A record the draft does not hold is left alone.** That is a broken reference, validation already
  reports it as one, and citing a record that is not there would not repair it.

The write order is `evidence/records.yaml`, then the fact and metric documents, then `manifest.yaml`
— the pointer target before the pointer. This matters only when a rename fails part-way, which
`partial_edit_applied` names (below): a failure between the first two leaves the evidence recorded
and the citation missing, which is repairable by an ordinary draft edit, rather than a fact citing an
evidence ID no document holds.

Evidence naming any other record kind is reported as a **wrong reference kind**, not doubly as an
asymmetry about the same edit.

---

## 11. Conflicts and rulings

Two facts that compete for one single-valued predicate must sit inside a conflict group. Competing
values **outside** a group are a hard validation error, not a warning.

```console
$ boardwatch profile-bundle conflicts --bundle <root>
profile-bundle conflicts: clean
conflict.packet-pantry.end-date: unresolved (2 candidates, active ruling none)
conflict.packet-pantry.start-date: resolved (2 candidates, active ruling ruling.packet-pantry.start-date.001)
```

An unresolved group blocks only the records that depend on it:

```console
blocker: unresolved_conflict (conflicts/groups.yaml conflict.packet-pantry.end-date): conflict.packet-pantry.end-date is unresolved and blocks 2 candidate fact(s) about project.packet-pantry until the owner rules on it
    blocked_record_ids: ["fact.packet-pantry.end-date.001", "fact.packet-pantry.end-date.002"]
```

`resolve-conflict` appends one owner ruling and updates only the group it rules on. **Nothing is
deleted**: prior rulings stay, every candidate stays, and the group keeps its history. A later ruling
on the same group is how a reopened conflict is settled again.

```bash
boardwatch profile-bundle resolve-conflict --draft work --ruling-file <ruling.yaml>
```

```console
profile-bundle resolve-conflict: clean
appended ruling.packet-pantry.end-date.001; conflict.packet-pantry.end-date is now resolved
owner approval required:
  authorize_conflict_ruling ruling.packet-pantry.end-date.001 -> authorized
```

Ruling decisions are a closed set: `select_candidate`, `replace_all`, `keep_unresolved`,
`not_applicable`. Conflict states are `unresolved`, `resolved`, `reopened`. Note the last line above:
appending a ruling **creates an owner gate**; it does not itself authorise anything.

---

## 12. Candidate digest versus bundle digest

Two digests, computed by the same canonical leaf algorithm over two different views. Confusing them
is the single most common way to misread this system.

| | Candidate content digest | Bundle digest |
|---|---|---|
| What it covers | The **proposed content** an owner is asked to approve | The **promoted revision** as it exists on disk |
| Exists for | A draft, and recomputably for every promoted revision | A revision only (a draft's is the empty-string sentinel) |
| Names | `approvals/sha256-<hex>.yaml`, and the stamp's `candidate_content_digest` | `revisions/sha256-<hex>/`, `COMPLETE`, `CURRENT`, `manifest.bundle_digest` |
| Changes when | Any proposed content changes | Any content changes, **including** the promotion-derived fields |

The candidate view is a precisely defined normalization of the proposed tree. It omits
`history/approvals.yaml`; keeps `history/changes.yaml` only through the direct parent's prefix; sets
`state: draft` and `draft_of_revision` to the parent's revision (or `null` at revision 1); drops the
promotion-derived `revision`, `created_at` and `created_by`; and replaces
`approved_candidate_digest`, `approval_stamp_id`, `change_id` and `bundle_digest` with empty-string
sentinels. It includes every proposed owner-gated state and every other draft document.

That normalization is **invertible**, which is what makes an approval auditable after the fact.
Validating a promoted revision removes exactly the final change record its manifest names, re-derives
the draft view, and recomputes the candidate digest; the result must equal both
`manifest.approved_candidate_digest` and the approval stamp's `candidate_content_digest`. This is
validation-only and never rewrites the revision.

Both are visible in ordinary output:

```console
$ boardwatch profile-bundle validate --bundle <root>
candidate digest: sha256:09d4b637...

$ boardwatch profile-bundle promote --bundle <root> --draft alpha --summary "Rename the example skill"
promoted revision 3
bundle digest: sha256:9d380da3...
authorised by: approval-stamp.000003 binding candidate sha256:09d4b637...
```

When the candidate digest cannot be recomputed — the direct parent is not on disk, say — the run says
so as an `information` finding and **stays clean**, because §21 keeps a revision valid when its
ancestry is unavailable. Naming the comparison that did not happen is what stops an unmeasured
revision from being indistinguishable from a verified one:

```console
profile-bundle validate: clean
0 error, 0 blocker, 0 warning, 1 information
candidate digest: not computed by this run
information: candidate_digest_unverified (manifest.yaml): no candidate digest could be recomputed for this revision, so its approved candidate digest was not compared against its content; this run makes no claim about it
EXIT=0
```

A direct edit to a promoted revision is caught by both digests at once — the bundle digest no longer
matches the manifest, and the candidate view no longer recomputes what the stamp approved:

```console
$ ...edit skills/inventory.yaml inside revisions/sha256-9d380da3.../ ...
$ boardwatch profile-bundle validate --bundle <root>
profile-bundle validate: findings
3 error, 0 blocker, 0 warning, 0 information
error: bundle_digest_mismatch (manifest.yaml): the revision's documents and blobs do not produce the digest its manifest carries
error: candidate_digest_mismatch (history/approvals.yaml approval-stamp.000003): the final approval stamp approved a candidate digest the revision does not recompute
error: candidate_digest_mismatch (manifest.yaml): the revision's inverse candidate view does not recompute the candidate digest its manifest says was approved
```

The candidate check is the one that survives a *thorough* forgery. Somebody who edits a revision and
re-seals it properly — recomputing the bundle digest, renaming the directory, rewriting `COMPLETE` and
`CURRENT` — makes every other digest agree again, because every other digest is recomputed from the new
bytes. Only `approved_candidate_digest` and the approval stamp still describe what the owner actually
looked at.

---

## 13. The owner-approval stop

```bash
boardwatch profile-bundle approve --draft work
```

`approve` prints the candidate digest and every owner-gated transition in the candidate, then asks for
one exact word:

```console
Approving drafts/baseline.
Candidate content digest: sha256:3faa0ea9...

35 owner-gated transition(s) in this candidate:
  approve_claim claim.example.summary.001 -> approved
  approve_evidence_sufficiency evidence.example.transcript.001 -> owner_approved
  approve_metric_surfaces metric.packet-pantry.latency.001 -> approved
  approve_source_scope source.synthetic-repository -> approved
  authorize_conflict_ruling ruling.packet-pantry.start-date.001 -> authorized
  confirm_contact contact.example.email -> owner_confirmed
  confirm_fact fact.example.name.001 -> owner_confirmed
  ...

Type 'approve' to approve:
```

The eight gated actions are a closed catalog: `confirm_fact`, `confirm_contact`,
`approve_evidence_sufficiency`, `approve_claim`, `approve_metric_surfaces`, `approve_source_scope`,
`approve_source_record_exclusion`, `authorize_conflict_ruling`.

Rules that are not negotiable here:

- **A controlling terminal on both stdin and stdout is required.** There is no `--yes`, no environment
  override, and no piped answer. A detached or redirected process gets
  `approval_requires_controlling_tty` at exit 1. The prompt is written to **stderr**, so `--json`
  still produces a capturable document on stdout.
- **An exact word, not `y`.** A stray keypress cannot file an approval. Anything else is
  `approval_declined`, and nothing is written.
- **An agent must stop here.** An automated caller presents the changed record IDs, the diagnostics,
  the owner-gated transitions and the candidate digest, then asks the owner to run `approve` for that
  exact digest. It must not invoke or answer the prompt on the owner's behalf.
- This is an operator-interaction seam, **not access control**. Any process with write permission can
  construct a stamp file. What makes an approval mean something is that it is bound to one candidate
  digest and is reviewable.

A stamp is filed at `approvals/sha256-<candidate-digest>.yaml`:

```console
profile-bundle approve: clean
approved candidate sha256:3faa0ea9...
stamp: approval-stamp.000001
```

### Stale stamps

The lookup is keyed by **digest**, not by draft name, so the lookup itself is the binding. Edit a
draft after approving it and its candidate digest moves; the old stamp is still on disk, still valid,
and simply does not cover the new content:

```console
$ ...edit drafts/work after approving it...
$ boardwatch profile-bundle promote --bundle <root> --draft work --summary "..."
profile-bundle promote: findings
error: missing_approval_stamp (approvals/sha256-5a541320....yaml): no owner approval is recorded for candidate digest sha256:5a541320...; run profile-bundle approve for this exact digest before promoting
EXIT=1
```

`stale_approval_stamp` is the *other* case, and it is narrower: a stamp file whose recorded
`candidate_content_digest` disagrees with the digest its filename claims. That can only happen to a
file that was copied or hand-edited, and it is refused rather than trusted, because trusting the
filename would let one approval authorise different content.

A rebase (§15) has the same effect by the same mechanism: it does not delete or modify any stamp; the
new candidate digest simply makes every old stamp stale by mismatch.

---

## 14. Promotion

```bash
boardwatch profile-bundle promote --draft work --summary "What this revision changes" [--actor owner]
```

`--summary` is required and goes into the change ledger. `--actor` is one of `owner`, `agent`,
`importer` and defaults to `owner`; `authorized_by` is **derived from the matching approval stamp**
rather than trusted from YAML.

Promotion is crash-consistent, under a non-blocking exclusive lock:

1. Acquire the lock non-blocking. Contention is exit 3 with `bundle_lock_held` — no wait, no mutation.
2. Re-check that the draft's parent is still `CURRENT`. A mismatch is `stale_draft_parent` at exit 1,
   and the draft is left exactly as it was.
3. Derive the next revision as `CURRENT.revision + 1`.
4. Validate the parent's manifest envelope, source documents, schema, canonical document digests and
   its three ledgers as exact canonical prefixes of the draft's; validate the draft; and check the
   owner-approval stamp against the candidate digest.
5. Write the next revision to a same-filesystem temporary directory.
6. Re-read and validate that directory **from disk**, then write `COMPLETE` last.
7. Rename it to `revisions/sha256-<full-bundle-digest>/`.
8. Write a temporary `CURRENT`, flush, close, and replace `CURRENT` atomically.
9. Release the lock.

An interruption before step 8 leaves `CURRENT` unchanged. If step 7's target already exists from a
torn earlier attempt, it is re-read and required to be an identical logical tree with a matching
`COMPLETE` and manifest digest; on an exact match this attempt's temporary directory is discarded and
the existing one is used. Any mismatch is exit 3 with `promotion_target_conflict`, and `CURRENT` and
both directories are left alone.

The promoted revision reports which stamp authorised it, read back from the tree rather than from
memory:

```console
profile-bundle promote: clean
promoted revision 1
bundle digest: sha256:7a530e40...
authorised by: approval-stamp.000001 binding candidate sha256:3faa0ea9...
```

Promotion does **not** delete the draft it promoted. Nothing in this family deletes a draft it did not
create.

### History is append-only

Every promotion appends exactly one change record and exactly one approval stamp. The parent's
canonical sequences must be identical **prefixes** of the child's; the change-ledger length must equal
the proposed revision number; and its last entry must match the manifest's revision, `change_id` and
parent digest. `changed_record_ids` is derived from the validated draft diff, never trusted from a
hand-authored list. A changed prefix is a hard failure — `ledger_prefix_changed` — which is what makes
local history verifiable without Git.

All completed revisions and captured blobs are retained. Automatic history pruning, blob garbage
collection and cleanup deletion are **forbidden** in this phase.

---

## 15. Recovery

### An authoring command was interrupted: `partial_edit_applied`

`add-evidence` and `resolve-conflict` each change **several** documents at once — `resolve-conflict`
the two conflict documents, and `add-evidence` the evidence record, the manifest digest that describes
it, and every fact or metric document it cites the new evidence back from (so three or more, not two).
All of them are written to temporary files first and then renamed into place, so anything that can be
reported (a full disk, an unwritable directory) fails before the first rename and leaves the draft
byte-identical.

Two documents at different paths cannot be renamed as one operation, so a narrow window remains. If a
later rename fails, the command says so rather than pretending nothing happened:

```console
$ boardwatch profile-bundle add-evidence --bundle <root> --draft baseline \
    --evidence-file <file> --capture <file>
profile-bundle add-evidence: findings
error: partial_edit_applied (manifest.yaml): manifest.yaml could not be rewritten: Operation not permitted. The change is half applied: evidence/records.yaml was rewritten and this one was not, so the draft is inconsistent until you repair it or discard the draft. Retrying the same command will refuse, because the part that landed is already there
EXIT=1
```

**Exit 1, not 3, on purpose.** Exit 3 means nothing usable happened and the caller may retry; here
something did happen, and the retry would refuse with `duplicate_record_id` against the record that
landed. `details.applied` lists the documents that were written.

The way out is to fix the cause and re-run `validate`, which will report the inconsistency (typically
`evidence_set_digest_mismatch`) — or to discard the draft and check out a fresh one, since a draft is
never the only copy of anything promoted. Promotion recomputes the evidence digest itself, so a draft
in this state is not permanently lost.

If the process is killed outright between the two renames, the un-renamed document is left as a
`.tmp-authoring-*` file inside the draft. That file is an undeclared entry, so every command that
loads the draft refuses it until the file is gone; `inventory` names it and says it is safe to delete.

### The parent moved: `stale_draft_parent` → `rebase-draft`

```console
$ boardwatch profile-bundle promote --bundle <root> --draft baseline --summary "..."
profile-bundle promote: findings
error: stale_draft_parent: drafts/baseline was checked out of no revision but this bundle now selects sha256:777f6c10...; rebase-draft moves it onto the current one and nothing about the draft was changed
EXIT=1
```

`rebase-draft` is the drain. Under the same non-blocking lock it computes the record-level diff from
the draft's old parent, applies it to a new draft based on `CURRENT` **only when** the touched record
IDs are disjoint from the intervening changes, renames the old draft to a deterministic backup, and
atomically installs the rebased draft at the original path.

```console
$ boardwatch profile-bundle rebase-draft --bundle <root> --draft beta
profile-bundle rebase-draft: clean
draft: beta
parent: sha256:9d380da3...

$ ls <root>/drafts
alpha  baseline  beta  beta.pre-rebase-sha256-777f6c10...  work
```

The backup path is `drafts/<name>.pre-rebase-<token>/`, where the token is
`sha256-<64-hex-old-parent-digest>`, or `root` for a parentless revision-1 draft. If that path already
exists it must be byte-identical to the old draft, or rebase returns `draft_backup_conflict` and
performs no write.

The same code has a second trigger: a draft whose name is already a derived backup cannot have a
backup derived from it, because the second suffix would exceed the per-component name limit. Rebasing
a `…pre-rebase-…` directory is therefore a typed refusal naming the way out rather than an exception —
re-parent it under a shorter name first. That path matters because such a directory is often the only
surviving copy of a draft whose rebase went wrong.

An overlap is refused with the exact record IDs, and nothing is written — a rebase never resolves a
record conflict on the owner's behalf:

```console
error: draft_rebase_conflict (affiliation.example-society): 98 record(s) were changed both in drafts/baseline and in revision 2; a rebase never resolves a record conflict for the owner
    record_ids: ["affiliation.example-society", "award.example-prize", ...]
```

In `draft_rebase_conflict`, `record_ids` is empty **exactly** when the conflicting unit has no
addressable records — a field-level or whole-document conflict — and `path`, with `details.field`
where there is one, is then the locator. An empty list is a statement about the unit's shape, never a
missing value.

### A corrupt blob: logical quarantine, then recapture

A corrupted or missing blob is **quarantined logically**. The bytes are never moved and never
deleted. Validation of the selected revision reports it as an error, and the manifest's evidence-set
digest and the candidate comparison fail with it, because the blob is a digest input:

```console
error: blob_digest_mismatch (evidence/records.yaml evidence.packet-pantry.benchmark.001): evidence.packet-pantry.benchmark.001: stored blob does not hash to sha256:21e4321f...; the bytes are quarantined in place, not moved or deleted
    actual_digest: 3dbb3963...
    expected_digest: 21e4321f...
error: evidence_set_digest_mismatch (manifest.yaml): the manifest's evidence_set_digest is not the one its evidence records and blobs produce
error: candidate_digest_mismatch (manifest.yaml): the revision's inverse candidate view does not recompute the candidate digest its manifest says was approved
```

Two ways out, in order of preference:

1. **Restore the exact digest** from an independently verified encrypted backup. Copying the correct
   bytes back returns the revision to `clean` with no new revision required — the digest is the
   identity, so restoring the bytes restores the revision.
2. **Recapture into a new blob.** If no valid backup exists the evidence is lost, and history is not
   rewritten to pretend otherwise. `checkout` will copy the still-parseable YAML of a revision with a
   broken blob into a **recovery draft**, and reports the quarantine as a blocker while doing it:

```console
$ boardwatch profile-bundle checkout --bundle <root> --draft recovery
profile-bundle checkout: findings
draft: recovery
parent: sha256:9d380da3...
blocker: corrupt_blob_quarantine (evidence/records.yaml): blob sha256:21e4321f... is quarantined (digest_mismatch); the draft was created so the evidence can be recaptured, and nothing was moved or deleted
    blob: 21e4321f...
    reason: digest_mismatch
EXIT=1
```

Recapture the material with `add-evidence` (which writes a **new** blob under its own digest), promote
the replacement draft, and the new revision is usable. Promotion validates the replacement fully and
treats the broken predecessor only as a stored-digest ancestor link — the one recovery exception that
skips a parent's blob-integrity and completeness checks. Document corruption, manifest/directory
disagreement, an unsupported parent schema, or a changed ledger prefix still block promotion.

### Missing ancestors

A missing or unreadable ancestor is a completeness **blocker**, not a structural error. The selected
revision stays valid:

```console
blocker: unverifiable_ancestor: ancestor sha256:7a530e40... could not be verified: sha256-7a530e40... is not on disk
    details: {"ancestor_bundle_digest": "sha256:7a530e40...", "reason": "absent"}
```

Ancestor links are traversed through stored manifest digests, verifying that each child's
`parent_bundle_digest` equals the stored `bundle_digest` of the digest-named parent. Ancestors are not
reparsed or re-hashed unless `--deep-history` is requested.

### Orphans: reported, never adopted, never deleted

`inventory` is the census. It reports drafts, complete revisions, incomplete temporary directories,
complete-but-unselected digest directories, approval stamps, referenced and unreferenced blobs, and
undeclared root entries.

```console
$ boardwatch profile-bundle inventory --bundle <root>
profile-bundle inventory: clean
selected revision: 3 sha256:9d380da3...
drafts: alpha, baseline, beta, beta.pre-rebase-sha256-777f6c10..., recovery, work
revisions: 3 complete, 0 incomplete
approval stamps: 3
blobs: 1 referenced, 1 unreferenced
information: orphaned_artefact (notes.txt): notes.txt: the bundle root's member list is closed
```

Everything here is **inventory-only**:

- Orphan findings are `information`, so they never change an exit code.
- Nothing is deleted. No Gate A/B command deletes revisions, blobs, evidence, conflicts, rulings,
  drafts, or unselected digest directories. The single exception is a staging directory the running
  command created itself, within the same operation, and has proved byte-identical to what it keeps.
- An unselected complete revision does **not** block a later promotion, because digest names do not
  reserve a revision-number slot. `inventory` never adopts one; `promote` may reuse only the exact
  complete digest target it independently recomputed from the current draft.
- `bundle_root` is deliberately absent from the JSON: it is an absolute path on your machine and you
  supplied it. `local-sources.yaml`'s values are absent for the same reason; the resolved source IDs
  are reported instead.
- `null` is not zero. When the evidence set could not be read, `referenced_blobs` and
  `unreferenced_blobs` are `null` and the human line says `blobs: not measured (the evidence set could
  not be read)`, rather than reporting a count nobody took.

---

## 16. Imports

`import` enumerates one owner-approved source into a draft's `imports/source-ledger.yaml`:

```bash
# the source's bytes, named explicitly
boardwatch profile-bundle import --draft work --source source.my-resume --from ~/resume.yaml

# or resolved through local-sources.yaml, beneath the root it maps the source to
boardwatch profile-bundle import --draft work --source source.my-resume
```

**It writes the ledger and nothing else.** `imports/candidates.yaml` and `imports/exclusions.yaml`
stay owner-authored, and validation enforces the arithmetic over all three. That split is what keeps
the command from dispositioning a record on your behalf: `build_source_ledger` derives every
disposition from the candidates and exclusions already in the draft, so a record you excluded stays
excluded across a re-import, and a record nothing else accounts for is `review_required`.

Two consequences worth knowing before the first run:

- **A first import of a real source reports every record as `review_required`, and that is correct.**
  Dispositioning them is the Gate B work, not a defect.
- **The undispositioned count is a completeness finding, so it does not affect the exit code.** The
  revalidation every authoring command ends with does not run the completeness tier; the count is in
  the command's own result, and `validate --completeness` is what reports them one by one.
- **But your first `import` on a fresh bundle still exits 1, for an unrelated reason.** Measured
  2026-08-14 against a real `resume.yaml`: 81 records, all `review_required`, and **exactly one**
  finding — `error: missing_required_file (facts/identity.yaml)`. `init` creates a bundle without
  that file on purpose (§7), the grammar requires it, and every authoring command revalidates the
  structural tier. So exit 1 on a first import is expected and is **not** about your records. Author
  `facts/identity.yaml` and it clears. An earlier version of this bullet said `import` "exits 0",
  which was true of the completeness tier and false of the command.

The scope is read from the ledger, never widened here. A source already enumerated keeps exactly the
scope it carries; a first import may only derive `complete_file`, because a `selected_sections`
source's locators are the owner's decision about what may be read (§18, below).

Four closed v1 source adapters, each pinned to a scope:

| Source kind | Adapter | Scope |
|---|---|---|
| `boardwatch_resume` | `boardwatch-resume-v1` | `complete_file` |
| `markdown_document` | `markdown-blocks-v1` | `complete_file` |
| `structured_objects` | `structured-objects-v1` | `complete_file` |
| `repository_markdown` | `markdown-blocks-v1` | `selected_sections` |

Every enumerated source record gets a deterministic locator and a derived ID. Locator segments are
percent-encoded, and three reserved spellings are **escaped rather than refused**, so no real heading
becomes unenumerable:

| Segment | Encoded as |
|---|---|
| `_root` | `%5Froot` |
| `.` | `%2E` |
| `..` | `%2E.` |
| `Alpha Beta` | `Alpha%20Beta` |
| `Alpha%20Beta` | `Alpha%2520Beta` |

`_root` itself is the one path that is not a heading path: it holds the blocks before the first
heading.

Every source record carries one of three dispositions — `imported`, `excluded`, `review_required` —
and an exclusion carries one of seven closed reasons: `duplicate`, `administrative_noise`,
`non_professional`, `prohibited_sensitive`, `superseded_source`, `no_candidate_assertion`,
`owner_excluded`. Completeness reports the denominator and every bucket, and refuses to leave a record
unaccounted for:

```console
blocker: import_record_undispositioned (imports/source-ledger.yaml source-record.5e052137...): source-record.5e052137... awaits review; Gate B requires zero undispositioned source records
    locator: _root/paragraph-1
blocker: import_unexplained_record (policy/sources.yaml source.synthetic-private-record): source.synthetic-private-record is an approved source that imports/source-ledger.yaml never enumerates

information: completeness_counts: ...
    source_ledger: {"candidates": 2, "denominator": 4, "excluded": 1, "imported": 2, "review_required": 1}
    exclusions_by_reason: {"administrative_noise": 1, "duplicate": 0, ...}
```

Imports are idempotent by construction: a candidate ID is derived from the canonical JSON of
`["candidate", source_record_id, predicate, canonicalized_typed_value]`, so re-importing unchanged
source material produces the same IDs and no new candidates. A changed source produces a **new
occurrence** for each stable record or value, and a **new candidate only when the canonical typed
value changes**. Nothing already canonical is mutated. Widening an approved source's scope needs a new
owner approval, because the scope is a property of the ledger rather than of the enumerator.

---

## 17. Schema migration

Schema evolution is append-only. **Schema v1 is the bootstrap release and supports exactly `{1}`.**
There is no invented v0 shape and no `0 → 1` migration.

```console
$ boardwatch profile-bundle migrate --bundle <root> --json
{"as_of":null,"command":"migrate","diagnostics":[],"exit_code":0,"outcome":"clean","report_schema":1,"result":{"schema_version":1,"status":"already_current"}}
```

On a v1 bundle `migrate` returns `already_current` and **performs no write**.

A bundle declaring a version this build does not support is exit 3, never a misreported unknown enum:

```console
$ boardwatch profile-bundle validate --bundle <root> --draft schema2
profile-bundle validate: could_not_complete
1 error, 0 blocker, 0 warning, 0 information
error: unsupported_schema_version: bundle schema version 2 is not supported (supported: [1])
EXIT=3
```

What bumps what:

- Any record-shape change, or any addition to a **code-defined** closed enum — entity kinds,
  verification states, evidence classes, claim states, ruling decisions — bumps `schema_version`.
- Adding data to a **revision-owned** catalog (`policy/predicates.yaml`, `units.yaml`, `relations.yaml`,
  `sources.yaml`, `skill-categories.yaml`, `assertion-tags.yaml`) changes that catalog's version and
  the bundle digest, but does **not** bump the schema unless the catalog entry's shape changes.

From v2 onward, readers support the current version and the immediately preceding one; every bump's
design must ship the exact previous-version fixture and its forward migration, and `migrate` creates a
new revision with a change record such as `schema_migration: "1 -> 2"`. Existing revisions are never
rewritten.

---

## 18. The contract for an automated author

An agent updating this bundle follows exactly this, and stops where it says stop:

1. Read the active manifest and this guide.
2. Inspect the affected entity, facts, evidence and conflicts.
3. Check out, or reuse, an explicit draft.
4. Make the smallest relevant change.
5. Add evidence and provenance **in the same draft**. `add-evidence` writes the back-citation the
   fact or metric owes as part of the same operation (§10), so this is one step, not two.
6. Run complete validation.
7. Present the changed record IDs, the eligibility changes, the diagnostics, the owner-gated
   transitions, and the candidate digest.
8. **Stop.** Ask the owner to run `profile-bundle approve` for that exact digest. Do not invoke the
   approval prompt and do not answer it.
9. Promote only with the matching approval stamp.

---

## 19. Command reference

Every command accepts `--bundle PATH`, and every one but `approve-projection` accepts `--json`.

| Command | Options | Writes |
|---|---|---|
| `init` | `--draft NAME` (default `baseline`) | the root skeleton and one parentless revision-1 draft |
| `checkout` | `--draft NAME` (default `baseline`) | one draft copied from the selected revision |
| `rebase-draft` | `--draft NAME` (required) | the rebased draft plus a deterministic backup |
| `validate` | `--draft NAME`, `--completeness`, `--as-of YYYY-MM-DD`, `--deep-history` | nothing |
| `inspect` | `RECORD_ID` (argument) | nothing |
| `inventory` | — | nothing |
| `conflicts` | — | nothing |
| `migrate` | — | nothing at schema v1 |
| `import` | `--draft`, `--source` (both required), `--from PATH` | `imports/source-ledger.yaml`, and nothing else |
| `add-evidence` | `--draft`, `--evidence-file`, `--capture` (all required) | `evidence/records.yaml`, each fact/metric document it cites back from, the manifest, and possibly one blob |
| `resolve-conflict` | `--draft`, `--ruling-file` (both required) | `conflicts/rulings.yaml` and the one ruled group |
| `approve` | `--draft NAME` (required) | one approval stamp under `approvals/` |
| `promote` | `--draft`, `--summary` (required), `--actor` | one immutable revision, and `CURRENT` |

`validate`, `inspect`, `inventory`, `conflicts` and `migrate` (at v1) perform **no writes at all**.

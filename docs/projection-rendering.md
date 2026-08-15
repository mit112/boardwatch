# Projecting a bundle into a résumé

Once the [career-profile bundle](profile-bundle-authoring.md) holds your facts, **projection** turns
a promoted revision into a rendered résumé. This document is the projection contract: the two files
you author, what every field means, and the commands that carry a bundle to a PDF.

Every example here is synthetic. Projection reads the bundle and writes a résumé document; it submits
nothing, fills no form, and drives no browser.

---

## 1. The two files you author

Projection is deliberately split from the bundle: *which* entries appear and *in what order* is an
editorial decision, and the bundle schema does not encode editorial decisions. Those choices live in
two files under your config directory, outside the bundle:

- **`{config_dir}/projection.yaml`** — the editorial declaration (below).
- **A shell document** (named by `shell_source`) — the header and education lines. The LaTeX renderer
  never reads `Resume.header` or `Resume.education`, so the bundle is deliberately *not* authoritative
  for your name, contacts, or education; the shell is.

## 2. `projection.yaml`

```yaml
projection_version: 1
shell_source: master_resume.yaml     # relative -> resolved against {config_dir}
open_range_label: Present            # the word for an open date range (end: null); no default

# Optional. OMIT this block to synthesize groups from the bundle's own
# policy/skill-categories.yaml, so the taxonomy lives in one versioned place.
skill_groups:
  - label: Languages
    skills: [skill.example-language]   # bundle skill ids, not display text

entries:
  - entity_id: employment.example-labs
    kind: experience                   # closed catalog: experience | project
    pinned: true                       # pinned entries always render; unpinned are JD-scored candidates
    heading: '{@display_name}'         # templates resolve against the entity + its résumé-citable facts
    title: '{employment.title}'
    dates: '{employment.date_range}'
    # Bullets come from claims, from bullet_predicates, or both:
    claims: [claim.example-labs.ownership.001]   # approved, résumé-surfaced ClaimRecords
    bullet_predicates: [employment.accomplishment]  # predicate ids whose facts render as bullets

no_match_fallback: [project.example-project]   # unpinned ids to fall back to when no candidate matches
extracurricular: []
```

**Fields**

- `skill_groups` — optional. Present: you control grouping, order, and inclusion, naming bundle skill
  ids under labels you choose. Omitted: the pool derives one group per skill category that has a
  résumé-surfaced skill, labelled by the category's `display_name`, in the catalog's own order.
- `entries[].heading/title/subtitle/dates/location` — templates. `{predicate}` resolves to the
  entity's one résumé-citable fact of that predicate; `{@display_name}` / `{@status}` read entity
  fields. An unresolved placeholder is fatal — projection never prints a half-built line.
- `entries[].claims` — `ClaimRecord` ids. Each must be `approved`, résumé-surfaced, and about this
  entry's entity; its text is copied verbatim.
- `entries[].bullet_predicates` — predicate ids whose résumé-citable facts render directly as bullets,
  in predicate-declaration then index order. This is how accomplishment/contribution facts reach the
  page without a `ClaimRecord`. A predicate that resolves to no fact is refused (not a silent gap); a
  value that is not a résumé line (a skill reference, a list) is refused too.
- `entries[].kind` — `experience` or `project`, declared not derived: it decides the page section, and
  an out-of-catalog value would silently drop the entry, so it is a closed catalog.

## 3. From declaration to PDF

```
# 1. Approve the projection on a controlling terminal. This is a consent gate: it shows the exact
#    resolved text and records your approval, bound to the bundle revision you reviewed. There is no
#    --yes and no machine mode — a piped stdin does not satisfy it.
boardwatch profile-bundle approve-projection

# 2a. JD-blind master résumé document (no posting, no scorer, no database):
boardwatch profile-bundle project

# 2b. Or a posting-aware résumé — Stage 1 then Stage 2 selection against one posting's JD:
boardwatch resume project --posting <id> --scorer <name> --out <dir>

# 3. Render a résumé document to PDF (requires tectonic on PATH):
boardwatch tailor run <id> --resume <path>
```

`approve-projection` binds the approval to the bundle digest it was made against. If the bundle moves
(a new revision), projection refuses the stale approval rather than emit résumé text you never
reviewed — re-approve after reviewing.

`--scorer` defaults to `mean_per_bullet`, adopted from the owner-labeled selection matrix (D-198): it
had the highest rank agreement with the matrix, though the margin over the alternatives is thin and all
four scorers agree only weakly with a hand ranking. The pick stays overridable — pass another registered
scorer (`total_distinct`, `coverage_then_density`, `mean_top_k`) to override it.

## 4. Multi-tenancy

Nothing here is specific to any one person or field. The mechanism — declaration, shell, skill
categories, predicates — is generic; what makes it *your* résumé is your own bundle, projection, and
shell layered on top. A résumé with no skills omits the Skills section; an entry with no bullets
renders its heading alone; a category with no résumé-surfaced skill is dropped — each an empty-section
guard, so a field whose résumé looks nothing like a software résumé still renders cleanly.

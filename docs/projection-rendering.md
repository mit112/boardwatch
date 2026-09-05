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
  for your name, contacts, or education; the shell is. Because the shell IS authoritative for them, it
  is printed on the approval screen and bound into the approval — editing it asks you to approve again.

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
    dates: '{employment.date_range}'   # ONE fact of type date_range -> "Oct 2025 – Present"
    # Bullets come from claims, from bullet_predicates, or both:
    claims: [claim.example-labs.ownership.001]   # approved, résumé-surfaced ClaimRecords
    bullet_predicates: [employment.accomplishment]  # predicate ids whose facts render as bullets

  - entity_id: project.example-project
    kind: project
    pinned: false
    heading: '{@display_name}'
    dates:                             # TWO facts: the shape projects and education use
      start: project.start_date
      end: project.end_date            # omit `end` entirely to declare the range OPEN

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
- `entries[].dates` — either a template string (above), **or** a two-fact range: `start:` and an
  optional `end:`, each naming a predicate. Both shapes exist because the bundle holds dates two
  ways: employment carries one `date_range` fact, while projects and education carry a
  `start_date`/`end_date` **pair** of `year_month` facts. Declaring the range — rather than writing
  `'{project.start_date} – {project.end_date}'` — keeps the separator and the open-range word in
  one place, and is the only way to express an ongoing project at all.
  **Omitting `end` declares the range open** and renders `open_range_label`. Naming an `end` whose
  fact is missing stays fatal: an absent fact is not you saying "still going", and printing
  "Present" over work that ended would put a false claim on a live application.

**Dates render at month precision**, in one convention set by the projection, not by the bundle and
not by your locale: `Oct 2025`, `Feb 2025 – Jan 2026`, `Oct 2025 – Present`. Only the word for an
open range is yours (`open_range_label`, no default). Fact-grounding dates this way means editing a
date in the bundle changes the page; hand-typed date literals still work, but nothing keeps them
honest.
- `entries[].claims` — `ClaimRecord` ids. Each must be `approved`, résumé-surfaced, and about this
  entry's entity; its text is copied verbatim.
- `entries[].bullet_predicates` — predicate ids whose résumé-citable facts render directly as bullets,
  in predicate-declaration then index order. This is how accomplishment/contribution facts reach the
  page without a `ClaimRecord`. A predicate that resolves to no fact is refused (not a silent gap); a
  value that is not a résumé line (a skill reference, a list) is refused too.
- `entries[].bulletless` — set it to `true` to declare that the entry renders with **no bullets**: role,
  organisation and dates only. A bulletless entry must name no bullet source at all — declaring it
  alongside `claims` or `bullet_predicates` is a contradiction and is refused. This is the *only* legal
  route to an entry with no bullets: an entry that merely resolves to zero bullets is still refused at
  the render gate, because an absence on its own cannot say whether it was meant. Useful when a role
  belongs on the page (it closes a gap in your timeline) but nothing has shipped under it yet.
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

`approve-projection` binds the approval to the exact résumé TEXT it printed — every entry field,
every bullet, the resolved skills section, and the shell's header and education — not to the bundle
revision it was read against (D-167). Any edit that changes one rendered character stales the
approval, and projection then refuses rather than emit text you never reviewed; an edit the
projection does not render (a fact it never cites, an unrelated revision promotion) does not. The
bundle revision is still recorded on the stamp as provenance. Re-approve after reviewing.

`--scorer` defaults to `mean_per_bullet`, adopted from the owner-labeled selection matrix (D-198): it
had the highest rank agreement with the matrix, though the margin over the alternatives is thin and all
four scorers agree only weakly with a hand ranking. The pick stays overridable — pass another registered
scorer (`total_distinct`, `coverage_then_density`, `mean_top_k`) to override it.

## 4. Multi-tenancy

Nothing here is specific to any one person or field. The mechanism — declaration, shell, skill
categories, predicates — is generic; what makes it *your* résumé is your own bundle, projection, and
shell layered on top. A résumé with no skills omits the Skills section; an entry that declares
`bulletless` renders its heading alone; a category with no résumé-surfaced skill is dropped — each an
empty-section guard, so a field whose résumé looks nothing like a software résumé still renders cleanly.

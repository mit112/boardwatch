# Registry catalog

`src/boardwatch/registry/companies.yaml` is a bundled YAML catalog of public
company job boards supported by boardwatch. It ships **inside the wheel** so the
tool can operate without network bootstrapping.

## Catalog schema

Every entry carries exactly four fields (`name`, `provider`, `slug`, `tags`);
no health data lives in the YAML — `last_health` / `last_ok_at` are written
exclusively by `doctor` to the user's local DB (§2.2, D27).

```yaml
companies:
  - name: Example Corp
    provider: greenhouse       # one of: greenhouse, lever, ashby
    slug: example              # the board's identifier on the provider's API
    tags: [starter]            # reserved: "starter" marks the starter set
```

> **`extra="forbid"` is enforced at load time** — any undefined field (e.g. a
> stray `url` or `notes` key) causes a `CatalogError` naming the offending
> entry.

## Starter-set selection rule

Roughly 15 of the 35+ catalog entries are tagged `starter`. This subset must
satisfy **four cumulative criteria** (from Issue #19):

1. **Stability** — the board was live-verified OK in **two attended checks ≥ 7
   days apart** (dates recorded per-entry in the M4 PR body, not in the YAML).
2. **Workload budget** — the entire starter set's cold scan → extract → rank
   completes in **≤ 480 s on the slowest CI OS** (≥ 20 % headroom under 600 s),
   validated by the Task 25 gate.
3. **Provider diversity** — every provider has ≥ 3 entries in the starter set.
4. **Recognizability** — explicit sign-off from the project owner (Mit) that
   the set provides a useful breadth-vs-cost trade-off per the §2.1 framing.
   US-company skew is acknowledged as an inherent limitation of an
   English-language, US-based maintainer's reach; the `companies add <url>`
   command offsets it by letting any user add their own boards.

Per-board posting counts are recorded as evidence but are **not** a selection
gate — a small board that is stable, recognisable, and budget-compliant is
valid.

## Contribution

The catalog is maintained via PR (same as code). To suggest an addition or
correction:

1. **Check** the board is publicly reachable (HTTP 200, valid JSON/XML per the
   provider's API).
2. **Add** a `name` / `provider` / `slug` entry to `companies.yaml`.
3. **Run** `make check` to confirm the YAML loads and validates.
4. **Open a PR** with the rationale — stable board URL, provider, and any note
   on recognisability.

See [CONTRIBUTING.md](../../../CONTRIBUTING.md) for the general contribution
workflow.

## Maintenance loop

A scheduled GitHub Actions workflow (`registry-health.yml`) runs every Monday
at 07:00 UTC and probes every catalog entry with politeness defaults.  The
run produces a per-entry Markdown summary table.  Any entry that returns
**dead**, **error**, or **unreachable** fails the workflow — drift is visible
in the Actions log.

DEAD entries trigger a removal PR per the §6.5 triage rule (a single board
that has been dead across two consecutive weekly runs is removed from the
catalog).

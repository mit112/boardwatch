# Provider compatibility matrix

The six ATS providers boardwatch reads, at a glance. For the exact public endpoints and auth,
see the [Supported boards table in the README](../README.md#supported-boards); for the
behavioural limits behind the last column, see [provider notes](providers.md).

Registry counts are the boards bundled in `src/boardwatch/registry/companies.yaml`. You can
watch any board a supported provider hosts with `companies add`, whether or not it is in the
registry.

| Provider | Registry boards | In starter set | JD body | `--verify` catches a wrong slug | Honest limit |
|---|---:|---|---|---|---|
| **Greenhouse** | 18 | yes | inline with the listing | yes — a wrong slug returns no board | — |
| **Lever** | 5 | yes | inline with the listing | yes — a wrong slug returns no board | — |
| **Ashby** | 12 | yes | inline with the listing | yes — a wrong slug returns no board | — |
| **Workable** | 1 | no (catalog only) | inline (whole board in one request) | yes — a wrong slug returns no board | 1 catalog entry so `doctor` can probe real connectivity; not curated into the starter set |
| **SmartRecruiters** | 1 | no (catalog only) | one detail fetch per unseen posting, bounded by `detail_fetch_budget`, never refreshed | **no** — an unknown slug returns an *empty* board, not an error, so a typo reads as "unverifiable", not "wrong" | bodies fill in across scans; a description-only edit is not re-fetched (no revision signal) |
| **Workday** | 0 | no | one detail fetch per unseen posting, bounded by `detail_fetch_budget`, never refreshed | reported "not checked" until you watch one with `companies add` | no `ETag`/`Last-Modified`, so every scan re-reads the whole board; large boards report `partial` and fill in over many scans |

## Reading the columns

- **In starter set** — the starter set (~15 boards used by `init` out of the box) is the three
  original providers: Greenhouse, Lever, and Ashby. Its selection bar (stability, a workload
  budget, provider diversity, owner recognizability sign-off) is documented in the
  [registry README](../src/boardwatch/registry/README.md#starter-set-selection-rule). Workable
  and SmartRecruiters ship as catalog-only entries so `doctor` can exercise those providers;
  Workday ships no bundled board.

- **JD body** — four providers (Greenhouse, Lever, Ashby, Workable) return the job description
  inline with the listing, so a scan has the body without a second request. SmartRecruiters and
  Workday require a separate per-posting detail fetch, capped each scan by `detail_fetch_budget`
  (default 50) and never refreshed once fetched.

- **`--verify` catches a wrong slug** — `companies add --verify` probes a board before watching
  it and skips any it cannot confirm. It works by the health vocabulary where a wrong slug reads
  as *dead* (no board). The one exception is **SmartRecruiters**, whose API returns an empty
  board for an unknown company, so `--verify` cannot tell a typo from a genuinely empty board —
  it says so rather than confirming. **Workday** ships no registry board, so `doctor` reports it
  as "not checked" until you watch one.

- **Honest limit** — the behaviour a new operator is most likely to be surprised by. Full detail,
  including the incremental fill both detail-fetch providers exhibit, is in
  [provider notes](providers.md).

## Adding a board or a provider

- A public board on a **supported** provider → a small registry PR. See the
  ["Contributing a board" walkthrough](../CONTRIBUTING.md#contributing-a-board).
- A **new provider** → its identity is a provider class plus one line in `PROVIDER_CLASSES`
  (`src/boardwatch/providers/registry.py`); the file's module docstring is the contract. This is
  a larger change and a good Discussions thread before a PR.

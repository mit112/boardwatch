# Contributing

Dev setup: install [uv](https://docs.astral.sh/uv/), then `uv sync` and
`uv run pre-commit install`. `make check` (generalization + index-check + ruff + mypy --strict + pytest) must
be green before every PR; CI runs the same commands: pull requests run the test suite on ubuntu with
Python 3.11-3.13, plus gitleaks and a dedicated generalization job; pushes to `main` additionally
run that test matrix on macOS and Windows.

## What must never enter this repo

This project is a general-purpose tool. Some of it grew out of a private, single-user
job-search setup, so there is a standing rule about what does not come along.

Never commit:

- **Personal career data.** Resume or CV text, work history, cover letters, EEO or
  work-authorization answers.
- **Personal targeting lists.** A private list of companies, recruiters or contacts.
- **Personal preference defaults.** One person's job titles, locations, salary floor or
  filters, shipped as the default for everybody.
- **Personal identifiers.** Home-directory paths, email addresses, phone numbers,
  profile URLs.

Curated generic content is welcome. The tech taxonomy and the public starter registry are
both good examples. The question that separates them:

> Does this content describe **the world**, or **one user's situation and preferences**?

A list of public company job boards describes the world. A list of the companies you
personally want to work at describes you.

These checks catch identifier shapes, new data files and changed defaults, so those cannot
land unnoticed. They do not and cannot catch personal values written into Python source or
prose; code review is the control there. For a legitimate block, add a reviewed entry to
`tools/generalization/allowlists.py` for the shape and inventory rules, or a reviewed update
to `tools/generalization/snapshots.py` for the pinned defaults. For the fixture rules
(R13/R14/R15), the remedy is `python -m tools.fixture_refresh` — `--check` to see what drifted,
`--record` to re-pin a reviewed fixture README, and `--extend <provider> --days N --reason "…"`
to accept an overdue capture review when you cannot reach the live API. It will not re-record
the corpus row count; that one is a deliberate hand edit. The collection-defaults rule
has no opt-out by design, so the remedy there is to restructure the value. Weakening or
removing a check is a security-sensitive change and will be reviewed as one.

All changes land via PR — `main` is branch-protected. One issue per PR.

The bundled registry catalog (company boards) has its own bar — see
[`src/boardwatch/registry/README.md`](src/boardwatch/registry/README.md).

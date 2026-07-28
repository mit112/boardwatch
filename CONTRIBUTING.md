# Contributing

Dev setup: install [uv](https://docs.astral.sh/uv/), then `uv sync` and
`uv run pre-commit install`. `make check` (generalization + ruff + mypy --strict + pytest) must
be green before every PR; CI runs the same on 3.11–3.13 ×
ubuntu/macos/windows plus gitleaks and a dedicated generalization job.

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

These rules are enforced by `make generalization` and by the `generalization` CI job. If a
check blocks something legitimate, add a reviewed entry to
`tools/generalization/allowlists.py` with a reason, rather than loosening the rule.
Weakening or removing a generalization check is a security-sensitive change and will be
reviewed as one.

All changes land via PR — `main` is branch-protected. One issue per PR.

The bundled registry catalog (company boards) has its own bar — see
[`src/boardwatch/registry/README.md`](src/boardwatch/registry/README.md).

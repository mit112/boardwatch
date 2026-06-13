# Contributing

Dev setup: install [uv](https://docs.astral.sh/uv/), then `uv sync` and
`uv run pre-commit install`. `make check` (ruff + mypy --strict + pytest) must
be green before every PR; CI runs the same commands on 3.11–3.13 ×
ubuntu/macos/windows plus gitleaks.

All changes land via PR — `main` is branch-protected. One issue per PR.

The bundled registry catalog (company boards) has its own bar — see
[`src/boardwatch/registry/README.md`](src/boardwatch/registry/README.md).

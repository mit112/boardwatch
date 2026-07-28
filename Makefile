.PHONY: check lint type test generalization
check: generalization lint type test
lint:
	uv run ruff check .
type:
	uv run mypy --strict src tools
test:
	uv run pytest
generalization:
	uv run python -m tools.generalization

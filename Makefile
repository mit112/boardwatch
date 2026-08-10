.PHONY: check lint type test generalization index-check reindex
check: generalization index-check lint type test
lint:
	uv run ruff check .
type:
	uv run mypy --strict src tools
test:
	uv run pytest
generalization:
	uv run python -m tools.generalization
index-check:
	uv run python -m tools.program_index --check
reindex:
	uv run python -m tools.program_index

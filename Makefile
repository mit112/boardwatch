.PHONY: check lint type test
check: lint type test
lint:
	uv run ruff check .
type:
	uv run mypy --strict src
test:
	uv run pytest

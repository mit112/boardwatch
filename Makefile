.PHONY: check lint type test generalization index-check reindex web
check: generalization index-check lint type test
lint:
	uv run ruff check .
type:
	uv run mypy --strict src tools
test:
	uv run pytest -n auto
generalization:
	uv run python -m tools.generalization
index-check:
	uv run python -m tools.program_index --check
reindex:
	uv run python -m tools.program_index
# Rebuilds the committed React bundle into src/boardwatch/web/static/ and re-records the hash
# of every build input under web/. Run it after touching anything in web/, and commit both.
# Deliberately NOT a prerequisite of `check`: the gate runs on macOS, Linux and Windows with no
# node toolchain, so it verifies the recorded manifest instead of rebuilding
# (tests/unit/test_web_bundle_freshness.py).
web:
	cd web && { [ -d node_modules ] || npm ci; } && npm run build
	uv run python tests/unit/test_web_bundle_freshness.py

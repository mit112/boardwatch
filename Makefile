.PHONY: check lint type test web-test generalization index-check reindex web
check: generalization index-check lint type web-test test
lint:
	uv run ruff check .
type:
	uv run mypy --strict src tools
test:
	uv run pytest -n auto
# The React tree's own suite (vitest + jsdom), and a prerequisite of `check` — unlike `web`.
#
# The distinction is that this REBUILDS NOTHING and compares nothing byte for byte, so none of
# the reasons `web` stays out of the gate apply to it. What does apply is that the viewer's error
# boundaries and its stale-server guards are behaviour `make check` could not see at all until
# this target existed, and a suite the gate does not run is decoration.
#
# It needs node, which the Python gate did not. Deliberately NOT made conditional on node being
# present: a check that skips itself where the toolchain is missing reports green while verifying
# nothing, which is the one failure mode this repository refuses everywhere else.
web-test:
	cd web && { [ -d node_modules ] || npm ci; } && npm test
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

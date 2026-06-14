#!/usr/bin/env bash
set -euo pipefail

# Bounded Ralph loop around `reasonix run` (DeepSeek V4 Flash executor,
# V4 Pro planner — see reasonix.toml). State lives in .agent/ and git;
# each iteration gets fresh context. Run from the boardwatch repo root,
# ON THE MILESTONE BRANCH (never main — branch protection requires PRs).
MAX_ITERS="${MAX_ITERS:-6}"
MAX_STEPS="${MAX_STEPS:-40}"
BUDGET="${BUDGET:-10}"              # configured-cost units from --metrics JSON.
                                    # Reasonix DeepSeek presets report CNY (confirmed
                                    # on a prior run) — re-verify after iteration 1.
ITER_TIMEOUT="${ITER_TIMEOUT:-45m}" # wall-clock cap per iteration
RUN_DIR=".reasonix-runs/$(date +%Y%m%d-%H%M%S)"
mkdir -p "$RUN_DIR"

# Refuse to run on main: the loop commits locally; only Claude pushes, via PR.
branch="$(git rev-parse --abbrev-ref HEAD)"
if [[ "$branch" == "main" ]]; then
  echo "ERROR: on main. Create the milestone branch first: git checkout -b issue-N" >&2
  exit 1
fi

# gtimeout needs GNU coreutils on macOS: brew install coreutils
TIMEOUT_BIN="$(command -v gtimeout || command -v timeout || true)"
if [[ -z "$TIMEOUT_BIN" ]]; then
  echo "WARN: no gtimeout/timeout found — iterations have no wall-clock cap." >&2
fi

for ((i = 1; i <= MAX_ITERS; i++)); do
  log="$RUN_DIR/iteration-$i.log"
  metrics="$RUN_DIR/iteration-$i.json"

  set +e
  ${TIMEOUT_BIN:+"$TIMEOUT_BIN" "$ITER_TIMEOUT"} reasonix run \
    --dir "$PWD" \
    --max-steps "$MAX_STEPS" \
    --metrics "$metrics" \
    "$(cat .agent/LOOP.md)" 2>&1 | tee "$log"
  rc=${PIPESTATUS[0]}
  set -e

  total="$(jq -s '[.[].cost] | add // 0' "$RUN_DIR"/*.json 2>/dev/null || echo 0)"
  printf 'iteration=%s exit=%s total_cost=%s\n' "$i" "$rc" "$total"

  if grep -q '<promise>MILESTONE-COMPLETE</promise>' "$log"; then
    echo "Milestone complete after $i iteration(s). Run the Pro review pass next."
    exit 0
  fi

  if ! awk "BEGIN { exit !($total <= $BUDGET) }"; then
    echo "Stopping: cost budget exceeded ($total > $BUDGET)."
    exit 2
  fi

  sleep 5
done

echo "Stopping: iteration limit reached without MILESTONE-COMPLETE."
exit 3

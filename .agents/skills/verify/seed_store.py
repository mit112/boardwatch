"""Forward the Codex verification entry point to the shared synthetic-store seeder."""

import runpy
from pathlib import Path

runpy.run_path(
    str(Path(__file__).resolve().parents[3] / ".claude/skills/verify/seed_store.py"),
    run_name="__main__",
)

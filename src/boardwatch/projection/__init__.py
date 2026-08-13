"""Bundle-to-résumé projection: the Gate B bridge, as a package outside both walls.

`boardwatch.projection` imports BOTH `boardwatch.profile_bundle` (to read) and `boardwatch.tailor`
(to construct and validate a `Resume`). That is legal precisely because this package is in neither
root set of `tests/profile_bundle/test_profile_bundle_tailor_isolation.py`, whose two assertions
walk OUTWARD from `boardwatch/tailor/**` and `boardwatch/profile_bundle/**`.

Two consequences, both load-bearing:

- This package must stay at `boardwatch/projection/`. Moving it under `boardwatch/tailor/` would
  make it a tailor root and the wall would fail on its first import.
- **No module in the tailor closure may import this package** — 58 modules, including
  `reports/tailor.py`, `core/settings.py` and `cli/context.py`. `cli/app.py` is outside the closure,
  which is why the CLI may register these commands.
"""

from boardwatch.projection.errors import ProjectionError, ProjectionIssue, ProjectionViolation

__all__ = ["ProjectionError", "ProjectionIssue", "ProjectionViolation"]

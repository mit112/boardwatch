"""The validation layers, in the order design §20 runs them.

Each layer is a pure function from a `ValidationContext` to diagnostics. Nothing here writes, and
nothing short-circuits on a finding: the layers accumulate, so one hand-edit that breaks fifty
references reports fifty times and the operator sees the shape of the damage.

The layers run in dependency order because a later one reads what an earlier one guarantees.
Referential validation assumes IDs are unique; running it over a tree with duplicate IDs would
resolve half the references against whichever record happened to be indexed first.
"""

from __future__ import annotations

from boardwatch.profile_bundle.validation.context import (
    BundleParseError,
    ParentSnapshot,
    ValidationContext,
    build_context,
    context_from_documents,
    load_documents,
    parse_error_diagnostics,
    sorted_diagnostics,
)
from boardwatch.profile_bundle.validation.referential import (
    records_blocked_by_unresolved_conflicts,
    validate_referential,
)
from boardwatch.profile_bundle.validation.semantic import (
    semantic_completeness,
    validate_semantic,
)
from boardwatch.profile_bundle.validation.structural import validate_structural

__all__ = [
    "BundleParseError",
    "ParentSnapshot",
    "ValidationContext",
    "build_context",
    "context_from_documents",
    "load_documents",
    "parse_error_diagnostics",
    "records_blocked_by_unresolved_conflicts",
    "semantic_completeness",
    "sorted_diagnostics",
    "validate_referential",
    "validate_semantic",
    "validate_structural",
]

"""`migrate`: schema evolution, which at the bootstrap head has nothing to do (design §7).

## Why this module exists at all when it migrates nothing

Schema v1 supports exactly `{1}`, so every bundle this build can read is already at the head. The
command still has to exist, and it still has to be the thing an operator runs when a bundle refuses
to load — because the answer they need is either "you are current" or the typed
`unsupported_schema_version` that tells them their build is older than their data. Leaving the
command out until v2 would mean the first bump introduced both the migration *and* the command that
reports it, with nothing having ever exercised the reporting path.

## What it must not do

Return `already_current` and write nothing: no draft, no revision, no change record, no touch to
`CURRENT`, no lock file. `read_current_once` and `selected_documents` are pure reads, and this
function adds no write of its own, so "nothing was written" is a property of the call graph rather
than of a cleanup path that could be skipped on an early return.

## Why `already_current` is not computed from a version comparison

`load_documents` puts every revision it returns through `require_supported_schema`, and the
supported set is exactly `{CURRENT_SCHEMA_VERSION}`. A revision that reached the end of this
function is therefore at the head by construction, and an `if found != CURRENT_SCHEMA_VERSION`
branch here could never execute — a check that cannot fire reads as coverage and is deleted
(D-115). That reasoning is void the moment a second version is supported, so it is pinned by a
tripwire: `test_a_previous_schema_fixture_and_a_forward_migration_are_owed_at_v2` fails as soon as
`SUPPORTED_SCHEMA_VERSIONS` grows, and the change that grows it owes the previous-version fixture
and the forward transform §7 requires.

## The extension point, stated rather than built

A future `1 -> 2` transform writes its output as a **draft** and goes through the same owner
approval and promotion path as any other change, ending in a new revision whose change record names
the migration. It never rewrites an existing revision: revisions are immutable and digest-named, so
rewriting one would either invalidate every descendant's `parent_bundle_digest` or, worse, leave a
directory whose contents no longer hash to its own name. There is deliberately no migration
registry and no placeholder transform here — a registry nothing consults is a speculative
abstraction, and a fabricated previous-version fixture would be the only thing exercising a path
that does not exist.

## What forces a bump, and what does not

Adding or changing a **code-defined** closed enum — entity kinds, verification states, evidence
classes, claim states, ruling decisions — or any record-shape change requires a schema bump, and
therefore a migration. Adding a row to a revision-owned catalog (a predicate, unit, relation,
source, skill category, assertion tag) changes only that catalog's own version and the bundle
digest, and needs nothing here. `schema.py` holds the head constants this rule is about.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from boardwatch.profile_bundle.errors import (
    OperationOutcome,
    ProfileBundleError,
    diagnostic,
    outcome_with,
)
from boardwatch.profile_bundle.storage import (
    SelectionError,
    read_current_once,
    selected_documents,
)
from boardwatch.profile_bundle.validation.context import parse_error_diagnostics


@dataclass(frozen=True)
class MigrationResult:
    """The outcome of a migration that had nothing to migrate.

    `status` is a one-member literal rather than a free string: at this head `already_current` is
    the only thing that can be reported, and the day that stops being true the type is what makes
    every caller acknowledge the new state instead of printing it as a surprise.
    """

    status: Literal["already_current"]
    schema_version: int


def migrate_bundle(bundle_root: Path) -> OperationOutcome[MigrationResult]:
    """Report the selected revision's schema state, writing nothing.

    Refuses through the selected revision's own typed failures: no `CURRENT` is a state refusal the
    operator can act on (exit 1), while a revision this build cannot read — including one written
    by a newer schema — is `could_not_complete` (exit 3).
    """
    try:
        selection = read_current_once(bundle_root)
        documents = selected_documents(selection)
    except SelectionError as exc:
        return outcome_with(None, (diagnostic(exc.code, str(exc)),))
    except ProfileBundleError as exc:
        return outcome_with(None, parse_error_diagnostics(exc))

    return OperationOutcome.clean(
        MigrationResult(
            status="already_current", schema_version=documents.manifest.schema_version
        )
    )


__all__ = ["MigrationResult", "migrate_bundle"]

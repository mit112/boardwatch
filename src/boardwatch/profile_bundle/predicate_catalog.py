"""The versioned starter predicate catalog seeded into every fresh bundle (design §5; D-172/D-174).

A fresh bundle with an empty predicate vocabulary can enumerate a source but never disposition a
record: `build_candidate_package` raises on an out-of-catalog predicate (`imports.py`), so with no
predicates every enumerated record stays `review_required` forever — a bundle that "claims a
denominator it can never disposition". So `init` seeds this build's starter catalog, exactly as it
seeds the secret-scan ruleset (`drafts.py`), and the content is written INTO the bundle (not
referenced by id) so a revision's meaning is fixed by its own digest-bound rows, not by whatever the
installed build currently means by a name.

`BUILTIN_PREDICATE_CATALOGS` is the closed set of catalogs this build retains; an unavailable
recorded version raises `UnsupportedPredicateCatalogError` rather than silently supplying an empty
vocabulary, because "this build cannot supply that catalog" and "the catalog is empty" must never
look alike.

The v1 rows are the audited comprehensive-example catalog plus two sanctioned changes (§9 Task 1):
`technology.used` admits `incidental` (a familiarity-level skill is a legitimate career state that
must remain effective and never ground verification, §5.1), and a new `project.name` predicate
carries a project's displayed name (`render/latex.py` shows `title` is that name). `measured`,
`secondary_only` and `multiple_sources` are `VerificationBasis` members no fact-only starter
predicate declares; `NOT_ADMITTED_VERIFICATION_BASES` rosters them with a reason so the §5.2 "no
dead enum member" gate stays honest — a NEW accidental orphan still fails — without forcing
metric/multi-source predicates a résumé starter has no bucket for.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import PurePosixPath
from typing import Final

from boardwatch.profile_bundle.errors import UnsupportedPredicateCatalogError
from boardwatch.profile_bundle.models.base import VerificationBasis

# Re-exported so a caller that only needs the starter catalog needs only this module. The direction
# matters: this module depends on the catalog record shapes, never the reverse.
from boardwatch.profile_bundle.models.policy import PredicateCatalog, PredicateSpec
from boardwatch.profile_bundle.yaml_loader import load_yaml_bytes

__all__ = [
    "BUILTIN_PREDICATE_CATALOGS",
    "CURRENT_CATALOG_VERSION",
    "NOT_ADMITTED_VERIFICATION_BASES",
    "SUPPORTED_CATALOG_VERSIONS",
    "PredicateCatalog",
    "PredicateSpec",
    "builtin_catalog",
    "catalog_matches_builtin",
]

CURRENT_CATALOG_VERSION: Final = 1

_RESOURCE_PACKAGE: Final = "boardwatch.profile_bundle.resources"
_CATALOG_RESOURCE_NAMES: Final[Mapping[int, str]] = {
    1: "predicate-catalog-v1.yaml",
}

#: `VerificationBasis` members that no fact-only starter predicate declares, each with the reason it
#: is intentionally unadmitted rather than an accidental orphan. The §5.2 invariant treats a basis
#: as satisfied when it is admitted by a predicate OR listed here — so this roster is the deliberate
#: escape hatch, and a member that is neither admitted nor rostered fails the gate.
NOT_ADMITTED_VERIFICATION_BASES: Final[Mapping[VerificationBasis, str]] = {
    VerificationBasis.MEASURED: (
        "measured is the basis for a metric record's quantity; the starter catalog carries fact "
        "predicates only, none of whose values are a measured quantity"
    ),
    VerificationBasis.SECONDARY_ONLY: (
        "secondary_only records corroboration by secondary sources; no starter predicate is "
        "established that way"
    ),
    VerificationBasis.MULTIPLE_SOURCES: (
        "multiple_sources records agreement across several independent sources; no starter "
        "predicate is established that way"
    ),
}


def _load_catalog(version: int) -> PredicateCatalog:
    """Parse the packaged catalog resource for `version` through the restricted loader."""
    resource = _CATALOG_RESOURCE_NAMES[version]
    from importlib import resources

    raw = resources.files(_RESOURCE_PACKAGE).joinpath(resource).read_bytes()
    parsed = load_yaml_bytes(raw, logical_path=PurePosixPath(resource))
    catalog = PredicateCatalog.model_validate(parsed)
    if catalog.predicates_version != version:
        raise ValueError(
            f"{resource}: predicates_version {catalog.predicates_version} disagrees with the "
            f"builtin key {version}"
        )
    return catalog


#: The closed set of starter catalogs this build retains. Bound at import over a static resource;
#: `drafts.py` reads it at seed time via `builtin_catalog` so a build retaining a newer head seeds
#: the newer head.
BUILTIN_PREDICATE_CATALOGS: Final[Mapping[int, PredicateCatalog]] = {
    version: _load_catalog(version) for version in _CATALOG_RESOURCE_NAMES
}

SUPPORTED_CATALOG_VERSIONS: Final[frozenset[int]] = frozenset(BUILTIN_PREDICATE_CATALOGS)


def builtin_catalog(version: int) -> PredicateCatalog:
    """The retained starter catalog for `version`.

    Raises `UnsupportedPredicateCatalogError` for anything not in `SUPPORTED_CATALOG_VERSIONS`, so a
    caller can turn an unavailable recorded version into exit 3 rather than supplying an empty
    vocabulary it never actually shipped.
    """
    try:
        return BUILTIN_PREDICATE_CATALOGS[version]
    except KeyError:
        raise UnsupportedPredicateCatalogError(
            version, sorted(SUPPORTED_CATALOG_VERSIONS)
        ) from None


def catalog_matches_builtin(recorded: PredicateCatalog) -> bool:
    """True only when `recorded` is identical to the retained builtin catalog of its version.

    Compared by canonical JSON so authoring-order differences in set-like fields (normalised to a
    sorted tuple by the model) never register as a divergence, while any added, removed, or altered
    predicate does.
    """
    builtin = BUILTIN_PREDICATE_CATALOGS.get(recorded.predicates_version)
    if builtin is None:
        return False
    return recorded.model_dump(mode="json") == builtin.model_dump(mode="json")

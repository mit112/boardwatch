"""The closed, ranked catalog of posting-identity kinds (P6 design §2, §3.1).

`exact_quad` is the ONLY suppressing kind. PROGRAM P6 item 1 restricts suppression to exact
identities and core/identity.py:3 records "cross-ID heuristics may only annotate"; every
other kind here is missing either company_id or content_hash from its key, so none of them
is exact. `cross_host` in particular is computed and stored — the host-class election in
core/dedup.py is written and tested against it — but it does not suppress until it can
dereference an aggregator posting to exact requisition evidence (design §3.1).

`content_hash_only` and `company_title_location` exist so the Gate P6 audit can see
near-misses without them being acted on: the live corpus holds 809 hash-collision groups of
which 727 span a different title or location, so a hash-keyed dedup demonstrably collapses
different jobs.

Bump IDENTITY_ALGORITHM_VERSION whenever any normalizer, key tuple, or host-class table
changes. Readers filter to the current version, so a bump degrades to "no identities yet"
(no suppression, `unique` reports None again) rather than to mixed-algorithm comparisons.
"""

from __future__ import annotations

from dataclasses import dataclass

IDENTITY_ALGORITHM_VERSION = "p6.1"


class UnknownIdentityKind(ValueError):
    """Raised at the computation site for a kind outside the closed catalog."""

    def __init__(self, name: str) -> None:
        super().__init__(f"unknown identity kind: {name!r}")
        self.name = name


@dataclass(frozen=True)
class IdentityKindSpec:
    name: str
    rank: int
    suppresses: bool


IDENTITY_KINDS: tuple[IdentityKindSpec, ...] = (
    # The identity floor. postings enforces UNIQUE(company_id, provider_posting_id), so
    # this can never collide and never suppresses. Stored so every posting has at least
    # one identity row and "why was this not suppressed?" is answerable from one table.
    IdentityKindSpec("exact_provider", 0, False),
    IdentityKindSpec("exact_quad", 1, True),
    # Annotate-only. See the module docstring and design §3.1 before changing this to True.
    IdentityKindSpec("cross_host", 2, False),
    IdentityKindSpec("company_title_location", 3, False),
    IdentityKindSpec("content_hash_only", 4, False),
)

IDENTITY_KIND_NAMES: tuple[str, ...] = tuple(k.name for k in IDENTITY_KINDS)
SUPPRESSING_KINDS: tuple[IdentityKindSpec, ...] = tuple(
    sorted((k for k in IDENTITY_KINDS if k.suppresses), key=lambda k: k.rank)
)
_BY_NAME = {k.name: k for k in IDENTITY_KINDS}


def kind_spec(name: str) -> IdentityKindSpec:
    try:
        return _BY_NAME[name]
    except KeyError:
        raise UnknownIdentityKind(name) from None

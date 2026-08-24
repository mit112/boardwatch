"""The closed, ranked catalog of posting-identity kinds (P6 design §2, §3.1).

TWO kinds suppress, and they suppress in DIFFERENT senses. Read `merges` beside
`suppresses` before changing either.

  - `exact_quad` suppresses AND merges. Its key folds in company_id and the body content
    hash, so two members are the same posting by every stored component; the ranker hides
    the loser and `identities regroup` moves it permanently onto the survivor's job.
  - `company_title_location` suppresses but MUST NOT merge (owner ruling, D-294). Its key
    is company + normalized title + normalized locations, so two members are the same ROLE
    at the same PLACE, which is not the same claim. Because that alone does not establish
    they are the same JOB, `core/dedup.py` additionally requires near-identical job
    descriptions before it suppresses. The ranker hides the loser; nothing is written to
    `postings.job_id`.

The distinction is not decorative. A merge rewrites job anchors and is undone only through
`job_grouping_events`, so a wrong merge on a weaker key is expensive; a wrong suppression is
recoverable through `top --include-duplicates`, which is why it is the level the owner
accepted the risk at. The stated cost, accepted: one company can legitimately run two
DIFFERENT openings under one title in one city, and the second is now hidden.

`cross_host` is computed and stored — the host-class election in core/dedup.py is written
and tested against it — but it does not suppress until it can dereference an aggregator
posting to exact requisition evidence (design §3.1). There is a SECOND reason it may not be
flipped on without more work: it would void the relabel proof in `core/dedup.py::_relabelled`.
Two suppressing kinds make suppression chains reachable, and a walked chain is stamped with
the WEAKEST kind on it. That is only honest while the weaker key's components are a subset of
the stronger one's — `company_title_location` is (company_id, title, locations) against
`exact_quad`'s (company_id, title, locations, content_hash) — because a subset makes "shares a
key of the stamped kind" transitive along the chain. `cross_host` keys on the normalized
company NAME, not `company_id`, so it is a subset of neither and neither is a subset of it: a
`cross_host` link followed by a `company_title_location` link would be stamped
`company_title_location` across two DIFFERENT company_ids, which is the pair sharing no key of
its own stamped kind. Merges stay safe either way (`exact_quad` is the only merging kind, and
a chain is stamped `exact_quad` only if every link is), so what breaks is the audit invariant
the ranker's suppression reasons rest on. `content_hash_only` stays annotate-only
on its own measurement: the live corpus holds 809 hash-collision groups of which 727 span a
different title or location, so a hash-keyed dedup demonstrably collapses different jobs.
That figure is about the HASH key and says nothing about company_title_location, which was
measured separately — 1,101 groups over 33,572 open postings, 1,597 redundant (4.76%). Of
the subset that actually reaches leads, only about a third are true repeats, which is why
the body-similarity floor in `core/dedup.py` is part of the ruling rather than a refinement
of it.

Bump IDENTITY_ALGORITHM_VERSION whenever any normalizer, key tuple, or host-class table
changes. Readers filter to the current version, so a bump degrades to "no identities yet"
(no suppression, `unique` reports None again) rather than to mixed-algorithm comparisons.
"""

from __future__ import annotations

from dataclasses import dataclass

# p6.2: normalize_title now folds "+" and "#" to words, so C++/C#/C stop sharing one title
# component. Any normalizer change requires this bump — see the module docstring. Readers
# filter to the current version, so existing p6.1 rows stop being read: suppression turns
# off and `unique` reports None until `boardwatch identities backfill` runs again. That is
# the designed degradation, not a regression.
IDENTITY_ALGORITHM_VERSION = "p6.2"


class UnknownIdentityKind(ValueError):
    """Raised at the computation site for a kind outside the closed catalog."""

    def __init__(self, name: str) -> None:
        super().__init__(f"unknown identity kind: {name!r}")
        self.name = name


@dataclass(frozen=True)
class IdentityKindSpec:
    name: str
    rank: int
    # The ranker hides the loser of a group. Recoverable: `top --include-duplicates`.
    suppresses: bool
    # `identities regroup` moves the loser permanently onto the survivor's job. Undone only
    # through `job_grouping_events`. Never true without `suppresses`; the reverse is allowed
    # and is the whole point of the pair.
    merges: bool = False


IDENTITY_KINDS: tuple[IdentityKindSpec, ...] = (
    # The identity floor. postings enforces UNIQUE(company_id, provider_posting_id), so
    # this can never collide and never suppresses. Stored so every posting has at least
    # one identity row and "why was this not suppressed?" is answerable from one table.
    IdentityKindSpec("exact_provider", 0, False),
    IdentityKindSpec("exact_quad", 1, True, merges=True),
    # Annotate-only. See the module docstring and design §3.1 before changing this to True.
    IdentityKindSpec("cross_host", 2, False),
    # Suppresses, never merges (D-294). See the module docstring for why the two differ.
    IdentityKindSpec("company_title_location", 3, True),
    IdentityKindSpec("content_hash_only", 4, False),
)

IDENTITY_KIND_NAMES: tuple[str, ...] = tuple(k.name for k in IDENTITY_KINDS)
SUPPRESSING_KINDS: tuple[IdentityKindSpec, ...] = tuple(
    sorted((k for k in IDENTITY_KINDS if k.suppresses), key=lambda k: k.rank)
)
# Kinds whose suppression may be persisted as a job merge. A strict subset of
# SUPPRESSING_KINDS: a kind that cannot suppress can never merge either.
MERGING_KINDS: tuple[IdentityKindSpec, ...] = tuple(
    sorted((k for k in IDENTITY_KINDS if k.merges), key=lambda k: k.rank)
)
MERGING_KIND_NAMES: frozenset[str] = frozenset(k.name for k in MERGING_KINDS)
_BY_NAME = {k.name: k for k in IDENTITY_KINDS}


def kind_spec(name: str) -> IdentityKindSpec:
    try:
        return _BY_NAME[name]
    except KeyError:
        raise UnknownIdentityKind(name) from None

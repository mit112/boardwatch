"""Compute the stored identities for a posting (P6 design §1.2, §2).

Identity is computed and stored, never inferred at read time from raw columns, so that a
stale identity is detectable (§6.3) instead of invisible.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime

from boardwatch.core.normalize import normalize_body, normalize_company, normalize_title

# ASCII unit separator: keeps ("ab","c") and ("a","bc") from hashing alike. It cannot occur
# in a normalized component, all of which are whitespace-collapsed.
_SEP = "\x1f"


@dataclass(frozen=True)
class IdentityInputs:
    posting_id: int
    company_id: int
    company_name: str
    provider_posting_id: str
    title: str
    locations: list[str] | None  # postings.locations_json is a nullable JSON column
    content_hash: str  # NOT NULL in the schema
    body_text: str  # NOT NULL in the schema
    url: str | None  # nullable
    first_seen_at: datetime


@dataclass(frozen=True)
class PostingIdentity:
    kind: str
    identity_key: str


def normalized_locations(locations: list[str] | None) -> str | None:
    """Canonical locations, or None when the posting carries no location evidence.

    Takes the *deserialized* list, because `postings.locations_json` is a SQLAlchemy JSON
    column and a SELECT hands back a list. Do not add a `json.loads` here: `str()` of a
    Python list is not JSON, so the parse would fail on every real row, the `except` would
    swallow it, and dedup would silently stop working. Coercion belongs at the loader
    boundary (identity_queries.load_identity_inputs), once.

    A list's serialization order is not identity, so it is sorted and case-folded.

    Absence returns None rather than "[]" on purpose (design §2.1). An "[]" sentinel makes
    every location-less posting equal to every other one on that component, and the failure
    is undetectable downstream: string-verify re-compares the same two "[]" values and
    passes, and the §6.3 recount recomputes the same "[]" and agrees. Returning None means
    the caller emits no location-bearing identity at all, so no suppression is possible.
    Measured cost on the live corpus: 7 postings of 23,455.
    """
    if not locations:
        return None
    folded = sorted(normalize_body(str(item)) for item in locations)
    if not any(folded):  # present but blank, e.g. ["", "  "]
        return None
    return json.dumps(folded)


def body_evidence(body_text: str) -> str | None:
    """Canonical body, or None when the posting carries no body evidence.

    Mirrors `normalized_locations` — same reason, same consequence. `postings.body_text` is
    NOT NULL, but NOT NULL is not non-empty: a stub posting stores "" or whitespace, and
    `content_hash` folds every one of them to the SHA-256 of the empty string. That hash is
    a component of `exact_quad`, the only suppressing kind, so for a stub the component
    carries no information while looking like a match.

    Returning None means no `exact_quad` is emitted at all, so no suppression is possible.
    An empty body is the absence of evidence, not evidence of sameness — the reasoning
    D-250 used to abstain a zero-evidence verdict rather than clear it.

    Measured on the live corpus when this landed: 13 whitespace-only bodies among 32,229
    open postings, on 2 companies, and 0 colliding (company, title, locations) groups. So
    the collision was latent, not firing. A lane that lands body-less rows in volume is
    what would have fired it.
    """
    return normalize_body(body_text) or None


def _key(*parts: str) -> str:
    return hashlib.sha256(_SEP.join(parts).encode("utf-8")).hexdigest()


def compute_identities(inp: IdentityInputs) -> tuple[PostingIdentity, ...]:
    company = str(inp.company_id)
    title = normalize_title(inp.title)
    locations = normalized_locations(inp.locations)
    body = body_evidence(inp.body_text)
    out = [
        PostingIdentity("exact_provider", _key(company, inp.provider_posting_id)),
        PostingIdentity("content_hash_only", _key(inp.content_hash)),
    ]
    if locations is not None:
        # No location evidence => no location-bearing identity. See normalized_locations.
        if body is not None:
            # No body evidence => no suppressing identity. See body_evidence. The guard
            # reads the body rather than content_hash because the body is what the stored
            # path re-verifies (dedup._verify_quad), so both paths agree on one rule.
            out.append(
                PostingIdentity("exact_quad", _key(company, title, locations, inp.content_hash))
            )
        out.append(PostingIdentity("company_title_location", _key(company, title, locations)))
        out.append(
            PostingIdentity(
                "cross_host", _key(normalize_company(inp.company_name), title, locations)
            )
        )
    return tuple(out)

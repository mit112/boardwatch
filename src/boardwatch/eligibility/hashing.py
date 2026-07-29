"""The ONE trusted boundary that turns snapshots into hashes.

Task 2 lands the canonical form only; task 4 adds the three hashes on top of it. The
canonical form is the shape extract/taxonomy.py:95-103 already uses: sorted keys,
compact separators. Formatting and mapping key order never matter; content always does,
including an explicit null, which must not collide with a missing key.
"""

from __future__ import annotations

import hashlib
import json


def canonical(payload: object) -> str:
    """Sorted-key compact JSON. The single serialisation used for every hash."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def digest(payload: object) -> str:
    """SHA-256 hex of the canonical form."""
    return hashlib.sha256(canonical(payload).encode("utf-8")).hexdigest()

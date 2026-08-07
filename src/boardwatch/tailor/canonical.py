"""P4 item 2: the canonical technology vocabulary consolidated behind one accessor.

Item 1 (`overmatch.py`, D-048) seeded `overmatch_reasons`'s `canonical` parameter with the
same 3-line expression duplicated verbatim in `rewrite/lane.py` and `rewrite/agent_lane.py`.
This module is the single source those two call sites now read from -- a pure derivation of
the two existing versioned data assets (`taxonomy.yaml` skill names, `equivalences.yaml`
approved swap images), not a new data file. `field` is a plain string tag, not a dispatched
selector: there is exactly one legal value today (see the design doc for why a per-field
selector is out of scope until a second field's vocabulary exists).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from boardwatch.extract.taxonomy import Taxonomy
from boardwatch.tailor.equivalences import EquivalenceTable


@dataclass(frozen=True)
class CanonicalVocab:
    field: str
    terms: frozenset[str]
    version: str


def build_canonical_vocab(
    taxonomy: Taxonomy, table: EquivalenceTable, *, field: str = "swe"
) -> CanonicalVocab:
    terms = frozenset(p.name.lower() for p in taxonomy.patterns) | frozenset(
        img.lower() for img in table.images()
    )
    version = hashlib.sha256(f"{taxonomy.version}|{table.version}|{field}".encode()).hexdigest()
    return CanonicalVocab(field=field, terms=terms, version=version)

"""The builtin deterministic extraction mapping, keyed by adapter (design §6.2; D-172/D-174).

The mapping is content defined here and — from the schema v2 bump on — seeded into the bundle as
`policy/extraction-mappings.yaml`, exactly as the predicate catalog and secret-scan ruleset are, so
a revision's extraction behaviour is fixed by its own digest-bound rows rather than by whatever the
installed build currently means by an adapter name.

This slice ships the two **literal-rule** buckets — `header/1` → `person.professional_name` and each
skill item → `technology.used` (O1/O2a/O3a/O4/O5). The **model-routed** metadata and bullet rules
(the `entry_kind_model`, O2b/O3b/O3c, §6.2a) land with the buckets that need them, and until they do
the metadata/bullet/education/`header/2` records simply match no rule. So this mapping is
deliberately **incomplete** — it does not yet name every catalog predicate, which is why §5.2's
package-level reachability invariant (invariant 4) stays owed until the full mapping exists.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from boardwatch.profile_bundle.extraction import ExtractionRule

#: The résumé adapter every `boardwatch_resume` source shares (the enumerator's id family).
RESUME_ADAPTER_ID: Final = "boardwatch-resume-v1"

CURRENT_MAPPING_VERSION: Final = 1

_RESUME_V1_RULES: Final[tuple[ExtractionRule, ...]] = (
    ExtractionRule(
        locator_pattern="header/1",
        predicate="person.professional_name",
        value_from=".",
        value_type="string",
        display_from=".",
    ),
    ExtractionRule(
        locator_pattern="skill-groups/*/*",
        predicate="technology.used",
        value_from="item",
        value_type="skill_ref",
        display_from="item",
    ),
)

#: The closed set of builtin mappings this build retains, keyed by adapter id.
BUILTIN_EXTRACTION_MAPPINGS: Final[Mapping[str, tuple[ExtractionRule, ...]]] = {
    RESUME_ADAPTER_ID: _RESUME_V1_RULES,
}

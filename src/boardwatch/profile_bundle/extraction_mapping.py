"""The builtin deterministic extraction mapping, keyed by adapter (design §6.2/§6.2a; D-172/D-174).

The mapping is content defined here and — from the schema v2 bump on — seeded into the bundle as
`policy/extraction-mappings.yaml`, exactly as the predicate catalog and secret-scan ruleset are, so
a revision's extraction behaviour is fixed by its own digest-bound rows rather than by whatever the
installed build currently means by an adapter name.

It is a **complete** mapping over the résumé buckets (§6.2a-proof): two literal rules (`header/1`,
skill items), two model-routed rules (entry metadata, bullets) resolving through the one
`entry_kind_model`, and two deferrals classifying the records that deliberately match no producing
rule (`header/2` → `no_predicate_exists`, education → `free_text_deferred`, the agent lane §8).
Every predicate it names is verified against the seeded catalog by
`validate_mapping_against_catalog`.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from boardwatch.profile_bundle.extraction import (
    Deferral,
    EntryKindSpec,
    ExtractionMapping,
    ExtractionRule,
    ModelRoutedRule,
    Slot,
)

#: The résumé adapter every `boardwatch_resume` source shares (the enumerator's id family).
RESUME_ADAPTER_ID: Final = "boardwatch-resume-v1"

CURRENT_MAPPING_VERSION: Final = 1

# The one object both the metadata rule and the bullet rule route through (O2b), so a project
# entry's facts can never land an `employment.*` predicate: each kind names its subject kind, and
# every slot is checked against the catalog's `legal_subject_kinds` for that subject (§6.2a).
_ENTRY_KIND_MODEL: Final[Mapping[str, EntryKindSpec]] = {
    "experience": EntryKindSpec(
        subject_kind="employment",
        slots=(
            Slot("metadata", "heading", "string", "employment.organization", "heading"),
            Slot("metadata", "title", "string", "employment.title", "title"),
            Slot("metadata", "dates", "date_range", "employment.date_range", "dates"),
            Slot("metadata", "location", "string", "entity.location", "location"),
            Slot("contribution", "text", "string", "employment.accomplishment", "text"),
        ),
    ),
    "project": EntryKindSpec(
        subject_kind="project",
        slots=(
            # O3c coalesce: title is the project's real name, heading its fallback (latex.py).
            Slot("metadata", ("title", "heading"), "string", "project.name", "chosen"),
            # O3b: the two ends of one parsed range, each its own year_month candidate.
            Slot("metadata", "dates", "year_month", "project.start_date", "dates", "range_start"),
            Slot("metadata", "dates", "year_month", "project.end_date", "dates", "range_end"),
            Slot("metadata", "location", "string", "entity.location", "location"),
            Slot("contribution", "text", "string", "project.contribution", "text"),
        ),
    ),
}

_RESUME_V1_MAPPING: Final = ExtractionMapping(
    literal_rules=(
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
    ),
    model_routed_rules=(
        ModelRoutedRule(
            locator_pattern="entries/*/metadata", kind_source="self", emits_group="metadata"
        ),
        ModelRoutedRule(
            locator_pattern="entries/*/bullets/*",
            kind_source="condition",
            emits_group="contribution",
        ),
    ),
    entry_kind_model=_ENTRY_KIND_MODEL,
    deferrals=(
        Deferral(locator_pattern="header/2", reason="no_predicate_exists"),
        Deferral(locator_pattern="education/*", reason="free_text_deferred"),
    ),
)

#: The closed set of builtin mappings this build retains, keyed by adapter id.
BUILTIN_EXTRACTION_MAPPINGS: Final[Mapping[str, ExtractionMapping]] = {
    RESUME_ADAPTER_ID: _RESUME_V1_MAPPING,
}

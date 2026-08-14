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
from boardwatch.profile_bundle.models.policy import (
    AdapterExtractionMapping,
    DeferralModel,
    EntryKindModelEntry,
    ExtractionMappingsDocument,
    LiteralRuleModel,
    ModelRoutedRuleModel,
    SlotModel,
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

#: Catalog predicates that no builtin mapping reaches, each with the reason it is deliberately
#: unreached rather than an accidental orphan (§5.2 invariant 4). The invariant treats a catalog
#: predicate as reconciled when it is named by some builtin mapping OR listed here — so a NEW
#: predicate nobody wires (§2.1's defect one layer over) fails the gate instead of sitting silently
#: present. `not_reachable_from_builtin_mappings` in the design.
#:
#: The `boardwatch-resume-v1` enumerator (§6.1) surfaces five bucket kinds — header, entry metadata,
#: entry bullets, skill items and education — so a catalog predicate no producing rule can populate
#: from those buckets is declared unreached here. Education's three predicates are reached by the
#: AGENT lane (§8), not by this deterministic mapping, which only defers `education/*`.
NOT_REACHABLE_FROM_BUILTIN_MAPPINGS: Final[Mapping[str, str]] = {
    "person.professional_headline": (
        "the résumé header carries only a name (header/1) and an email (header/2, no predicate); "
        "there is no headline bucket"
    ),
    "education.institution": (
        "the education agent lane's target (§8), not this deterministic mapping's — the mapping "
        "defers `education/*` (free_text_deferred) rather than producing a candidate"
    ),
    "education.credential": "as education.institution — the education agent lane's target (§8)",
    "education.field": "as education.institution — the education agent lane's target (§8)",
    "education.start_date": (
        "the résumé's two education lines carry institution/credential/field only; no bucket "
        "carries an education date"
    ),
    "education.end_date": "as education.start_date — no résumé bucket carries an education date",
    "education.result": "no résumé bucket carries an education result (e.g. a GPA line)",
    "employment.responsibility": (
        "résumé bullets route to employment.accomplishment; there is no separate responsibility "
        "bucket"
    ),
    "employment.team_size": "no résumé bucket carries a team size",
    "project.summary": (
        "no longer the metadata heading's target after §6.2a routed project.name; the résumé has "
        "no project-summary bucket"
    ),
    "deployment.environment": "no résumé bucket carries a deployment environment",
    "publication.title": "a publications surface the résumé enumerator has no bucket for",
    "publication.venue": "as publication.title — no publications bucket",
    "publication.date": "as publication.title — no publications bucket",
    "entity.url": "the enumerator surfaces no per-entity URL bucket",
    "recognition.name": "a recognition surface the résumé enumerator has no bucket for",
    "recognition.issuer": "as recognition.name — no recognition bucket",
    "award.date": "an awards surface the résumé enumerator has no bucket for",
    "certification.issue_date": "a certifications surface the résumé enumerator has no bucket for",
    "certification.expiry": "as certification.issue_date — no certifications bucket",
    "affiliation.role": "an affiliations surface the résumé enumerator has no bucket for",
    "affiliation.date_range": "as affiliation.role — no affiliations bucket",
    "course.title": "a courses surface the résumé enumerator has no bucket for",
    "presentation.title": "a presentations surface the résumé enumerator has no bucket for",
    "presentation.date": "as presentation.title — no presentations bucket",
    "presentation.venue": "as presentation.title — no presentations bucket",
    "patent.title": "a patents surface the résumé enumerator has no bucket for",
    "patent.filing_date": "as patent.title — no patents bucket",
    "patent.grant_date": "as patent.title — no patents bucket",
    "application.requires_sponsorship": (
        "an application-only work-authorization fact, never sourced from a résumé; it belongs to "
        "application/gated-facts.yaml (§16)"
    ),
    "application.authorized_regions": (
        "as application.requires_sponsorship — an application-only fact, never résumé-sourced"
    ),
}


# --------------------------------------------------------------------------------------------------
# The persisted form: dataclasses <-> `policy/extraction-mappings.yaml` document (schema v2).
#
# The interpreter (`extraction.py`) reads dataclasses; the bundle stores a pydantic document. These
# two converters are the only bridge, so `run_extraction` can consume a seeded/loaded bundle and the
# controller's schema-v2 seed can be reconstructed from the builtin. Serialisation is deterministic:
# adapters sort by id and every rule/slot keeps its declared order, so identical content addresses.
# --------------------------------------------------------------------------------------------------


def _slot_model(slot: Slot) -> SlotModel:
    return SlotModel(
        group=slot.group,
        value_from=slot.value_from,
        value_type=slot.value_type,
        predicate=slot.predicate,
        display_from=slot.display_from,
        value_selector=slot.value_selector,
    )


def _adapter_mapping(adapter_id: str, mapping: ExtractionMapping) -> AdapterExtractionMapping:
    return AdapterExtractionMapping(
        adapter_id=adapter_id,
        literal_rules=tuple(
            LiteralRuleModel(
                locator_pattern=rule.locator_pattern,
                predicate=rule.predicate,
                value_from=rule.value_from,
                value_type=rule.value_type,
                display_from=rule.display_from,
            )
            for rule in mapping.literal_rules
        ),
        model_routed_rules=tuple(
            ModelRoutedRuleModel(
                locator_pattern=rule.locator_pattern,
                kind_source=rule.kind_source,
                emits_group=rule.emits_group,
            )
            for rule in mapping.model_routed_rules
        ),
        entry_kind_model=tuple(
            EntryKindModelEntry(
                kind=kind,
                subject_kind=spec.subject_kind,
                slots=tuple(_slot_model(slot) for slot in spec.slots),
            )
            for kind, spec in sorted(mapping.entry_kind_model.items())
        ),
        deferrals=tuple(
            DeferralModel(locator_pattern=deferral.locator_pattern, reason=deferral.reason)
            for deferral in mapping.deferrals
        ),
    )


def extraction_mappings_document(
    mappings: Mapping[str, ExtractionMapping], *, version: int = CURRENT_MAPPING_VERSION
) -> ExtractionMappingsDocument:
    """Serialise the interpreter's dataclasses to the persisted document (adapters sorted by id)."""
    return ExtractionMappingsDocument(
        mappings_version=version,
        adapters=tuple(
            _adapter_mapping(adapter_id, mappings[adapter_id]) for adapter_id in sorted(mappings)
        ),
    )


def _slot_dataclass(slot: SlotModel) -> Slot:
    return Slot(
        group=slot.group,
        value_from=slot.value_from,
        value_type=slot.value_type,
        predicate=slot.predicate,
        display_from=slot.display_from,
        value_selector=slot.value_selector,
    )


def _adapter_dataclass(adapter: AdapterExtractionMapping) -> ExtractionMapping:
    return ExtractionMapping(
        literal_rules=tuple(
            ExtractionRule(
                locator_pattern=rule.locator_pattern,
                predicate=rule.predicate,
                value_from=rule.value_from,
                value_type=rule.value_type,
                display_from=rule.display_from,
            )
            for rule in adapter.literal_rules
        ),
        model_routed_rules=tuple(
            ModelRoutedRule(
                locator_pattern=rule.locator_pattern,
                kind_source=rule.kind_source,
                emits_group=rule.emits_group,
            )
            for rule in adapter.model_routed_rules
        ),
        entry_kind_model={
            entry.kind: EntryKindSpec(
                subject_kind=entry.subject_kind,
                slots=tuple(_slot_dataclass(slot) for slot in entry.slots),
            )
            for entry in adapter.entry_kind_model
        },
        deferrals=tuple(
            Deferral(locator_pattern=deferral.locator_pattern, reason=deferral.reason)
            for deferral in adapter.deferrals
        ),
    )


def mappings_from_document(doc: ExtractionMappingsDocument) -> dict[str, ExtractionMapping]:
    """Parse the persisted document back into the interpreter's dataclasses, keyed by adapter id."""
    return {adapter.adapter_id: _adapter_dataclass(adapter) for adapter in doc.adapters}


def builtin_extraction_mappings_document() -> ExtractionMappingsDocument:
    """The builtin mapping as the persisted document — the schema-v2 seed and migration source."""
    return extraction_mappings_document(BUILTIN_EXTRACTION_MAPPINGS)

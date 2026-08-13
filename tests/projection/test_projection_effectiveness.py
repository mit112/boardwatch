"""Effectiveness and expiry are different gates, and the synthetic bundle proves it.

The design's §9 asked for a before/after expiry control using the stale fact. That cannot work:
`fact.packet-pantry.legacy-language.001` fails on `verification_state: stale`, so no choice of
`as_of` changes its verdict. The fact that CAN demonstrate a date-driven transition is
`fact.example-credential.expiry.001` — verified, `expires_at: '2026-07-01'`, and still effective.
Two fixtures, two code paths.

A further, non-obvious trap: `project.packet-pantry` already has an EFFECTIVE `technology.used`
fact ahead of the stale one in index order, so `resume_facts_for`'s first-wins `setdefault` masks
the stale fact from the output even if the effectiveness check were deleted outright — the earlier
fact already claims the predicate's slot in the returned mapping regardless of what happens to the
later one, so a real-bundle query alone cannot prove the effectiveness gate is what excludes the
stale fact (confirmed by mutation — see the task report); the isolated fixture below,
`test_an_isolated_stale_fact_is_refused_because_it_is_not_effective`, uses a synthetic subject with
no colliding sibling to close that gap.

Three more cases isolate the rows the two fixtures above cannot reach on their own:

- a fact that IS effective and unexpired but never declared `resume` in `allowed_surfaces` (the
  row Task 6 handed to this module, since `EntryDeclaration` has no fact-id field to check it
  against);
- a fact that declares `resume` anyway but whose predicate's surface policy is `application_only`
  — proving `is_application_only` does independent work the surface check alone would miss;
- a fact whose predicate's expiry behaviour is `never` but which still carries a stray, long-past
  `expires_at` — an author's review reminder, per `completeness.py`'s own docstring, not a
  deadline. `declared_expiry` would flag it anyway if asked unconditionally, which is exactly why
  `resume_facts_for` must gate that question on the predicate's `expiry.behaviour` first.
"""

from __future__ import annotations

from datetime import date

from boardwatch.profile_bundle.effective import effective_fact_ids
from boardwatch.projection.effectiveness import resume_facts_for
from tests.projection.conftest import bundle_ctx, context_over, materialised_bundle  # noqa: F401

STALE = "fact.packet-pantry.legacy-language.001"
EXPIRING = "fact.example-credential.expiry.001"

#: Appended to `facts/projects/project.packet-pantry.yaml`, naming a synthetic subject that has no
#: OTHER fact at all — unlike the real `STALE` fixture above, nothing else can account for this
#: fact's absence from `resume_facts_for`'s output, so its exclusion isolates the effectiveness
#: gate specifically.
_ISOLATED_STALE_FACT = """
- fact_id: fact.synthetic-stale-fixture.language.001
  subject_id: project.synthetic-stale-fixture
  predicate: technology.used
  value:
    type: skill_ref
    skill_id: skill.example-language
  verification_state: stale
  verification_basis: repository_verified
  usage_context: personal_project
  evidence_ids: []
  allowed_surfaces:
  - resume
  conflict_group_id: null
  reviewed_at: '2026-08-10'
  expires_at: null
  supersedes_fact_ids: []
  import_lineage: null
  notes: Isolated stale fixture; no sibling fact shares its predicate or subject.
"""

#: Appended to `facts/certifications.yaml`, naming a synthetic subject with no sibling fact under
#: the same predicate — `certification.example-credential` already has an effective, resume-
#: surfaced `recognition.issuer` fact, and (as with `_ISOLATED_STALE_FACT` above) reusing that
#: subject would let the earlier fact's `setdefault` slot mask this fixture's own exclusion,
#: making the guard mutation-proof for the wrong reason. Effective, unexpired, standard predicate,
#: not gated — it simply never declared `resume`.
_FACT_DECLARED_WITHOUT_RESUME = """
- fact_id: fact.synthetic-surface-fixture.internal-note.001
  subject_id: certification.synthetic-surface-fixture
  predicate: recognition.issuer
  value:
    type: string
    value: Internal note, not declared for the resume surface
  verification_state: verified
  verification_basis: public_record_verified
  usage_context: professional
  evidence_ids: []
  allowed_surfaces:
  - public
  conflict_group_id: null
  reviewed_at: '2026-08-10'
  expires_at: null
  supersedes_fact_ids: []
  import_lineage: null
  notes: null
"""

#: Appended to `facts/identity.yaml`. Declares `resume` in `allowed_surfaces` — a leaky declaration
#: a surface-only check would pass — but its predicate's `surface_policy: application_only` means
#: `is_application_only` must refuse it regardless. (`application/gated-facts.yaml` cannot host
#: this fixture: `GatedFactsDocument` itself refuses a fact there declaring anything but
#: `[application]`, so the leak this fixture models can only be authored in a plain facts file.)
_FACT_APPLICATION_ONLY_PREDICATE_BUT_DECLARES_RESUME = """
- fact_id: fact.example.leaked-application-only.001
  subject_id: person.example-candidate
  predicate: application.requires_sponsorship
  value:
    type: boolean
    value: true
  verification_state: owner_confirmed
  verification_basis: owner_attested
  usage_context: professional
  evidence_ids: []
  allowed_surfaces:
  - resume
  conflict_group_id: null
  reviewed_at: '2026-08-10'
  expires_at: null
  supersedes_fact_ids: []
  import_lineage: null
  notes: A deliberately leaky declaration; proves the application_only guard fires independent of the surface check.
"""

#: Appended to `facts/projects/project.packet-pantry.yaml`, but naming a SUBJECT the packaged
#: example never uses (`project.packet-pantry` already has an effective `technology.used` fact,
#: and `resume_facts_for` keeps only the first-in-index-order fact per predicate — a second one on
#: the same subject would be silently shadowed by the real one instead of exercising the guard
#: under test). `technology.used` has `expiry.behaviour: never`, so a stray `expires_at` on it is a
#: review reminder, not a deadline — it must survive at any `as_of`, including one long after it.
_FACT_NEVER_EXPIRING_WITH_A_STRAY_DATE = """
- fact_id: fact.synthetic-note-fixture.legacy-note.001
  subject_id: project.synthetic-note-fixture
  predicate: technology.used
  value:
    type: skill_ref
    skill_id: skill.example-language
  verification_state: verified
  verification_basis: repository_verified
  usage_context: personal_project
  evidence_ids: []
  allowed_surfaces:
  - resume
  conflict_group_id: null
  reviewed_at: '2026-08-10'
  expires_at: '2020-01-01'
  supersedes_fact_ids: []
  import_lineage: null
  notes: A stray review-reminder date; technology.used never blocks active use on it.
"""


def test_the_stale_fact_is_resume_surfaced_and_conflict_free(bundle_ctx) -> None:  # noqa: F811
    """The premise. If the bundle stops carrying such a fact, every test below is vacuous."""
    fact = next(f for f in bundle_ctx.index.facts if f.fact_id == STALE)
    assert "resume" in [s.value for s in fact.allowed_surfaces]
    assert fact.conflict_group_id is None
    assert fact.fact_id not in effective_fact_ids(bundle_ctx)


def test_an_isolated_stale_fact_is_refused_because_it_is_not_effective(
    materialised_bundle,  # noqa: F811
) -> None:
    """The genuine effectiveness-gate proof. This fixture is the ONLY fact its subject has, is
    résumé-surfaced, unexpired (`technology.used` never blocks active use), and not gated — so an
    empty result can only be the effectiveness check at work, unconfounded by predicate collision."""
    materialised_bundle.write(
        "facts/projects/project.packet-pantry.yaml",
        materialised_bundle.read("facts/projects/project.packet-pantry.yaml")
        + _ISOLATED_STALE_FACT,
    )
    ctx = context_over(materialised_bundle)
    fact = next(
        f for f in ctx.index.facts if f.fact_id == "fact.synthetic-stale-fixture.language.001"
    )
    assert fact.fact_id not in effective_fact_ids(ctx), "premise: it must not be effective"
    assert "resume" in [s.value for s in fact.allowed_surfaces], "premise: it must be resume-surfaced"

    facts = resume_facts_for("project.synthetic-stale-fixture", ctx, as_of=date(2026, 8, 13))
    assert facts == {}, "the only candidate fact for this subject must be refused"


def test_the_expiring_fact_is_effective_so_only_the_date_decides(bundle_ctx) -> None:  # noqa: F811
    """The before/after control the design wanted, on the fact that can actually provide it."""
    fact = next(f for f in bundle_ctx.index.facts if f.fact_id == EXPIRING)
    assert fact.fact_id in effective_fact_ids(bundle_ctx)
    assert fact.expires_at is not None

    subject = fact.subject_id
    before = resume_facts_for(subject, bundle_ctx, as_of=date(2026, 6, 1))
    after = resume_facts_for(subject, bundle_ctx, as_of=date(2026, 8, 1))

    assert EXPIRING in {f.fact_id for f in before.values()}, "same bytes must pass before expiry"
    assert EXPIRING not in {f.fact_id for f in after.values()}, "and fail after"


def test_a_fact_not_declared_for_resume_is_excluded(materialised_bundle) -> None:  # noqa: F811
    """Effective, unexpired, not gated — but it never declared `resume`. The row Task 6 handed to
    this module, isolated from `is_application_only` AND from predicate collision by construction:
    this is the ONLY fact its (synthetic) subject has, so an empty result can only be the surface
    check at work."""
    materialised_bundle.write(
        "facts/certifications.yaml",
        materialised_bundle.read("facts/certifications.yaml") + _FACT_DECLARED_WITHOUT_RESUME,
    )
    ctx = context_over(materialised_bundle)
    fact = next(
        f
        for f in ctx.index.facts
        if f.fact_id == "fact.synthetic-surface-fixture.internal-note.001"
    )
    assert fact.fact_id in effective_fact_ids(ctx), "premise: the fixture must be effective"
    assert "resume" not in [s.value for s in fact.allowed_surfaces], "premise: it must lack resume"

    facts = resume_facts_for("certification.synthetic-surface-fixture", ctx, as_of=date(2026, 8, 13))
    assert facts == {}, "the only candidate fact for this subject must be refused"


def test_an_application_only_predicate_fact_declaring_resume_is_still_excluded(
    materialised_bundle,  # noqa: F811
) -> None:
    """A leaky declaration a surface-only check would let through. `is_application_only`'s
    `surface_policy` path must catch it anyway."""
    materialised_bundle.write(
        "facts/identity.yaml",
        materialised_bundle.read("facts/identity.yaml")
        + _FACT_APPLICATION_ONLY_PREDICATE_BUT_DECLARES_RESUME,
    )
    ctx = context_over(materialised_bundle)
    fact = next(
        f for f in ctx.index.facts if f.fact_id == "fact.example.leaked-application-only.001"
    )
    assert fact.fact_id in effective_fact_ids(ctx), "premise: the fixture must be effective"
    assert "resume" in [s.value for s in fact.allowed_surfaces], "premise: it must declare resume"
    catalog = ctx.index.predicates
    assert catalog is not None
    spec = catalog.by_id["application.requires_sponsorship"]
    assert spec.surface_policy.value == "application_only", "premise: its predicate must be gated"

    facts = resume_facts_for("person.example-candidate", ctx, as_of=date(2026, 8, 13))
    assert "fact.example.leaked-application-only.001" not in {f.fact_id for f in facts.values()}


def test_a_never_expiring_predicates_stray_date_does_not_exclude_the_fact(
    materialised_bundle,  # noqa: F811
) -> None:
    """`technology.used` never blocks active use, so a long-past `expires_at` on it must not
    exclude the fact at any `as_of` — the exact failure mode `completeness.py`'s own docstring
    names: "blocking on that alone would retire a live skill because somebody left themselves a
    note." """
    materialised_bundle.write(
        "facts/projects/project.packet-pantry.yaml",
        materialised_bundle.read("facts/projects/project.packet-pantry.yaml")
        + _FACT_NEVER_EXPIRING_WITH_A_STRAY_DATE,
    )
    ctx = context_over(materialised_bundle)
    fact = next(
        f for f in ctx.index.facts if f.fact_id == "fact.synthetic-note-fixture.legacy-note.001"
    )
    assert fact.fact_id in effective_fact_ids(ctx), "premise: the fixture must be effective"
    assert fact.expires_at is not None and fact.expires_at < date(2026, 8, 13), (
        "premise: its expires_at must already be in the past at the as_of used below"
    )

    facts = resume_facts_for("project.synthetic-note-fixture", ctx, as_of=date(2026, 8, 13))
    assert "fact.synthetic-note-fixture.legacy-note.001" in {f.fact_id for f in facts.values()}

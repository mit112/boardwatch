"""P9's two employment-type families, and the catalog change that re-keys every verdict.

Two halves, deliberately separate:

`TestContractNotFte` / `TestInternship` assert BEHAVIOUR through `evaluate`, including the
suppressors that exist because a naive pattern was measured wrong on the 13,590 real postings
P8 imported (see .agent/plans/2026-08-04-p9-eligibility-families-design.md §0). Each family
carries positive rows, negative controls, a negation-cue zero-row case, and the specific
false-positive class its suppressor closes.

`TestCatalogChangeReEvaluates` exercises the part that is NOT a pattern assertion: adding a
family moves `catalog.version`, which moves `rules_hash`, which invalidates every stored
`input_fingerprint` and re-evaluates the whole corpus. The four eligibility tables carry
BEFORE UPDATE/DELETE RAISE(ABORT) triggers, so that path can only ever supersede rows. A test
that only checked the new patterns match would leave the migration entirely uncovered.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import func, insert, select
from typer.testing import CliRunner

from boardwatch.cli.app import app
from boardwatch.core.clock import utcnow
from boardwatch.eligibility.catalog import RulesCatalog, bundled_rules_text, load_rules
from boardwatch.eligibility.engine import evaluate
from boardwatch.eligibility.facts import Facts, Policy
from boardwatch.store import tables
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.queries import save_profile

runner = CliRunner()

# Both families default to `preference`; a blocker policy is what makes `unmet` observable as
# `ineligible`, so the disposition tests state it explicitly rather than relying on a default.
BLOCK_BOTH = Policy(families={"contract_not_fte": "blocker", "internship": "blocker"})


@pytest.fixture(scope="module")
def catalog(tmp_path_factory: pytest.TempPathFactory) -> RulesCatalog:
    return load_rules(tmp_path_factory.mktemp("no-override"))


def rows(catalog: RulesCatalog, body: str, facts: Facts, policy: Policy = BLOCK_BOTH):
    """(rule_id, disposition) for the two P9 families only, so an unrelated family's row
    from a shared body cannot make a case pass or fail by accident."""
    result = evaluate(body, facts, policy, catalog)
    return sorted(
        (r.rule_id, r.disposition)
        for r in result.requirements
        if r.rule_id.startswith(("contract_not_fte:", "internship:"))
    )


def verdict(catalog: RulesCatalog, body: str, facts: Facts, policy: Policy = BLOCK_BOTH) -> str:
    return evaluate(body, facts, policy, catalog).verdict


FTE_ONLY = Facts(employment_type_preference="fte_only")
OPEN_TO_CONTRACT = Facts(employment_type_preference="open_to_contract")
CONTRACT_ONLY = Facts(employment_type_preference="contract_only")
NO_INTERNS = Facts(internship_preference="exclude")
WANTS_INTERNS = Facts(internship_preference="open")


class TestContractNotFte:
    @pytest.mark.parametrize(
        "body",
        [
            "This is a contract position based in Denver.",
            "This role is on a two-year fixed-term contract.",
            "We are hiring for a 12-month contract.",
            "This is a contract-to-hire role.",
            "The engagement is a contract assignment.",
        ],
    )
    def test_a_declared_contract_engagement_blocks_an_fte_only_candidate(
        self, catalog: RulesCatalog, body: str
    ) -> None:
        assert rows(catalog, body, FTE_ONLY) == [
            ("contract_not_fte:contract_engagement_declared", "unmet")
        ]
        assert verdict(catalog, body, FTE_ONLY) == "ineligible"

    def test_the_same_posting_is_met_when_contract_is_acceptable(
        self, catalog: RulesCatalog
    ) -> None:
        body = "This is a contract position based in Denver."
        assert rows(catalog, body, OPEN_TO_CONTRACT) == [
            ("contract_not_fte:contract_engagement_declared", "met")
        ]
        assert verdict(catalog, body, OPEN_TO_CONTRACT) == "eligible"

    def test_1099_and_c2c_are_a_separate_pattern_from_the_contract_surface(
        self, catalog: RulesCatalog
    ) -> None:
        body = "PLEASE NOTE: this is a fully remote, 1099 independent contractor opportunity."
        assert rows(catalog, body, FTE_ONLY) == [
            ("contract_not_fte:independent_contractor_declared", "unmet")
        ]

    def test_a_temporary_engagement_has_its_own_pattern_and_requirement_text(
        self, catalog: RulesCatalog
    ) -> None:
        assert rows(catalog, "This is a temporary position covering parental leave.", FTE_ONLY) == [
            ("contract_not_fte:temporary_engagement_declared", "unmet")
        ]

    def test_the_three_non_fte_patterns_corroborate_rather_than_conflict(
        self, catalog: RulesCatalog
    ) -> None:
        """REVIEW REGRESSION. The three non-FTE patterns first shipped with a distinct
        `implies` each, all four values in one exclusive group. engine.py conflicts a group
        when two DISTINCT values are present, so a posting that said the same thing twice
        conflicted with itself and went `uncertain` -- the more explicit the posting, the less
        decidable the verdict. They now share `non_permanent_role`, and two detections of the
        same value are corroboration by design (engine.py:144).
        """
        body = (
            "This is a 6-month contract position. You will be engaged as an independent"
            " contractor and invoice monthly."
        )
        assert verdict(catalog, body, FTE_ONLY) == "ineligible"
        assert {d for _, d in rows(catalog, body, FTE_ONLY)} == {"unmet"}

        both = "This is a temporary assignment. It is also a 12 month contract."
        assert verdict(catalog, both, FTE_ONLY) == "ineligible"

    def test_permanent_employment_is_unmet_for_a_contract_only_candidate(
        self, catalog: RulesCatalog
    ) -> None:
        """The family is SYMMETRIC. Without the fte_role arm `contract_only` would be a
        choice no pattern could ever decide."""
        body = "This is a permanent full-time position with full benefits."
        assert rows(catalog, body, CONTRACT_ONLY) == [
            ("contract_not_fte:permanent_fte_declared", "unmet")
        ]
        assert rows(catalog, body, FTE_ONLY) == [
            ("contract_not_fte:permanent_fte_declared", "met")
        ]

    @pytest.mark.parametrize(
        "body",
        [
            # The measured false-positive class. A bare \bcontract\b matches 849 of the
            # 13,590 real postings, against 96 whose TITLE names a contract role and 30 whose
            # provider states a non-permanent employment type: under 10% precision on either
            # denominator. Precision here comes from the declaration frame instead.
            "You will own customer contract renewals end to end.",
            "Experience with government contract vehicles is required.",
            "You will lead contract negotiation with our vendors.",
            "Build the API contract between our services.",
            "Experience auditing smart contract security is a plus.",
            "You will manage the client contract lifecycle.",
            # These state the OPPOSITE: the posting is permanent employment.
            "W-2 only; no C2C or 1099 candidates.",
            "This is not a contract role.",
        ],
    )
    def test_a_contract_that_is_a_document_is_not_an_engagement(
        self, catalog: RulesCatalog, body: str
    ) -> None:
        assert rows(catalog, body, FTE_ONLY) == []
        assert verdict(catalog, body, FTE_ONLY) == "eligible"

    def test_a_temporary_computing_noun_is_not_a_temporary_engagement(
        self, catalog: RulesCatalog
    ) -> None:
        assert rows(catalog, "You will optimise temporary table usage in our warehouse.", FTE_ONLY) == []

    def test_a_negated_contract_statement_produces_no_row(
        self, catalog: RulesCatalog
    ) -> None:
        """The cue guard, not a suppressor: a cue inside the span drops the detection."""
        assert rows(catalog, "This is not a contract position.", FTE_ONLY) == []
        assert verdict(catalog, "This is not a contract position.", FTE_ONLY) == "eligible"

    def test_a_posting_declaring_both_abstains_instead_of_guessing(
        self, catalog: RulesCatalog
    ) -> None:
        """A posting that declares BOTH a contract engagement and permanent employment is
        genuinely ambiguous, and the two-member exclusive group makes both rows undecidable
        rather than letting whichever pattern fired first decide."""
        body = "This is a contract position. This role is a permanent full-time position."
        assert rows(catalog, body, FTE_ONLY) == [
            ("contract_not_fte:contract_engagement_declared", "unknown"),
            ("contract_not_fte:permanent_fte_declared", "unknown"),
        ]
        assert verdict(catalog, body, FTE_ONLY) == "uncertain"

    def test_an_undeclared_preference_abstains_rather_than_assuming_fte(
        self, catalog: RulesCatalog
    ) -> None:
        body = "This is a contract position based in Denver."
        assert rows(catalog, body, Facts()) == [
            ("contract_not_fte:contract_engagement_declared", "unknown")
        ]
        assert rows(catalog, body, Facts(employment_type_preference="prefer_not_to_say")) == [
            ("contract_not_fte:contract_engagement_declared", "unknown")
        ]


class TestInternship:
    @pytest.mark.parametrize(
        "body",
        [
            "This is a paid summer internship in our Seattle office.",
            "This is a 12-week internship on the platform team.",
            "This is a co-op position running from January to June.",
            "Apply for our summer 2026 internship today.",
            "As an intern you will be paired with a mentor and you will ship real code.",
            "This internship runs from June to August and pays hourly.",
        ],
    )
    def test_a_self_declared_internship_blocks_a_candidate_excluding_them(
        self, catalog: RulesCatalog, body: str
    ) -> None:
        assert rows(catalog, body, NO_INTERNS) == [
            ("internship:internship_role_declared", "unmet")
        ]
        assert verdict(catalog, body, NO_INTERNS) == "ineligible"

    def test_the_same_posting_is_met_for_a_candidate_who_wants_one(
        self, catalog: RulesCatalog
    ) -> None:
        body = "This is a paid summer internship in our Seattle office."
        assert rows(catalog, body, WANTS_INTERNS) == [
            ("internship:internship_role_declared", "met")
        ]
        assert verdict(catalog, body, WANTS_INTERNS) == "eligible"

    @pytest.mark.parametrize(
        "body",
        [
            # Credit-for-internships: a CONCESSION on an experience floor. Reading it as an
            # internship role inverts the most candidate-friendly sentence a posting has.
            "Internship and co-op experience counts toward this requirement.",
            "We accept internships as relevant professional experience.",
            "0-2 years of experience; internships and academic projects count.",
            # Senior JDs that supervise interns.
            "You will mentor interns and junior engineers on the team.",
            "This role manages our intern cohort each summer.",
            "Our former interns often return as full-time engineers.",
            # Programme-owner context: the JD is ABOUT internships because the job runs them.
            "Support recruiting events, university recruiting, and internship programs.",
            "Define the global early career recruiting strategy spanning internship programs.",
        ],
    )
    def test_a_mention_of_internships_is_not_a_declaration_of_one(
        self, catalog: RulesCatalog, body: str
    ) -> None:
        assert rows(catalog, body, NO_INTERNS) == []
        assert verdict(catalog, body, NO_INTERNS) == "eligible"

    @pytest.mark.parametrize(
        "body",
        [
            # THE measured regression this family must never reintroduce. An enrolment
            # pattern looked like the strongest internship signal and fired on real
            # "Software Engineer - New Grad 2026" postings, which are permanent roles and
            # exactly what the search is for. Enrolment is not internship.
            "Recently graduated or currently enrolled in a university program in Computer"
            " Science, Computer Engineering, or a related discipline.",
            "Enrolled in a University program with a degree in Computer Science.",
            "Must be currently enrolled in an accredited degree program.",
            "You should be pursuing a Bachelor's degree in a technical field.",
        ],
    )
    def test_an_enrolment_requirement_is_not_an_internship(
        self, catalog: RulesCatalog, body: str
    ) -> None:
        assert rows(catalog, body, NO_INTERNS) == []
        assert verdict(catalog, body, NO_INTERNS) == "eligible"

    @pytest.mark.parametrize(
        "body",
        [
            "Internal tooling experience is required.",
            "We work with international teams across four continents.",
            "You will build cooperative multiplayer features.",
        ],
    )
    def test_words_that_merely_contain_intern_or_coop_never_match(
        self, catalog: RulesCatalog, body: str
    ) -> None:
        assert rows(catalog, body, NO_INTERNS) == []

    def test_a_negated_internship_statement_produces_no_row(
        self, catalog: RulesCatalog
    ) -> None:
        body = "This is not an internship; it is a permanent role."
        assert [r for r in rows(catalog, body, NO_INTERNS) if r[0].startswith("internship:")] == []

    def test_an_undeclared_preference_abstains(self, catalog: RulesCatalog) -> None:
        body = "This is a paid summer internship in our Seattle office."
        assert rows(catalog, body, Facts()) == [
            ("internship:internship_role_declared", "unknown")
        ]


class TestReviewRegressions:
    """Wrong verdicts an external review found in the first draft of these families, each
    reproduced against a real corpus sentence where one existed.

    The unifying lesson is structural: `_suppressed` (detect.py:224) only drops when the
    suppressor match lies WHOLLY OUTSIDE the detection span, so a benign-context regex whose
    match ends on the trigger word is inert. The draft had five such suppressors and review
    measured all five removing zero detections across 13,590 postings, while two killed true
    positives. Precision now comes from the declaration frame; the surviving suppressors are
    lookahead-terminated so their match provably ends before the span.
    """

    @pytest.mark.parametrize(
        "body",
        [
            # A refusal to ENGAGE contractors is not a contractor role. The corpus sentence
            # is the second one; its `not` sits in a different CLAUSE from the trigger, which
            # is why the guard had to be suppressed_by_sentence rather than _unit.
            "Please note we are unable to consider C2C applicants.",
            "Unfortunately, we are not able to sponsor visas, including CPT/OPT or employ"
            " corp-to-corp.",
            "We cannot accept 1099 contractors for this role.",
            "W-2 only; no C2C or 1099 candidates.",
        ],
    )
    def test_a_refusal_to_engage_contractors_is_not_a_contractor_role(
        self, catalog: RulesCatalog, body: str
    ) -> None:
        assert rows(catalog, body, FTE_ONLY) == []
        assert verdict(catalog, body, FTE_ONLY) == "eligible"

    @pytest.mark.parametrize(
        "body,facts",
        [
            # The draft frame `(?:this|the)\s+(?:\w+\s+){0,2}?(?:is|will be)` let any noun be
            # the subject, so ordinary prose produced `unmet` rows. The subject must be a role.
            ("The output is a temporary file stored on disk.", FTE_ONLY),
            ("Data in the staging area is a temporary copy.", FTE_ONLY),
            ("The first deliverable is a contract review checklist.", FTE_ONLY),
            ("The team is permanent and distributed.", CONTRACT_ONLY),
        ],
    )
    def test_an_ordinary_sentence_about_a_thing_is_not_an_employment_declaration(
        self, catalog: RulesCatalog, body: str, facts: Facts
    ) -> None:
        assert rows(catalog, body, facts) == []
        assert verdict(catalog, body, facts) == "eligible"

    def test_a_true_positive_survives_a_second_temporary_noun_in_the_same_sentence(
        self, catalog: RulesCatalog
    ) -> None:
        """The draft carried a `temporary (table|file|...)` suppressor which never fired on the
        prose it targeted (its match overlapped the span) but DID fire on a second occurrence,
        deleting a real declaration. Requiring a role noun after `temporary` replaced it."""
        body = "This is a temporary position that writes to a temporary table."
        assert rows(catalog, body, FTE_ONLY) == [
            ("contract_not_fte:temporary_engagement_declared", "unmet")
        ]

    @pytest.mark.parametrize(
        "body",
        [
            # The draft added privacy-notice terms (`personal data`, `evaluate your
            # application`) to the shared benign list. They were redundant -- the declaration
            # frame already excluded the notice -- and they dropped genuine declarations.
            "We will review your application for the contract position.",
            "Interviews are scheduled once we evaluate your application for this 6-month"
            " contract role.",
            "The contract position requires handling personal data of customers.",
        ],
    )
    def test_application_and_privacy_wording_does_not_cancel_a_real_declaration(
        self, catalog: RulesCatalog, body: str
    ) -> None:
        assert rows(catalog, body, FTE_ONLY) == [
            ("contract_not_fte:contract_engagement_declared", "unmet")
        ]

    def test_the_privacy_notice_itself_still_produces_no_row(
        self, catalog: RulesCatalog
    ) -> None:
        """~240 of the draft's 249 `independent contractor` hits were this one sentence."""
        body = (
            "We will use this information to evaluate your application for employment or an"
            " independent contractor role, as applicable."
        )
        assert rows(catalog, body, FTE_ONLY) == []

    @pytest.mark.parametrize(
        "body",
        [
            # The draft's programme-owner suppressor was a bare clause-wide keyword list
            # (`talent`, `early career`, `coordinator`, `university relations`), which
            # silenced ordinary internship JDs. It now needs an ownership VERB.
            "This internship is part of our Early Career Program.",
            "This is a paid summer internship in our university relations program.",
            "This internship is run by our talent team.",
        ],
    )
    def test_a_real_internship_survives_programme_vocabulary(
        self, catalog: RulesCatalog, body: str
    ) -> None:
        assert rows(catalog, body, NO_INTERNS) == [
            ("internship:internship_role_declared", "unmet")
        ]

    @pytest.mark.parametrize(
        "body",
        [
            "You will own and scale our internship program and new grad hiring pipeline.",
            "Support recruiting events, university recruiting, and internship programs.",
            "Define and own the global early career recruiting strategy spanning internship"
            " programs.",
        ],
    )
    def test_a_programme_owner_jd_is_still_not_an_internship(
        self, catalog: RulesCatalog, body: str
    ) -> None:
        assert rows(catalog, body, NO_INTERNS) == []


class TestSecondReviewRegressions:
    """A second review pass on the corrected families found five more, four of them a
    direction problem: a guard that must only look BACKWARD from the trigger was scoped to
    look both ways, so it deleted true positives. `subject_suppressors` is the only
    before-only kind (detect.py:267), and it is what these now use.
    """

    @pytest.mark.parametrize(
        "body",
        [
            # The role-noun subject fix had been applied to contract_not_fte and MISSED here,
            # leaving the original permissive frame live in the internship family.
            "The first deliverable is a co-op hiring plan.",
            "Your top priority this quarter is an internship pipeline for EMEA.",
            "The result will be an internship program with 40 students.",
        ],
    )
    def test_the_internship_frame_also_requires_a_role_noun_subject(
        self, catalog: RulesCatalog, body: str
    ) -> None:
        assert rows(catalog, body, NO_INTERNS) == []
        assert verdict(catalog, body, NO_INTERNS) == "eligible"

    def test_trailing_programme_ownership_prose_does_not_delete_a_real_internship(
        self, catalog: RulesCatalog
    ) -> None:
        """The ownership guard is before-only, so `owns ... early career program` AFTER the
        declaration no longer cancels it. Unit-scoped it did, and this posting is a genuine
        internship the excluding user asked to be told about."""
        body = "This internship is run by the team that owns our early career program."
        assert rows(catalog, body, NO_INTERNS) == [
            ("internship:internship_role_declared", "unmet")
        ]

    @pytest.mark.parametrize(
        "body",
        [
            "You will own and scale our internship program and new grad hiring pipeline.",
            "You will administer the campus recruiting program end to end.",
        ],
    )
    def test_ownership_before_the_mention_still_excludes_a_programme_owner_jd(
        self, catalog: RulesCatalog, body: str
    ) -> None:
        assert rows(catalog, body, NO_INTERNS) == []

    @pytest.mark.parametrize(
        "body",
        [
            # The refusal guard's lookahead named `contract(?:ors?)?`, and because a suppressor
            # may match on EITHER side of the span, any negation plus any later `contract`
            # token killed a genuine declaration. The lookahead now names only c2c/1099/
            # corp-to-corp, which a declaring sentence never also contains.
            "This is a contract position with limited benefits, and contractors invoice"
            " monthly.",
            "This is a 12-month contract role; benefits are not offered to contract staff.",
            "This is a contract position and we do not offer benefits to contractors.",
        ],
    )
    def test_a_negation_elsewhere_in_the_sentence_does_not_delete_the_declaration(
        self, catalog: RulesCatalog, body: str
    ) -> None:
        assert [d for _, d in rows(catalog, body, FTE_ONLY)] == ["unmet"]

    @pytest.mark.parametrize(
        "body",
        [
            # `as an intern` matched the start of a JOB TITLE, and the mentor stand-down could
            # not help because its match starts INSIDE the span. Now guarded by lookahead.
            "As an Intern Program Manager, you will own the summer cohort end to end.",
            # The `interns will VERB` arm is deleted outright: 0 matches in 13,590 postings, so
            # it had no measured recall, and it fired on intern-manager JDs.
            "Interns will receive feedback from you every two weeks.",
            "You will design a curriculum; interns will learn from your team.",
        ],
    )
    def test_an_intern_manager_jd_is_not_an_internship(
        self, catalog: RulesCatalog, body: str
    ) -> None:
        assert rows(catalog, body, NO_INTERNS) == []
        assert verdict(catalog, body, NO_INTERNS) == "eligible"

    @pytest.mark.parametrize(
        "body",
        [
            # Frame-free arms firing on staffing, vendor and HR prose. The first is why the
            # standalone `contract-to-hire` and `c2h` arms were deleted (0 corpus matches, and
            # `and` is a clause boundary so no subject suppressor could reach across it); the
            # rest are caught by the staffing subject suppressor or by dropping `assignment`
            # from the frame-free temporary arm.
            "You will manage full-cycle recruiting for direct hire and contract-to-hire"
            " placements.",
            "Negotiate a 12 month contract with each vendor.",
            "Support employees on a temporary assignment abroad.",
            "You will administer our temporary assignment policy for relocating employees.",
        ],
    )
    def test_staffing_and_hr_prose_is_not_an_employment_declaration(
        self, catalog: RulesCatalog, body: str
    ) -> None:
        assert rows(catalog, body, FTE_ONLY) == []
        assert verdict(catalog, body, FTE_ONLY) == "eligible"

    def test_a_genuine_contract_to_hire_posting_still_fires_through_the_framed_arm(
        self, catalog: RulesCatalog
    ) -> None:
        """Deleting the standalone arm must not cost the real form."""
        assert rows(catalog, "This is a contract-to-hire role.", FTE_ONLY) == [
            ("contract_not_fte:contract_engagement_declared", "unmet")
        ]

    def test_the_benign_document_suppressor_is_the_thing_doing_the_work(
        self, catalog: RulesCatalog
    ) -> None:
        """Review noted the earlier benign-noun cases all passed via the declaration frame, so
        nothing actually pinned the suppressor. This body reaches the frame-free
        `contract role` arm, so only the lookahead-terminated suppressor can stop it."""
        assert rows(catalog, "The customer contract role includes quarterly reviews.", FTE_ONLY) == []


class TestDefaultSeverityCannotHide:
    """Both families ship `default_policy: preference`, measured against the providers' own
    structured employment-type field at 86% precision for contract and 100% for internship.
    Only `blocker` can yield `ineligible`, so at the shipped default a false positive costs
    one informational row and hides nothing."""

    @pytest.mark.parametrize(
        "body,facts",
        [
            ("This is a contract position based in Denver.", FTE_ONLY),
            ("This is a paid summer internship in our Seattle office.", NO_INTERNS),
        ],
    )
    def test_an_unmet_row_at_the_shipped_default_does_not_make_a_posting_ineligible(
        self, catalog: RulesCatalog, body: str, facts: Facts
    ) -> None:
        result = evaluate(body, facts, Policy(), catalog)  # no overrides: catalog defaults
        assert any(d == "unmet" for _, d in rows(catalog, body, facts, Policy()))
        assert result.verdict == "eligible"

    def test_the_catalog_still_declares_preference_for_both(
        self, catalog: RulesCatalog
    ) -> None:
        assert catalog.family("contract_not_fte").default_policy == "preference"
        assert catalog.family("internship").default_policy == "preference"


# --------------------------------------------------------------------------------------
# The migration path: a catalog change re-keys and re-evaluates every stored verdict.
# --------------------------------------------------------------------------------------

CONTRACT_BODY = (
    "We are hiring a backend engineer. This is a contract position based in Denver."
)


def _four_family_rules() -> str:
    """The bundled catalog with P9's two families cut off, i.e. the pre-P9 catalog.

    Derived from the shipped text rather than checked in as a second fixture, so it cannot
    drift away from the real four families and quietly stop representing the `before` state.
    """
    text = bundled_rules_text()
    head, marker, _ = text.partition("  - id: contract_not_fte")
    assert marker, "the P9 family marker moved; this splice needs updating"
    return head


class TestCatalogChangeReEvaluates:
    @pytest.fixture()
    def env(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "cfg"))
        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
        (tmp_path / "cfg").mkdir(parents=True, exist_ok=True)
        return tmp_path / "data"

    def _run(self, data_dir: Path, args: list[str]):
        return runner.invoke(app, ["--data-dir", str(data_dir), *args])

    def _seed(self, data_dir: Path, body: str) -> int:
        engine = get_engine(data_dir)
        ensure_schema(engine)
        now = utcnow()
        with engine.begin() as conn:
            company_id = int(
                conn.execute(
                    insert(tables.companies).values(
                        name="Acme", provider="greenhouse", slug="acme2",
                        source="user", watched=True,
                    )
                ).inserted_primary_key[0]
            )
            job_id = int(
                conn.execute(insert(tables.jobs).values(created_at=now)).inserted_primary_key[0]
            )
            posting_id = int(
                conn.execute(
                    insert(tables.postings).values(
                        company_id=company_id, provider_posting_id="p1",
                        title="Backend Engineer", normalized_title="backend engineer",
                        remote_policy="unknown", first_seen_at=now, last_seen_at=now,
                        status="open", consecutive_missing=0, content_hash="h1",
                        body_text=body, job_id=job_id,
                    )
                ).inserted_primary_key[0]
            )
            conn.execute(
                insert(tables.posting_versions).values(
                    posting_id=posting_id, content_hash="h1", body_text=body,
                    captured_at=now, capture_reason="new",
                )
            )
            save_profile(
                conn, text="Backend engineer.", target_titles=[], exclude_titles=[],
                locations=[], remote_only=False, skills=[], taxonomy_version="t",
                resume_max_pages=1,
            )
        return posting_id

    def _ledger(self, data_dir: Path) -> tuple[int, set[str]]:
        """(evaluation count, distinct rules_hash values) across the whole ledger."""
        engine = get_engine(data_dir)
        with engine.connect() as conn:
            count = int(
                conn.execute(select(func.count()).select_from(tables.eligibility_evaluations)).scalar_one()
            )
            hashes = {
                str(h) for (h,) in conn.execute(select(tables.eligibility_inputs.c.rules_hash)).all()
            }
        return count, hashes

    def test_adding_the_families_re_evaluates_every_stored_verdict(
        self, env: Path, tmp_path: Path
    ) -> None:
        override = tmp_path / "cfg" / "rules.yaml"
        override.write_text(_four_family_rules(), encoding="utf-8")
        self._seed(env, CONTRACT_BODY)
        assert self._run(env, ["eligibility", "facts", "set", "highest_degree", "master"]).exit_code == 0

        first = self._run(env, ["eligibility", "run"])
        assert first.exit_code == 0
        assert "evaluated 1" in first.output
        before_count, before_hashes = self._ledger(env)
        assert before_count == 1

        # A second run under the SAME catalog must be a no-op: the identity already exists.
        assert "evaluated 0" in self._run(env, ["eligibility", "run"]).output
        assert self._ledger(env) == (before_count, before_hashes)

        # Now the catalog gains P9's two families, exactly as shipping this phase does.
        override.unlink()

        after = self._run(env, ["eligibility", "run"])
        assert after.exit_code == 0
        assert "evaluated 1" in after.output, "a changed rules_hash must re-evaluate, not skip"
        after_count, after_hashes = self._ledger(env)
        assert after_count == 2, "the new verdict is a NEW row; rows are superseded, never edited"
        assert before_hashes < after_hashes, "the added families must move rules_hash"
        assert len(after_hashes) == 2

    def test_the_superseded_row_survives_the_re_evaluation_intact(self, env: Path, tmp_path: Path) -> None:
        """The eligibility tables carry BEFORE UPDATE/DELETE RAISE(ABORT) triggers, so a
        re-evaluation that tried to correct a row in place would raise rather than silently
        rewrite history. Assert the old row is still readable at its own fingerprint."""
        override = tmp_path / "cfg" / "rules.yaml"
        override.write_text(_four_family_rules(), encoding="utf-8")
        self._seed(env, CONTRACT_BODY)
        assert self._run(env, ["eligibility", "run"]).exit_code == 0
        engine = get_engine(env)
        with engine.connect() as conn:
            original = conn.execute(
                select(tables.eligibility_evaluations.c.id, tables.eligibility_evaluations.c.verdict)
            ).all()

        override.unlink()
        after = self._run(env, ["eligibility", "run"])
        assert after.exit_code == 0
        # Assert the re-evaluation HAPPENED first. Without this the test passes unchanged when
        # the post-change run silently re-evaluates nothing, which is the very failure the
        # docstring is about -- an untouched row proves immutability only if something tried
        # to touch it. Review caught exactly that gap.
        assert "evaluated 1" in after.output

        with engine.connect() as conn:
            all_rows = conn.execute(
                select(tables.eligibility_evaluations.c.id, tables.eligibility_evaluations.c.verdict)
                .order_by(tables.eligibility_evaluations.c.id)
            ).all()
            requirement_count = int(
                conn.execute(
                    select(func.count()).select_from(tables.eligibility_requirements)
                ).scalar_one()
            )
        assert len(all_rows) == 2, "the re-evaluation must ADD a row, not replace one"
        assert all_rows[0] == original[0], "the superseded row is byte-identical afterwards"
        assert requirement_count > 0

    def test_the_new_families_change_the_verdict_they_should_change(
        self, env: Path, tmp_path: Path
    ) -> None:
        """End to end, the point of the phase: a contract posting that the pre-P9 catalog had
        nothing to say about becomes ineligible once the family exists and is a blocker."""
        override = tmp_path / "cfg" / "rules.yaml"
        override.write_text(_four_family_rules(), encoding="utf-8")
        posting_id = self._seed(env, CONTRACT_BODY)
        assert self._run(env, ["eligibility", "run"]).exit_code == 0
        assert "hidden as ineligible" not in self._run(env, ["top"]).output

        override.unlink()
        assert self._run(
            env, ["eligibility", "facts", "set", "employment_type_preference", "fte_only"]
        ).exit_code == 0
        assert self._run(env, ["eligibility", "policy", "set", "contract_not_fte", "blocker"]).exit_code == 0
        assert self._run(env, ["eligibility", "run"]).exit_code == 0

        top = self._run(env, ["top"])
        assert "hidden as ineligible" in top.output
        assert str(posting_id) not in "\n".join(
            line for line in top.output.splitlines() if "hidden as ineligible" not in line
        )

    def test_a_partial_override_declaring_fewer_families_still_loads(
        self, env: Path, tmp_path: Path
    ) -> None:
        """catalog._verify_families_are_wired is deliberately FORWARD-only: an override may
        declare fewer families than the registry, and the dropped ones simply are not
        evaluated. P9 doubles the number of resolvers that a partial override omits, so the
        asymmetry is worth pinning."""
        override = tmp_path / "cfg" / "rules.yaml"
        override.write_text(_four_family_rules(), encoding="utf-8")
        loaded = load_rules(tmp_path / "cfg")
        assert [f.id for f in loaded.families] == [
            "work_auth", "experience_years", "clearance", "degree",
        ]
        assert loaded.source == "override"

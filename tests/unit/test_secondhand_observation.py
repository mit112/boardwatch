"""D-414(a): a lower-fidelity observation must not overwrite fields it never observed.

`scan/apply.py`'s D25 rule refreshes every provider-sourced column on every positive observation
regardless of `content_hash`. That is right for a provider reading the employer's own board and
wrong for an aggregator lane whose hit converged onto that provider's
`(company_id, provider_posting_id)`: the lane never looked at `remote_policy`, `department` or
`salary_*`, and the location it did read is its own index of the posting. With
`location_filter_mode = "hard"` the overwrite is a deletion path -- a posting recorded remote,
re-rendered as one metro, is hard-vetoed in the SAME run, because the lane stage runs after the
scan and before the ranker.

`body_text` is the member that reaches a VERDICT rather than a score, and it is guarded through
the real eligibility engine below rather than by asserting a column: eligibility reads the CURRENT
`posting_versions` row, so an aggregator body with a different content hash becomes the document
every rule quotes, and an `ineligible` then carries a span that is genuine text cut from the wrong
document -- the keystone invariant passing syntactically while failing in substance.

The INSERT has its own rule for one field only. "A later board scan corrects it" is FALSE for a
lane-first company: `upsert_lane_company` stores it `watched=False`, `get_watched_companies`
filters `watched.is_(True)`, and nothing else feeds the scan its companies, so no board scan will
ever run. The premise is pinned as its own guard below rather than trusted.

The neutrality guards are the other half and are the reason the mechanism is a DECLARATION rather
than a rank on the lane: a board scan must still write exactly what it writes today.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, get_args

import pytest
from sqlalchemy import Engine, insert, select, update

from boardwatch.core.models import BoardSnapshot, RawPosting, SecondhandField
from boardwatch.core.posting_identity import IdentityInputs, compute_identities
from boardwatch.eligibility.catalog import RulesCatalog, load_rules
from boardwatch.eligibility.engine import evaluate
from boardwatch.eligibility.facts import ClearanceFact, Facts, Policy, WorkAuthFact
from boardwatch.rank.heuristic import ProfileView, hard_filter_verdict
from boardwatch.rank.location_gate import classify_location
from boardwatch.scan.apply import (
    _SECONDHAND_COLUMNS,
    _inserted_fields,
    _mutable_fields,
    apply_board,
)
from boardwatch.store import tables
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.queries import (
    current_posting_versions,
    get_watched_companies,
    insert_run,
    upsert_lane_company,
)

ALL_SECONDHAND: frozenset[SecondhandField] = frozenset(get_args(SecondhandField))

#: Sol's repro, verbatim: two readings of ONE posting that decide opposite ways under the SHIPPED
#: rules. The employer offers sponsorship; the aggregator's 31-character rendering restricts to
#: citizens. Held as literals so the guard states the whole claim it is making.
EMPLOYER_JD = "Visa sponsorship is available."
AGGREGATOR_JD = "Applicants must be US citizens."
#: A profile that needs sponsorship, so both rules DECIDE rather than abstain (the keystone: a
#: rule with no resolvable profile field returns ABSTAIN, which would make this guard vacuous).
NEEDS_SPONSORSHIP = Facts(
    work_authorization=WorkAuthFact(
        status="ead_or_similar", jurisdiction="us", needs_sponsorship=True
    ),
    security_clearance=ClearanceFact(level="none", state="none", obtainable=False),
    total_years_experience=1,
)
BLOCK_ALL = Policy(families={
    "work_auth": "blocker", "clearance": "blocker", "experience_years": "blocker",
    "degree": "blocker", "internship": "blocker", "contract_not_fte": "blocker",
})

# The provider's own reading of the posting, and the aggregator's weaker one of the SAME posting.
# Every field differs, so a column that is not asserted below is a column this file forgot.
PROVIDER = dict(
    provider_posting_id="p1",
    title="Senior Backend Engineer",
    url="https://boards.greenhouse.io/acme/jobs/p1",
    locations=["Remote - US"],
    department="Engineering",
    remote_policy="remote",
    posted_at=datetime(2026, 8, 1, 12, 0),
    updated_at=datetime(2026, 8, 2, 12, 0),
    body_text="The employer's own job description.",
    raw_json={"greenhouse": {"id": "p1"}},
    salary_min=150000.0,
    salary_max=200000.0,
    salary_currency="USD",
    salary_period="year",
)
AGGREGATOR = dict(
    provider_posting_id="p1",
    title="Backend Engineer II",
    url="https://www.indeed.com/viewjob?jk=deadbeef",
    locations=["Austin, TX"],
    body_text="The aggregator's rendering of the same job description.",
    posted_at=datetime(2026, 8, 20, 12, 0),
    raw_json={"job": {"key": "deadbeef"}},
)


@pytest.fixture(scope="module")
def catalog(tmp_path_factory: pytest.TempPathFactory) -> RulesCatalog:
    """The BUNDLED rules, not a fixture catalog. A hand-written pattern would test this guard
    against itself; what has to hold is that the SHIPPED rules decide these two bodies apart."""
    return load_rules(tmp_path_factory.mktemp("no-override"))


@pytest.fixture()
def engine(tmp_path: Path) -> Engine:
    eng = get_engine(tmp_path)
    ensure_schema(eng)
    return eng


@pytest.fixture()
def company_id(engine: Engine) -> int:
    with engine.begin() as conn:
        return int(
            conn.execute(
                insert(tables.companies).values(
                    name="Acme", provider="greenhouse", slug="acme", source="user", watched=True,
                )
            ).inserted_primary_key[0]
        )


def _apply(engine: Engine, company_id: int, raw: RawPosting, *, status: str = "partial") -> None:
    apply_board(
        engine,
        BoardSnapshot(
            status=status,  # type: ignore[arg-type]
            postings=[raw],
            url="https://boards.greenhouse.io/acme",
        ),
        company_id,
        insert_run(engine),
    )


def _posting(engine: Engine) -> Any:
    with engine.connect() as conn:
        return conn.execute(select(tables.postings)).one()


def _age_the_row(engine: Engine) -> datetime:
    """Push the row into the state a missing-then-relisted posting is actually in."""
    stale = datetime(2020, 1, 1, 0, 0)
    with engine.begin() as conn:
        conn.execute(
            update(tables.postings).values(
                last_seen_at=stale, consecutive_missing=1, death_strikes=2
            )
        )
    return stale


def test_a_provider_observation_still_refreshes_every_mutable_column(
    engine: Engine, company_id: int
) -> None:
    """VERDICT-NEUTRALITY. A board scan writes exactly what it wrote before D-414(a).

    The declaration defaults to EMPTY, so nothing on the six-provider path changes. Asserted
    column by column against a second observation in which every value differs.
    """
    _apply(engine, company_id, RawPosting(**PROVIDER))  # type: ignore[arg-type]
    second = dict(PROVIDER) | dict(
        title="Staff Backend Engineer",
        url="https://boards.greenhouse.io/acme/jobs/p1?utm=board",
        locations=["Remote - Canada"],
        department="Platform",
        remote_policy="hybrid",
        posted_at=datetime(2026, 8, 3, 12, 0),
        updated_at=datetime(2026, 8, 4, 12, 0),
        body_text="A revised job description.",
        raw_json={"greenhouse": {"id": "p1", "v": 2}},
        salary_min=160000.0,
        salary_max=210000.0,
        salary_currency="CAD",
        salary_period="month",
    )
    _apply(engine, company_id, RawPosting(**second), status="complete")  # type: ignore[arg-type]

    row = _posting(engine)
    assert row.title == "Staff Backend Engineer"
    assert row.normalized_title == "staff backend engineer"
    assert row.url == "https://boards.greenhouse.io/acme/jobs/p1?utm=board"
    assert row.locations_json == ["Remote - Canada"]
    assert row.remote_policy == "hybrid"
    assert row.department == "Platform"
    assert row.posted_at == datetime(2026, 8, 3, 12, 0)
    assert row.updated_at == datetime(2026, 8, 4, 12, 0)
    assert float(row.salary_min) == 160000.0
    assert float(row.salary_max) == 210000.0
    assert row.salary_currency == "CAD"
    assert row.salary_period == "month"
    assert row.raw_json == {"greenhouse": {"id": "p1", "v": 2}}  # decoded dict, never a string
    assert row.body_text == "A revised job description."
    # The revision branch itself, not just its two columns: an undeclared observation still
    # appends the version and emits the event. The body gate added for D-414(a) sits on this
    # exact branch, so neutrality has to be asserted at the version chain or it is not asserted.
    with engine.connect() as conn:
        versions = conn.execute(
            select(tables.posting_versions.c.capture_reason).order_by(
                tables.posting_versions.c.id
            )
        ).scalars().all()
        events = conn.execute(
            select(tables.posting_events.c.kind).order_by(tables.posting_events.c.id)
        ).scalars().all()
    assert list(versions) == ["new", "revised"]
    assert list(events) == ["new", "revised"]


def test_a_secondhand_observation_keeps_the_provider_reading_of_every_declared_column(
    engine: Engine, company_id: int
) -> None:
    """The defect itself. `Remote - US` must survive a hit that renders it as `Austin, TX`."""
    _apply(engine, company_id, RawPosting(**PROVIDER))  # type: ignore[arg-type]
    _apply(engine, company_id, RawPosting(**AGGREGATOR, secondhand=ALL_SECONDHAND))  # type: ignore[arg-type]

    row = _posting(engine)
    assert row.locations_json == ["Remote - US"]
    assert row.remote_policy == "remote"
    assert row.title == "Senior Backend Engineer"
    assert row.normalized_title == "senior backend engineer"
    assert row.url == "https://boards.greenhouse.io/acme/jobs/p1"
    assert row.department == "Engineering"
    assert row.posted_at == datetime(2026, 8, 1, 12, 0)
    assert row.updated_at == datetime(2026, 8, 2, 12, 0)
    assert float(row.salary_min) == 150000.0
    assert float(row.salary_max) == 200000.0
    assert row.salary_currency == "USD"
    assert row.salary_period == "year"
    assert row.raw_json == {"greenhouse": {"id": "p1"}}


def test_a_secondhand_observation_records_liveness_but_never_restates_the_body(
    engine: Engine, company_id: int
) -> None:
    """The two halves that MUST NOT be conflated, asserted against each other in one guard.

    LIVENESS STILL RESETS. A listing is positive evidence that the posting is alive no matter
    whose text arrived, so `consecutive_missing` and `death_strikes` go to zero and `last_seen_at`
    moves. Without this half, "drop the whole update for a secondhand observation" would satisfy
    the body half while quietly disarming the reset that stops a stale strike closing a posting
    the lane just watched being served.

    THE BODY DOES NOT MOVE. Not the column, not the hash, and -- the part that actually matters --
    not the version chain, because eligibility reads the CURRENT `posting_versions` row and never
    `postings.body_text`. Withholding only the two columns would leave `_insert_version` armed,
    put the aggregator's text at the head of the chain anyway, and additionally leave the posting's
    own hash naming a version that is no longer current. No `revised` EVENT either: an event that
    fires for a revision that did not happen is a lie in the audit trail.
    """
    _apply(engine, company_id, RawPosting(**PROVIDER))  # type: ignore[arg-type]
    stale = _age_the_row(engine)
    before = _posting(engine).content_hash
    _apply(engine, company_id, RawPosting(**AGGREGATOR, secondhand=ALL_SECONDHAND))  # type: ignore[arg-type]

    row = _posting(engine)
    assert row.last_seen_at > stale
    assert row.consecutive_missing == 0
    assert row.death_strikes == 0
    assert row.content_hash == before
    assert row.body_text == "The employer's own job description."
    with engine.connect() as conn:
        versions = conn.execute(
            select(tables.posting_versions.c.capture_reason).order_by(
                tables.posting_versions.c.id
            )
        ).scalars().all()
        current = current_posting_versions(conn, [int(row.id)])[int(row.id)]
        events = conn.execute(
            select(tables.posting_events.c.kind).order_by(tables.posting_events.c.id)
        ).scalars().all()
    assert list(versions) == ["new"]
    assert current.body_text == "The employer's own job description."
    assert list(events) == ["new"]


def test_a_secondhand_body_cannot_turn_an_eligible_posting_ineligible(
    engine: Engine, company_id: int, catalog: RulesCatalog
) -> None:
    """SOL'S REPRO, end to end, through the SHIPPED rules -- the keystone risk in this branch.

    The chain the store makes possible: the employer's JD offers sponsorship and reads `eligible`;
    an aggregator hit converges onto the same `(company_id, provider_posting_id)` carrying a
    31-character rendering that restricts to citizens; `scan/apply.py` makes it the current
    version; the ranker reads the NEW current verdict and hides the posting before its existing
    handled/built disposition is ever consulted.

    `INELIGIBLE` still carried a quoted span from what the store calls the frozen JD, so the
    keystone invariant passed on its face -- and that is exactly why the defect was invisible.
    The span is genuine text; it was cut from the wrong document, so the provenance to the
    employer's posting is false, and CLAUDE.md's invariant is about EVIDENCE.

    The verdict is recomputed from the CURRENT VERSION the store hands back, not from the column
    and not from the RawPosting, because that resolver is the one the eligibility path uses. The
    two arms are asserted in the same test so a rules change that stopped deciding these bodies
    apart shows up as the control failing rather than as a silent pass.
    """
    assert evaluate(EMPLOYER_JD, NEEDS_SPONSORSHIP, BLOCK_ALL, catalog).verdict == "eligible"
    aggregator_alone = evaluate(AGGREGATOR_JD, NEEDS_SPONSORSHIP, BLOCK_ALL, catalog)
    assert aggregator_alone.verdict == "ineligible"  # the CONTROL: the substitution really flips
    # THE SPAN, cut out of the body by the offsets the store would persist. Read through
    # `jd_locator` rather than matched against `requirement_text`, which is the catalog's own
    # label: what makes the defect a keystone failure is that the quote is real TEXT FROM THE
    # DOCUMENT the store called frozen, and only the offsets show that.
    spans = [
        AGGREGATOR_JD[r.jd_locator["span"][0]:r.jd_locator["span"][1]]
        for r in aggregator_alone.requirements
        if r.jd_locator.get("field") == "body_text"
    ]
    assert "must be US citizens" in spans

    _apply(engine, company_id, RawPosting(**{**PROVIDER, "body_text": EMPLOYER_JD}))  # type: ignore[arg-type]
    _apply(  # the converged aggregator hit, declaring what it does not own
        engine, company_id,
        RawPosting(**{**AGGREGATOR, "body_text": AGGREGATOR_JD}, secondhand=ALL_SECONDHAND),  # type: ignore[arg-type]
    )

    row = _posting(engine)
    with engine.connect() as conn:
        current = current_posting_versions(conn, [int(row.id)])[int(row.id)]
    assert current.body_text == EMPLOYER_JD
    verdict = evaluate(current.body_text, NEEDS_SPONSORSHIP, BLOCK_ALL, catalog)
    assert verdict.verdict == "eligible"
    assert not [r for r in verdict.requirements if r.rule_id == "work_auth:us_citizen_required"]


def test_the_insert_path_writes_everything_a_secondhand_observation_carries_but_the_location(
    engine: Engine, company_id: int
) -> None:
    """A row the lane CREATES has no prior observation to preserve -- with ONE exception.

    Everything else stays: dropping the declared columns wholesale would replace values the lane
    genuinely holds with schema defaults -- a loss, not a preservation -- and the body would go
    empty on every posting the lane is the only source for, which is the reach the lane exists to
    buy.

    LOCATION IS THE EXCEPTION because it is the one declared field that both HARD-VETOES and can
    be withheld without making the row unusable, and because the INSERT has no eventual correction
    for a lane-first company (guarded below). `title` and `url` cannot be blanked and leave a
    usable row; `department` / `salary_*` / `posted_at` / `raw_json` move a score or a display
    line and cannot veto.
    """
    _apply(engine, company_id, RawPosting(**AGGREGATOR, secondhand=ALL_SECONDHAND))  # type: ignore[arg-type]

    row = _posting(engine)
    assert row.title == "Backend Engineer II"
    assert row.normalized_title == "backend engineer ii"
    assert row.url == "https://www.indeed.com/viewjob?jk=deadbeef"
    assert row.posted_at == datetime(2026, 8, 20, 12, 0)
    assert row.raw_json == {"job": {"key": "deadbeef"}}
    assert row.body_text == "The aggregator's rendering of the same job description."
    assert row.locations_json == []


def test_a_secondhand_insert_blanks_a_false_non_us_location_the_hard_gate_would_delete(
    engine: Engine, company_id: int
) -> None:
    """FAIL-SAFE DIRECTION, chosen for THIS gate, and asserted through the REAL hard gate.

    The location gate's two failure modes are not symmetric. `hard_filter_verdict` under
    `location_filter_mode = "hard"` DELETES a lead on a CONFIRMED `non_us` location and merely
    declines to filter an `unknown` one, so the INSERT records no location rather than the
    aggregator's -- the direction that cannot delete a real lead.

    Stated honestly, because the earlier version of this test was not: a US metro like `Austin, TX`
    does NOT veto (it classifies `us`, which the gate keeps), and the `remote_only` veto is a
    SEPARATE clause on `remote_policy`. Neither is the hazard. The hazard this blanking removes is a
    FALSE `non_us` -- so the aggregator here indexes a genuinely-remote role as
    `London, United Kingdom`, which classifies `non_us` and WOULD hard-veto.

    Both arms run through the actual gate. WITHOUT the blanking the false location vetoes (deletes)
    the lead; WITH it (`_inserted_fields` stores `[]`, classified `unknown`) the gate keeps it.

    The identity cost is asserted too: with no location evidence `compute_identities` emits neither
    `company_title_location`, `cross_host` nor `exact_quad`, so this row can neither suppress nor be
    suppressed on a place the aggregator assigned. Same direction -- absence of evidence is not
    evidence of sameness.
    """
    _apply(  # a genuinely-remote role the aggregator indexed under a foreign metro
        engine, company_id,
        RawPosting(
            **{**AGGREGATOR, "locations": ["London, United Kingdom"]},
            secondhand=ALL_SECONDHAND,  # type: ignore[arg-type]
        ),
    )

    row = _posting(engine)
    profile = ProfileView(
        skills=frozenset(), target_titles=(), exclude_titles=(), locations=(), remote_only=False
    )
    # CONTROL: the value the aggregator assigned really is a deletion -- a confirmed `non_us` that
    # the REAL hard gate vetoes. Without the blanking below, this is what would decide the lead.
    assert classify_location(["London, United Kingdom"]) == "non_us"
    unblanked = hard_filter_verdict(
        str(row.title), ["London, United Kingdom"], str(row.remote_policy), profile, "hard"
    )
    assert unblanked is not None and unblanked.clause == "non_us_location"
    # WITH the blanking the row carries no location, classifies `unknown`, and the gate KEEPS it.
    assert row.locations_json == []
    assert classify_location(row.locations_json) == "unknown"
    assert (
        hard_filter_verdict(
            str(row.title), row.locations_json, str(row.remote_policy), profile, "hard"
        )
        is None
    )
    with engine.connect() as conn:
        kinds = set(conn.execute(select(tables.posting_identities.c.kind)).scalars().all())
    assert kinds == {"exact_provider", "content_hash_only"}


def test_nothing_ever_scans_the_board_a_lane_first_company_was_filed_under(
    engine: Engine,
) -> None:
    """THE PREMISE the INSERT rule rests on, pinned so it cannot be re-derived wrongly.

    The branch this fixes originally recorded "a later board scan of the same company rewrites it
    as a revision" as the reason the INSERT needed no protection. That holds only when the user
    ALREADY watches the board the hit converged onto. When the lane discovers the company,
    `upsert_lane_company` stores it `watched=False` (D-285, load-bearing), and
    `get_watched_companies` -- the only source of the scan's company rows -- filters
    `watched.is_(True)`. There is no later scan, so the INSERT is the last writer that row will
    ever have.
    """
    with engine.begin() as conn:
        lane_id = upsert_lane_company(conn, provider="greenhouse", slug="lanefirst", name="Acme")
        watched_id = int(
            conn.execute(
                insert(tables.companies).values(
                    name="Watched", provider="greenhouse", slug="watched",
                    source="user", watched=True,
                )
            ).inserted_primary_key[0]
        )
    with engine.connect() as conn:
        scanned = {int(r.id) for r in get_watched_companies(conn)}
    assert watched_id in scanned  # CONTROL: the query does return companies
    assert lane_id not in scanned


def test_a_secondhand_update_keys_the_identity_on_what_the_row_holds(
    engine: Engine, company_id: int
) -> None:
    """An identity naming a value no row holds suppresses against evidence that exists nowhere.

    `write_identities` rewrites a posting's rows on every observation, so the identity has to be
    computed from the persisted title/locations, not from the observation that declined to write
    them.
    """
    _apply(engine, company_id, RawPosting(**PROVIDER))  # type: ignore[arg-type]
    _apply(engine, company_id, RawPosting(**AGGREGATOR, secondhand=ALL_SECONDHAND))  # type: ignore[arg-type]

    row = _posting(engine)
    with engine.connect() as conn:
        stored = {
            r.kind: r.identity_key
            for r in conn.execute(select(tables.posting_identities)).all()
        }

    def expect(title: str, locations: list[str]) -> dict[str, str]:
        return {
            i.kind: i.identity_key
            for i in compute_identities(
                IdentityInputs(
                    posting_id=int(row.id),
                    company_id=company_id,
                    company_name="Acme",
                    provider_posting_id="p1",
                    title=title,
                    locations=locations,
                    content_hash=str(row.content_hash),
                    body_text=str(row.body_text),
                    url=str(row.url),
                    first_seen_at=row.first_seen_at,
                )
            )
        }

    persisted = expect("Senior Backend Engineer", ["Remote - US"])
    observed = expect("Backend Engineer II", ["Austin, TX"])
    assert persisted["company_title_location"] != observed["company_title_location"]
    assert stored == persisted


def test_a_secondhand_update_never_records_an_exact_quad_the_persisted_body_cannot_reproduce(
    engine: Engine, company_id: int
) -> None:
    """Blocker 3 (D-414(a)). The identity BODY comes off the row, not off the observation.

    `exact_quad` is the only SUPPRESSING identity kind, and it folds the body. `_write_posting_identity`
    used to read `raw.body_text`; on a secondhand UPDATE that lets the aggregator's text decide a
    suppression key the persisted row cannot reproduce.

    The provider's own INSERT here carries a real location but an EMPTY body — a stub the board
    listed without a description, which `content_hash` folds to the SHA-256 of the empty string.
    The converged aggregator hit then arrives with a NON-empty body it does not own. Because
    `body_evidence("")` is None, the persisted row emits no `exact_quad`; reading the aggregator's
    body instead would emit one keyed on the empty-body hash, a claim `identities verify` would
    read as stale and no recomputation from the row could confirm.

    Asserted as the recorded kinds being EXACTLY what recomputation from the persisted row yields,
    with `exact_quad`'s absence pinned on its own so the guard names the member it protects.
    """
    _apply(engine, company_id, RawPosting(**{**PROVIDER, "body_text": ""}))  # type: ignore[arg-type]
    _apply(  # the converged aggregator hit carrying a body the provider row never held
        engine, company_id,
        RawPosting(
            **{**AGGREGATOR, "body_text": "Real aggregator text the provider row never held."},
            secondhand=ALL_SECONDHAND,  # type: ignore[arg-type]
        ),
    )

    row = _posting(engine)
    assert row.body_text == ""  # the empty provider body survived the secondhand update
    assert row.locations_json == ["Remote - US"]  # provider location survived => location-bearing
    with engine.connect() as conn:
        stored = {
            r.kind: r.identity_key
            for r in conn.execute(select(tables.posting_identities)).all()
        }
    expected = {
        i.kind: i.identity_key
        for i in compute_identities(
            IdentityInputs(
                posting_id=int(row.id),
                company_id=company_id,
                company_name="Acme",
                provider_posting_id="p1",
                title=str(row.title),
                locations=list(row.locations_json),
                content_hash=str(row.content_hash),
                body_text=str(row.body_text),
                url=str(row.url),
                first_seen_at=row.first_seen_at,
            )
        )
    }
    # The row itself yields no `exact_quad`: an empty body is the absence of evidence, not evidence
    # of sameness. The CONTROL that this is not vacuous is `company_title_location`/`cross_host`
    # still being present — the location-bearing kinds prove identities were written at all.
    assert "exact_quad" not in expected
    assert "company_title_location" in stored
    assert stored == expected  # no body-bearing identity the persisted row cannot reproduce


def test_an_undeclared_observation_inserts_exactly_what_it_always_did(
    engine: Engine, company_id: int
) -> None:
    """VERDICT-NEUTRALITY for the INSERT half. Every provider board scan goes through here.

    Asserted as an equality between the two writers rather than column by column: what has to
    hold is that `_inserted_fields` IS `_mutable_fields` for an undeclared observation, whatever
    either one grows next. The end-to-end row is checked too, so the equality cannot pass while
    the caller stops using the result.
    """
    raw = RawPosting(**PROVIDER)  # type: ignore[arg-type]
    now = datetime(2026, 9, 1)
    assert _inserted_fields(raw, now) == _mutable_fields(raw, now)

    _apply(engine, company_id, raw)
    row = _posting(engine)
    assert row.locations_json == ["Remote - US"]
    assert row.body_text == "The employer's own job description."


def test_a_stored_identity_does_not_depend_on_the_url(engine: Engine, company_id: int) -> None:
    """The measurement that justifies NOT passing the row's URL into the identity write.

    A review round claimed the stored URL had to be threaded through for identity correctness.
    It does not: `compute_identities` reads company / provider_posting_id / title / locations /
    content_hash / body_text / company_name and never touches `IdentityInputs.url`, so the two
    URLs a secondhand update chooses between produce byte-identical identities. URL ranks
    survivors in `core.dedup` only, off a separate loader that reads the COLUMN back after the
    fact. A parameter that cannot change an output is not a safeguard.
    """
    def identities(url: str | None) -> dict[str, str]:
        return {
            i.kind: i.identity_key
            for i in compute_identities(
                IdentityInputs(
                    posting_id=1, company_id=company_id, company_name="Acme",
                    provider_posting_id="p1", title="Senior Backend Engineer",
                    locations=["Remote - US"], content_hash="deadbeef",
                    body_text="The employer's own job description.", url=url,
                    first_seen_at=datetime(2026, 8, 1),
                )
            )
        }

    provider_url = identities("https://boards.greenhouse.io/acme/jobs/p1")
    assert provider_url  # CONTROL: identities are emitted at all
    assert provider_url == identities("https://www.indeed.com/viewjob?jk=deadbeef")
    assert provider_url == identities(None)


def test_every_column_the_writer_refreshes_is_classified_exactly_once(
    engine: Engine, company_id: int
) -> None:
    """A column added to `_mutable_fields` must be declarable, or it is silently unprotected.

    The literal below is the contract, restated here rather than read back off the writer: an
    assertion of `_mutable_fields` against itself passes however the writer changes.
    """
    written = set(_mutable_fields(RawPosting(**PROVIDER), datetime(2026, 9, 1)))  # type: ignore[arg-type]
    assert written == {
        "title", "normalized_title", "url", "locations_json", "remote_policy", "department",
        "posted_at", "updated_at", "salary_min", "salary_max", "salary_currency",
        "salary_period", "raw_json", "last_seen_at",
    }
    assert set(_SECONDHAND_COLUMNS) == set(get_args(SecondhandField))
    classified = [column for columns in _SECONDHAND_COLUMNS.values() for column in columns]
    assert len(classified) == len(set(classified))  # no column owned by two declarations
    # `last_seen_at` is the one exclusion, and it is deliberate: it is the observation's OWN
    # claim, never the provider's, so no declaration may withhold it.
    assert set(classified) == written - {"last_seen_at"}


def test_body_text_is_declarable_but_owns_no_mutable_column() -> None:
    """The one empty entry in the map, asserted rather than left to be noticed.

    `content_hash` and `body_text` are not `_mutable_fields` columns -- `_apply_listed` writes
    them inside the revision branch together with the immutable `posting_versions` row and the
    `revised` event, and all four are withheld or none are. So the declaration is honoured at
    that branch's own condition and there is nothing for the map to drop. Pinned here so a
    future reader cannot read the empty tuple as an oversight and "fix" it into a `del` that
    KeyErrors on every secondhand update.
    """
    assert "body_text" in get_args(SecondhandField)
    assert _SECONDHAND_COLUMNS["body_text"] == ()
    assert "body_text" not in _mutable_fields(RawPosting(**PROVIDER), datetime(2026, 9, 1))  # type: ignore[arg-type]
    assert "content_hash" not in _mutable_fields(RawPosting(**PROVIDER), datetime(2026, 9, 1))  # type: ignore[arg-type]

"""D-654: a posting is held when the same EMPLOYER REQUISITION was delivered, applied to, or is on
this slate already.

**The shape.** On 2026-10-30 a manual triage removed 11 duplicates, and 7 of them were one
requisition reached a second way: a job-apps or Indeed copy carrying the employer's own URL under a
differently spelled company ("Amazon" / "Amazon.com"), or one Oracle requisition published on two
career sites. `cross_host` keys on the company name, title and location, so it missed every one.
The requisition is in the URL.

**What these tests pin.** WHICH row survives, never only a count; that the company, title and
location may all differ and the rule still fires; that a delivered holder releases when it is
reported or closed while an applied one holds; that a held row is not recorded `seen` and its slot
refills; that a URL nothing can read is never held; and that the shortlist identity still adds up.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import Engine, insert, select, update

from boardwatch.cli.top_cmd import RankedResults, rank_open_postings
from boardwatch.core.clock import utcnow
from boardwatch.core.settings import Settings
from boardwatch.lanes.dereference import requisition_key
from boardwatch.store.applications import mark_job_applied
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.ledger_queries import record_disposition
from boardwatch.store.queries import save_profile
from boardwatch.store.queue_state import mark_job_reported
from boardwatch.store.tables import (
    artifacts,
    companies,
    job_dispositions,
    jobs,
    posting_versions,
    postings,
)

NOW = utcnow()

WD = (
    "https://statestreet.wd1.myworkdayjobs.com/{site}/job/Burlington-Massachusetts/"
    "SW-Engineer-I_{req}"
)
AMAZON = "https://www.amazon.jobs/en/jobs/{req}/software-development-engineer"
ORACLE = "https://eeho.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/{site}/job/{req}"

# (company slug, provider, title, url). Every row a distinct company, title and location, so no
# grouping by name, title or place can be what fires.
Row = tuple[str, str, str, str]


def _seed(data_dir: Path, rows: Sequence[Row]) -> tuple[Engine, list[int]]:
    """One open posting per row, `posted_at` descending, so row order is rank order."""
    engine = get_engine(data_dir)
    ensure_schema(engine)
    ids: list[int] = []
    with engine.begin() as conn:
        save_profile(
            conn, text="Backend engineer.", target_titles=[], exclude_titles=[],
            locations=[], remote_only=False, skills=[], taxonomy_version="t",
            resume_max_pages=1,
        )
        for offset, (slug, provider, title, url) in enumerate(rows):
            company_id = int(conn.execute(insert(companies).values(
                name=slug.replace("-", " ").title(), provider=provider, slug=slug,
                source="user", watched=True,
            )).inserted_primary_key[0])
            job_id = int(conn.execute(insert(jobs).values(created_at=NOW)).inserted_primary_key[0])
            body = f"JD {offset}. " + "detail " * (offset + 1)
            posting_id = int(conn.execute(insert(postings).values(
                company_id=company_id, job_id=job_id, provider_posting_id=f"pp-{offset}",
                title=title, normalized_title=title.lower(), url=url,
                locations_json=[f"City {offset}, TX"], remote_policy="onsite",
                posted_at=NOW - timedelta(days=offset), first_seen_at=NOW, last_seen_at=NOW,
                status="open", consecutive_missing=0, content_hash=f"hash-{offset}",
                body_text=body,
            )).inserted_primary_key[0])
            conn.execute(insert(posting_versions).values(
                posting_id=posting_id, content_hash=f"hash-{offset}", body_text=body,
                captured_at=NOW, capture_reason="new",
            ))
            ids.append(posting_id)
    return engine, ids


def _rank(engine: Engine, data_dir: Path, *, limit: int = 10) -> RankedResults:
    return rank_open_postings(
        engine, Settings(data_dir=data_dir, config_dir=data_dir), limit=limit
    )


def _delivered(engine: Engine, posting_id: int) -> int:
    """Put `posting_id` in the queue the way an earlier run leaves it: an artifact, and the `built`
    disposition that stops it ranking again (so only the seed can be what holds its twin)."""
    with engine.begin() as conn:
        version_id = int(conn.execute(
            select(posting_versions.c.id).where(posting_versions.c.posting_id == posting_id)
        ).scalar_one())
        conn.execute(insert(artifacts).values(
            posting_version_id=version_id, kind="resume_tailored",
            uri=f"/out/{posting_id}.typ", generator="boardwatch.tailor",
            media_type="text/x-typst", meta_json={}, created_at=NOW, run_id=None,
        ))
        job_id = int(conn.execute(
            select(postings.c.job_id).where(postings.c.id == posting_id)
        ).scalar_one())
        record_disposition(
            conn, job_id, disposition="built", reason="lead_built", policy_version="v1", now=NOW,
        )
        return job_id


def _visible(results: RankedResults) -> list[int]:
    return [p.posting_id for p in results.visible]


@pytest.fixture()
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    return tmp_path / "data"


# ------------------------------------------------------------------------ the key itself


def test_one_workday_requisition_on_two_sites_and_two_spellings_is_one_key() -> None:
    assert requisition_key(WD.format(site="Global", req="R-785495")) == requisition_key(
        WD.format(site="global", req="R-785495")
    )
    assert requisition_key(WD.format(site="Global", req="R-785495")) != requisition_key(
        WD.format(site="Global", req="R-785496")
    )


def test_one_oracle_requisition_on_two_career_sites_is_one_key() -> None:
    assert requisition_key(ORACLE.format(site="CX_1", req="341917")) == requisition_key(
        ORACLE.format(site="CX_45001", req="341917")
    )


def test_the_same_requisition_number_at_two_employers_is_two_keys() -> None:
    other_tenant = WD.format(site="Global", req="R-785495").replace("statestreet", "acme")
    assert requisition_key(other_tenant) != requisition_key(
        WD.format(site="Global", req="R-785495")
    )


@pytest.mark.parametrize(
    ("a", "b"),
    [
        (AMAZON.format(req="10530257"), "https://www.amazon.jobs/jobs/10530257/x?cmpid=DA"),
        (
            "https://jobs.ashbyhq.com/agave/73bd2c98-bf87-4eaa-aea8-35e7b6131d0e",
            "https://jobs.ashbyhq.com/agave/73bd2c98-bf87-4eaa-aea8-35e7b6131d0e/application?x=1",
        ),
        (
            "https://jobs.lever.co/acme/0f1e2d3c-4b5a-6978-8a9b-0c1d2e3f4a5b",
            "https://jobs.lever.co/acme/0f1e2d3c-4b5a-6978-8a9b-0c1d2e3f4a5b/apply",
        ),
    ],
)
def test_an_amazon_id_and_an_apply_form_tail_read_as_their_requisition(a: str, b: str) -> None:
    assert requisition_key(a) is not None
    assert requisition_key(a) == requisition_key(b)


@pytest.mark.parametrize(
    "url",
    [
        "https://www.linkedin.com/jobs/view/4458214586",
        "https://jobright.ai/jobs/info/abc123",
        "https://www.indeed.com/viewjob?jk=959e782d161315be",
        "https://jobs.ashbyhq.com/agave",
        "https://www.amazon.jobs/en/search?base_query=engineer",
    ],
)
def test_a_url_naming_no_requisition_has_no_key(url: str) -> None:
    assert requisition_key(url) is None


# ------------------------------------------------------------------------ the rule


def test_a_copy_of_a_DELIVERED_requisition_is_held_and_the_rest_survive(  # noqa: N802
    data_dir: Path,
) -> None:
    """The copy is seeded FIRST, so it outranks everything: only the rule can be what holds it."""
    engine, (copy, delivered, other) = _seed(data_dir, [
        ("state-street", "jobapps", "SW Engineer I – Full Stack",
         WD.format(site="global", req="R-785495")),
        ("statestreet", "workday", "Software Engineer I, Officer",
         WD.format(site="Global", req="R-785495")),
        ("beta", "greenhouse", "Backend Engineer", "https://boards.greenhouse.io/beta/jobs/111111"),
    ])
    _delivered(engine, delivered)

    results = _rank(engine, data_dir)

    assert _visible(results) == [other]
    assert results.hidden_requisition_twin == 1
    assert copy not in _visible(results)


def test_a_different_requisition_at_the_same_employer_is_not_held(data_dir: Path) -> None:
    """The null control for the test above: everything the same but the requisition number."""
    engine, (copy, delivered, other) = _seed(data_dir, [
        ("state-street", "jobapps", "SW Engineer I – Full Stack",
         WD.format(site="global", req="R-785496")),
        ("statestreet", "workday", "Software Engineer I, Officer",
         WD.format(site="Global", req="R-785495")),
        ("beta", "greenhouse", "Backend Engineer", "https://boards.greenhouse.io/beta/jobs/111111"),
    ])
    _delivered(engine, delivered)

    results = _rank(engine, data_dir)

    assert _visible(results) == [copy, other]
    assert results.hidden_requisition_twin == 0


def test_an_APPLIED_requisition_holds_its_copy(data_dir: Path) -> None:  # noqa: N802
    engine, (copy, applied, other) = _seed(data_dir, [
        ("amazon-com", "indeed", "SDE, Robotics, Early Career", AMAZON.format(req="10567489")),
        ("software-development", "amazon", "Software Development Engineer",
         AMAZON.format(req="10567489")),
        ("beta", "greenhouse", "Backend Engineer", "https://boards.greenhouse.io/beta/jobs/111111"),
    ])
    with engine.begin() as conn:
        mark_job_applied(conn, posting_id=applied, source="test")

    results = _rank(engine, data_dir)

    assert _visible(results) == [other]
    assert results.hidden_requisition_twin == 1


def test_two_copies_on_one_slate_keep_the_higher_ranked_and_the_slot_refills(
    data_dir: Path,
) -> None:
    """Oracle 341917 on two career sites. At a limit of two, the held copy's slot goes to the next
    row down rather than being left empty."""
    engine, (first, second, refill) = _seed(data_dir, [
        ("eeho-cx45001", "oraclehcm", "Building Automation Engineer",
         ORACLE.format(site="CX_45001", req="341917")),
        ("eeho-cx1", "oraclehcm", "Building Automation Eng.",
         ORACLE.format(site="CX_1", req="341917")),
        ("beta", "greenhouse", "Backend Engineer", "https://boards.greenhouse.io/beta/jobs/111111"),
    ])

    results = _rank(engine, data_dir, limit=2)

    assert _visible(results) == [first, refill]
    assert results.hidden_requisition_twin == 1
    assert second not in _visible(results)


def test_a_REPORTED_holder_releases_its_twin(data_dir: Path) -> None:  # noqa: N802
    engine, (copy, delivered) = _seed(data_dir, [
        ("state-street", "jobapps", "SW Engineer I", WD.format(site="global", req="R-785495")),
        ("statestreet", "workday", "Software Engineer I", WD.format(site="Global", req="R-785495")),
    ])
    job = _delivered(engine, delivered)
    with engine.begin() as conn:
        mark_job_reported(conn, job_id=job, at=NOW)

    results = _rank(engine, data_dir)

    assert _visible(results) == [copy]
    assert results.hidden_requisition_twin == 0


def test_a_CLOSED_holder_releases_its_twin(data_dir: Path) -> None:  # noqa: N802
    engine, (copy, delivered) = _seed(data_dir, [
        ("state-street", "jobapps", "SW Engineer I", WD.format(site="global", req="R-785495")),
        ("statestreet", "workday", "Software Engineer I", WD.format(site="Global", req="R-785495")),
    ])
    _delivered(engine, delivered)
    with engine.begin() as conn:
        conn.execute(update(postings).where(postings.c.id == delivered).values(status="closed"))

    results = _rank(engine, data_dir)

    assert _visible(results) == [copy]


def test_urls_naming_no_requisition_are_never_held(data_dir: Path) -> None:
    """Two LinkedIn rows for one job read nothing: no key, so the rule cannot fire."""
    engine, (a, delivered) = _seed(data_dir, [
        ("acme", "linkedin", "Backend Engineer", "https://www.linkedin.com/jobs/view/4458214586"),
        ("acme-corp", "linkedin", "Backend Engineer",
         "https://www.linkedin.com/jobs/view/4458214586"),
    ])
    _delivered(engine, delivered)

    assert _visible(_rank(engine, data_dir)) == [a]


def test_a_held_row_is_not_recorded_seen(data_dir: Path) -> None:
    """A `seen` row would keep it out after its holder is reported, closing the drain."""
    engine, (copy, delivered) = _seed(data_dir, [
        ("state-street", "jobapps", "SW Engineer I", WD.format(site="global", req="R-785495")),
        ("statestreet", "workday", "Software Engineer I", WD.format(site="Global", req="R-785495")),
    ])
    _delivered(engine, delivered)
    rank_open_postings(
        engine, Settings(data_dir=data_dir, config_dir=data_dir), limit=10, record_surfaced=True
    )
    with engine.connect() as conn:
        copy_job = conn.execute(
            select(postings.c.job_id).where(postings.c.id == copy)
        ).scalar_one()
        seen = conn.execute(
            select(job_dispositions.c.job_id).where(
                job_dispositions.c.job_id == copy_job, job_dispositions.c.disposition == "seen"
            )
        ).all()
    assert seen == []


def test_the_shortlist_identity_still_adds_up(data_dir: Path) -> None:
    engine, (_, delivered, _, _) = _seed(data_dir, [
        ("state-street", "jobapps", "SW Engineer I", WD.format(site="global", req="R-785495")),
        ("statestreet", "workday", "Software Engineer I", WD.format(site="Global", req="R-785495")),
        ("eeho-cx45001", "oraclehcm", "Building Automation Engineer",
         ORACLE.format(site="CX_45001", req="341917")),
        ("eeho-cx1", "oraclehcm", "Building Automation Eng.",
         ORACLE.format(site="CX_1", req="341917")),
    ])
    _delivered(engine, delivered)

    r = _rank(engine, data_dir, limit=10)

    assert r.hidden_requisition_twin == 2
    assert r.considered == (
        len(r.visible) + r.skipped_not_new + r.hidden_hard_filter + r.hidden_non_swe
        + r.hidden_zero_signal + r.hidden_over_seniority + r.hidden_ineligible
        + r.hidden_duplicate + r.hidden_applied + r.hidden_handled + r.hidden_slate_cap
        + r.hidden_cluster_cap + r.hidden_lane_copy + r.hidden_requisition_twin
        + r.hidden_below_cutoff
    )


def _artifact_only(engine: Engine, posting_id: int) -> None:
    """Delivered with no disposition, so the row still ranks: a lead whose `seen` aged out."""
    with engine.begin() as conn:
        version_id = int(conn.execute(
            select(posting_versions.c.id).where(posting_versions.c.posting_id == posting_id)
        ).scalar_one())
        conn.execute(insert(artifacts).values(
            posting_version_id=version_id, kind="resume_tailored",
            uri=f"/out/{posting_id}.typ", generator="boardwatch.tailor",
            media_type="text/x-typst", meta_json={}, created_at=NOW, run_id=None,
        ))


def test_two_delivered_copies_never_hold_each_other(data_dir: Path) -> None:
    """Both were delivered and both still rank. Each is the other's holder, so without the guard
    both would vanish and the owner would lose the job."""
    engine, (a, b) = _seed(data_dir, [
        ("state-street", "jobapps", "SW Engineer I", WD.format(site="global", req="R-785495")),
        ("statestreet", "workday", "Software Engineer I", WD.format(site="Global", req="R-785495")),
    ])
    _artifact_only(engine, a)
    _artifact_only(engine, b)

    results = _rank(engine, data_dir)

    assert _visible(results) == [a, b]
    assert results.hidden_requisition_twin == 0


def test_a_smartrecruiters_id_keys_and_a_uuid_prefix_does_not() -> None:
    """The numeric prefix of a UUID's first group is shared by unrelated jobs, so it is no key."""
    real = "https://jobs.smartrecruiters.com/ServiceNow/744000153279380-software-engineer"
    assert requisition_key(real) == ("smartrecruiters", "servicenow", "744000153279380")
    for uuid in ("12345678-1234-4234-8234-123456789abc", "12345678-abcd-4abc-8abc-abcdefabcdef"):
        assert requisition_key(f"https://jobs.smartrecruiters.com/servicenow/{uuid}") is None


@pytest.mark.parametrize("url", ["https://[broken/jobs/1", "https://[broken/jobs/1/apply"])
def test_a_url_urlparse_cannot_read_has_no_key(url: str) -> None:
    assert requisition_key(url) is None


def test_a_malformed_url_on_the_slate_or_in_the_seed_does_not_stop_the_ranking(
    data_dir: Path,
) -> None:
    engine, (broken, delivered, other) = _seed(data_dir, [
        ("simplify", "jobapps", "Backend Engineer", "https://[broken/jobs/1"),
        ("simplify-2", "jobapps", "Data Engineer", "https://[broken/jobs/2/apply"),
        ("beta", "greenhouse", "Platform Engineer", "https://boards.greenhouse.io/beta/jobs/111111"),
    ])
    _delivered(engine, delivered)

    assert _visible(_rank(engine, data_dir)) == [broken, other]


def test_an_attempt_never_submitted_does_not_hold_its_requisition(data_dir: Path) -> None:
    """`track add` makes an `interested` attempt; nothing was applied, so it holds nothing.

    The two rows still share a requisition, so the slate keeps one: the higher-ranked copy. Had the
    unsubmitted attempt held its requisition, the copy would be the row held instead."""
    from boardwatch.store.applications import create_application  # noqa: PLC0415

    engine, (copy, interested) = _seed(data_dir, [
        ("amazon-com", "indeed", "SDE, Robotics, Early Career", AMAZON.format(req="10567489")),
        ("software-development", "amazon", "Software Development Engineer",
         AMAZON.format(req="10567489")),
    ])
    with engine.begin() as conn:
        job = conn.execute(
            select(postings.c.job_id).where(postings.c.id == interested)
        ).scalar_one()
        create_application(conn, job_id=job)

    results = _rank(engine, data_dir)

    assert _visible(results) == [copy]
    assert results.hidden_requisition_twin == 1


@pytest.mark.parametrize("enriched", ["candidate", "delivered", "applied"])
def test_resolved_jobright_candidate_and_holders_use_employer_evidence(
    data_dir: Path, enriched: str,
) -> None:
    """Reading only postings.url misses either side of a jobright requisition match."""
    url = WD.format(site="Global", req="R-785495")
    jobright = "https://jobright.ai/jobs/info/6a95ed6fcabc9f6703e1b085"
    engine, (copy, holder) = _seed(data_dir, [
        ("copy", "jobapps", "SW Engineer I", jobright if enriched == "candidate" else url),
        ("holder", "jobapps", "Software Engineer", url if enriched == "candidate" else jobright),
    ])
    evidenced = copy if enriched == "candidate" else holder
    with engine.begin() as conn:
        conn.execute(update(postings).where(postings.c.id == evidenced).values(
            raw_json={"jobapps": {"employer_url": url}},
        ))
        if enriched == "applied":
            mark_job_applied(conn, posting_id=holder, source="test")
    if enriched != "applied":
        _delivered(engine, holder)
    assert _visible(_rank(engine, data_dir)) == []
    # Bad evidence falls back to the stored employer URL. No title/company inference.
    with engine.begin() as conn:
        conn.execute(update(postings).where(postings.c.id == evidenced).values(url=url))
    for invalid in ("https://[broken/", "https://unknown.invalid/no-key", None, 7, {}):
        with engine.begin() as conn:
            conn.execute(update(postings).where(postings.c.id == evidenced).values(
                raw_json={"jobapps": {"employer_url": invalid}},
            ))
        assert _visible(_rank(engine, data_dir)) == []

"""The lane-body precondition at EVERY eligibility seam, not just the deterministic preflight.

The first version of this change guarded `eligibility/preflight.py` alone and claimed the harm
was therefore unreachable. It was not. A quarantined posting stays VISIBLE by design — the
quarantine withholds a verdict, it does not hide a job — so the ranked shortlist still carries
it, `gate request` still hands its foreign body to the judge, and `gate apply` still persists an
ineligible-capable verdict with a span cut out of that body. A judge reading jobright's own
`H1B Sponsor Likely` label returns exactly `ineligible(work_auth)` citing it, which is the
third-party-attributed INELIGIBLE the keystone forbids and the one failure the evidence chain
cannot detect after the fact.

Three seams, three guards: the SEND boundary (`build_gate_request`), the WRITE boundary
(`apply_gate_verdicts` -> `record_gate_verdict`), and advisory extraction
(`extract_llm.extract_and_record`), which walks every current open body of its own accord.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import Engine, insert, select

from boardwatch.eligibility.catalog import load_rules
from boardwatch.eligibility.extract_llm import extract_and_record
from boardwatch.eligibility.facts import Facts, Policy
from boardwatch.eligibility.gate_handshake import apply_gate_verdicts, build_gate_request
from boardwatch.eligibility.oracle import OracleVerdict
from boardwatch.store import tables
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.queries import CurrentVersion
from tests.unit.test_lane_body_precondition import JOBRIGHT_PAGE

CLEAN_BODY = """About the role
We are hiring a backend engineer to build payment services.
Responsibilities
Design and ship APIs used by every internal team.
Requirements
Strong Python. Experience operating production systems.
"""

_T0 = datetime(2026, 1, 1)

# The judge's answer to jobright's page, reproduced from the review that found this hole: it
# reads jobright's OWN derived label and returns it as the employer's requirement.
JOBRIGHT_JUDGE_VERDICT = OracleVerdict(
    label="1",
    decision="ineligible",
    reason="work_auth",
    evidence="H1B Sponsor Likely",
    confidence="high",
)


class _Ranked:
    def __init__(self, posting_id: int) -> None:
        self.posting_id = posting_id


@pytest.fixture()
def engine(tmp_path: Path) -> Engine:
    eng = get_engine(tmp_path / "data")
    ensure_schema(eng)
    with eng.begin() as conn:
        conn.execute(
            insert(tables.companies).values(
                name="Acme", provider="greenhouse", slug="acme", source="user", watched=True
            )
        )
    return eng


def _seed(engine: Engine, pid: str, body: str) -> CurrentVersion:
    with engine.begin() as conn:
        job_id = int(
            conn.execute(insert(tables.jobs).values(created_at=_T0)).inserted_primary_key[0]
        )
        posting_id = int(
            conn.execute(
                insert(tables.postings).values(
                    company_id=1, job_id=job_id, provider_posting_id=pid,
                    title="Backend Engineer", normalized_title="backend engineer",
                    url="https://example.test/j", locations_json=["Remote"],
                    remote_policy="remote", first_seen_at=_T0, last_seen_at=_T0, status="open",
                    consecutive_missing=0, content_hash=f"h-{pid}", body_text=body,
                )
            ).inserted_primary_key[0]
        )
        version_id = int(
            conn.execute(
                insert(tables.posting_versions).values(
                    posting_id=posting_id, content_hash=f"h-{pid}", body_text=body,
                    captured_at=_T0, capture_reason="new",
                )
            ).inserted_primary_key[0]
        )
    return CurrentVersion(
        posting_version_id=version_id, posting_id=posting_id, body_text=body, captured_at=_T0
    )


def _catalog(tmp_path: Path):
    return load_rules(tmp_path / "no-override")


def _evaluations(engine: Engine) -> list[tuple[str, str]]:
    with engine.connect() as conn:
        return [
            (str(r.engine_kind), str(r.verdict))
            for r in conn.execute(
                select(
                    tables.eligibility_evaluations.c.engine_kind,
                    tables.eligibility_evaluations.c.verdict,
                )
            ).all()
        ]


def _live_quarantine(engine: Engine) -> dict[int, list[str]]:
    with engine.connect() as conn:
        return {
            int(r.posting_version_id): list(r.markers_json)
            for r in conn.execute(select(tables.quarantined_bodies)).all()
            if r.reopened_at is None
        }


def test_the_send_boundary_never_hands_a_foreign_body_to_the_judge(
    engine: Engine, tmp_path: Path
) -> None:
    foreign = _seed(engine, "foreign", JOBRIGHT_PAGE)
    clean = _seed(engine, "clean", CLEAN_BODY)
    versions = {foreign.posting_id: foreign, clean.posting_id: clean}

    request = build_gate_request(
        [_Ranked(foreign.posting_id), _Ranked(clean.posting_id)],
        versions,
        Facts(),
        _catalog(tmp_path),
        request_id="r1",
    )

    labels = [item["label"] for item in request["items"]]
    assert labels == [str(clean.posting_id)]
    bodies = " ".join(str(item) for item in request["items"])
    assert "H1B Sponsor Likely" not in bodies
    assert "Jobright" not in bodies


def test_the_write_boundary_refuses_a_hand_authored_verdict_for_a_foreign_body(
    engine: Engine, tmp_path: Path
) -> None:
    """`gate apply` reads a FILE. It must refuse even when `gate request` never ran — which is
    the case the send-boundary guard alone cannot cover."""
    foreign = _seed(engine, "foreign", JOBRIGHT_PAGE)
    verdict = OracleVerdict(
        label=str(foreign.posting_id), decision="ineligible", reason="work_auth",
        evidence="H1B Sponsor Likely", confidence="high",
    )

    with engine.begin() as conn:
        result = apply_gate_verdicts(
            conn, [verdict], versions={foreign.posting_id: foreign},
            facts=Facts(), policy=Policy(families={"work_auth": "blocker"}),
            catalog=_catalog(tmp_path),
        )

    assert result.judged == 0
    assert result.ineligible == 0
    assert result.demoted_labels == ()
    assert _evaluations(engine) == [], "no verdict may be persisted from a foreign body"
    assert foreign.posting_version_id in _live_quarantine(engine)


def test_the_write_boundary_still_persists_a_verdict_for_an_employer_body(
    engine: Engine, tmp_path: Path
) -> None:
    """The guard must not eat the corpus: the same call on a real employer body still writes."""
    clean = _seed(engine, "clean", CLEAN_BODY)
    verdict = OracleVerdict(
        label=str(clean.posting_id), decision="eligible", reason=None,
        evidence="", confidence="high",
    )
    with engine.begin() as conn:
        result = apply_gate_verdicts(
            conn, [verdict], versions={clean.posting_id: clean},
            facts=Facts(), policy=Policy(families={}), catalog=_catalog(tmp_path),
        )
    assert result.judged == 1
    assert len(_evaluations(engine)) == 1
    assert _live_quarantine(engine) == {}


def test_advisory_extraction_neither_calls_the_provider_nor_records_for_a_foreign_body(
    engine: Engine, tmp_path: Path
) -> None:
    foreign = _seed(engine, "foreign", JOBRIGHT_PAGE)

    class _ExplodingClient:
        def complete(self, *args: object, **kwargs: object) -> str:
            raise AssertionError("a foreign body was sent to the provider")

    class _Cache:
        def get(self, key: str) -> str | None:
            return None

        def put(self, key: str, value: str) -> None:
            raise AssertionError("a foreign body reached the response cache")

    with engine.begin() as conn:
        evaluation_id = extract_and_record(
            conn,
            posting_version_id=foreign.posting_version_id,
            jd_text=foreign.body_text,
            facts=Facts(),
            policy=Policy(families={}),
            catalog=_catalog(tmp_path),
            client=_ExplodingClient(),  # type: ignore[arg-type]
            cache=_Cache(),  # type: ignore[arg-type]
        )

    assert evaluation_id is None
    assert _evaluations(engine) == []
    assert foreign.posting_version_id in _live_quarantine(engine)

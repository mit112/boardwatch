"""The loopback review server, driven over a real socket on 127.0.0.1.

**Every test here goes over TCP, through `http.client`, and never calls a handler method.** Half of
what this module is responsible for IS the envelope — the status code, the `WWW-Authenticate`-less
401, the CSP header, the `Content-Disposition` — and none of that exists when a handler method is
called directly. `http.client` rather than `urllib` for one specific reason: it lets a test set the
`Host` header itself, which is the only way to exercise the DNS-rebinding defence.

**The store is a fresh one on `tmp_path` for every test.** `BOARDWATCH_DATA_DIR` and
`BOARDWATCH_CONFIG_DIR` are both redirected, because the payload path resolves the eligibility
identity and the taxonomy through `load_settings()`; without the config redirect, a developer's own
`rules.yaml` override would decide the verdict assertions. The live store is never opened.

**Every refusal test carries the request that should SUCCEED.** A server that answered 401 to
everything would pass "no token is 401", "a wrong token is 401" and "a query-string token is 401"
simultaneously, and a `403` on every request would pass the Host test — so each of those asserts
the paired 200 in the same test rather than in a neighbour that could be deleted on its own. The
same rule applies to the traversal test, which asserts both that the outside-the-root path is
refused AND that a path inside the root serves those exact bytes.
"""

from __future__ import annotations

import http.client
import json
import os
import re
import sqlite3
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Connection, Engine, func, insert, select, update

from boardwatch.core.settings import load_settings
from boardwatch.delivery import server as server_mod
from boardwatch.delivery.api import ApiContext
from boardwatch.delivery.server import (
    CONTENT_SECURITY_POLICY,
    TOKEN_FILENAME,
    WRITE_BUSY_TIMEOUT_MS,
    BundleMissingError,
    NonLoopbackBindError,
    ReviewServer,
    build_server,
    load_or_create_token,
    static_root,
)
from boardwatch.eligibility.catalog import load_rules
from boardwatch.eligibility.engine import evaluate, write_evaluation
from boardwatch.eligibility.facts import Facts, Policy, WorkAuthFact, facts_payload
from boardwatch.eligibility.hashing import build_identity
from boardwatch.eligibility.resolve import declared_fields
from boardwatch.store.db import DB_FILENAME, ensure_schema, get_engine
from boardwatch.store.queries import save_eligibility, save_profile
from boardwatch.store.tables import (
    application_events,
    applications,
    artifacts,
    companies,
    jobs,
    posting_versions,
    postings,
    runs,
)
from boardwatch.tailor.load import scaffold_template

NOW = datetime(2026, 8, 26, 12, 0, 0)

# Empirically pinned against the bundled catalog under `Facts()` / `Policy()`: a `preferred`
# degree row can never decide, so the roll-up is `eligible`; a body that fires no family at all
# reaches the roll-up with zero rows, which abstains rather than clearing by silence.
JD_ELIGIBLE = "Bachelor's degree preferred. We build lovely software in Python."
JD_UNCERTAIN = "We build lovely software."
JD_INELIGIBLE = "Applicants must be authorized to work in the United States."
#: The one facts/policy pair in this file that can yield `ineligible` at all: every family ships
#: `default_policy: preference`, and only a `blocker` family can produce that verdict (D-319).
BLOCKING_FACTS = Facts(
    work_authorization=WorkAuthFact(status="needs_sponsorship", jurisdiction="us")
)
BLOCKING_POLICY = Policy(families={"work_auth": "blocker"})

PDF_BYTES = b"%PDF-1.7 the real tailored resume"
SECRET_BYTES = b"%PDF-1.7 SECRET-OUTSIDE-THE-ROOT"


# ------------------------------------------------------------------------------------- fixtures


@pytest.fixture(autouse=True)
def _scratch_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("BOARDWATCH_DATA_DIR", str(tmp_path / "data"))


@pytest.fixture()
def engine(tmp_path: Path) -> Engine:
    eng = get_engine(tmp_path / "data")
    ensure_schema(eng)
    return eng


@pytest.fixture()
def ctx(tmp_path: Path) -> ApiContext:
    out_root = tmp_path / "out"
    queue_root = tmp_path / "queue"
    out_root.mkdir()
    queue_root.mkdir()
    return ApiContext(
        settings=load_settings(),
        out_root=out_root.resolve(),
        queue_root=queue_root.resolve(),
        owner_name="Example Owner",
        platform="darwin",
    )


@dataclass(frozen=True)
class Live:
    server: ReviewServer
    token: str

    @property
    def authority(self) -> str:
        return self.server.deps.authority


@contextmanager
def serving(ctx: ApiContext) -> Iterator[Live]:
    """A real listener on 127.0.0.1, port 0, served from a daemon thread.

    Port 0 rather than a fixed port so parallel workers cannot collide, and because the `Host`
    check has to be exercised against a port the test did not choose in advance.
    """
    token = load_or_create_token(ctx.settings.config_dir)
    server = ReviewServer(("127.0.0.1", 0), ctx=ctx, token=token)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield Live(server=server, token=token)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.fixture()
def live(ctx: ApiContext, engine: Engine) -> Iterator[Live]:
    # `engine` is requested so the store exists and is migrated before anything is served: the
    # read path opens READ-ONLY and refuses to create a store it was asked only to read.
    with serving(ctx) as running:
        yield running


@dataclass(frozen=True)
class Response:
    status: int
    headers: dict[str, str]
    body: bytes

    def json(self) -> Any:
        return json.loads(self.body)


def call(
    live: Live,
    path: str,
    *,
    method: str = "GET",
    bearer: str | None = None,
    host: str | None = None,
    extra: dict[str, str] | None = None,
) -> Response:
    """One request. `bearer=None` sends no `Authorization` header at all."""
    headers = {"Host": live.authority if host is None else host}
    if bearer is not None:
        headers["Authorization"] = f"Bearer {bearer}"
    headers.update(extra or {})
    conn = http.client.HTTPConnection(live.authority, timeout=15)
    try:
        conn.request(method, path, headers=headers)
        raw = conn.getresponse()
        return Response(
            status=raw.status,
            headers={name.lower(): value for name, value in raw.getheaders()},
            body=raw.read(),
        )
    finally:
        conn.close()


# -------------------------------------------------------------------------------------- seeding


def _run(conn: Connection, *, finished: datetime | None = NOW) -> int:
    return int(
        conn.execute(
            insert(runs).values(
                started_at=NOW - timedelta(minutes=20),
                finished_at=finished,
                boards_attempted=3,
                boards_complete=3,
                postings_seen=120,
                new_count=7,
                status="ok",
            )
        ).inserted_primary_key[0]
    )


def _deliver(
    conn: Connection,
    key: str,
    *,
    body: str = JD_ELIGIBLE,
    job_id: int | None = None,
    pdf_uri: str | None = None,
    run_id: int | None = None,
    delivered_at: datetime = NOW,
    title: str = "Software Engineer",
    watched: bool = True,
    locations: list[str] | None = None,
) -> tuple[int, int]:
    """One delivered lead: company, job, posting, frozen version, tailored artifact."""
    company_id = int(
        conn.execute(
            insert(companies).values(
                name=f"Acme {key}", provider="greenhouse", slug=f"acme-{key}",
                source="user", watched=watched,
            )
        ).inserted_primary_key[0]
    )
    job = job_id
    if job is None:
        job = int(conn.execute(insert(jobs).values(created_at=NOW)).inserted_primary_key[0])
    posting_id = int(
        conn.execute(
            insert(postings).values(
                company_id=company_id, job_id=job, provider_posting_id=key, title=title,
                normalized_title=title.casefold(), url="https://boards.test/apply",
                locations_json=locations if locations is not None else ["Boston, MA"],
                remote_policy="remote",
                posted_at=NOW - timedelta(days=3), first_seen_at=NOW, last_seen_at=NOW,
                status="open", consecutive_missing=0, content_hash=f"hash-{key}", body_text=body,
            )
        ).inserted_primary_key[0]
    )
    version_id = int(
        conn.execute(
            insert(posting_versions).values(
                posting_id=posting_id, content_hash=f"v-{key}", body_text=body,
                captured_at=NOW, capture_reason="new",
            )
        ).inserted_primary_key[0]
    )
    conn.execute(
        insert(artifacts).values(
            posting_version_id=version_id, kind="resume_tailored",
            uri=f"/out/{key}/tailored-{posting_id}.typ", generator="boardwatch.tailor",
            media_type="text/x-tex", meta_json={"pdf_uri": pdf_uri},
            created_at=delivered_at, run_id=run_id,
        )
    )
    return posting_id, job


def _judge(
    conn: Connection,
    posting_id: int,
    body: str,
    *,
    facts: Facts | None = None,
    policy: Policy | None = None,
) -> str:
    """A real deterministic evaluation under the LIVE profile's identity.

    Through `evaluate` + `write_evaluation` rather than hand-inserted ledger rows: a hand-written
    `profile_hash` would read back under any implementation that hand-wrote the same constant,
    which is exactly the vacuous shape this has to avoid.
    """
    catalog = load_rules(load_settings().config_dir)
    version_id = int(
        conn.execute(
            select(posting_versions.c.id).where(posting_versions.c.posting_id == posting_id)
        ).scalar_one()
    )
    used_facts = Facts() if facts is None else facts
    used_policy = Policy() if policy is None else policy
    result = evaluate(body, used_facts, used_policy, catalog)
    write_evaluation(
        conn,
        posting_version_id=version_id,
        identity=build_identity(
            posting_version_id=version_id, facts=used_facts, policy=used_policy,
            catalog=catalog, declared_fields=declared_fields(),
        ),
        result=result,
    )
    return result.verdict


def _profile(
    conn: Connection, *, facts: Facts | None = None, policy: Policy | None = None
) -> None:
    """The default pair is `None`/`None`, which leaves eligibility unsaved exactly as before —
    every existing caller keeps its current identity. Pass both to store a policy that can
    actually block."""
    save_profile(
        conn, text="resume", target_titles=["software engineer"], exclude_titles=[],
        locations=["Boston, MA"], remote_only=False, skills=["python"],
        taxonomy_version="v1", resume_max_pages=1,
    )
    if facts is not None and policy is not None:
        save_eligibility(
            conn, facts_json=facts_payload(facts), policy_json=policy.model_dump(mode="json")
        )


def _event_count(engine: Engine) -> int:
    with engine.connect() as conn:
        return int(conn.execute(select(func.count()).select_from(application_events)).scalar_one())


# ------------------------------------------------------------------------------ authentication


def test_an_api_request_needs_a_bearer_token_and_the_same_request_with_one_succeeds(
    live: Live, engine: Engine
) -> None:
    """Both halves in one test on purpose: a server that answered 401 to everything would pass
    the refusal alone, and a test that only asserted the refusal could never tell them apart."""
    with engine.begin() as conn:
        _deliver(conn, "one")

    refused = call(live, "/api/queue", bearer=None)
    assert refused.status == 401
    assert b"posting_id" not in refused.body

    allowed = call(live, "/api/queue", bearer=live.token)
    assert allowed.status == 200
    assert len(allowed.json()["rows"]) == 1


def test_a_wrong_token_is_refused(live: Live, engine: Engine) -> None:
    with engine.begin() as conn:
        _deliver(conn, "one")

    assert call(live, "/api/queue", bearer="not-the-token").status == 401
    # The token really is the discriminator, not the presence of any Authorization header.
    assert call(live, "/api/queue", bearer=live.token).status == 200


def test_a_token_in_the_query_string_is_never_accepted(live: Live, engine: Engine) -> None:
    """A query string reaches server logs, browser history and the `Referer` of every link on
    the page. Accepting it "as a convenience" would undo the reason the client keeps the token in
    the fragment and calls `history.replaceState`."""
    with engine.begin() as conn:
        _deliver(conn, "one")

    smuggled = call(live, f"/api/queue?token={live.token}", bearer=None)
    assert smuggled.status == 401
    assert b"rows" not in smuggled.body
    # The SAME path with the header set is served, so the 401 above is about where the token was
    # and not about the query string being an unroutable path.
    assert call(live, f"/api/queue?token={live.token}", bearer=live.token).status == 200


# ---------------------------------------------------------------------------- bind, host, origin


def test_a_non_loopback_bind_is_refused_before_a_socket_exists(ctx: ApiContext) -> None:
    """Refused, not warned about. The whole threat model rests on the socket being unreachable
    from the network, and `NonLoopbackBindError` is raised before `super().__init__` binds."""
    for host in ("0.0.0.0", "192.168.1.20", "::1", "localhost"):
        with pytest.raises(NonLoopbackBindError):
            ReviewServer((host, 0), ctx=ctx, token="t")
        with pytest.raises(NonLoopbackBindError):
            build_server(ctx=ctx, token="t", host=host, port=0)

    # The control: the one permitted address really does bind, so the refusals above are about
    # the address and not about the server being unable to start at all.
    server = ReviewServer(("127.0.0.1", 0), ctx=ctx, token="t")
    try:
        assert server.server_address[0] == "127.0.0.1"
    finally:
        server.server_close()


def test_a_host_header_for_another_name_is_rejected(live: Live, engine: Engine) -> None:
    """The other half of the rebinding defence: a page on `evil.test` whose name resolves to
    127.0.0.1 reaches this socket, and the request it sends carries `Host: evil.test`."""
    with engine.begin() as conn:
        _deliver(conn, "one")
    port = live.server.server_address[1]

    rebound = call(live, "/api/queue", bearer=live.token, host=f"evil.test:{port}")
    assert rebound.status == 403
    assert b"rows" not in rebound.body
    # `localhost` is refused too: the bound authority is the literal address, and widening the
    # check to "any name that resolves to loopback" is the check being deleted.
    assert call(live, "/api/queue", bearer=live.token, host=f"localhost:{port}").status == 403
    assert call(live, "/api/queue", bearer=live.token).status == 200


def test_a_cross_origin_request_is_rejected_and_a_preflight_is_not_served(
    live: Live, engine: Engine
) -> None:
    with engine.begin() as conn:
        _deliver(conn, "one")

    foreign = call(
        live, "/api/queue", bearer=live.token, extra={"Origin": "https://evil.test"}
    )
    assert foreign.status == 403

    preflight = call(live, "/api/queue", method="OPTIONS", bearer=None)
    assert preflight.status == 405
    # Answering a preflight is what would make the cross-origin request possible, so not one
    # CORS header may be present.
    assert not [name for name in preflight.headers if name.startswith("access-control-")]

    same = call(
        live,
        "/api/queue",
        bearer=live.token,
        extra={"Origin": f"http://{live.authority}"},
    )
    assert same.status == 200


# --------------------------------------------------------------------------------------- headers


def test_an_api_response_carries_the_csp_and_referrer_policy_headers(
    live: Live, engine: Engine
) -> None:
    """Asserted on a response that carries the real payload, so a handler returning a hardcoded
    `{}` with the right headers could not pass."""
    with engine.begin() as conn:
        _deliver(conn, "one")

    response = call(live, "/api/queue", bearer=live.token)
    assert response.status == 200
    assert len(response.json()["rows"]) == 1
    assert response.headers["content-security-policy"] == CONTENT_SECURITY_POLICY
    assert "default-src 'none'" in response.headers["content-security-policy"]
    assert "unsafe-inline" not in response.headers["content-security-policy"]
    assert "http:" not in response.headers["content-security-policy"]
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_the_index_document_needs_no_token_and_carries_no_meta_csp(live: Live) -> None:
    """The token arrives in the FRAGMENT, which a browser never sends, so the document itself
    cannot be token-guarded — and the policy therefore has to be a response header. A
    `<meta http-equiv>` policy would also govern the dev server's inline react-refresh preamble
    and break `npm run dev`, which is why its absence from the built HTML is asserted here."""
    response = call(live, "/", bearer=None)
    assert response.status == 200
    assert response.headers["content-type"].startswith("text/html")
    assert response.headers["content-security-policy"] == CONTENT_SECURITY_POLICY
    assert b'<div id="root">' in response.body
    # Comments stripped first: the built document explains in a comment WHY it carries no meta
    # policy, so a naive substring check would trip over the explanation.
    uncommented = re.sub(rb"<!--.*?-->", b"", response.body, flags=re.DOTALL)
    assert b"http-equiv" not in uncommented


def test_an_asset_name_with_a_path_segment_is_not_served(live: Live) -> None:
    assert call(live, "/assets/../../etc/passwd", bearer=None).status == 404
    assert call(live, "/assets/..%2f..%2findex.html", bearer=None).status == 404

    # The control: a real asset from the committed bundle IS served, so the 404s above are about
    # the names and not about `/assets/` being unrouted.
    names = sorted(path.name for path in (static_root() / "assets").iterdir())
    assert names, "the committed bundle has no assets to serve"
    served = call(live, f"/assets/{names[0]}", bearer=None)
    assert served.status == 200
    assert served.body


# ------------------------------------------------------------------------------------------- PDF


def test_a_pdf_inside_the_output_root_streams_inline_with_a_human_filename(
    live: Live, ctx: ApiContext, engine: Engine
) -> None:
    pdf = ctx.out_root / "2026-08-26" / "acme" / "tailored-1.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(PDF_BYTES)
    with engine.begin() as conn:
        posting_id, _job = _deliver(conn, "one", pdf_uri=str(pdf))

    response = call(live, f"/api/pdf/{posting_id}", bearer=live.token)
    assert response.status == 200
    assert response.body == PDF_BYTES
    assert response.headers["content-type"] == "application/pdf"
    disposition = response.headers["content-disposition"]
    assert disposition.startswith("inline;")
    # The human-readable name, not `tailored-<id>.pdf`: the owner is about to paste this into an
    # employer's upload dialog.
    assert "Example_Owner_Acme_one_Software_Engineer.pdf" in disposition


def test_a_pdf_path_outside_the_output_root_is_refused_and_never_read(
    live: Live, ctx: ApiContext, engine: Engine, tmp_path: Path
) -> None:
    """A real traversal, constructed the way a corrupted or hand-edited `artifacts` row would
    express one: the stored `pdf_uri` climbs out of the output root with a `..` segment, and the
    file it names genuinely exists and genuinely holds bytes this endpoint must never return.

    A SIBLING whose name merely starts with the root's is the second case, and it is the one a
    string-prefix containment check gets wrong: `<tmp>/out-evil` starts with `<tmp>/out` as a
    string and is not inside it. Without this case, `str.startswith` and `is_relative_to` are
    indistinguishable here — measured, a prefix-comparison mutant passed the `..` case alone.
    """
    secret = tmp_path / "secret" / "stolen.pdf"
    secret.parent.mkdir()
    secret.write_bytes(SECRET_BYTES)
    escaping = f"{ctx.out_root}{os.sep}..{os.sep}secret{os.sep}stolen.pdf"
    assert Path(escaping).resolve() == secret.resolve(), "the traversal must actually resolve"

    sibling = tmp_path / f"{ctx.out_root.name}-evil" / "stolen.pdf"
    sibling.parent.mkdir()
    sibling.write_bytes(SECRET_BYTES)
    assert str(sibling).startswith(str(ctx.out_root)), "the sibling must share the root's prefix"

    inside = ctx.out_root / "2026-08-26" / "acme" / "tailored-2.pdf"
    inside.parent.mkdir(parents=True)
    inside.write_bytes(PDF_BYTES)

    with engine.begin() as conn:
        escaped_id, _ = _deliver(conn, "escaped", pdf_uri=escaping)
        sibling_id, _ = _deliver(conn, "sibling", pdf_uri=str(sibling))
        contained_id, _ = _deliver(conn, "contained", pdf_uri=str(inside))

    for refused_id in (escaped_id, sibling_id):
        refused = call(live, f"/api/pdf/{refused_id}", bearer=live.token)
        assert refused.status == 403, f"posting {refused_id} was not refused"
        assert SECRET_BYTES not in refused.body
        assert b"SECRET" not in refused.body

    # The same endpoint, the same shape of row, a path inside the root: served. Without this the
    # 403 above would also pass against an endpoint that refused every PDF.
    allowed = call(live, f"/api/pdf/{contained_id}", bearer=live.token)
    assert allowed.status == 200
    assert allowed.body == PDF_BYTES

    rows = {
        row["posting_id"]: row
        for row in call(live, "/api/queue", bearer=live.token).json()["rows"]
    }
    # A row must not advertise a PDF the endpoint would refuse: that is a button that only fails.
    assert rows[escaped_id]["pdf_available"] is False
    assert rows[sibling_id]["pdf_available"] is False
    assert rows[contained_id]["pdf_available"] is True


# ------------------------------------------------------------------- live score, role, coverage

def test_the_rows_arrive_ranked_and_carry_no_rank_field(live: Live, engine: Engine) -> None:
    """Rank is the array POSITION, so the array has to be ordered — and there must be no `rank`
    field that could disagree with the order describing it.

    The two leads are delivered in the OPPOSITE order to their scores, so an implementation that
    returned `delivered_unapplied`'s most-recent-delivery-first order unchanged fails here.

    BOTH titles are software, so both sit in the apply lane and the ordering is actually
    exercised. The weaker lead used to be a "Data Entry Clerk", which the D-332 split now routes
    to `review` — that would have left ONE row here and an assertion that could not fail. The gap
    has to come from the title rather than the body: `JD_ELIGIBLE` and `JD_UNCERTAIN` score
    IDENTICALLY against this fixture profile (0.719 both, coverage `None`), so a body-derived gap
    would have been the vacuous version of the same mistake.
    """
    with engine.begin() as conn:
        _profile(conn)
        wanted, _ = _deliver(
            conn, "swe", title="Software Engineer", delivered_at=NOW - timedelta(days=2)
        )
        unwanted, _ = _deliver(
            conn, "swe2", title="Software Developer", delivered_at=NOW
        )

    rows = call(live, "/api/queue", bearer=live.token).json()["rows"]
    assert [row["posting_id"] for row in rows] == [wanted, unwanted]
    assert rows[0]["score"] is not None
    assert rows[0]["score"] > rows[1]["score"]
    assert "rank" not in rows[0]
    # The `why` line comes from the shipped explainer, not from a sentence composed here.
    assert rows[0]["why"]


def test_the_queue_payload_reports_unverifiable_for_an_unenumerated_board(
    live: Live, engine: Engine
) -> None:
    """The wire is where the label has to arrive: the frontend never re-derives it.

    Asserted through the HTTP layer and on BOTH endpoints, because the row and the detail pane
    are separately serialized and a lead that read `unverifiable` in the list and `open` in the
    pane would be worse than either alone.
    """
    with engine.begin() as conn:
        unwatched, _ = _deliver(conn, "unwatched", watched=False)
        watched, _ = _deliver(conn, "watched", watched=True)

    rows = {
        row["posting_id"]: row
        for row in call(live, "/api/queue", bearer=live.token).json()["rows"]
    }
    assert rows[unwatched]["status"] == "unverifiable"
    assert rows[watched]["status"] == "open"

    pane = call(live, f"/api/queue/{unwatched}", bearer=live.token).json()
    assert pane["row"]["status"] == "unverifiable"



def test_off_target_carries_the_role_gates_own_matched_text_and_uncertain_is_not_a_veto(
    live: Live, engine: Engine
) -> None:
    """The badge has to be traceable to the words that caused it, and `uncertain` must not wear
    it.

    `off_target` comes from `role_verdict`, never from a title pattern written in the API — a
    second opinion about a shipped gate is a wrong one. And `uncertain` is not a veto: about a
    third of the delivered set classifies that way, so badging it "off target" would assert a
    decision the gate declined to make. "Tax CPA" is exactly that shape — a title that looks
    off-target to a human and that the gate deliberately does not reject.

    Both of those still hold, and the D-332 split is why they now MATTER. `off_target` is
    `not_swe` ONLY, while `review_gate.lane` demotes anything not positively `swe` — so the
    vetoed nurse and the uncertain CPA land in the SAME list and only one of them wears a badge.
    That is exactly why the review lane had to become its own list rather than a flag: the flag
    cannot describe the lane, and reading `off_target` as "this is a review lead" would miss
    every `uncertain` one.
    """
    with engine.begin() as conn:
        vetoed, _ = _deliver(conn, "nurse", title="Registered Nurse Practitioner")
        unsure, _ = _deliver(conn, "cpa", title="Tax CPA")
        software, _ = _deliver(conn, "swe", title="Software Engineer")

    payload = call(live, "/api/queue", bearer=live.token).json()
    rows = {row["posting_id"]: row for row in payload["rows"]}
    review = {row["posting_id"]: row for row in payload["review"]}

    # The apply lane holds the software lead and NOTHING else.
    assert set(rows) == {software}
    assert set(review) == {vetoed, unsure}
    assert payload["counts"]["review"] == 2
    assert payload["counts"]["in_queue"] == 1

    assert review[vetoed]["off_target"] is True
    # The gate's own reason string, carrying the text it matched in quotes.
    assert review[vetoed]["off_target_reason"] == 'not software (matched "Nurse")'

    # The uncertain lead is in review WITHOUT a badge — the flag and the lane are not the same
    # question, and this is the pair that proves it.
    assert review[unsure]["off_target"] is False
    assert review[unsure]["off_target_reason"] is None
    assert rows[software]["off_target"] is False
    assert rows[software]["off_target_reason"] is None


def test_every_review_row_names_which_reason_held_it_and_apply_rows_carry_none(
    live: Live, engine: Engine
) -> None:
    """`review_reason` on the wire, one member per branch of `review_gate.classify`.

    Before it existed the only marker a review row could carry was `off_target`, which is
    `not_swe` ALONE — so a lead held for a confirmed non-US location, and a lead held because the
    role gate would not positively call its title software, both rendered indistinguishable from a
    clean one. All three cases are asserted together here, because the defect was not any single
    missing string: it was that two of the three lanes' reasons had nowhere to travel.

    The apply row is in the same assertion for the same reason. `review_reason` being `None`
    exactly off the review lane is what lets the page treat the field and the list as one fact
    rather than two that happen to agree.
    """
    with engine.begin() as conn:
        foreign, _ = _deliver(conn, "vilnius", title="Software Engineer",
                              locations=["Kaunas, Lithuania"])
        vetoed, _ = _deliver(conn, "nurse", title="Registered Nurse Practitioner")
        unconfirmed, _ = _deliver(conn, "cpa", title="Tax CPA")
        software, _ = _deliver(conn, "swe", title="Software Engineer")

    payload = call(live, "/api/queue", bearer=live.token).json()
    rows = {row["posting_id"]: row for row in payload["rows"]}
    review = {row["posting_id"]: row for row in payload["review"]}

    assert set(review) == {foreign, vetoed, unconfirmed}
    assert review[foreign]["review_reason"] == "non_us_location"
    assert review[vetoed]["review_reason"] == "role_vetoed"
    assert review[unconfirmed]["review_reason"] == "role_unconfirmed"

    # The abstain is NOT folded into the veto. These two are in the same list and only one of
    # them is a decision the role gate made.
    assert review[unconfirmed]["review_reason"] != review[vetoed]["review_reason"]
    # And it is not reachable through `off_target`, which is why the field had to exist: two of
    # the three held leads wear no badge at all.
    assert review[foreign]["off_target"] is False
    assert review[unconfirmed]["off_target"] is False

    assert set(rows) == {software}
    assert rows[software]["review_reason"] is None

    # The detail pane serializes a row with no list around it, so the field has to survive there
    # too — that endpoint is where the pane would otherwise have to guess.
    pane = call(live, f"/api/queue/{foreign}", bearer=live.token).json()
    assert pane["row"]["review_reason"] == "non_us_location"


def test_a_review_lead_is_listed_not_dropped_and_the_band_reconciles(
    live: Live, engine: Engine
) -> None:
    """A review lead is WORK, so it must appear somewhere on the wire.

    `_ineligible` is an exclusion and is only counted; `_review` is a second location and is
    LISTED. Getting these two confused would silently hide about a third of the delivered set
    behind a folder the page never mentions. The band has to reconcile too: `in_queue` counts the
    apply lane alone, so without `review` the difference between it and the delivered set is an
    unexplained remainder — the same defect D-321 fixed for `ineligible`.
    """
    with engine.begin() as conn:
        _profile(conn, facts=BLOCKING_FACTS, policy=BLOCKING_POLICY)
        software, _ = _deliver(conn, "swe", title="Software Engineer", body=JD_UNCERTAIN)
        held, _ = _deliver(conn, "nurse", title="Registered Nurse Practitioner",
                           body=JD_UNCERTAIN)
        rejected, _ = _deliver(conn, "noauth", title="Software Engineer", body=JD_INELIGIBLE)
        # The premise, stated out loud rather than assumed: if the engine stops calling this
        # body ineligible, THIS fails instead of the counts passing vacuously.
        assert (
            _judge(conn, rejected, JD_INELIGIBLE, facts=BLOCKING_FACTS, policy=BLOCKING_POLICY)
            == "ineligible"
        )

    payload = call(live, "/api/queue", bearer=live.token).json()
    counts = payload["counts"]
    listed = {row["posting_id"] for row in payload["rows"]} | {
        row["posting_id"] for row in payload["review"]
    }
    # The ineligible lead is the ONLY one that may be absent from both lists.
    assert listed == {software, held}
    assert rejected not in listed
    assert counts["ineligible"] == 1
    assert counts["review"] == 1
    assert counts["in_queue"] == 1


def test_a_closed_lead_leaves_both_lists_and_is_counted_as_closed_not_ineligible(
    live: Live, engine: Engine
) -> None:
    """The page has to mirror the folder tree, and the mirror is where it silently breaks.

    A closed lead drains to `_closed` on disk. If the page keeps deriving `ineligible` as "the
    delivered set minus what is listed", the same lead is reported as ineligible here while
    sitting in `_closed` there — a page and a folder tree disagreeing about one lead, which is
    the single failure `queue_payload` is arranged against.

    `counts["ineligible"] == 0` is the assertion that carries the test. Without it every arm
    below still passes when the closed lead is miscounted, because it is absent from both lists
    either way — absence is exactly what the two remainders have in common.
    """
    with engine.begin() as conn:
        live_lead, _ = _deliver(conn, "live", title="Software Engineer")
        dead_lead, _ = _deliver(conn, "dead", title="Software Engineer")
        conn.execute(
            update(postings).where(postings.c.id == dead_lead).values(status="closed")
        )

    payload = call(live, "/api/queue", bearer=live.token).json()
    counts = payload["counts"]
    listed = {row["posting_id"] for row in payload["rows"]} | {
        row["posting_id"] for row in payload["review"]
    }
    assert listed == {live_lead}, "the closed lead is still being listed as work"
    assert counts["closed"] == 1
    assert counts["ineligible"] == 0, "a closed lead was counted as an eligibility rejection"
    assert counts["review"] == 0
    assert counts["in_queue"] == 1


def test_an_unverifiable_lead_is_never_counted_as_closed(live: Live, engine: Engine) -> None:
    """The fail-open direction, on the wire.

    `unverifiable` means open on a board nothing enumerates (D-324). It is one `status` value
    away from `closed` and a drain keyed on `!= "open"` would sweep it, so the page is asserted
    to keep it as listed work — the arm that the closed-lead test above cannot see.
    """
    with engine.begin() as conn:
        unverifiable, _ = _deliver(conn, "unwatched", title="Software Engineer", watched=False)

    payload = call(live, "/api/queue", bearer=live.token).json()
    rows = {row["posting_id"]: row for row in payload["rows"]}
    assert rows[unverifiable]["status"] == "unverifiable", "premise: the label must be reached"
    assert payload["counts"]["closed"] == 0
    assert payload["counts"]["in_queue"] == 1


def test_coverage_is_a_live_fraction_and_thin_jd_is_derived_from_it(
    live: Live, engine: Engine
) -> None:
    """`thin_jd` is `coverage.fraction is None` and nothing else.

    Both halves are asserted against the same résumé in the same request: a JD carrying a
    recognised requirement term yields a real fraction and `thin_jd: false`, and a JD carrying
    none yields `null` and `thin_jd: true`. An implementation that reported `0.0` for the second
    would be claiming "your résumé covers none of this" about a JD that asked for nothing, and
    an implementation that reported `null` for both would fail the first.
    """
    resume = live.server.deps.ctx.settings.config_dir / "resume.yaml"
    resume.parent.mkdir(parents=True, exist_ok=True)
    resume.write_text(scaffold_template(), encoding="utf-8")

    with engine.begin() as conn:
        measured, _ = _deliver(conn, "python", body=JD_ELIGIBLE)
        thin, _ = _deliver(conn, "thin", body=JD_UNCERTAIN)

    rows = {
        row["posting_id"]: row
        for row in call(live, "/api/queue", bearer=live.token).json()["rows"]
    }

    assert rows[measured]["thin_jd"] is False
    assert rows[measured]["coverage"] == 1.0
    detail = rows[measured]["coverage_detail"]
    assert detail["covered"] and detail["total_count"] == detail["covered_count"]
    assert detail["fraction"] == rows[measured]["coverage"]

    assert rows[thin]["thin_jd"] is True
    assert rows[thin]["coverage"] is None
    assert rows[thin]["coverage_detail"]["total_count"] == 0
    assert rows[thin]["coverage_detail"]["fraction"] is None


# ------------------------------------------------------------------------------- a locked store


def test_a_locked_store_answers_503_without_stalling(
    live: Live, engine: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A bounded retry and then 503 — not a five-second stall ending in a traceback.

    The lock is a real `BEGIN EXCLUSIVE` on a second connection, so the write genuinely gets
    SQLITE_BUSY rather than a simulated one.

    The discriminator is the BUDGET THE WRITE PATH ASKED FOR, asserted directly, not inferred from
    a stopwatch. The wrong implementation this guards against is one that inherited `get_engine`'s
    5000 ms default; spying on `get_engine` names that difference exactly (300 ms x 3 attempts
    against 5000 ms) instead of hoping a wall-clock bound lands between them.

    It did not. The real budget is `WRITE_ATTEMPTS * WRITE_BUSY_TIMEOUT_MS` = 900 ms, but three
    engine construct/dispose cycles dominate it, so a loaded macOS runner measured 3.01-3.15 s
    against a 3.0 s bound and `main` went red on all three macOS jobs at once. The bound was never
    load-sensitive in a useful way: it sat on top of the true elapsed while the implementation it
    rejects is ~15 s away. The clock assertion therefore STAYS, as a generous backstop against a
    genuine stall, and moves to 8 s — still less than the ~15 s the 5000 ms version would take, so
    nothing is given up.
    """
    with engine.begin() as conn:
        posting_id, _job = _deliver(conn, "one")

    asked: list[int | None] = []
    real_get_engine = server_mod.get_engine

    def spy_get_engine(data_dir: Path, busy_timeout_ms: int | None = None, **kw: object) -> Any:
        asked.append(busy_timeout_ms)
        return real_get_engine(data_dir, busy_timeout_ms=busy_timeout_ms, **kw)  # type: ignore[arg-type]

    monkeypatch.setattr(server_mod, "get_engine", spy_get_engine)

    locker = sqlite3.connect(str(tmp_path / "data" / DB_FILENAME), timeout=0.05)
    locker.isolation_level = None
    locker.execute("BEGIN EXCLUSIVE")
    try:
        started = time.monotonic()
        refused = call(live, f"/api/queue/{posting_id}/applied", method="POST", bearer=live.token)
        elapsed = time.monotonic() - started
        assert refused.status == 503
        assert b"Traceback" not in refused.body
        # The real discriminator: the write path asked for the BOUNDED budget on every attempt,
        # never `get_engine`'s 5000 ms default.
        # The count is a LITERAL 3, not `WRITE_ATTEMPTS`. Comparing against the constant put it on
        # both sides of the assertion, so collapsing the retry budget to 1 moved the expectation
        # with it and the test passed against the mutant. The budget stays a constant — tuning it
        # is legitimate — but the number of attempts is the contract this test pins.
        assert asked == [WRITE_BUSY_TIMEOUT_MS] * 3, asked
        # A generous backstop against a genuine stall. 8 s is far below the ~15 s the 5000 ms
        # version would take, so widening it from 3 s gives up no discriminating power.
        assert elapsed < 8.0, f"a contended write took {elapsed:.2f}s"
    finally:
        locker.execute("ROLLBACK")
        locker.close()

    # The control: with the lock released the very same request succeeds, so the 503 was about
    # contention and not about the endpoint being broken.
    allowed = call(live, f"/api/queue/{posting_id}/applied", method="POST", bearer=live.token)
    assert allowed.status == 200
    assert allowed.json()["outcome"] == "created"


# ------------------------------------------------------------------------------ applied and undo


def test_marking_applied_twice_appends_exactly_one_event(
    live: Live, engine: Engine
) -> None:
    """An endpoint a browser can re-POST must be idempotent in the LOG as well as in the state.
    An immutable event log is only readable if every row in it records something that happened,
    and a refresh is not an event."""
    with engine.begin() as conn:
        posting_id, job = _deliver(conn, "one")
    assert _event_count(engine) == 0

    first = call(live, f"/api/queue/{posting_id}/applied", method="POST", bearer=live.token)
    assert first.status == 200
    assert first.json() == {"outcome": "created", "job_id": job}
    # The control for the count assertion below: the FIRST write really does append an event, so
    # "no new event" is a measurement rather than a log nothing ever writes to.
    after_first = _event_count(engine)
    assert after_first == 1

    second = call(live, f"/api/queue/{posting_id}/applied", method="POST", bearer=live.token)
    assert second.status == 200
    assert second.json() == {"outcome": "unchanged", "job_id": job}
    assert _event_count(engine) == after_first

    with engine.connect() as conn:
        statuses = conn.execute(select(applications.c.status)).scalars().all()
    assert list(statuses) == ["applied"]


def test_unapplied_returns_the_lead_to_the_queue_and_keeps_the_applied_event(
    live: Live, engine: Engine
) -> None:
    """The undo the frontend's toast needs. Without it the row comes back on screen while the
    store still says `applied` forever, and the lead never re-enters the queue.

    The applied event is NOT deleted: the record has to read "applied, then withdrawn", which is
    what happened. Erasing it would be a tidier log and a false one.
    """
    with engine.begin() as conn:
        posting_id, job = _deliver(conn, "one")

    assert [row["posting_id"] for row in call(live, "/api/queue", bearer=live.token).json()["rows"]] == [posting_id]

    call(live, f"/api/queue/{posting_id}/applied", method="POST", bearer=live.token)
    assert call(live, "/api/queue", bearer=live.token).json()["rows"] == []

    undo = call(live, f"/api/queue/{posting_id}/unapplied", method="POST", bearer=live.token)
    assert undo.status == 200
    assert undo.json() == {"outcome": "transitioned", "job_id": job}

    restored = call(live, "/api/queue", bearer=live.token).json()
    assert [row["posting_id"] for row in restored["rows"]] == [posting_id]
    assert restored["counts"]["applied_ever"] == 0

    with engine.connect() as conn:
        events = conn.execute(
            select(application_events.c.event_type, application_events.c.to_status)
            .order_by(application_events.c.id)
        ).all()
        rows = conn.execute(
            select(applications.c.status, applications.c.submitted_at)
        ).all()
    assert [(event.event_type, event.to_status) for event in events] == [
        ("created", "applied"),
        ("status_change", "withdrawn"),
    ]
    assert [row.status for row in rows] == ["withdrawn"]
    # `submitted_at` stands: an application that really was submitted must not read as one that
    # never was.
    assert rows[0].submitted_at is not None

    # Idempotent in the log, exactly like `applied`: a second undo records nothing.
    before = _event_count(engine)
    again = call(live, f"/api/queue/{posting_id}/unapplied", method="POST", bearer=live.token)
    assert again.json()["outcome"] == "unchanged"
    assert _event_count(engine) == before


def test_skip_removes_a_lead_and_unskip_restores_it(live: Live, engine: Engine) -> None:
    with engine.begin() as conn:
        posting_id, _job = _deliver(conn, "one")

    skipped = call(live, f"/api/queue/{posting_id}/skipped", method="POST", bearer=live.token)
    assert skipped.json() == {"outcome": "skipped"}
    gone = call(live, "/api/queue", bearer=live.token).json()
    assert gone["rows"] == []
    assert gone["counts"]["skipped"] == 1
    # A skip is NOT an application: it must never inflate the conversion count.
    assert gone["counts"]["applied_ever"] == 0

    unskipped = call(live, f"/api/queue/{posting_id}/unskip", method="POST", bearer=live.token)
    assert unskipped.json() == {"outcome": "unskipped"}
    back = call(live, "/api/queue", bearer=live.token).json()
    assert [row["posting_id"] for row in back["rows"]] == [posting_id]
    assert back["counts"]["skipped"] == 0


def test_report_removes_a_lead_and_unreport_restores_it(live: Live, engine: Engine) -> None:
    with engine.begin() as conn:
        posting_id, _job = _deliver(conn, "one")

    reported = call(live, f"/api/queue/{posting_id}/reported", method="POST", bearer=live.token)
    assert reported.json() == {"outcome": "reported"}
    gone = call(live, "/api/queue", bearer=live.token).json()
    assert gone["rows"] == []
    assert gone["counts"]["reported"] == 1
    # A report is neither an application nor a skip: it must inflate neither of those counts.
    assert gone["counts"]["applied_ever"] == 0
    assert gone["counts"]["skipped"] == 0

    undone = call(live, f"/api/queue/{posting_id}/unreport", method="POST", bearer=live.token)
    assert undone.json() == {"outcome": "unreported"}
    back = call(live, "/api/queue", bearer=live.token).json()
    assert [row["posting_id"] for row in back["rows"]] == [posting_id]
    assert back["counts"]["reported"] == 0


def test_reporting_a_posting_that_does_not_exist_is_a_404(live: Live, engine: Engine) -> None:
    with engine.begin() as conn:
        posting_id, _job = _deliver(conn, "one")
    assert (
        call(live, "/api/queue/999999/reported", method="POST", bearer=live.token).status == 404
    )
    assert (
        call(live, f"/api/queue/{posting_id}/reported", method="POST", bearer=live.token).status
        == 200
    )


def test_marking_a_posting_that_does_not_exist_is_a_404(live: Live, engine: Engine) -> None:
    with engine.begin() as conn:
        posting_id, _job = _deliver(conn, "one")
    assert call(live, "/api/queue/999999/applied", method="POST", bearer=live.token).status == 404
    assert call(live, f"/api/queue/{posting_id}/applied", method="POST", bearer=live.token).status == 200


# -------------------------------------------------------------------------------------- counts


def test_uncertain_is_never_summed_into_the_eligible_count(live: Live, engine: Engine) -> None:
    """`eligible` is the affirmatively-eligible count and the headline yield; `uncertain` is its
    own visible bucket. Folding the two would be the same error as folding an abstain into a
    neighbour, and on this corpus it is a 2x overstatement of the yield.

    Both verdicts are written by the real engine under the live profile's identity, so a wired
    `eligible: 1` here cannot come from a hand-written constant.
    """
    with engine.begin() as conn:
        _profile(conn)
        clear, _ = _deliver(conn, "clear", body=JD_ELIGIBLE)
        vague, _ = _deliver(conn, "vague", body=JD_UNCERTAIN)
        assert _judge(conn, clear, JD_ELIGIBLE) == "eligible"
        assert _judge(conn, vague, JD_UNCERTAIN) == "uncertain"

    payload = call(live, "/api/queue", bearer=live.token).json()
    verdicts = {row["posting_id"]: row["verdict"] for row in payload["rows"]}
    assert verdicts == {clear: "eligible", vague: "uncertain"}

    counts = payload["counts"]
    assert counts["in_queue"] == 2
    assert counts["eligible"] == 1
    assert counts["uncertain"] == 1
    # Stated as its own assertion because the sum is the specific defect: an implementation that
    # counted "eligible or uncertain" reports 2 and passes an `>= 1` check.
    assert counts["eligible"] != counts["in_queue"]


def test_counts_report_ineligible_as_its_own_cell_and_keep_it_out_of_the_queue(
    live: Live, engine: Engine
) -> None:
    """An ineligible lead is not work, so it is not a row — but it IS a number.

    Both halves matter and they fail differently. Dropping the row without counting it makes
    `in_queue` an unexplained remainder, which is the same defect as an unreported abstain.
    Counting it without dropping the row leaves the page disagreeing with the folder tree, since
    `reconcile_queue` drains the folder to `_ineligible`.

    The verdicts are asserted before the payload is read, so `ineligible: 1` cannot come from a
    hand-written constant — and `assert ... == "ineligible"` is the premise stated out loud: if
    the engine stops calling this body ineligible, this fails instead of passing vacuously.
    """
    with engine.begin() as conn:
        _profile(conn, facts=BLOCKING_FACTS, policy=BLOCKING_POLICY)
        clear, _ = _deliver(conn, "clear", body=JD_UNCERTAIN)
        barred, _ = _deliver(conn, "barred", body=JD_INELIGIBLE)
        assert (
            _judge(conn, barred, JD_INELIGIBLE, facts=BLOCKING_FACTS, policy=BLOCKING_POLICY)
            == "ineligible"
        )
        assert (
            _judge(conn, clear, JD_UNCERTAIN, facts=BLOCKING_FACTS, policy=BLOCKING_POLICY)
            != "ineligible"
        )

    payload = call(live, "/api/queue", bearer=live.token).json()
    shown = {row["posting_id"] for row in payload["rows"]}
    assert barred not in shown, "an ineligible lead was listed as work"
    assert clear in shown, "a non-ineligible lead must still be listed"

    counts = payload["counts"]
    assert counts["ineligible"] == 1
    assert counts["in_queue"] == 1
    # Its own cell, never folded into a neighbour: an implementation that added it to `uncertain`
    # or left it inside `in_queue` reports 2 here and passes any `>= 1` check.
    assert counts["in_queue"] == counts["eligible"] + counts["uncertain"]


def test_counts_report_the_last_finished_run(live: Live, engine: Engine) -> None:
    with engine.begin() as conn:
        run_id = _run(conn)
        _deliver(conn, "delivered", run_id=run_id)
        _deliver(conn, "older", run_id=None)

    counts = call(live, "/api/queue", bearer=live.token).json()["counts"]
    assert counts["delivered_last_run"] == 1
    assert counts["last_run_finished"] == NOW.isoformat()


# -------------------------------------------------------------------------------------- details


def test_a_lead_with_no_current_version_serves_a_body_unavailable_detail(
    live: Live, engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`jd_body: null` and HTTP 200, never a 500.

    The two existing readers of a frozen body disagree about this case —
    `eligibility/audit.py` tolerates it, `projection/posting.py` raises — and the API picks
    tolerate and says so, because a detail request that raised would take a whole page down over
    one missing row.

    The state is induced rather than seeded: `artifacts` FKs to `posting_versions`, which FKs to
    `postings`, so the join that finds a delivered lead cannot yield a row whose version is gone.
    `current_posting_versions` is therefore emptied for BOTH of its consumers on this path — the
    store's detail read and the API's live-coverage read — which is the state the tolerate branch
    exists for and the state in which a `[posting_id]` subscript would raise.
    """
    with engine.begin() as conn:
        posting_id, _job = _deliver(conn, "one")

    # The control first, against the real store: a lead WITH a version reports its frozen body,
    # so `jd_body is None` below is a change in behaviour and not the only thing this can return.
    present = call(live, f"/api/queue/{posting_id}", bearer=live.token).json()
    assert present["jd_body"] == JD_ELIGIBLE

    for module in ("boardwatch.store.delivery_queries", "boardwatch.delivery.api"):
        monkeypatch.setattr(f"{module}.current_posting_versions", lambda *a, **k: {})

    absent = call(live, f"/api/queue/{posting_id}", bearer=live.token)
    assert absent.status == 200
    payload = absent.json()
    assert payload["jd_body"] is None
    assert payload["row"]["posting_id"] == posting_id
    assert payload["row"]["thin_jd"] is True


def test_a_detail_carries_the_rule_that_fired_and_its_quoted_span(
    live: Live, engine: Engine
) -> None:
    """A `rule` entry is what the evidence list renders. The quote is sliced from the frozen
    version body by `load_audit`, so it has to be a real substring of it."""
    with engine.begin() as conn:
        _profile(conn)
        posting_id, _job = _deliver(conn, "one", body=JD_ELIGIBLE)
        _judge(conn, posting_id, JD_ELIGIBLE)

    payload = call(live, f"/api/queue/{posting_id}", bearer=live.token).json()
    evidence = [entry for entry in payload["requirements"] if entry["rule"] is not None]
    assert evidence, "the audit rows did not reach the payload"
    for entry in evidence:
        assert set(entry) == {
            "requirement", "covered", "rule", "disposition", "profile_field", "quote", "rationale",
        }
        assert entry["disposition"] is not None
        if entry["quote"] is not None:
            assert entry["quote"] in JD_ELIGIBLE


def test_a_detail_for_an_undelivered_posting_is_a_404(live: Live, engine: Engine) -> None:
    with engine.begin() as conn:
        posting_id, _job = _deliver(conn, "one")
    assert call(live, "/api/queue/999999", bearer=live.token).status == 404
    assert call(live, f"/api/queue/{posting_id}", bearer=live.token).status == 200


# --------------------------------------------------------------------------------------- reveal


def test_reveal_is_post_only_and_reports_the_platforms_capability(
    ctx: ApiContext, engine: Engine
) -> None:
    """The capability flag has to come from the same function that builds the argv, or the
    button can be shown on a platform where it can only fail."""
    with engine.begin() as conn:
        posting_id, _job = _deliver(conn, "one")

    with serving(replace(ctx, platform="sunos5")) as live:
        assert call(live, "/api/queue", bearer=live.token).json()["meta"]["reveal_supported"] is False
        unsupported = call(
            live, f"/api/queue/{posting_id}/reveal", method="POST", bearer=live.token
        ).json()
        assert unsupported["ok"] is False
        assert "sunos5" in unsupported["reason"]

    with serving(replace(ctx, platform="darwin")) as live:
        assert call(live, "/api/queue", bearer=live.token).json()["meta"]["reveal_supported"] is True
        # POST-only: a GET must not reach the handler at all, or a link or an <img> would fire it.
        assert call(live, f"/api/queue/{posting_id}/reveal", bearer=live.token).status == 404
        # No folder has been synced, so nothing is launched and no subprocess runs.
        refused = call(
            live, f"/api/queue/{posting_id}/reveal", method="POST", bearer=live.token
        ).json()
        assert refused == {"ok": False, "reason": "this lead has no folder in the queue yet"}


# ----------------------------------------------------------------------------------- the runs


def test_the_runs_payload_counts_leads_from_the_artifacts_that_recorded_them(
    live: Live, engine: Engine
) -> None:
    with engine.begin() as conn:
        run_id = _run(conn)
        _deliver(conn, "a", run_id=run_id)
        _deliver(conn, "b", run_id=run_id)

    (run,) = call(live, "/api/runs", bearer=live.token).json()["runs"]
    assert run["id"] == run_id
    assert run["leads"] == 2
    assert run["postings_seen"] == 120

    assert call(live, f"/api/runs/{run_id}", bearer=live.token).status == 404


def test_the_runs_payload_carries_the_four_way_board_split(
    live: Live, engine: Engine
) -> None:
    """/api/runs must expose partial/unchanged/failed so the web run list can reconcile the
    total; a run that never measured them reports NULL, never a fabricated 0 (D-341)."""
    with engine.begin() as conn:
        measured = _run(conn)
        conn.execute(
            update(runs)
            .where(runs.c.id == measured)
            .values(boards_partial=1, boards_unchanged=1, boards_failed=1)
        )
        unmeasured = _run(conn)

    by_id = {r["id"]: r for r in call(live, "/api/runs", bearer=live.token).json()["runs"]}
    assert by_id[measured]["boards_partial"] == 1
    assert by_id[measured]["boards_unchanged"] == 1
    assert by_id[measured]["boards_failed"] == 1
    assert by_id[unmeasured]["boards_partial"] is None
    assert by_id[unmeasured]["boards_unchanged"] is None
    assert by_id[unmeasured]["boards_failed"] is None


def test_a_runs_funnel_artifact_is_passed_through(
    live: Live, ctx: ApiContext, engine: Engine
) -> None:
    with engine.begin() as conn:
        run_id = _run(conn)
    day = ctx.out_root / "2026-08-26"
    day.mkdir()
    (day / f"funnel-{run_id}.json").write_text(
        json.dumps({"run_id": run_id, "stages": [], "reconciles": True}), encoding="utf-8"
    )

    payload = call(live, f"/api/runs/{run_id}", bearer=live.token).json()
    assert payload == {"run_id": run_id, "stages": [], "reconciles": True}
    # An exact numeric name: `funnel-7.json` must never answer for run 70.
    assert call(live, f"/api/runs/{run_id}0", bearer=live.token).status == 404


# ---------------------------------------------------------------------------------- the token


def test_the_token_is_stable_per_install_and_stored_at_mode_0600(tmp_path: Path) -> None:
    """Stable, not minted per launch: a per-launch token cannot be bookmarked, and it buys
    nothing because it is handed to the browser opener and lands in that process's argv either
    way."""
    config_dir = tmp_path / "cfg"
    first = load_or_create_token(config_dir)
    second = load_or_create_token(config_dir)
    assert first == second
    assert len(first) >= 32

    path = config_dir / TOKEN_FILENAME
    assert path.read_text(encoding="utf-8").strip() == first
    if os.name == "posix":
        assert oct(path.stat().st_mode & 0o777) == "0o600"

    # An empty file is treated as absent AND is replaceable: a zero-byte token would
    # authenticate a request that presented nothing, and refusing to replace one would brick the
    # command permanently on a single truncated write.
    path.write_text("   \n", encoding="utf-8")
    replaced = load_or_create_token(config_dir)
    assert replaced not in ("", first)
    assert path.read_text(encoding="utf-8").strip() == replaced
    if os.name == "posix":
        assert oct(path.stat().st_mode & 0o777) == "0o600"
    assert not list(config_dir.glob(f"{TOKEN_FILENAME}.*")), "a temp file was left behind"


def test_a_missing_bundle_is_refused_with_a_named_error(
    ctx: ApiContext, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "boardwatch.delivery.server.static_root", lambda: tmp_path / "no-such-bundle"
    )
    with pytest.raises(BundleMissingError):
        build_server(ctx=ctx, token="t", host="127.0.0.1", port=0)

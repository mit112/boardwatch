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
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Connection, Engine, func, insert, select, update

from boardwatch.core.host_class import classify_host
from boardwatch.core.settings import load_settings
from boardwatch.delivery import DRAIN_DIRS
from boardwatch.delivery import server as server_mod
from boardwatch.delivery.answers import (
    WORK_AUTH_JURISDICTION_WORDS,
    WORK_AUTH_STATUS_WORDS,
)
from boardwatch.delivery.api import ApiContext, local_today
from boardwatch.delivery.queue import SKIPPED_DIR, sync_queue
from boardwatch.delivery.server import (
    CONTENT_SECURITY_POLICY,
    FOLLOWUP_DATE_REASON,
    FOLLOWUP_RANGE_REASON,
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
from boardwatch.eligibility.final_gate import record_gate_verdict
from boardwatch.eligibility.hashing import build_identity
from boardwatch.eligibility.oracle import OracleVerdict
from boardwatch.eligibility.resolve import declared_fields
from boardwatch.store.applications import create_application
from boardwatch.store.db import DB_FILENAME, ensure_schema, get_engine
from boardwatch.store.queries import save_eligibility, save_profile
from boardwatch.store.queue_state import followup_job_dates
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
#: An `uncertain` verdict that still reaches the APPLY lane, which `JD_UNCERTAIN` no longer does:
#: it carries a requirement row, so A3's zero-row hold does not fire, and the abstaining family is
#: `student_status` — a blocker (hence `uncertain`) that is neither a hard family nor
#: `experience_years`, so neither of the two older requirement holds fires either.
JD_UNCERTAIN_STATED = (
    "Candidates must be currently enrolled in a degree program. We build lovely software."
)
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
    body: Any | None = None,
) -> Response:
    """One request. `bearer=None` sends no `Authorization` header at all.

    `body` is serialised as JSON and sent with a `Content-Type`, which is what the batch routes
    read. `None` sends no body at all, so every existing caller's request is byte-identical.
    """
    headers = {"Host": live.authority if host is None else host}
    if bearer is not None:
        headers["Authorization"] = f"Bearer {bearer}"
    headers.update(extra or {})
    payload = None if body is None else json.dumps(body).encode("utf-8")
    if payload is not None:
        headers["Content-Type"] = "application/json"
    conn = http.client.HTTPConnection(live.authority, timeout=15)
    try:
        conn.request(method, path, body=payload, headers=headers)
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
    judge: bool = True,
    facts: Facts | None = None,
    policy: Policy | None = None,
    provider: str = "greenhouse",
    url: str = "https://boards.test/apply",
) -> tuple[int, int]:
    """One delivered lead: company, job, posting, frozen version, tailored artifact.

    `judge=True` writes a real evaluation of `body`, which is what puts the lead in the apply
    lane: since A3 a lead with no current evaluation routes to `_review`, because nothing cleared
    it. These fixtures used to leave every verdict `None` and rely on that fail-open.

    Pass `facts`/`policy` when the test stores a non-default identity — the evaluation has to be
    written under the identity `current_identity` will recompute, or it does not govern and the
    lead reads as unevaluated. `judge=False` is for a test that is ABOUT the unevaluated case.
    """
    company_id = int(
        conn.execute(
            insert(companies).values(
                name=f"Acme {key}",
                provider=provider,
                slug=f"acme-{key}",
                source="user",
                watched=watched,
            )
        ).inserted_primary_key[0]
    )
    job = job_id
    if job is None:
        job = int(conn.execute(insert(jobs).values(created_at=NOW)).inserted_primary_key[0])
    posting_id = int(
        conn.execute(
            insert(postings).values(
                company_id=company_id,
                job_id=job,
                provider_posting_id=key,
                title=title,
                normalized_title=title.casefold(),
                url=url,
                locations_json=locations if locations is not None else ["Boston, MA"],
                remote_policy="remote",
                posted_at=NOW - timedelta(days=3),
                first_seen_at=NOW,
                last_seen_at=NOW,
                status="open",
                consecutive_missing=0,
                content_hash=f"hash-{key}",
                body_text=body,
            )
        ).inserted_primary_key[0]
    )
    version_id = int(
        conn.execute(
            insert(posting_versions).values(
                posting_id=posting_id,
                content_hash=f"v-{key}",
                body_text=body,
                captured_at=NOW,
                capture_reason="new",
            )
        ).inserted_primary_key[0]
    )
    conn.execute(
        insert(artifacts).values(
            posting_version_id=version_id,
            kind="resume_tailored",
            uri=f"/out/{key}/tailored-{posting_id}.typ",
            generator="boardwatch.tailor",
            media_type="text/x-tex",
            meta_json={"pdf_uri": pdf_uri},
            created_at=delivered_at,
            run_id=run_id,
        )
    )
    if judge:
        # The profile too: `current_identity` reads the STORE, and with no profile saved it is
        # `(None, None)` — every verdict comes back `None` however many evaluations were written.
        # `save_profile` keys by content, so the callers that already store the same profile keep
        # the same identity.
        _profile(conn, facts=facts, policy=policy)
        _judge(conn, posting_id, body, facts=facts, policy=policy)
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
            posting_version_id=version_id,
            facts=used_facts,
            policy=used_policy,
            catalog=catalog,
            declared_fields=declared_fields(),
        ),
        result=result,
    )
    return result.verdict


def _gate(
    conn: Connection,
    posting_id: int,
    body: str,
    decision: str,
    *,
    facts: Facts | None = None,
    policy: Policy | None = None,
    seniority_fit: str = "unclear",
) -> None:
    """One FINAL-GATE verdict for `posting_id`'s current version, under the live identity.

    Through `record_gate_verdict` rather than a hand-inserted `engine_kind='llm'` row: the read
    behind `QueueRow.judge_verdict` is scoped to `engine_version LIKE 'final_gate:%'`, so a
    hand-written version constant here would read back under any implementation that hand-wrote
    the same constant — the vacuous shape `_judge` above avoids for the same reason.

    `confidence="low"` and `reason=None` keep an `ineligible` decision on the fail-open path
    (`accept_oracle_verdict` downgrades it to `uncertain`), which is why no caller below asks this
    for an `ineligible`.
    """
    catalog = load_rules(load_settings().config_dir)
    version_id = int(
        conn.execute(
            select(posting_versions.c.id).where(posting_versions.c.posting_id == posting_id)
        ).scalar_one()
    )
    record_gate_verdict(
        conn,
        posting_version_id=version_id,
        jd_text=body,
        facts=Facts() if facts is None else facts,
        policy=Policy() if policy is None else policy,
        catalog=catalog,
        verdict=OracleVerdict(
            label="synthetic",
            decision=decision,
            reason=None,
            evidence="",
            confidence="low",
            seniority_fit=seniority_fit,
        ),
    )


def _profile(conn: Connection, *, facts: Facts | None = None, policy: Policy | None = None) -> None:
    """The default pair is `None`/`None`, which leaves eligibility unsaved exactly as before —
    every existing caller keeps its current identity. Pass both to store a policy that can
    actually block."""
    save_profile(
        conn,
        text="resume",
        target_titles=["software engineer"],
        exclude_titles=[],
        locations=["Boston, MA"],
        remote_only=False,
        skills=["python"],
        taxonomy_version="v1",
        resume_max_pages=1,
    )
    if facts is not None and policy is not None:
        save_eligibility(
            conn, facts_json=facts_payload(facts), policy_json=policy.model_dump(mode="json")
        )


def _undelivered(conn: Connection, key: str, *, title: str = "Data Engineer") -> int:
    """A company and a posting with NO tailored artifact, returning the posting's canonical job.

    This is the shape of the applications imported from another tool's history: `import_history`
    matches a row against a real posting, so the job EXISTS, but nothing ever tailored a résumé
    for it — so the delivery queue never offered it and there is no `posting_id` for the web page
    to key a PDF or an unmark on.
    """
    company_id = int(
        conn.execute(
            insert(companies).values(
                name=f"Acme {key}",
                provider="greenhouse",
                slug=f"acme-{key}",
                source="user",
                watched=True,
            )
        ).inserted_primary_key[0]
    )
    job = int(conn.execute(insert(jobs).values(created_at=NOW)).inserted_primary_key[0])
    conn.execute(
        insert(postings).values(
            company_id=company_id,
            job_id=job,
            provider_posting_id=key,
            title=title,
            normalized_title=title.casefold(),
            url="https://careers.acme.test/apply",
            locations_json=["Austin, TX"],
            remote_policy="remote",
            posted_at=NOW - timedelta(days=9),
            first_seen_at=NOW,
            last_seen_at=NOW,
            status="open",
            consecutive_missing=0,
            content_hash=f"hash-{key}",
            body_text=JD_ELIGIBLE,
        )
    )
    return job


def _queue_folders(base: Path) -> list[str]:
    """Lead folders directly under `base`, sorted. Drain directories and dotfiles are not leads."""
    if not base.is_dir():
        return []
    return sorted(
        path.name
        for path in base.iterdir()
        if path.is_dir() and not path.name.startswith(".") and path.name not in DRAIN_DIRS
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

    foreign = call(live, "/api/queue", bearer=live.token, extra={"Origin": "https://evil.test"})
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
        row["posting_id"]: row for row in call(live, "/api/queue", bearer=live.token).json()["rows"]
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
        unwanted, _ = _deliver(conn, "swe2", title="Software Developer", delivered_at=NOW)

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
        row["posting_id"]: row for row in call(live, "/api/queue", bearer=live.token).json()["rows"]
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
        foreign, _ = _deliver(
            conn, "vilnius", title="Software Engineer", locations=["Kaunas, Lithuania"]
        )
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
        # `JD_ELIGIBLE` rather than `JD_UNCERTAIN` for both, so the TITLE is the only difference
        # that decides the lane. `JD_UNCERTAIN` carries no requirement row at all, which since A3
        # holds a lead on its own — both leads would land in `review` and `in_queue` would be 0,
        # which is a true count of a fixture that no longer exercises the role gate.
        software, _ = _deliver(
            conn,
            "swe",
            title="Software Engineer",
            body=JD_ELIGIBLE,
            facts=BLOCKING_FACTS,
            policy=BLOCKING_POLICY,
        )
        held, _ = _deliver(
            conn,
            "nurse",
            title="Registered Nurse Practitioner",
            body=JD_ELIGIBLE,
            facts=BLOCKING_FACTS,
            policy=BLOCKING_POLICY,
        )
        rejected, _ = _deliver(
            conn,
            "noauth",
            title="Software Engineer",
            body=JD_INELIGIBLE,
            facts=BLOCKING_FACTS,
            policy=BLOCKING_POLICY,
        )
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


def test_a_lead_whose_JD_states_no_requirement_is_listed_under_review_with_that_reason(
    live: Live, engine: Engine
) -> None:
    """A3 through the API, which is a DIFFERENT call site from the folder tree's (D-332).

    `JD_UNCERTAIN` carries no requirement at all, so a real evaluation of it produces zero rows —
    the 521-lead population. Both halves are asserted because they fail differently: dropping the
    new argument from `queue_payload`'s lane calls puts the lead back in `rows`, and dropping it
    from `_row_json`'s `classify` call leaves the row listed under `review` with a reason drawn
    from a branch that did not hold it.

    The control is the SAME shape with a stated requirement, which stays in `rows` — so the
    routing is attributable to the empty extraction and not to the body being short.
    """
    with engine.begin() as conn:
        silent, _ = _deliver(conn, "silent", body=JD_UNCERTAIN)
        stated, _ = _deliver(conn, "stated", body=JD_UNCERTAIN_STATED)
        assert _judge(conn, silent, JD_UNCERTAIN) == "uncertain"
        assert _judge(conn, stated, JD_UNCERTAIN_STATED) == "uncertain"

    payload = call(live, "/api/queue", bearer=live.token).json()
    assert [row["posting_id"] for row in payload["rows"]] == [stated]
    review = {row["posting_id"]: row for row in payload["review"]}
    assert silent in review
    assert review[silent]["review_reason"] == "no_requirements_found"
    assert payload["counts"]["review"] == 1


def test_an_unevaluated_lead_is_listed_under_review_as_unevaluated(
    live: Live, engine: Engine
) -> None:
    """The third case, through the API: nothing has judged this lead under the live profile.

    `judge=False` is what makes it real — the fixture stores a profile but writes no evaluation,
    which is the 34-lead population. Its reason must be `unevaluated` and not
    `no_requirements_found`: the two are separate members precisely because this one is transient.
    """
    with engine.begin() as conn:
        _profile(conn)
        unjudged, _ = _deliver(conn, "unjudged", judge=False)

    payload = call(live, "/api/queue", bearer=live.token).json()
    assert payload["rows"] == []
    review = {row["posting_id"]: row for row in payload["review"]}
    assert review[unjudged]["verdict"] is None
    assert review[unjudged]["review_reason"] == "unevaluated"


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
        conn.execute(update(postings).where(postings.c.id == dead_lead).values(status="closed"))

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

    # Both lists: `thin_jd` is a property of the JD, not of the lane, and a JD with no recognised
    # requirement is exactly the lead A3 now holds for review — so the thin one is under `review`.
    payload = call(live, "/api/queue", bearer=live.token).json()
    rows = {row["posting_id"]: row for row in payload["rows"] + payload["review"]}

    assert rows[measured]["thin_jd"] is False
    assert rows[measured]["coverage"] == 1.0

    assert rows[thin]["thin_jd"] is True
    assert rows[thin]["coverage"] is None

    # Non-vacuity, read on the surface the PAGE takes the terms from: the measured lead's detail
    # lists covered terms and none missing, which is what a fraction of 1.0 claims, and the thin
    # one lists no coverage terms at all — a fraction of 1.0 over nothing would be the same number
    # about a different thing. (The row itself carries the fraction alone; the term lists live on
    # the detail payload, where `_requirements_json` puts them.)
    assert _detail_coverage_terms(live, measured)[0], "premise: something was recognised"
    assert _detail_coverage_terms(live, measured)[1] == []
    assert _detail_coverage_terms(live, thin) == ([], [])


def _detail_coverage_terms(live: Live, posting_id: int) -> tuple[list[str], list[str]]:
    """The covered and missing résumé terms as the page receives them: the `rule`-less entries of
    the detail payload's requirement list, which is where `_requirements_json` puts them."""
    entries = call(live, f"/api/queue/{posting_id}", bearer=live.token).json()["requirements"]
    terms = [entry for entry in entries if entry["rule"] is None]
    return (
        [entry["requirement"] for entry in terms if entry["covered"]],
        [entry["requirement"] for entry in terms if not entry["covered"]],
    )


def test_the_row_payload_carries_no_coverage_detail(live: Live, engine: Engine) -> None:
    """`coverage_detail` was serialised on every row and read by nothing.

    The covered/missing terms the client actually renders come from `_requirements_json` on the
    DETAIL payload; `QueueRow` in `web/src/api/types.ts` never declared this key, so the lists were
    built and shipped for every row of every render and then dropped on the floor. Asserted as an
    ABSENT key rather than a null, because a null would still be a field the client could start
    reading.
    """
    resume = live.server.deps.ctx.settings.config_dir / "resume.yaml"
    resume.parent.mkdir(parents=True, exist_ok=True)
    resume.write_text(scaffold_template(), encoding="utf-8")
    with engine.begin() as conn:
        posting_id, _ = _deliver(conn, "python", body=JD_ELIGIBLE)

    payload = call(live, "/api/queue", bearer=live.token).json()
    (row,) = [r for r in payload["rows"] + payload["review"] if r["posting_id"] == posting_id]
    detail_row = call(live, f"/api/queue/{posting_id}", bearer=live.token).json()["row"]

    assert "coverage_detail" not in row
    assert "coverage_detail" not in detail_row
    # The information is not lost: it reaches the page through the detail's requirement list.
    assert _detail_coverage_terms(live, posting_id)[0]


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


def test_marking_applied_twice_appends_exactly_one_event(live: Live, engine: Engine) -> None:
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

    assert [
        row["posting_id"] for row in call(live, "/api/queue", bearer=live.token).json()["rows"]
    ] == [posting_id]

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
            select(application_events.c.event_type, application_events.c.to_status).order_by(
                application_events.c.id
            )
        ).all()
        rows = conn.execute(select(applications.c.status, applications.c.submitted_at)).all()
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


def test_a_batch_skip_is_one_write_that_drains_what_it_can_and_names_what_it_could_not(
    live: Live, engine: Engine, ctx: ApiContext
) -> None:
    """The bulk-skip contract, all of it: 200 for a batch that is only partly skippable, the two
    standing jobs in `skipped`, the id that is in no lane in `failed`, and BOTH folders under
    `_skipped/` — counted through the filesystem rather than through the response that claimed it.

    The unskippable id is checked in the same test as the skippable ones on this module's standing
    rule: a route that answered `failed` for everything would pass a refusal test on its own.
    """
    with engine.begin() as conn:
        one, job_one = _deliver(conn, "one")
        two, job_two = _deliver(conn, "two")
    with engine.connect() as conn:
        sync_queue(conn, root=ctx.queue_root, owner_name=ctx.owner_name)
    standing = _queue_folders(ctx.queue_root)
    assert len(standing) == 2, "two folders have to exist or the move below is unfalsifiable"

    answer = call(
        live,
        "/api/queue/skip",
        method="POST",
        bearer=live.token,
        body={"job_ids": [job_one, 999999, job_two]},
    )

    assert answer.status == 200, answer.body[:200]
    # Request order is preserved in both lists, so a client can pair an id with its outcome.
    assert answer.json() == {"skipped": [job_one, job_two], "failed": [999999]}
    # The FOLDERS, not the response: the drain is the deliverable and the response is the claim.
    assert _queue_folders(ctx.queue_root) == []
    assert _queue_folders(ctx.queue_root / SKIPPED_DIR) == standing

    page = call(live, "/api/queue", bearer=live.token).json()
    assert [row["posting_id"] for row in page["rows"] if row["posting_id"] in (one, two)] == []
    assert page["counts"]["skipped"] == 2
    # A skip is not an application, in a batch exactly as it is one at a time.
    assert page["counts"]["applied_ever"] == 0


def test_a_batch_unskip_returns_every_id_it_was_given_to_the_queue(
    live: Live, engine: Engine, ctx: ApiContext
) -> None:
    """The undo half. One call, so the toast's Undo is one write and not N."""
    with engine.begin() as conn:
        one, job_one = _deliver(conn, "one")
        two, job_two = _deliver(conn, "two")
    with engine.connect() as conn:
        sync_queue(conn, root=ctx.queue_root, owner_name=ctx.owner_name)
    standing = _queue_folders(ctx.queue_root)

    call(
        live,
        "/api/queue/skip",
        method="POST",
        bearer=live.token,
        body={"job_ids": [job_one, job_two]},
    )
    undone = call(
        live,
        "/api/queue/unskip",
        method="POST",
        bearer=live.token,
        body={"job_ids": [job_one, job_two]},
    )

    assert undone.status == 200, undone.body[:200]
    assert undone.json() == {"skipped": [job_one, job_two], "failed": []}
    assert _queue_folders(ctx.queue_root) == standing
    assert _queue_folders(ctx.queue_root / SKIPPED_DIR) == []
    page = call(live, "/api/queue", bearer=live.token).json()
    assert sorted(row["posting_id"] for row in page["rows"]) == sorted([one, two])
    assert page["counts"]["skipped"] == 0


def test_a_batch_skip_obeys_the_same_bearer_and_host_checks_as_every_other_route(
    live: Live, engine: Engine
) -> None:
    """The checks live in the dispatcher, so this asserts the batch route did not arrive with its
    own. Each refusal carries the request that SUCCEEDS, this module's standing rule."""
    with engine.begin() as conn:
        _one, job_one = _deliver(conn, "one")
    payload = {"job_ids": [job_one]}

    assert call(live, "/api/queue/skip", method="POST", bearer=None, body=payload).status == 401
    assert (
        call(
            live,
            "/api/queue/skip",
            method="POST",
            bearer=live.token,
            host="evil.test",
            body=payload,
        ).status
        == 403
    )
    assert (
        call(live, "/api/queue/skip", method="POST", bearer=live.token, body=payload).status == 200
    )


def test_a_batch_skip_refuses_a_body_that_is_not_a_list_of_job_ids(
    live: Live, engine: Engine
) -> None:
    """A malformed batch is a 400 and writes nothing — never a 500, and never a partial skip from
    a body the route could not read. `true` is rejected with the integers because Python reads a
    bool as an `int`, so a bare `isinstance` check would skip job 1."""
    with engine.begin() as conn:
        _one, job_one = _deliver(conn, "one")

    for body in ([job_one], {"job_ids": job_one}, {"job_ids": ["1"]}, {"job_ids": [True]}, {}):
        answer = call(live, "/api/queue/skip", method="POST", bearer=live.token, body=body)
        assert answer.status == 400, (body, answer.status, answer.body[:200])
    assert call(live, "/api/queue", bearer=live.token).json()["counts"]["skipped"] == 0

    assert (
        call(
            live,
            "/api/queue/skip",
            method="POST",
            bearer=live.token,
            body={"job_ids": [job_one]},
        ).status
        == 200
    )


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
    assert call(live, "/api/queue/999999/reported", method="POST", bearer=live.token).status == 404
    assert (
        call(live, f"/api/queue/{posting_id}/reported", method="POST", bearer=live.token).status
        == 200
    )


def test_marking_a_posting_that_does_not_exist_is_a_404(live: Live, engine: Engine) -> None:
    with engine.begin() as conn:
        posting_id, _job = _deliver(conn, "one")
    assert call(live, "/api/queue/999999/applied", method="POST", bearer=live.token).status == 404
    assert (
        call(live, f"/api/queue/{posting_id}/applied", method="POST", bearer=live.token).status
        == 200
    )


def test_the_applied_history_names_a_closed_lead_and_one_that_never_reached_the_queue(
    live: Live, engine: Engine
) -> None:
    """`GET /api/applied`, the third page's whole payload.

    Two applications, chosen because they are the two shapes the live store actually holds: one
    the queue delivered and the owner marked, whose posting the employer has since taken down,
    and one imported from another tool's history, whose job never reached the delivery queue at
    all. The second is what `posting_id: null` is FOR — the page has to say what was applied to
    without claiming a delivery that never happened, and a row that invented a posting id would
    hand the PDF and unmark controls an id the queue never offered.

    `posting_closed` counts the first and not the second, which is what makes it answerable at a
    recruiter call: applied, and the requisition is gone.
    """
    with engine.begin() as conn:
        closed_posting, _closed_job = _deliver(conn, "one", pdf_uri=None)
        conn.execute(
            update(postings)
            .where(postings.c.id == closed_posting)
            .values(status="closed", closed_at=NOW)
        )
        never_queued = _undelivered(conn, "two")
        create_application(
            conn,
            job_id=never_queued,
            status="applied",
            source="import",
            occurred_at=NOW - timedelta(days=5),
        )

    # Through the route the queue page uses, so the mark under test is the one it writes.
    marked = call(live, f"/api/queue/{closed_posting}/applied", method="POST", bearer=live.token)
    assert marked.status == 200

    response = call(live, "/api/applied", bearer=live.token)
    assert response.status == 200
    payload = response.json()
    # Newest first, and the imported row was applied to five days earlier.
    assert [row["posting_id"] for row in payload["rows"]] == [closed_posting, None]
    lead, imported = payload["rows"]

    assert lead["company"] == "Acme one"
    assert lead["title"] == "Software Engineer"
    assert lead["status"] == "applied"
    assert lead["posting_status"] == "closed"
    assert lead["closed_at"] == "2026-08-26T12:00:00+00:00"
    assert lead["source"] == "web"
    # No PDF was ever built for this lead, so the control the page offers must not claim one.
    assert lead["pdf_available"] is False
    assert lead["pdf_uri"] is None

    assert imported["company"] == "Acme two"
    assert imported["title"] == "Data Engineer"
    assert imported["location"] == "Austin, TX"
    assert imported["apply_url"] == "https://careers.acme.test/apply"
    assert imported["posting_status"] == "open"
    assert imported["closed_at"] is None
    assert imported["source"] == "import"
    # An explicit offset, never a naive timestamp: the store holds naive UTC and a browser reads
    # a bare timestamp as LOCAL time (D-485 finding 1).
    assert imported["submitted_at"] == "2026-08-21T12:00:00+00:00"

    counts = payload["counts"]
    assert counts["total"] == 2
    # The whole closed catalog every time, so a 0 here is a measurement rather than an absence.
    assert counts["by_status"] == {
        "interested": 0,
        "applied": 2,
        "interviewing": 0,
        "offer": 0,
        "rejected": 0,
        "withdrawn": 0,
    }
    assert counts["posting_closed"] == 1


def test_the_applied_row_describes_the_posting_the_application_was_made_against(
    live: Live, engine: Engine
) -> None:
    """`applications.posting_version_id` decides the row's posting, not `_supersedes`.

    The eBay shape `_supersedes` exists for: one job holding two delivered postings, an open
    requisition and a dead copy. `_delivered_winners` prefers the LIVE one (D-432), which is right
    for the queue — it is looking for work — and wrong here, because the owner applied against the
    copy that is now closed. Without this the page answers `posting_status: "open"`,
    `closed_at: null` and serves the résumé tailored for a requisition nobody applied to.

    `_deliver` mints a company per delivery, so the two postings here sit on sibling company rows;
    every assertion below is keyed on the posting id and its standing rather than on the name.
    """
    with engine.begin() as conn:
        live_posting, job = _deliver(conn, "live", pdf_uri="file:///out/live.pdf")
        dead_posting, _same = _deliver(
            conn,
            "dead",
            job_id=job,
            pdf_uri="file:///out/dead.pdf",
            delivered_at=NOW + timedelta(hours=1),
        )
        conn.execute(
            update(postings)
            .where(postings.c.id == dead_posting)
            .values(status="closed", closed_at=NOW)
        )
        applied_against = int(
            conn.execute(
                select(posting_versions.c.id).where(posting_versions.c.posting_id == dead_posting)
            ).scalar_one()
        )
        create_application(
            conn, job_id=job, posting_version_id=applied_against, status="applied"
        )

    row = call(live, "/api/applied", bearer=live.token).json()["rows"][0]
    assert row["posting_id"] == dead_posting
    assert row["posting_status"] == "closed"
    assert row["closed_at"] == "2026-08-26T12:00:00+00:00"
    # The résumé that went out, which is the one tailored for the requisition applied to.
    assert row["pdf_uri"] == "file:///out/dead.pdf"
    # The live sibling is still there and is still what the QUEUE would offer — this changed the
    # applied page's reading of one application, not the delivery rule.
    assert live_posting != dead_posting


def test_an_unresolvable_applied_version_keeps_the_delivery_queues_own_choice(
    live: Live, engine: Engine
) -> None:
    """The fallback, asserted so the branch above cannot be the only path that works.

    Two applications that name no usable version: one with `posting_version_id` NULL — every row
    `mark_job_applied` wrote before A4, and every row whose posting had no version — and one
    naming a version on a posting the queue never DELIVERED, which has no artifact and therefore
    no résumé or delivered id to offer. Both keep `_supersedes`' live winner.
    """
    with engine.begin() as conn:
        live_posting, job = _deliver(conn, "live", pdf_uri="file:///out/live.pdf")
        dead_posting, _same = _deliver(
            conn, "dead", job_id=job, delivered_at=NOW + timedelta(hours=1)
        )
        conn.execute(
            update(postings)
            .where(postings.c.id == dead_posting)
            .values(status="closed", closed_at=NOW)
        )
        create_application(conn, job_id=job, status="applied")

        undelivered_job = _undelivered(conn, "two")
        undelivered_version = int(
            conn.execute(
                insert(posting_versions).values(
                    posting_id=int(
                        conn.execute(
                            select(postings.c.id).where(postings.c.job_id == undelivered_job)
                        ).scalar_one()
                    ),
                    content_hash="v-two",
                    body_text=JD_ELIGIBLE,
                    captured_at=NOW,
                    capture_reason="new",
                )
            ).inserted_primary_key[0]
        )
        create_application(
            conn,
            job_id=undelivered_job,
            posting_version_id=undelivered_version,
            status="applied",
            occurred_at=NOW - timedelta(days=5),
        )

    rows = call(live, "/api/applied", bearer=live.token).json()["rows"]
    unnamed, never_delivered = rows
    assert unnamed["posting_id"] == live_posting
    assert unnamed["posting_status"] == "open"
    assert unnamed["pdf_uri"] == "file:///out/live.pdf"
    # Never delivered, so no posting id and no résumé — the posting's own facts still answer
    # "what was applied to".
    assert never_delivered["posting_id"] is None
    assert never_delivered["title"] == "Data Engineer"
    assert never_delivered["pdf_uri"] is None


def test_only_a_jobs_latest_submitted_attempt_offers_the_unmark(
    live: Live, engine: Engine
) -> None:
    """`can_unmark` per ROW, because the write behind it is per JOB.

    `mark_job_unapplied` resolves posting -> job -> `attempts[-1]`, so a control offered on an
    earlier attempt makes a promise about a row the reader did not click. Both orders are seeded
    here because they fail differently: with the submitted attempt FIRST the click answers
    `unchanged` and nothing happens, and with it SECOND the click withdraws an attempt further
    down the page.
    """
    with engine.begin() as conn:
        first_posting, first_job = _deliver(conn, "one")
        second_posting, second_job = _deliver(conn, "two")
        # Submitted attempt, then a `track add --new-attempt` row sitting at `interested`.
        early_applied = create_application(
            conn, job_id=first_job, status="applied", occurred_at=NOW - timedelta(days=5)
        )
        later_interested = create_application(conn, job_id=first_job, status="interested")
        # The inverted order: a dead earlier attempt under a live one.
        early_rejected = create_application(
            conn, job_id=second_job, status="rejected", occurred_at=NOW - timedelta(days=5)
        )
        later_applied = create_application(
            conn, job_id=second_job, status="applied", occurred_at=NOW - timedelta(days=1)
        )

    payload = call(live, "/api/applied", bearer=live.token).json()
    offered = {row["application_id"]: row["can_unmark"] for row in payload["rows"]}

    # Neither row on the first job: the latest attempt does not read as submitted, so there is
    # nothing to withdraw, and the earlier one is not the row the write would reach.
    assert offered[early_applied] is False
    assert offered[later_interested] is False
    # And on the second job exactly the row the write acts on, and only that row.
    assert offered[early_rejected] is False
    assert offered[later_applied] is True
    # The ids the page would key the control on are the delivered postings, not a sibling's.
    postings_by_application = {row["application_id"]: row["posting_id"] for row in payload["rows"]}
    assert postings_by_application[later_applied] == second_posting
    assert postings_by_application[later_interested] == first_posting


def test_an_undelivered_application_never_offers_the_unmark(live: Live, engine: Engine) -> None:
    """No posting id, so no control: every existing write route keys on one."""
    with engine.begin() as conn:
        never_queued = _undelivered(conn, "two")
        create_application(conn, job_id=never_queued, status="applied")

    row = call(live, "/api/applied", bearer=live.token).json()["rows"][0]
    assert row["posting_id"] is None
    assert row["can_unmark"] is False


def test_an_applied_leads_follow_up_reaches_the_applied_history_and_its_band(
    live: Live, engine: Engine
) -> None:
    """The gap T83 left: a follow-up SURVIVES `mark_job_applied` in the store, but `queue_payload`
    is built on `delivered_unapplied`, so an applied lead was in neither lane and no surface
    showed its date or let the owner set one — and the applied lead is exactly the one the owner
    follows up on.

    The count is per JOB, not per attempt: two attempts on one job carry the same date (the key is
    `queue.followup.<job_id>`), and counting both would report two pieces of work where there is
    one. `<=` today, so a date that slipped past unread is counted.
    """
    with engine.begin() as conn:
        posting_id, job_id = _deliver(conn, "one")
        # Two attempts, both reading as submitted, so the dedup is exercised rather than asserted
        # on a shape that cannot distinguish the two rules.
        create_application(
            conn, job_id=job_id, status="applied", occurred_at=NOW - timedelta(days=5)
        )
        create_application(conn, job_id=job_id, status="interviewing")
    today = local_today()
    call(live, f"/api/queue/{posting_id}/applied", method="POST", bearer=live.token)

    overdue = call(
        live,
        f"/api/queue/{posting_id}/followup",
        method="POST",
        bearer=live.token,
        body={"date": (today - timedelta(days=3)).isoformat()},
    )
    assert overdue.status == 200, overdue.body[:200]

    payload = call(live, "/api/applied", bearer=live.token).json()
    # Resolved on `job_id`, so every attempt on the job carries it — the store holds one date.
    assert [row["follow_up"] for row in payload["rows"]] == [
        (today - timedelta(days=3)).isoformat()
    ] * 2
    assert payload["counts"]["follow_up_due"] == 1

    # Tomorrow's date is pinned but not due, and the same two rows now count for nothing.
    later = call(
        live,
        f"/api/queue/{posting_id}/followup",
        method="POST",
        bearer=live.token,
        body={"date": (today + timedelta(days=1)).isoformat()},
    )
    assert later.status == 200, later.body[:200]
    future = call(live, "/api/applied", bearer=live.token).json()
    assert [row["follow_up"] for row in future["rows"]] == [
        (today + timedelta(days=1)).isoformat()
    ] * 2
    assert future["counts"]["follow_up_due"] == 0

    cleared = call(
        live, f"/api/queue/{posting_id}/unfollowup", method="POST", bearer=live.token
    )
    assert cleared.status == 200
    gone = call(live, "/api/applied", bearer=live.token).json()
    assert [row["follow_up"] for row in gone["rows"]] == [None, None]
    assert gone["counts"]["follow_up_due"] == 0


def test_a_withdrawn_attempts_follow_up_is_not_counted_as_due(
    live: Live, engine: Engine
) -> None:
    """`follow_up_due` is gated on `APPLIED_STATUSES`, exactly as `posting_closed` is: a withdrawn
    attempt is not an application anybody is waiting on, so its date is shown and not counted."""
    with engine.begin() as conn:
        posting_id, job_id = _deliver(conn, "one")
        create_application(conn, job_id=job_id, status="withdrawn")
    today = local_today()
    call(
        live,
        f"/api/queue/{posting_id}/followup",
        method="POST",
        bearer=live.token,
        body={"date": today.isoformat()},
    )

    payload = call(live, "/api/applied", bearer=live.token).json()
    # Shown on the row — the date is still pinned to the lead, which is the queue's business.
    assert payload["rows"][0]["follow_up"] == today.isoformat()
    assert payload["counts"]["follow_up_due"] == 0


def test_the_applied_history_is_read_only_and_needs_the_token(live: Live, engine: Engine) -> None:
    """A read, through `_read`, like `/api/queue`: no token is a 401 and a POST is not a route.

    The paired 200 is in the same test on purpose — a server that answered 401 or 404 to
    everything would pass both refusals on its own.
    """
    with engine.begin() as conn:
        posting_id, _job = _deliver(conn, "one")
    call(live, f"/api/queue/{posting_id}/applied", method="POST", bearer=live.token)

    assert call(live, "/api/applied", bearer=None).status == 401
    assert call(live, "/api/applied", method="POST", bearer=live.token).status == 404
    served = call(live, "/api/applied", bearer=live.token)
    assert served.status == 200
    assert len(served.json()["rows"]) == 1


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
        # `JD_UNCERTAIN_STATED`, not `JD_UNCERTAIN`: `in_queue` counts the APPLY lane, and since
        # A3 a body carrying no requirement row at all is held for review — which would make
        # `in_queue` 1 and, worse, make the `eligible != in_queue` discriminator below pass for
        # the wrong reason. This body abstains on a stated requirement instead, so the lead is
        # genuinely `uncertain` AND genuinely in the apply lane.
        vague, _ = _deliver(conn, "vague", body=JD_UNCERTAIN_STATED)
        assert _judge(conn, clear, JD_ELIGIBLE) == "eligible"
        assert _judge(conn, vague, JD_UNCERTAIN_STATED) == "uncertain"

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
        clear, _ = _deliver(
            conn, "clear", body=JD_ELIGIBLE, facts=BLOCKING_FACTS, policy=BLOCKING_POLICY
        )
        barred, _ = _deliver(
            conn, "barred", body=JD_INELIGIBLE, facts=BLOCKING_FACTS, policy=BLOCKING_POLICY
        )
        assert (
            _judge(conn, barred, JD_INELIGIBLE, facts=BLOCKING_FACTS, policy=BLOCKING_POLICY)
            == "ineligible"
        )
        # `JD_ELIGIBLE` rather than `JD_UNCERTAIN`: the claim under test is that a NON-ineligible
        # lead is still listed, and a zero-requirement body is now held for review on its own,
        # which would move the lead out of `rows` for a reason this test is not about.
        assert (
            _judge(conn, clear, JD_ELIGIBLE, facts=BLOCKING_FACTS, policy=BLOCKING_POLICY)
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


def test_every_row_carries_the_gates_own_verdict_and_it_is_counted_apart_from_the_rules_one(
    live: Live, engine: Engine
) -> None:
    """The final gate's verdict on the ROW and in its own three cells.

    The store has carried it since T42 and `classify` has read it since D-489; nothing emitted it,
    so a lead the gate read as `uncertain` was indistinguishable on the page from one it cleared.

    Three leads with the SAME body and therefore the same RULES verdict, so the only thing that
    differs between them is the gate. That is what makes this test discriminating: an
    implementation that echoed `verdict` into `judge_verdict` reports `eligible` three times and
    fails on the `uncertain` row, and one that treated "no gate row" as a clear reports
    `judge_eligible: 2`.

    The gate verdicts are written through `record_gate_verdict` and asserted on the payload rather
    than read back through the same query that produced them.
    """
    with engine.begin() as conn:
        _profile(conn)
        held, _ = _deliver(conn, "held", body=JD_ELIGIBLE)
        cleared, _ = _deliver(conn, "cleared", body=JD_ELIGIBLE)
        silent, _ = _deliver(conn, "silent", body=JD_ELIGIBLE)
        _gate(conn, held, JD_ELIGIBLE, "uncertain")
        _gate(conn, cleared, JD_ELIGIBLE, "eligible")

    payload = call(live, "/api/queue", bearer=live.token).json()
    rows = {row["posting_id"]: row for row in payload["rows"]}
    assert set(rows) == {held, cleared, silent}
    assert rows[held]["judge_verdict"] == "uncertain"
    assert rows[cleared]["judge_verdict"] == "eligible"
    # `None`, never omitted and never "eligible": no gate row exists for this lead, and "the gate
    # has not spoken" is not "the gate cleared it".
    assert rows[silent]["judge_verdict"] is None
    # The RULES verdict is untouched on all three, which is what makes the two columns two
    # opinions rather than one renamed twice.
    assert [rows[pid]["verdict"] for pid in (held, cleared, silent)] == ["eligible"] * 3

    counts = payload["counts"]
    assert counts["judge_uncertain"] == 1
    assert counts["judge_eligible"] == 1
    assert counts["judge_unjudged"] == 1
    # Stated out loud because the sum is the specific defect: an implementation that folded the
    # gate's uncertain into its eligible reports `judge_eligible: 2` and passes any `>= 1` check.
    assert counts["judge_eligible"] != counts["eligible"]
    assert counts["eligible"] == 3

    # `detail_payload` serializes one row with no list around it, through the same `_row_json`.
    # Asserted here so the field cannot exist on the list and be absent in the pane.
    detail = call(live, f"/api/queue/{held}", bearer=live.token).json()
    assert detail["row"]["judge_verdict"] == "uncertain"


def test_every_row_carries_the_gates_seniority_reading_the_badge_is_keyed_on(
    live: Live, engine: Engine
) -> None:
    """`judge_seniority_above_band` on the wire, as the boolean `QueueRowItem` keys its badge on.

    `types.ts` has said "the server has always sent this" since D-504. It never had: `_row_json`
    fed the reading into `classify` and dropped it, so the badge could not render against any
    real server and the test that covered it set the field in a fixture by hand.

    The hold is ARMED here because the store deliberately leaves the column at its inert
    `"unclear"` while it is off (`delivered_unapplied` does not run the seniority read at all),
    so an armed hold is the only state in which the wire can carry a `True`. Under it the
    above-band lead is held for review, and the field rides on THAT row too — `_row_json`
    serializes both lanes — while the cleared lead reads `False`, never an omitted key.
    """
    with engine.begin() as conn:
        _profile(conn)
        senior, _ = _deliver(conn, "senior", body=JD_ELIGIBLE)
        junior, _ = _deliver(conn, "junior", body=JD_ELIGIBLE)
        _gate(conn, senior, JD_ELIGIBLE, "eligible", seniority_fit="no")
        _gate(conn, junior, JD_ELIGIBLE, "eligible", seniority_fit="yes")
    config = live.server.deps.ctx.settings.config_dir / "config.toml"
    config.write_text("[gate]\nseniority_hold = true\n", encoding="utf-8")

    payload = call(live, "/api/queue", bearer=live.token).json()
    apply_rows = {row["posting_id"]: row for row in payload["rows"]}
    review_rows = {row["posting_id"]: row for row in payload["review"]}
    # The control: the hold really is armed, or the `True` below could not be reached.
    assert review_rows[senior]["review_reason"] == "seniority_judged_above_band"
    assert review_rows[senior]["judge_seniority_above_band"] is True
    assert apply_rows[junior]["judge_seniority_above_band"] is False


def test_a_form_hard_stop_reaches_the_page_with_the_question_it_quotes(
    live: Live, engine: Engine
) -> None:
    """T91 on the wire. The reason and its EVIDENCE travel together, and they have to: this is the
    one hold whose requirement is nowhere in the job description the pane renders beside it, so a
    chip that could not quote the form would send the reader to a JD that says nothing about it.

    The cache is written through the real sweep with a stub fetcher, so this pins the whole server
    path — store read, catalog match, `classify`, `_row_json` — rather than a hand-set field.
    """
    from boardwatch.delivery.form_questions import sweep_form_questions  # noqa: PLC0415

    question = "Are you currently a U. S. citizen?"

    class _Result:
        content = json.dumps(
            {"questions": [{"label": question, "description": None, "fields": []}]}
        ).encode()
        not_modified = False

    class _Fetcher:
        def get(self, url: str) -> _Result:
            return _Result()

    with engine.begin() as conn:
        _profile(conn)
        held, _ = _deliver(
            conn, "form", body=JD_ELIGIBLE,
            url="https://job-boards.greenhouse.io/tenet3/jobs/8810809002",
        )
        clear, _ = _deliver(conn, "clear", body=JD_ELIGIBLE)
    with engine.begin() as conn:
        sweep_form_questions(conn, fetcher=_Fetcher(), budget=10)  # type: ignore[arg-type]

    payload = call(live, "/api/queue", bearer=live.token).json()
    apply_rows = {row["posting_id"]: row for row in payload["rows"]}
    review_rows = {row["posting_id"]: row for row in payload["review"]}
    assert review_rows[held]["review_reason"] == "form_question_hard_stop"
    assert review_rows[held]["form_question"] == question
    # The two lists PARTITION the delivered set, and this is the assertion that says so. The
    # page splits them with two separate `lane()` calls; one of them omitting the form input
    # leaves the held lead in BOTH lists, and every other assertion here passes against that.
    assert held not in apply_rows
    assert clear not in review_rows
    # The lead is held WITHOUT a verdict being written: the form is not the frozen JD, so the
    # eligibility gate's own answer is untouched and still says this lead is eligible.
    assert review_rows[held]["verdict"] == "eligible"
    # The control: the non-Greenhouse lead is unheld, and the key is present as `null` rather
    # than omitted, so the page can tell "no hard stop" from "an older server".
    assert apply_rows[clear]["review_reason"] is None
    assert apply_rows[clear]["form_question"] is None
    # Same field through `_row_json`'s single-row path, so it cannot exist on the list and be
    # absent in the detail pane.
    detail = call(live, f"/api/queue/{held}", bearer=live.token).json()
    assert detail["row"]["form_question"] == question


def test_counts_report_the_last_finished_run(live: Live, engine: Engine) -> None:
    with engine.begin() as conn:
        run_id = _run(conn)
        _deliver(conn, "delivered", run_id=run_id)
        _deliver(conn, "older", run_id=None)

    counts = call(live, "/api/queue", bearer=live.token).json()["counts"]
    assert counts["delivered_last_run"] == 1
    assert counts["last_run_finished"] == NOW.replace(tzinfo=UTC).isoformat()


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
            "requirement",
            "covered",
            "rule",
            "disposition",
            "profile_field",
            "quote",
            "rationale",
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
        assert (
            call(live, "/api/queue", bearer=live.token).json()["meta"]["reveal_supported"] is False
        )
        unsupported = call(
            live, f"/api/queue/{posting_id}/reveal", method="POST", bearer=live.token
        ).json()
        assert unsupported["ok"] is False
        assert "sunos5" in unsupported["reason"]

    with serving(replace(ctx, platform="darwin")) as live:
        assert (
            call(live, "/api/queue", bearer=live.token).json()["meta"]["reveal_supported"] is True
        )
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


def test_the_runs_payload_carries_the_four_way_board_split(live: Live, engine: Engine) -> None:
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


def test_an_unusable_profile_row_is_answered_not_dropped(
    live: Live, engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T7 follow-up, found by review. `answers.py` reads the stored facts to prefill the
    work-authorisation answers, and T7 made that read RAISE on a malformed row instead of failing
    closed to an empty model. `ProfileRowInvalid` is a plain `ValueError`, so it matched none of
    the dispatcher's three handled types: it escaped to `ThreadingHTTPServer`'s default path,
    which prints a traceback to stderr and DROPS THE CONNECTION without a response. The browser
    then shows a bare network error for a condition that has a precise explanation.

    Answered as 503 with the COLUMN named, and deliberately not degraded to an empty prefill —
    that would hide a corrupt profile row behind a blank form field.
    """
    from boardwatch.eligibility.facts import ProfileRowInvalid

    # A real profile row has to exist, or `_profile_work_auth` returns early and never parses.
    with engine.begin() as conn:
        _profile(conn)

    def raiser(_raw: object) -> object:
        raise ProfileRowInvalid("eligibility_facts_json", "stray: Extra inputs are not permitted")

    monkeypatch.setattr("boardwatch.delivery.answers.parse_facts", raiser)

    response = call(live, "/api/answers", bearer=live.token)

    assert response.status == 503, response.body[:400]
    assert b"eligibility_facts_json" in response.body


# -------------------------------------------------------------- the web-viewer payload contract


def test_every_queue_timestamp_carries_an_explicit_utc_offset(live: Live, engine: Engine) -> None:
    """The store holds NAIVE UTC (`core/clock.utcnow` strips tzinfo). A zone-less ISO string is
    parsed by the browser as LOCAL time, so an owner at UTC-5 read a run that finished at 12:56 PM
    as 05:56 PM. The offset is the fix, and it belongs on the wire rather than in the client:
    `new Date()` on an offset-carrying string is right in every locale.
    """
    with engine.begin() as conn:
        run_id = _run(conn)
        _deliver(conn, "one", run_id=run_id)

    payload = call(live, "/api/queue", bearer=live.token).json()

    stamps = [payload["counts"]["last_run_finished"], payload["rows"][0]["first_seen"]]
    assert all(stamp is not None for stamp in stamps), payload["counts"]
    for stamp in stamps:
        assert stamp.endswith("+00:00"), stamp
        assert datetime.fromisoformat(stamp).tzinfo is not None, stamp
    # The instant is unchanged: the offset is attached to the stored naive value, never shifted.
    assert datetime.fromisoformat(payload["counts"]["last_run_finished"]) == NOW.replace(tzinfo=UTC)
    assert datetime.fromisoformat(payload["rows"][0]["first_seen"]) == NOW.replace(tzinfo=UTC)


def test_every_run_timestamp_carries_an_explicit_utc_offset(live: Live, engine: Engine) -> None:
    with engine.begin() as conn:
        _run(conn)

    run = call(live, "/api/runs", bearer=live.token).json()["runs"][0]

    for name in ("started", "finished"):
        assert run[name] is not None, run
        assert run[name].endswith("+00:00"), run[name]
    assert datetime.fromisoformat(run["finished"]) == NOW.replace(tzinfo=UTC)
    assert datetime.fromisoformat(run["started"]) == (NOW - timedelta(minutes=20)).replace(
        tzinfo=UTC
    )


def test_an_unfinished_run_still_reports_a_null_finished(live: Live, engine: Engine) -> None:
    """The control for the two above: attaching an offset must not turn "not finished yet" into
    a string. `_counts` reads only FINISHED runs, so this is the runs payload's case alone."""
    with engine.begin() as conn:
        _run(conn, finished=None)

    run = call(live, "/api/runs", bearer=live.token).json()["runs"][0]

    assert run["finished"] is None
    assert run["started"].endswith("+00:00")


def test_a_rows_locations_are_de_duplicated_and_location_is_the_first(
    live: Live, engine: Engine
) -> None:
    """The live store served "Austin, Texas, United States; Bozeman, …; …, Austin, Bozeman, …" —
    one list joined twice, with duplicates. `location` is now the PRIMARY location and `locations`
    the de-duplicated list, so the client renders "Austin, TX +1" instead of a wall of text.

    De-duplication is at the ENTRY level and case-insensitive on the trimmed entry; an entry is
    never split on its internal commas, or "Austin, TX" becomes two places.
    """
    with engine.begin() as conn:
        _deliver(conn, "one", locations=["Austin, TX", "austin, tx ", "Remote"])

    row = call(live, "/api/queue", bearer=live.token).json()["rows"][0]

    assert row["location"] == "Austin, TX"
    assert row["locations"] == ["Austin, TX", "Remote"]


def test_a_row_with_no_locations_reports_none_and_an_empty_list(live: Live, engine: Engine) -> None:
    with engine.begin() as conn:
        _deliver(conn, "one", locations=[])

    row = call(live, "/api/queue", bearer=live.token).json()["rows"][0]

    assert row["location"] is None
    assert row["locations"] == []


def test_the_answers_panel_serves_work_auth_words_not_enum_tokens(
    live: Live, engine: Engine
) -> None:
    """The panel exists to be COPIED into an employer's form. `ead_or_similar` pasted into "what
    is your work authorization status?" is a token from this program's catalog, not an answer a
    human wrote, so the profile's stored value is restated in the words the form expects.
    """
    facts = Facts(
        work_authorization=WorkAuthFact(
            status="ead_or_similar", jurisdiction="us", needs_sponsorship=False
        )
    )
    with engine.begin() as conn:
        _profile(conn, facts=facts, policy=Policy())

    work_auth = call(live, "/api/answers", bearer=live.token).json()["work_auth"]

    assert work_auth["status"] == "EAD or similar (work authorization document)"
    # Already true before this change, asserted so it stays true: a raw `True` on a form is not
    # an answer to "do you need sponsorship".
    assert work_auth["needs_sponsorship"] == "no"


def test_the_answers_panel_serves_the_jurisdiction_in_words_too(
    live: Live, engine: Engine
) -> None:
    """`us` is this catalog's token for a country, not the answer a form asks for.

    The same argument as the status above, on the field beside it: the panel exists to be COPIED,
    and a two-letter code pasted into "which country is that authorisation for?" is this program's
    vocabulary reaching an employer.
    """
    facts = Facts(
        work_authorization=WorkAuthFact(status="citizen", jurisdiction="us", needs_sponsorship=False)
    )
    with engine.begin() as conn:
        _profile(conn, facts=facts, policy=Policy())

    work_auth = call(live, "/api/answers", bearer=live.token).json()["work_auth"]

    assert work_auth["jurisdiction"] == "United States"


def test_a_jurisdiction_outside_the_catalog_is_passed_through_rather_than_refused(
    live: Live, engine: Engine
) -> None:
    """The one place this field parts company with `status`, asserted so the asymmetry is
    deliberate rather than an omission.

    An unrecognised `status` is refused because `ead_or_similar` has no meaning outside this
    program and a corrupt one must not reach a form. A jurisdiction the catalog does not declare is
    a stored value the panel already served verbatim before it was restated at all, so refusing it
    would take a working panel to a 422 over a field restating was only ever meant to improve.
    Passed through unchanged, and never dropped: a blank would hide the stored fact entirely.
    """
    facts = Facts(work_authorization=WorkAuthFact(status="citizen", jurisdiction="zz"))
    with engine.begin() as conn:
        _profile(conn, facts=facts, policy=Policy())

    response = call(live, "/api/answers", bearer=live.token)

    assert response.status == 200, response.body[:400]
    assert response.json()["work_auth"]["jurisdiction"] == "zz"


#: The catalog's own `work_auth.status` vocabulary, read from the BUNDLED rules rather than
#: respelled here: the choice vocabulary belongs to the catalog (D-P2-4), and a list retyped in a
#: test would go on passing after the catalog gained a sixth member.
WORK_AUTH_STATUS_CHOICES: tuple[str, ...] = next(
    field.choices
    for field in load_rules(Path("/nonexistent")).family("work_auth").fields
    if field.name == "status"
)


@pytest.mark.parametrize("status", WORK_AUTH_STATUS_CHOICES)
def test_every_declared_work_auth_status_has_words(status: str) -> None:
    """The mapping is CLOSED over the catalog's declared choices. Parametrised over the catalog so
    a new member ships with words or fails here — a member with none would otherwise reach an
    employer's form as a raw token, which is the bug this closes."""
    assert status in WORK_AUTH_STATUS_WORDS
    assert WORK_AUTH_STATUS_WORDS[status] != status


#: The catalog's own `work_auth.jurisdiction` vocabulary, read from the BUNDLED rules for the same
#: reason the status list above is.
WORK_AUTH_JURISDICTION_CHOICES: tuple[str, ...] = next(
    field.choices
    for field in load_rules(Path("/nonexistent")).family("work_auth").fields
    if field.name == "jurisdiction"
)


@pytest.mark.parametrize("jurisdiction", WORK_AUTH_JURISDICTION_CHOICES)
def test_every_declared_work_auth_jurisdiction_has_words(jurisdiction: str) -> None:
    """Closed over the catalog's declared choices, so a new member ships with words. Unlike the
    status mapping this one does not REFUSE an unlisted value, which is exactly why its coverage
    has to be asserted here: a missing member would otherwise be served as a raw token forever
    instead of failing."""
    assert jurisdiction in WORK_AUTH_JURISDICTION_WORDS
    assert WORK_AUTH_JURISDICTION_WORDS[jurisdiction] != jurisdiction


def test_a_work_auth_status_outside_the_catalog_is_refused_not_copied(
    live: Live, engine: Engine
) -> None:
    """Out-of-catalog is a failure, never a new bucket. Passing the unknown token through would
    put it on the clipboard, which is exactly what the words mapping exists to prevent; answering
    with a blank would hide a corrupt profile row behind an empty form field."""
    facts = Facts(work_authorization=WorkAuthFact(status="not_a_catalog_status"))
    with engine.begin() as conn:
        _profile(conn, facts=facts, policy=Policy())

    response = call(live, "/api/answers", bearer=live.token)

    assert response.status == 422, response.body[:400]
    assert response.json()["issue"] == "unknown_work_auth_status"
    # `AnswersViolation` carries no VALUE by construction; the field is named, its content is not.
    assert b"not_a_catalog_status" not in response.body


def test_the_favicon_is_served_and_the_ico_request_is_not_a_404(
    live: Live, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every page load asked for `/favicon.ico` and got a 404 in the console. The bundle carries
    `favicon.svg` (Vite copies `public/` to the static root), which is served here; `.ico` is what
    a browser asks for unprompted and is answered without content rather than refused.

    `static_root` is redirected because the favicon is added to the bundle by the client half of
    this change, and the bundle is rebuilt once after both land.
    """
    bundle = tmp_path / "bundle"
    (bundle / "assets").mkdir(parents=True)
    (bundle / "favicon.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"/>', "utf-8")
    monkeypatch.setattr(server_mod, "static_root", lambda: bundle)

    svg = call(live, "/favicon.svg", bearer=None)
    assert svg.status == 200
    assert svg.headers["content-type"] == "image/svg+xml"
    assert svg.body.startswith(b"<svg")

    ico = call(live, "/favicon.ico", bearer=None)
    assert ico.status != 404, ico.body[:200]

    # The control: the closed asset-name rule is untouched, so widening it is not what made the
    # two requests above succeed.
    assert call(live, "/assets/../../etc/passwd", bearer=None).status == 404


def test_the_queue_payload_carries_the_fields_the_client_halves_are_built_against(
    live: Live, engine: Engine
) -> None:
    """`counts.closed`, `meta.reveal_supported` and `row.why` were audited as already emitted and
    are asserted here as ONE statement about a default payload, so the client halves that consume
    them are not built against a field that only exists in a special-cased test."""
    with engine.begin() as conn:
        _deliver(conn, "one")

    payload = call(live, "/api/queue", bearer=live.token).json()

    assert payload["counts"]["closed"] == 0
    assert payload["meta"]["reveal_supported"] is True
    assert "why" in payload["rows"][0]


def test_a_rows_provider_is_the_company_row_and_not_the_apply_urls_host(
    live: Live, engine: Engine
) -> None:
    """`provider` is the ATS the posting SITS ON, carried from `companies.provider`.

    The lane row below is seeded with an apply URL on an ATS vendor's own host — which is what
    the job-apps lane really writes — so a `provider` derived from the URL would report
    `greenhouse` for it. The `classify_host` control states that the host really does read as
    `ats`, so the payload's `jobapps` is attributable to the company row and nothing else.

    The DETAIL payload is asserted in the same test because it serializes through `_row_json`:
    that is what makes one field emitted once rather than twice, and the assertion is what
    keeps it that way.
    """
    with engine.begin() as conn:
        lane, _ = _deliver(
            conn, "lane", provider="jobapps", url="https://boards.greenhouse.io/acme/jobs/1"
        )

    row = call(live, "/api/queue", bearer=live.token).json()["rows"][0]
    assert classify_host(row["apply_url"]) == "ats"
    assert row["provider"] == "jobapps"

    detail = call(live, f"/api/queue/{lane}", bearer=live.token).json()
    assert detail["row"]["provider"] == "jobapps"


def test_a_semicolon_joined_location_entry_is_split_into_places(tmp_path: Path) -> None:
    """The live store holds one "A; B; C" entry beside "A", "B", "C": the primary must be a place,
    never the joined dump, and the split entries de-duplicate against the plain ones."""
    from boardwatch.delivery.api import _unique_locations

    joined = "Austin, Texas, United States; Bozeman, Montana, United States; Free Solo"
    assert _unique_locations(
        [joined, "Austin, Texas, United States", "bozeman, montana, united states"]
    ) == [
        "Austin, Texas, United States",
        "Bozeman, Montana, United States",
        "Free Solo",
    ]


# ----------------------------------------------------------------------------------- follow-up


def test_a_follow_up_date_is_set_read_back_on_the_row_and_the_detail_and_cleared(
    live: Live, engine: Engine
) -> None:
    """The whole round trip in one test, on this module's standing rule: a route that answered
    `null` for everything would pass a "clearing works" test on its own."""
    with engine.begin() as conn:
        posting_id, _job = _deliver(conn, "one")

    before = call(live, "/api/queue", bearer=live.token).json()
    assert before["rows"][0]["follow_up"] is None

    set_ = call(
        live,
        f"/api/queue/{posting_id}/followup",
        method="POST",
        bearer=live.token,
        body={"date": "2026-09-20"},
    )
    assert set_.status == 200, set_.body[:200]
    assert set_.json() == {"outcome": "follow_up_set", "follow_up": "2026-09-20"}

    after = call(live, "/api/queue", bearer=live.token).json()
    assert [row["follow_up"] for row in after["rows"]] == ["2026-09-20"]
    detail = call(live, f"/api/queue/{posting_id}", bearer=live.token).json()
    assert detail["row"]["follow_up"] == "2026-09-20"
    # A note, not a disposition: the lead is still in the lane it was in, and no other dimension
    # moved. This is what makes follow-up NOT a fourth kind of skip.
    assert [row["posting_id"] for row in after["rows"]] == [posting_id]
    assert after["counts"]["skipped"] == 0
    assert after["counts"]["reported"] == 0
    assert after["counts"]["applied_ever"] == 0

    cleared = call(
        live, f"/api/queue/{posting_id}/unfollowup", method="POST", bearer=live.token
    )
    assert cleared.status == 200, cleared.body[:200]
    assert cleared.json() == {"outcome": "follow_up_cleared", "follow_up": None}
    back = call(live, "/api/queue", bearer=live.token).json()
    assert [row["follow_up"] for row in back["rows"]] == [None]
    assert [row["posting_id"] for row in back["rows"]] == [posting_id]


def test_a_follow_up_survives_the_lead_being_marked_applied(live: Live, engine: Engine) -> None:
    """The reason the feature exists: an applied lead is exactly the one the owner follows up on.

    Counted through the STORE rather than through the queue payload that would have claimed it —
    an applied lead is no longer a row, so the payload cannot answer this question at all.
    """
    with engine.begin() as conn:
        posting_id, job_id = _deliver(conn, "one")

    call(
        live,
        f"/api/queue/{posting_id}/followup",
        method="POST",
        bearer=live.token,
        body={"date": "2026-09-20"},
    )
    applied = call(live, f"/api/queue/{posting_id}/applied", method="POST", bearer=live.token)
    assert applied.status == 200, applied.body[:200]

    page = call(live, "/api/queue", bearer=live.token).json()
    assert page["rows"] == []
    assert page["counts"]["applied_ever"] == 1
    with engine.connect() as conn:
        assert followup_job_dates(conn) == {job_id: "2026-09-20"}
    # And the detail still serves it, which is the only surface that can still show it.
    detail = call(live, f"/api/queue/{posting_id}", bearer=live.token).json()
    assert detail["row"]["follow_up"] == "2026-09-20"


def test_setting_a_follow_up_moves_no_folder(
    live: Live, engine: Engine, ctx: ApiContext
) -> None:
    """A follow-up is a note ON a lead. Skip and report each drain a folder; this must not, and
    the filesystem is what says so rather than the response that claimed it."""
    with engine.begin() as conn:
        posting_id, _job = _deliver(conn, "one")
    with engine.connect() as conn:
        sync_queue(conn, root=ctx.queue_root, owner_name=ctx.owner_name)
    standing = _queue_folders(ctx.queue_root)
    assert len(standing) == 1, "a folder has to exist or a no-move assertion is unfalsifiable"

    call(
        live,
        f"/api/queue/{posting_id}/followup",
        method="POST",
        bearer=live.token,
        body={"date": "2026-09-20"},
    )

    assert _queue_folders(ctx.queue_root) == standing
    for drain in DRAIN_DIRS:
        assert _queue_folders(ctx.queue_root / drain) == []


@pytest.mark.parametrize(
    "body",
    [
        {"date": "tomorrow"},           # prose
        {"date": "2026-13-01"},         # out of range
        {"date": "2026-09-20T09:00"},   # an instant, not a date
        {"date": "20/09/2026"},         # a different notation
        {"date": ""},                   # empty: clearing is its own route
        {"date": None},                 # null: clearing is its own route
        {"date": 20260920},             # a number
        {"when": "2026-09-20"},         # the wrong key
        {},                             # no key at all
    ],
)
def test_a_malformed_follow_up_date_is_refused_with_a_named_reason(
    live: Live, engine: Engine, body: Any
) -> None:
    with engine.begin() as conn:
        posting_id, job_id = _deliver(conn, "one")

    refused = call(
        live, f"/api/queue/{posting_id}/followup", method="POST", bearer=live.token, body=body
    )

    assert refused.status == 400, refused.body[:200]
    assert refused.json()["error"] == FOLLOWUP_DATE_REASON
    # Nothing was written. A parser that refuses AFTER writing is the failure worth naming.
    with engine.connect() as conn:
        assert followup_job_dates(conn) == {}
    # The paired success, in the same test: a route that answered 400 to everything would pass
    # every case above on its own.
    ok = call(
        live,
        f"/api/queue/{posting_id}/followup",
        method="POST",
        bearer=live.token,
        body={"date": "2026-09-20"},
    )
    assert ok.status == 200, ok.body[:200]
    with engine.connect() as conn:
        assert followup_job_dates(conn) == {job_id: "2026-09-20"}


def test_a_follow_up_more_than_a_year_out_is_refused_as_a_fat_finger(
    live: Live, engine: Engine
) -> None:
    """A mistyped year is the realistic slip — `2036` for `2026` — and it would park a lead's
    follow-up a decade away where nothing would ever surface it again. 366 days is the bound, so
    "this time next year" on a leap year is still accepted."""
    with engine.begin() as conn:
        posting_id, _job = _deliver(conn, "one")
    today = local_today()

    too_far = call(
        live,
        f"/api/queue/{posting_id}/followup",
        method="POST",
        bearer=live.token,
        body={"date": (today + timedelta(days=367)).isoformat()},
    )
    assert too_far.status == 400, too_far.body[:200]
    assert too_far.json()["error"] == FOLLOWUP_RANGE_REASON

    edge = call(
        live,
        f"/api/queue/{posting_id}/followup",
        method="POST",
        bearer=live.token,
        body={"date": (today + timedelta(days=366)).isoformat()},
    )
    assert edge.status == 200, edge.body[:200]


def test_a_follow_up_more_than_a_year_in_the_PAST_is_refused_in_the_same_words(
    live: Live, engine: Engine
) -> None:
    """The guard is two-sided because the slip is: a mistyped year lands in the past as readily as
    in the future (`2016` for `2026`), and the date input's own segment order makes `0202-09-20` a
    value the keyboard walks through on the way to `2026-09-20`. A date that far back is `<= today`,
    so it would render as "follow-up due 0202-09-20" and count in `follow_up_due` forever.

    A RECENT past date is still accepted: overdue is a real state and the count exists to surface
    it."""
    with engine.begin() as conn:
        posting_id, job_id = _deliver(conn, "one")
    today = local_today()

    too_old = call(
        live,
        f"/api/queue/{posting_id}/followup",
        method="POST",
        bearer=live.token,
        body={"date": (today - timedelta(days=367)).isoformat()},
    )
    assert too_old.status == 400, too_old.body[:200]
    # The SAME named reason in both directions: one guard, one sentence to reword.
    assert too_old.json()["error"] == FOLLOWUP_RANGE_REASON
    with engine.connect() as conn:
        assert followup_job_dates(conn) == {}

    overdue = call(
        live,
        f"/api/queue/{posting_id}/followup",
        method="POST",
        bearer=live.token,
        body={"date": (today - timedelta(days=3)).isoformat()},
    )
    assert overdue.status == 200, overdue.body[:200]
    edge = call(
        live,
        f"/api/queue/{posting_id}/followup",
        method="POST",
        bearer=live.token,
        body={"date": (today - timedelta(days=366)).isoformat()},
    )
    assert edge.status == 200, edge.body[:200]
    with engine.connect() as conn:
        assert followup_job_dates(conn) == {job_id: (today - timedelta(days=366)).isoformat()}


def test_the_follow_up_due_count_is_dates_up_to_today_and_no_further(
    live: Live, engine: Engine
) -> None:
    """`follow_up_due` is "what is due", so it is `<= today` and never `== today`: a date that
    slipped past unread is the one the owner most needs counted."""
    with engine.begin() as conn:
        overdue, _ = _deliver(conn, "overdue")
        today_row, _ = _deliver(conn, "today")
        later, _ = _deliver(conn, "later")
    today = local_today()
    for posting_id, on in (
        (overdue, today - timedelta(days=3)),
        (today_row, today),
        (later, today + timedelta(days=1)),
    ):
        answer = call(
            live,
            f"/api/queue/{posting_id}/followup",
            method="POST",
            bearer=live.token,
            body={"date": on.isoformat()},
        )
        assert answer.status == 200, answer.body[:200]

    counts = call(live, "/api/queue", bearer=live.token).json()["counts"]

    # Two of three: the overdue one and today's. Tomorrow's is pinned but not due.
    assert counts["follow_up_due"] == 2
    assert counts["in_queue"] == 3


def test_local_today_is_the_servers_own_zone_and_never_utc() -> None:
    """The date a follow-up is written in is the one on the owner's wall calendar.

    UTC+14 and UTC-12 are 26 hours apart, so their local dates ALWAYS differ — which is exactly
    what `utcnow().date()` cannot produce, since it answers the same date in both. That is the
    assertion: a UTC implementation makes these two equal.
    """
    original = os.environ.get("TZ")
    try:
        os.environ["TZ"] = "Pacific/Kiritimati"  # UTC+14
        time.tzset()
        ahead = local_today()
        os.environ["TZ"] = "Etc/GMT+12"  # UTC-12
        time.tzset()
        behind = local_today()
    finally:
        if original is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = original
        time.tzset()

    assert ahead != behind
    assert 1 <= (ahead - behind).days <= 2

"""lanes.indeed against the authored payload in `indeed_shape.py`.

Two halves, and the first exists to make the second worth anything. An authored fixture proves
only what our own code constructs, so before any client behaviour is asserted the fixture's four
traps are checked: a `recruit.viewJobUrl` that resolves keys the company under its REAL provider,
one carrying `/apply` chrome REFUSES rather than keying on the constant `apply`, two employers
sharing a display name are two companies, and `datePublished` is read in UTC rather than in the
running machine's zone.

**The dereference assertion carries its own vacuity control.**
`test_the_dereference_is_load_bearing_not_incidental` runs the identical fixture with
`board_posting_target` stubbed to always return None and asserts the companies land under
`indeed` instead. Without it, the positive test would agree with an implementation that never
called the resolver at all.

Every request is mocked. Nothing in this file reaches the network -- this lane presents a
vendor's own app credentials against a host whose `robots.txt` is `Disallow: /`, so the suite
must never exercise it live.
"""

from __future__ import annotations

import inspect
import json
import re
from dataclasses import replace
from datetime import date
from pathlib import Path

import httpx
import pytest
import respx
from indeed_shape import (
    DEREFERENCE_HITS,
    GARBAGE_VIEW_JOB_URL_HIT,
    KNOWN_PROVIDER_UNROUTABLE_SEED_HIT,
    LOCAL_MIDNIGHT_HIT,
    MALFORMED_VIEW_JOB_URL_HIT,
    NAME_COLLISION_HITS,
    NO_BODY_HIT,
    NO_EMPLOYER_PAGE_HIT,
    REVIEW_BY,
    TENANT_SEED_HIT,
    TRAILING_CHROME_HIT,
    UNIDENTIFIABLE_TENANT_SEED_HIT,
    Hit,
    error_response,
    job_dict,
    search_hits,
    search_response,
)
from sqlalchemy import select
from typer.testing import CliRunner

from boardwatch.cli.app import app
from boardwatch.core.politeness import Fetcher
from boardwatch.core.settings import Settings, load_settings
from boardwatch.lanes import indeed
from boardwatch.lanes.base import Lane, LaneContext
from boardwatch.lanes.facets import LaneFacets
from boardwatch.lanes.indeed import (
    LANE_PROVIDER,
    SEARCH_URL,
    IndeedLane,
    SearchPageError,
)
from boardwatch.pipeline.runner import _collect_lane, _refused_seed_note
from boardwatch.store import tables
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.queries import get_watched_companies, insert_run

runner = CliRunner()

# (facet term, cursor) -> the page to answer with. `""` is the unfaceted search and `None` is the
# first page of any facet, which is exactly how the lane spells them on the wire.
_Page = tuple[list[Hit], str | None]


def _fetcher(tmp_path: Path) -> Fetcher:
    return Fetcher(
        Settings(
            data_dir=tmp_path, config_dir=tmp_path, retry_attempts=1,
            per_host_delay_seconds=0.25,
        )
    )


def _query_of(request: httpx.Request) -> str:
    body = json.loads(request.content.decode("utf-8"))
    assert set(body) == {"query"}, f"the POST body carries more than the query: {sorted(body)}"
    return str(body["query"])


def _term_of(request: httpx.Request) -> str:
    """The facet the request asks for, read back off the wire rather than off the lane.

    Read from the request the lane actually sent, so a routing test cannot agree with whatever
    argument the implementation chose to send -- including none at all.
    """
    found = re.search(r'what: "((?:[^"\\]|\\.)*)"', _query_of(request))
    return json.loads(f'"{found.group(1)}"') if found else ""


def _cursor_of(request: httpx.Request) -> str | None:
    found = re.search(r'cursor: "((?:[^"\\]|\\.)*)"', _query_of(request))
    return json.loads(f'"{found.group(1)}"') if found else None


def _mock(pages: dict[tuple[str, str | None], _Page]) -> respx.Route:
    """Answer each (facet, cursor) with its page; anything else is a loud failure.

    An unexpected request raises rather than returning a 404, because a 404 is a `FetchFailure`
    the lane is DESIGNED to absorb per facet -- so a mis-routed request would be swallowed and
    the test would report a benign empty facet instead of the routing bug.
    """

    def _respond(request: httpx.Request) -> httpx.Response:
        key = (_term_of(request), _cursor_of(request))
        if key not in pages:
            raise AssertionError(f"the lane requested an unmocked page: {key!r}")
        hits, cursor = pages[key]
        return httpx.Response(200, text=search_response(hits, next_cursor=cursor))

    return respx.post(SEARCH_URL).mock(side_effect=_respond)


def _mock_one(hits: list[Hit], *, next_cursor: str | None = None) -> respx.Route:
    """The unfaceted first page, for tests that do not care about routing."""
    return _mock({("", None): (hits, next_cursor)})


def _collect(lane: IndeedLane, tmp_path: Path, admits: bool = True):
    return lane.collect(_fetcher(tmp_path), lambda provider, slug: admits)


# ---------------------------------------------------------------------------------------
# The fixture traces to the recorded field list, and its traps have content.
# ---------------------------------------------------------------------------------------


def test_the_authored_payload_reproduces_the_recorded_hit_fields():
    """key, title, employer, location, datePublished, description.html, recruit.viewJobUrl."""
    hits = search_hits()
    page = indeed.parse_search_page(search_response(hits, next_cursor="abc").encode("utf-8"))

    assert len(page.hits) == 8
    assert page.next_cursor == "abc"
    for job, hit in zip(page.hits, hits, strict=True):
        identity = indeed.hit_identity(job)
        assert identity.provider == LANE_PROVIDER
        assert identity.posting_id == hit.key
        assert identity.slug == (hit.employer_page or "").rsplit("/", 1)[-1]
        assert indeed.company_name(job) == hit.employer_name
        posting = indeed.raw_posting(job, identity)
        assert posting is not None
        assert posting.title == hit.title
        assert posting.locations == [hit.location]
        assert "responsibilities" in posting.body_text.lower()


def test_an_absent_next_cursor_reads_as_no_further_page():
    """`None` rather than "", so a renamed field stops the facet instead of paging on page one."""
    page = indeed.parse_search_page(search_response(search_hits(1)).encode("utf-8"))
    assert page.next_cursor is None


def test_the_authored_shape_carries_a_review_deadline():
    """R15 in spirit: a shape that still parses can have been overtaken months ago.

    Red here is actionable at arm time: re-confirm the field list and the response envelope
    against the live endpoint, then roll `REVIEW_BY` in `tests/unit/indeed_shape.py` forward with
    a reason.
    """
    assert date.today() <= REVIEW_BY, (
        f"the Indeed GraphQL shape was last reviewed before {REVIEW_BY}. Re-confirm the field "
        "list and the response envelope and roll the deadline forward with a reason."
    )


# ---------------------------------------------------------------------------------------
# The request. One shape, and the arguments it must and must not carry.
# ---------------------------------------------------------------------------------------


@respx.mock
def test_the_request_is_a_graphql_post_with_the_hours_form_date_filter(tmp_path):
    """The date filter is HOURS. An ISO timestamp is refused outright with `BAD_USER_INPUT`.

    Asserted as the literal the endpoint accepts rather than by re-deriving it from the module,
    which would agree with any spelling the module chose -- including the one that fails.
    """
    route = _mock_one(search_hits(1))

    _collect(IndeedLane(), tmp_path)

    query = _query_of(route.calls[0].request)
    assert 'filters: { date: { field: "dateOnIndeed", start: "24h" } }' in query
    assert "sort: RELEVANCE" in query
    assert "limit: 100" in query
    assert query.lstrip().startswith("query GetJobData {")
    # An ISO timestamp anywhere in the filter is the form that is REFUSED.
    assert not re.search(r"start:\s*\"\d{4}-\d{2}-\d{2}", query)
    # The fields the mapping reads are asked for.
    for field in ("key", "title", "datePublished", "description", "recruit", "viewJobUrl"):
        assert field in query


@respx.mock
def test_no_location_argument_is_ever_sent(tmp_path):
    """Location is a fact a downstream rule must be able to ABSTAIN on, so the query must not
    pre-empt it -- and there is no metro written down here to send in the first place.
    """
    route = _mock({("software engineer", None): (search_hits(1), None)})

    _collect(IndeedLane(search_facets=("software engineer",)), tmp_path)

    query = _query_of(route.calls[0].request)
    assert "location:" not in query
    assert "radius" not in query


@respx.mock
def test_the_indeed_app_headers_are_sent_on_the_request(tmp_path):
    """The endpoint answers only to these. Sent PER REQUEST so they cannot leak onto the other
    lanes sharing one `Fetcher`, which is why `post_json` grew a `headers` argument at all.
    """
    route = _mock_one(search_hits(1))

    _collect(IndeedLane(), tmp_path)

    headers = route.calls[0].request.headers
    assert headers["indeed-api-key"] == indeed._INDEED_APP_IDENT
    assert "Indeed App 193.1" in headers["user-agent"]
    assert "appid=com.indeed.jobsearch" in headers["indeed-app-info"]
    assert headers["indeed-locale"] == "en-US"
    # The lane fetcher's own browser UA must NOT be what reached this host.
    assert "Chrome/" not in headers["user-agent"]


def test_a_facet_is_escaped_into_one_graphql_string():
    """Facets come from user PROFILE data, so a quote, a backslash or a newline in a target title
    is ordinary input -- and the reference implementation's `.replace('"', '\\\\"')` handles
    exactly one of the three. A broken literal here would not narrow the search; it would make
    every request this lane sends a syntax error.
    """
    query = indeed.search_query('sr "staff" \\ engineer\nbackend', limit=100)

    assert 'what: "sr \\"staff\\" \\\\ engineer\\nbackend"' in query
    # The `what:` argument closes exactly once, so nothing escaped into a second argument.
    assert len(re.findall(r"what:", query)) == 1


def test_no_facet_omits_the_what_argument_rather_than_sending_an_empty_one():
    """A profile naming no target titles is a legitimate profile: it is what every user has
    before onboarding fills one in. `what: ""` is a different ask from no `what:` at all.
    """
    assert "what:" not in indeed.search_query("", limit=100)
    assert "cursor:" not in indeed.search_query("", limit=100)
    assert 'cursor: "c2"' in indeed.search_query("", cursor="c2", limit=100)


@respx.mock
def test_the_results_per_page_ceiling_reaches_the_wire(tmp_path):
    route = _mock_one(search_hits(1))

    _collect(IndeedLane(results_per_page=25), tmp_path)

    assert "limit: 25" in _query_of(route.calls[0].request)


def test_a_results_per_page_above_the_measured_maximum_is_clamped():
    """100 is the only page size measured against this endpoint. Above it is a guess, and a lane
    constructed directly must not send one.
    """
    assert IndeedLane(results_per_page=500)._results_per_page == 100
    assert IndeedLane(results_per_page=0)._results_per_page == 1
    assert IndeedLane(search_pages=0)._search_pages == 1


# ---------------------------------------------------------------------------------------
# Identity: the dereference, and what happens when it does not resolve.
# ---------------------------------------------------------------------------------------


@respx.mock
def test_a_view_job_url_that_resolves_registers_under_the_real_provider(tmp_path):
    """The most valuable field in the response. Filing these under `indeed` instead would put
    three employers on a provider no board scan can ever reach.
    """
    _mock_one(DEREFERENCE_HITS)

    result = _collect(IndeedLane(), tmp_path)

    assert {(s.provider, s.slug) for s in result.snapshots} == {
        ("greenhouse", "vertexsystems"),
        ("lever", "beaconlabs"),
        ("ashby", "halcyonworks"),
    }
    # The posting id is the PROVIDER's, which is what makes the convergence with a later board
    # scan exact through UNIQUE(company_id, provider_posting_id) rather than a duplicate row.
    by_provider = {s.provider: s.snapshot.postings[0].provider_posting_id for s in result.snapshots}
    assert by_provider["greenhouse"] == "6000001"
    assert by_provider["lever"] == "a1000000-0000-0000-0000-000000000001"
    assert by_provider["ashby"] == "ashby-0001"
    # And none of them is Indeed's own key, which is what a lane that skipped the step would have.
    assert not any(value.startswith("key") for value in by_provider.values())


@respx.mock
def test_the_dereference_is_load_bearing_not_incidental(tmp_path, monkeypatch):
    """THE VACUITY CONTROL for the test above. With the resolver stubbed dead, the identical
    fixture must land under `indeed` -- so the positive assertion cannot be passing for any
    reason other than the dereference actually running.
    """
    monkeypatch.setattr(indeed, "board_posting_target", lambda apply_url: None)
    _mock_one(DEREFERENCE_HITS)

    result = _collect(IndeedLane(), tmp_path)

    assert {s.provider for s in result.snapshots} == {LANE_PROVIDER}
    assert {s.slug for s in result.snapshots} == {
        "Vertex-Systems", "Beacon-Labs", "Halcyon-Works"
    }


@respx.mock
def test_a_converged_hit_declares_every_declarable_field_secondhand(tmp_path):
    """D-414(a). Convergence claims WHICH posting this is -- never to own the provider's columns.

    A tier-1 hit is filed under a real provider's `(company_id, provider_posting_id)`, and
    `scan/apply.py`'s D25 rule refreshes every provider-sourced column on any positive
    observation regardless of `content_hash`. This lane never read the provider's
    `remote_policy`, `department` or `salary_*`, and the location it did read is Indeed's index
    of the posting; with `location_filter_mode = "hard"` writing that over the provider's row
    hard-vetoes a lead the pipeline already held, in the same run.

    `body_text` IS IN THE SET AND IS THE MOST CONSEQUENTIAL MEMBER. The other fields move a score
    or a filter; the body decides a VERDICT, because `scan/apply.py` makes a differing content
    hash the current `posting_versions` row and that row is what every eligibility rule quotes.

    The expected set is spelled out as a LITERAL rather than compared against
    `indeed.CONVERGED_SECONDHAND`, which is derived from `SecondhandField` and would agree with
    itself however either one changes. A new declarable field therefore reddens this test on
    purpose: somebody has to decide whether a converged Indeed hit owns it.
    """
    _mock_one(DEREFERENCE_HITS)

    result = _collect(IndeedLane(), tmp_path)

    declared = {frozenset(s.snapshot.postings[0].secondhand) for s in result.snapshots}
    assert declared == {
        frozenset(
            {
                "title", "url", "locations", "remote_policy", "department",
                "posted_at", "updated_at", "body_text", "salary", "raw_json",
            }
        )
    }


@respx.mock
def test_an_indeed_keyed_hit_declares_nothing_secondhand(tmp_path):
    """Tier 2, and the reason the declaration rides on the IDENTITY rather than on the lane.

    A hit keyed under `indeed`'s own employer key lands on a row this lane is the only observer
    of and will ever be -- no board scan reaches it (D-314). A rank attached to the lane as a
    whole would freeze these rows; the tier decides, so they keep refreshing normally.
    """
    _mock_one(search_hits(2, companies=2))

    result = _collect(IndeedLane(), tmp_path)

    assert result.snapshots
    assert all(s.snapshot.postings[0].secondhand == frozenset() for s in result.snapshots)


@respx.mock
def test_a_tier1_convergence_asks_for_its_board_to_be_watched(tmp_path):
    """Blockers 1 & 2 (D-414(a)). A tier-1 hit sits on a provider the scanner CAN parse, so the
    lane sets `watch=True` on its snapshot -- the drain that lets the next scan replace the
    secondhand body this hit wrote with the employer's own JD. `watch=provider != LANE_PROVIDER`,
    asserted as the tier, so a lane that stopped setting it reddens rather than silently leaving a
    lane-first tier-1 board scanned by nothing.
    """
    _mock_one(DEREFERENCE_HITS)

    result = _collect(IndeedLane(), tmp_path)

    assert {s.provider for s in result.snapshots} == {"greenhouse", "lever", "ashby"}
    assert all(s.watch is True for s in result.snapshots)


@respx.mock
def test_a_tier2_indeed_keyed_hit_does_not_ask_for_watching(tmp_path):
    """Tier 2 is keyed under `indeed`, a board no scan can reach, so it stays unwatched: a watched
    row on a provider the scanner cannot parse would add an `unknown provider` line to every run
    forever (D-285). The pair with the test above pins the flag to the TIER, not to the lane.
    """
    _mock_one(search_hits(2, companies=2))

    result = _collect(IndeedLane(), tmp_path)

    assert result.snapshots
    assert all(s.provider == LANE_PROVIDER and s.watch is False for s in result.snapshots)


@respx.mock
def test_a_tier1_convergence_is_watched_after_the_lane_applies_end_to_end(tmp_path):
    """The whole chain, read back off the store. The lane sets `watch`, `_apply_lane` threads it
    into `upsert_lane_company`, and the company lands `watched=True` -- so the next scan drains
    the secondhand JD. Verified through `get_watched_companies`, the ONLY source of the scan's
    companies, so a broken link anywhere from the snapshot flag to the stored column reddens.
    """
    engine = get_engine(tmp_path / "store")
    ensure_schema(engine)
    settings = Settings(data_dir=tmp_path / "store", config_dir=tmp_path / "cfg")
    _mock_one(DEREFERENCE_HITS)

    _collect_lane(engine, settings, IndeedLane(), _fetcher(tmp_path), insert_run(engine))

    with engine.connect() as conn:
        watched = {(r.provider, r.slug) for r in get_watched_companies(conn)}
    assert watched == {
        ("greenhouse", "vertexsystems"),
        ("lever", "beaconlabs"),
        ("ashby", "halcyonworks"),
    }


@respx.mock
def test_a_tier2_hit_lands_unwatched_after_the_lane_applies_end_to_end(tmp_path):
    """The tier-2 arm of the chain. The two indeed-keyed companies DO land -- the lane's postings
    still reach the shortlist -- but `watched=False`, so no scan is ever asked to reach a board
    that does not exist. The company count is the CONTROL that they landed at all.
    """
    engine = get_engine(tmp_path / "store")
    ensure_schema(engine)
    settings = Settings(data_dir=tmp_path / "store", config_dir=tmp_path / "cfg")
    _mock_one(search_hits(2, companies=2))

    _collect_lane(engine, settings, IndeedLane(), _fetcher(tmp_path), insert_run(engine))

    with engine.connect() as conn:
        watched = [r.slug for r in get_watched_companies(conn)]
        total = len(conn.execute(select(tables.companies)).all())
    assert watched == []
    assert total == 2


@respx.mock
def test_a_trailing_apply_segment_falls_back_to_indeed_rather_than_keying_on_apply(tmp_path):
    """`apply` is CONSTANT per provider, so reading it as a posting reference collides two real
    postings at one employer on UNIQUE(company_id, provider_posting_id) -- the second is applied
    as a revision of the first and one real body is overwritten. `parse_posting_target` refuses
    it, and the lane must take the refusal rather than work around it.
    """
    _mock_one([TRAILING_CHROME_HIT])

    result = _collect(IndeedLane(), tmp_path)

    (snapshot,) = result.snapshots
    assert (snapshot.provider, snapshot.slug) == (LANE_PROVIDER, "Beacon-Labs")
    assert snapshot.snapshot.postings[0].provider_posting_id == "key9101"


@respx.mock
def test_a_hit_with_no_apply_url_uses_indeeds_own_employer_key(tmp_path):
    """Tier 2. The `/cmp/` segment is Indeed's employer RECORD, which is what two listings of one
    employer agree on -- unlike a display name, which `companies` is not unique on.
    """
    _mock_one(search_hits(2, companies=2))

    result = _collect(IndeedLane(), tmp_path)

    assert {(s.provider, s.slug) for s in result.snapshots} == {
        (LANE_PROVIDER, "Acme-00"),
        (LANE_PROVIDER, "Acme-01"),
    }
    assert {s.name for s in result.snapshots} == {"Acme 00", "Acme 01"}


@respx.mock
def test_two_employers_sharing_a_display_name_form_two_companies(tmp_path):
    """The trap: grouping by display name would apply two employers' postings against one
    `company_id`, where the loser's postings can never converge and close after two misses.
    """
    _mock_one(NAME_COLLISION_HITS)

    result = _collect(IndeedLane(), tmp_path)

    assert {(s.provider, s.slug) for s in result.snapshots} == {
        (LANE_PROVIDER, "Vertex-Analytics"),
        (LANE_PROVIDER, "Vertex-Robotics"),
    }


@respx.mock
def test_a_hit_with_no_employer_page_is_counted_not_dropped(tmp_path):
    """It REFUSES rather than slugifying the display name, and the refusal is counted. A silent
    drop is what the closed outcome catalog exists to prevent.
    """
    _mock_one([NO_EMPLOYER_PAGE_HIT, *search_hits(1)])

    result = _collect(IndeedLane(), tmp_path)

    assert result.tally.counts["not_attemptable"] == 1
    assert [s.slug for s in result.snapshots] == ["Acme-00"]


@respx.mock
def test_a_hit_with_no_title_is_counted_not_dropped(tmp_path):
    _mock_one([replace(search_hits(1)[0], title="")])

    result = _collect(IndeedLane(), tmp_path)

    assert result.tally.counts["not_attemptable"] == 1
    assert result.snapshots == ()


@respx.mock
def test_a_second_hit_for_one_posting_is_dropped_before_it_reaches_apply_board(tmp_path):
    """An aggregator MAY serve one posting twice, and two rows with one `provider_posting_id`
    violate UNIQUE(company_id, provider_posting_id) inside `apply_board`'s single transaction --
    rolling the whole board back and taking every later company's results with it.
    """
    duplicate = search_hits(1)[0]
    _mock({
        ("software engineer", None): ([duplicate], None),
        ("backend engineer", None): ([duplicate], None),
    })

    result = _collect(
        IndeedLane(search_facets=("software engineer", "backend engineer")), tmp_path
    )

    stored = [p.provider_posting_id for s in result.snapshots for p in s.snapshot.postings]
    assert stored == ["key0000"]
    assert result.tally.counts["body_inline"] == 1
    # Seen on the second facet and not taken again. Counted, never dropped in silence.
    assert result.tally.counts["not_attemptable"] == 1


# ---------------------------------------------------------------------------------------
# Tenant seeds: the tier-D handoff to `lane_seeds` (D-413).
# ---------------------------------------------------------------------------------------


def test_a_view_job_url_naming_no_recognized_board_is_seeded(tmp_path):
    """The tier-D case. No provider is registered for this host, so `UnregisteredBoardHost`
    is the signal that a real employer board exists and this repo has no adapter for it at
    all. The expected URL is a LITERAL, not `TENANT_SEED_HIT.view_job_url`: a fixture
    mutation that broke the fixture's own contract must not also break what this test
    expects, or the assertion is checking the fixture against itself.
    """
    seed = indeed.tenant_seed_url(job_dict(TENANT_SEED_HIT))
    assert seed == "https://careers.example-hcm.com/en/sites/CX_1/job/9601"


@respx.mock
def test_a_hit_whose_view_job_url_is_unrecognized_is_seeded_through_collect(tmp_path):
    """End to end through `collect`: the seed rides in `LaneResult.discovered_seeds`, and the hit is
    STILL keyed under `indeed` (tier 2) the same way any other apply-url-less hit would be --
    seeding is additive, not a substitute for the existing fallback.
    """
    _mock_one([TENANT_SEED_HIT])

    result = _collect(IndeedLane(), tmp_path)

    assert result.discovered_seeds == ("https://careers.example-hcm.com/en/sites/CX_1/job/9601",)
    assert {(s.provider, s.slug) for s in result.snapshots} == {
        (LANE_PROVIDER, "Example-Manufacturing")
    }


@respx.mock
def test_a_view_job_url_that_resolves_is_not_seeded(tmp_path):
    """Tier 1 already applies this hit under the real provider THIS run. Seeding it too would
    hand a resolver a URL a board scan already owns.
    """
    _mock_one(DEREFERENCE_HITS)

    result = _collect(IndeedLane(), tmp_path)

    assert result.discovered_seeds == ()


@respx.mock
def test_a_control_character_view_job_url_never_reaches_the_seed_queue(tmp_path):
    """The persistence path. `a.test` is unregistered, so pre-fix a NUL-bearing url on it would
    ride `discovered_seeds` into `lane_seeds` and then fail every fetch as `InvalidURL`. It must
    never enter the queue; the hit is still keyed under `indeed` (tier 2) like any other.
    """
    hit = replace(TENANT_SEED_HIT, key="key9900", view_job_url="https://a.test/job/\x00x")
    _mock_one([hit])

    result = _collect(IndeedLane(), tmp_path)

    assert result.discovered_seeds == ()
    assert {(s.provider, s.slug) for s in result.snapshots} == {
        (LANE_PROVIDER, "Example-Manufacturing")
    }


@respx.mock
def test_a_recognized_board_url_with_no_evidenced_reference_is_not_seeded(tmp_path):
    """THE DISTINGUISHING TRAP. `TRAILING_CHROME_HIT` names a real lever URL this repo already
    has an adapter for; only its posting reference is unreadable (`UnresolvablePostingURL`). That
    is a URL-shape defect, not a missing tenant, and a client that seeded every
    `board_posting_target`-failure indiscriminately would seed this too.
    """
    _mock_one([TRAILING_CHROME_HIT])

    result = _collect(IndeedLane(), tmp_path)

    assert result.discovered_seeds == ()


@respx.mock
def test_a_hit_with_no_apply_url_is_not_seeded(tmp_path):
    """Nothing to hand a resolver: an absent `viewJobUrl` is not a URL of any kind."""
    _mock_one(search_hits(1))

    result = _collect(IndeedLane(), tmp_path)

    assert result.discovered_seeds == ()


@respx.mock
def test_an_unidentifiable_hit_is_still_seeded(tmp_path):
    """Seeding is read off the raw search entries, not off `_group_by_company`'s output: a hit
    `hit_identity` refuses entirely (no employer page, so `UnidentifiableHit`) still carries a
    real, unrecognized board URL, and gating the seed on grouping would silently drop exactly the
    hits with the least other trace of themselves.
    """
    _mock_one([UNIDENTIFIABLE_TENANT_SEED_HIT])

    result = _collect(IndeedLane(), tmp_path)

    assert result.discovered_seeds == ("https://careers.example-hcm.com/en/sites/CX_1/job/9701",)
    assert result.tally.counts["not_attemptable"] == 1
    assert result.snapshots == ()


@respx.mock
def test_a_refused_companys_hit_is_still_seeded(tmp_path):
    """A seed is not a write against this run's company cap -- it is a URL for a LATER resolver
    lane to spend its own budget on -- so refusing the company must not cost the seed.
    """
    _mock_one([TENANT_SEED_HIT])

    result = _collect(IndeedLane(), tmp_path, admits=False)

    assert result.discovered_seeds == ("https://careers.example-hcm.com/en/sites/CX_1/job/9601",)
    assert result.snapshots == ()


@respx.mock
def test_two_hits_naming_the_same_unresolved_tenant_url_seed_it_once(tmp_path):
    """Deduplicated in the lane, in first-seen order, rather than left for the store's conflict
    clause to absorb one row at a time.
    """
    second = replace(TENANT_SEED_HIT, key="key9602", title="Software Engineer II")
    _mock_one([TENANT_SEED_HIT, second])

    result = _collect(IndeedLane(), tmp_path)

    assert result.discovered_seeds == ("https://careers.example-hcm.com/en/sites/CX_1/job/9601",)


def test_a_known_providers_url_with_no_extractable_slug_is_not_seeded(tmp_path):
    """THE BLOCKER TRAP. `apply.workable.com/j/ABC123` is Workable's own bare shortlink -- a
    REGISTERED provider -- and `parse_posting_target` refuses it with the `UnknownBoardURL` BASE
    class because it carries no org. An unregistered host raises the `UnregisteredBoardHost`
    subclass, so both share the same `except UnknownBoardURL` catcher; a client keying its seed
    decision on that catcher alone would file a known provider's posting into the tier-D queue.
    Only `UnregisteredBoardHost` -- a distinct, narrower exception -- may seed.
    """
    seed = indeed.tenant_seed_url(job_dict(KNOWN_PROVIDER_UNROUTABLE_SEED_HIT))

    assert seed is None


@respx.mock
def test_a_known_providers_unroutable_hit_is_not_seeded_through_collect(tmp_path):
    _mock_one([KNOWN_PROVIDER_UNROUTABLE_SEED_HIT])

    result = _collect(IndeedLane(), tmp_path)

    assert result.discovered_seeds == ()


def test_a_malformed_view_job_url_is_not_seeded(tmp_path):
    """THE BLOCKER TRAP, second half. `https://[broken` makes `urlparse` raise a bare
    `ValueError` inside `core/board_urls.py`, converted there to the `UnknownBoardURL` BASE class --
    the same catcher, but NOT the `UnregisteredBoardHost` subclass an unregistered host raises. Not
    a URL in any usable sense, let alone a tenant.
    """
    seed = indeed.tenant_seed_url(job_dict(MALFORMED_VIEW_JOB_URL_HIT))

    assert seed is None


@respx.mock
def test_a_malformed_view_job_url_is_not_seeded_through_collect(tmp_path):
    """A malformed `viewJobUrl` must cost this seed and nothing else -- the hit still falls
    through to tier 2 and is applied normally."""
    _mock_one([MALFORMED_VIEW_JOB_URL_HIT])

    result = _collect(IndeedLane(), tmp_path)

    assert result.discovered_seeds == ()
    assert {(s.provider, s.slug) for s in result.snapshots} == {
        (LANE_PROVIDER, "Halcyon-Works")
    }


@respx.mock
def test_a_malformed_view_job_url_surfaces_as_a_visible_refusal_note(tmp_path):
    """BLOCKER 3, through the REAL producer. A malformed `viewJobUrl` used to be dropped silently by
    `tenant_seed_url` -- invisible past the `not_attemptable` tally, never reaching a note. It must
    now ride `LaneResult.refused_seeds` so the runner turns it into a visible operator line, WITHOUT
    the ordinary "known provider / no vendor" case (which correctly returns None) becoming noise.

    Two malformed shapes -- an IP literal and an unbalanced bracket -- ride `refused_seeds`; the
    known-provider shortlink does NOT. `_refused_seed_note` is what `_run_lanes` appends, so a
    non-None note here is the visible line an operator sees.
    """
    ip_hit = replace(TENANT_SEED_HIT, key="key9700", view_job_url="https://127.0.0.1:443/job/1")
    _mock_one([ip_hit, MALFORMED_VIEW_JOB_URL_HIT, KNOWN_PROVIDER_UNROUTABLE_SEED_HIT])

    result = _collect(IndeedLane(), tmp_path)

    # Both malformed URLs are carried, in first-seen order; neither becomes a discovered seed, and
    # the ordinary known-provider shortlink is NOT treated as a refusal.
    assert result.refused_seeds == ("https://127.0.0.1:443/job/1", "https://[broken")
    assert result.discovered_seeds == ()
    note = _refused_seed_note("indeed", result)
    assert note is not None and "malformed" in note and "127.0.0.1" in note


def test_an_ordinary_unseedable_hit_produces_no_refusal_note(tmp_path):
    """The control that keeps the note from becoming noise. A known provider's un-slugged shortlink
    and a hit with no apply URL both return None from `tenant_seed_url` for ordinary reasons -- not
    a malformed producer value -- so NOTHING rides `refused_seeds` and no note is produced."""
    _mock_one([KNOWN_PROVIDER_UNROUTABLE_SEED_HIT, *search_hits(1)])

    result = _collect(IndeedLane(), tmp_path)

    assert result.refused_seeds == ()
    assert _refused_seed_note("indeed", result) is None


def test_a_non_absolute_garbage_string_is_not_seeded(tmp_path):
    """`urlparse` does not raise on this at all -- once `parse_board_target` prepends a scheme,
    it returns a literal, space-containing string as the "hostname". `parse_posting_target` then
    raises the `UnknownBoardURL` BASE class (a space-bearing host matches no provider), NOT the
    `UnregisteredBoardHost` subclass a real unrecognized vendor raises -- but the seed never gets
    that far: `_is_addressable_url`'s own check (a scheme, a real hostname, no embedded whitespace
    or control chars) rejects it first.
    """
    seed = indeed.tenant_seed_url(job_dict(GARBAGE_VIEW_JOB_URL_HIT))

    assert seed is None


@pytest.mark.parametrize(
    ("value", "addressable"),
    [
        ("https://example.com/job/1", True),
        ("https://ex\tample.com/job/1", False),  # `urlsplit` strips the tab; the recorded url keeps it
        ("https://exa\nmple.com/job/1", False),  # a newline, stripped the same WHATWG way
        ("https://example.com/a b", False),       # a raw space in the path
        ("https://a.test/job/\x00x", False),      # NUL -- not whitespace, but HTTPX rejects it at fetch
        ("https://a.test/job/\x7fx", False),      # DEL -- the other char `isspace()` misses
        ("https://a.test:99999/x", False),        # a port outside 0-65535 -- `.port` raises here
        ("https://127.0.0.1:443/job/1", False),   # a bare IPv4 literal -- no host filter is an address
        ("https://[::1]/job/1", False),           # a bare IPv6 literal, same reason
        ("https://tést.applytojob.com/apply/ABC/Title", True),  # IDN -- valid via its punycode form
    ],
)
def test_is_addressable_url_rejects_whitespace_control_chars_and_a_bad_port(value, addressable):
    """`_is_addressable_url` guards the STRING that gets recorded. Raw whitespace anywhere fails it
    even where `urlsplit` would parse a clean host; NUL and DEL fail it too (they are not
    `isspace()` but HTTPX rejects them as `InvalidURL` at fetch); and a port outside 0-65535 fails
    it because `parsed.port` raises `ValueError` on it here rather than only downstream."""
    assert indeed._is_addressable_url(value) is addressable


def test_an_out_of_range_port_is_not_seeded_though_the_bare_host_would_be(tmp_path):
    """The port is the ONLY difference: `a.test` is unregistered, so a well-formed url on it seeds,
    but an out-of-range port makes `_is_addressable_url` refuse the value outright (`parsed.port`
    raises) -- a value HTTPX would reject at fetch never reaches the tier-D queue."""
    assert indeed.tenant_seed_url({"recruit": {"viewJobUrl": "https://a.test/x"}}) == "https://a.test/x"
    assert indeed.tenant_seed_url({"recruit": {"viewJobUrl": "https://a.test:99999/x"}}) is None


def test_an_ip_literal_view_job_url_is_not_seeded_but_an_idn_host_is(tmp_path):
    """The round-6 blocker, at the Indeed producer. A bare IP literal routes to no resolver, so it
    must NOT seed (against HEAD `is_seedable_url` accepted `127.0.0.1` and it seeded an undrainable
    row). An unregistered IDN host is a real tier-D board whose punycode form HTTPX dials and whose
    stored unicode host a suffix filter selects, so it MUST seed -- refusing it dropped a live URL.
    """
    assert indeed.tenant_seed_url({"recruit": {"viewJobUrl": "https://127.0.0.1:443/job/1"}}) is None
    assert indeed.tenant_seed_url({"recruit": {"viewJobUrl": "https://[::1]/job/1"}}) is None
    assert (
        indeed.tenant_seed_url(
            {"recruit": {"viewJobUrl": "https://tést.example-hcm.com/en/sites/CX_1/job/9601"}}
        )
        == "https://tést.example-hcm.com/en/sites/CX_1/job/9601"
    )


def test_a_control_character_in_the_view_job_url_is_not_seeded(tmp_path):
    """NUL and DEL are not whitespace, so `isspace()` alone let them through -- but HTTPX rejects
    such a URL as `InvalidURL` at fetch, AFTER it has persisted as a seed. `a.test` is an
    unregistered host, so without the control-char guard the bad string would be seeded."""
    assert indeed.tenant_seed_url({"recruit": {"viewJobUrl": "https://a.test/job/\x00x"}}) is None
    assert indeed.tenant_seed_url({"recruit": {"viewJobUrl": "https://a.test/job/\x7fx"}}) is None


def test_a_dns_root_dot_known_provider_url_is_not_seeded(tmp_path):
    """`boards.greenhouse.io.` names the SAME registered host as `boards.greenhouse.io`; the DNS
    root dot must not let a known provider's board fall through to the tier-D queue."""
    seed = indeed.tenant_seed_url(
        {"recruit": {"viewJobUrl": "https://boards.greenhouse.io./acme/jobs/123"}}
    )
    assert seed is None


def test_a_view_job_url_with_an_embedded_tab_is_not_seeded(tmp_path):
    """`urlsplit` strips the tab and routes as `example.com`, but `lane_seeds.url` would record the
    original tab-bearing string -- a url no fetch log could match. Not seeded."""
    seed = indeed.tenant_seed_url({"recruit": {"viewJobUrl": "https://ex\tample.com/job/1"}})
    assert seed is None


@pytest.mark.parametrize(
    "url",
    [
        "not a url at all",
        "",
        "ftp://careers.example-hcm.com/job/1",
        "https://",
        "https://[broken",
        "careers.example-hcm.com/job/1",  # no scheme at all -- board_urls.py would still accept it
    ],
)
def test_is_addressable_url_rejects_non_absolute_and_malformed_values(url):
    assert indeed._is_addressable_url(url) is False


def test_is_addressable_url_accepts_a_real_absolute_url():
    assert indeed._is_addressable_url("https://careers.example-hcm.com/job/1") is True


# ---------------------------------------------------------------------------------------
# collect: admission, the inline body, and the snapshot it builds.
# ---------------------------------------------------------------------------------------


def test_the_lane_satisfies_the_protocol():
    assert IndeedLane.name == "indeed"
    assert list(inspect.signature(IndeedLane.collect).parameters) == list(
        inspect.signature(Lane.collect).parameters
    ) == ["self", "fetcher", "admits"]
    # Position is asserted because the registry passes every argument by name and one that landed
    # in front of another would still typecheck. There is deliberately NO `posting_budget`: this
    # lane makes no body request, so a ceiling on body requests would bound a constant zero.
    assert list(inspect.signature(IndeedLane.__init__).parameters) == [
        "self",
        "search_facets",
        "search_pages",
        "results_per_page",
    ]


@respx.mock
def test_admits_is_asked_once_per_distinct_company_never_once_per_posting(tmp_path):
    """8 postings sit on 4 companies; the cap counts companies, not postings."""
    route = _mock_one(search_hits())
    asked: list[tuple[str, str]] = []

    def _admits(provider: str, slug: str) -> bool:
        asked.append((provider, slug))
        return False

    result = IndeedLane().collect(_fetcher(tmp_path), _admits)

    assert len(asked) == 4
    assert set(asked) == {(LANE_PROVIDER, f"Acme-{index:02d}") for index in range(4)}
    # Refusal is free, and it is not an attempt: nothing is tallied for a refused company.
    assert route.call_count == 1
    assert result.snapshots == ()
    assert result.tally.attempted == 0
    assert result.tally.is_silent_outage is False


@respx.mock
def test_every_body_arrives_inline_and_costs_no_second_request(tmp_path):
    """The whole reason this lane exists. One request, every body, and `body_inline` rather than
    `body_fetched` -- the two outcomes exist to keep exactly that distinction.
    """
    route = _mock_one(search_hits())

    result = _collect(IndeedLane(), tmp_path)

    assert route.call_count == 1
    assert len(respx.calls) == 1  # no body GET follows, at all
    assert result.tally.counts["body_inline"] == 8
    assert result.tally.counts["body_fetched"] == 0
    assert result.tally.resolved == 8
    assert result.tally.is_silent_outage is False


@respx.mock
def test_the_snapshot_is_partial_and_cites_the_endpoint_it_requested(tmp_path):
    """`complete` is never available to a lane: `_process_missing` runs on it, and an empty
    `complete` snapshot marks every open posting of that company missing (D-278 §4.2).
    """
    _mock_one(search_hits(2, companies=1))

    result = _collect(IndeedLane(), tmp_path)

    (snapshot,) = result.snapshots
    assert snapshot.snapshot.status == "partial"
    assert snapshot.snapshot.url == SEARCH_URL
    assert snapshot.snapshot.listed_ids == frozenset()
    assert snapshot.snapshot.board_reported_total is None
    assert len(snapshot.snapshot.postings) == 2


@respx.mock
def test_a_posting_carries_the_employer_apply_url_location_title_and_key(tmp_path):
    _mock_one([DEREFERENCE_HITS[0]])

    result = _collect(IndeedLane(), tmp_path)
    posting = result.snapshots[0].snapshot.postings[0]

    assert posting.url == DEREFERENCE_HITS[0].view_job_url
    assert posting.title == "Platform Engineer"
    assert posting.locations == ["Austin, TX"]
    assert posting.remote_policy == "unknown"
    assert "responsibilities" in posting.body_text.lower()
    # The JD is stored once. `raw_json` is a JSON column, so carrying it twice doubles the row.
    assert "description" not in posting.raw_json["job"]
    assert posting.raw_json["job"]["key"] == "key9001"


@respx.mock
def test_a_hit_with_no_apply_url_falls_back_to_indeeds_own_permalink(tmp_path):
    """A display URL built from the posting key, never a URL this lane requests."""
    _mock_one(search_hits(1))

    result = _collect(IndeedLane(), tmp_path)

    assert result.snapshots[0].snapshot.postings[0].url == (
        "https://www.indeed.com/viewjob?jk=key0000"
    )


@respx.mock
def test_a_hit_with_no_description_is_extracted_empty_and_yields_no_snapshot(tmp_path):
    """An ABSENT body is not a body. Reporting it as resolved is how a lane reads healthy while
    delivering nothing the eligibility engine can quote a span from.
    """
    _mock_one([NO_BODY_HIT])

    result = _collect(IndeedLane(), tmp_path)

    assert result.tally.counts["extracted_empty"] == 1
    assert result.tally.counts["body_inline"] == 0
    assert result.snapshots == ()
    assert result.tally.is_silent_outage is True


@respx.mock
def test_posted_at_is_read_in_utc_not_the_machines_local_zone(tmp_path):
    """`datePublished` is epoch MILLISECONDS. Reading it with a naive `fromtimestamp` uses the
    RUNNING MACHINE's zone, so this posting would record 2026-08-30 on a US laptop and
    2026-08-31 on a UTC runner -- and the recency score would move with the machine.
    """
    _mock_one([LOCAL_MIDNIGHT_HIT])

    result = _collect(IndeedLane(), tmp_path)
    posted_at = result.snapshots[0].snapshot.postings[0].posted_at

    assert posted_at is not None
    assert posted_at.tzinfo is None  # naive UTC, matching every provider's `posted_at`
    assert posted_at.isoformat() == "2026-08-31T01:00:00"


@respx.mock
def test_an_unparseable_date_published_leaves_posted_at_unset_rather_than_raising(tmp_path):
    _mock_one([replace(search_hits(1)[0], published_ms="yesterday")])  # type: ignore[arg-type]

    result = _collect(IndeedLane(), tmp_path)

    assert result.snapshots[0].snapshot.postings[0].posted_at is None


# ---------------------------------------------------------------------------------------
# Paging -- the cursor, and the two things an empty page can mean.
# ---------------------------------------------------------------------------------------


@respx.mock
def test_the_default_ceiling_requests_exactly_one_page_per_facet(tmp_path):
    """`indeed_search_pages = 1` is the measured shape: one request, no cursor anywhere."""
    route = _mock({("software engineer", None): (search_hits(2), "cursor-2")})

    result = _collect(IndeedLane(search_facets=("software engineer",), search_pages=1), tmp_path)

    assert route.call_count == 1
    assert _cursor_of(route.calls[0].request) is None
    assert result.search_pages == ((SEARCH_URL, 1),)


@respx.mock
def test_paging_follows_next_cursor_up_to_the_configured_ceiling(tmp_path):
    """The feature: page two is the cursor page one handed back, and the ceiling stops it."""
    route = _mock({
        ("software engineer", None): (search_hits(2, companies=2), "cursor-2"),
        ("software engineer", "cursor-2"): (
            [replace(hit, key=f"p2-{hit.key}", employer_page="/cmp/Beacon-00")
             for hit in search_hits(2, companies=2)],
            "cursor-3",
        ),
        # Page three must never be requested at a ceiling of 2.
    })

    result = _collect(IndeedLane(search_facets=("software engineer",), search_pages=2), tmp_path)

    assert route.call_count == 2
    assert [_cursor_of(call.request) for call in route.calls] == [None, "cursor-2"]
    assert result.search_pages == ((SEARCH_URL, 2),)
    assert result.tally.counts["body_inline"] == 4


@respx.mock
def test_an_absent_next_cursor_ends_the_facet_before_the_ceiling(tmp_path):
    """Running out of results is the EXPECTED outcome of a ceiling above 1, not an outage."""
    route = _mock({("software engineer", None): (search_hits(2), None)})

    result = _collect(IndeedLane(search_facets=("software engineer",), search_pages=5), tmp_path)

    assert route.call_count == 1
    assert result.search_pages == ((SEARCH_URL, 1),)
    assert result.tally.is_silent_outage is False


@respx.mock
def test_a_repeat_page_ends_the_facet_and_is_not_counted_twice(tmp_path):
    """A host that stops honouring the cursor and re-serves page one would otherwise burn every
    remaining request on hits already held -- the offset-wrap tail `providers/workday.py` guards.
    """
    hits = search_hits(2, companies=2)
    route = _mock({
        ("software engineer", None): (hits, "cursor-2"),
        ("software engineer", "cursor-2"): (hits, "cursor-3"),
    })

    result = _collect(IndeedLane(search_facets=("software engineer",), search_pages=5), tmp_path)

    assert route.call_count == 2
    assert result.search_pages == ((SEARCH_URL, 2),)
    # One posting per hit, and the repeat is a server artifact rather than a second listing.
    assert result.tally.counts["body_inline"] == 2
    assert result.tally.counts["not_attemptable"] == 0


@respx.mock
def test_a_later_page_that_is_refused_keeps_the_pages_already_paid_for(tmp_path):
    """Page-1 isolation, one level down. A facet refused on its FIRST page produced nothing; one
    refused on page 2 has already bought a page of results.
    """
    hits = search_hits(2, companies=2)

    def _respond(request: httpx.Request) -> httpx.Response:
        if _cursor_of(request) is None:
            return httpx.Response(200, text=search_response(hits, next_cursor="cursor-2"))
        return httpx.Response(403, text="")

    respx.post(SEARCH_URL).mock(side_effect=_respond)

    result = _collect(IndeedLane(search_facets=("software engineer",), search_pages=3), tmp_path)

    assert result.search_pages == ((SEARCH_URL, 1),)
    assert result.tally.counts["body_inline"] == 2


@respx.mock
def test_the_page_counts_are_positional_one_per_facet(tmp_path):
    """Every entry names the same URL -- the facet travels in the POST body -- so the ENTRIES are
    what carry the facet, in configured order. That is what still tells a facet that ran out
    apart from one the ceiling truncated.
    """
    _mock({
        ("software engineer", None): (search_hits(2, companies=2), None),
        ("data engineer", None): (
            [replace(hit, key=f"d-{hit.key}", employer_page="/cmp/Beacon-00")
             for hit in search_hits(2, companies=2)],
            "cursor-2",
        ),
        ("data engineer", "cursor-2"): (
            [replace(hit, key=f"d2-{hit.key}", employer_page="/cmp/Beacon-01")
             for hit in search_hits(2, companies=2)],
            "cursor-3",
        ),
    })

    result = _collect(
        IndeedLane(search_facets=("software engineer", "data engineer"), search_pages=2), tmp_path
    )

    assert result.search_pages == ((SEARCH_URL, 1), (SEARCH_URL, 2))


@respx.mock
def test_hits_from_several_facets_are_interleaved_round_robin(tmp_path):
    """Companies are worked in iteration order, so concatenating would put every later target
    title behind the first facet's entire yield.
    """
    first = [
        Hit(key=f"a{i}", title="Backend Engineer", employer_name=f"Acme {i}",
            employer_page=f"/cmp/Acme-{i}")
        for i in range(3)
    ]
    second = [
        Hit(key=f"b{i}", title="Backend Engineer", employer_name=f"Beacon {i}",
            employer_page=f"/cmp/Beacon-{i}")
        for i in range(3)
    ]
    _mock({
        ("software engineer", None): (first, None),
        ("data engineer", None): (second, None),
    })

    result = _collect(
        IndeedLane(search_facets=("software engineer", "data engineer")), tmp_path
    )

    assert [s.slug for s in result.snapshots] == [
        "Acme-0", "Beacon-0", "Acme-1", "Beacon-1", "Acme-2", "Beacon-2",
    ]


# ---------------------------------------------------------------------------------------
# Outage handling. A 200 that carries nothing is the failure this design exists to see.
# ---------------------------------------------------------------------------------------


@respx.mock
def test_graphql_errors_inside_a_200_raise_rather_than_reading_as_a_quiet_day(tmp_path):
    """A rejected filter argument arrives exactly this way. A client reading only `results` would
    see an empty list and record a clean run with no postings, forever.
    """
    respx.post(SEARCH_URL).mock(return_value=httpx.Response(200, text=error_response()))

    with pytest.raises(SearchPageError, match="GraphQL errors"):
        _collect(IndeedLane(), tmp_path)


@respx.mock
def test_a_response_with_no_job_search_object_raises(tmp_path):
    respx.post(SEARCH_URL).mock(
        return_value=httpx.Response(200, text=json.dumps({"data": {"somethingElse": {}}}))
    )

    with pytest.raises(SearchPageError, match="data.jobSearch"):
        _collect(IndeedLane(), tmp_path)


@respx.mock
def test_the_unfaceted_search_yielding_nothing_raises(tmp_path):
    """No facet isolation to soften it: one search failing this way is the whole search failing."""
    _mock_one([])

    with pytest.raises(SearchPageError, match="unfaceted"):
        _collect(IndeedLane(), tmp_path)


@respx.mock
def test_every_facet_yielding_nothing_raises_instead_of_reporting_a_quiet_day(tmp_path):
    """With no hits nothing is ever attempted, so `is_silent_outage` stays False and the lane
    would report a clean quiet day forever -- the prior art's 11-run silent outage.
    """
    _mock({("software engineer", None): ([], None), ("data engineer", None): ([], None)})

    with pytest.raises(SearchPageError, match="every role facet"):
        _collect(IndeedLane(search_facets=("software engineer", "data engineer")), tmp_path)


@respx.mock
def test_one_empty_facet_among_several_is_tolerated_rather_than_fatal(tmp_path):
    """One keyword matching nothing is a profile-data matter, not an outage."""
    _mock({
        ("software engineer", None): (search_hits(2), None),
        ("zzq not a real role", None): ([], None),
    })

    result = _collect(
        IndeedLane(search_facets=("software engineer", "zzq not a real role")), tmp_path
    )

    assert result.tally.counts["body_inline"] == 2
    assert result.tally.is_silent_outage is False


@respx.mock
def test_one_facet_whose_request_fails_does_not_cost_the_others_their_results(tmp_path):
    """Per-facet isolation. The fetcher has already retried with backoff, so this is a surviving
    failure rather than a blip worth aborting a run over.
    """
    hits = search_hits(2)

    def _respond(request: httpx.Request) -> httpx.Response:
        if _term_of(request) == "software engineer":
            return httpx.Response(403, text="")
        return httpx.Response(200, text=search_response(hits))

    respx.post(SEARCH_URL).mock(side_effect=_respond)

    result = _collect(
        IndeedLane(search_facets=("software engineer", "data engineer")), tmp_path
    )

    assert result.tally.counts["body_inline"] == 2
    assert result.search_pages == ((SEARCH_URL, 0), (SEARCH_URL, 1))


@respx.mock
def test_every_facet_request_failing_raises_rather_than_reporting_a_quiet_day(tmp_path):
    """Isolation must not become suppression: swallowing per facet and stopping there turns a
    host that refuses every request into a clean run with no postings.
    """
    respx.post(SEARCH_URL).mock(return_value=httpx.Response(403, text=""))

    with pytest.raises(SearchPageError, match="2 request failures"):
        _collect(IndeedLane(search_facets=("software engineer", "data engineer")), tmp_path)


@respx.mock
def test_every_facet_failing_after_its_first_page_raises(tmp_path):
    """One facet losing page 4 keeps the three it paid for and says nothing about the host; EVERY
    facet losing a later page is the host degrading under exactly the paging this lane does, and
    each facet on its own reports only a shorter depth.
    """
    hits = search_hits(2, companies=2)

    def _respond(request: httpx.Request) -> httpx.Response:
        if _cursor_of(request) is None:
            return httpx.Response(200, text=search_response(hits, next_cursor="cursor-2"))
        return httpx.Response(503, text="")

    respx.post(SEARCH_URL).mock(side_effect=_respond)

    with pytest.raises(SearchPageError, match="failed after its first page"):
        _collect(
            IndeedLane(search_facets=("software engineer", "data engineer"), search_pages=3),
            tmp_path,
        )


# ---------------------------------------------------------------------------------------
# Registration, and the two settings fields.
# ---------------------------------------------------------------------------------------


def test_the_lane_is_registered_but_off_by_default(tmp_path):
    """Registered makes it reachable; enabled runs it. It ships off, and not armed."""
    from boardwatch.pipeline.runner import LANE_FACTORIES

    settings = Settings(data_dir=tmp_path, config_dir=tmp_path)
    assert "indeed" in LANE_FACTORIES
    built = LANE_FACTORIES["indeed"](
        LaneContext(
            settings=settings,
            facets=LaneFacets(profile=("software engineer",)),
            rotation_index=0,
        )
    )
    assert isinstance(built, IndeedLane)
    # The factory's facets argument is asserted through the registry, not only on the
    # constructor: a registry row that dropped it would leave every test above green while the
    # live lane searched the general labour market.
    assert built._search_facets == ("software engineer",)
    assert "indeed" not in settings.lanes_enabled


def test_the_registry_hands_the_lane_its_configured_page_knobs(tmp_path):
    """A registry row that dropped either would leave every test above green while the live lane
    kept requesting one page of 100.
    """
    from boardwatch.pipeline.runner import LANE_FACTORIES

    settings = Settings(
        data_dir=tmp_path, config_dir=tmp_path,
        indeed_search_pages=4, indeed_results_per_page=25,
    )
    built = LANE_FACTORIES["indeed"](
        LaneContext(settings=settings, facets=LaneFacets(), rotation_index=0)
    )

    assert (built._search_pages, built._results_per_page) == (4, 25)
    # The defaults are the measured shape, so registering the lane moves nobody's request volume.
    default = Settings(data_dir=tmp_path, config_dir=tmp_path)
    assert (default.indeed_search_pages, default.indeed_results_per_page) == (1, 100)


def test_the_lane_is_not_handed_the_mined_facets(tmp_path):
    """Mined terms are pruned by a trial record that lives on the LinkedIn lane's own `keywords=`
    provenance (`store.facet_queries`). Handing them to a lane whose acquisitions leave no such
    record would buy searches nothing could ever measure or retire.
    """
    from boardwatch.pipeline.runner import LANE_FACTORIES

    settings = Settings(data_dir=tmp_path, config_dir=tmp_path)
    built = LANE_FACTORIES["indeed"](
        LaneContext(
            settings=settings,
            facets=LaneFacets(profile=("software engineer",), mined=("staff engineer",)),
            rotation_index=0,
        )
    )

    assert built._search_facets == ("software engineer",)


@pytest.fixture()
def cfg(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path))
    return tmp_path


def test_both_new_settings_round_trip_through_config_set_and_show(cfg) -> None:
    """Reachability is not enough -- a key that shows but cannot be written is still a gap, and
    `_SCALAR_KEYS` is a hand-maintained mirror of `Settings` that has drifted silently before.
    """
    assert runner.invoke(app, ["config", "set", "indeed_search_pages", "3"]).exit_code == 0
    assert runner.invoke(app, ["config", "set", "indeed_results_per_page", "50"]).exit_code == 0

    out = runner.invoke(app, ["config", "show"]).stdout
    assert "indeed_search_pages = 3" in out
    assert "indeed_results_per_page = 50" in out

    settings = load_settings(data_dir=None)
    assert (settings.indeed_search_pages, settings.indeed_results_per_page) == (3, 50)


@pytest.mark.parametrize(
    "key,value",
    [
        ("indeed_search_pages", "0"),
        ("indeed_results_per_page", "0"),
        ("indeed_results_per_page", "500"),
    ],
)
def test_an_out_of_range_page_knob_is_refused(cfg, key, value) -> None:
    """Validation rides on constructing a `Settings`, so both bounds fire through the CLI. 500 is
    the one that matters most: nothing above 100 has been measured against this endpoint.
    """
    result = runner.invoke(app, ["config", "set", key, value])

    assert result.exit_code == 1
    assert key in result.output

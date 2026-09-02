"""`lanes.jsonld` against the authored pages in `jsonld_shape.py`.

Every request is mocked; nothing here reaches the network.

**THE FIXTURES ARE TRAPS, NOT SAMPLES**, and that is what makes the assertions below worth
anything. An authored fixture can only prove what our own code constructs, so each page carries
the specific measured shape that breaks a naive implementation -- an `identifier` that disagrees
with its own URL, a description escaped one level too deep, a JD split across three properties,
a vendor `url` that is not the page it came from. A test suite over a happy-path fixture would
agree with an implementation that read `identifier`, extracted once, and echoed the vendor's URL.

Two vacuity controls ride along with the positive claims rather than being left implicit:
`test_the_dereference_is_load_bearing` runs the identical seed with the provider dereference
stubbed out and asserts the URL stops being refused, and `test_the_escape_rule_is_load_bearing`
asserts an ordinary un-escaped JD is NOT put through a second extraction pass. Without the first,
the refusal assertion would pass against a lane that never called the resolver; without the
second, the escape rule would pass against one that always unescaped.
"""

from __future__ import annotations

import hashlib
import re
from datetime import date, datetime
from pathlib import Path

import httpx
import pytest
import respx
from jsonld_shape import (
    BREEZY_APPLY_URL,
    BREEZY_PAGE,
    BREEZY_POSTING,
    BREEZY_URL,
    BROKEN_BLOCK,
    CAREERPLUG_POSTING,
    CAREERPLUG_URL,
    CATALOG_DIGEST,
    GRAPH_PAGE,
    HIREOLOGY_PAGE,
    HIREOLOGY_POSTING,
    HIREOLOGY_URL,
    ICIMS_HOME_URL,
    ICIMS_PAGE,
    ICIMS_POSTING,
    ICIMS_URL,
    JAZZHR_PAGE,
    JAZZHR_POSTING,
    JAZZHR_SHORT_URL,
    JAZZHR_URL,
    LIST_TYPE_PAGE,
    LOGIN_WALL_PAGE,
    MEASURED_DATE_FORMATS,
    MEASURED_FROM,
    MEASURED_JSONLD_KEYS,
    MIXED_MARKUP_PAGE,
    NO_LD_PAGE,
    NO_ORG_PAGE,
    REVIEW_BY,
    SENTINEL_BODY_POSTING,
    STRING_ORG_PAGE,
    STRING_ORG_POSTING,
    page,
)

from boardwatch.core.politeness import Fetcher
from boardwatch.core.settings import Settings
from boardwatch.lanes import jsonld
from boardwatch.lanes.base import LaneCompanySnapshot, LaneResult, lane_snapshot
from boardwatch.lanes.jsonld import (
    SEED_HOST_SUFFIXES,
    SEED_HOSTS,
    VENDORS,
    JsonLdLane,
    NoJobPosting,
    UnsupportedSeedURL,
    body_html,
    company_name,
    job_posting,
    locations,
    match_vendor,
    posted_at,
    raw_posting,
    seed_identity,
)
from boardwatch.lanes.outcomes import AcquisitionTally
from boardwatch.store.seed_queries import LaneSeed, seed_host

# --------------------------------------------------------------------------------------------
# Harness
# --------------------------------------------------------------------------------------------


def _fetcher(tmp_path: Path) -> Fetcher:
    """A real `Fetcher` at the pacing FLOOR, against `respx`-mocked transport.

    `per_host_delay_seconds=0.25` is `politeness.PER_HOST_DELAY_FLOOR` -- the lowest the client
    will accept. Going through the real `Fetcher` rather than a stub is what keeps the per-host
    lock, the status classification and `FetchFailure` in the path being tested.
    """
    return Fetcher(
        Settings(
            data_dir=tmp_path, config_dir=tmp_path, retry_attempts=1,
            per_host_delay_seconds=0.25,
        ),
        client=httpx.Client(timeout=5.0, follow_redirects=True),
    )


def _seed(url: str, seed_id: int = 1, attempts: int = 0) -> LaneSeed:
    return LaneSeed(
        id=seed_id, url=url, host=seed_host(url), discovered_by="test", attempts=attempts
    )


class _Reader:
    """A `PendingSeeds` stub that records exactly how the lane asked for its work."""

    def __init__(self, seeds: tuple[LaneSeed, ...]) -> None:
        self._seeds = seeds
        self.calls: list[dict[str, object]] = []

    def __call__(
        self,
        *,
        hosts: frozenset[str],
        host_suffixes: frozenset[str] = frozenset(),
        max_attempts: int,
        limit: int,
    ) -> tuple[LaneSeed, ...]:
        self.calls.append(
            {
                "hosts": hosts,
                "host_suffixes": host_suffixes,
                "max_attempts": max_attempts,
                "limit": limit,
            }
        )
        return self._seeds


class _Admits:
    """A `CompanyAdmission` stub recording every call, so the once-per-company rule is checkable."""

    def __init__(self, *, allow: bool = True) -> None:
        self._allow = allow
        self.calls: list[tuple[str, str]] = []

    def __call__(self, provider: str, slug: str) -> bool:
        self.calls.append((provider, slug))
        return self._allow


# The two list URLs the discovery half fetches. Mocked empty by default: a test about the drain
# must not depend on the public lists, and an unmocked request would raise rather than pass.
_LIST_URL_RE = re.compile(r"https://raw\.githubusercontent\.com/.*/listings\.json")


def _mock_lists(router: respx.Router, payload: str = "[]") -> None:
    router.get(url__regex=_LIST_URL_RE).mock(return_value=httpx.Response(200, text=payload))


# --------------------------------------------------------------------------------------------
# The catalog: what this lane will and will not request
# --------------------------------------------------------------------------------------------


def test_the_vendor_catalog_is_pinned() -> None:
    """A vendor added, removed or re-patterned must fail until a reviewer re-pins the digest.

    The digest is over the shipped catalog and the expectation is a LITERAL in `jsonld_shape`.
    Recomputing the expectation here would pass against any catalog at all -- including one that
    had grown a host whose `robots.txt` nobody fetched, which is the exact thing this lane's
    posture record depends on not happening quietly.
    """
    rows = [
        f"{v.provider}|{v.host}|{v.path.pattern}|{v.tenant_is_subdomain}|{v.crawl_delay_seconds}"
        for v in VENDORS
    ]
    digest = hashlib.sha256("\n".join(rows).encode()).hexdigest()
    assert digest == CATALOG_DIGEST, (
        "the vendor catalog changed. Confirm the new host's robots.txt is fetched and quoted in "
        "the module docstring, then update CATALOG_DIGEST in jsonld_shape.py"
    )


def test_icims_dot_com_is_owner_declined_and_absent_from_the_catalog() -> None:
    """`*.icims.com` is `Disallow: /` and was declined. The custom domain is a different host.

    Pinned as LITERAL hostnames rather than by iterating the catalog: the claim is about two
    specific hosts and their opposite verdicts, and a loop over `VENDORS` would restate whatever
    the catalog happens to say.
    """
    assert match_vendor("https://career-schwab.icims.com/jobs/125797/java-engineer/job") is None
    assert match_vendor("https://careers.garmin.com/jobs/19732?icims=1") is not None


def test_paylocity_is_absent_because_no_tenant_survives_its_url() -> None:
    """Recorded as a refusal, not an omission -- see the module docstring for the cost."""
    assert match_vendor("https://recruiting.paylocity.com/Recruiting/Jobs/Details/4459022") is None


def test_jobvite_is_absent_because_its_description_is_the_whole_page() -> None:
    assert match_vendor("https://jobs.jobvite.com/exampletenant/job/otYIAfwt") is None


@pytest.mark.parametrize(
    "url",
    [
        # A catalog HOST at a path that is not a posting. Host-only matching would admit all of
        # these, and each returns a 200 with no JobPosting -- a whole request budget spent on
        # `extracted_empty`.
        "https://careers.garmin.com/search",
        "https://careers.garmin.com/",
        "https://exampletenant.applytojob.com/",
        "https://example-improvements.breezy.hr/",
        "https://careers.hireology.com/exampletenant",
    ],
)
def test_a_catalog_host_at_a_non_posting_path_is_refused(url: str) -> None:
    assert match_vendor(url) is None


def test_a_known_providers_posting_url_belongs_to_that_provider() -> None:
    """The #304 pattern: a URL a real provider owns is refused here rather than re-filed.

    Filing it under a lane-invented provider would mint a second company row for a board the scan
    stage already enumerates, and the two copies could never converge on
    `UNIQUE(company_id, provider_posting_id)`.
    """
    with pytest.raises(UnsupportedSeedURL, match="known provider"):
        seed_identity("https://boards.greenhouse.io/acme/jobs/6000001", 1)
    with pytest.raises(UnsupportedSeedURL, match="known provider"):
        # A recognized board target whose reference this repo will not read is STILL that
        # provider's URL.
        seed_identity("https://boards.greenhouse.io/acme", 1)


def test_the_dereference_is_load_bearing(monkeypatch: pytest.MonkeyPatch) -> None:
    """VACUITY CONTROL for the test above.

    With the provider dereference stubbed to find nothing, the greenhouse URL stops being refused
    for that reason -- proving the refusal came from the dereference call and not from the URL
    merely being absent from the vendor catalog, which would be true either way.
    """
    monkeypatch.setattr(jsonld, "owning_provider", lambda _url: None)
    with pytest.raises(UnsupportedSeedURL) as caught:
        seed_identity("https://boards.greenhouse.io/acme/jobs/6000001", 1)
    assert "known provider" not in str(caught.value)
    assert "no catalog vendor" in str(caught.value)


# --------------------------------------------------------------------------------------------
# Identity, read from the URL alone
# --------------------------------------------------------------------------------------------


def test_the_posting_id_comes_from_the_url_never_from_identifier() -> None:
    """MEASURED: the page at `.../2855936/description` carries `identifier.value == 2855935`.

    Both numbers are LITERALS. Asserting against the fixture's own `identifier` would restate
    whichever value the fixture holds, and the whole point is that the two disagree.
    """
    assert HIREOLOGY_POSTING["identifier"] == {
        "@type": "PropertyValue",
        "name": "Example",
        "value": 2855935,
    }
    resolved = seed_identity(HIREOLOGY_URL, 7)
    assert resolved.posting_id == "2855936"
    assert resolved.vendor.provider == "hireology"
    assert resolved.slug == "exampletenant"


def test_the_id_still_comes_from_the_url_once_the_body_is_read() -> None:
    """The end-to-end half of the claim above: `RawPosting.provider_posting_id` is the URL's.

    Separate from the identity test on purpose -- `seed_identity` reading the URL correctly does
    not prove `raw_posting` did not overwrite it from the payload on the way out.
    """
    posting = raw_posting(HIREOLOGY_POSTING, seed_identity(HIREOLOGY_URL, 7), "body")
    assert posting.provider_posting_id == "2855936"


@pytest.mark.parametrize(
    ("url", "provider", "slug", "posting_id"),
    [
        (HIREOLOGY_URL, "hireology", "exampletenant", "2855936"),
        (CAREERPLUG_URL, "careerplug", "example-partners-llc", "3570902"),
        # BOTH measured JazzHR shapes, and the SAME reference out of each.
        (JAZZHR_URL, "jazzhr", "exampletenant", "AbC123xyz"),
        (JAZZHR_SHORT_URL, "jazzhr", "exampletenant", "AbC123xyz"),
        (BREEZY_URL, "breezy", "example-improvements", "824adfc228b2"),
        # The apply suffix must NOT become the reference.
        (BREEZY_APPLY_URL, "breezy", "example-improvements", "824adfc228b2"),
        # An iCIMS custom domain IS the tenant, one host per employer.
        (ICIMS_URL, "icims", "careers.garmin.com", "19732"),
        (ICIMS_HOME_URL, "icims", "careers.garmin.com", "15924"),
    ],
)
def test_every_measured_url_shape_resolves_to_its_pinned_identity(
    url: str, provider: str, slug: str, posting_id: str
) -> None:
    """Every expectation is a LITERAL. The two-shapes-one-reference rows are the load-bearing
    ones: reading the LAST path segment would key JazzHR on a title slug and Breezy on the
    constant `apply`, and a constant reference collides every posting at one employer onto one
    row through `UNIQUE(company_id, provider_posting_id)`."""
    resolved = seed_identity(url, 1)
    assert (resolved.vendor.provider, resolved.slug, resolved.posting_id) == (
        provider,
        slug,
        posting_id,
    )


def test_a_wildcard_vendor_at_its_bare_apex_has_no_tenant() -> None:
    with pytest.raises(UnsupportedSeedURL):
        seed_identity("https://careerplug.com/jobs/1", 1)


def test_the_two_routing_arms_are_derived_from_the_catalog_not_written_twice() -> None:
    """Two spellings of one set is how a vendor joins the catalog and never the query.

    Both expectations are LITERALS, so this fails when a vendor is added without the routing
    following it AND if a vendor ever lands in the WRONG arm. The arms are not interchangeable:
    a single-host vendor in the suffix arm would claim every subdomain of a host it shares, and a
    wildcard vendor in the exact arm matches no tenant at all -- which reads as a drained backlog.
    """
    assert SEED_HOSTS == frozenset({"careers.hireology.com", "careers.garmin.com"})
    assert SEED_HOST_SUFFIXES == frozenset({"applytojob.com", "breezy.hr", "careerplug.com"})
    assert not (SEED_HOSTS & SEED_HOST_SUFFIXES), "a vendor may not be claimed by both arms"


# --------------------------------------------------------------------------------------------
# The body: extraction, the escape trap, and the split JD
# --------------------------------------------------------------------------------------------


def test_an_escaped_description_is_unescaped_exactly_once() -> None:
    """MEASURED on CareerPlug: 151 escaped tags, zero real ones, inside the JSON string.

    Without the rule, one extraction pass yields the MARKUP AS TEXT -- which clears the quality
    floor comfortably and is then stored as the frozen JD every `INELIGIBLE` span is quoted from.
    """
    raw = CAREERPLUG_POSTING["description"]
    assert isinstance(raw, str)
    assert "&lt;" in raw and "<" not in raw  # the measured shape, restated as a precondition

    text, rejection = jsonld.assess_body(body_html(CAREERPLUG_POSTING), title="Software Developer")
    assert rejection is None
    assert "<" not in text, "the JD was stored as markup"
    assert "About the role" in text
    assert "Responsibilities" in text


def test_the_escape_rule_is_load_bearing(monkeypatch: pytest.MonkeyPatch) -> None:
    """VACUITY CONTROL: with the rule disabled the same fixture DOES store markup as text.

    Without this, the test above would pass against an implementation that unescaped everything
    unconditionally -- and that implementation is wrong in the other direction.
    """
    monkeypatch.setattr(jsonld, "_description_html", lambda value: value)
    text, _ = jsonld.assess_body(body_html(CAREERPLUG_POSTING), title="Software Developer")
    assert "<" in text


def test_an_ordinary_description_is_not_unescaped_a_second_time() -> None:
    """The other side of the closed condition: a real JD that MENTIONS an escaped tag.

    `&lt;` alone must not trigger the rule, or an employer writing `&lt;script&gt;` in a code
    sample would have it decoded into the body as real markup.
    """
    mentioning = "<p>Do not write &lt;script&gt; tags in this codebase.</p>"
    assert jsonld._description_html(mentioning) == mentioning


def test_the_icims_jd_carries_its_responsibilities_and_qualifications() -> None:
    """MEASURED: `description` is 2,665 chars and the Basic Qualifications live elsewhere.

    Those are exactly the spans a years-of-experience or education rule has to quote, so a body
    that dropped them would abstain where it should decide -- silently, since the body still
    clears the floor on `description` alone.
    """
    text, rejection = jsonld.assess_body(body_html(jsonld_icims_posting()), title="Engineer")
    assert rejection is None
    assert "Overview" in text
    assert "Essential Functions" in text
    assert "Basic Qualifications" in text
    assert "Bachelor's degree" in text


def test_the_unavailable_sentinel_never_reaches_the_body() -> None:
    """MEASURED: this vendor writes the literal `UNAVAILABLE` into a property it has nothing for.

    Asserted against a fixture whose `qualifications` IS the sentinel, and the precondition says
    so out loud. The first version of this guard read the plain iCIMS page, whose four sentinel
    properties are all ones the lane never reads -- so deleting the filter changed nothing and
    the guard passed against the broken version. A control is bounded by its fixture's fact
    VALUES, not by the rule it means to check.
    """
    assert SENTINEL_BODY_POSTING["qualifications"] == "UNAVAILABLE"
    body = body_html(SENTINEL_BODY_POSTING)
    assert "UNAVAILABLE" not in body
    # The other body properties still land: the filter drops the sentinel, not the JD.
    assert "Essential Functions" in body


def test_a_property_this_lane_does_not_read_stays_out_of_the_body() -> None:
    """The property list is CLOSED. `jobBenefits` is measured present and blank; a lane that
    concatenated every text property would pull page chrome into the frozen JD."""
    assert body_html({"description": "<p>A</p>", "jobBenefits": "<p>PERKS</p>"}) == "<p>A</p>"


# --------------------------------------------------------------------------------------------
# JSON-LD block discovery
# --------------------------------------------------------------------------------------------


def test_a_job_posting_is_found_among_sibling_blocks() -> None:
    assert job_posting(HIREOLOGY_PAGE)["title"] == "Associate Software Engineer"


def test_a_graph_envelope_and_a_list_type_both_resolve() -> None:
    """Three block shapes occur in the wild and all three must be read: a bare object, a list,
    and a `@graph`; and `@type` may itself be a list."""
    assert job_posting(GRAPH_PAGE)["title"] == "Associate Software Engineer"
    assert job_posting(LIST_TYPE_PAGE)["title"] == "Associate Software Engineer"


def test_one_broken_block_does_not_cost_the_page() -> None:
    """Per-block isolation, the same rule every provider's board parse applies per posting."""
    assert job_posting(page(dict(HIREOLOGY_POSTING), extra_blocks=(BROKEN_BLOCK,)))["title"]


def test_a_page_with_no_job_posting_raises_rather_than_returning_empty() -> None:
    """Typed at the raise site. An empty return here reads as `the page had no JD`, which is the
    absent-versus-zero confusion the acquisition tally exists to prevent."""
    with pytest.raises(NoJobPosting):
        job_posting(NO_LD_PAGE)


# --------------------------------------------------------------------------------------------
# Field mapping
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(("raw", "expected"), MEASURED_DATE_FORMATS)
def test_the_four_measured_dateposted_formats_parse_to_naive_utc(
    raw: str, expected: str
) -> None:
    """All four measured on real vendor pages, and the last one is the one that matters most:
    a `-05:00` offset read as naive would put the posting five hours early and move its recency
    score. Expectations are LITERALS -- computing one with the parser under test proves nothing.
    """
    assert posted_at({"datePosted": raw}) == datetime.fromisoformat(expected)


def test_an_unreadable_date_is_none_rather_than_an_exception() -> None:
    assert posted_at({"datePosted": "sometime next spring"}) is None
    assert posted_at({}) is None


def test_job_location_is_read_as_a_dict_and_as_a_list() -> None:
    """Both shapes measured: a dict on one vendor, a list on another."""
    assert locations(HIREOLOGY_POSTING) == ["Springfield, IL"]
    assert locations(STRING_ORG_POSTING) == ["Braselton, Georgia"]


def test_a_location_with_no_region_yields_no_dangling_comma() -> None:
    assert locations({"jobLocation": {"address": {"addressLocality": "Remote"}}}) == ["Remote"]


def test_an_address_with_no_place_names_yields_nothing() -> None:
    """An empty string here would reach `rank.location_gate` as a real place."""
    assert locations({"jobLocation": {"address": {"addressCountry": "US"}}}) == []


def test_the_company_name_falls_back_to_the_tenant_when_the_org_is_absent() -> None:
    """MEASURED absent on one vendor. `LaneCompanySnapshot.name` requires something evidenced."""
    assert company_name(job_posting(NO_ORG_PAGE), fallback="exampletenant") == "exampletenant"


def test_a_bare_string_hiring_organization_is_read() -> None:
    """MEASURED: one vendor sends the org as a string, not an object."""
    assert company_name(job_posting(STRING_ORG_PAGE), fallback="x") == "Example Venue Group"


def test_the_stored_url_is_the_one_requested_not_the_vendors_own() -> None:
    """MEASURED: the vendor's `url` property differs from the page it was served on.

    Echoing it would file a lead under a link this run never fetched -- and in the measured case
    would attach an analytics parameter the employer never sent us to.
    """
    seed = seed_identity(BREEZY_URL, 1)
    built = raw_posting(job_posting(BREEZY_PAGE), seed, "body")
    assert built.url == BREEZY_URL
    assert "source=GoogleJobs" not in built.url


def test_the_body_is_not_carried_twice_in_raw_json() -> None:
    """`raw_json` is a JSON column and `body_text` already holds the JD."""
    built = raw_posting(job_posting(ICIMS_PAGE), seed_identity(ICIMS_URL, 1), "body")
    stored = built.raw_json["job_posting"]
    assert "description" not in stored
    assert "responsibilities" not in stored
    assert "qualifications" not in stored
    assert stored["title"] == "Software Engineer 1 - Aviation Backend Web"


# --------------------------------------------------------------------------------------------
# The lane
# --------------------------------------------------------------------------------------------


@respx.mock
def test_the_snapshot_is_always_partial(respx_mock: respx.Router, tmp_path: Path) -> None:
    """`complete` is what closes a board. A lane never enumerates one, so it can never claim it:
    an empty `complete` marks every open posting of that company missing and two such scans close
    them all."""
    _mock_lists(respx_mock)
    respx_mock.get(HIREOLOGY_URL).mock(return_value=httpx.Response(200, text=HIREOLOGY_PAGE))
    lane = JsonLdLane(_Reader((_seed(HIREOLOGY_URL),)))
    result = lane.collect(_fetcher(tmp_path), _Admits())
    assert [s.snapshot.status for s in result.snapshots] == ["partial"]
    assert result.snapshots[0].snapshot.listed_ids == frozenset()
    assert result.snapshots[0].snapshot.board_reported_total is None


@respx.mock
def test_admits_is_asked_once_per_company_before_any_body_is_fetched(
    respx_mock: respx.Router, tmp_path: Path
) -> None:
    """The protocol's contract, both halves, and they need one test because they are one ordering.

    Two postings at one employer plus one at another: `admits` must be asked TWICE, not three
    times, and both calls must land before the first GET. A per-posting call charges one employer
    twice against a cap that counts companies; a call after the fetch has already paid for
    everything it is about to discard.
    """
    _mock_lists(respx_mock)
    order: list[str] = []
    second = "https://careers.hireology.com/exampletenant/2855937/description"
    for url in (HIREOLOGY_URL, second, JAZZHR_URL):
        page_text = HIREOLOGY_PAGE if "hireology" in url else JAZZHR_PAGE
        respx_mock.get(url).mock(
            side_effect=lambda _req, text=page_text: (
                order.append("GET"),
                httpx.Response(200, text=text),
            )[1]
        )

    class _Recording(_Admits):
        def __call__(self, provider: str, slug: str) -> bool:
            order.append("ADMIT")
            return super().__call__(provider, slug)

    admits = _Recording()
    lane = JsonLdLane(_Reader((_seed(HIREOLOGY_URL, 1), _seed(second, 2), _seed(JAZZHR_URL, 3))))
    lane.collect(_fetcher(tmp_path), admits)

    assert admits.calls == [("hireology", "exampletenant"), ("jazzhr", "exampletenant")]
    assert order.index("ADMIT") < order.index("GET")
    # And no ADMIT after the first GET: every admission is settled before anything is spent.
    assert order == ["ADMIT", "ADMIT", "GET", "GET", "GET"]


@respx.mock
def test_a_refused_company_costs_no_request_and_no_attempt(respx_mock: respx.Router, tmp_path: Path) -> None:
    """The one asymmetry in the attempt policy, and it is deliberate.

    The cap DEFERRED this company, it did not try it. Charging the seed would age a real posting
    out of the queue for having been unlucky three times, and the refusal is already reported by
    name through `CompanyBudget.refused`.
    """
    _mock_lists(respx_mock)
    route = respx_mock.get(HIREOLOGY_URL).mock(
        return_value=httpx.Response(200, text=HIREOLOGY_PAGE)
    )
    lane = JsonLdLane(_Reader((_seed(HIREOLOGY_URL),)))
    result = lane.collect(_fetcher(tmp_path), _Admits(allow=False))
    assert not route.called
    assert result.seed_attempts == ()
    assert result.snapshots == ()


@respx.mock
def test_an_out_of_catalog_seed_is_charged_but_costs_no_request(
    respx_mock: respx.Router, tmp_path: Path
) -> None:
    """The cost leak this ceiling exists to bound.

    An unresolvable URL that is never charged sits in the ordered candidate set forever, taking a
    scanned slot every run from a seed that could have been resolved. Charged, it ages out.
    """
    _mock_lists(respx_mock)
    declined = "https://career-schwab.icims.com/jobs/125797/java-engineer/job"
    lane = JsonLdLane(_Reader((_seed(declined, 42),)))
    result = lane.collect(_fetcher(tmp_path), _Admits())
    assert result.seed_attempts == ((42, False),)
    assert result.tally.counts["not_attemptable"] == 1
    assert respx_mock.calls.call_count == 2  # the two list GETs, and nothing else


@respx.mock
def test_the_request_budget_bounds_the_gets_and_unspent_seeds_are_uncharged(
    respx_mock: respx.Router, tmp_path: Path
) -> None:
    """A seed the budget never reached had no turn, so it must not be charged for missing one."""
    _mock_lists(respx_mock)
    urls = [f"https://careers.hireology.com/exampletenant/{2855930 + n}/description" for n in range(4)]
    for url in urls:
        respx_mock.get(url).mock(return_value=httpx.Response(200, text=HIREOLOGY_PAGE))
    lane = JsonLdLane(
        _Reader(tuple(_seed(url, n) for n, url in enumerate(urls, start=1))), request_budget=2
    )
    result = lane.collect(_fetcher(tmp_path), _Admits())
    assert [call.request.url.path for call in respx_mock.calls if "hireology" in str(call.request.url)]
    assert sorted(seed_id for seed_id, _ in result.seed_attempts) == [1, 2]
    assert result.tally.counts["not_attemptable"] == 2


@respx.mock
def test_a_resolved_seed_reports_resolved_and_a_failed_one_does_not(
    respx_mock: respx.Router, tmp_path: Path
) -> None:
    """`resolved` closes a seed forever (`resolved_at` is never cleared), so reporting one for a
    seed that produced nothing would silently drop a real posting from the queue for good."""
    _mock_lists(respx_mock)
    gone = "https://careers.hireology.com/exampletenant/2855999/description"
    respx_mock.get(HIREOLOGY_URL).mock(return_value=httpx.Response(200, text=HIREOLOGY_PAGE))
    respx_mock.get(gone).mock(return_value=httpx.Response(404))
    lane = JsonLdLane(_Reader((_seed(HIREOLOGY_URL, 1), _seed(gone, 2))))
    result = lane.collect(_fetcher(tmp_path), _Admits())
    assert dict(result.seed_attempts) == {1: True, 2: False}
    assert result.tally.counts["fetch_gone"] == 1
    assert result.tally.counts["body_fetched"] == 1


@respx.mock
def test_a_login_wall_is_rejected_and_never_stored(respx_mock: respx.Router, tmp_path: Path) -> None:
    """The prior art's failure inverted: a sign-in interstitial and a real JD must not be one row.

    The seed is still CHARGED -- it had its turn and the request was spent -- but nothing is
    stored and the outcome says which control fired.
    """
    _mock_lists(respx_mock)
    respx_mock.get(HIREOLOGY_URL).mock(return_value=httpx.Response(200, text=LOGIN_WALL_PAGE))
    lane = JsonLdLane(_Reader((_seed(HIREOLOGY_URL, 5),)))
    result = lane.collect(_fetcher(tmp_path), _Admits())
    assert result.snapshots == ()
    assert result.seed_attempts == ((5, False),)
    assert result.tally.counts["rejected_login_wall"] == 1


@respx.mock
def test_the_outcome_is_body_fetched_not_body_inline(respx_mock: respx.Router, tmp_path: Path) -> None:
    """One request bought ONE body. `body_inline` means "at no extra request" and is what
    hiring.cafe earns by buying every body at a company with one board GET; recording it here
    would understate this lane's per-posting cost in the one report that exists to show it."""
    _mock_lists(respx_mock)
    respx_mock.get(HIREOLOGY_URL).mock(return_value=httpx.Response(200, text=HIREOLOGY_PAGE))
    result = JsonLdLane(_Reader((_seed(HIREOLOGY_URL),))).collect(_fetcher(tmp_path), _Admits())
    assert result.tally.counts["body_fetched"] == 1
    assert result.tally.counts["body_inline"] == 0


@respx.mock
def test_a_transport_refusal_and_a_gone_posting_are_different_outcomes(
    respx_mock: respx.Router, tmp_path: Path
) -> None:
    """Folding these is precisely how the prior art hid an eleven-day outage."""
    _mock_lists(respx_mock)
    refused = "https://careers.hireology.com/exampletenant/2855901/description"
    gone = "https://careers.hireology.com/exampletenant/2855902/description"
    respx_mock.get(refused).mock(return_value=httpx.Response(403))
    respx_mock.get(gone).mock(return_value=httpx.Response(410))
    result = JsonLdLane(_Reader((_seed(refused, 1), _seed(gone, 2)))).collect(
        _fetcher(tmp_path), _Admits()
    )
    assert result.tally.counts["fetch_refused"] == 1
    assert result.tally.counts["fetch_gone"] == 1


@respx.mock
def test_the_seed_read_is_filtered_to_this_lanes_own_hosts(respx_mock: respx.Router, tmp_path: Path) -> None:
    """An unfiltered draw takes the oldest rows in a SHARED queue whoever can resolve them, so a
    vendor with few seeds starves behind one with many and an attempt can be charged against a
    seed belonging to a resolver that does not exist yet. Both failures look like a full budget
    and a clean tally, which is why this is asserted rather than assumed.

    The ceiling and the limit are pinned as LITERALS here, not read off the module. An assertion
    against the same constant the code uses passes whatever that constant becomes, which is the
    vacuity this repo has been bitten by before -- and these two numbers are a request budget and
    a retry policy, so a silent change to either is a silent change in cost.
    """
    _mock_lists(respx_mock)
    reader = _Reader(())
    JsonLdLane(reader).collect(_fetcher(tmp_path), _Admits())
    assert reader.calls == [
        {
            "hosts": frozenset({"careers.hireology.com", "careers.garmin.com"}),
            "host_suffixes": frozenset({"applytojob.com", "breezy.hr", "careerplug.com"}),
            "max_attempts": 3,
            "limit": 400,
        }
    ]


@respx.mock
def test_a_company_whose_every_body_was_refused_yields_no_snapshot(
    respx_mock: respx.Router, tmp_path: Path
) -> None:
    """An empty snapshot still writes a `board_scans` row and obliges a company row for zero
    postings, and the refusal is already counted in the tally."""
    _mock_lists(respx_mock)
    respx_mock.get(HIREOLOGY_URL).mock(return_value=httpx.Response(200, text=NO_LD_PAGE))
    result = JsonLdLane(_Reader((_seed(HIREOLOGY_URL),))).collect(_fetcher(tmp_path), _Admits())
    assert result.snapshots == ()
    assert result.tally.counts["extracted_empty"] == 1


# --------------------------------------------------------------------------------------------
# Discovery
# --------------------------------------------------------------------------------------------


@respx.mock
def test_discovery_seeds_only_active_catalog_matching_urls(respx_mock: respx.Router, tmp_path: Path) -> None:
    """Three filters, and each one is load-bearing.

    `active is not True` matches `github_lists.discover` exactly -- and it is not a nicety: the
    one Paylocity posting in the gate-1 miss set is `active: false` here AND was separately
    measured serving `JobNotFound`. The catalog filter keeps 793 owner-declined `*.icims.com`
    URLs out of a queue nothing can drain. The provider filter keeps a greenhouse posting with
    the board-scan path rather than duplicating it under a lane.
    """
    payload = (
        "["
        f'{{"active": true, "url": "{HIREOLOGY_URL}", "company_name": "A"}},'
        f'{{"active": false, "url": "{CAREERPLUG_URL}", "company_name": "B"}},'
        '{"active": true, "url": "https://career-schwab.icims.com/jobs/1/job"},'
        '{"active": true, "url": "https://boards.greenhouse.io/acme/jobs/6000001"},'
        '{"active": true, "url": "https://recruiting.paylocity.com/Recruiting/Jobs/Details/1"},'
        f'{{"active": true, "url": "{HIREOLOGY_URL}"}},'
        '{"active": true}'
        "]"
    )
    _mock_lists(respx_mock, payload)
    result = JsonLdLane(_Reader(())).collect(_fetcher(tmp_path), _Admits())
    # Deduplicated, in first-seen order: a caller reporting discovery must not count one twice.
    assert result.discovered_seeds == (HIREOLOGY_URL,)


@respx.mock
def test_a_list_failure_propagates_rather_than_reading_as_an_empty_day(
    respx_mock: respx.Router, tmp_path: Path
) -> None:
    """A half-read corpus must not be reported as a smaller list. The seed table is what makes
    this cheap: an undrained seed keeps its row, UNCHARGED, and is first in line next run."""
    respx_mock.get(url__regex=_LIST_URL_RE).mock(return_value=httpx.Response(503))
    with pytest.raises(Exception, match="(?i)fetch|503"):
        JsonLdLane(_Reader(())).collect(_fetcher(tmp_path), _Admits())


# --------------------------------------------------------------------------------------------
# Pacing and registration
# --------------------------------------------------------------------------------------------


def test_only_a_host_declaring_a_stricter_delay_is_paced_further() -> None:
    """`careers.garmin.com` declares `crawl-delay: 5`, which is STRICTER than the fetcher's own
    >=1.0s floor. Every other vendor here is already covered by the shared pacer, and adding a
    second WEAKER rule is the thing `lanes/hiringcafe.py` refuses.

    Pinned as LITERALS per provider rather than read off the catalog, so a delay silently dropped
    from the one host that declares one fails here.
    """
    declared = {v.provider: v.crawl_delay_seconds for v in VENDORS}
    assert declared == {
        "hireology": None,
        "careerplug": None,
        "jazzhr": None,
        "breezy": None,
        "icims": 5.0,
    }


def test_the_authored_shapes_are_still_in_review() -> None:
    """These fixtures cannot notice the vendors moving. The drain is a dated edit to `REVIEW_BY`
    with the reason recorded beside it -- not an expiry nobody sees."""
    assert REVIEW_BY >= date.today(), (
        "the authored JSON-LD shapes are due for re-confirmation against the live vendors"
    )


def jsonld_icims_posting() -> dict[str, object]:
    """The iCIMS posting, read back through the page so the block-finder is in the path."""
    return job_posting(ICIMS_PAGE)


# --------------------------------------------------------------------------------------------
# Registration
# --------------------------------------------------------------------------------------------


def test_the_lane_is_registered_and_takes_one_context() -> None:
    """One row in the registry, one `LaneContext`, no branch beside it.

    Built through the registry rather than by calling the constructor, so a factory whose
    signature stopped matching `Callable[[LaneContext], Lane]` fails here and not at the first
    live run.
    """
    from boardwatch.lanes.base import LaneContext
    from boardwatch.lanes.facets import LaneFacets
    from boardwatch.pipeline.runner import LANE_FACTORIES

    assert "jsonld" in LANE_FACTORIES
    ctx = LaneContext(
        settings=Settings(data_dir=Path("."), config_dir=Path(".")),
        facets=LaneFacets(profile=("software engineer",)),
        rotation_index=0,
    )
    built = LANE_FACTORIES["jsonld"](ctx)
    assert built.name == "jsonld"


def test_the_factory_hands_the_lane_the_runners_reader_not_the_empty_default() -> None:
    """`LaneContext.pending_seeds` defaults to `_no_seeds`, which returns `()`.

    A factory that forgot to pass it through would build a lane that drains an empty backlog
    every run while still fetching its discovery half, still recording seeds, still reporting and
    still looking correct -- the silent zero the required-field discipline exists to catch. The
    assertion is identity against the runner's own object, so a reader that merely BEHAVES like
    one does not pass.
    """
    from boardwatch.lanes.base import LaneContext
    from boardwatch.lanes.facets import LaneFacets
    from boardwatch.pipeline.runner import LANE_FACTORIES

    sentinel = _Reader(())
    ctx = LaneContext(
        settings=Settings(data_dir=Path("."), config_dir=Path(".")),
        facets=LaneFacets(),
        rotation_index=0,
        pending_seeds=sentinel,
    )
    built = LANE_FACTORIES["jsonld"](ctx)
    assert built._seeds is sentinel


def test_the_lane_is_registered_but_not_enabled() -> None:
    """Registered is NOT enabled. `lanes_enabled` ships empty, so nothing here runs for anyone
    who has not named it -- which is what contains a lane whose posture record is per host.

    Asserted against the FIELD DEFAULT, never `load_settings()`. That function reads whatever
    config the machine running the suite happens to have, so on a developer's own laptop it
    returns their enabled lanes and this guard would pass or fail by whose machine it ran on --
    and would pass vacuously on any machine that had simply never enabled anything.
    """
    from boardwatch.pipeline.runner import LANE_FACTORIES

    assert "jsonld" in LANE_FACTORIES
    assert Settings(data_dir=Path("."), config_dir=Path(".")).lanes_enabled == ()


@respx.mock
def test_an_alias_is_closed_without_a_request_when_its_twin_resolves(
    respx_mock: respx.Router, tmp_path: Path
) -> None:
    """`lane_seeds` is unique on URL, not identity, and three vendors serve one posting at two
    path shapes -- both of which occur in the public lists.

    The redundant alias is charged RESOLVED and never requested. `resolved_at` is what retires a
    row permanently, and the posting this seed names demonstrably was produced this run, so
    closing it is true; charging it unresolved would have it fetched again next run for a posting
    the store already holds.

    NOTE what this does NOT claim. An earlier version asserted this prevented `apply_board` from
    rolling the company back. That rationale was FALSE -- `scan/apply.py::_apply_listed` has
    collapsed duplicate `provider_posting_id`s since before this lane existed -- so what is
    asserted here is the request saved and the seed retired, which is what the code actually does.
    """
    _mock_lists(respx_mock)
    first = respx_mock.get(ICIMS_URL).mock(return_value=httpx.Response(200, text=ICIMS_PAGE))
    alias = "https://careers.garmin.com/careers-home/jobs/19732"
    second = respx_mock.get(alias).mock(return_value=httpx.Response(200, text=ICIMS_PAGE))

    result = JsonLdLane(_Reader((_seed(ICIMS_URL, 1), _seed(alias, 2)))).collect(
        _fetcher(tmp_path), _Admits()
    )
    ids = [p.provider_posting_id for s in result.snapshots for p in s.snapshot.postings]
    assert ids == ["19732"]
    assert first.called and not second.called, "the alias must cost no request"
    assert dict(result.seed_attempts) == {1: True, 2: True}


@respx.mock
def test_a_dead_alias_does_not_discard_its_live_twin(
    respx_mock: respx.Router, tmp_path: Path
) -> None:
    """THE DEFECT A PRE-FETCH DUPLICATE SUPPRESSION CAUSED, pinned so it cannot come back.

    Suppressing the second URL before either was fetched meant that when the FIRST shape was dead
    and its alias was live, the live posting was discarded unfetched, both seeds took failed
    attempts, and after three runs both aged out -- a real posting lost to a rule that was
    defending against a store failure the store already handles itself.
    """
    _mock_lists(respx_mock)
    dead = "https://careers.garmin.com/jobs/19732"
    live = "https://careers.garmin.com/careers-home/jobs/19732"
    respx_mock.get(dead).mock(return_value=httpx.Response(404))
    respx_mock.get(live).mock(return_value=httpx.Response(200, text=ICIMS_PAGE))

    result = JsonLdLane(_Reader((_seed(dead, 1), _seed(live, 2)))).collect(
        _fetcher(tmp_path), _Admits()
    )
    ids = [p.provider_posting_id for s in result.snapshots for p in s.snapshot.postings]
    assert ids == ["19732"], "the live alias must still be fetched and kept"
    assert dict(result.seed_attempts) == {1: False, 2: True}
    assert result.tally.counts["fetch_gone"] == 1
    assert result.tally.counts["body_fetched"] == 1


@respx.mock
def test_the_snapshot_url_is_one_that_actually_resolved(
    respx_mock: respx.Router, tmp_path: Path
) -> None:
    """`BoardSnapshot.url` is what `apply_board` hands `record_version_source` for every version
    in the batch, so naming a seed that 404'd would record provenance pointing at a request that
    produced nothing."""
    _mock_lists(respx_mock)
    dead = "https://careers.hireology.com/exampletenant/2855901/description"
    live = HIREOLOGY_URL
    respx_mock.get(dead).mock(return_value=httpx.Response(404))
    respx_mock.get(live).mock(return_value=httpx.Response(200, text=HIREOLOGY_PAGE))
    result = JsonLdLane(_Reader((_seed(dead, 1), _seed(live, 2)))).collect(
        _fetcher(tmp_path), _Admits()
    )
    assert [s.snapshot.url for s in result.snapshots] == [live]


@respx.mock
def test_mixed_real_and_escaped_markup_is_never_stored_as_a_jd(
    respx_mock: respx.Router, tmp_path: Path
) -> None:
    """THE HOLE THE ESCAPE RULE ALONE DOES NOT CLOSE, end to end.

    `_description_html` only unescapes a value escaped WHOLE. A description mixing REAL `<br>`
    separators with ESCAPED block content carries a real tag, so the rule correctly declines, and
    `html_to_text` then emits the escaped tags as literal text. MEASURED at 905 chars over 14
    lines with a Responsibilities marker -- which `assess_body` accepts.

    Asserted at the LANE boundary, not on a helper: what matters is that no snapshot is emitted,
    because a snapshot is what becomes the frozen JD every `INELIGIBLE` span is quoted from.
    """
    _mock_lists(respx_mock)
    respx_mock.get(HIREOLOGY_URL).mock(
        return_value=httpx.Response(200, text=MIXED_MARKUP_PAGE)
    )
    result = JsonLdLane(_Reader((_seed(HIREOLOGY_URL, 9),))).collect(
        _fetcher(tmp_path), _Admits()
    )
    assert result.snapshots == (), "markup reached the store as a job description"
    assert result.tally.counts["rejected_quality_gate"] == 1
    assert dict(result.seed_attempts) == {9: False}


@respx.mock
def test_a_page_that_crashes_the_parser_does_not_discard_the_runs_charges(
    respx_mock: respx.Router, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The drain failing silently, pinned.

    The runner only charges what a returned `LaneResult` carries, so an exception escaping
    `collect` discards not just the offending seed but EVERY attempt already made this run --
    leaving them all at the same attempt count, to be re-fetched at one GET each, every run,
    forever. One seed resolves first here precisely so the test can prove the EARLIER charge
    survives the later crash.
    """
    _mock_lists(respx_mock)
    good, bad = HIREOLOGY_URL, JAZZHR_URL
    respx_mock.get(good).mock(return_value=httpx.Response(200, text=HIREOLOGY_PAGE))
    respx_mock.get(bad).mock(return_value=httpx.Response(200, text=JAZZHR_PAGE))

    real = jsonld.job_posting

    def _explode(page_html: str) -> dict[str, object]:
        if "Junior Product Engineer" in page_html:
            raise RuntimeError("selectolax fell over on this vendor's markup")
        return real(page_html)

    monkeypatch.setattr(jsonld, "job_posting", _explode)
    result = JsonLdLane(_Reader((_seed(good, 1), _seed(bad, 2)))).collect(
        _fetcher(tmp_path), _Admits()
    )
    assert dict(result.seed_attempts) == {1: True, 2: False}
    assert result.tally.counts["extracted_empty"] == 1
    assert len(result.snapshots) == 1


@respx.mock
def test_a_declared_crawl_delay_reaches_the_fetcher_for_every_physical_attempt(
    respx_mock: respx.Router, tmp_path: Path
) -> None:
    """The pacing guard that the catalog assertion could not make.

    `Fetcher` makes up to `retry_attempts` REAL requests inside one `get()` with a backoff
    starting at 0.5s, so a lane that slept once per call paced the first request of a run and no
    retry of it -- against the one host that asks for five seconds. The delay is therefore passed
    INTO the fetcher, which applies it per attempt.

    Asserted by capturing what the lane hands `Fetcher.get`, with the value pinned as a LITERAL:
    an assertion reading `vendor.crawl_delay_seconds` back out of the catalog would pass against
    a lane that never passed it at all.
    """
    _mock_lists(respx_mock)
    respx_mock.get(ICIMS_URL).mock(return_value=httpx.Response(200, text=ICIMS_PAGE))
    respx_mock.get(HIREOLOGY_URL).mock(return_value=httpx.Response(200, text=HIREOLOGY_PAGE))
    fetcher = _fetcher(tmp_path)
    seen: list[tuple[str, float | None]] = []
    real_get = fetcher.get

    def _record(url: str, *args: object, **kwargs: object) -> object:
        if "githubusercontent" not in url:
            seen.append((url, kwargs.get("min_host_delay")))  # type: ignore[arg-type]
        return real_get(url, *args, **kwargs)  # type: ignore[arg-type]

    fetcher.get = _record  # type: ignore[method-assign]
    JsonLdLane(_Reader((_seed(ICIMS_URL, 1), _seed(HIREOLOGY_URL, 2)))).collect(fetcher, _Admits())
    assert (ICIMS_URL, 5.0) in seen, "the declared crawl-delay must reach the fetcher"
    assert (HIREOLOGY_URL, None) in seen, "a host declaring nothing must not be slowed"


def test_a_www_prefixed_url_routes_and_stores_under_one_identity() -> None:
    """Routing and IDENTITY must share one host normalisation.

    `seed_host` strips `www.`, so the seed is ROUTED under the stripped host. If identity used
    the unstripped one, the same employer would be stored a second time under slug `www.…` --
    two company rows that can never converge.
    """
    plain = seed_identity("https://exampletenant.applytojob.com/apply/AbC1/Title", 1)
    prefixed = seed_identity("https://WWW.ExampleTenant.applytojob.com/apply/AbC1/Title", 2)
    assert prefixed.slug == plain.slug == "exampletenant"


# --------------------------------------------------------------------------------------------
# Against the real store, not the reader stub
# --------------------------------------------------------------------------------------------


def test_this_lanes_routing_actually_selects_its_seeds_from_the_store(tmp_path: Path) -> None:
    """The `_Reader` stub hands back whatever it was given, so it can never catch a routing set
    that the SQL does not match. This drives the real `record_seeds` -> `unresolved_seeds` pair.

    Three claims, and each has a silent wrong implementation:

    * The two arms together select every seed this lane can resolve, INCLUDING a wildcard tenant
      no discovery pass ever named -- which is the whole reason the suffix arm exists and is
      exactly the Indeed-discovered seed this lane is meant to drain.
    * A suffix does NOT match a different registrable domain that merely ends in the same
      characters. `notapplytojob.com` is somebody else's domain.
    * A host this lane does not serve is NOT selected, so the filter is doing work rather than
      matching everything.
    """
    from boardwatch.store.db import ensure_schema, get_engine
    from boardwatch.store.queries import insert_run
    from boardwatch.store.seed_queries import record_seeds, unresolved_seeds

    engine = get_engine(tmp_path / "seeds.db")
    ensure_schema(engine)
    run = insert_run(engine)

    mine = (
        HIREOLOGY_URL,                                              # exact host
        ICIMS_URL,                                                  # exact host
        JAZZHR_URL,                                                 # suffix, seen tenant
        "https://brandnew.applytojob.com/apply/ZZ9/Some-Title",     # suffix, NEVER seen
        CAREERPLUG_URL,                                             # suffix
        BREEZY_URL,                                                 # suffix
    )
    theirs = (
        "https://career-schwab.icims.com/jobs/1/job",               # owner-declined vendor
        "https://recruiting.paylocity.com/Recruiting/Jobs/Details/1",  # refused vendor
        "https://notapplytojob.com/apply/AA1/Title",                # look-alike domain
    )
    with engine.begin() as conn:
        written = record_seeds(
            conn, mine + theirs, discovered_by="indeed", run_id=run, now=datetime(2026, 9, 2, 12, 0)
        )
    assert written.inserted == len(mine) + len(theirs)
    assert written.unroutable == ()

    with engine.connect() as conn:
        found = unresolved_seeds(
            conn,
            hosts=SEED_HOSTS,
            host_suffixes=SEED_HOST_SUFFIXES,
            max_attempts=3,
            limit=400,
        )
    assert {seed.url for seed in found} == set(mine), (
        "this lane's routing does not select exactly the seeds it can resolve"
    )


def test_claiming_no_hosts_selects_nothing_rather_than_everything(tmp_path: Path) -> None:
    """The dangerous wrong implementation, pinned from this lane's side too.

    An `or_()` over an empty predicate list renders as a TAUTOLOGY, so a resolver that claimed no
    hosts at all would be handed every unresolved seed in the table -- and would then charge
    attempts against seeds belonging to resolvers that do not exist yet, spending a budget that
    is not its own. The store guards this; this asserts the guard from the caller's side, because
    it is this lane that would silently consume the queue.
    """
    from boardwatch.store.db import ensure_schema, get_engine
    from boardwatch.store.queries import insert_run
    from boardwatch.store.seed_queries import record_seeds, unresolved_seeds

    engine = get_engine(tmp_path / "seeds.db")
    ensure_schema(engine)
    run = insert_run(engine)
    with engine.begin() as conn:
        record_seeds(
            conn, (HIREOLOGY_URL, JAZZHR_URL), discovered_by="indeed", run_id=run,
            now=datetime(2026, 9, 2, 12, 0),
        )
    with engine.connect() as conn:
        assert unresolved_seeds(
            conn, hosts=frozenset(), host_suffixes=frozenset(), max_attempts=3, limit=400
        ) == ()


def test_a_failed_apply_still_charges_every_attempt_and_marks_none_resolved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The drain must not stop draining the moment anything else goes wrong.

    Before this, attempts were charged after the last `apply_board`, so ONE company that could
    not be applied skipped the seed write entirely: the runner reported the lane error, every
    seed stayed at the same attempt count, and each was re-fetched at one GET every run forever.

    The `resolved` half is the fail-safe direction and it is asymmetric on purpose. `resolved_at`
    is never cleared, so marking a seed resolved whose posting was rolled back loses that posting
    permanently; marking one unresolved whose posting DID land costs one redundant GET next run,
    which converges on the stored row. This asserts BOTH: the rows are charged, and none is
    closed.
    """
    from boardwatch.lanes.admission import CompanyBudget
    from boardwatch.pipeline import runner as runner_mod
    from boardwatch.store.db import ensure_schema, get_engine
    from boardwatch.store.queries import insert_run
    from boardwatch.store.seed_queries import record_seeds, unresolved_seeds

    engine = get_engine(tmp_path / "apply.db")
    ensure_schema(engine)
    run = insert_run(engine)
    with engine.begin() as conn:
        record_seeds(
            conn, (HIREOLOGY_URL,), discovered_by="jsonld", run_id=run,
            now=datetime(2026, 9, 2, 12, 0),
        )
    with engine.connect() as conn:
        seed_id = unresolved_seeds(
            conn, hosts=SEED_HOSTS, host_suffixes=SEED_HOST_SUFFIXES, max_attempts=3, limit=10
        )[0].id

    posting = raw_posting(
        job_posting(HIREOLOGY_PAGE), seed_identity(HIREOLOGY_URL, seed_id), "body text"
    )
    result = LaneResult(
        snapshots=(
            LaneCompanySnapshot(
                provider="hireology",
                slug="exampletenant",
                name="Example Tooling Co",
                snapshot=lane_snapshot([posting], HIREOLOGY_URL),
            ),
        ),
        tally=AcquisitionTally(),
        # The lane succeeded on this seed. The APPLY is what fails.
        seed_attempts=((seed_id, True),),
    )

    def _explode(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("the board could not be applied")

    monkeypatch.setattr(runner_mod, "apply_board", _explode)

    class _Lane:
        name = "jsonld"

    with pytest.raises(RuntimeError):
        runner_mod._apply_lane(
            engine,
            _Lane(),  # type: ignore[arg-type]
            runner_mod._FetchedLane(result=result, budget=CompanyBudget(10), fetch_seconds=0.0),
            run,
        )

    with engine.connect() as conn:
        still_open = unresolved_seeds(
            conn, hosts=SEED_HOSTS, host_suffixes=SEED_HOST_SUFFIXES, max_attempts=3, limit=10
        )
    assert [s.id for s in still_open] == [seed_id], "the seed must not be closed by a failed apply"
    assert still_open[0].attempts == 1, "the attempt must still be charged"


@pytest.mark.parametrize(
    ("vendor", "posting"),
    [
        ("hireology", HIREOLOGY_POSTING),
        ("careerplug", CAREERPLUG_POSTING),
        ("jazzhr", JAZZHR_POSTING),
        ("breezy", BREEZY_POSTING),
        ("icims", ICIMS_POSTING),
    ],
)
def test_no_authored_fixture_invents_a_field_no_vendor_sends(
    vendor: str, posting: dict[str, object]
) -> None:
    """The fixtures must be SOURCE-DERIVED, not invented, and this is what makes that checkable.

    A fixture key that no vendor was ever measured sending is a fiction, and the danger is not
    that it is untidy -- it is that the lane can come to depend on it and pass a suite forever
    while the field does not exist in production. Checked against key names read off the real
    probed pages; see `MEASURED_JSONLD_KEYS` for the provenance and the refresh path.
    """
    invented = set(posting) - set(MEASURED_JSONLD_KEYS[vendor])
    assert not invented, (
        f"{vendor} fixture carries {sorted(invented)}, which no measured page sent "
        f"({MEASURED_FROM[vendor]})"
    )


@pytest.mark.parametrize(
    ("vendor", "posting"),
    [
        ("hireology", HIREOLOGY_POSTING),
        ("careerplug", CAREERPLUG_POSTING),
        ("jazzhr", JAZZHR_POSTING),
        ("breezy", BREEZY_POSTING),
        ("icims", ICIMS_POSTING),
    ],
)
def test_every_field_this_lane_reads_is_present_exactly_where_it_was_measured(
    vendor: str, posting: dict[str, object]
) -> None:
    """The other half, and the one the traps actually turn on.

    Every trap this lane defends is a PRESENCE-OR-ABSENCE fact: `identifier` absent on three
    vendors, `qualifications`/`responsibilities` present only on iCIMS, `url` present and
    disagreeing with its own page on two. A fixture that quietly gained an `identifier` where the
    vendor sends none would make the URL-parsing guard pass for the wrong reason.
    """
    measured = set(MEASURED_JSONLD_KEYS[vendor])
    for field in ("identifier", "url", "qualifications", "responsibilities", "description"):
        assert (field in posting) == (field in measured), (
            f"{vendor}: fixture has {field!r}={field in posting}, "
            f"measurement says {field in measured} ({MEASURED_FROM[vendor]})"
        )


@respx.mock
def test_a_declared_host_delay_spaces_every_physical_attempt(
    respx_mock: respx.Router, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`Fetcher` honours a declared crawl-delay before EVERY physical attempt, not once per call.

    This is the half a lane cannot enforce for itself and the reason the delay moved into the
    client. `_send_with_retries` makes up to `retry_attempts` REAL requests inside one `get()`,
    with a tenacity backoff starting at 0.5s -- so a 503 from a host asking for five seconds got
    its retries half a second apart, and the caller that slept once had no way to know.

    Asserted on the SLEEP the client asks for rather than on wall-clock, so it is deterministic
    and costs no real time: every `time.sleep` is captured, and the 503 forces two attempts. The
    expectation is a LITERAL 5.0 -- reading it back off the catalog would pass against a client
    that never applied it.
    """
    from boardwatch.core import politeness as politeness_mod

    slept: list[float] = []
    monkeypatch.setattr(politeness_mod.time, "sleep", slept.append)

    url = "https://slow.test/jobs/1"
    respx_mock.get(url).mock(
        side_effect=[httpx.Response(503), httpx.Response(200, text="ok")]
    )
    fetcher = Fetcher(
        Settings(
            data_dir=tmp_path, config_dir=tmp_path, retry_attempts=2,
            per_host_delay_seconds=0.25,
        ),
        client=httpx.Client(timeout=5.0),
    )
    fetcher.get(url, min_host_delay=5.0)

    assert slept, "the client never paced at all"
    assert max(slept) >= 5.0, (
        f"a retry was spaced {max(slept)}s against a host that declared 5s: {slept}"
    )

    # AND the initial pace of the NEXT call to the same host. This is a separate code path from
    # the retry wait above -- `_pace` versus the tenacity backoff -- and a mutation campaign
    # showed the retry assertion alone stays green when the override is dropped from `_pace`,
    # because the retry term still supplies a five-second sleep. Two paths, two assertions.
    slept.clear()
    respx_mock.get("https://slow.test/jobs/2").mock(return_value=httpx.Response(200, text="ok"))
    fetcher.get("https://slow.test/jobs/2", min_host_delay=5.0)
    assert slept and max(slept) >= 4.0, (
        f"the second call to a host declaring 5s was paced {slept}"
    )

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
    ICIMS_URL,
    JAZZHR_PAGE,
    JAZZHR_SHORT_URL,
    JAZZHR_URL,
    LIST_TYPE_PAGE,
    LOGIN_WALL_PAGE,
    MEASURED_DATE_FORMATS,
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
from boardwatch.lanes.jsonld import (
    FIXED_SEED_HOSTS,
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
    seed_hosts,
    seed_identity,
)
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
        self, *, hosts: frozenset[str], max_attempts: int, limit: int
    ) -> tuple[LaneSeed, ...]:
        self.calls.append({"hosts": hosts, "max_attempts": max_attempts, "limit": limit})
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


def test_the_fixed_host_filter_is_derived_from_the_catalog_not_written_twice() -> None:
    """Two spellings of one set is how a vendor joins the catalog and never the query.

    The expectation is a LITERAL, so this fails both when a fixed-host vendor is added without
    the filter following it AND if the derivation ever starts emitting a wildcard vendor's
    `.suffix`, which `lane_seeds.host` would never equal -- an `IN (...)` against `.breezy.hr`
    matches no row ever recorded, and the lane would report a drained backlog forever.
    """
    assert FIXED_SEED_HOSTS == frozenset({"careers.hireology.com", "careers.garmin.com"})


def test_a_wildcard_vendors_tenant_host_is_asked_for_only_once_discovery_names_it() -> None:
    """The limit of an exact-hostname filter, pinned so it cannot be forgotten.

    Three of the five vendors give every employer its own subdomain, so there is no finite set to
    enumerate; the tenants come from this run's own discovery pass. Both halves are asserted --
    that a discovered tenant DOES reach the filter, and that the fixed hosts are there without
    one -- because an implementation that returned only the fixed set would still pass a test
    that checked membership alone.
    """
    assert seed_hosts(()) == FIXED_SEED_HOSTS
    widened = seed_hosts((CAREERPLUG_URL, JAZZHR_URL))
    assert "example-partners-llc.careerplug.com" in widened
    assert "exampletenant.applytojob.com" in widened
    assert widened > FIXED_SEED_HOSTS


def test_the_host_spelling_matches_the_one_the_store_records() -> None:
    """`seed_host` lower-cases and strips `www.`. A filter spelled any other way matches nothing,
    and a row that no filter matches can never be drained and never reports itself as stuck."""
    assert seed_hosts(("https://WWW.Example-Partners-LLC.CareerPlug.com/jobs/1",)) == (
        FIXED_SEED_HOSTS | {"example-partners-llc.careerplug.com"}
    )


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
        {"hosts": FIXED_SEED_HOSTS, "max_attempts": 3, "limit": 400},
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
def test_two_seed_urls_for_one_posting_do_not_abort_the_company(
    respx_mock: respx.Router, tmp_path: Path
) -> None:
    """`lane_seeds` is unique on URL, not on identity, and three vendors serve one posting at two
    path shapes -- both of which occur in the public lists.

    This is not a wasted-request guard. `scan/apply.py` snapshots `existing` once before its loop,
    so two postings sharing a `provider_posting_id` both take the INSERT branch and the second
    violates UNIQUE(company_id, provider_posting_id) inside `apply_board`'s single transaction:
    the whole company rolls back and the exception escapes to the lane stage. So the assertion is
    that ONE posting is emitted, and that the redundant seed is CHARGED rather than left to be
    skipped forever.
    """
    _mock_lists(respx_mock)
    respx_mock.get(ICIMS_URL).mock(return_value=httpx.Response(200, text=ICIMS_PAGE))
    same_posting = "https://careers.garmin.com/careers-home/jobs/19732"
    respx_mock.get(same_posting).mock(return_value=httpx.Response(200, text=ICIMS_PAGE))

    result = JsonLdLane(_Reader((_seed(ICIMS_URL, 1), _seed(same_posting, 2)))).collect(
        _fetcher(tmp_path), _Admits()
    )
    ids = [p.provider_posting_id for s in result.snapshots for p in s.snapshot.postings]
    assert ids == ["19732"], "one posting, or apply_board rolls the company back"
    assert dict(result.seed_attempts) == {1: True, 2: False}
    assert result.tally.counts["not_attemptable"] == 1

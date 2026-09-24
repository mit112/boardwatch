"""T188 (DESIGN-T183 E1/N1): the Indeed lane's `co=` comes from the profile's `target_countries`.

Before this every tenant's Indeed search was `?co=US`, a module constant. Now each declared
country is searched, the run's one company cap covers all of them, and a profile declaring no
country makes no request and says why.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import httpx
import respx
from indeed_shape import search_hits, search_response
from sqlalchemy import Engine, insert

from boardwatch.core.clock import utcnow
from boardwatch.core.settings import Settings
from boardwatch.lanes.base import LaneContext
from boardwatch.lanes.facets import LaneFacets
from boardwatch.lanes.indeed import IndeedLane, search_url
from boardwatch.pipeline.runner import LANE_FACTORIES, _run_lanes
from boardwatch.rank.location_data import ISO3166_ALPHA2, ISO3166_ALPHA3
from boardwatch.rank.tenant_assumptions import (
    TenantAssumptionReport,
    TenantAssumptionTally,
    tenant_assumptions_to_dict,
)
from boardwatch.store import tables
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.queries import insert_run
from tests.unit.test_indeed_lane import _fetcher


def _admit_all(provider: str, slug: str, *, tier1: bool = False) -> bool:
    return True


def _hits(prefix: str) -> str:
    """Two companies' worth of hits whose keys and employers are unique to `prefix`."""
    return search_response([
        replace(hit, key=f"{prefix}{hit.key}", employer_name=f"{prefix} {hit.employer_name}",
                employer_page=f"/cmp/{prefix}-{hit.employer_page.rsplit('-', 1)[-1]}")
        for hit in search_hits(4, companies=2)
    ])


def test_every_alpha3_code_has_exactly_one_alpha2_code() -> None:
    assert set(ISO3166_ALPHA2) == ISO3166_ALPHA3
    assert len(set(ISO3166_ALPHA2.values())) == len(ISO3166_ALPHA2)
    assert all(len(code) == 2 and code.isupper() for code in ISO3166_ALPHA2.values())


def test_a_canadian_profile_searches_canada(tmp_path: Path) -> None:
    with respx.mock(assert_all_called=True) as router:
        route = router.post("https://apis.indeed.com/graphql?co=CA").mock(
            return_value=httpx.Response(200, text=_hits("ca"))
        )
        result = IndeedLane(target_countries=("CAN",)).collect(_fetcher(tmp_path), _admit_all)

    assert route.call_count == 1
    assert result.not_attemptable is None
    assert result.search_pages == ((search_url("CAN"), 1),)


def _hits_then_more(prefix: str) -> list[httpx.Response]:
    """Two pages for one country, each naming a next page, so only the page budget can stop it."""
    def page(n: int) -> httpx.Response:
        hits = [
            replace(hit, key=f"{prefix}{n}{hit.key}", employer_name=f"{prefix} {hit.employer_name}",
                    employer_page=f"/cmp/{prefix}-{hit.employer_page.rsplit('-', 1)[-1]}")
            for hit in search_hits(4, companies=2)
        ]
        return httpx.Response(200, text=search_response(hits, next_cursor=f"{prefix}-c{n}"))
    return [page(1), page(2)]


def test_two_countries_share_one_page_budget_round_robin(tmp_path: Path) -> None:
    """T188b: the page budget is the run's, not each country's. Two countries under
    `search_pages=2`, every page offering a next one, send exactly two POSTs — one per country,
    round-robin — where giving each country the whole budget sent four."""
    with respx.mock(assert_all_called=True) as router:
        us = router.post("https://apis.indeed.com/graphql?co=US").mock(
            side_effect=_hits_then_more("us")
        )
        ca = router.post("https://apis.indeed.com/graphql?co=CA").mock(
            side_effect=_hits_then_more("ca")
        )
        result = IndeedLane(search_pages=2, target_countries=("USA", "CAN")).collect(
            _fetcher(tmp_path), _admit_all
        )

    assert (us.call_count, ca.call_count) == (1, 1)
    assert result.search_pages == ((search_url("USA"), 1), (search_url("CAN"), 1))


def test_the_page_budget_is_shared_across_countries_and_facets(tmp_path: Path) -> None:
    """Two facets × two pages is a budget of four whatever the country count: two countries get
    one page per (facet, country) search, not two."""
    with respx.mock(assert_all_called=True) as router:
        us = router.post("https://apis.indeed.com/graphql?co=US").mock(
            side_effect=_hits_then_more("us") + _hits_then_more("ux")
        )
        ca = router.post("https://apis.indeed.com/graphql?co=CA").mock(
            side_effect=_hits_then_more("ca") + _hits_then_more("cx")
        )
        IndeedLane(
            search_facets=("backend engineer", "data engineer"), search_pages=2,
            target_countries=("USA", "CAN"),
        ).collect(_fetcher(tmp_path), _admit_all)

    assert us.call_count + ca.call_count == 4
    assert (us.call_count, ca.call_count) == (2, 2)


def test_one_country_keeps_its_whole_page_budget_per_facet(tmp_path: Path) -> None:
    """CONTROL: the owner's single-country run is unchanged — every facet pages to the ceiling."""
    with respx.mock(assert_all_called=True) as router:
        us = router.post("https://apis.indeed.com/graphql?co=US").mock(
            side_effect=_hits_then_more("us") + _hits_then_more("ux")
        )
        IndeedLane(
            search_facets=("backend engineer", "data engineer"), search_pages=2,
            target_countries=("USA",),
        ).collect(_fetcher(tmp_path), _admit_all)

    assert us.call_count == 4


def test_two_countries_are_each_searched_under_one_company_cap(tmp_path: Path) -> None:
    """One search per country; the admission callback — the run's one company budget — is the
    same one for both, so a cap of one company admits one across the two countries, not one each."""
    admitted: list[tuple[str, str]] = []

    def admit_one(provider: str, slug: str, *, tier1: bool = False) -> bool:
        if admitted:
            return False
        admitted.append((provider, slug))
        return True

    with respx.mock(assert_all_called=True) as router:
        us = router.post("https://apis.indeed.com/graphql?co=US").mock(
            return_value=httpx.Response(200, text=_hits("us"))
        )
        ca = router.post("https://apis.indeed.com/graphql?co=CA").mock(
            return_value=httpx.Response(200, text=_hits("ca"))
        )
        result = IndeedLane(search_pages=2, target_countries=("USA", "CAN")).collect(
            _fetcher(tmp_path), admit_one
        )

    assert (us.call_count, ca.call_count) == (1, 1)
    assert result.search_pages == ((search_url("USA"), 1), (search_url("CAN"), 1))
    assert len(result.snapshots) == 1 and len(admitted) == 1


def test_no_declared_country_makes_no_request_and_says_why(tmp_path: Path) -> None:
    with respx.mock(assert_all_mocked=True) as router:
        result = IndeedLane(target_countries=()).collect(_fetcher(tmp_path), _admit_all)
        assert router.calls.call_count == 0

    assert result.not_attemptable == "no_target_countries"
    assert result.snapshots == ()
    assert result.tally.attempted == 0


def test_the_registry_hands_the_lane_the_profiles_countries(tmp_path: Path) -> None:
    built = LANE_FACTORIES["indeed"](
        LaneContext(
            settings=Settings(data_dir=tmp_path, config_dir=tmp_path),
            facets=LaneFacets(), rotation_index=0, target_countries=("CAN",),
        )
    )
    assert isinstance(built, IndeedLane)
    assert built._search_urls == (search_url("CAN"),)


def _store(tmp_path: Path, target_countries: list[str]) -> Engine:
    engine = get_engine(tmp_path / "store")
    ensure_schema(engine)
    with engine.begin() as conn:
        conn.execute(insert(tables.profile).values(
            id=1, text="Backend engineer.", remote_only=False, resume_max_pages=1,
            updated_at=utcnow(), target_countries_json=target_countries,
        ))
    return engine


def test_the_run_reads_the_countries_off_the_profile_and_reports_an_undeclared_one(
    tmp_path: Path,
) -> None:
    settings = Settings(
        data_dir=tmp_path / "store", config_dir=tmp_path / "cfg", lanes_enabled=("indeed",),
        retry_attempts=1,
    )
    engine = _store(tmp_path, [])
    with respx.mock(assert_all_mocked=True) as router:
        reports, errors = _run_lanes(engine, settings, insert_run(engine))
        assert router.calls.call_count == 0

    assert errors == []
    assert [(r.name, r.not_attemptable) for r in reports] == [("indeed", "no_target_countries")]

    engine = _store(tmp_path / "declared", ["CAN", "ATA"])
    settings = settings.model_copy(update={"data_dir": tmp_path / "declared" / "store"})
    with respx.mock(assert_all_called=True) as router:
        route = router.post("https://apis.indeed.com/graphql?co=CA").mock(
            return_value=httpx.Response(200, text=_hits("ca"))
        )
        reports, errors = _run_lanes(engine, settings, insert_run(engine))

    assert route.call_count == 1, errors
    assert [(r.name, r.not_attemptable, r.not_attempted) for r in reports] == [
        ("indeed", None, ("unsupported_country:ATA",))
    ]


def test_the_tenant_assumption_report_carries_the_lane_abstain() -> None:
    report = TenantAssumptionReport(
        ranker=TenantAssumptionTally(grounding={}), review=None,
        lanes={"indeed": "no_target_countries"},
    )
    assert tenant_assumptions_to_dict(report) == {
        "ranker": {}, "review": None, "lanes": {"indeed": "no_target_countries"},
    }


def test_a_country_indeed_does_not_serve_is_refused_by_name_and_never_posted(
    tmp_path: Path,
) -> None:
    """T188b. `ATA` is a valid ISO code Indeed has no site for: it used to go out as `co=AQ` and
    come back `first_page_failed`, indistinguishable from an outage. Now it is a recorded refusal
    naming it, with no request, and the served country is still searched."""
    with respx.mock(assert_all_called=True, assert_all_mocked=True) as router:
        us = router.post("https://apis.indeed.com/graphql?co=US").mock(
            return_value=httpx.Response(200, text=_hits("us"))
        )
        result = IndeedLane(target_countries=("USA", "ATA")).collect(
            _fetcher(tmp_path), _admit_all
        )
        assert router.calls.call_count == 1

    assert us.call_count == 1
    assert result.search_pages == ((search_url("USA"), 1),)
    assert [str(note) for note in result.not_attempted] == ["unsupported_country:ATA"]
    assert result.not_attemptable is None, "the lane searched the US; it did not abstain"


def test_only_unserved_countries_make_no_request_and_the_lane_abstains(tmp_path: Path) -> None:
    with respx.mock(assert_all_mocked=True) as router:
        result = IndeedLane(target_countries=("ATA",)).collect(_fetcher(tmp_path), _admit_all)
        assert router.calls.call_count == 0

    assert result.not_attemptable == "unsupported_country"
    assert [str(note) for note in result.not_attempted] == ["unsupported_country:ATA"]


def test_every_served_country_is_an_iso_country() -> None:
    from boardwatch.lanes.indeed import INDEED_COUNTRIES

    assert INDEED_COUNTRIES <= ISO3166_ALPHA3
    assert {"USA", "CAN", "GBR", "IND"} <= INDEED_COUNTRIES
    assert "ATA" not in INDEED_COUNTRIES

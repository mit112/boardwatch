"""`lanes.github_lists` against the authored payloads in `github_lists_shape.py`.

Two halves, and the first is what makes the second worth anything. An authored fixture proves
only what our own code constructs, so before any client behaviour is asserted the fixture is
checked against the contract the probe recorded -- the two record shapes, the four-value
`sponsorship` vocabulary, the fourteen `degrees` values, the seven malformed URLs, and the
recorded ABSENCE of CJK.

Those literals are written HERE, not imported, wherever the point is to catch the fixture
drifting. A test that re-derives its expectation from the constant the code under test used
agrees with itself. The provider names are spelled out for the same reason: reading them from
`PROVIDER_NAMES` would make the stratification test agree with the registry rather than with the
recorded cost model.

Every request is mocked. Nothing in this file reaches the network.
"""

from __future__ import annotations

import json
import unicodedata
from datetime import date
from pathlib import Path

import httpx
import pytest
import respx
import yaml
from github_lists_shape import (
    ACCENTED_NAME,
    EMBED_URL,
    MALFORMED_URLS,
    REVIEW_BY,
    S1_KEYS,
    S1_REPO,
    S2_KEYS,
    S2_REPO,
    listings,
)

from boardwatch.lanes import github_lists
from boardwatch.lanes.admission import CompanyBudget
from boardwatch.lanes.github_lists import (
    LIST_URLS,
    PROVIDER_PRIORITY,
    ListPayloadError,
    candidate_document,
    discover,
    fetch_listings,
    read_listings,
    select,
)
from boardwatch.registry.validate import CompanyEntry, validate_entries

# The four providers that serve a JD body with the listing, cheapest first; then the two that
# spend `detail_fetch_budget` on a per-posting GET. Written out rather than imported: this IS the
# ramp order the owner ruled, and a test that reads it from the module cannot catch it changing.
_INLINE_BODY = ("greenhouse", "lever", "ashby", "workable")
_DETAIL_BUDGET = ("workday", "smartrecruiters")

# `listings()` is deterministic, so the fixture's own board population is a fixed fact. Written
# here so a fixture edit that changes the corpus reds this file rather than sliding through.
_FIXTURE_BOARDS = 35
_FIXTURE_INLINE_BOARDS = 21  # greenhouse 8 + lever 4 + ashby 6 + workable 3
_FIXTURE_WORKDAY_BOARDS = 9
_FIXTURE_SMARTRECRUITERS_BOARDS = 5


def _sources() -> dict[str, list[dict]]:
    return {S1_REPO: listings("S1"), S2_REPO: listings("S2")}


def _all_records() -> list[dict]:
    return listings("S1") + listings("S2")


def _never_known(provider: str, slug: str) -> bool:
    return False


# ---------------------------------------------------------------------------------------
# The fixture traces to the recorded contract.
# ---------------------------------------------------------------------------------------


def test_each_source_is_a_bare_array_in_its_own_recorded_shape():
    """Contract §3: S1 carries `category` and `degrees`; S2 carries NEITHER."""
    s1, s2 = listings("S1"), listings("S2")
    assert isinstance(s1, list) and isinstance(s2, list)
    assert S1_KEYS == frozenset({
        "source", "category", "company_name", "id", "title", "active", "date_updated",
        "date_posted", "url", "locations", "company_url", "is_visible", "sponsorship", "degrees",
    })
    assert "category" not in S2_KEYS and "degrees" not in S2_KEYS
    for record in s1:
        assert set(record) <= S1_KEYS, record
        assert "category" in record and "degrees" in record
    for record in s2:
        assert set(record) <= S2_KEYS | {"season"}, record
        assert "category" not in record and "degrees" not in record


def test_season_leaks_onto_a_tiny_minority_of_one_source_only():
    """Contract §3: 2 of 1,142 S2 records. An OPTIONAL key a reader must not require."""
    assert sum(1 for r in listings("S2") if "season" in r) == 2
    assert sum(1 for r in listings("S1") if "season" in r) == 0


def test_absence_is_always_a_missing_key_and_never_a_null():
    """Contract §3: not one field in any source is ever JSON null."""
    for record in _all_records():
        for key, value in record.items():
            assert value is not None, (key, record)


def test_the_closed_vocabularies_are_the_recorded_ones():
    """Contract §3: `sponsorship` is closed at four values; `degrees` at fourteen."""
    sponsorship = {r["sponsorship"] for r in _all_records()}
    assert sponsorship <= {
        "Other", "U.S. Citizenship is Required", "Does Not Offer Sponsorship", "Offers Sponsorship",
    }
    degrees = {value for r in listings("S1") for value in r["degrees"]}
    assert degrees <= {
        "Bachelor's", "Master's", "PhD", "Associate's", "Certificate", "MBA", "Bootcamp",
        "MD", "JD", "PharmD", "Incomplete", "DO", "DDS", "DVM",
    }
    # 29.3% of live S1 records carry an EMPTY list, so a reader must not assume one element.
    assert any(r["degrees"] == [] for r in listings("S1"))


def test_locations_is_never_empty_and_the_dates_are_ints():
    """Contract §3: `locations` min length 1 in all four sources; epoch SECONDS as an int."""
    for record in _all_records():
        assert isinstance(record["locations"], list) and record["locations"]
        assert isinstance(record["date_updated"], int) and not isinstance(record["date_updated"], bool)
        assert isinstance(record["date_posted"], int)
        assert isinstance(record["active"], bool) and isinstance(record["is_visible"], bool)


def test_one_record_is_active_while_the_list_itself_hides_it():
    """Contract §5 trap 7: 1 live record is `active: true, is_visible: false`.

    The owner's rule filters on `active` alone, so this record IS in scope. Authored so that
    anyone who later adds an `is_visible` filter has a case that changes.
    """
    hidden = [r for r in _all_records() if r["active"] and not r["is_visible"]]
    assert len(hidden) == 1


def test_all_seven_malformed_urls_are_present_active_and_in_one_source():
    """Contract §5 trap 1. A fixture of well-formed URLs cannot fail the parse-refusal test."""
    assert len(MALFORMED_URLS) == 7
    s2_urls = [r["url"] for r in listings("S2") if r["active"]]
    for bad in MALFORMED_URLS:
        assert bad in s2_urls
    assert not any(bad in [r.get("url") for r in listings("S1")] for bad in MALFORMED_URLS)
    # The recorded defect: one slash after the scheme, so the host is empty.
    for bad in MALFORMED_URLS:
        assert bad.startswith("https:/") and not bad.startswith("https://")


def test_there_is_no_cjk_anywhere_and_the_real_non_ascii_is_present():
    """Contract §5 trap 6: 0 CJK hits over all 34,958 records, in all four sources.

    Asserted rather than assumed because the build brief expected CJK here. A fixture carrying
    it would model something the corpus does not contain -- and the corpus DOES contain an en
    dash and an accented employer name, which is what a reader has to survive.
    """
    blob = json.dumps(_all_records(), ensure_ascii=False)
    cjk = [
        ch for ch in blob
        if any(tag in unicodedata.name(ch, "") for tag in ("CJK", "HIRAGANA", "KATAKANA", "HANGUL"))
    ]
    assert cjk == []
    assert "–" in blob  # EN DASH, 610 live S1 records
    assert ACCENTED_NAME in blob


def test_company_url_never_names_a_board_we_could_use():
    """Contract §3: 0 of 3,129 live records. A reader falling back to it finds nothing."""
    for record in _all_records():
        assert not any(
            host in record["company_url"]
            for host in ("greenhouse.io", "lever.co", "ashbyhq.com", "workable.com",
                         "smartrecruiters.com", "myworkdayjobs.com")
        )


def test_the_authored_shape_carries_a_review_deadline():
    """R15 in spirit: a shape that still parses can have been overtaken months ago.

    Red here is actionable with the four `curl` commands at the end of the contract and nothing
    else. Confirm the key sets and the `active` proportion, then roll `REVIEW_BY` forward in
    `tests/unit/github_lists_shape.py` with the date and the reason recorded beside it.
    """
    assert date.today() <= REVIEW_BY, (
        f"the GitHub-lists shape was last reviewed against the live files before {REVIEW_BY}. "
        "Re-run the contract's curl commands and roll the deadline forward with a reason."
    )


# ---------------------------------------------------------------------------------------
# Reading a payload.
# ---------------------------------------------------------------------------------------


def test_a_bare_array_reads_and_non_records_are_dropped():
    payload = json.dumps([{"url": "x"}, 7, None, "s", {"url": "y"}]).encode()
    assert read_listings(payload) == [{"url": "x"}, {"url": "y"}]


@pytest.mark.parametrize(
    "payload",
    [b"not json", b"{}", b'{"listings": []}', b"null", b"7", b'"a string"'],
)
def test_a_payload_that_is_not_an_array_raises_rather_than_reading_empty(payload):
    """An empty list would reach the caller as "the list is empty today", which is a lie.

    The whole file is one array (contract §3), so anything else means the contract moved or a
    proxy answered -- both of which the operator has to see.
    """
    with pytest.raises(ListPayloadError):
        read_listings(payload)


def test_the_two_in_scope_repos_are_the_only_ones_read():
    """The owner's ruling is the new-grad pair. The internship lists are out of scope."""
    assert [repo for repo, _ in LIST_URLS] == [S1_REPO, S2_REPO]
    for repo, url in LIST_URLS:
        assert url == (
            f"https://raw.githubusercontent.com/{repo}/dev/.github/scripts/listings.json"
        )


@respx.mock
def test_one_get_per_repo_and_a_failure_is_not_a_quiet_empty_day(tmp_path):
    from boardwatch.core.politeness import FetchFailure

    routes = [
        respx.get(url).mock(return_value=httpx.Response(200, json=listings(shape)))
        for (_, url), shape in zip(LIST_URLS, ("S1", "S2"), strict=True)
    ]
    sources = fetch_listings(_fetcher(tmp_path))
    assert [route.call_count for route in routes] == [1, 1]
    assert sorted(sources) == sorted([S1_REPO, S2_REPO])

    respx.reset()
    respx.get(LIST_URLS[0][1]).mock(return_value=httpx.Response(500))
    with pytest.raises(FetchFailure):
        fetch_listings(_fetcher(tmp_path))


def _fetcher(tmp_path: Path):
    from boardwatch.core.politeness import Fetcher
    from boardwatch.core.settings import Settings

    return Fetcher(Settings(
        data_dir=tmp_path, config_dir=tmp_path, retry_attempts=1, per_host_delay_seconds=0.25,
    ))


# ---------------------------------------------------------------------------------------
# Records -> boards.
# ---------------------------------------------------------------------------------------


def test_the_census_partitions_every_record_it_read():
    """Nothing is dropped silently: the four buckets must sum to the records read."""
    census = discover(_sources()).census
    assert census.records == len(_all_records())
    assert census.records == (
        census.inactive + census.no_url + census.unparseable_url + census.matched
    )
    assert census.inactive > 0 and census.no_url > 0 and census.unparseable_url > 0


def test_the_seven_malformed_urls_are_refused_as_ordinary_input():
    """Contract §5 trap 1: `UnknownBoardURL`, the same class 47% of records raise.

    So there is no exception path. What must NOT happen is a traceback, and what must not happen
    either is a board named after an empty host.
    """
    result = discover(_sources())
    assert result.census.unparseable_url >= len(MALFORMED_URLS)
    for candidate in result.candidates:
        assert candidate.slug
        assert "workable.com" not in candidate.slug


def test_a_missing_url_key_and_a_non_string_url_are_counted_not_crashed():
    """Zero live records; both would crash a reader that passed the value straight through."""
    census = discover({
        "authored": [
            {"active": True, "company_name": "No URL"},
            {"active": True, "company_name": "Int URL", "url": 12345},
            {"active": True, "company_name": "Blank URL", "url": "   "},
        ]
    }).census
    assert (census.records, census.no_url, census.matched) == (3, 3, 0)


def test_inactive_records_are_excluded_and_counted():
    """The owner's scope is `active is True`. A truthy non-True value is NOT active."""
    census = discover({
        "authored": [
            {"active": False, "url": "https://job-boards.greenhouse.io/a/jobs/1"},
            {"active": "yes", "url": "https://job-boards.greenhouse.io/b/jobs/1"},
            {"url": "https://job-boards.greenhouse.io/c/jobs/1"},
            {"active": True, "url": "https://job-boards.greenhouse.io/d/jobs/1"},
        ]
    }).census
    assert (census.records, census.inactive, census.matched) == (4, 3, 1)


def test_workday_keeps_its_composite_and_smartrecruiters_is_lowercased():
    """The identity must be the one `companies` is UNIQUE on, per provider normalization."""
    by_key = {(c.provider, c.slug): c for c in discover(_sources()).candidates}
    assert ("workday", "acme01.wd1.myworkdayjobs.com/acme01/Careers") in by_key
    # The site segment's case is preserved and the tenant is lowercased -- workday board slugs
    # are case-sensitive live, and a lowercased site 404s forever.
    assert ("workday", "acme01.wd1.myworkdayjobs.com/acme01/careers") not in by_key
    # `jobs.smartrecruiters.com/Acme03/...` -- the provider normalizes the case.
    assert ("smartrecruiters", "acme03") in by_key
    assert ("smartrecruiters", "Acme03") not in by_key


def test_a_board_is_distinct_on_provider_and_slug_and_counts_its_records():
    """Neither `url` nor `(employer, title)` is unique live; `(provider, slug)` is the key."""
    candidates = discover(_sources()).candidates
    keys = [(c.provider, c.slug) for c in candidates]
    assert len(keys) == len(set(keys)) == _FIXTURE_BOARDS
    acme02 = next(c for c in candidates if (c.provider, c.slug) == ("greenhouse", "acme02"))
    # Two planned records plus the whitespace-padded one, all on one board.
    assert acme02.records == 3
    assert acme02.evidence_url.startswith("https://job-boards.greenhouse.io/acme02/jobs/")


def test_the_employer_name_is_stripped():
    """114 live S1 records are padded, and `companies.name` feeds the `cross_host` identity."""
    acme02 = next(
        c for c in discover(_sources()).candidates
        if (c.provider, c.slug) == ("greenhouse", "acme02")
    )
    assert acme02.name == "Acme 02"


def test_ats_chrome_that_parses_is_surfaced_with_the_evidence_that_condemns_it():
    """Contract §5 trap 2: `boards.greenhouse.io/embed/job_app?token=` -> the slug `embed`.

    Not filtered -- filtering it would need a per-provider chrome catalog this probe cannot
    justify, and the owner put a human between the list and the store for exactly this. What the
    candidate owes is the URL that makes it refusable at a glance.
    """
    embed = next(
        c for c in discover(_sources()).candidates
        if (c.provider, c.slug) == ("greenhouse", "embed")
    )
    assert embed.evidence_url == EMBED_URL


# ---------------------------------------------------------------------------------------
# The ramp.
# ---------------------------------------------------------------------------------------


def test_candidates_are_ordered_cheapest_provider_first():
    """The owner's ramp: the four inline-body providers, then workday, then smartrecruiters.

    Five of six providers serve every board from ONE host and `Fetcher` holds a per-host lock for
    each request's full duration, so boards on one provider serialize and no worker count
    compresses it. Only workday and smartrecruiters additionally spend `detail_fetch_budget` on a
    per-posting GET, and boardwatch watches ZERO smartrecruiters boards, so that path has never
    run at scale.
    """
    assert PROVIDER_PRIORITY == (
        "greenhouse", "lever", "ashby", "workable", "workday", "smartrecruiters"
    )
    providers = [c.provider for c in discover(_sources()).candidates]
    inline_positions = [i for i, p in enumerate(providers) if p in _INLINE_BODY]
    workday_positions = [i for i, p in enumerate(providers) if p == "workday"]
    sr_positions = [i for i, p in enumerate(providers) if p == "smartrecruiters"]
    assert max(inline_positions) < min(workday_positions)
    assert max(workday_positions) < min(sr_positions)
    # Deterministic within a provider, so re-running emits the same batch until it is imported.
    assert providers == [c.provider for c in discover(_sources()).candidates]


@pytest.mark.parametrize(
    "limit,expected_providers",
    [
        (0, set()),
        (10, set(_INLINE_BODY)),
        (_FIXTURE_INLINE_BOARDS, set(_INLINE_BODY)),
        (_FIXTURE_INLINE_BOARDS + 1, set(_INLINE_BODY) | {"workday"}),
        (_FIXTURE_INLINE_BOARDS + _FIXTURE_WORKDAY_BOARDS, set(_INLINE_BODY) | {"workday"}),
        (_FIXTURE_BOARDS, set(_INLINE_BODY) | set(_DETAIL_BUDGET)),
    ],
)
def test_the_cap_admits_exactly_its_limit_from_the_cheapest_tiers_first(limit, expected_providers):
    result = discover(_sources())
    selection = select(result, is_known=_never_known, budget=CompanyBudget(limit))
    assert len(selection.admitted) == min(limit, _FIXTURE_BOARDS)
    assert {c.provider for c in selection.admitted} == expected_providers
    assert len(selection.admitted) + len(selection.refused) == _FIXTURE_BOARDS


def test_smartrecruiters_is_admitted_last_and_only_when_nothing_cheaper_is_left():
    result = discover(_sources())
    just_short = select(
        result, is_known=_never_known,
        budget=CompanyBudget(_FIXTURE_BOARDS - _FIXTURE_SMARTRECRUITERS_BOARDS),
    )
    assert not any(c.provider == "smartrecruiters" for c in just_short.admitted)
    assert {c.provider for c in just_short.refused} == {"smartrecruiters"}


def test_a_board_already_in_the_store_is_excluded_and_costs_no_cap_slot():
    """`company_exists`, not the watched-only lookup: a lane row is stored UNWATCHED, so asking
    the watched view would charge a slot to a company already stored, every run, forever."""
    result = discover(_sources())
    known = {(c.provider, c.slug) for c in result.candidates[:5]}
    selection = select(
        result, is_known=lambda p, s: (p, s) in known, budget=CompanyBudget(10),
    )
    assert {(c.provider, c.slug) for c in selection.already_known} == known
    assert len(selection.admitted) == 10
    assert not (known & {(c.provider, c.slug) for c in selection.admitted})
    assert len(selection.admitted) + len(selection.refused) + len(known) == _FIXTURE_BOARDS


def test_the_budget_and_the_selection_agree_about_both_sides():
    """Counted through a different path than the one that produced it."""
    result = discover(_sources())
    budget = CompanyBudget(7)
    selection = select(result, is_known=_never_known, budget=budget)
    assert budget.admitted == tuple((c.provider, c.slug) for c in selection.admitted)
    assert budget.refused == tuple((c.provider, c.slug) for c in selection.refused)


# ---------------------------------------------------------------------------------------
# The emitted candidate file.
# ---------------------------------------------------------------------------------------


def _document(limit: int = 10) -> str:
    result = discover(_sources())
    selection = select(result, is_known=_never_known, budget=CompanyBudget(limit))
    return candidate_document(selection, census=result.census, generated_on=date(2026, 8, 24))


def test_the_emitted_document_is_accepted_by_the_registry_validator():
    """`companies import`'s own path: model_validate, then validate_entries. Nothing else."""
    entries = [
        CompanyEntry.model_validate(row)
        for row in yaml.safe_load(_document())["companies"]
    ]
    assert len(entries) == 10
    assert validate_entries(entries) == entries
    # `extra="forbid"`, so a provenance FIELD would fail validation. The provenance lives in the
    # header comment instead, which `yaml.safe_load` ignores.
    for row in yaml.safe_load(_document())["companies"]:
        assert set(row) == {"name", "provider", "slug", "tags"}


def test_the_header_carries_the_census_the_sources_and_the_cap():
    """A file a human reviews asynchronously has to say what it excluded, not just what it kept."""
    document = _document()
    header = [line for line in document.splitlines() if line.startswith("#")]
    blob = "\n".join(header)
    assert S1_REPO in blob and S2_REPO in blob
    assert "2026-08-24" in blob
    census = discover(_sources()).census
    for number in (census.records, census.inactive, census.unparseable_url, _FIXTURE_BOARDS):
        assert str(number) in blob
    # Every admitted board is reviewable from the header alone: identity, employer, evidence.
    for row in yaml.safe_load(document)["companies"]:
        candidate = next(
            c for c in discover(_sources()).candidates
            if (c.provider, c.slug) == (row["provider"], row["slug"])
        )
        assert candidate.evidence_url in blob


def test_a_yaml_hostile_slug_survives_the_round_trip():
    """A public list can name a board `no`, `123` or `~`, all of which YAML 1.1 retypes."""
    from boardwatch.lanes.github_lists import BoardCandidate, RecordCensus, Selection

    hostile = tuple(
        BoardCandidate(
            provider="greenhouse", slug=slug, name=slug,
            evidence_url=f"https://job-boards.greenhouse.io/{slug}/jobs/1", records=1,
        )
        for slug in ("no", "yes", "on", "off", "true", "123", "1.5", "null", "~", "y")
    )
    document = candidate_document(
        Selection(admitted=hostile, refused=(), already_known=()),
        census=RecordCensus(records=10, matched=10),
        generated_on=date(2026, 8, 24),
    )
    rows = yaml.safe_load(document)["companies"]
    assert [row["slug"] for row in rows] == [c.slug for c in hostile]
    assert all(isinstance(row["slug"], str) and isinstance(row["name"], str) for row in rows)


def test_an_empty_selection_still_emits_a_readable_file():
    """Zero new boards is the steady state once the ramp finishes. It is not an error."""
    document = _document(limit=0)
    assert yaml.safe_load(document)["companies"] == []
    assert "#" in document


def test_the_module_is_not_a_lane():
    """It has no postings and no tally, so it cannot satisfy `LaneResult`. Registering it in
    `LANE_FACTORIES` would make the pipeline call `collect(fetcher, admits)` on it every run."""
    from boardwatch.pipeline.runner import LANE_FACTORIES

    assert not hasattr(github_lists, "collect")
    assert "github_lists" not in LANE_FACTORIES


def test_the_ramp_ranks_every_registered_provider_and_no_others():
    """Bidirectional, and the direction that matters is the one that fires on a SEVENTH provider.

    `parse_board_target` can only return a registered provider, so an unranked one means a
    provider was added without placing its first-exposure cost in the ramp -- and the cap would
    then admit it without anyone deciding where it belongs. `UnrankedProvider` makes that a
    failure at the ranking site; this makes it a failure at merge time instead.
    """
    from boardwatch.providers.registry import PROVIDER_NAMES

    assert set(PROVIDER_PRIORITY) == set(PROVIDER_NAMES)
    assert len(PROVIDER_PRIORITY) == len(set(PROVIDER_PRIORITY)) == 6


def test_an_unranked_provider_is_a_failure_and_not_a_quiet_last_place():
    from boardwatch.lanes.github_lists import UnrankedProvider, ramp_order

    with pytest.raises(UnrankedProvider):
        ramp_order({("hiringcafe", "icims2:acme"): []})


def test_a_batch_is_spread_across_a_tier_rather_than_draining_one_provider():
    """Ordering WITHIN a cost tier is free, and spreading it buys two things.

    Ten boards on one provider are ten serial requests -- `Fetcher` holds a per-host lock for each
    request's full duration and five of six providers serve every board from one host. And
    workable, which boardwatch watches zero of, would otherwise wait out greenhouse's 147, lever's
    62 and ashby's 167 before being exercised at all.

    The tier BOUNDARIES are the owner's ruling and are asserted separately; this is the part the
    ruling leaves open.
    """
    from boardwatch.lanes.github_lists import ramp_order

    boards = {
        (provider, f"{provider}{n}"): []
        for provider, count in (
            ("greenhouse", 4), ("lever", 2), ("ashby", 3), ("workable", 1),
            ("workday", 2), ("smartrecruiters", 2),
        )
        for n in range(count)
    }
    order = [provider for provider, _slug in ramp_order(boards)]
    assert order[:4] == ["greenhouse", "lever", "ashby", "workable"]
    assert order[4:7] == ["greenhouse", "lever", "ashby"]
    assert order[7:9] == ["greenhouse", "ashby"]
    assert order[9] == "greenhouse"
    assert order[10:] == ["workday", "workday", "smartrecruiters", "smartrecruiters"]


def test_the_census_reports_whether_it_partitions():
    from boardwatch.lanes.github_lists import RecordCensus

    assert RecordCensus(records=4, inactive=1, no_url=1, unparseable_url=1, matched=1).partitions
    assert not RecordCensus(records=4, matched=1).partitions

"""The job-apps ingestion lane (D-385).

The tests that matter most here are the ones about ABSENCE. A filesystem source can fail in a
way a network source cannot -- by quietly not being there -- and the record count carries no
health signal in either direction: it tracks the owner's backlog, not a fixed population, and
group folders legitimately hold zero on any given day. The tests below that assert a raise are
checking a STRUCTURAL break (an absent source, an unreadable one, no group folder at all, or
candidates that fail to parse); the one that asserts no raise is checking that a tree which is
intact but currently empty of records is reported as a clean zero instead.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from boardwatch.core.politeness import Fetcher
from boardwatch.core.settings import Settings
from boardwatch.eligibility.catalog import load_rules
from boardwatch.eligibility.engine import evaluate
from boardwatch.eligibility.facts import Facts, Policy
from boardwatch.lanes.base import Lane
from boardwatch.lanes.jobapps import (
    SUPPORTED_SCHEMA_VERSION,
    JobAppsLane,
    JobAppsSourceError,
    strip_header,
    unescape_markdown,
)

# The real separator: a THREE-line sandwich, byte-identical in 930 of 930 sampled files.
_RULE = "=" * 80
_MARKER = f"{_RULE}\nJOB DESCRIPTION\n{_RULE}"

# job-apps' authored header, carrying the three lines that leaked into a blind audit set.
_HEADER = (
    "Company:  Acme\n"
    "Role:     Software Engineer\n"
    "Source:   Greenhouse-API\n"
    "URL:      https://example.invalid/x\n"
    "Template: SDE\n"
    "Fit:      40/100\n"
    "Target:   Yes (curated H-1B sponsor)\n"
)

_BODY = "We are hiring a backend engineer. Requirements: 2+ years of Python.\n"

_ALL = object()


def _fetcher(tmp_path: Path) -> Fetcher:
    return Fetcher(
        Settings(
            data_dir=tmp_path, config_dir=tmp_path, retry_attempts=1,
            per_host_delay_seconds=0.25,
        )
    )


def _write(
    root: Path,
    ats: str,
    name: str,
    *,
    company: str = "Acme",
    title: str = "Software Engineer",
    direct_url: str = "https://job-boards.greenhouse.io/gitlab/jobs/8698330002",
    location: str = "Remote, United States",
    acquisition: str = "greenhouse_api",
    posting_id: str | None = None,
    schema_version: int = SUPPORTED_SCHEMA_VERSION,
    jd: object = _ALL,
    extra: dict[str, object] | None = None,
) -> Path:
    """One record folder, shaped exactly as the live tree shapes it."""
    folder = root / ats / name
    folder.mkdir(parents=True)
    payload: dict[str, object] = {
        "schema_version": schema_version,
        "posting_id": posting_id or f"pst_{name}",
        "primary_acquisition": acquisition,
        "cohort_date": "2026-08-29",
        "canonical": {
            "company": company,
            "title": title,
            "direct_url": direct_url,
            "location": location,
        },
    }
    if extra:
        payload.update(extra)
    (folder / "discovery_record.json").write_text(json.dumps(payload), encoding="utf-8")
    text = f"{_HEADER}{_MARKER}\n\n{_BODY}" if jd is _ALL else jd
    if text is not None:
        (folder / "job_description.txt").write_text(str(text), encoding="utf-8")
    return folder


def _collect(root: Path | None, tmp_path: Path, admits=lambda provider, slug: True):
    return JobAppsLane(source_dir=root).collect(_fetcher(tmp_path), admits)


def _collect_two(source: Path | None, queue: Path | None, tmp_path: Path):
    return JobAppsLane(source_dir=source, queue_dir=queue).collect(
        _fetcher(tmp_path), lambda provider, slug: True
    )


def _postings(result):
    return [posting for snapshot in result.snapshots for posting in snapshot.snapshot.postings]


# ---------------------------------------------------------------------------------------
# Protocol conformance.
# ---------------------------------------------------------------------------------------


def test_the_lane_satisfies_the_lane_protocol():
    assert JobAppsLane.name == "jobapps"
    assert list(inspect.signature(JobAppsLane.collect).parameters) == list(
        inspect.signature(Lane.collect).parameters
    ) == ["self", "fetcher", "admits"]


def test_the_lane_is_registered_and_still_disarmed_by_default():
    """Registered is not enabled -- the whole reason merging this changes no run."""
    from boardwatch.pipeline.runner import LANE_FACTORIES

    assert "jobapps" in LANE_FACTORIES
    assert Settings(data_dir=Path("/x"), config_dir=Path("/x")).lanes_enabled == ()
    assert Settings(data_dir=Path("/x"), config_dir=Path("/x")).jobapps_discovery_dir is None


# ---------------------------------------------------------------------------------------
# A missing source can never read as a quiet feed.
# ---------------------------------------------------------------------------------------


def test_an_unset_source_dir_raises_rather_than_returning_an_empty_result(tmp_path):
    with pytest.raises(JobAppsSourceError, match="no source directory configured"):
        _collect(None, tmp_path)


def test_an_absent_source_dir_raises(tmp_path):
    with pytest.raises(JobAppsSourceError, match="absent or not a directory"):
        _collect(tmp_path / "nope", tmp_path)


def test_a_source_dir_that_is_a_file_raises(tmp_path):
    target = tmp_path / "afile"
    target.write_text("x", encoding="utf-8")
    with pytest.raises(JobAppsSourceError, match="absent or not a directory"):
        _collect(target, tmp_path)


def test_a_tree_with_no_group_folder_at_all_raises(tmp_path):
    """The failure this lane exists to make visible: a renamed queue, or a layout change."""
    root = tmp_path / "queue"
    root.mkdir()
    with pytest.raises(JobAppsSourceError, match="no group folder anywhere"):
        _collect(root, tmp_path)


def test_a_schema_bump_is_reported_as_a_FORMAT_change_not_a_missing_queue(tmp_path):
    """Both causes end with zero usable records and want opposite fixes, so they must not
    share one message."""
    root = tmp_path / "queue"
    _write(root, "Greenhouse", "a", schema_version=SUPPORTED_SCHEMA_VERSION + 1)
    with pytest.raises(JobAppsSourceError, match="record format has probably moved"):
        _collect(root, tmp_path)


# ---------------------------------------------------------------------------------------
# A tree that is intact but currently empty is the owner catching up, not a break.
# ---------------------------------------------------------------------------------------


def test_group_folders_present_with_zero_records_returns_a_clean_zero_not_a_raise(tmp_path):
    """`attempted` tracks the owner's backlog, not a fixed corpus -- he drains each group folder
    as he works it, so a group folder that currently holds no discovery record is normal, not a
    structural break. This must NOT raise."""
    root = tmp_path / "queue"
    (root / "Greenhouse" / "Some_Role").mkdir(parents=True)
    result = _collect(root, tmp_path)
    assert _postings(result) == []


# ---------------------------------------------------------------------------------------
# The header, and the verdicts inside it.
# ---------------------------------------------------------------------------------------


def test_strip_header_removes_every_line_of_the_three_line_sandwich():
    """Discriminating against the one-line form: matching a single rule line leaves two behind."""
    body = strip_header(f"{_HEADER}{_MARKER}\n\n{_BODY}")
    assert body == _BODY
    assert "JOB DESCRIPTION" not in body
    assert _RULE not in body


def test_strip_header_fails_closed_when_the_separator_is_absent():
    assert strip_header(f"{_HEADER}{_BODY}") is None


def test_a_jd_with_no_separator_yields_no_posting_and_is_counted(tmp_path):
    root = tmp_path / "queue"
    _write(root, "Greenhouse", "a", jd=f"{_HEADER}{_BODY}")
    result = _collect(root, tmp_path)
    assert _postings(result) == []
    assert result.tally.counts["extracted_empty"] == 1
    assert result.tally.counts["body_inline"] == 0


def test_a_missing_jd_file_yields_no_posting_and_is_counted(tmp_path):
    root = tmp_path / "queue"
    _write(root, "Greenhouse", "a", jd=None)
    result = _collect(root, tmp_path)
    assert _postings(result) == []
    assert result.tally.counts["extracted_empty"] == 1


def test_no_verdict_line_from_the_header_reaches_the_body(tmp_path):
    root = tmp_path / "queue"
    _write(root, "Greenhouse", "a")
    (posting,) = _postings(_collect(root, tmp_path))
    for leaked in ("Template:", "Fit:", "40/100", "Target:", "curated H-1B sponsor", "URL:"):
        assert leaked not in posting.body_text
    assert posting.body_text == _BODY


# ---------------------------------------------------------------------------------------
# job-apps contributes discovery, never judgement.
# ---------------------------------------------------------------------------------------


def test_raw_json_carries_provenance_and_none_of_job_apps_judgement(tmp_path):
    root = tmp_path / "queue"
    _write(
        root, "Greenhouse", "a",
        extra={
            "dispositions": [{"stage": "eligibility", "outcome": "review", "reason": "senior"}],
            "observations": [{"employer_verification": "yes", "query_kind": "target"}],
        },
    )
    (posting,) = _postings(_collect(root, tmp_path))
    serialized = json.dumps(posting.raw_json)
    assert "dispositions" not in serialized
    assert "observations" not in serialized
    assert "senior" not in serialized
    assert posting.raw_json["jobapps"]["primary_acquisition"] == "greenhouse_api"
    assert posting.raw_json["jobapps"]["cohort_date"] == "2026-08-29"


def test_the_skipped_and_applied_directories_are_never_walked(tmp_path):
    """Their subdirectory NAMES are job-apps' verdicts; recursing would inherit them."""
    root = tmp_path / "queue"
    _write(root, "Greenhouse", "kept")
    _write(root, "_skipped", "posting_closed")
    _write(root, "_applied", "already_done")
    titles = {posting.provider_posting_id for posting in _postings(_collect(root, tmp_path))}
    assert titles == {"8698330002"}


def test_cohort_date_is_not_used_as_a_posting_date(tmp_path):
    """The ranker is recency-dominated: a discovery date fed in as a posting date fakes freshness."""
    root = tmp_path / "queue"
    _write(root, "Greenhouse", "a")
    (posting,) = _postings(_collect(root, tmp_path))
    assert posting.posted_at is None
    assert posting.updated_at is None


# ---------------------------------------------------------------------------------------
# Reach: which records are usable at all.
# ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("acquisition", ["linkedin"])
def test_an_aggregator_only_record_is_counted_and_not_ingested(tmp_path, acquisition):
    """`linkedin` is the aggregator that stays OUT, and deliberately so: boardwatch runs its own
    LinkedIn lane, so admitting these would duplicate a lane we already have against an identity
    scheme that cannot converge the two. It is the largest source in the tree (88 records), and
    that reach is bought by un-throttling our own lane instead."""
    root = tmp_path / "queue"
    _write(root, "Greenhouse", "ok")
    _write(root, "LinkedIn", "agg", acquisition=acquisition, posting_id="pst_agg")
    result = _collect(root, tmp_path)
    assert len(_postings(result)) == 1
    assert result.tally.counts["not_attemptable"] == 1


@pytest.mark.parametrize(
    "acquisition", ["hiringcafe", "simplify", "speedyapply", "zapply", "hn", "greenhouse_api"]
)
def test_a_direct_apply_record_is_ingested(tmp_path, acquisition):
    root = tmp_path / "queue"
    _write(root, "Greenhouse", "a", acquisition=acquisition)
    assert len(_postings(_collect(root, tmp_path))) == 1


@pytest.mark.parametrize("acquisition", ["indeed", "jobright"])
def test_the_two_admitted_aggregators_are_ingested(tmp_path, acquisition):
    """The 24.2% slice (D-393 item 3). These two carry a posting-SPECIFIC url in
    `canonical.direct_url` -- `indeed.com/viewjob?jk=<key>` and `jobright.ai/jobs/info/<id>` --
    rather than a search page, and the JD body is already on disk, so the slice costs zero
    network requests. Measured over the live tree: indeed 48 records, jobright 5.

    Separate from `test_a_direct_apply_record_is_ingested` on purpose: these are the two the
    closed set was widened for, and if a later change narrows it again this test names exactly
    what was lost rather than one parametrise case going quiet."""
    root = tmp_path / "queue"
    _write(root, "Other", "a", acquisition=acquisition)
    assert len(_postings(_collect(root, tmp_path))) == 1


def test_the_promoted_queue_is_read_as_a_second_root(tmp_path):
    """job-apps MOVES a folder out of the discovery tree when it promotes it, so a posting used
    to become invisible to boardwatch at exactly the moment it became one the owner was working
    on. Measured against the real trees: discovery holds 190 records and the promoted queue holds
    737 -- and 737 is the number this lane's own docstring was written against, before the drain.
    """
    discovery = tmp_path / "resumes"
    promoted = tmp_path / "APPLY_QUEUE"
    # Distinct direct_urls, or the two collide on posting identity and the second is correctly
    # deduped as an in-tree duplicate -- which would make this test pass for the wrong reason.
    _write(
        discovery, "Greenhouse", "fresh",
        title="Fresh Discovery Role",
        direct_url="https://job-boards.greenhouse.io/gitlab/jobs/1111111111",
    )
    _write(
        promoted, "Ashby", "promoted",
        title="Promoted Role", posting_id="pst_promoted",
        direct_url="https://job-boards.greenhouse.io/gitlab/jobs/2222222222",
    )

    result = _collect_two(discovery, promoted, tmp_path)

    titles = {posting.title for posting in _postings(result)}
    assert titles == {"Fresh Discovery Role", "Promoted Role"}, titles


def test_a_break_in_either_root_is_still_visible(tmp_path):
    """Per root, never folded: a moved discovery tree must not hide behind a healthy queue tree.
    Folding the two would defeat the structural check this lane exists to carry."""
    discovery = tmp_path / "resumes"
    promoted = tmp_path / "APPLY_QUEUE"
    _write(promoted, "Ashby", "promoted")  # healthy
    with pytest.raises(JobAppsSourceError):
        _collect_two(discovery, promoted, tmp_path)  # discovery absent


def test_an_unset_queue_root_is_exactly_the_previous_behaviour(tmp_path):
    root = tmp_path / "queue"
    _write(root, "Greenhouse", "a")
    assert len(_postings(_collect_two(root, None, tmp_path))) == 1


def test_an_unknown_acquisition_source_is_skipped_rather_than_trusted(tmp_path):
    """A closed set: a NEW source is counted, not silently assumed direct-apply."""
    root = tmp_path / "queue"
    _write(root, "Other", "a", acquisition="brand_new_aggregator")
    result = _collect(root, tmp_path)
    assert _postings(result) == []
    assert result.tally.counts["not_attemptable"] == 1


def test_a_duplicate_posting_id_is_ingested_once_and_counted(tmp_path):
    root = tmp_path / "queue"
    _write(root, "Greenhouse", "a", posting_id="pst_same")
    _write(root, "Lever", "b", posting_id="pst_same", direct_url="https://jobs.lever.co/acme")
    result = _collect(root, tmp_path)
    assert len(_postings(result)) == 1
    assert result.tally.counts["not_attemptable"] == 1


def test_two_records_dereferencing_to_one_posting_are_ingested_once(tmp_path):
    """The convergence case, and the one that would ABORT the lane stage if it slipped through.

    Two DIFFERENT job-apps records (distinct `posting_id`, as if found through hiring.cafe and
    simplify) whose `direct_url` is the same posting. Deduplicating on `posting_id` alone lets
    both through, and two postings sharing a `provider_posting_id` violate
    UNIQUE(company_id, provider_posting_id) inside `apply_board`'s single transaction -- which
    rolls the board back and discards every later company with it.
    """
    root = tmp_path / "queue"
    _write(root, "Greenhouse", "viahiringcafe", acquisition="hiringcafe", posting_id="pst_1")
    _write(root, "Other", "viasimplify", acquisition="simplify", posting_id="pst_2")
    result = _collect(root, tmp_path)
    postings = _postings(result)
    assert len(postings) == 1
    assert result.tally.counts["not_attemptable"] == 1


def test_no_snapshot_ever_holds_two_postings_with_one_provider_posting_id(tmp_path):
    """The invariant itself, stated independently of how it is achieved."""
    root = tmp_path / "queue"
    for index in range(4):
        _write(root, "Greenhouse", f"a{index}", acquisition="hiringcafe", posting_id=f"pst_{index}")
    for snapshot in _collect(root, tmp_path).snapshots:
        ids = [posting.provider_posting_id for posting in snapshot.snapshot.postings]
        assert len(ids) == len(set(ids))


def test_a_record_at_an_unsupported_schema_version_is_skipped(tmp_path):
    root = tmp_path / "queue"
    _write(root, "Greenhouse", "ok")
    _write(root, "Greenhouse", "future", schema_version=99, posting_id="pst_future")
    assert len(_postings(_collect(root, tmp_path))) == 1


@pytest.mark.parametrize("missing", ["company", "title", "direct_url"])
def test_a_record_missing_a_required_canonical_field_is_skipped(tmp_path, missing):
    root = tmp_path / "queue"
    _write(root, "Greenhouse", "ok")
    folder = _write(root, "Greenhouse", "bad", posting_id="pst_bad")
    payload = json.loads((folder / "discovery_record.json").read_text())
    payload["canonical"][missing] = ""
    (folder / "discovery_record.json").write_text(json.dumps(payload), encoding="utf-8")
    assert len(_postings(_collect(root, tmp_path))) == 1


# ---------------------------------------------------------------------------------------
# Identity: the three-tier ladder.
# ---------------------------------------------------------------------------------------


def test_tier_one_uses_the_real_provider_slug_and_posting_reference(tmp_path):
    root = tmp_path / "queue"
    _write(root, "Greenhouse", "a")
    (snapshot,) = _collect(root, tmp_path).snapshots
    assert (snapshot.provider, snapshot.slug) == ("greenhouse", "gitlab")
    assert snapshot.snapshot.postings[0].provider_posting_id == "8698330002"


def test_tier_two_keeps_the_real_company_and_falls_back_for_the_reference(tmp_path):
    root = tmp_path / "queue"
    _write(root, "Ashby", "a", direct_url="https://jobs.ashbyhq.com/openai", posting_id="pst_x")
    (snapshot,) = _collect(root, tmp_path).snapshots
    assert (snapshot.provider, snapshot.slug) == ("ashby", "openai")
    assert snapshot.snapshot.postings[0].provider_posting_id == "pst_x"


def test_tier_three_falls_back_to_the_lane_namespace(tmp_path):
    root = tmp_path / "queue"
    _write(
        root, "Other", "a",
        company="TikTok Inc.",
        direct_url="https://lifeattiktok.com/search/123",
        posting_id="pst_y",
    )
    (snapshot,) = _collect(root, tmp_path).snapshots
    assert (snapshot.provider, snapshot.slug) == ("jobapps", "tiktok-inc")
    assert snapshot.snapshot.postings[0].provider_posting_id == "pst_y"


def test_two_spellings_of_one_lane_company_still_collapse_to_one_slug(tmp_path):
    root = tmp_path / "queue"
    for index, spelling in enumerate(("Acme Corp", "acme  corp")):
        _write(
            root, "Other", f"a{index}",
            company=spelling,
            direct_url=f"https://lifeattiktok.com/search/{index}",
            posting_id=f"pst_{index}",
        )
    (snapshot,) = _collect(root, tmp_path).snapshots
    assert snapshot.slug == "acme-corp"
    assert len(snapshot.snapshot.postings) == 2


def test_the_first_spelling_wins_the_display_name(tmp_path):
    """Matches `upsert_lane_company`, which touches nothing on conflict."""
    root = tmp_path / "queue"
    for index, spelling in enumerate(("Acme Corp", "acme  corp")):
        _write(
            root, "Other", f"a{index}",
            company=spelling,
            direct_url=f"https://lifeattiktok.com/search/{index}",
            posting_id=f"pst_{index}",
        )
    (snapshot,) = _collect(root, tmp_path).snapshots
    assert snapshot.name == "Acme Corp"


# ---------------------------------------------------------------------------------------
# The snapshot, the admission contract and locations.
# ---------------------------------------------------------------------------------------


def test_the_snapshot_is_always_partial_and_lists_no_ids(tmp_path):
    """A lane never enumerates a whole board, so it must never claim `complete` (D-314)."""
    root = tmp_path / "queue"
    _write(root, "Greenhouse", "a")
    (snapshot,) = _collect(root, tmp_path).snapshots
    assert snapshot.snapshot.status == "partial"
    assert snapshot.snapshot.listed_ids == frozenset()
    assert snapshot.snapshot.board_reported_total is None


def test_admits_is_asked_once_per_distinct_company_never_once_per_posting(tmp_path):
    root = tmp_path / "queue"
    for index in range(3):
        _write(
            root, "Greenhouse", f"a{index}",
            direct_url=f"https://job-boards.greenhouse.io/gitlab/jobs/{index}",
            posting_id=f"pst_{index}",
        )
    _write(root, "Ashby", "b", direct_url="https://jobs.ashbyhq.com/openai", posting_id="pst_b")
    asked: list[tuple[str, str]] = []

    def _admits(provider: str, slug: str) -> bool:
        asked.append((provider, slug))
        return True

    _collect(root, tmp_path, _admits)
    # Directory order, so Ashby precedes Greenhouse. The point is the LENGTH: three greenhouse
    # postings share one company and must cost one question, not three.
    assert asked == [("ashby", "openai"), ("greenhouse", "gitlab")]
    assert len(asked) == len(set(asked)) == 2


def test_a_refused_company_yields_no_snapshot_and_no_tally_entry(tmp_path):
    root = tmp_path / "queue"
    _write(root, "Greenhouse", "a")
    result = _collect(root, tmp_path, lambda provider, slug: False)
    assert result.snapshots == ()
    assert result.tally.counts["body_inline"] == 0
    assert result.tally.counts["not_attemptable"] == 0


def test_locations_split_on_semicolons_and_not_on_commas(tmp_path):
    """"Remote, Canada" is ONE location; splitting on the comma loses the country."""
    root = tmp_path / "queue"
    _write(root, "Greenhouse", "a", location="Remote, Canada; Remote, United States")
    (posting,) = _postings(_collect(root, tmp_path))
    assert posting.locations == ["Remote, Canada", "Remote, United States"]


def test_a_blank_location_yields_an_empty_list(tmp_path):
    root = tmp_path / "queue"
    _write(root, "Greenhouse", "a", location="")
    (posting,) = _postings(_collect(root, tmp_path))
    assert posting.locations == []


def test_the_posting_url_is_the_employers_own_apply_page(tmp_path):
    root = tmp_path / "queue"
    _write(root, "Greenhouse", "a")
    (posting,) = _postings(_collect(root, tmp_path))
    assert posting.url == "https://job-boards.greenhouse.io/gitlab/jobs/8698330002"


def test_no_search_page_is_reported_because_there_is_no_search(tmp_path):
    root = tmp_path / "queue"
    _write(root, "Greenhouse", "a")
    assert _collect(root, tmp_path).search_pages == ()


class _ExplodingFetcher:
    """Fails on ANY attribute access, so it cannot pass for the wrong reason.

    Patching one named method would be vacuous twice over: it assumes a method name this test
    never verified, and `collect` drops its `fetcher` on the first line, so nothing could call it
    anyway. Touching ANY attribute is the property actually worth asserting, and this fails the
    moment a future edit reaches for the fetcher at all.
    """

    def __getattr__(self, name: str) -> object:
        raise AssertionError(f"the jobapps lane must not use the fetcher (touched {name!r})")


def test_the_lane_never_touches_the_fetcher(tmp_path):
    """The bodies are on disk. A socket opened here would be a bug, not an optimisation."""
    root = tmp_path / "queue"
    _write(root, "Greenhouse", "a")
    result = JobAppsLane(source_dir=root).collect(
        _ExplodingFetcher(),  # type: ignore[arg-type]
        lambda provider, slug: True,
    )
    assert len(_postings(result)) == 1


def test_a_partly_refused_run_tallies_only_the_admitted_company(tmp_path):
    """The first armed run refuses ~93 of 103 new employers, and refusals are NOT tallied.

    So the tally on that run under-reports what the source held, by design -- refusals are named
    in `LaneReport.refused` instead. Pinned here so nobody reads the tally alone and concludes
    the source shrank.
    """
    root = tmp_path / "queue"
    _write(root, "Greenhouse", "kept")
    _write(root, "Ashby", "refused", direct_url="https://jobs.ashbyhq.com/openai", posting_id="p2")
    result = _collect(root, tmp_path, lambda provider, slug: provider == "greenhouse")
    (snapshot,) = result.snapshots
    assert (snapshot.provider, snapshot.slug) == ("greenhouse", "gitlab")
    assert result.tally.counts["body_inline"] == 1
    assert result.tally.counts["not_attemptable"] == 0
    assert result.tally.attempted == 1, "a refused company must not enter the tally at all"


# ---------------------------------------------------------------------------------------
# job-apps' markdown escapes (D-443).
#
# This lane is the ONLY one that carries them: measured over the live store, 473 of the 1,620
# bodies it ingests (29.2%) contain a backslash escape, and every other provider measures 0.0%.
# ---------------------------------------------------------------------------------------

# Verbatim from a live body the catalog could not read.
_ESCAPED_BAR = r"3\+ years of experience in software engineering or a relevant field."
_PLAIN_BAR = "3+ years of experience in software engineering or a relevant field."

# The most common escaped form on this lane, and it stays SILENT even unescaped: the catalog
# has no arm for four modifiers between `of` and `experience`. Pinned so the residual is
# visible rather than assumed fixed by D-443 -- unescaping is necessary here, not sufficient.
_STILL_UNCOVERED = "3+ years of non-internship professional software development experience"


@pytest.mark.parametrize(
    ("escaped", "plain"),
    [
        (_ESCAPED_BAR, _PLAIN_BAR),
        (r"H\-1B sponsorship is not available", "H-1B sponsorship is not available"),
        (r"Requires U.S\. citizenship", "Requires U.S. citizenship"),
        (r"\* Bachelor's degree \(or equivalent\)", "* Bachelor's degree (or equivalent)"),
        (r"C\+\+ and Python", "C++ and Python"),
    ],
)
def test_markdown_escapes_are_removed(escaped, plain):
    assert unescape_markdown(escaped) == plain


@pytest.mark.parametrize(
    "untouched",
    [
        r"Caf\u00e9 in the office",   # undecoded JSON escape: dropping the backslash leaves `u00e9`
        r"line one\nline two",        # same, for a newline
        r"column\tseparated",
        r"regex classes \d and \w are not escapes at all",
    ],
)
def test_a_non_punctuation_escape_is_left_exactly_as_job_apps_wrote_it(untouched):
    """`\\uXXXX` outnumbers every markdown escape on disk (150,665 to 540,050 for `\\-`).

    It is a DIFFERENT and unfixed upstream defect. Unescaping it would put the literal text
    `u00e9` into the frozen JD, which is worse than the escape, so the punctuation restriction
    in `_MARKDOWN_ESCAPE` is load-bearing rather than incidental.
    """
    assert unescape_markdown(untouched) == untouched


def test_the_escaped_years_bar_writes_NO_requirement_row_and_the_plain_one_does():
    """The reason this fix exists, pinned against the eligibility engine rather than asserted.

    A backslash before `+` is invisible to a reader and fatal to the catalog: the escaped
    sentence produces ZERO requirement rows, so the posting carries nothing evaluable, lands
    `uncertain`, and routes to the APPLY lane as blindly-appliable. Measured over the live
    store, 132 jobapps bodies go from zero rows to some rows on this change alone, and 83
    verdicts move -- 70 of them `uncertain` to `ineligible`.

    If the unescape is ever reverted, THIS is the assertion that fails.
    """
    catalog = load_rules(Path("/nonexistent"))  # bundled catalog
    facts = Facts(total_years_experience=1)
    policy = Policy()

    def years(body: str) -> list[str]:
        return [
            item.rule_id or ""
            for item in evaluate(body, facts, policy, catalog).requirements
            if (item.rule_id or "").startswith("experience_years:")
        ]

    assert years(_ESCAPED_BAR) == [], "the escaped bar must be what the catalog cannot see"
    assert years(_PLAIN_BAR), "and the plain bar must be what it can"
    assert years(unescape_markdown(_ESCAPED_BAR)) == years(_PLAIN_BAR)
    assert years(_STILL_UNCOVERED) == [], (
        "unescaping is necessary but NOT sufficient -- this form needs a catalog arm, and "
        "pinning it here keeps the residual from being read as closed"
    )


def test_a_body_read_off_disk_reaches_the_posting_unescaped(tmp_path):
    """End to end through the lane, because `unescape_markdown` being correct is not the claim.

    The claim is that `_body` APPLIES it -- a pure function nobody calls fixes nothing.
    """
    root = tmp_path / "queue"
    _write(root, "Greenhouse", "escaped", jd=f"{_HEADER}{_MARKER}\n\n{_ESCAPED_BAR}\n")
    (posting,) = _postings(_collect(root, tmp_path))
    assert posting.body_text is not None
    assert _PLAIN_BAR in posting.body_text
    assert "\\" not in posting.body_text


def test_the_header_strip_still_runs_before_the_unescape(tmp_path):
    """Order matters: unescaping first would not change the marker, but a body that fails to
    strip must still fail CLOSED rather than arriving unescaped-but-with-a-header."""
    root = tmp_path / "queue"
    _write(root, "Greenhouse", "noheader", jd=f"Company: Acme\n\n{_ESCAPED_BAR}\n")
    assert _postings(_collect(root, tmp_path)) == []

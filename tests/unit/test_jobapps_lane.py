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


def test_the_rejected_count_sums_across_both_roots(tmp_path):
    """T168's other follow-up: `_records` adds `_records_under`'s rejected count per root
    (`rejected += root_rejected`), so a cause in EITHER root must reach the tally, and one in
    BOTH roots must reach it twice -- not just the last root read. A dangling symlink under
    `discovery` and an ordinary unreadable (malformed JSON) record under the promoted queue,
    together, must count as two, and each root's readable record must still be ingested."""
    discovery = tmp_path / "resumes"
    promoted = tmp_path / "APPLY_QUEUE"
    _write(
        discovery, "Greenhouse", "ok",
        direct_url="https://job-boards.greenhouse.io/gitlab/jobs/1111111111",
    )
    dangling = discovery / "Greenhouse" / "dangling"
    dangling.mkdir(parents=True)
    (dangling / "discovery_record.json").symlink_to(dangling / "nonexistent_target.json")

    _write(
        promoted, "Ashby", "ok", posting_id="pst_promoted",
        direct_url="https://jobs.ashbyhq.com/openai",
    )
    corrupt = promoted / "Ashby" / "corrupt"
    corrupt.mkdir(parents=True)
    (corrupt / "discovery_record.json").write_text("{not json", encoding="utf-8")

    result = _collect_two(discovery, promoted, tmp_path)
    assert len(_postings(result)) == 2
    assert result.tally.counts["not_attemptable"] == 2


def _two_roots_sharing_one_record(tmp_path: Path) -> tuple[Path, Path]:
    """Two roots of two records each, one record in BOTH by the same `posting_id` -- the
    promotion race, where job-apps has copied a folder into the queue but not yet removed it from
    discovery. Three distinct employers, so a count of companies and a count of postings are the
    same number and either one exposes a root read twice or skipped."""
    discovery = tmp_path / "resumes"
    promoted = tmp_path / "APPLY_QUEUE"
    shared = {
        "company": "Shared Co", "title": "Shared Role", "posting_id": "pst_shared",
        "direct_url": "https://job-boards.greenhouse.io/sharedco/jobs/3333333333",
    }
    _write(
        discovery, "Greenhouse", "only-discovery", company="Alpha", title="Discovery Role",
        posting_id="pst_discovery",
        direct_url="https://job-boards.greenhouse.io/alpha/jobs/1111111111",
    )
    _write(discovery, "Greenhouse", "shared", **shared)
    _write(promoted, "Greenhouse", "shared", **shared)
    _write(
        promoted, "Greenhouse", "only-queue", company="Beta", title="Queue Role",
        posting_id="pst_queue",
        direct_url="https://job-boards.greenhouse.io/beta/jobs/2222222222",
    )
    return discovery, promoted


def test_two_roots_are_each_walked_once_and_yield_exactly_the_distinct_set(tmp_path, monkeypatch):
    """T218: the lane's count over two roots is the DISTINCT set -- three postings from four
    records, the cross-root duplicate counted once as `not_attemptable` -- and each root is
    walked exactly once, in order. A walk that reads the discovery root twice (in place of the
    queue, or in addition to it) either loses "Queue Role" or counts the two extra duplicates."""
    discovery, promoted = _two_roots_sharing_one_record(tmp_path)
    walked: list[Path] = []
    real_walk = JobAppsLane._records_under

    def spy(self, root):
        walked.append(root)
        return real_walk(self, root)

    monkeypatch.setattr(JobAppsLane, "_records_under", spy)

    result = _collect_two(discovery, promoted, tmp_path)

    assert walked == [discovery, promoted]
    assert sorted(posting.title for posting in _postings(result)) == [
        "Discovery Role", "Queue Role", "Shared Role",
    ]
    assert result.tally.counts["not_attemptable"] == 1
    assert result.tally.counts["body_inline"] == 3


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


def test_a_record_at_an_unsupported_schema_version_is_skipped_and_counted(tmp_path):
    """`_read_record` rejects this folder, and a silent drop is indistinguishable from a record
    the lane never saw -- so it must land in the tally, exactly like the lane's other drops
    (`collect`'s own `not_attemptable` comment states the rule this pins)."""
    root = tmp_path / "queue"
    _write(root, "Greenhouse", "ok")
    _write(root, "Greenhouse", "future", schema_version=99, posting_id="pst_future")
    result = _collect(root, tmp_path)
    assert len(_postings(result)) == 1
    assert result.tally.counts["not_attemptable"] == 1


@pytest.mark.parametrize("missing", ["company", "title", "direct_url"])
def test_a_record_missing_a_required_canonical_field_is_skipped_and_counted(tmp_path, missing):
    root = tmp_path / "queue"
    _write(root, "Greenhouse", "ok")
    folder = _write(root, "Greenhouse", "bad", posting_id="pst_bad")
    payload = json.loads((folder / "discovery_record.json").read_text())
    payload["canonical"][missing] = ""
    (folder / "discovery_record.json").write_text(json.dumps(payload), encoding="utf-8")
    result = _collect(root, tmp_path)
    assert len(_postings(result)) == 1
    assert result.tally.counts["not_attemptable"] == 1


def test_an_unreadable_record_file_is_skipped_and_counted(tmp_path):
    """Not just a bad field -- invalid JSON on disk, the other way `_read_record` returns None."""
    root = tmp_path / "queue"
    _write(root, "Greenhouse", "ok")
    folder = root / "Greenhouse" / "corrupt"
    folder.mkdir(parents=True)
    (folder / "discovery_record.json").write_text("{not json", encoding="utf-8")
    result = _collect(root, tmp_path)
    assert len(_postings(result)) == 1
    assert result.tally.counts["not_attemptable"] == 1


def test_a_dangling_record_symlink_is_skipped_and_counted(tmp_path):
    """T168's follow-up (checkpointed in the ticket): a candidate folder can hold a
    `discovery_record.json` that is a SYMLINK to nothing. `Path.is_file()` stats through a
    symlink and reads False for a dangling one, so before this fix the folder never became a
    candidate at all -- not `not_attemptable`, not anything, just absent from every tally,
    which is the exact silent drop T168 closed for every other rejection cause."""
    root = tmp_path / "queue"
    _write(root, "Greenhouse", "ok")
    folder = root / "Greenhouse" / "dangling"
    folder.mkdir(parents=True)
    (folder / "discovery_record.json").symlink_to(folder / "nonexistent_target.json")
    result = _collect(root, tmp_path)
    assert len(_postings(result)) == 1
    assert result.tally.counts["not_attemptable"] == 1


def test_a_dangling_link_beside_an_incomplete_record_is_counted_once_of_its_own(tmp_path):
    """T218: one good record, one incomplete record (T168's shape: a required `canonical` field
    blank) and one `discovery_record.json` linking to nothing. Each rejection is its own count in
    `not_attemptable` -- the closed tally's member for "seen, never attempted", which both
    rejections are -- so the two sum to exactly two: the link is neither a candidate that became
    a posting, nor a crash, nor silence."""
    root = tmp_path / "queue"
    _write(root, "Greenhouse", "ok", title="Good Role")
    incomplete = _write(root, "Greenhouse", "incomplete", posting_id="pst_incomplete")
    payload = json.loads((incomplete / "discovery_record.json").read_text())
    payload["canonical"]["title"] = ""
    (incomplete / "discovery_record.json").write_text(json.dumps(payload), encoding="utf-8")
    dangling = root / "Greenhouse" / "dangling"
    dangling.mkdir()
    (dangling / "discovery_record.json").symlink_to(tmp_path / "gone" / "discovery_record.json")

    result = _collect(root, tmp_path)

    assert [posting.title for posting in _postings(result)] == ["Good Role"]
    assert result.tally.counts["not_attemptable"] == 2
    assert result.tally.attempted == 3


def test_a_record_symlink_to_an_existing_record_is_read_as_that_record(tmp_path):
    """Control: a link that resolves is an ordinary record, not a rejection. Linking is a normal
    shape for a refreshed tree, so admitting links as candidates must not start counting the
    live ones as unreadable."""
    root = tmp_path / "queue"
    target = _write(tmp_path / "elsewhere", "Greenhouse", "real", title="Linked Role")
    folder = root / "Greenhouse" / "linked"
    folder.mkdir(parents=True)
    (folder / "discovery_record.json").symlink_to(target / "discovery_record.json")
    (folder / "job_description.txt").write_text(f"{_HEADER}{_MARKER}\n\n{_BODY}", encoding="utf-8")

    result = _collect(root, tmp_path)

    assert [posting.title for posting in _postings(result)] == ["Linked Role"]
    assert result.tally.counts["not_attemptable"] == 0
    assert result.tally.counts["body_inline"] == 1


def test_a_dangling_posting_folder_link_is_counted_as_one_unread_record(tmp_path):
    """T238: a posting FOLDER that is a link to nothing fails `is_dir()`, so it fell out of the
    group listing before it became a candidate -- not counted anywhere. One folder is one
    record, seen in the listing and never read, so it is `not_attemptable` like T218's dangling
    record link, and it stays a record in `attempted`."""
    root = tmp_path / "queue"
    _write(root, "Greenhouse", "ok", title="Good Role")
    (root / "Greenhouse" / "dangling").symlink_to(
        tmp_path / "gone" / "dangling", target_is_directory=True
    )

    result = _collect(root, tmp_path)

    assert [posting.title for posting in _postings(result)] == ["Good Role"]
    assert result.tally.counts["not_attemptable"] == 1
    assert result.tally.counts["dangling_group_link"] == 0
    assert result.tally.attempted == 2


def test_a_posting_folder_link_that_resolves_is_read_as_that_record(tmp_path):
    """Control: a folder link whose target exists is an ordinary record, not a rejection."""
    root = tmp_path / "queue"
    target = _write(tmp_path / "elsewhere", "Greenhouse", "real", title="Linked Role")
    (root / "Greenhouse").mkdir(parents=True)
    (root / "Greenhouse" / "linked").symlink_to(target, target_is_directory=True)

    result = _collect(root, tmp_path)

    assert [posting.title for posting in _postings(result)] == ["Linked Role"]
    assert result.tally.counts["not_attemptable"] == 0
    assert result.tally.attempted == 1


def test_a_tree_where_every_candidate_fails_to_parse_still_raises_and_counts_nothing(tmp_path):
    """The control the ticket asks for: mixing two different `_read_record` rejection causes in
    one tree, with NO parseable record anywhere, must still raise `JobAppsSourceError` with its
    existing message -- not quietly count the candidates and return a clean, misleadingly benign
    zero."""
    root = tmp_path / "queue"
    _write(root, "Greenhouse", "a", schema_version=99, posting_id="pst_a")
    folder = _write(root, "Greenhouse", "b", posting_id="pst_b")
    payload = json.loads((folder / "discovery_record.json").read_text())
    payload["canonical"]["company"] = ""
    (folder / "discovery_record.json").write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(JobAppsSourceError, match="record format has probably moved"):
        _collect(root, tmp_path)


def test_a_tree_of_only_valid_records_reports_the_same_counts_as_before(tmp_path):
    """Control: nothing rejected, so the tally must show exactly what it showed before this
    change -- no phantom `not_attemptable` entries from a tree with nothing wrong in it."""
    root = tmp_path / "queue"
    _write(root, "Greenhouse", "a")
    _write(root, "Ashby", "b", direct_url="https://jobs.ashbyhq.com/openai", posting_id="pst_b")
    result = _collect(root, tmp_path)
    assert len(_postings(result)) == 2
    assert result.tally.counts["not_attemptable"] == 0
    assert result.tally.attempted == 2


def _staging_with_one_dangling_group_link(tmp_path: Path) -> Path:
    """A staging root shaped like the owner's: GROUP directories linked in, not record files.

    One group link that resolves (two records behind it), one whose target is gone -- the
    refresher's link-refresh race -- and one plain group directory with one record. Distinct
    posting URLs, so no record dedups against another and every readable one becomes a posting.
    """
    queue = tmp_path / "APPLY_QUEUE"
    _write(
        queue, "Greenhouse", "linked-a", title="Linked A", posting_id="pst_linked_a",
        direct_url="https://job-boards.greenhouse.io/gitlab/jobs/1111111111",
    )
    _write(
        queue, "Greenhouse", "linked-b", title="Linked B", posting_id="pst_linked_b",
        direct_url="https://job-boards.greenhouse.io/gitlab/jobs/2222222222",
    )
    staging = tmp_path / "jobapps-staging"
    staging.mkdir()
    (staging / "Greenhouse").symlink_to(queue / "Greenhouse", target_is_directory=True)
    (staging / "Ashby").symlink_to(queue / "Ashby", target_is_directory=True)  # never created
    _write(
        staging, "Lever", "plain", title="Plain Role", posting_id="pst_plain",
        direct_url="https://job-boards.greenhouse.io/gitlab/jobs/3333333333",
    )
    return staging


def test_a_dangling_group_link_is_counted_per_group_and_the_rest_of_the_tree_is_read(tmp_path):
    """T220: the owner's refresher links GROUP directories into the staging root. A group link
    whose target is gone used to fail `is_dir()` and drop out of the listing with its whole
    group -- not counted, not raised. It is counted once, per GROUP, in its own tally member:
    the records behind it are unknowable, so it is NOT folded into `not_attemptable`, which
    counts records the lane saw and rejected. The resolving and plain groups read as before."""
    staging = _staging_with_one_dangling_group_link(tmp_path)

    result = _collect(staging, tmp_path)

    assert sorted(posting.title for posting in _postings(result)) == [
        "Linked A", "Linked B", "Plain Role",
    ]
    assert result.tally.counts["dangling_group_link"] == 1
    assert result.tally.counts["not_attemptable"] == 0
    assert result.tally.counts["body_inline"] == 3
    # A record count: the three records, not the broken group beside them.
    assert result.tally.attempted == 3


def test_a_dangling_skip_folder_link_loses_nothing_and_is_not_counted(tmp_path):
    """`_applied` and `_skipped` are never read, so a broken link at either name hides no record
    the lane would have ingested; counting it would report a loss that did not happen."""
    root = tmp_path / "queue"
    _write(root, "Greenhouse", "a")
    (root / "_applied").symlink_to(tmp_path / "gone" / "_applied", target_is_directory=True)
    result = _collect(root, tmp_path)
    assert len(_postings(result)) == 1
    assert result.tally.counts["dangling_group_link"] == 0


def test_a_tree_of_only_dangling_group_links_still_raises_as_no_group_folder(tmp_path):
    """Control, green by design: with EVERY group link dangling there is no group folder to
    read at all, which is the structural break this lane raises for -- the count must not turn
    it into a quiet zero."""
    staging = tmp_path / "jobapps-staging"
    staging.mkdir()
    (staging / "Greenhouse").symlink_to(tmp_path / "gone" / "Greenhouse", target_is_directory=True)
    (staging / "Ashby").symlink_to(tmp_path / "gone" / "Ashby", target_is_directory=True)
    with pytest.raises(JobAppsSourceError, match="no group folder anywhere"):
        _collect(staging, tmp_path)


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


def test_a_tier_one_record_declares_every_field_secondhand(tmp_path):
    """D-500: a tier-1 hit lands on the BOARD's own `(company_id, provider_posting_id)`.

    `scan/apply.py`'s D25 rule refreshes every provider-sourced column on any positive
    observation regardless of `content_hash`, so without a declaration this lane's rendering
    replaces the employer's on the row every rule quotes. Measured on the live store before this
    landed: 612 `revised` versions written by this lane onto board postings, ALL of them tier 1,
    and the board's very next reading reverted 87 of 436 (20.0%) by more than half the body.

    `"liveness"` is declared IN ADDITION, and on every tier (see the tiers-2-and-3 test below):
    it is not a column family, it is the statement that this observation is a directory read
    rather than a fetch. Tier 1 is the tier where the two meet — the board scan owns the columns
    AND is the only thing that can see whether the posting is still served.

    The expected set is spelled out as a LITERAL rather than compared against
    `CONVERGED_SECONDHAND`, which is derived from `SecondhandColumnField` and would agree with
    itself however either one changes. A new declarable field reddens this test on purpose.
    """
    root = tmp_path / "queue"
    _write(root, "Greenhouse", "a")
    (posting,) = _postings(_collect(root, tmp_path))
    assert posting.secondhand == frozenset(
        {
            "title", "url", "locations", "remote_policy", "department",
            "posted_at", "updated_at", "body_text", "salary", "raw_json", "liveness",
        }
    )


@pytest.mark.parametrize(
    "direct_url,posting_id",
    [
        ("https://jobs.ashbyhq.com/openai", "pst_x"),          # tier 2: board, no posting ref
        ("https://lifeattiktok.com/search/123", "pst_y"),      # tier 3: the lane namespace
    ],
)
def test_a_record_filed_under_its_own_key_declares_only_liveness(
    tmp_path, direct_url, posting_id
):
    """Tiers 2 and 3, and the reason the declaration rides on the IDENTITY rather than the lane.

    Neither tier converges onto a board's posting key -- both file under job-apps' own `pst_`
    reference -- so this lane is the ONLY observer those rows will ever have. Declaring a COLUMN
    there would freeze whatever landed first and never refresh it, which is the failure mode
    `SecondhandField`'s reason 1 rejects a per-lane precedence rule for.

    `"liveness"` is the one member that does NOT vary by tier, because it is not a claim about
    fidelity: this lane reads a static local directory and re-lists every record in it on every
    run, whatever identity the record resolved to. A tier-3 row can still close through the
    death probe (D-325), and letting a file read clear its strikes disarms that.
    """
    root = tmp_path / "queue"
    _write(root, "Other", "a", direct_url=direct_url, posting_id=posting_id)
    (posting,) = _postings(_collect(root, tmp_path))
    assert posting.secondhand == frozenset({"liveness"})


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

# The most common escaped form on this lane. It was SILENT even unescaped when D-443 shipped --
# no arm allowed four modifiers between `of` and `experience` -- and D-447 widened
# `scoped_years_minimum`'s arbitrary-word run to {0,3} on a measured span read, closing it.
# Kept rather than deleted: this assertion is what made the residual VISIBLE, and it now pins
# the JOIN of the two changes. Neither alone reads this bar -- the widening never sees it while
# the escape hides it, and the unescape cannot parse it while the window is {0,2}.
_WAS_UNCOVERED_UNTIL_D445 = "3+ years of non-internship professional software development experience"


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
    assert years(_WAS_UNCOVERED_UNTIL_D445), (
        "D-447 widened the scoped run to {0,3}, so this lane's single most common bar is now "
        "read -- if this is empty the window regressed and D-443's unescape stops paying here"
    )
    assert years(r"3\+ years of non\-internship professional software development experience") == [], (
        "and it is still invisible while ESCAPED, which is the join the two changes make"
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

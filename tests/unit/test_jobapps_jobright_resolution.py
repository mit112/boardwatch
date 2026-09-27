"""A jobright record filed under the employer posting job-apps' resolver found (`employer_posting`).

The folder shapes are the resolver's own (`autoapply/jobright_resolver.py resolve-date --apply`):
it rewrites `1_apply.webloc` from a plist template without XML-escaping the URL, and writes the
jobright URL it replaced, tracking parameters and all, to `jobright_source.url`.
"""

from __future__ import annotations

import json
from collections.abc import Collection, Mapping
from pathlib import Path

import pytest

from boardwatch.core.models import CONVERGED_SECONDHAND
from boardwatch.core.politeness import Fetcher
from boardwatch.core.settings import Settings
from boardwatch.lanes.base import LaneResult
from boardwatch.lanes.jobapps import JobAppsLane

JOBRIGHT_ID = "6a95ed6fcabc9f6703e1b085"
JOBRIGHT_URL = f"https://jobright.ai/jobs/info/{JOBRIGHT_ID}"
WORKDAY_URL = (
    "https://cboe.wd1.myworkdayjobs.com/External_Career_CBOE/job/Chicago-IL/"
    "Software-Engineer_R-12345?source=jobright&utm_medium=x"
)
WORKDAY = ("workday", "cboe.wd1.myworkdayjobs.com/cboe/External_Career_CBOE", "R-12345")
_RULE = "=" * 80
_WEBLOC = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
    '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
    '<plist version="1.0">\n<dict>\n\t<key>URL</key>\n\t<string>{url}</string>\n</dict>\n</plist>\n'
)


def _record(
    root: Path,
    *,
    webloc: str | None = WORKDAY_URL,
    source: str | None = f"{JOBRIGHT_URL}?utm_campaign=Software%20Engineering&utm_source=1103",
    acquisition: str = "jobright",
) -> None:
    folder = root / "Jobright" / "Cboe_Software_Engineer"
    folder.mkdir(parents=True)
    (folder / "discovery_record.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "posting_id": "pst_cboe",
                "primary_acquisition": acquisition,
                "cohort_date": "2026-09-27",
                "canonical": {
                    "company": "CBRE",
                    "title": "Software Engineer",
                    "direct_url": JOBRIGHT_URL,
                    "location": "Chicago, IL",
                },
            }
        ),
        encoding="utf-8",
    )
    (folder / "job_description.txt").write_text(
        f"Company: CBRE\nFit: 70/100\n\n{_RULE}\nJOB DESCRIPTION\n{_RULE}\n\n"
        "Build trading systems in Python and Java. New grads welcome.\n",
        encoding="utf-8",
    )
    if webloc is not None:
        (folder / "1_apply.webloc").write_text(_WEBLOC.format(url=webloc), encoding="utf-8")
    if source is not None:
        (folder / "jobright_source.url").write_text(source + "\n", encoding="utf-8")


def _collect(
    root: Path, tmp_path: Path, stored_own: Collection[str] = ()
) -> tuple[LaneResult, list[tuple[str, str, bool]]]:
    """The lane's result and every admission it asked for, as `(provider, slug, tier1)`.
    `stored_own` are the job-apps posting ids the store already holds under job-apps' own key."""
    asked: list[tuple[str, str, bool]] = []

    def admits(provider: str, slug: str, *, tier1: bool = False) -> bool:
        asked.append((provider, slug, tier1))
        return True

    def reader(provider: str, posting_ids: Collection[str]) -> Mapping[str, str]:
        if provider != "jobapps":
            return {}
        return {posting_id: "cbre" for posting_id in posting_ids if posting_id in stored_own}

    fetcher = Fetcher(Settings(data_dir=tmp_path, config_dir=tmp_path, retry_attempts=1))
    lane = JobAppsLane(source_dir=root, stored_posting_slugs=reader)
    return lane.collect(fetcher, admits), asked


def _filed(result: LaneResult) -> list[tuple[str, str, str, bool]]:
    """`(provider, slug, posting ref, watched)` of every posting the lane emitted."""
    return [
        (company.provider, company.slug, posting.provider_posting_id, company.watch)
        for company in result.snapshots
        for posting in company.snapshot.postings
    ]


def test_a_resolved_record_is_filed_under_the_employers_posting_and_its_board_watched(
    tmp_path: Path,
) -> None:
    """The resolver's webloc (an unescaped `&` in it, as its template writes) and a sidecar naming
    this record's jobright id: the record converges on the board's own key, declares every column
    secondhand, is admitted as tier 1 and turns the board's scan on -- the scan is its drain.
    Catches the webloc read as XML (it is not valid XML), the guard's id comparison inverted, and
    tier 1 or watching left off."""
    root = tmp_path / "queue"
    _record(root)
    result, asked = _collect(root, tmp_path)

    assert _filed(result) == [(*WORKDAY, True)]
    assert asked == [(WORKDAY[0], WORKDAY[1], True)]
    (posting,) = result.snapshots[0].snapshot.postings
    assert posting.url == WORKDAY_URL
    assert CONVERGED_SECONDHAND <= posting.secondhand
    # Provenance keeps job-apps' own URL.
    assert posting.raw_json["jobapps"]["canonical"]["direct_url"] == JOBRIGHT_URL


@pytest.mark.parametrize(
    "written",
    [
        pytest.param(WORKDAY_URL + "&copy=1", id="resolver-template-raw"),
        pytest.param((WORKDAY_URL + "&copy=1").replace("&", "&amp;"), id="valid-plist-escaped"),
    ],
)
def test_the_employer_url_is_stored_as_the_webloc_means_it(tmp_path: Path, written: str) -> None:
    """The resolver's own webloc holds the URL raw (not valid XML), a valid plist holds it escaped;
    both mean the same URL. Catches unescaping the raw form (`&copy=1` read as an entity) and
    reading the escaped form by pattern without unescaping it."""
    root = tmp_path / "queue"
    _record(root, webloc=written)
    result, _ = _collect(root, tmp_path)
    (posting,) = result.snapshots[0].snapshot.postings
    assert posting.url == WORKDAY_URL + "&copy=1"


def test_a_record_boardwatch_already_holds_under_job_apps_key_keeps_it(tmp_path: Path) -> None:
    """Resolved AFTER boardwatch stored it: re-filing would open a second posting and leave the
    first open forever, so the record keeps the key the store holds. Catches the guard missing."""
    root = tmp_path / "queue"
    _record(root)
    result, asked = _collect(root, tmp_path, stored_own={"pst_cboe"})

    assert _filed(result) == [("jobapps", "cbre", "pst_cboe", False)]
    assert asked == [("jobapps", "cbre", False)]


def _unresolved(root: Path, tmp_path: Path) -> list[tuple[str, str, str, bool]]:
    result, _ = _collect(root, tmp_path)
    return _filed(result)


def test_a_sidecar_naming_another_jobright_job_is_not_a_resolution(tmp_path: Path) -> None:
    """A webloc copied from another folder carries that folder's sidecar. Catches the sidecar's
    id not being compared with the record's own."""
    root = tmp_path / "queue"
    _record(root, source="https://jobright.ai/jobs/info/6a0000000000000000000000")
    assert _unresolved(root, tmp_path) == [("jobapps", "cbre", "pst_cboe", False)]


def test_a_webloc_with_no_sidecar_is_not_a_resolution(tmp_path: Path) -> None:
    """Without the resolver's sidecar the URL's origin is unknown. Catches the sidecar made
    optional."""
    root = tmp_path / "queue"
    _record(root, source=None)
    assert _unresolved(root, tmp_path) == [("jobapps", "cbre", "pst_cboe", False)]


def test_a_webloc_still_on_jobright_is_not_a_resolution(tmp_path: Path) -> None:
    """The resolver writes the sidecar even when it leaves the jobright URL in place (login
    lapsed, no apply button). Catches a jobright URL taken for an employer's."""
    root = tmp_path / "queue"
    _record(root, webloc=f"{JOBRIGHT_URL}?utm_source=1103")
    assert _unresolved(root, tmp_path) == [("jobapps", "cbre", "pst_cboe", False)]


def test_a_board_level_url_is_not_a_resolution(tmp_path: Path) -> None:
    """Greenhouse's embedded application form names the board, not a posting this repo can key.
    Filing under the board would sit a job-apps key beside the scan's own row for the job.
    Catches `parse_board_target` accepted in place of `parse_posting_target`."""
    root = tmp_path / "queue"
    _record(root, webloc="https://boards.greenhouse.io/embed/job_app?for=acme&amp;token=4012345")
    assert _unresolved(root, tmp_path) == [("jobapps", "cbre", "pst_cboe", False)]


def test_only_a_jobright_record_is_read_for_a_resolution(tmp_path: Path) -> None:
    """The resolver works on jobright records alone. Catches the acquisition guard dropped."""
    root = tmp_path / "queue"
    _record(root, acquisition="simplify")
    assert _unresolved(root, tmp_path) == [("jobapps", "cbre", "pst_cboe", False)]

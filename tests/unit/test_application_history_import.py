"""`track import`: filling `applications` from a history kept in some other tool.

What is asserted here is the contract the CLI depends on, not implementation detail:

* **the five buckets partition the input** — every row lands in exactly one, so an unmatched,
  malformed or ambiguous row is counted rather than dropped;
* **a weak-key match that fans out writes nothing** — one (company, title) covering several
  requisitions is refused and reported, because a wrongly-applied job is hidden for good;
* **the two keys are not equally trusted** — `company_title` matches nothing unless the caller
  opts in, and the key that matched is recorded per row;
* **importing twice writes nothing the second time** — no duplicate application, no bumped
  `attempt_no`, and no `application_events` row, counted before and after;
* **a written row enters `applied_job_ids`**, which is the set `top` suppresses on. Without
  that link the import is decorative.
"""

from pathlib import Path

import pytest
from sqlalchemy import Connection, Engine, func, insert, select

from boardwatch.core.clock import utcnow
from boardwatch.store.application_history import (
    HistoryFormatError,
    ImportBucket,
    MalformedReason,
    MatchKey,
    import_history,
    parse_history,
)
from boardwatch.store.applications import (
    applied_job_ids,
    create_application,
    get_applications,
    set_application_status,
)
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.tables import application_events, applications, companies, jobs, postings

NOW = utcnow()


@pytest.fixture()
def engine(tmp_path: Path) -> Engine:
    eng = get_engine(tmp_path)
    ensure_schema(eng)
    return eng


def _posting(
    conn: Connection,
    *,
    company: str = "Acme Inc",
    title: str = "Software Engineer",
    url: str | None = "https://boards.example.test/acme/1",
    key: str = "alpha",
    status: str = "open",
) -> int:
    """A company, a job and a posting on it. Returns the job id."""
    company_id = int(
        conn.execute(
            insert(companies).values(
                name=company, provider="greenhouse", slug=f"slug-{key}",
                source="user", watched=True,
            )
        ).inserted_primary_key[0]
    )
    job_id = int(conn.execute(insert(jobs).values(created_at=NOW)).inserted_primary_key[0])
    conn.execute(
        insert(postings).values(
            company_id=company_id, job_id=job_id, provider_posting_id=key, title=title,
            normalized_title=title.lower(), url=url, locations_json=["Remote"],
            remote_policy="remote", first_seen_at=NOW, last_seen_at=NOW, status=status,
            consecutive_missing=0, content_hash=key, body_text=f"body {key}",
        )
    )
    return job_id


def _count(conn: Connection, table: object) -> int:
    return int(conn.execute(select(func.count()).select_from(table)).scalar_one())  # type: ignore[arg-type]


def _write(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


# --- parsing -----------------------------------------------------------------------------


def test_csv_and_jsonl_read_the_same_row(tmp_path: Path) -> None:
    csv_rows, _ = parse_history(
        _write(
            tmp_path, "h.csv",
            "company,title,url,applied_at,status\n"
            "Acme,Software Engineer,https://x.test/1,2026-03-09,applied\n",
        )
    )
    json_rows, _ = parse_history(
        _write(
            tmp_path, "h.jsonl",
            '{"company":"Acme","title":"Software Engineer","url":"https://x.test/1",'
            '"applied_at":"2026-03-09","status":"applied"}\n',
        )
    )
    assert [
        (row.company, row.title, row.url, row.applied_at, row.status) for row in csv_rows
    ] == [(row.company, row.title, row.url, row.applied_at, row.status) for row in json_rows]


def test_an_unreadable_suffix_is_refused(tmp_path: Path) -> None:
    with pytest.raises(HistoryFormatError):
        parse_history(_write(tmp_path, "history.txt", "Acme,SWE\n"))


def test_a_header_with_no_key_column_is_refused_whole(tmp_path: Path) -> None:
    """A misspelled header must fail loudly, not present as "every row unmatched"."""
    with pytest.raises(HistoryFormatError):
        parse_history(_write(tmp_path, "h.csv", "companyy,titel,link\nAcme,SWE,x\n"))


def test_extra_columns_are_ignored(tmp_path: Path) -> None:
    rows, malformed = parse_history(
        _write(tmp_path, "h.csv", "company,title,notes\nAcme,SWE,referred by Dana\n")
    )
    assert malformed == []
    assert (rows[0].company, rows[0].title) == ("Acme", "SWE")


@pytest.mark.parametrize(
    ("body", "reason"),
    [
        ("company,title,url\nAcme,,\n", MalformedReason.NO_KEY),
        ("company,title,url,status\nAcme,SWE,,ghosted\n", MalformedReason.UNKNOWN_STATUS),
        ("company,title,url,applied_at\nAcme,SWE,,last March\n", MalformedReason.BAD_APPLIED_AT),
    ],
)
def test_a_row_that_cannot_be_read_is_reported_not_dropped(
    tmp_path: Path, body: str, reason: MalformedReason
) -> None:
    rows, malformed = parse_history(_write(tmp_path, "h.csv", body))
    assert rows == []
    assert [bad.reason for bad in malformed] == [reason]


def test_a_missing_status_means_applied(tmp_path: Path) -> None:
    """An *application* history row with no status still records that a submission happened."""
    rows, _ = parse_history(_write(tmp_path, "h.csv", "company,title,url\nAcme,SWE,https://x/1\n"))
    assert rows[0].status == "applied"


def test_a_bad_json_line_is_a_malformed_row_not_a_crash(tmp_path: Path) -> None:
    rows, malformed = parse_history(
        _write(tmp_path, "h.jsonl", '{"url":"https://x.test/1"}\nnot json\n[1,2]\n')
    )
    assert len(rows) == 1
    assert [bad.reason for bad in malformed] == [
        MalformedReason.BAD_JSON,
        MalformedReason.NOT_AN_OBJECT,
    ]


# --- matching and writing ----------------------------------------------------------------


def test_a_url_match_writes_an_application_the_ranker_then_suppresses(
    engine: Engine, tmp_path: Path
) -> None:
    """Case, `www.`, a tracking param and a trailing slash are all noise on the same URL."""
    with engine.begin() as conn:
        job_id = _posting(conn, url="https://boards.example.test/acme/1")
    rows, malformed = parse_history(
        _write(
            tmp_path, "h.jsonl",
            '{"url": "https://www.Boards.Example.test/acme/1/?utm_source=x"}\n',
        )
    )
    with engine.begin() as conn:
        report = import_history(conn, rows, malformed, allow_title_match=False)
    assert [result.bucket for result in report.results] == [ImportBucket.MATCHED]
    assert report.results[0].match_key is MatchKey.URL
    assert report.results[0].job_ids == (job_id,)
    with engine.connect() as conn:
        assert applied_job_ids(conn) == {job_id: "applied"}


def test_company_title_matches_only_when_the_caller_opts_in(tmp_path: Path, engine: Engine) -> None:
    """The weaker key is off by default. This is the whole reason the flag exists."""
    with engine.begin() as conn:
        job_id = _posting(conn, company="Acme Inc", title="Software Engineer", url=None)
    path = _write(tmp_path, "h.csv", "company,title\nACME,software  engineer\n")
    rows, malformed = parse_history(path)

    with engine.begin() as conn:
        closed = import_history(conn, rows, malformed, allow_title_match=False)
    assert [result.bucket for result in closed.results] == [ImportBucket.UNMATCHED]
    with engine.connect() as conn:
        assert _count(conn, applications) == 0

    with engine.begin() as conn:
        opened = import_history(conn, rows, malformed, allow_title_match=True)
    assert opened.results[0].bucket is ImportBucket.MATCHED
    assert opened.results[0].match_key is MatchKey.COMPANY_TITLE
    assert opened.results[0].job_ids == (job_id,)


def test_the_url_key_wins_when_both_could_match(engine: Engine, tmp_path: Path) -> None:
    """The reported key must be the one actually used, or the audit lies."""
    with engine.begin() as conn:
        url_job = _posting(conn, company="Acme Inc", title="Data Engineer", key="a",
                           url="https://boards.example.test/acme/1")
        _posting(conn, company="Acme Inc", title="Software Engineer", key="b", url=None)
    path = _write(
        tmp_path, "h.csv",
        "company,title,url\nAcme Inc,Software Engineer,https://boards.example.test/acme/1\n",
    )
    rows, malformed = parse_history(path)
    with engine.begin() as conn:
        report = import_history(conn, rows, malformed, allow_title_match=True)
    assert report.results[0].match_key is MatchKey.URL
    assert report.results[0].job_ids == (url_job,)


def test_the_buckets_partition_every_input_row(engine: Engine, tmp_path: Path) -> None:
    """All five buckets, each populated, summing to the input. Literal counts, not a derived set.

    The fifth (`ambiguous`) is what makes this more than a rename: a bucket that is never
    exercised cannot show that a refusal is still counted rather than dropped.
    """
    with engine.begin() as conn:
        _posting(conn, url="https://boards.example.test/acme/1", key="a")
        tracked = _posting(conn, url="https://boards.example.test/acme/2", key="b")
        create_application(conn, job_id=tracked, status="applied", source="user")
        # Two distinct requisitions sharing one normalised (company, title) and no URL.
        _posting(conn, company="Duplo Corp", title="Platform Engineer", key="c", url=None)
        _posting(conn, company="Duplo Corp", title="Platform Engineer", key="d", url=None)
    path = _write(
        tmp_path, "h.csv",
        "company,title,url,status\n"
        "Acme,SWE,https://boards.example.test/acme/1,applied\n"    # matched
        "Acme,SWE,https://boards.example.test/acme/2,applied\n"    # already present
        "Acme,SWE,https://boards.example.test/nowhere,applied\n"   # unmatched
        "Acme,SWE,https://boards.example.test/acme/1,ghosted\n"    # malformed
        "Duplo Corp,Platform Engineer,,applied\n",                 # ambiguous
    )
    rows, malformed = parse_history(path)
    with engine.begin() as conn:
        report = import_history(conn, rows, malformed, allow_title_match=True)
    counts = report.counts()
    assert counts == {
        ImportBucket.MATCHED: 1,
        ImportBucket.ALREADY_PRESENT: 1,
        ImportBucket.UNMATCHED: 1,
        ImportBucket.MALFORMED: 1,
        ImportBucket.AMBIGUOUS: 1,
    }
    assert sum(counts.values()) == len(rows) + len(malformed) == 5
    assert [result.line_no for result in report.results] == [2, 3, 4, 5, 6]


def test_applied_at_moves_submitted_at_but_not_created_at(engine: Engine, tmp_path: Path) -> None:
    """A March application must not be stamped as submitted today."""
    with engine.begin() as conn:
        _posting(conn, url="https://boards.example.test/acme/1")
    rows, malformed = parse_history(
        _write(
            tmp_path, "h.csv",
            "company,title,url,applied_at\nAcme,SWE,https://boards.example.test/acme/1,"
            "2026-03-09T14:30:00+00:00\n",
        )
    )
    with engine.begin() as conn:
        import_history(conn, rows, malformed, allow_title_match=False)
    with engine.connect() as conn:
        row = conn.execute(
            select(applications.c.submitted_at, applications.c.created_at)
        ).one()
        event = conn.execute(select(application_events.c.occurred_at)).scalar_one()
    assert row.submitted_at.isoformat() == "2026-03-09T14:30:00"
    assert event.isoformat() == "2026-03-09T14:30:00"
    assert row.created_at >= NOW


def test_importing_the_same_file_twice_writes_nothing_the_second_time(
    engine: Engine, tmp_path: Path
) -> None:
    with engine.begin() as conn:
        _posting(conn, url="https://boards.example.test/acme/1")
    rows, malformed = parse_history(
        _write(tmp_path, "h.csv", "company,title,url\nAcme,SWE,https://boards.example.test/acme/1\n")
    )
    with engine.begin() as conn:
        first = import_history(conn, rows, malformed, allow_title_match=False)
    with engine.connect() as conn:
        before = (_count(conn, applications), _count(conn, application_events))
    with engine.begin() as conn:
        second = import_history(conn, rows, malformed, allow_title_match=False)
    with engine.connect() as conn:
        after = (_count(conn, applications), _count(conn, application_events))
        attempts = conn.execute(select(applications.c.attempt_no)).scalars().all()
    assert first.results[0].bucket is ImportBucket.MATCHED
    assert second.results[0].bucket is ImportBucket.ALREADY_PRESENT
    assert second.results[0].application_ids == ()
    assert before == after == (1, 1)
    assert list(attempts) == [1]


def test_a_withdrawn_job_is_not_re_applied_by_a_later_import(
    engine: Engine, tmp_path: Path
) -> None:
    """`withdrawn` is the documented drain out of the applied set; an import must not undo it."""
    with engine.begin() as conn:
        job_id = _posting(conn, url="https://boards.example.test/acme/1")
        app_id = create_application(conn, job_id=job_id, status="applied", source="user")
        set_application_status(
            conn, application_id=app_id, to_status="withdrawn", source="user"
        )
    rows, malformed = parse_history(
        _write(tmp_path, "h.csv", "company,title,url\nAcme,SWE,https://boards.example.test/acme/1\n")
    )
    with engine.begin() as conn:
        report = import_history(conn, rows, malformed, allow_title_match=False)
    assert report.results[0].bucket is ImportBucket.ALREADY_PRESENT
    with engine.connect() as conn:
        assert applied_job_ids(conn) == {}
        assert [row.status for row in get_applications(conn, job_id)] == ["withdrawn"]


def test_a_closed_posting_still_matches(engine: Engine, tmp_path: Path) -> None:
    """The index is the whole store, so the same file imports the same way on any day."""
    with engine.begin() as conn:
        job_id = _posting(conn, url="https://boards.example.test/acme/1", status="closed")
    rows, malformed = parse_history(
        _write(tmp_path, "h.csv", "company,title,url\nAcme,SWE,https://boards.example.test/acme/1\n")
    )
    with engine.begin() as conn:
        report = import_history(conn, rows, malformed, allow_title_match=False)
    assert report.results[0].job_ids == (job_id,)


def test_an_ambiguous_company_title_row_writes_nothing_at_all(
    engine: Engine, tmp_path: Path
) -> None:
    """The weak key fanning out is a REFUSAL, not a licence to mark every candidate applied.

    Two distinct requisitions at one employer share a normalised title. Writing an application
    for both hides a job the owner never applied to, permanently and silently — the queue never
    shows it again and nothing reports that it was suppressed. Showing a duplicate is recoverable;
    this is not. So the row writes nothing and is reported `ambiguous`, carrying both job ids so
    the audit says exactly which requisitions it refused to choose between.
    """
    with engine.begin() as conn:
        first = _posting(conn, company="Acme Inc", title="Software Engineer", key="a", url=None)
        second = _posting(conn, company="Acme, Inc.", title="Software Engineer", key="b", url=None)
    rows, malformed = parse_history(
        _write(tmp_path, "h.csv", "company,title\nAcme Inc,Software Engineer\n")
    )
    with engine.begin() as conn:
        report = import_history(conn, rows, malformed, allow_title_match=True)
    result = report.results[0]
    assert result.bucket is ImportBucket.AMBIGUOUS
    assert result.match_key is MatchKey.COMPANY_TITLE
    assert result.job_ids == tuple(sorted((first, second)))
    assert result.application_ids == ()
    with engine.connect() as conn:
        assert _count(conn, applications) == 0
        assert _count(conn, application_events) == 0
        assert applied_job_ids(conn) == {}


def test_an_ambiguous_row_stays_ambiguous_on_re_import(engine: Engine, tmp_path: Path) -> None:
    """Refusing is stable: the second run neither writes nor reclassifies the row."""
    with engine.begin() as conn:
        _posting(conn, company="Acme Inc", title="Software Engineer", key="a", url=None)
        _posting(conn, company="Acme, Inc.", title="Software Engineer", key="b", url=None)
    rows, malformed = parse_history(
        _write(tmp_path, "h.csv", "company,title\nAcme Inc,Software Engineer\n")
    )
    with engine.begin() as conn:
        first = import_history(conn, rows, malformed, allow_title_match=True)
    with engine.begin() as conn:
        second = import_history(conn, rows, malformed, allow_title_match=True)
    assert first.results[0].bucket is ImportBucket.AMBIGUOUS
    assert second.results[0].bucket is ImportBucket.AMBIGUOUS
    with engine.connect() as conn:
        assert _count(conn, applications) == 0


def test_an_ambiguous_row_is_refused_even_when_every_candidate_is_already_tracked(
    engine: Engine, tmp_path: Path
) -> None:
    """Precedence: ambiguity is judged BEFORE the write loop, so it outranks `already_present`.

    The refusal is about the match being untrustworthy, not about what the store already holds —
    and judging it first is what keeps the bucket stable across re-runs.
    """
    with engine.begin() as conn:
        first = _posting(conn, company="Acme Inc", title="Software Engineer", key="a", url=None)
        second = _posting(conn, company="Acme, Inc.", title="Software Engineer", key="b", url=None)
        create_application(conn, job_id=first, status="applied", source="user")
        create_application(conn, job_id=second, status="applied", source="user")
    rows, malformed = parse_history(
        _write(tmp_path, "h.csv", "company,title\nAcme Inc,Software Engineer\n")
    )
    with engine.begin() as conn:
        report = import_history(conn, rows, malformed, allow_title_match=True)
    assert report.results[0].bucket is ImportBucket.AMBIGUOUS
    assert report.results[0].application_ids == ()


def test_a_url_key_that_covers_several_jobs_still_writes_to_all_of_them(
    engine: Engine, tmp_path: Path
) -> None:
    """The URL key is exact, so a fan-out on it is one posting seen twice, not two requisitions.

    Deliberately NOT changed alongside the company/title refusal: `normalize_url` folding two
    stored postings onto one key means the same application really does cover both.
    """
    with engine.begin() as conn:
        first = _posting(conn, key="a", url="https://boards.example.test/acme/1")
        second = _posting(conn, key="b", url="https://www.boards.example.test/acme/1/?utm_source=x")
    rows, malformed = parse_history(
        _write(tmp_path, "h.csv", "company,title,url\nAcme,SWE,https://boards.example.test/acme/1\n")
    )
    with engine.begin() as conn:
        report = import_history(conn, rows, malformed, allow_title_match=False)
    assert report.results[0].bucket is ImportBucket.MATCHED
    assert report.results[0].match_key is MatchKey.URL
    assert report.results[0].job_ids == tuple(sorted((first, second)))
    assert len(report.results[0].application_ids) == 2


def test_a_quoted_newline_stays_inside_its_field(tmp_path: Path) -> None:
    """A record is not always one line, and the reported line number must survive that."""
    rows, malformed = parse_history(
        _write(
            tmp_path, "h.csv",
            'company,title,url\n"Acme\nHoldings",SWE,https://x.test/1\nBeta,SRE,https://x.test/2\n',
        )
    )
    assert malformed == []
    assert [(row.line_no, row.company) for row in rows] == [(3, "Acme\nHoldings"), (4, "Beta")]

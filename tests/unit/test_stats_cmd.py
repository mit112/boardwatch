from pathlib import Path

import pytest
from rich.console import Console
from sqlalchemy import insert
from typer.testing import CliRunner

from boardwatch.cli.app import app
from boardwatch.cli.profile_cmd import persist_profile
from boardwatch.core.clock import utcnow
from boardwatch.core.settings import load_settings
from boardwatch.reports.stats import StatsReport, compute_stats
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.tables import companies, jobs, postings

NOW = utcnow()
runner = CliRunner()


@pytest.fixture()
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "cfg"))
    data = tmp_path / "data"
    eng = get_engine(data)
    ensure_schema(eng)
    return data


def test_stats_without_profile_reports_no_profile(data_dir: Path) -> None:
    result = runner.invoke(app, ["--data-dir", str(data_dir), "stats"])
    assert "no profile" in result.stdout.lower()


def test_stats_with_profile_but_no_evals_reports_unevaluated(data_dir: Path) -> None:
    eng = get_engine(data_dir)
    settings = load_settings(data_dir=data_dir)  # matches build_context's construction
    persist_profile(
        eng, settings, text="python engineer",
        target_titles=[], exclude_titles=[], locations=[], remote_only=False,
    )
    with eng.begin() as conn:
        c = int(conn.execute(insert(companies).values(
            name="Acme", provider="greenhouse", slug="acme", source="user", watched=True,
        )).inserted_primary_key[0])
        job_id = int(conn.execute(insert(jobs).values(created_at=NOW)).inserted_primary_key[0])
        conn.execute(insert(postings).values(
            company_id=c, job_id=job_id, provider_posting_id="p1", title="Python Engineer",
            normalized_title="python engineer", url="https://example.test/p1",
            locations_json=["Remote"], remote_policy="remote", posted_at=NOW,
            first_seen_at=NOW, last_seen_at=NOW, status="open", consecutive_missing=0,
            content_hash="p1", body_text="We hire python engineers.",
        ))
    result = runner.invoke(app, ["--data-dir", str(data_dir), "stats"])
    assert result.exit_code == 0
    out = result.stdout.lower()
    assert "unevaluated" in out
    assert "seen" in out

    report = compute_stats(
        eng, settings, window_days=7, now=NOW, output_console=Console()
    )
    assert report is not None
    assert report.unevaluated == 1
    assert report.qualified == 0


# `uncertain` by title with a substantive body that yields no recognised taxonomy term -- the
# only pair the zero-signal veto fires on. "Senior" is what makes this fixture discriminating:
# the posting is ALSO above an `entry` target band, so it is the exact overlap the gate ORDER
# has to resolve. Live today, 3 of the 8 titles the veto drops carry Sr./Senior.
ZERO_SIGNAL_SENIOR_TITLE = "Senior Mixed Reality Developer"
ZERO_SKILL_BODY = (
    "We are looking for a motivated team member to join our growing operation. You will "
    "coordinate with partners, keep the floor moving, and report to the shift lead."
)


def _seed_one_posting(
    data_dir: Path, *, title: str, band: str, slug: str = "acme",
    body: str = "We hire python engineers.",
) -> None:
    """One open posting plus a profile targeting `band` — the smallest stats population.

    `slug` is per-posting because (provider, slug) is UNIQUE on companies, so a test seeding a
    second posting needs a second company. `persist_profile` upserts, so calling this twice
    leaves one profile at the band the last call named.
    """
    eng = get_engine(data_dir)
    settings = load_settings(data_dir=data_dir)
    persist_profile(
        eng, settings, text="python engineer",
        target_titles=[], exclude_titles=[], locations=[], remote_only=False,
        target_seniority_band=band,
    )
    with eng.begin() as conn:
        c = int(conn.execute(insert(companies).values(
            name="Acme", provider="greenhouse", slug=slug, source="user", watched=True,
        )).inserted_primary_key[0])
        job_id = int(conn.execute(insert(jobs).values(created_at=NOW)).inserted_primary_key[0])
        conn.execute(insert(postings).values(
            company_id=c, job_id=job_id, provider_posting_id=f"p1-{slug}", title=title,
            normalized_title=title.lower(), url=f"https://example.test/{slug}",
            locations_json=["Remote"], remote_policy="remote", posted_at=NOW,
            first_seen_at=NOW, last_seen_at=NOW, status="open", consecutive_missing=0,
            content_hash=f"p1-{slug}", body_text=body,
        ))


def _report(data_dir: Path) -> StatsReport | None:
    return compute_stats(
        get_engine(data_dir), load_settings(data_dir=data_dir),
        window_days=7, now=NOW, output_console=Console(),
    )


def test_stats_counts_an_above_band_posting(data_dir: Path) -> None:
    """`top` hides it, so a readout that never counted it would disagree with the shortlist."""
    _seed_one_posting(data_dir, title="Staff Software Engineer", band="entry")
    report = _report(data_dir)
    assert report is not None
    assert report.over_seniority == 1
    assert report.passes_filters == 1  # reported alongside the chain, never subtracted from it


def test_stats_does_not_count_an_in_band_posting(data_dir: Path) -> None:
    _seed_one_posting(data_dir, title="Python Engineer", band="entry")
    report = _report(data_dir)
    assert report is not None
    assert report.over_seniority == 0


def test_the_stats_table_renders_the_over_seniority_count(data_dir: Path) -> None:
    """A counter that is computed and tested but never rendered is invisible to the operator.

    T19. This used to read `inspect.getsource(stats_cmd)` and assert the label and the attribute
    appeared SOMEWHERE in the module, which is satisfied by the comment that names them — the
    test passed with the `add_row` line deleted. It now drives the real command and reads the
    rendered table, so deleting either row fails it. Verified by deleting each row once.

    `-1` on the width because rich wraps the table to the terminal and the label is long enough
    to fold at the default 80 columns; the rendered text would then carry a newline inside the
    phrase this asserts on.
    """
    _seed_one_posting(data_dir, title="Staff Software Engineer", band="entry")

    result = runner.invoke(app, ["--data-dir", str(data_dir), "stats"], env={"COLUMNS": "200"})

    assert result.exit_code == 0, result.stdout
    assert "over target band" in result.stdout, "over_seniority is counted but never shown"
    # Ordering the gates correctly moves postings OUT of `over_seniority`; if the bucket they
    # move into is never rendered, fixing the double-count would simply make them disappear
    # from the readout.
    assert "zero signal" in result.stdout, "zero_signal is counted but never shown"
    # The VALUE, not only the label: a row rendering a hardcoded 0 would pass a label check.
    over_line = next(
        line for line in result.stdout.splitlines() if "over target band" in line
    )
    assert "1" in over_line, over_line
def test_a_posting_that_is_both_non_swe_and_over_band_is_counted_once(data_dir: Path) -> None:
    """`top` gates in ORDER: the role gate `continue`s before the seniority gate ever runs, so
    this posting is `hidden_non_swe` there and nothing else. Counted independently here it
    landed in both buckets, and `stats.over_seniority` read higher than the funnel's
    `hidden_over_seniority` for the same corpus -- two numbers for one gate that could not be
    reconciled, which is the whole discipline this gate was built under."""
    from boardwatch.cli.top_cmd import rank_open_postings

    _seed_one_posting(data_dir, title="Senior Marketing Manager", band="entry")
    # The SECOND overlap, added with the zero-signal veto: `uncertain` title + zero recognised
    # terms + above band. The ranker `continue`s on zero-signal BEFORE the seniority gate runs,
    # so this posting is `hidden_zero_signal` there and nothing else. Evaluated independently
    # here it landed in `over_seniority` as well -- the identical irreconcilable double-count,
    # one gate later.
    _seed_one_posting(
        data_dir, title=ZERO_SIGNAL_SENIOR_TITLE, band="entry",
        slug="acme-zero", body=ZERO_SKILL_BODY,
    )
    report = _report(data_dir)
    assert report is not None
    assert report.non_swe == 1
    assert report.zero_signal == 1
    assert report.over_seniority == 0

    # Counted a second time through the OTHER path -- the one the funnel writes down -- because
    # a component's self-report is not verification (CLAUDE.md).
    ranked = rank_open_postings(
        get_engine(data_dir), load_settings(data_dir=data_dir),
        limit=50, record_surfaced=False, output_console=Console(),
    )
    assert (ranked.hidden_non_swe, ranked.hidden_zero_signal, ranked.hidden_over_seniority) == (
        report.non_swe, report.zero_signal, report.over_seniority
    )

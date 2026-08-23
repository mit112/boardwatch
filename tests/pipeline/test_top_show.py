import json
from datetime import timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from gh_fixtures import BOARD_URL, clone_with_id, gh_jobs, set_body, snapshot_for
from sqlalchemy import Engine, insert, select, update
from typer.testing import CliRunner

from boardwatch.cli.app import app
from boardwatch.core.clock import utcnow
from boardwatch.extract.taxonomy import load_taxonomy
from boardwatch.scan.apply import apply_board
from boardwatch.store import tables
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.queries import save_profile

runner = CliRunner()


@pytest.fixture()
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(cfg))
    return tmp_path


def _seed_profile(
    engine: Engine, config_dir: Path, text: str = "Python, Go, PostgreSQL.",
    target_seniority_band: str = "any",
) -> None:
    taxonomy = load_taxonomy(config_dir)
    with engine.begin() as conn:
        save_profile(
            conn, text=text, target_titles=["Backend Engineer"], exclude_titles=[],
            locations=["Remote"], remote_only=False,
            skills=sorted(taxonomy.extract(text)), taxonomy_version=taxonomy.version,
            resume_max_pages=1, target_seniority_band=target_seniority_band,
        )


def _seed_postings(engine: Engine, company_id: int, run_id: int) -> dict[str, int]:
    jobs = gh_jobs()[:2]
    strong = set_body(clone_with_id(jobs[0], 111), "<p>Python, Go, and PostgreSQL daily.</p>")
    strong["title"] = "Backend Engineer"
    strong["location"] = {"name": "Remote — US"}
    weak = set_body(clone_with_id(jobs[1], 222), "<p>Watering plants and pruning roses.</p>")
    weak["title"] = "Gardener"
    weak["location"] = {"name": "On-site greenhouse"}
    apply_board(engine, snapshot_for([strong, weak]), company_id, run_id)
    with engine.connect() as conn:
        rows = conn.execute(
            select(tables.postings.c.id, tables.postings.c.provider_posting_id)
        ).all()
    return {row.provider_posting_id: int(row.id) for row in rows}


def _invoke(data_dir: Path, args: list[str]) -> Any:
    return runner.invoke(app, ["--data-dir", str(data_dir), *args])


def test_top_ranks_strong_match_first(
    env: Path, engine: Engine, company_id: int, run_id: int, tmp_path: Path
) -> None:
    _seed_postings(engine, company_id, run_id)
    _seed_profile(engine, env / "cfg")
    result = _invoke(tmp_path, ["top"])
    assert result.exit_code == 0
    out = result.stdout
    assert "Backend Engineer" in out and "Gardener" in out
    assert out.index("Backend Engineer") < out.index("Gardener")
    assert "covers" in out  # the why column


def test_top_json_outputs_ranked_postings(
    env: Path, engine: Engine, company_id: int, run_id: int, tmp_path: Path
) -> None:
    _seed_postings(engine, company_id, run_id)
    _seed_profile(engine, env / "cfg")

    result = _invoke(tmp_path, ["top", "--json"])

    assert result.exit_code == 0
    postings = json.loads(result.stdout)
    assert postings[0]["title"] == "Backend Engineer"
    assert {"posting_id", "company", "score", "why"} <= postings[0].keys()


def test_top_json_outputs_empty_array_for_no_matching_postings(
    env: Path, engine: Engine, tmp_path: Path
) -> None:
    _seed_profile(engine, env / "cfg")

    result = _invoke(tmp_path, ["top", "--json"])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == []


def test_top_json_outputs_empty_array_for_no_new_matching_postings(
    env: Path, engine: Engine, tmp_path: Path
) -> None:
    _seed_profile(engine, env / "cfg")

    result = _invoke(tmp_path, ["top", "--json", "--new"])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == []
def test_top_json_keeps_missing_profile_message_off_stdout(env: Path, tmp_path: Path) -> None:
    result = _invoke(tmp_path, ["top", "--json"])

    assert result.exit_code == 1
    assert result.stdout == ""
    assert "no profile yet" in result.stderr


def test_top_excludes_closed_postings(
    env: Path, engine: Engine, company_id: int, run_id: int, tmp_path: Path
) -> None:
    ids = _seed_postings(engine, company_id, run_id)
    _seed_profile(engine, env / "cfg")
    apply_board(engine, snapshot_for([]), company_id, run_id)  # miss 1 for both
    jobs = gh_jobs()[:1]
    strong = set_body(clone_with_id(jobs[0], 111), "<p>Python, Go, and PostgreSQL daily.</p>")
    strong["title"] = "Backend Engineer"
    apply_board(engine, snapshot_for([strong]), company_id, run_id)  # Gardener: miss 2 -> closed
    result = _invoke(tmp_path, ["top"])
    assert result.exit_code == 0
    assert "Gardener" not in result.stdout
    assert ids  # silence unused warning


def test_top_help_lists_the_new_flag(env: Path) -> None:
    result = runner.invoke(app, ["top", "--help"])
    assert result.exit_code == 0
    assert "--new" in result.stdout  # P5 task 2 ships the digest-window filter


def test_show_open_posting_renders_breakdown(
    env: Path, engine: Engine, company_id: int, run_id: int, tmp_path: Path
) -> None:
    ids = _seed_postings(engine, company_id, run_id)
    _seed_profile(engine, env / "cfg")
    result = _invoke(tmp_path, ["show", str(ids["111"])])
    assert result.exit_code == 0
    out = result.stdout
    assert "skill_coverage" in out and "title_match" in out
    assert "recency" in out and "location_fit" in out
    assert "Python" in out  # body text rendered


def test_show_closed_posting_banner_no_score_no_extraction(
    env: Path, engine: Engine, company_id: int, run_id: int,
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    ids = _seed_postings(engine, company_id, run_id)
    _seed_profile(engine, env / "cfg")
    apply_board(engine, snapshot_for([]), company_id, run_id)
    apply_board(engine, snapshot_for([]), company_id, run_id)  # both closed

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("preflight must not run for closed postings")

    monkeypatch.setattr("boardwatch.cli.show_cmd.run_preflight", forbidden)
    result = _invoke(tmp_path, ["show", str(ids["222"])])
    assert result.exit_code == 0
    out = result.stdout
    assert "CLOSED" in out
    assert "closed — not ranked" in out
    assert "skill_coverage" not in out  # no score section
    assert "Watering plants" in out  # body/link/comp stay readable
    with engine.connect() as conn:
        extraction_count = len(conn.execute(select(tables.extractions)).all())
    assert extraction_count == 0  # no on-demand extraction for closed postings


def test_show_no_recognized_skills_message(
    env: Path, engine: Engine, company_id: int, run_id: int, tmp_path: Path
) -> None:
    ids = _seed_postings(engine, company_id, run_id)
    _seed_profile(engine, env / "cfg")
    result = _invoke(tmp_path, ["show", str(ids["222"])])  # gardening body: no taxonomy hits
    assert result.exit_code == 0
    assert "no recognized skills" in result.stdout  # Rich may wrap across lines


def test_show_prints_the_band_line(
    env: Path, engine: Engine, company_id: int, run_id: int, tmp_path: Path
) -> None:
    """A row `top` hides as above_band must be explainable by looking it up."""
    senior = set_body(clone_with_id(gh_jobs()[0], 333), "<p>Python, Go, and PostgreSQL daily.</p>")
    senior["title"] = "Staff Software Engineer"
    senior["location"] = {"name": "Remote — US"}
    apply_board(engine, snapshot_for([senior]), company_id, run_id)
    _seed_profile(engine, env / "cfg", target_seniority_band="entry")
    with engine.connect() as conn:
        posting_id = conn.execute(
            select(tables.postings.c.id).where(
                tables.postings.c.provider_posting_id == "333"
            )
        ).scalar_one()
    result = _invoke(tmp_path, ["show", str(posting_id)])
    assert result.exit_code == 0
    out = " ".join(result.stdout.split())  # Rich wraps the line at the console width
    assert "Band:" in out
    assert 'seniority word "staff"' in out
    assert "hidden from top unless --include-over-seniority" in out


def test_show_band_line_carries_no_hidden_note_for_an_in_band_title(
    env: Path, engine: Engine, company_id: int, run_id: int, tmp_path: Path
) -> None:
    ids = _seed_postings(engine, company_id, run_id)
    _seed_profile(engine, env / "cfg", target_seniority_band="entry")
    result = _invoke(tmp_path, ["show", str(ids["111"])])
    assert result.exit_code == 0
    out = " ".join(result.stdout.split())
    assert "Band: no seniority signal in title" in out
    assert "--include-over-seniority" not in out


def test_show_unknown_id_fails_cleanly(env: Path, engine: Engine, tmp_path: Path) -> None:
    result = _invoke(tmp_path, ["show", "424242"])
    assert result.exit_code == 1
    assert "no posting with id 424242" in result.stdout


def test_scan_summary_includes_filter_match_count(
    env: Path, engine: Engine, company_id: int, run_id: int, tmp_path: Path
) -> None:
    _seed_profile(engine, env / "cfg")
    fixture = Path(__file__).resolve().parents[1] / "fixtures" / "greenhouse" / "normal.json"
    with respx.mock:
        respx.get(BOARD_URL).mock(
            return_value=httpx.Response(200, content=fixture.read_bytes())
        )
        result = _invoke(tmp_path, ["scan"])
    assert result.exit_code == 0
    assert "match ranking filters" in result.stdout  # renamed: this count comes from the ranker


def test_help_smoke(env: Path) -> None:
    assert runner.invoke(app, ["top", "--help"]).exit_code == 0
    assert runner.invoke(app, ["show", "--help"]).exit_code == 0


DEGREE_BODY = "We are hiring a backend engineer. A Bachelor's degree is required."
PLAIN_BODY = "Python and Go services with PostgreSQL."


def _seed_one(data_dir: Path, *, title: str, body: str, slug: str) -> int:
    engine = get_engine(data_dir)
    ensure_schema(engine)
    now = utcnow()
    with engine.begin() as conn:
        company_id = int(
            conn.execute(
                insert(tables.companies).values(
                    name="Acme", provider="greenhouse", slug=slug, source="user", watched=True
                )
            ).inserted_primary_key[0]
        )
        job_id = int(conn.execute(insert(tables.jobs).values(created_at=now)).inserted_primary_key[0])
        posting_id = int(
            conn.execute(
                insert(tables.postings).values(
                    company_id=company_id, provider_posting_id=f"pp-{slug}", title=title,
                    normalized_title=title.lower(), url="https://x.example/y",
                    locations_json=["Remote"], remote_policy="remote", first_seen_at=now,
                    last_seen_at=now, status="open", consecutive_missing=0,
                    content_hash=f"hh-{slug}", body_text=body, job_id=job_id,
                )
            ).inserted_primary_key[0]
        )
        conn.execute(
            insert(tables.posting_versions).values(
                posting_id=posting_id, content_hash=f"hh-{slug}", body_text=body,
                captured_at=now, capture_reason="new",
            )
        )
    return posting_id


def _seed_flagged_corpus(data_dir: Path) -> None:
    engine = get_engine(data_dir)
    ensure_schema(engine)
    with engine.begin() as conn:
        save_profile(
            conn, text="Backend engineer.", target_titles=[], exclude_titles=[],
            locations=[], remote_only=False, skills=[], taxonomy_version="t",
            resume_max_pages=1,
        )
    _seed_one(data_dir, title="Open Role", body=PLAIN_BODY, slug="open")
    _seed_one(data_dir, title="Blocked Role", body=DEGREE_BODY, slug="blocked")
    assert _invoke(data_dir, ["eligibility", "facts", "set", "highest_degree", "none"]).exit_code == 0
    assert _invoke(data_dir, ["eligibility", "policy", "set", "degree", "blocker"]).exit_code == 0
    assert _invoke(data_dir, ["eligibility", "run"]).exit_code == 0


def test_top_hides_ineligible_by_default(env: Path, tmp_path: Path) -> None:
    _seed_flagged_corpus(tmp_path)
    result = _invoke(tmp_path, ["top"])
    assert result.exit_code == 0
    out = result.stdout
    assert "Open Role" in out
    assert "no flags" in out  # the eligible posting's one-token flag
    assert "Blocked Role" not in out  # hidden as ineligible
    assert "hidden as ineligible" in out
    assert "not that you qualify" in out  # the qualification carried on the hidden line


def test_top_include_ineligible_shows_the_blocked_row(env: Path, tmp_path: Path) -> None:
    _seed_flagged_corpus(tmp_path)
    result = _invoke(tmp_path, ["top", "--include-ineligible"])
    assert result.exit_code == 0
    out = result.stdout
    assert "Blocked Role" in out
    assert "blocked" in out  # the one-token flag for a persisted ineligible
    assert "hidden as ineligible" not in out


def test_top_hides_ineligible_before_applying_the_limit(env: Path, tmp_path: Path) -> None:
    engine = get_engine(tmp_path)
    ensure_schema(engine)
    with engine.begin() as conn:
        save_profile(
            conn, text="Backend engineer.", target_titles=[], exclude_titles=[],
            locations=[], remote_only=False, skills=[], taxonomy_version="t",
            resume_max_pages=1,
        )
    blocked = _seed_one(tmp_path, title="Blocked Role", body=DEGREE_BODY, slug="blocked")
    eligible = _seed_one(tmp_path, title="Eligible Role", body=PLAIN_BODY, slug="eligible")
    # make the ineligible posting rank #1 by recency so the limit would cut the eligible one
    with engine.begin() as conn:
        conn.execute(
            update(tables.postings).where(tables.postings.c.id == blocked).values(posted_at=utcnow())
        )
        conn.execute(
            update(tables.postings)
            .where(tables.postings.c.id == eligible)
            .values(posted_at=utcnow() - timedelta(days=30))
        )
    assert _invoke(tmp_path, ["eligibility", "facts", "set", "highest_degree", "none"]).exit_code == 0
    assert _invoke(tmp_path, ["eligibility", "policy", "set", "degree", "blocker"]).exit_code == 0
    assert _invoke(tmp_path, ["eligibility", "run"]).exit_code == 0
    result = _invoke(tmp_path, ["top", "1"])
    assert result.exit_code == 0
    out = result.stdout
    # the #1-ranked posting is ineligible; hide-before-limit must still surface the eligible
    # one below it rather than returning an empty shortlist.
    assert "Eligible Role" in out
    assert "Blocked Role" not in out
    assert "hidden as ineligible" in out


def test_top_never_hides_an_unevaluated_posting(env: Path, tmp_path: Path) -> None:
    save_profile_dir = tmp_path
    engine = get_engine(save_profile_dir)
    ensure_schema(engine)
    with engine.begin() as conn:
        save_profile(
            conn, text="Backend engineer.", target_titles=[], exclude_titles=[],
            locations=[], remote_only=False, skills=[], taxonomy_version="t",
            resume_max_pages=1,
        )
    _seed_one(save_profile_dir, title="Unseen Role", body=DEGREE_BODY, slug="unseen")
    # no `eligibility run`: the posting has no evaluation, so it must still appear with `-`
    result = _invoke(save_profile_dir, ["top"])
    assert result.exit_code == 0
    assert "Unseen Role" in result.stdout
    assert "hidden as ineligible" not in result.stdout


def test_eligibility_summary_reports_family_and_disposition(env: Path, tmp_path: Path) -> None:
    _seed_flagged_corpus(tmp_path)
    result = _invoke(tmp_path, ["eligibility", "summary"])
    assert result.exit_code == 0
    out = result.stdout
    assert "no current-engine evaluation" in out
    assert "degree" in out
    assert "unmet" in out


def test_eligibility_summary_sums_a_family_across_postings(env: Path, tmp_path: Path) -> None:
    """The family fold must ADD the per-rule counts, not count each rule once.

    `summary` no longer fetches one row per requirement; it folds `count_requirement_dispositions`'
    pre-aggregated `(rule_id, disposition) -> count` up into families (D-287), which is what makes
    it cap-safe. That fold is only distinguishable from `+= 1` when two postings share a
    (family, disposition), so this seeds two degree-blocked postings and asserts the printed
    **2**. Reverting `+= count` to `+= 1` prints `degree · unmet: 1` and fails here.
    """
    engine = get_engine(tmp_path)
    ensure_schema(engine)
    with engine.begin() as conn:
        save_profile(
            conn, text="Backend engineer.", target_titles=[], exclude_titles=[],
            locations=[], remote_only=False, skills=[], taxonomy_version="t",
            resume_max_pages=1,
        )
    _seed_one(tmp_path, title="Blocked One", body=DEGREE_BODY, slug="blocked-one")
    _seed_one(tmp_path, title="Blocked Two", body=DEGREE_BODY, slug="blocked-two")
    assert _invoke(tmp_path, ["eligibility", "facts", "set", "highest_degree", "none"]).exit_code == 0
    assert _invoke(tmp_path, ["eligibility", "policy", "set", "degree", "blocker"]).exit_code == 0
    assert _invoke(tmp_path, ["eligibility", "run"]).exit_code == 0

    result = _invoke(tmp_path, ["eligibility", "summary"])
    assert result.exit_code == 0
    assert "degree · unmet: 2" in result.stdout, result.stdout

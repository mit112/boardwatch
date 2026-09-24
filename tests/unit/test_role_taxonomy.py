"""The per-user role taxonomy (P2 item 8, D-054): the role gate reads the USER's field, not ours.

Every non-software vocabulary here is synthetic and written by the test — boardwatch ships role
knowledge for software only, and anything else is a user's own onboarding answer.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
import yaml
from sqlalchemy import Engine, insert, select
from typer.testing import CliRunner

from boardwatch.cli.app import app
from boardwatch.cli.top_cmd import RankedResults, rank_open_postings
from boardwatch.core.clock import utcnow
from boardwatch.core.settings import Settings
from boardwatch.pipeline.runner import _lead_lanes
from boardwatch.rank.role_gate import role_verdict, taxonomy_role_verdict
from boardwatch.rank.role_taxonomy import (
    MISSING_ROLE_TAXONOMY,
    ROLE_TAXONOMY_FILE,
    RoleTaxonomyError,
    load_role_taxonomy,
    parse_role_taxonomy,
    write_role_taxonomy,
)
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.delivery_queries import delivered_unapplied, lane_decision, queue_detail
from boardwatch.store.queries import save_profile
from boardwatch.store.tables import artifacts, companies, jobs, posting_versions, postings

NOW = utcnow()
runner = CliRunner()

# A synthetic non-software field, as onboarding would gather it for some user.
WIDGET_FIELD: dict[str, Any] = {
    "version": 1,
    "field": "widgetry",
    "role_families": [
        {"id": "inspection", "title_words": ["widget inspector", "inspection lead"]},
        {"id": "assembly", "title_words": ["widget assembler"]},
    ],
    "exclude_words": ["software", "engineer"],
}
BUNDLED_SOFTWARE: dict[str, Any] = {"version": 1, "field": "software", "bundled": True}

# `Account Executive` is a hard deny in the bundled software gate, so "no taxonomy" can be told
# apart from "classified with the bundled software list" by whether it is hidden.
SOFTWARE_TITLE = "Senior Software Engineer, Payments"
DENIED_BY_SOFTWARE_GATE = "Account Executive"
WIDGET_TITLE = "Senior Widget Inspector"
BODY = "Strong Python and SQL experience, with Docker in production."

# The control sample: titles spanning every stage of the bundled gate (rescue, hard deny,
# exec-rank deny, soft deny, signal, uncertain).
CONTROL_TITLES = (
    SOFTWARE_TITLE,
    "Backend Engineer",
    "iOS Developer",
    "Site Reliability Engineer",
    "Software Quality Engineer",
    "Front End Lead Trainee",
    "Assistant Manager Front End",
    "Chief Technology Officer",
    DENIED_BY_SOFTWARE_GATE,
    "Registered Nurse - ICU",
    "Water Spider",
    "Implementation Engineer",
    "Data Engineer",
    "Machine Learning Engineer",
    "On Shift (IOS) Technology Development Engineer",
    "Program Manager",
)


def _seed(data_dir: Path, titles: list[str]) -> Engine:
    engine = get_engine(data_dir)
    ensure_schema(engine)
    with engine.begin() as conn:
        save_profile(
            conn, text="A profile.", target_titles=[], exclude_titles=[],
            locations=[], remote_only=False, skills=[], taxonomy_version="t",
            resume_max_pages=1,
        )
        company_id = int(conn.execute(insert(companies).values(
            name="Acme", provider="greenhouse", slug="acme-role", source="user", watched=True,
        )).inserted_primary_key[0])
        for offset, title in enumerate(titles):
            job_id = int(conn.execute(insert(jobs).values(created_at=NOW)).inserted_primary_key[0])
            posting_id = int(conn.execute(insert(postings).values(
                company_id=company_id, job_id=job_id, provider_posting_id=f"rt-{offset}",
                title=title, normalized_title=title.casefold(),
                locations_json=["Remote"], remote_policy="remote",
                posted_at=NOW - timedelta(days=offset), first_seen_at=NOW, last_seen_at=NOW,
                status="open", consecutive_missing=0, content_hash=f"rt-{offset}",
                body_text=BODY,
            )).inserted_primary_key[0])
            conn.execute(insert(posting_versions).values(
                posting_id=posting_id, content_hash=f"rt-{offset}", body_text=BODY,
                captured_at=NOW, capture_reason="new",
            ))
    return engine


def _rank(
    tmp_path: Path, titles: list[str], taxonomy: dict[str, Any] | None,
    *, include_non_swe: bool = False,
) -> RankedResults:
    data_dir = tmp_path / "data"
    if taxonomy is not None:
        write_role_taxonomy(data_dir, taxonomy)
    engine = _seed(data_dir, titles)
    return rank_open_postings(
        engine, Settings(data_dir=data_dir, config_dir=data_dir), limit=50, record_surfaced=False,
        include_non_swe=include_non_swe,
    )


# ------------------------------------------------------------ (1) no taxonomy ⇒ the gate abstains


def test_a_user_with_no_taxonomy_abstains_and_the_ranker_counts_it(tmp_path: Path) -> None:
    titles = [SOFTWARE_TITLE, DENIED_BY_SOFTWARE_GATE, WIDGET_TITLE]
    results = _rank(tmp_path, titles, taxonomy=None)
    # Not cleared, not rejected: every posting stays visible and names the missing field.
    assert results.hidden_non_swe == 0
    assert sorted(p.title for p in results.visible) == sorted(titles)
    assert {(p.role, p.role_reason) for p in results.visible} == {
        ("unmeasured", MISSING_ROLE_TAXONOMY)
    }
    assert results.role_unmeasured == len(titles)


def test_the_abstain_is_its_own_verdict_never_folded_into_uncertain() -> None:
    # `uncertain` feeds the zero-signal veto; an abstain must not become a drop.
    assert taxonomy_role_verdict("Water Spider", None) == ("unmeasured", MISSING_ROLE_TAXONOMY)


# ----------------------------------------------- (2) a non-tech taxonomy ranks on the user's field


def test_a_gathered_taxonomy_ranks_its_own_field_and_not_software(tmp_path: Path) -> None:
    results = _rank(
        tmp_path, [WIDGET_TITLE, SOFTWARE_TITLE, "Widget Assembler II"], taxonomy=WIDGET_FIELD
    )
    visible = {p.title: p for p in results.visible}
    assert set(visible) == {WIDGET_TITLE, "Widget Assembler II"}
    assert visible[WIDGET_TITLE].role == "swe"
    assert "'inspection'" in visible[WIDGET_TITLE].role_reason
    assert results.hidden_non_swe == 1
    assert results.role_unmeasured == 0


def test_a_family_word_is_tried_before_any_exclude_word() -> None:
    taxonomy = parse_role_taxonomy(WIDGET_FIELD)
    # "engineer" is excluded, but a family hit decides first (the software gate's rescue order).
    assert taxonomy_role_verdict("Widget Inspector Engineer", taxonomy)[0] == "swe"
    assert taxonomy_role_verdict("Plant Engineer", taxonomy)[0] == "not_swe"
    assert taxonomy_role_verdict("Floor Coordinator", taxonomy)[0] == "uncertain"


def test_title_words_match_whole_words_only() -> None:
    taxonomy = parse_role_taxonomy(WIDGET_FIELD)
    assert taxonomy_role_verdict("Widget   Inspector", taxonomy)[0] == "swe"
    assert taxonomy_role_verdict("Widget Inspectorate Clerk", taxonomy)[0] == "uncertain"


# --------------------------------------------- (3) control: the tech user's verdicts do not move


@pytest.mark.parametrize("title", CONTROL_TITLES)
def test_the_bundled_software_taxonomy_is_byte_identical_to_the_software_gate(title: str) -> None:
    taxonomy = parse_role_taxonomy(BUNDLED_SOFTWARE)
    assert taxonomy_role_verdict(title, taxonomy) == role_verdict(title)


def test_a_tech_user_ranks_exactly_as_before(tmp_path: Path) -> None:
    results = _rank(tmp_path, list(CONTROL_TITLES), taxonomy=BUNDLED_SOFTWARE)
    expected_hidden = [t for t in CONTROL_TITLES if role_verdict(t)[0] == "not_swe"]
    assert results.hidden_non_swe == len(expected_hidden)
    assert results.role_unmeasured == 0
    for posting in results.visible:
        assert (posting.role, posting.role_reason) == role_verdict(posting.title)


# ----------------------------------- (T184b) the delivery lane reads the same verdict as the ranker


def _lanes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, titles: list[str],
    taxonomy: dict[str, Any] | None, *, include_non_swe: bool = False,
) -> dict[str, tuple[str, str, str | None, str | None, str]]:
    """Per visible title: `(top's role, the list row's role, the list's reason, the pane's reason,
    the run's pre-tailor lane)` — every lane reader, against the ONE store `top` ranked."""
    results = _rank(tmp_path, titles, taxonomy, include_non_swe=include_non_swe)
    data_dir = tmp_path / "data"
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(data_dir))
    monkeypatch.setenv("BOARDWATCH_DATA_DIR", str(data_dir))
    engine = get_engine(data_dir)
    with engine.begin() as conn:
        # A tailored artifact on every posting makes each one a standing lead.
        for version_id in conn.execute(select(posting_versions.c.id)).scalars():
            conn.execute(insert(artifacts).values(
                posting_version_id=version_id, kind="resume_tailored",
                uri=f"/out/{version_id}.typ", generator="boardwatch.tailor",
                media_type="text/x-tex", meta_json={}, created_at=NOW,
            ))
    run_lanes, _ = _lead_lanes(
        engine, Settings(data_dir=data_dir, config_dir=data_dir), results.visible
    )
    top = {p.title: (p.role, run_lanes[p.posting_id][0]) for p in results.visible}
    out: dict[str, tuple[str, str, str | None, str | None, str]] = {}
    with engine.connect() as conn:
        for row in delivered_unapplied(conn, skipped=set()):
            if row.title not in top:
                continue
            detail = queue_detail(conn, row.posting_id)
            assert detail is not None
            out[row.title] = (
                top[row.title][0], row.role, lane_decision(row).reason,
                lane_decision(detail.row).reason, top[row.title][1],
            )
    return out


def test_with_no_taxonomy_the_lane_holds_as_unmeasured_never_as_a_veto(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lanes = _lanes(tmp_path, monkeypatch, [DENIED_BY_SOFTWARE_GATE], taxonomy=None)
    # The bundled software gate would VETO this title; with no taxonomy nothing decided it.
    top_role, row_role, reason, pane_reason, run_lane = lanes[DENIED_BY_SOFTWARE_GATE]
    assert (reason, pane_reason) == ("role_gate_unmeasured", "role_gate_unmeasured")
    assert run_lane == "_review"
    assert top_role == row_role == "unmeasured"


def test_a_gathered_taxonomy_passes_its_own_field_through_the_lane_role_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lanes = _lanes(tmp_path, monkeypatch, [WIDGET_TITLE], taxonomy=WIDGET_FIELD)
    top_role, row_role, reason, pane_reason, _run_lane = lanes[WIDGET_TITLE]
    role_reasons = {"role_vetoed", "role_unconfirmed", "role_gate_unmeasured"}
    assert reason not in role_reasons and pane_reason not in role_reasons
    # Past the role gate it is held only because the catalog found no requirement in `BODY`.
    assert (reason, pane_reason) == ("no_requirements_found", "no_requirements_found")
    assert top_role == row_role == "swe"


def test_a_tech_user_lane_still_vetoes_a_not_software_title(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # CONTROL: `bundled: true` routes exactly as the bundled `role_verdict` did.
    titles = [DENIED_BY_SOFTWARE_GATE, "Water Spider", SOFTWARE_TITLE]
    lanes = _lanes(
        tmp_path, monkeypatch, titles, taxonomy=BUNDLED_SOFTWARE, include_non_swe=True
    )
    assert set(lanes) == set(titles)
    for title, (top_role, row_role, reason, pane_reason, _run_lane) in lanes.items():
        assert top_role == row_role == role_verdict(title)[0]
        assert reason == pane_reason
    assert lanes[DENIED_BY_SOFTWARE_GATE][2] == "role_vetoed"
    assert lanes["Water Spider"][2] == "role_unconfirmed"
    assert lanes[SOFTWARE_TITLE][2] == "no_requirements_found"


# ------------------------------------------------ (4) onboarding writes it; re-reading hashes same

# The init wizard's answers up to its last pre-existing prompt (the eligibility confirm).
_INIT_PREFIX = "3\nacme\nA profile.\n\n\n\nn\nn\n"


@pytest.fixture(autouse=True)
def _config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)


def _cli(tmp_path: Path, args: list[str], answers: str) -> Any:
    return runner.invoke(app, ["--data-dir", str(tmp_path / "data"), *args], input=answers)


def _init(tmp_path: Path, answers: str) -> Any:
    return _cli(tmp_path, ["init"], _INIT_PREFIX + answers)


def test_onboarding_writes_a_gathered_taxonomy_that_rereads_to_the_same_hash(
    tmp_path: Path,
) -> None:
    result = _init(
        tmp_path,
        "widgetry\ninspection, assembly\nwidget inspector, inspection lead\n"
        "widget assembler\nsoftware, engineer\n",
    )
    assert result.exit_code == 0, result.output
    config_dir = tmp_path / "cfg"
    first = load_role_taxonomy(config_dir)
    second = load_role_taxonomy(config_dir)
    assert first is not None and second is not None
    assert first.digest == second.digest == parse_role_taxonomy(WIDGET_FIELD).digest
    assert yaml.safe_load((config_dir / ROLE_TAXONOMY_FILE).read_text()) == WIDGET_FIELD


def test_onboarding_a_tech_user_gets_the_bundled_taxonomy(tmp_path: Path) -> None:
    result = _init(tmp_path, "software\n")
    assert result.exit_code == 0, result.output
    taxonomy = load_role_taxonomy(tmp_path / "cfg")
    assert taxonomy is not None and taxonomy.bundled
    assert taxonomy.digest == parse_role_taxonomy(BUNDLED_SOFTWARE).digest


def test_onboarding_a_blank_answer_writes_nothing_and_says_the_gate_abstains(
    tmp_path: Path,
) -> None:
    result = _init(tmp_path, "\n")
    assert result.exit_code == 0, result.output
    assert not (tmp_path / "cfg" / ROLE_TAXONOMY_FILE).exists()
    assert MISSING_ROLE_TAXONOMY in result.output


def test_init_never_overwrites_an_existing_taxonomy(tmp_path: Path) -> None:
    write_role_taxonomy(tmp_path / "cfg", WIDGET_FIELD)
    before = (tmp_path / "cfg" / ROLE_TAXONOMY_FILE).read_text()
    assert _init(tmp_path, "software\n").exit_code == 0
    assert (tmp_path / "cfg" / ROLE_TAXONOMY_FILE).read_text() == before


def test_profile_role_taxonomy_replaces_it_on_an_existing_install(tmp_path: Path) -> None:
    write_role_taxonomy(tmp_path / "cfg", WIDGET_FIELD)
    result = _cli(tmp_path, ["profile", "role-taxonomy"], "software\n")
    assert result.exit_code == 0, result.output
    taxonomy = load_role_taxonomy(tmp_path / "cfg")
    assert taxonomy is not None and taxonomy.bundled


def test_an_invalid_onboarding_answer_reprompts_instead_of_writing(tmp_path: Path) -> None:
    # "Bad Id" is not a token; the wizard says so and asks again rather than writing a file
    # the ranker would refuse.
    result = _init(tmp_path, "Bad Id\nsoftware\n")
    assert result.exit_code == 0, result.output
    assert "lowercase token" in result.output
    taxonomy = load_role_taxonomy(tmp_path / "cfg")
    assert taxonomy is not None and taxonomy.bundled


# ------------------------------------------------ (5) a malformed file is a typed failure


@pytest.mark.parametrize(
    ("document", "message"),
    [
        ("- just a list\n", "top level must be a mapping"),
        ("version: 2\nfield: widgetry\nbundled: true\n", "version 2"),
        ("version: 1\nfield: Widgetry\nbundled: true\n", "lowercase token"),
        ("version: 1\nfield: widgetry\nbundled: true\n", "only available for"),
        ("version: 1\nfield: software\nbundled: true\nexclude_words: [x]\n", "cannot also"),
        ("version: 1\nfield: widgetry\n", "non-empty list"),
        ("version: 1\nfield: widgetry\nrole_families: []\n", "non-empty list"),
        (
            "version: 1\nfield: widgetry\nrole_families: [{id: a, title_words: []}]\n",
            "no title_words",
        ),
        (
            "version: 1\nfield: widgetry\nrole_families:\n"
            "  - {id: a, title_words: [x]}\n  - {id: a, title_words: [y]}\n",
            "duplicate role family",
        ),
        (
            "version: 1\nfield: widgetry\nrole_families: [{id: a, title_words: [x, X]}]\n",
            "repeats",
        ),
        (
            "version: 1\nfield: widgetry\nrole_families: [{id: a, title_words: [x], w: 1}]\n",
            "unknown key",
        ),
        ("version: 1\nfield: software\nbundled: yes please\n", "true or false"),
        ("version: 1\nfield: software\nbundled: true\nextra: 1\n", "unknown key"),
        ("version: [1\n", "not valid YAML"),
    ],
)
def test_a_malformed_taxonomy_is_a_typed_failure(
    tmp_path: Path, document: str, message: str
) -> None:
    (tmp_path / ROLE_TAXONOMY_FILE).write_text(document, encoding="utf-8")
    with pytest.raises(RoleTaxonomyError, match=message):
        load_role_taxonomy(tmp_path)


def test_the_ranker_refuses_a_malformed_taxonomy_rather_than_defaulting(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / ROLE_TAXONOMY_FILE).write_text("version: 1\nfield: widgetry\n", encoding="utf-8")
    engine = _seed(data_dir, [SOFTWARE_TITLE])
    with pytest.raises(RoleTaxonomyError):
        rank_open_postings(
            engine, Settings(data_dir=data_dir, config_dir=data_dir), limit=50,
            record_surfaced=False,
        )


def test_a_missing_file_is_no_taxonomy_not_an_error(tmp_path: Path) -> None:
    assert load_role_taxonomy(tmp_path) is None


def test_the_digest_follows_meaning_not_formatting(tmp_path: Path) -> None:
    (tmp_path / ROLE_TAXONOMY_FILE).write_text(
        "# a comment\nversion: 1\nfield: software\nbundled: true\n", encoding="utf-8"
    )
    commented = load_role_taxonomy(tmp_path)
    assert commented is not None
    assert commented.digest == parse_role_taxonomy(BUNDLED_SOFTWARE).digest
    assert commented.digest != parse_role_taxonomy(WIDGET_FIELD).digest

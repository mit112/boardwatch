"""TDD for T45 (D-477): the ranker must tier on the verdict before it orders by score.

Before this ticket `scored.sort(key=lambda r: r.score.total, reverse=True)` (top_cmd.py
~561) was the WHOLE sort key — `eligible` and `uncertain` postings tied on score alone, so
a decided lead could rank below one nobody has judged yet. The fix sorts on
`(tier, -score.total)`: tier 0 is a decided `eligible` (the deterministic verdict on the
row, OR a persisted final-gate `eligible` — same read `hidden_ineligible` already uses,
`current_gate_verdicts` via `gate_verdicts`), tier 1 is `uncertain` + role `swe` (the
release population), tier 2 is everything else visible. Score still orders WITHIN a tier.

Seeding mirrors test_rank_gate_filter.py: one company, SAFE_BODY postings (never flagged
by the deterministic engine), `Facts()`/`Policy(families={})` so `record_gate_verdict`'s
identity matches the seeded profile's, and `current_posting_versions` to get the
`posting_version_id` a gate row is written against.
"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine, insert

from boardwatch.cli.top_cmd import RankedResults, rank_open_postings
from boardwatch.core.clock import utcnow
from boardwatch.core.settings import Settings
from boardwatch.eligibility import final_gate
from boardwatch.eligibility.catalog import RulesCatalog, load_rules
from boardwatch.eligibility.facts import Facts, Policy
from boardwatch.eligibility.oracle import OracleVerdict
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.queries import current_posting_versions, save_profile
from boardwatch.store.tables import companies, jobs, posting_versions, postings

NOW = utcnow()

# Never flagged by the deterministic engine (test_rank_gate_filter.py's fixture body).
SAFE_BODY = "We are hiring a backend engineer to work on our platform."


def _catalog(tmp_path: Path) -> RulesCatalog:
    return load_rules(tmp_path / "no-such-cfg-dir")


def _settings(data_dir: Path) -> Settings:
    return Settings(data_dir=data_dir, config_dir=data_dir)


def _seed(data_dir: Path, titles: list[str]) -> dict[str, int]:
    """One company, one open SAFE_BODY posting per title, ALL posted at the same instant
    so recency cannot explain a score difference — only title_match against the single
    seeded target title ("Software Engineer") can. Returns title -> posting_id."""
    engine = get_engine(data_dir)
    ensure_schema(engine)
    posting_ids: dict[str, int] = {}
    with engine.begin() as conn:
        save_profile(
            conn, text="Backend engineer.", target_titles=["Software Engineer"],
            exclude_titles=[], locations=[], remote_only=False, skills=[],
            taxonomy_version="t", resume_max_pages=1,
        )
        company_id = int(conn.execute(insert(companies).values(
            name="Acme", provider="greenhouse", slug="acme-verdict-tiers", source="user",
            watched=True,
        )).inserted_primary_key[0])
        for offset, title in enumerate(titles):
            job_id = int(conn.execute(insert(jobs).values(created_at=NOW)).inserted_primary_key[0])
            posting_id = int(conn.execute(insert(postings).values(
                company_id=company_id, job_id=job_id, provider_posting_id=f"pp-{offset}",
                title=title, normalized_title=title.casefold(),
                locations_json=["Remote"], remote_policy="remote",
                posted_at=NOW, first_seen_at=NOW, last_seen_at=NOW,
                status="open", consecutive_missing=0, content_hash=f"hh-{offset}",
                body_text=SAFE_BODY,
            )).inserted_primary_key[0])
            posting_ids[title] = posting_id
            conn.execute(insert(posting_versions).values(
                posting_id=posting_id, content_hash=f"hh-{offset}", body_text=SAFE_BODY,
                captured_at=NOW, capture_reason="new",
            ))
    return posting_ids


def _mark_gate_eligible(engine: Engine, tmp_path: Path, *, posting_id: int) -> None:
    """Persist a final-gate `eligible` verdict for `posting_id`, the same write path
    `test_rank_gate_filter.py` uses for `ineligible`. `accept_oracle_verdict` only gates
    the `ineligible` decision (a span-less ineligible downgrades to uncertain); `eligible`
    passes straight through, so this is the read `current_gate_verdicts`/`gate_verdicts`
    surfaces at the sort site."""
    catalog = _catalog(tmp_path)
    with engine.connect() as conn:
        pv_id = current_posting_versions(conn, [posting_id])[posting_id].posting_version_id
    with engine.begin() as conn:
        final_gate.record_gate_verdict(
            conn, posting_version_id=pv_id, jd_text=SAFE_BODY,
            facts=Facts(), policy=Policy(families={}), catalog=catalog,
            verdict=OracleVerdict(
                label=str(posting_id), decision="eligible", reason=None, evidence="",
                confidence="high",
            ),
        )


def test_a_decided_eligible_lead_outranks_a_higher_scoring_uncertain_swe_lead(
    tmp_path: Path,
) -> None:
    """A: `Data Engineer`, gate-marked `eligible`, LOWER score (title_match 0.0 against the
    lone target "Software Engineer"). B: `Software Engineer`, verdict `uncertain` (the
    deterministic engine's default on a body it never flags — see the module docstring),
    role `swe`, and a HIGHER score (title_match 1.0, exact target match). Both are visible
    (role `swe`, no hard filter, `--include-*` defaults untouched).

    Against unchanged code (`scored.sort(key=lambda r: r.score.total, reverse=True)`) B
    ranks first — score is the only key. The fix must rank A first: a decided `eligible`
    lead outranks an undecided one regardless of score.
    """
    posting_ids = _seed(tmp_path, ["Data Engineer", "Software Engineer"])
    a_id, b_id = posting_ids["Data Engineer"], posting_ids["Software Engineer"]
    engine = get_engine(tmp_path)
    _mark_gate_eligible(engine, tmp_path, posting_id=a_id)

    results: RankedResults = rank_open_postings(engine, _settings(tmp_path), limit=10, now=NOW)
    by_id = {p.posting_id: p for p in results.visible}
    assert by_id[b_id].role == "swe"
    assert by_id[b_id].verdict == "uncertain"
    # The scores must actually differ, and B's must be the higher one — otherwise a pass
    # below would be an accident of the fixture, not evidence the tiering fired.
    assert by_id[b_id].score.total > by_id[a_id].score.total

    assert [p.posting_id for p in results.visible] == [a_id, b_id]


def test_two_eligible_leads_keep_score_order_inside_the_tier(tmp_path: Path) -> None:
    """Control, not a red-first test: green before AND after the fix. Two postings both
    gate-marked `eligible` (same tier) must still rank by score within that tier — this is
    a re-ordering by tier, not a re-weighting that flattens score inside one."""
    posting_ids = _seed(tmp_path, ["Data Engineer", "Software Engineer"])
    low_id, high_id = posting_ids["Data Engineer"], posting_ids["Software Engineer"]
    engine = get_engine(tmp_path)
    _mark_gate_eligible(engine, tmp_path, posting_id=low_id)
    _mark_gate_eligible(engine, tmp_path, posting_id=high_id)

    results: RankedResults = rank_open_postings(engine, _settings(tmp_path), limit=10, now=NOW)
    by_id = {p.posting_id: p for p in results.visible}
    assert by_id[high_id].score.total > by_id[low_id].score.total

    assert [p.posting_id for p in results.visible] == [high_id, low_id]

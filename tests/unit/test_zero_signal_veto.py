"""The zero-signal veto: no role signal in the title AND no recognised term in the body.

Two independently-computed abstains, ANDed. `role_verdict` returning `uncertain` used to fail
open all by itself — `top_cmd` vetoed only `not_swe` — so a title carrying no software word
shipped a résumé regardless of what its job description said. Measured over the full corpus,
the zero-skill rate is 1.5% under a `swe` title and 35.9% under an `uncertain` one, and a
posting with zero recognised requirement terms cannot be tailored to at all.

**What every test here has to defend against, because it is the failure mode that would ship
silently.** `top_cmd`'s scoring line reads `(row.extraction_json or {}).get("skills", [])`,
which collapses a NULL outer-join row into an empty skill set. Copying that expression into
the veto turns the rule into "veto everything un-extracted". Confirmed 0 of 48,285 open
postings currently lack an extraction row, so the two states are indistinguishable on today's
data and no ordinary test would notice — which is why
`test_a_posting_with_no_extraction_row_at_all_still_ships` builds the state deliberately.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import Engine, insert

from boardwatch.cli.top_cmd import RankedResults, rank_open_postings
from boardwatch.core.clock import utcnow
from boardwatch.core.settings import Settings
from boardwatch.rank.role_gate import role_verdict, zero_signal_verdict
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.queries import save_profile
from boardwatch.store.tables import companies, jobs, posting_versions, postings

NOW = utcnow()

# Every string below is a REAL title from the measured population, not a plausible invention.
# Two `swe`-by-title postings whose bodies yield zero recognised terms. Both would be deleted
# if the rule were applied unconditionally instead of only to `uncertain`.
SWE_ZERO_SKILL = "Embedded Software Engineer - MCU Platforms"
SWE_ZERO_SKILL_2 = "Associate Software Engineer"
# `uncertain` by title. The first two are the noise the rule exists to remove; the third is the
# one that survives, because its body yields a single recognised term.
UNCERTAIN_NOISE = "Water Spider"
UNCERTAIN_NOISE_2 = "BIM Modeler"
UNCERTAIN_WITH_SIGNAL = "Implementation Engineer"

# Yields no recognised taxonomy term. Substantive on purpose: the measured population is bodies
# of 1,646-10,324 characters that recognise nothing, not empty stubs.
ZERO_SKILL_BODY = (
    "We are looking for a motivated team member to join our growing operation. You will "
    "coordinate with partners, keep the floor moving, and report to the shift lead."
)
# The threshold is exactly zero, so ONE recognised term is enough to survive. `Distributed
# systems` is the entire yield of the real Implementation Engineer body this stands in for.
ONE_SKILL_BODY = "You will work on distributed systems supporting our platform partners."
MANY_SKILL_BODY = "Strong Python and SQL experience, with Docker in production."


@pytest.fixture()
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    return tmp_path / "data"


def _seed(data_dir: Path, rows: list[tuple[str, str]]) -> Engine:
    """One open posting per (title, body), distinct posted_at so ranking is total."""
    engine = get_engine(data_dir)
    ensure_schema(engine)
    with engine.begin() as conn:
        save_profile(
            conn, text="Backend engineer.", target_titles=[], exclude_titles=[],
            locations=[], remote_only=False, skills=[], taxonomy_version="t",
            resume_max_pages=1,
        )
        company_id = int(conn.execute(insert(companies).values(
            name="Acme", provider="greenhouse", slug="acme-zero", source="user", watched=True,
        )).inserted_primary_key[0])
        for offset, (title, body) in enumerate(rows):
            job_id = int(conn.execute(insert(jobs).values(created_at=NOW)).inserted_primary_key[0])
            posting_id = int(conn.execute(insert(postings).values(
                company_id=company_id, job_id=job_id, provider_posting_id=f"pp-{offset}",
                title=title, normalized_title=title.casefold(),
                locations_json=["Remote"], remote_policy="remote",
                posted_at=NOW - timedelta(days=offset), first_seen_at=NOW, last_seen_at=NOW,
                status="open", consecutive_missing=0, content_hash=f"hh-{offset}",
                body_text=body,
            )).inserted_primary_key[0])
            conn.execute(insert(posting_versions).values(
                posting_id=posting_id, content_hash=f"hh-{offset}", body_text=body,
                captured_at=NOW, capture_reason="new",
            ))
    return engine


def _settings(data_dir: Path) -> Settings:
    return Settings(data_dir=data_dir, config_dir=data_dir)


def _rank(data_dir: Path, rows: list[tuple[str, str]], **kwargs: object) -> RankedResults:
    engine = _seed(data_dir, rows)
    return rank_open_postings(
        engine, _settings(data_dir), limit=50, record_surfaced=False, **kwargs  # type: ignore[arg-type]
    )


def _titles(results: RankedResults) -> list[str]:
    return [posting.title for posting in results.visible]


def _accounted(results: RankedResults) -> int:
    """Every drop bucket in the reconciliation identity, plus what stayed visible.

    `signal_unmeasured` and `uncertain_band` are deliberately absent: they count postings that
    are already inside `visible`, so adding them would double-count.
    """
    return (
        len(results.visible)
        + results.skipped_not_new
        + results.hidden_hard_filter
        + results.hidden_non_swe
        + results.hidden_zero_signal
        + results.hidden_over_seniority
        + results.hidden_ineligible
        + results.hidden_below_cutoff
        + results.hidden_duplicate
        + results.hidden_applied
        + results.hidden_handled
    )


# ---------------------------------------------------------------------------------------
# The rule itself. Four combinations of {role} x {body signal}, plus the two abstain shapes.
# ---------------------------------------------------------------------------------------


def test_the_titles_this_module_relies_on_still_carry_the_role_verdicts_it_assumes() -> None:
    """Every test below is conditioned on these verdicts; if the role gate is retuned and a
    fixture title changes bucket, the tests would keep passing while testing nothing."""
    assert role_verdict(SWE_ZERO_SKILL)[0] == "swe"
    assert role_verdict(SWE_ZERO_SKILL_2)[0] == "swe"
    assert role_verdict(UNCERTAIN_NOISE)[0] == "uncertain"
    assert role_verdict(UNCERTAIN_NOISE_2)[0] == "uncertain"
    assert role_verdict(UNCERTAIN_WITH_SIGNAL)[0] == "uncertain"


def test_only_uncertain_and_zero_skills_is_vetoed() -> None:
    """The four combinations. Three of them must NOT veto, and each for its own reason."""
    assert zero_signal_verdict("uncertain", {"skills": []})[0] == "veto"
    assert zero_signal_verdict("uncertain", {"skills": ["Distributed systems"]})[0] == "pass"
    assert zero_signal_verdict("swe", {"skills": []})[0] == "pass"
    assert zero_signal_verdict("swe", {"skills": ["Python"]})[0] == "pass"
    # `not_swe` is the role gate's own bucket and is already gone by this point; asserted so
    # nobody widens the rule to it and quietly changes which counter a posting lands in.
    assert zero_signal_verdict("not_swe", {"skills": []})[0] == "pass"


def test_exactly_one_recognised_term_survives() -> None:
    """The threshold is exactly zero and is not tunable. At <=1 this posting is dropped, and
    the measured loss rate more than triples."""
    assert zero_signal_verdict("uncertain", {"skills": ["Distributed systems"]}) == ("pass", "")


def test_a_missing_extraction_is_not_zero_skills() -> None:
    """The distinction the whole rule rests on: "we looked and found nothing" is a claim, and
    "nothing looked" is the absence of one. Only the first may fire."""
    verdict, reason = zero_signal_verdict("uncertain", None)
    assert verdict == "unmeasured"
    assert "no taxonomy extraction" in reason
    # An extraction whose payload has no skills list is unreadable, not empty. Same treatment.
    assert zero_signal_verdict("uncertain", {})[0] == "unmeasured"
    assert zero_signal_verdict("uncertain", {"skills": None})[0] == "unmeasured"


def test_the_reason_string_distinguishes_the_two_states() -> None:
    """Both are auditable, and they must never read the same: one hides a posting and the
    other declines to. A shared reason string would make an outage look like a clean gate."""
    vetoed = zero_signal_verdict("uncertain", {"skills": []})[1]
    unmeasured = zero_signal_verdict("uncertain", None)[1]
    assert vetoed != unmeasured
    assert "0 recognised requirement terms" in vetoed
    assert "body never read" in unmeasured


# ---------------------------------------------------------------------------------------
# The ranker: the counter, the drain, the accounting identity, the fail-open.
# ---------------------------------------------------------------------------------------


def test_a_zero_signal_posting_is_vetoed_and_counted(env: Path) -> None:
    results = _rank(env, [
        ("Backend Engineer", MANY_SKILL_BODY),
        (UNCERTAIN_NOISE, ZERO_SKILL_BODY),
        (UNCERTAIN_NOISE_2, ZERO_SKILL_BODY),
    ])
    assert results.hidden_zero_signal == 2
    assert _titles(results) == ["Backend Engineer"]
    # Counted, never a silent drop: the identity has to hold with the bucket populated.
    assert _accounted(results) == results.considered == 3


def test_a_software_title_with_a_zero_skill_body_still_ships(env: Path) -> None:
    """The regression trap, on the real measured strings. Both of these have bodies that
    recognise nothing and would be deleted by an unconditional zero-skill veto. Scoping the
    rule to `uncertain` is what keeps them, and this is the test that fails if that is lost.
    """
    results = _rank(env, [
        (SWE_ZERO_SKILL, ZERO_SKILL_BODY),
        (SWE_ZERO_SKILL_2, ZERO_SKILL_BODY),
        (UNCERTAIN_NOISE, ZERO_SKILL_BODY),
    ])
    assert sorted(_titles(results)) == sorted([SWE_ZERO_SKILL, SWE_ZERO_SKILL_2])
    assert results.hidden_zero_signal == 1
    assert _accounted(results) == results.considered == 3


def test_an_uncertain_title_with_one_recognised_term_still_ships(env: Path) -> None:
    """Exactly zero, not one-or-fewer. This posting's entire body yield is one term."""
    results = _rank(env, [
        (UNCERTAIN_WITH_SIGNAL, ONE_SKILL_BODY),
        (UNCERTAIN_NOISE, ZERO_SKILL_BODY),
    ])
    assert _titles(results) == [UNCERTAIN_WITH_SIGNAL]
    assert results.hidden_zero_signal == 1


def test_a_posting_with_no_extraction_row_at_all_still_ships(env: Path) -> None:
    """The fail-open, built deliberately because the corpus cannot produce it.

    `rank_open_postings` calls `run_preflight`, which guarantees an extraction row at the
    current taxonomy version for every open posting — which is why 0 of 48,285 live postings
    lack one, and why a NULL outer-join row and an empty skill set are indistinguishable on
    real data. Suppressing the backfill is the only way to reach the state that a failed
    backfill or a taxonomy version rolling ahead of it would produce for real.

    The posting here is the WORST case for the rule: `uncertain` title, and a body that would
    recognise nothing even if it had been read. It must still ship, because "0 terms" is a
    claim the system has not earned. If the veto ever reads `(extraction or {})`, this fails.
    """
    engine = _seed(env, [
        ("Backend Engineer", MANY_SKILL_BODY),
        (UNCERTAIN_NOISE, ZERO_SKILL_BODY),
    ])
    import boardwatch.cli.top_cmd as top_cmd

    original = top_cmd.run_preflight
    try:
        top_cmd.run_preflight = lambda *args, **kwargs: None  # type: ignore[assignment]
        results = rank_open_postings(
            engine, _settings(env), limit=50, record_surfaced=False
        )
    finally:
        top_cmd.run_preflight = original  # type: ignore[assignment]

    assert results.hidden_zero_signal == 0, "an unread body must never be read as zero signal"
    assert UNCERTAIN_NOISE in _titles(results)
    # Visible AND counted: an inert gate has to be legible as a number, or `hidden_zero_signal
    # == 0` cannot be told apart from a clean corpus.
    assert results.signal_unmeasured == 1
    # `swe`-titled postings are not this rule's population and never reach the abstain.
    assert _accounted(results) == results.considered == 2


def test_the_unmeasured_abstain_is_not_a_drop(env: Path) -> None:
    """It counts postings that are IN `visible`. Folding it into the identity double-counts."""
    engine = _seed(env, [(UNCERTAIN_NOISE, ZERO_SKILL_BODY)])
    import boardwatch.cli.top_cmd as top_cmd

    original = top_cmd.run_preflight
    try:
        top_cmd.run_preflight = lambda *args, **kwargs: None  # type: ignore[assignment]
        results = rank_open_postings(engine, _settings(env), limit=50, record_surfaced=False)
    finally:
        top_cmd.run_preflight = original  # type: ignore[assignment]

    assert results.signal_unmeasured == 1
    assert len(results.visible) == 1
    assert _accounted(results) == results.considered == 1


def test_the_drain_restores_the_vetoed_postings(env: Path) -> None:
    """Every quarantine needs a re-entry path, shipped in the same change as the quarantine."""
    rows = [
        ("Backend Engineer", MANY_SKILL_BODY),
        (UNCERTAIN_NOISE, ZERO_SKILL_BODY),
        (UNCERTAIN_NOISE_2, ZERO_SKILL_BODY),
    ]
    closed = _rank(env, rows)
    assert closed.hidden_zero_signal == 2
    assert len(closed.visible) == 1


def test_a_drained_posting_names_what_triggered_it(env: Path) -> None:
    """A suppression you cannot read is a leak. The drained row carries the reason inline, so
    it can never be mistaken for an ordinary lead."""
    engine = _seed(env, [
        ("Backend Engineer", MANY_SKILL_BODY),
        (UNCERTAIN_NOISE, ZERO_SKILL_BODY),
    ])
    results = rank_open_postings(
        engine, _settings(env), limit=50, record_surfaced=False, include_zero_signal=True
    )
    assert results.hidden_zero_signal == 0
    assert sorted(_titles(results)) == sorted(["Backend Engineer", UNCERTAIN_NOISE])
    drained = next(p for p in results.visible if p.title == UNCERTAIN_NOISE)
    assert drained.zero_signal == "veto"
    assert "0 recognised requirement terms" in drained.zero_signal_reason
    # The identity holds in BOTH modes: with the drain open the row is in `visible` instead.
    assert _accounted(results) == results.considered == 2
    # A row that stayed visible on its own merits carries no annotation.
    kept = next(p for p in results.visible if p.title == "Backend Engineer")
    assert kept.zero_signal == "pass"
    assert kept.zero_signal_reason == ""


def test_looking_into_the_quarantine_does_not_consume_the_queue(env: Path) -> None:
    """The drain must be a re-entry path, not a one-way read: recording a drained row `seen`
    would suppress it from later runs, so the drain would close behind you (D-110)."""
    engine = _seed(env, [
        ("Backend Engineer", MANY_SKILL_BODY),
        (UNCERTAIN_NOISE, ZERO_SKILL_BODY),
    ])
    results = rank_open_postings(
        engine, _settings(env), limit=50, record_surfaced=False, include_zero_signal=True
    )
    drained = next(p for p in results.visible if p.title == UNCERTAIN_NOISE)
    kept = next(p for p in results.visible if p.title == "Backend Engineer")
    surfaced = set(results.surfaced_job_ids)
    assert surfaced, "the ordinary lead must still be surfaced, or this proves nothing"
    with engine.connect() as conn:
        from sqlalchemy import select

        anchors = {
            int(row.id): int(row.job_id)
            for row in conn.execute(select(postings.c.id, postings.c.job_id)).all()
        }
    assert anchors[kept.posting_id] in surfaced
    assert anchors[drained.posting_id] not in surfaced

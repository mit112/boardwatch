"""The ranker accounts for every posting it considered (P0 item 3).

Gate P0 requires *why every non-lead was dropped* to be answerable from the funnel artifact
alone. Before this, `rank_open_postings` reported only two of its **five** exits: postings
vetoed by the hard filters, postings narrowed away by `--new`, and postings that ranked below
the `--top` cutoff all simply vanished. On a real run that was **15,959 of 19,262 open
postings in no bucket at all** — 11,517 hard-filter vetoes and 4,442 below the cutoff.

The identity these tests pin is `considered == visible + every drop`. It is worth pinning
because it is the one arithmetic in the ranker that a future `continue` can silently break:
adding an early exit without a counter makes the funnel's shortlist stage stop reconciling,
which is exactly the signal Gate P0 is built on.

**What these tests CANNOT pin, stated so nobody assumes otherwise.** That `considered` is
`len(rows)` rather than the sum of the buckets is a **code-review invariant, not a tested
one.** Rewriting it as an exact sum is behaviourally identical on every valid input — the
loop's exits are exhaustive — so no test can distinguish the two, and a mutation review
confirmed the substitution survives the whole suite. It still matters: with `len(rows)`,
deleting any single counter is caught; with the sum, a missing counter is self-consistent and
invisible. The guard is structural, and this note is the only thing defending it.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import Engine, insert
from typer.testing import CliRunner

from boardwatch.cli.app import app
from boardwatch.cli.top_cmd import RankedResults, rank_open_postings
from boardwatch.core.clock import utcnow
from boardwatch.core.posting_identity import compute_identities
from boardwatch.core.settings import Settings
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.identity_queries import load_identity_inputs, write_identities
from boardwatch.store.ledger_queries import record_disposition
from boardwatch.store.queries import save_profile
from boardwatch.store.tables import companies, jobs, posting_versions, postings, runs

NOW = utcnow()

# Vetoed by the exclude-title substring rule, so it never reaches the role gate or the score.
EXCLUDED_TITLE = "Data Intern"
# The role gate reads this as non-software; it is counted, never a silent drop.
NON_SWE_TITLE = "Deal Strategist"


@pytest.fixture()
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    # Config dir == data dir so `_settings` below and the CLI invocations in the ineligible
    # test read the SAME facts and policy. With them split, `eligibility facts set` writes
    # somewhere the engine under test never looks.
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    return tmp_path / "data"


def _cli(data_dir: Path, args: list[str]) -> None:
    result = CliRunner().invoke(app, ["--data-dir", str(data_dir), *args])
    assert result.exit_code == 0, f"{args} failed: {result.stdout}"


def _seed(data_dir: Path, titles: list[str], *, bodies: list[str] | None = None) -> Engine:
    """One company, one open posting per title, distinct posted_at so ranking is total.

    `exclude_titles=["intern"]` is what makes EXCLUDED_TITLE a deterministic hard-filter
    rejection rather than a low score.
    """
    engine = get_engine(data_dir)
    ensure_schema(engine)
    with engine.begin() as conn:
        save_profile(
            conn, text="Backend engineer.", target_titles=[], exclude_titles=["intern"],
            locations=[], remote_only=False, skills=[], taxonomy_version="t",
            resume_max_pages=1,
        )
        company_id = int(conn.execute(insert(companies).values(
            name="Acme", provider="greenhouse", slug="acme-acct", source="user", watched=True,
        )).inserted_primary_key[0])
        for offset, title in enumerate(titles):
            body = bodies[offset] if bodies else "b"
            job_id = int(conn.execute(insert(jobs).values(created_at=NOW)).inserted_primary_key[0])
            posting_id = int(conn.execute(insert(postings).values(
                company_id=company_id, job_id=job_id, provider_posting_id=f"pp-{offset}",
                title=title, normalized_title=title.casefold(),
                locations_json=["Remote"], remote_policy="remote",
                # Descending recency, so `scored` has a strict order and "below the cutoff"
                # is a fact about a known posting rather than a tie broken arbitrarily.
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


def _rank(data_dir: Path, titles: list[str], *, limit: int) -> RankedResults:
    engine = _seed(data_dir, titles)
    return rank_open_postings(engine, _settings(data_dir), limit=limit)


def _accounted(results: RankedResults) -> int:
    """Everything the ranker says it did with the postings it looked at."""
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
        + results.hidden_slate_cap
    )


def test_every_considered_posting_lands_in_exactly_one_bucket(env: Path) -> None:
    """The whole point of item 3: no posting leaves the ranker uncounted."""
    results = _rank(
        env,
        ["Backend Engineer", "Platform Engineer", EXCLUDED_TITLE, NON_SWE_TITLE],
        limit=1,
    )
    assert results.considered == 4
    assert _accounted(results) == results.considered


def test_a_posting_below_the_top_cutoff_is_counted_rather_than_vanishing(env: Path) -> None:
    """The bucket that did not exist at all before item 3.

    Two software postings clear every filter and `limit=1`, so exactly one is shown and the
    other is below the cutoff. Asserted as its own number, not as a remainder: on a real run at
    --top 5 this population was 4,442 and the artifact could not name it.
    """
    results = _rank(env, ["Backend Engineer", "Platform Engineer"], limit=1)
    assert len(results.visible) == 1
    assert results.hidden_below_cutoff == 1
    assert results.considered == 2


def test_a_title_vetoed_by_the_hard_filters_is_counted(env: Path) -> None:
    """A hard-filter veto used to `continue` with no counter, so it left no trace anywhere."""
    results = _rank(env, ["Backend Engineer", EXCLUDED_TITLE], limit=10)
    assert results.hidden_hard_filter == 1
    assert [posting.title for posting in results.visible] == ["Backend Engineer"]


def test_the_role_gate_and_the_cutoff_are_kept_apart(env: Path) -> None:
    """Two different reasons a posting is not a lead must not collapse into one number."""
    results = _rank(env, ["Backend Engineer", "Platform Engineer", NON_SWE_TITLE], limit=1)
    assert results.hidden_non_swe == 1
    assert results.hidden_below_cutoff == 1


def test_raising_the_limit_moves_postings_out_of_the_cutoff_bucket(env: Path) -> None:
    """Pins the cutoff counter to the limit rather than to a fixed shape of the data.

    Without this, `hidden_below_cutoff` could be hard-coded to `considered - 1` and the test
    above would still pass.

    "Systems Engineer" is `uncertain` to the role gate and `_seed`'s default body ("b")
    recognises no taxonomy term, so the zero-signal veto now removes it BEFORE the cutoff and
    only two postings reach the limit. The expected counts therefore moved 2 -> 1 at `limit=1`;
    the property under test is unchanged and still discriminating, because `considered` is 3
    and the mutation this test exists to catch (`hidden_below_cutoff = considered - 1`) yields
    2 at `limit=1` and 2 at `limit=3`, disagreeing with both assertions. The third assertion
    pins WHERE the missing posting went, so a future change that loses it silently — rather
    than moving it to a named bucket — fails here instead of passing quietly.
    """
    engine = _seed(env, ["Backend Engineer", "Platform Engineer", "Systems Engineer"])
    settings = _settings(env)
    # Same three postings both times, so only `limit` differs between the two counts.
    # `record_surfaced=False` is what keeps that comment TRUE: while the ranker consumed the queue
    # on every call, the second call's `hidden_below_cutoff == 0` held because the third posting was
    # hidden as already-handled, not because the limit rose — so the mutation this test exists to
    # catch (hard-coding the counter) would have survived it.
    capped = rank_open_postings(engine, settings, limit=1, record_surfaced=False)
    assert capped.hidden_below_cutoff == 1
    assert rank_open_postings(
        engine, settings, limit=3, record_surfaced=False
    ).hidden_below_cutoff == 0
    assert capped.hidden_zero_signal == 1
    assert _accounted(capped) == capped.considered == 3


def test_postings_narrowed_away_by_only_new_are_counted(env: Path) -> None:
    """`--new` narrows the candidate set; the postings it removes are still accounted for.

    No caller in the pipeline passes `only_new`, but the identity above must hold for every
    caller or it is not an identity — and `top --new` is a real one.
    """
    engine = _seed(env, ["Backend Engineer", "Platform Engineer"])
    results = rank_open_postings(engine, _settings(env), limit=10, only_new=True)
    # No posting carries a `new` event past the cursor here, so all of them are narrowed out.
    assert results.skipped_not_new == 2
    assert results.visible == []
    assert _accounted(results) == results.considered == 2


# The only body text that makes the degree rule fire, so one posting persists as ineligible.
DEGREE_BODY = "We are hiring a backend engineer. A Bachelor's degree is required."


def test_a_posting_hidden_as_ineligible_is_not_also_counted_as_capped(env: Path) -> None:
    """`hidden_ineligible` was 0 in every fixture, which left two real regressions invisible.

    A mutation-based review found that with no fixture exercising this bucket, the whole
    `capped_by_top_n` counter could be replaced by `len(scored) - len(visible)` — a remainder —
    and the suite stayed green, silently folding hidden-ineligible postings into the cutoff
    bucket. Deleting the `continue` that skips an ineligible posting also survived here.

    `limit=10` with two postings means nothing can be capped, so the second assertion is the
    load-bearing one: an ineligible posting must land in exactly ONE bucket.
    """
    _seed(env, ["Backend Engineer", "Platform Engineer"], bodies=[DEGREE_BODY, "b"])
    _cli(env, ["eligibility", "facts", "set", "highest_degree", "none"])
    _cli(env, ["eligibility", "policy", "set", "degree", "blocker"])
    _cli(env, ["eligibility", "run"])

    results = rank_open_postings(get_engine(env), _settings(env), limit=10)

    assert results.hidden_ineligible == 1
    assert results.hidden_below_cutoff == 0, "an ineligible posting was also counted as capped"
    assert [posting.title for posting in results.visible] == ["Platform Engineer"]
    assert _accounted(results) == results.considered == 2


# --------------------------------------------------------------------------------------
# B5 — run-scoped twins of the suppression drops
# --------------------------------------------------------------------------------------


def _company(engine: Engine, slug: str) -> int:
    with engine.begin() as conn:
        return int(
            conn.execute(
                insert(companies).values(
                    name="Acme", provider="greenhouse", slug=slug, source="user", watched=True,
                )
            ).inserted_primary_key[0]
        )


def _posting_with_job(
    engine: Engine, company_id: int, *, tag: str, content_hash: str, offset: int
) -> tuple[int, int]:
    """One posting on its own job, distinct posted_at so ranking is total."""
    with engine.begin() as conn:
        job_id = int(conn.execute(insert(jobs).values(created_at=NOW)).inserted_primary_key[0])
        posting_id = int(
            conn.execute(
                insert(postings).values(
                    company_id=company_id, job_id=job_id, provider_posting_id=f"pp-{tag}",
                    title="Backend Engineer", normalized_title="backend engineer",
                    locations_json=["Remote"], remote_policy="remote",
                    posted_at=NOW - timedelta(days=offset), first_seen_at=NOW, last_seen_at=NOW,
                    status="open", consecutive_missing=0, content_hash=content_hash,
                    body_text="We are hiring a backend engineer.",
                )
            ).inserted_primary_key[0]
        )
        conn.execute(
            insert(posting_versions).values(
                posting_id=posting_id, content_hash=content_hash,
                body_text="We are hiring a backend engineer.",
                captured_at=NOW, capture_reason="new",
            )
        )
    return posting_id, job_id


def _backfill_all_identities(engine: Engine) -> None:
    """Every open posting must carry an identity for `identities_complete` to gate dedup on."""
    with engine.begin() as conn:
        for row in load_identity_inputs(conn, None):
            write_identities(conn, row.posting_id, compute_identities(row), now=NOW)


def _run_row(engine: Engine) -> int:
    with engine.begin() as conn:
        return int(
            conn.execute(
                insert(runs).values(started_at=NOW, boards_attempted=0)
            ).inserted_primary_key[0]
        )


def test_rank_twins_count_only_this_run_suppressions(env: Path) -> None:
    """Run-scoped twins count ONLY postings THIS run judged, restricted to the suppression
    drops that make an empty day honest — a prior-run posting's suppression must not bleed
    into this run's twins even though the corpus counter sees it."""
    engine = get_engine(env)
    ensure_schema(engine)
    with engine.begin() as conn:
        save_profile(
            conn, text="Backend engineer.", target_titles=[], exclude_titles=[],
            locations=[], remote_only=False, skills=[], taxonomy_version="t",
            resume_max_pages=1,
        )
    company_id = _company(engine, "acme-twins")
    settings = _settings(env)

    # P3: judged by a prior run, gets a live `built` disposition.
    p3, j3 = _posting_with_job(engine, company_id, tag="p3", content_hash="hh-p3", offset=0)
    _backfill_all_identities(engine)
    run_prior = _run_row(engine)
    rank_open_postings(engine, settings, run_id=run_prior, record_surfaced=False, limit=10)
    with engine.begin() as conn:
        record_disposition(
            conn, j3, disposition="built", reason="lead_built", policy_version="v1",
            now=NOW, run_id=run_prior,
        )

    # P1: judged by THIS run, gets a live `built` disposition this run.
    p1, j1 = _posting_with_job(engine, company_id, tag="p1", content_hash="hh-p1", offset=1)
    # P2a/P2b: an exact_quad duplicate pair, both judged by THIS run.
    p2a, _j2a = _posting_with_job(engine, company_id, tag="p2a", content_hash="hh-p2", offset=2)
    p2b, _j2b = _posting_with_job(engine, company_id, tag="p2b", content_hash="hh-p2", offset=3)
    _backfill_all_identities(engine)

    run_this = _run_row(engine)
    with engine.begin() as conn:
        record_disposition(
            conn, j1, disposition="built", reason="lead_built", policy_version="v1",
            now=NOW, run_id=run_this,
        )

    ranked = rank_open_postings(engine, settings, run_id=run_this, record_surfaced=False, limit=10)

    assert ranked.judged_this_run_ids == {p1, p2a, p2b}
    assert ranked.hidden_handled_this_run == 1  # P1 only; P3 is prior-run
    assert ranked.hidden_duplicate_this_run == 1  # one of the P2 pair
    assert ranked.hidden_applied_this_run == 0
    # Corpus counters still see all of it:
    assert ranked.hidden_handled == 2  # P1 + P3
    assert p1 in ranked.judged_this_run_ids
    assert p3 not in ranked.judged_this_run_ids

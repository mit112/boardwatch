"""The funnel's `death_probe` section (D-325) — the pure half.

A detector that quietly stops firing must show up as a number that moved, not as silence, and
this one has an unusual amount of room to stop firing: its measured sensitivity is 6.7% (4 of 60
postings the scanner had PROVED closed; workday 0 of 37), so `closed: 0` is the EXPECTED reading
and is nearly worthless as evidence about the corpus. Every other bucket exists to tell a reader
which of the many zeros they are looking at — a budget that refused everything, a due set with
no URLs, a redirect rule swallowing every gone-status, a drain that never fires.

`artifact_version` is left ALONE (8 since T60, 9 since T204). Asserted here as well as at the four sites that pin it,
so the additive-key ruling is visible from the change that relies on it.

T89 added the ATS list-API half and holds the version there too, on **D-498's** ruling rather
than D-285's: `due`/`attempted`/`gone`/`alive` count exactly what they always counted — what the
URL probe asked and heard — and what is new is a REASON `due` can be smaller, published as its
own set of keys in the same section rather than folded into a neighbour. The reconciliation
identities a consumer checks still add up from keys it can read: `due = attempted +
budget_refused`, `companies_due = companies_attempted + companies_refused`, and
`closed = closed_by_url + closed_by_listing`.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from boardwatch.eligibility.catalog import load_rules
from boardwatch.reports.abstain import build_abstain_report
from boardwatch.reports.run_funnel import (
    ARTIFACT_VERSION,
    DEATH_PROBE_COST_ROWS,
    DeathProbeCost,
    DeathProbeReport,
    RunFunnel,
    RunManifest,
    ScanContext,
    build_run_funnel,
    funnel_to_dict,
    funnel_to_markdown,
)
from boardwatch.store.run_funnel_queries import CorpusCounts, TailoredArtifactCounts


def _funnel(death_probe: DeathProbeReport | None = None) -> RunFunnel:
    """The smallest funnel that renders, with only the death-probe section varying."""
    return build_run_funnel(
        run_id=1,
        started_at=None,
        finished_at=None,
        manifest=RunManifest(
            code_fingerprint="f",
            config_hash="c",
            profile_facts_hash=None,
            profile_row_hash=None,
            rules_hash=None,
            status="ok",
            # Required since D-323 bumped the artifact to v7. `soft` is the default, and this
            # section has nothing to do with the location gate — it is supplied so the helper
            # constructs, not because the value matters here.
            location_filter_mode="soft",
        ),
        scan=ScanContext(ran=False),
        corpus=CorpusCounts(
            open_postings=0,
            evaluated=0,
            no_current_evaluation=0,
            by_verdict={},
            judged_this_run=0,
            cache_hit_prior_run=0,
            cache_hit_unattributed=0,
        ),
        shortlist=None,
        sources=(),
        leads=(),
        tailor_failed=0,
        tailored_artifacts=TailoredArtifactCounts(rows=0, with_pdf=0),
        marked_applied=0,
        stub_postings=0,
        rewrite_rows=(),
        unattributed_evaluations=0,
        abstain=build_abstain_report(
            # No override dir: `load_rules` falls back to the bundled catalog.
            load_rules(Path("does-not-exist")), {}, not_applicable_families=frozenset()
        ),
        death_probe=death_probe,
    )


def _sample() -> DeathProbeReport:
    return DeathProbeReport(
        due=12,
        unprobeable=2,
        attempted=5,
        budget_refused=7,
        gone=3,
        unknown=1,
        alive=1,
        closed_by_url=2,
        closed_by_listing=4,
        strikes_cleared=1,
        companies_due=9,
        companies_attempted=6,
        companies_refused=3,
        listing_absent=8,
        listing_present=13,
        listing_unknown=2,
    )


def test_every_probe_bucket_reaches_the_artifact() -> None:
    payload = funnel_to_dict(_funnel(_sample()))["death_probe"]

    assert payload == {
        "instrumented": True,
        "due": 12,
        "unprobeable": 2,
        "attempted": 5,
        "budget_refused": 7,
        "gone": 3,
        "unknown": 1,
        "alive": 1,
        "closed": 6,
        "closed_by_url": 2,
        "closed_by_listing": 4,
        "strikes_cleared": 1,
        "companies_due": 9,
        "companies_attempted": 6,
        "companies_refused": 3,
        "listing_absent": 8,
        "listing_present": 13,
        "listing_unknown": 2,
        "linkedin_guest": None,
        "guard_boards": 0,
        "guard_rows": 0,
        "guard_rows_unjudgeable": 0,
        "guard_attempted": 0,
        "guard_closed": 0,
        "cost": None,
    }


def _guarded_sample() -> DeathProbeReport:
    return DeathProbeReport(
        due=12, unprobeable=2, attempted=5, budget_refused=7, gone=3, unknown=1, alive=1,
        closed_by_url=2, closed_by_listing=4, strikes_cleared=1, companies_due=9,
        companies_attempted=6, companies_refused=3, listing_absent=8, listing_present=13,
        listing_unknown=2,
        guard_boards=6, guard_rows=127, guard_rows_unjudgeable=80, guard_attempted=100,
        guard_closed=9,
    )


def test_the_guard_drain_counts_reach_the_artifact_and_the_markdown() -> None:
    """T334 (D-705): the drain is observable. The five counts ride the existing `death_probe`
    block, and the markdown line appears only once a board is past the threshold."""
    payload = funnel_to_dict(_funnel(_guarded_sample()))["death_probe"]
    assert isinstance(payload, dict)
    assert {k: v for k, v in payload.items() if k.startswith("guard_")} == {
        "guard_boards": 6, "guard_rows": 127, "guard_rows_unjudgeable": 80,
        "guard_attempted": 100, "guard_closed": 9,
    }

    rendered = funnel_to_markdown(_funnel(_guarded_sample()))
    assert "guard drain: 6 watched board(s)" in rendered
    assert "127 open rows handed to the URL probe (100 asked this run, 9 closed)" in rendered
    assert "80 rows on Ashby or Greenhouse stay open" in rendered
    # Nothing handed over, nothing printed: the healthy-run case is not a line to learn to ignore.
    assert "guard drain:" not in funnel_to_markdown(_funnel(_sample()))


def test_an_unswept_run_reports_UNMEASURED_rather_than_zero() -> None:  # noqa: N802
    """The D-022/D-023 rule. `closed: 0` from a run that never swept asserts a measurement
    nobody took, and would read as "the class is healthy" from the same JSON a genuinely clean
    sweep produces. `instrumented` is emitted so a reader never has to infer it from a null."""
    payload = funnel_to_dict(_funnel())["death_probe"]

    assert payload == {
        "instrumented": False,
        "due": None,
        "unprobeable": None,
        "attempted": None,
        "budget_refused": None,
        "gone": None,
        "unknown": None,
        "alive": None,
        "closed": None,
        "closed_by_url": None,
        "closed_by_listing": None,
        "strikes_cleared": None,
        "companies_due": None,
        "companies_attempted": None,
        "companies_refused": None,
        "listing_absent": None,
        "listing_present": None,
        "listing_unknown": None,
        "linkedin_guest": None,
        "guard_boards": None,
        "guard_rows": None,
        "guard_rows_unjudgeable": None,
        "guard_attempted": None,
        "guard_closed": None,
        "cost": None,
    }


def test_the_markdown_names_the_measured_sensitivity() -> None:
    """The number this whole section has to be read against. Ship it without, and `closed: 0`
    gets trusted as evidence about the corpus rather than about the probe."""
    rendered = funnel_to_markdown(_funnel(_sample()))

    assert "## Death probe" in rendered
    assert "6.7%" in rendered
    assert "5 of 12 due probed" in rendered
    assert "7 refused by the budget" in rendered
    # T89's half, and the number it has to be read against: the URL probe is not merely
    # insensitive on these providers, it answers `alive` for a posting that is dead.
    assert "6 of 9 due companies asked" in rendered
    assert "3 refused by the company budget" in rendered
    assert "8 rows absent" in rendered
    assert "2 closed by URL" in rendered
    assert "4 closed by listing" in rendered
    assert "12.6%" in rendered


def test_the_markdown_says_UNMEASURED_when_the_sweep_did_not_run() -> None:  # noqa: N802
    rendered = funnel_to_markdown(_funnel())

    assert "not instrumented" in rendered
    assert "NOT the same as nothing having died" in rendered


def test_the_artifact_version_does_not_move_for_the_death_probe_section() -> None:
    """An ADDITIVE top-level key on the D-113 -> D-285 precedent: it does not move the version.

    v5 bumped because an existing value CHANGED MEANING (`tailor.entered` stopped being the
    ranker's `shortlisted`); v6 bumped because `board_coverage` supplied a denominator the
    `scan` block had been read without; **v7 bumped for D-323's lead locations, which landed
    while this branch was open.** `death_probe` does none of those — `liveness` still counts the
    shortlist probe, and every stage's `entered`/`advanced` is untouched. The `lanes` key settled
    the identical question the identical way. Asserted from both directions, because a bump made
    in the constant alone would still change every artifact a consumer reads.

    The literal tracks whatever `main` currently declares; what this test defends is that adding
    `death_probe` leaves it ALONE. It caught exactly that on rebase: the pin said 6, D-323 had
    moved main to 7, and a textual merge could not see the disagreement.
    """
    assert ARTIFACT_VERSION == 9
    assert funnel_to_dict(_funnel())["artifact_version"] == 9
    assert funnel_to_dict(_funnel(_sample()))["artifact_version"] == 9


def test_closed_is_the_sum_of_the_two_halves_by_construction(tmp_path: object) -> None:
    """`closed` is the key every reader that predates T89's split already reads, so it must keep
    answering "how many did the sweep retire?". A PROPERTY rather than a third field: a stored
    total is a third number that can disagree with the two it summarises, and a report whose
    halves do not add up would make a close unattributable — the same defect D-325 gave
    `death_strikes` its own column to avoid."""
    report = _sample()

    assert report.closed == report.closed_by_url + report.closed_by_listing == 6
    payload = funnel_to_dict(_funnel(report))["death_probe"]
    assert isinstance(payload, dict)
    assert payload["closed"] == payload["closed_by_url"] + payload["closed_by_listing"]
    # And it cannot be set independently: there is no `closed` field to pass.
    assert "closed" not in DeathProbeReport.__dataclass_fields__


def _cost(
    kind: str, host: str, seconds: float, *, asked: int = 1, closed: int = 0
) -> DeathProbeCost:
    return DeathProbeCost(
        kind=kind, host=host, asked=asked, seconds=seconds, gone=closed, alive=asked - closed,
        unknown=0, closed=closed,
    )


def test_the_probe_cost_keeps_the_costliest_hosts_and_sums_the_rest_so_it_reconciles() -> None:
    """T344. The artifact keeps DEATH_PROBE_COST_ROWS hosts, costliest first; the rest are summed
    into `other`, so rows + other == the totals == by_kind, and a close on a cheap host is not
    lost from the table's sums."""
    cheap = [_cost("url", f"h{i:02d}.example", 1.0 + i) for i in range(DEATH_PROBE_COST_ROWS)]
    rest = [
        _cost("url", "tail-a.example", 0.5, closed=1),
        _cost("linkedin_guest", "www.linkedin.com", 0.25, asked=3),
    ]
    big = _cost("listing", "ashby", 99.0, asked=2, closed=2)
    report = replace(_sample(), cost=(*cheap, *rest, big))

    payload = funnel_to_dict(_funnel(report))["death_probe"]
    assert isinstance(payload, dict)
    cost = payload["cost"]
    assert cost["hosts"] == DEATH_PROBE_COST_ROWS + 3
    assert [r["host"] for r in cost["rows"]][:2] == ["ashby", "h19.example"]
    assert len(cost["rows"]) == DEATH_PROBE_COST_ROWS
    # Shown: `ashby` and h19..h01. Outside the cut: h00 (1.0 s), tail-a (0.5 s, the close) and
    # LinkedIn (0.25 s, 3 asked).
    assert cost["other"] == {
        "asked": 1 + 1 + 3, "gone": 1, "alive": 1 + 0 + 3, "unknown": 0, "closed": 1,
        "seconds": 1.75,
    }
    every = (*cheap, *rest, big)
    shown_asked = sum(r["asked"] for r in cost["rows"])
    assert cost["asked"] == sum(r.asked for r in every) == shown_asked + cost["other"]["asked"]
    assert cost["closed"] == 3
    assert {k["kind"]: (k["asked"], k["closed"]) for k in cost["by_kind"]} == {
        "linkedin_guest": (3, 0), "listing": (2, 2), "url": (DEATH_PROBE_COST_ROWS + 1, 1),
    }

    rendered = funnel_to_markdown(_funnel(report))
    assert "- `listing`: 2 asked in 99.0 s (49.50 s each) · 2 gone · 2 closed" in rendered
    assert "| listing | `ashby` | 2 | 99.0 | 2 | 0 | 0 | 2 |" in rendered


def test_a_sweep_that_did_not_time_its_probes_says_so() -> None:
    assert funnel_to_dict(_funnel(_sample()))["death_probe"]["cost"] is None  # type: ignore[index]
    assert "probe cost: **not measured** this run." in funnel_to_markdown(_funnel(_sample()))

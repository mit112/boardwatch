"""Every ranker drop bucket must reach every mirror site (D-246).

`top_cmd.py`'s own docstring has claimed the mirror-site count is 3, then 4, then 6, then 21 —
wrong every time, and the real floor is at least 27. The reason it keeps being wrong is that
`Drop.reason` is a bare `str`: there is no closed catalog, so nothing refuses a bucket that was
added to the ranker and forgotten downstream. The stage `reconciled` identity catches a missing
`Drop`, but only at runtime and only on a run where that bucket is non-zero — and the fixtures
that exercise the pipeline leave `target_seniority_band` at the inert default, so a dropped
mapping line for `hidden_over_seniority` would have passed silently.

These tests replace the hand-maintained checklist with an enforced invariant, so the NEXT bucket
is covered without anyone remembering to walk the list.
"""

from __future__ import annotations

import dataclasses
import inspect

from boardwatch.cli import run_cmd, top_cmd
from boardwatch.pipeline import runner
from boardwatch.reports import run_funnel
from boardwatch.reports.run_funnel import ShortlistCounts

# Buckets the ranker owns. Derived from the dataclass, never restated, so a new field is
# picked up automatically instead of needing this list edited.
#
# `_this_run` fields are excluded on purpose (B5): they are run-scoped TWINS of four of the
# buckets above, diagnostics for the zero-output guard, and are deliberately NOT part of the
# `considered == Σ drops` reconciliation identity — so they must not be swept into the mirror-
# site walk that identity's buckets are held to.
RANKER_BUCKETS = frozenset(
    f.name
    for f in dataclasses.fields(top_cmd.RankedResults)
    if f.name.startswith("hidden_") and not f.name.endswith("_this_run")
)

# `_shortlist_line` is the operator's one-line summary and deliberately does NOT name every
# bucket -- it omits the ones that are scoping choices rather than rejections the operator would
# act on. Exempting them explicitly keeps the check honest: anything else added here is a
# decision someone had to write down.
#
# `hidden_hard_filter` LEFT this set when its drain shipped. The exemption was defensible only
# while the bucket was un-inspectable; a 59%-of-corpus cut that the operator can now list with
# `top --include-hard-filter` has to appear in the line that reports the day.
SUMMARY_LINE_EXEMPT = frozenset({"hidden_below_cutoff"})

# The funnel names one drop for what it IS rather than for the counter that feeds it. That
# divergence is exactly what makes the mirror-site walk error-prone, so it is recorded here
# explicitly instead of being papered over by a looser assertion.
DROP_REASON_ALIASES = {"hidden_below_cutoff": "capped_by_top_n"}


def test_the_ranker_owns_at_least_the_buckets_we_know_about() -> None:
    """Guards against the derivation above silently matching nothing."""
    assert {"hidden_non_swe", "hidden_over_seniority", "hidden_duplicate"} <= RANKER_BUCKETS
    assert len(RANKER_BUCKETS) >= 8


def test_every_ranker_bucket_is_a_shortlist_counts_field() -> None:
    fields = {f.name for f in dataclasses.fields(ShortlistCounts)}
    missing = RANKER_BUCKETS - fields
    assert not missing, f"buckets missing from ShortlistCounts: {sorted(missing)}"


def test_every_ranker_bucket_is_mapped_by_the_pipeline() -> None:
    """A missing mapping line is caught by nothing until a run has a non-zero count."""
    source = inspect.getsource(runner)
    missing = [b for b in sorted(RANKER_BUCKETS) if f"{b}=" not in source]
    assert not missing, f"buckets not mapped into ShortlistCounts in runner.py: {missing}"


def test_every_ranker_bucket_has_a_funnel_drop() -> None:
    """Without a Drop the shortlist stage stops reconciling -- but only at runtime."""
    source = inspect.getsource(run_funnel)
    missing = [
        b
        for b in sorted(RANKER_BUCKETS)
        if f'reason="{DROP_REASON_ALIASES.get(b, b)}"' not in source
    ]
    assert not missing, f"buckets with no Drop in the shortlist stage: {missing}"


def test_every_non_exempt_bucket_is_named_in_the_operator_summary() -> None:
    """Nothing statically catches a miss here; this test is the only guard."""
    source = inspect.getsource(run_cmd)
    expected = RANKER_BUCKETS - SUMMARY_LINE_EXEMPT
    missing = [b for b in sorted(expected) if b not in source]
    assert not missing, f"buckets absent from _shortlist_line: {missing}"


def test_reported_counters_are_not_drops() -> None:
    """An abstain counts postings that PASSED. As a Drop it would double-subtract and the
    shortlist stage would stop reconciling on every run that had one."""
    source = inspect.getsource(run_funnel)
    for reported in ("uncertain_band", "band_tokens_seen_while_inert"):
        assert hasattr(ShortlistCounts(considered=0, shortlisted=0), reported)
        assert f'reason="{reported}"' not in source, (
            f"{reported} counts postings that passed; it must not be a Drop"
        )

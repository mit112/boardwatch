"""`LaneContext` — the registration surface a concurrent lane build no longer has to edit.

The wart this replaces was real and named in `runner.py`'s own comment: `LaneFactory` was
`Callable[..., Lane]`, so `mypy --strict` checked no call site at all, and `_run_lanes` carried
`if name == LinkedInLane.name:` to hand that one factory a keyword nothing else took. Every lane
needing a per-run value the previous ones did not would add a keyword to one signature and a
branch beside it.

The guard below is deliberately over the REAL registry rather than a stub. A stub would pass on
the exact implementation this exists to forbid: a registry whose rows disagree about their
signature is only observable when every row is called the same way.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from boardwatch.core.settings import Settings
from boardwatch.lanes.base import LaneContext, _no_seeds
from boardwatch.lanes.facets import LaneFacets
from boardwatch.pipeline.runner import LANE_FACTORIES


def _ctx(tmp_path: Path, **kwargs: object) -> LaneContext:
    return LaneContext(
        settings=Settings(data_dir=tmp_path, config_dir=tmp_path, **kwargs),  # type: ignore[arg-type]
        facets=LaneFacets(profile=("software engineer",)),
        rotation_index=3,
    )


def test_every_registered_lane_is_built_from_one_context_and_nothing_else(
    tmp_path: Path,
) -> None:
    """The branch-free property, asserted over the real registry.

    `_run_lanes` calls `factory(context)` for every name with no special case, so a row that
    needs anything else raises `TypeError` inside the per-lane `except` — where it is reported as
    "collection failed" and the lane is silently absent from the run, which reads exactly like an
    aggregator that was down.
    """
    ctx = _ctx(tmp_path, jobapps_discovery_dir=tmp_path)

    built = {name: factory(ctx) for name, factory in LANE_FACTORIES.items()}

    assert set(built) == set(LANE_FACTORIES)
    for name, lane in built.items():
        # `Lane` is a Protocol and deliberately not `@runtime_checkable`, so the contract is
        # asserted directly: the one method `_fetch_lane` calls, and the name the registry keys.
        assert callable(getattr(lane, "collect", None)), name
        assert lane.name == name, "a factory must build the lane its registry key names"


def test_the_context_refuses_field_rebinding(tmp_path: Path) -> None:
    """One context is built per STAGE and handed to every factory, so a factory that rebound a
    field would configure the lanes after it by registry ORDER.

    **This is a claim about REBINDING and nothing more, and the narrower wording is deliberate.**
    An earlier version of this test was titled "one lane cannot retune the next" and that claim
    is FALSE: `Settings` is a pydantic model whose container fields are mutable, so a factory can
    still reach into `ctx.settings.lane_new_companies_per_run_overrides` and insert a value a
    later lane's `_lane_company_cap` reads. Nothing does, and closing it means handing out a
    deep-frozen settings snapshot — a real change with its own cost. What must not stand is a
    green test asserting a protection that is not there.
    """
    ctx = _ctx(tmp_path)

    with pytest.raises((AttributeError, TypeError)):
        ctx.rotation_index = 99  # type: ignore[misc]


def test_a_lane_that_resolves_no_seeds_is_handed_the_empty_reader(tmp_path: Path) -> None:
    """Three of the four registered lanes read no seeds, so the default has to be inert.

    EMPTY rather than raising: a lane is additive breadth, and a resolver handed no backlog must
    report that it found nothing rather than fail the run.
    """
    ctx = LaneContext(
        settings=Settings(data_dir=tmp_path, config_dir=tmp_path),
        facets=LaneFacets(),
        rotation_index=0,
    )

    assert ctx.pending_seeds is _no_seeds
    assert ctx.pending_seeds(hosts=frozenset({"x.test"}), max_attempts=9, limit=9) == ()


def test_the_rotation_index_reaches_the_linkedin_factory_through_the_context(
    tmp_path: Path,
) -> None:
    """The value the deleted `if name == ...` branch used to carry.

    Pinned as a LITERAL slice rather than by recomputing `hub_nets` with the same index, which
    would assert the implementation against itself.
    """
    ctx = LaneContext(
        settings=Settings(
            data_dir=tmp_path,
            config_dir=tmp_path,
            lane_search_hubs=("Austin, TX", "Boston, MA", "Seattle, WA"),
            lane_hub_combos_per_run=1,
        ),
        facets=LaneFacets(profile=("software engineer",)),
        rotation_index=2,
    )

    built = LANE_FACTORIES["linkedin"](ctx)

    assert built._search_nets == (("software engineer", "Seattle, WA"),)

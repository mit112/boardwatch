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
from boardwatch.lanes.base import LaneContext
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


def test_the_context_is_frozen_so_one_lane_cannot_retune_the_next(tmp_path: Path) -> None:
    """One context is built per STAGE and handed to every factory.

    Mutable, a lane's factory could rewrite the settings the lanes after it are built from, and
    the resulting run would be configured by registry ORDER — reproducible, plausible, and
    impossible to read off any artifact.
    """
    ctx = _ctx(tmp_path)

    with pytest.raises((AttributeError, TypeError)):
        ctx.rotation_index = 99  # type: ignore[misc]


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

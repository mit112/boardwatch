"""Pytest wiring for deterministic test sharding. The logic lives in `tools/shard.py`.

This file exists at the repository root rather than under `tests/` because `pytest_addoption`
is only honoured in an INITIAL conftest, and the rootdir conftest is always one.

`trylast=True` matters. It puts this hook AFTER pytest's own marker deselection, so the
partition covers the ELIGIBLE collection (what `-m 'not perf'` leaves) rather than the raw
one. Sharding before deselection would let perf tests distort shard sizes without ever
running.

The manifest is what makes the split verifiable rather than merely plausible — see
`tools/shard_audit.py`. A unit test of the splitter alone would still pass if this hook were
never registered, if the option were parsed and ignored, or if two shard jobs collected
different tests. The audit compares independently-produced manifests across jobs instead.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from tools.shard import ShardSpecError, owns, parse_shard, write_manifest

if TYPE_CHECKING:
    from _pytest.config import Config
    from _pytest.config.argparsing import Parser


def pytest_addoption(parser: Parser) -> None:
    group = parser.getgroup("sharding")
    group.addoption(
        "--shard",
        default="1/1",
        metavar="INDEX/TOTAL",
        help="Run only shard INDEX of TOTAL (1-based). Default 1/1 runs everything.",
    )
    group.addoption(
        "--shard-manifest",
        default=None,
        metavar="PATH",
        help="Write this shard's collection manifest to PATH, for tools.shard_audit.",
    )


def _writes_manifest(session: pytest.Session) -> bool:
    """Elect exactly one process to write the manifest.

    The xdist CONTROLLER does not run `pytest_collection_modifyitems` at all — the workers
    collect and the controller compares their results. So a "controller only" guard writes
    nothing under `-n auto`. Electing the first worker is what actually produces one file,
    and it reflects the run that really happened rather than a separate collection pass.

    `get_xdist_worker_id` wants a request or session — something carrying `.config` — not a
    `Config`. Handing it the `Config` raises `AttributeError: 'Config' object has no attribute
    'config'` inside pytest's own hook wrapper, which surfaces as an INTERNALERROR rather than
    a normal failure.
    """
    try:
        from xdist import get_xdist_worker_id
    except ImportError:  # pragma: no cover - xdist is a hard dependency of the gate
        return True
    return bool(get_xdist_worker_id(session) in {"master", "gw0"})


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(
    session: pytest.Session, config: Config, items: list[pytest.Item]
) -> None:
    try:
        index, total = parse_shard(str(config.getoption("--shard")))
    except ShardSpecError as exc:
        raise pytest.UsageError(str(exc)) from None

    full = [item.nodeid for item in items]
    kept = [item for item in items if owns(item.nodeid, index, total)]

    manifest = config.getoption("--shard-manifest")
    if manifest and _writes_manifest(session):
        write_manifest(Path(str(manifest)), full, [item.nodeid for item in kept], total)

    if total > 1:
        items[:] = kept

"""D-669: only a typed board-level dead response can count toward a dead-board streak."""

from pathlib import Path

import pytest
import respx

from boardwatch.core.models import BoardRequest
from boardwatch.core.politeness import Fetcher
from boardwatch.core.settings import Settings
from boardwatch.providers.registry import build_providers


@pytest.mark.parametrize("name,slug", [
    ("greenhouse", "acme"), ("lever", "acme"), ("ashby", "acme"),
    ("workable", "acme"), ("smartrecruiters", "acme"),
    ("workday", "acme.wd1.myworkdayjobs.com/acme/External"),
    ("eightfold", "acme.eightfold.ai"),
])
@pytest.mark.usefixtures("no_real_sleep")
def test_board_404_carries_a_dead_signal(name: str, slug: str, tmp_path: Path) -> None:
    provider = build_providers()[name]
    settings = Settings(data_dir=tmp_path / "data", config_dir=tmp_path / "cfg", retry_attempts=1)
    url = provider.board_url(slug)
    with respx.mock as routes:
        routes.route().respond(404)
        snapshot = provider.fetch_board(Fetcher(settings), BoardRequest(provider=name, slug=slug, url=url))
    assert snapshot.status == "failed"
    assert snapshot.dead is True

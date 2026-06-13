"""Subprocess probe for the Ashby huge-board memory ceiling (D26). Drives the full
fetch_board path with a fixture-backed Fetcher and prints a JSON report on stdout.
Run as: python -m tests.contract._ashby_huge_probe <fixture>."""

import json
import sys
import tracemalloc
from pathlib import Path

from boardwatch.core.models import BoardRequest
from boardwatch.core.politeness import FetchResult
from boardwatch.providers.ashby import AshbyProvider


class _FixtureFetcher:
    """Minimal Fetcher stand-in: reads the fixture bytes lazily, inside the window."""

    def __init__(self, fixture: Path) -> None:
        self._fixture = fixture

    def get(self, url: str, validators=None) -> FetchResult:
        content = self._fixture.read_bytes()  # read/decode happens INSIDE tracemalloc
        return FetchResult(200, content, False, None)


def main(fixture: Path) -> None:
    provider = AshbyProvider()
    url = provider.board_url("acme")
    request = BoardRequest(provider="ashby", slug="acme", url=url)
    tracemalloc.start()  # window opens before any read/decode
    snapshot = provider.fetch_board(_FixtureFetcher(fixture), request)  # complete path
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    print(json.dumps({"status": snapshot.status, "postings": len(snapshot.postings),
                      "peak_bytes": peak}))


if __name__ == "__main__":
    main(Path(sys.argv[1]))

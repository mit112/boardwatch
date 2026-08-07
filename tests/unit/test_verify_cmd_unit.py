from pathlib import Path

from boardwatch.cli.verify_cmd import _run_id_from_name


def test_run_id_from_name_parses_valid_filename() -> None:
    assert _run_id_from_name(Path("funnel-7.json")) == 7
    assert _run_id_from_name(Path("funnel-70.json")) == 70


def test_run_id_from_name_returns_none_for_malformed_filename() -> None:
    assert _run_id_from_name(Path("funnel-abc.json")) is None
    assert _run_id_from_name(Path("funnel-.json")) is None

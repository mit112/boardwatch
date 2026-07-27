from boardwatch.providers.ashby import AshbyProvider
from boardwatch.providers.greenhouse import GreenhouseProvider
from boardwatch.providers.lever import LeverProvider


def test_each_provider_declares_public_board_hosts() -> None:
    assert GreenhouseProvider().board_hosts == ("job-boards.greenhouse.io", "boards.greenhouse.io")
    assert LeverProvider().board_hosts == ("jobs.lever.co", "jobs.eu.lever.co")
    assert AshbyProvider().board_hosts == ("jobs.ashbyhq.com",)

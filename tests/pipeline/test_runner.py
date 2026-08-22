from boardwatch.pipeline.runner import DEFAULT_TOP_N


def test_default_top_n_is_forty() -> None:
    """D-272. The cap is a DISPLAY limit, not a filter — run 67 cut 3,502 qualifying postings.
    It also gates P7, whose rule 'judge a source by leads over >=3 runs' cannot run while the
    numerator is fixed at 8 by construction."""
    assert DEFAULT_TOP_N == 40

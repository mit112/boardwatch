from boardwatch.pipeline.runner import DEFAULT_TOP_N


def test_default_top_n_is_ten_while_the_precision_work_is_outstanding() -> None:
    """D-293 lowered this 40 -> 10; it is a HOLDING value, not a new equilibrium.

    The cap is a DISPLAY limit, not a filter — everything past it stays `open` and is counted
    into `capped_by_top_n` (run 67 cut 3,502 qualifying postings, which is why D-272 raised it
    from 8). What changed is the denominator: D-272 justified 40 by job-apps' median of 42 **a
    day**, and D-288 then made the job fire 8 times a day, so 40 per run became 320 a day. Every
    lead costs a tailored résumé and a PDF, and D-292 measured ~51% of the shortlist as
    non-software, so the render was being spent on a half-junk pile.

    Pinned rather than left to drift because the value is load-bearing in two directions at once:
    **0 fails B1** (>= 10 net-new leads/day) outright and would stall the provisional pass, while
    **raising it before the D-293 precision work lands** re-creates the waste. 10 x 8 runs = 80 a
    day, comfortably over B1.
    """
    assert DEFAULT_TOP_N == 10

"""Tests for the résumé-wide verb-opening-diversity post-pass (P4 item 3a, 2c). Pure
`(Resume, TierBResult) -> TierBResult`; a small synthetic Resume is enough, no JD needed.
"""

from __future__ import annotations

from boardwatch.tailor.model import Bullet, Entry, Resume
from boardwatch.tailor.plan import Rewrite
from boardwatch.tailor.rewrite.result import RewriteRow, TierBResult
from boardwatch.tailor.rewrite.verb_diversity import VERB_DIVERSITY_VERSION, enforce_verb_diversity


def _resume(bullets: list[tuple[str, str]]) -> Resume:
    return Resume(
        header=["h"],
        education=[],
        skill_groups=[],
        entries=[
            Entry(
                entry_id="e1",
                heading="Work",
                bullets=[Bullet(bullet_id=bid, text=text) for bid, text in bullets],
            )
        ],
    )


def _kept_row(bullet_id: str, a_text: str, b_text: str) -> RewriteRow:
    return RewriteRow(
        bullet_id=bullet_id,
        entry_id="e1",
        a_text=a_text,
        b_text=b_text,
        filter_pass=True,
        judge_verdict="ENTAILED",
        kept=True,
        drop_reason=None,
    )


def test_verb_diversity_version_is_defined():
    assert isinstance(VERB_DIVERSITY_VERSION, str)
    assert VERB_DIVERSITY_VERSION == "p4-verb-diversity-1"


def test_baseline_already_at_cap_demotes_the_accepted_rewrite():
    """Two Tier-A bullets (not rewritten) already open with "Built"; an accepted Tier-B
    rewrite that ALSO opens with "Built" would be the 3rd -- past the cap of 2."""
    resume = _resume(
        [
            ("b1", "Built the x service"),
            ("b2", "Built the y pipeline"),
            ("b3", "Wrote the z report"),
        ]
    )
    accepted = [Rewrite(bullet_id="b3", text="Built the w dashboard")]
    rows = [
        _kept_row("b1", "Built the x service", "Built the x service"),
        _kept_row("b2", "Built the y pipeline", "Built the y pipeline"),
        _kept_row("b3", "Wrote the z report", "Built the w dashboard"),
    ]
    # b1/b2 were never sent through Tier-B (no row for them at all in a real run since
    # run_tier_b_core only rows bullets it actually processed) -- omit them here; only
    # b3's row matters for this test, but the seed reads from `resume`, not `rows`.
    result = TierBResult(accepted=accepted, rows=[rows[2]], calls_made=5)
    out = enforce_verb_diversity(resume, result)
    assert out.accepted == []
    assert out.rows[0].kept is False
    assert out.rows[0].drop_reason == "verb_repeat"
    assert out.calls_made == 5


def test_within_cap_rewrite_is_kept_baseline_plus_one():
    """One Tier-A baseline "Built" bullet + one accepted "Built" rewrite = 2 total, AT the
    cap, not over it -- must be kept."""
    resume = _resume([("b1", "Built the x service"), ("b2", "Wrote the y report")])
    accepted = [Rewrite(bullet_id="b2", text="Built the y report")]
    rows = [_kept_row("b2", "Wrote the y report", "Built the y report")]
    result = TierBResult(accepted=accepted, rows=rows, calls_made=2)
    out = enforce_verb_diversity(resume, result)
    assert out.accepted == accepted
    assert out.rows[0].kept is True
    assert out.rows[0].drop_reason is None


def test_excess_accepted_rewrites_are_demoted_in_bullet_order():
    """Three accepted rewrites all open with "Led", no baseline conflict -- the first two
    (in bullet/row order) stand, the third is demoted."""
    resume = _resume(
        [
            ("b1", "Managed the x team"),
            ("b2", "Ran the y project"),
            ("b3", "Owned the z rollout"),
        ]
    )
    accepted = [
        Rewrite(bullet_id="b1", text="Led the x team"),
        Rewrite(bullet_id="b2", text="Led the y project"),
        Rewrite(bullet_id="b3", text="Led the z rollout"),
    ]
    rows = [
        _kept_row("b1", "Managed the x team", "Led the x team"),
        _kept_row("b2", "Ran the y project", "Led the y project"),
        _kept_row("b3", "Owned the z rollout", "Led the z rollout"),
    ]
    result = TierBResult(accepted=accepted, rows=rows, calls_made=6)
    out = enforce_verb_diversity(resume, result)
    assert [r.bullet_id for r in out.accepted] == ["b1", "b2"]
    assert [r.kept for r in out.rows] == [True, True, False]
    assert out.rows[2].drop_reason == "verb_repeat"
    assert out.rows[2].bullet_id == "b3"


def test_diverse_opening_verbs_are_never_demoted():
    resume = _resume(
        [("b1", "Managed the x team"), ("b2", "Ran the y project"), ("b3", "Owned the z rollout")]
    )
    accepted = [
        Rewrite(bullet_id="b1", text="Led the x team"),
        Rewrite(bullet_id="b2", text="Built the y project"),
        Rewrite(bullet_id="b3", text="Shipped the z rollout"),
    ]
    rows = [
        _kept_row("b1", "Managed the x team", "Led the x team"),
        _kept_row("b2", "Ran the y project", "Built the y project"),
        _kept_row("b3", "Owned the z rollout", "Shipped the z rollout"),
    ]
    result = TierBResult(accepted=accepted, rows=rows, calls_made=6)
    out = enforce_verb_diversity(resume, result)
    assert out.accepted == accepted
    assert [r.kept for r in out.rows] == [True, True, True]


def test_tier_a_content_is_never_demoted_regardless_of_repetition():
    """Three Tier-A bullets share an opening verb and NONE were rewritten (accepted is
    empty) -- the post-pass must be a pure no-op; Tier-A is never audited."""
    resume = _resume(
        [
            ("b1", "Built the x service"),
            ("b2", "Built the y pipeline"),
            ("b3", "Built the z dashboard"),
        ]
    )
    result = TierBResult(accepted=[], rows=[], calls_made=0)
    out = enforce_verb_diversity(resume, result)
    assert out is result


def test_max_repeats_is_configurable():
    resume = _resume([("b1", "Wrote the x report")])
    accepted = [Rewrite(bullet_id="b1", text="Built the x report")]
    rows = [_kept_row("b1", "Wrote the x report", "Built the x report")]
    result = TierBResult(accepted=accepted, rows=rows, calls_made=2)
    out = enforce_verb_diversity(resume, result, max_repeats=0)
    assert out.accepted == []
    assert out.rows[0].drop_reason == "verb_repeat"

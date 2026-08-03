from boardwatch.extract.taxonomy import load_taxonomy
from boardwatch.tailor.rewrite.filter import passes_overmatch_filter


def _tax(tmp_path):
    return load_taxonomy(tmp_path)  # bundled default taxonomy when no user file present


def test_faithful_reword_passes(tmp_path):
    r = passes_overmatch_filter("Built the service in Python", "Shipped the service using Python", _tax(tmp_path))
    assert r.passed and r.reason is None


def test_invented_skill_rejected(tmp_path):
    # A has no Kubernetes; B adds it -> overmatch.
    r = passes_overmatch_filter(
        "Built the billing service and its API in Python",
        "Built the billing service and its API in Python and Kubernetes",
        _tax(tmp_path),
    )
    assert not r.passed and r.reason == "invented_skill"


def test_added_number_rejected(tmp_path):
    r = passes_overmatch_filter("Improved latency", "Improved latency by 40%", _tax(tmp_path))
    assert not r.passed and r.reason == "added_number"


def test_dropping_a_number_is_allowed(tmp_path):
    r = passes_overmatch_filter("Cut costs by 30 percent", "Cut costs materially", _tax(tmp_path))
    assert r.passed


def test_invented_acronym_rejected(tmp_path):
    r = passes_overmatch_filter("Ran jobs on the cluster", "Ran jobs on AWS", _tax(tmp_path))
    assert not r.passed and r.reason == "invented_entity"


def test_invented_brand_rejected(tmp_path):
    # A mid-sentence Title-case brand name absent from the source is an invented entity,
    # even though it is neither an acronym nor a taxonomy skill (this is the c15 gap).
    r = passes_overmatch_filter(
        "Built and maintained the billing service for customers worldwide",
        "Built and maintained the billing service for Google customers worldwide",
        _tax(tmp_path),
    )
    assert not r.passed and r.reason == "invented_entity"


def test_sentence_initial_verb_not_flagged(tmp_path):
    # Swapping the leading action verb (both Title-case, sentence-initial) must NOT be
    # read as an invented entity -- that exemption is exactly why the brand rule skips
    # token 0.
    r = passes_overmatch_filter("Improved the checkout flow", "Built the checkout flow", _tax(tmp_path))
    assert r.passed


def test_title_case_skill_keeps_invented_skill_reason(tmp_path):
    # Kubernetes is Title-case AND a taxonomy skill; the added-brand rule must not steal
    # it from the more specific invented_skill reason.
    r = passes_overmatch_filter(
        "Built the billing service in Python",
        "Built the billing service in Python and Kubernetes",
        _tax(tmp_path),
    )
    assert not r.passed and r.reason == "invented_skill"


def test_multiline_rejected(tmp_path):
    r = passes_overmatch_filter("Built the service", "Built\nthe service", _tax(tmp_path))
    assert not r.passed and r.reason == "not_single_line"


def test_too_long_rejected(tmp_path):
    r = passes_overmatch_filter("Built it", "Built it " + "x" * 100, _tax(tmp_path))
    assert not r.passed and r.reason == "too_long"


def test_empty_rejected(tmp_path):
    r = passes_overmatch_filter("Built it", "   ", _tax(tmp_path))
    assert not r.passed and r.reason == "empty"

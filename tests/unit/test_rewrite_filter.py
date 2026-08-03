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


def test_multiline_rejected(tmp_path):
    r = passes_overmatch_filter("Built the service", "Built\nthe service", _tax(tmp_path))
    assert not r.passed and r.reason == "not_single_line"


def test_too_long_rejected(tmp_path):
    r = passes_overmatch_filter("Built it", "Built it " + "x" * 100, _tax(tmp_path))
    assert not r.passed and r.reason == "too_long"


def test_empty_rejected(tmp_path):
    r = passes_overmatch_filter("Built it", "   ", _tax(tmp_path))
    assert not r.passed and r.reason == "empty"

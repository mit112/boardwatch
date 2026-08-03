"""Guard test: prevent silent deletion of the tailor-rewrite skill.

The skill file is prose (not Python), so it does not run and cannot be covered
by normal unit tests. This test only asserts the file exists and encodes the
core safety property — the judge is a separate, JD-blind agent invocation —
plus the three CLI command verbs it must document accurately.
"""

from pathlib import Path


def test_tailor_rewrite_skill_encodes_jd_blind_rule():
    text = Path(".claude/skills/tailor-rewrite/SKILL.md").read_text(encoding="utf-8")
    assert "JD-blind" in text and "separate" in text.lower()


def test_tailor_rewrite_skill_documents_all_three_cli_commands():
    text = Path(".claude/skills/tailor-rewrite/SKILL.md").read_text(encoding="utf-8")
    assert "rewrite request" in text
    assert "rewrite screen" in text
    assert "rewrite apply" in text

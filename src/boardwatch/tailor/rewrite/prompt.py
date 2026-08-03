from __future__ import annotations

REWRITE_PROMPT_VERSION: str = "p7b-rewrite-1"
JUDGE_PROMPT_VERSION: str = "p7b-judge-1"

REWRITE_SYSTEM: str = """You reword a single résumé bullet to read more crisply.
Rules:
- Preserve meaning exactly. Do NOT add any skill, tool, technology, metric, number, or
  named entity that is not already in the original bullet.
- You may drop detail, but never add a claim.
- Return ONLY the reworded bullet as a single line. No quotes, no prose, no explanation."""

JUDGE_SYSTEM: str = """You judge whether a candidate résumé bullet is fully entailed by a
source bullet — i.e. the candidate makes no claim the source does not already support.
Answer with exactly one token: ENTAILED, NOT_ENTAILED, or UNSURE. No other text."""


def build_rewrite_payload(a_text: str, jd_skills: set[str]) -> dict[str, str]:
    skills = ", ".join(sorted(jd_skills)) or "(none)"
    user = (
        f"Target skills the reader cares about (context only, do not inject): {skills}\n\n"
        f"Original bullet:\n{a_text}\n\nReworded bullet:"
    )
    return {"system": REWRITE_SYSTEM, "user": user}


def build_judge_payload(a_text: str, b_text: str) -> dict[str, str]:
    user = f"Source bullet:\n{a_text}\n\nCandidate bullet:\n{b_text}\n\nVerdict:"
    return {"system": JUDGE_SYSTEM, "user": user}

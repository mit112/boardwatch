from __future__ import annotations

import re
from pathlib import Path

import yaml
from pydantic import ValidationError

from boardwatch.reports.resume_gate import (
    GateReason,
    contains_template_artifact,
    layout_scan_fields,
)
from boardwatch.tailor.model import Resume


class ResumeLoadError(ValueError):
    """Authored résumé YAML is missing, unparseable, or invalid."""


class MasterResumeError(ResumeLoadError):
    """The authored master résumé failed a run-once structural check at `load_resume()` time
    (PROGRAM.md P4 item 5b): a broken contact block, or a leftover template artifact, in the
    master itself. A `ResumeLoadError` subclass on purpose — every existing caller that already
    treats a malformed `resume.yaml` as fatal (the CLI's `except ResumeLoadError` sites) treats
    this identically with no further change, and the pipeline runner special-cases
    `ResumeLoadError` as a run-level fatal for the same reason `TypstUnavailableError` is: this
    is an authoring/environment fault, not a per-lead one, so every remaining lead would fail
    identically and re-discovering that lead by lead wastes compile time for no new information.
    """

    def __init__(self, reason: GateReason, message: str) -> None:
        super().__init__(message)
        self.reason = reason


_EMAIL_PATTERN = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


def validate_master(resume: Resume) -> None:
    """Run-once, fatal structural checks on the authored MASTER résumé (PROGRAM.md P4 item
    5b): contact-block integrity and leftover template artifacts. A standalone validator, not
    a pydantic `model_validator`, mirroring `resume_gate.validate_slots`'s call convention.

    Deliberately does NOT check bullet length or bullet count (P4 item 5a's job, on the
    TAILORED résumé): those are genuinely per-lead risks (Tier-B rewrite, JD-driven trimming)
    that vary posting to posting, whereas a concise or long authored bullet, or an entry with
    more than 6 bullets, is Mit's authoring choice on the master. Gating the master on them
    was exactly the regression D-055 removed — this function must not reintroduce it.
    """
    if not resume.header or not resume.header[0].strip():
        raise MasterResumeError(
            GateReason.CONTACT_BLOCK_MISSING_NAME,
            "master résumé header is missing a name (empty header, or a blank first line)",
        )
    if not any(_EMAIL_PATTERN.search(line) for line in resume.header):
        raise MasterResumeError(
            GateReason.CONTACT_BLOCK_INVALID_EMAIL,
            "master résumé header has no valid email address",
        )
    for text, where in layout_scan_fields(resume):
        token = contains_template_artifact(text)
        if token is not None:
            raise MasterResumeError(
                GateReason.TEMPLATE_ARTIFACT,
                f"master résumé {where} contains template artifact {token!r}",
            )


def load_resume(path: Path) -> Resume:
    if not path.is_file():
        raise ResumeLoadError(f"no résumé at {path}; run `boardwatch tailor init` to scaffold one")
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ResumeLoadError(f"{path}: not valid UTF-8: {exc}") from exc
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ResumeLoadError(f"{path}: invalid YAML: {exc}") from exc
    try:
        resume = Resume.model_validate(data)
    except ValidationError as exc:
        raise ResumeLoadError(f"{path}: {exc}") from exc
    validate_master(resume)
    return resume


def scaffold_template() -> str:
    return _TEMPLATE


_TEMPLATE = """\
header:
  - "Ada Lovelace"
  - "ada@example.com · github.com/ada"
education:
  - "BSc Mathematics — Example University — 2018"
skill_groups:
  - label: "Languages"
    items: ["Python", "Rust", "JavaScript"]
entries:
  - entry_id: "acme-sre"
    heading: "Senior Engineer — Acme — 2021–2024 — Remote"
    bullets:
      - bullet_id: "acme-1"
        text: "Built a Python service handling 2M requests/day on Kubernetes"
        tech_tags: ["Python", "Kubernetes"]
      - bullet_id: "acme-2"
        text: "Cut p99 latency 40% by rewriting the hot path in Rust"
        tech_tags: ["Rust"]
"""

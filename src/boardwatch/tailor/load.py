from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from boardwatch.tailor.model import Resume


class ResumeLoadError(ValueError):
    """Authored résumé YAML is missing, unparseable, or invalid."""


def load_resume(path: Path) -> Resume:
    if not path.is_file():
        raise ResumeLoadError(f"no résumé at {path}; run `boardwatch tailor init` to scaffold one")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ResumeLoadError(f"{path}: invalid YAML: {exc}") from exc
    try:
        return Resume.model_validate(data)
    except ValidationError as exc:
        raise ResumeLoadError(f"{path}: {exc}") from exc


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

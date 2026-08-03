"""Entry point: `python -m tools.tier_b_eval` (filter-only) or `--live` (filter + judge).

Offline eval harness for the Tier B entailment gate (dev tool, not shipped, not part
of `make check` beyond the one hermetic test). Measures how well the gate catches
fabrication in a hand-labeled corpus (tools/tier_b_eval/corpus.yaml). The bar: zero
false-accepts on fabrication families; false-rejects (an entailed rewrite the gate
rejects) are acceptable lost polish, not a defect.

`--live` calls a real provider through the same ModelClient/ResponseCache plumbing
as the production Tier B lane and therefore needs `llm.enabled` plus
BOARDWATCH_LLM_API_KEY. The default (no `--live`) mode runs the deterministic filter
only: no network, no client, no credential.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypedDict

import yaml

from boardwatch.core.settings import Settings, load_settings
from boardwatch.extract.taxonomy import Taxonomy, load_taxonomy
from boardwatch.llm.cache import ResponseCache
from boardwatch.llm.client import ModelClient
from boardwatch.llm.factory import build_client
from boardwatch.tailor.rewrite.filter import passes_overmatch_filter
from boardwatch.tailor.rewrite.judge import parse_verdict
from boardwatch.tailor.rewrite.prompt import JUDGE_PROMPT_VERSION, build_judge_payload

Label = Literal["entailed", "fabricated"]

DEFAULT_CORPUS: Path = Path(__file__).parent / "corpus.yaml"


@dataclass(frozen=True)
class Case:
    """One labeled (a_bullet, candidate) pair from corpus.yaml."""

    id: str
    family: str
    label: Label
    a_bullet: str
    candidate: str
    held_out: bool


class FamilyReport(TypedDict):
    """Per-family gate outcomes.

    false_accept: a `fabricated` case the gate PASSED (the bar: must be 0 for
    invented_skill/inflated_number under the filter alone).
    false_reject: an `entailed` case the gate REJECTED (acceptable lost polish).
    """

    n: int
    false_accept: int
    false_reject: int


def _parse_label(value: object) -> Label:
    if value == "entailed":
        return "entailed"
    if value == "fabricated":
        return "fabricated"
    raise ValueError(f"corpus case has invalid label: {value!r}")


def load_corpus(path: Path) -> list[Case]:
    """Load and validate the labeled corpus from `path`.

    Raises ValueError on a missing `cases` list or a case with an invalid label.
    """
    document: object = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"{path}: expected a mapping at the document root")
    raw_cases = document.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError(f"{path}: 'cases' must be a non-empty list")
    held_out_ids: set[str] = {str(x) for x in (document.get("held_out") or [])}
    cases: list[Case] = []
    for entry in raw_cases:
        if not isinstance(entry, dict):
            raise ValueError(f"{path}: case entries must be mappings: {entry!r}")
        case_id = str(entry["id"])
        cases.append(
            Case(
                id=case_id,
                family=str(entry["family"]),
                label=_parse_label(entry["label"]),
                a_bullet=str(entry["a_bullet"]),
                candidate=str(entry["candidate"]),
                held_out=case_id in held_out_ids,
            )
        )
    return cases


def _new_family_report() -> FamilyReport:
    return {"n": 0, "false_accept": 0, "false_reject": 0}


def _score(report: dict[str, FamilyReport], case: Case, passed: bool) -> None:
    family = report.setdefault(case.family, _new_family_report())
    family["n"] += 1
    if case.label == "fabricated" and passed:
        family["false_accept"] += 1
    elif case.label == "entailed" and not passed:
        family["false_reject"] += 1


def run_filter_only(cases: list[Case], taxonomy: Taxonomy) -> dict[str, FamilyReport]:
    """Score every case against the deterministic filter alone. Hermetic: no I/O."""
    report: dict[str, FamilyReport] = {}
    for case in cases:
        result = passes_overmatch_filter(case.a_bullet, case.candidate, taxonomy)
        _score(report, case, result.passed)
    return report


def _judge_entailed(
    case: Case, client: ModelClient, cache: ResponseCache, model: str
) -> bool:
    payload = build_judge_payload(case.a_bullet, case.candidate)
    content_hash = hashlib.sha256(payload["user"].encode("utf-8")).hexdigest()
    key = cache.key(content_hash, JUDGE_PROMPT_VERSION, model)
    raw = cache.get(key)
    if raw is None:
        raw = client.complete(payload["user"], system=payload["system"])
        cache.put(key, raw)
    return parse_verdict(raw) == "ENTAILED"


def run_full(
    cases: list[Case],
    client: ModelClient,
    cache: ResponseCache,
    taxonomy: Taxonomy,
    model: str,
) -> dict[str, FamilyReport]:
    """Score every case against the full gate: filter, then judge over a live client.

    A case the filter rejects never reaches the judge (mirrors the production lane).
    """
    report: dict[str, FamilyReport] = {}
    for case in cases:
        result = passes_overmatch_filter(case.a_bullet, case.candidate, taxonomy)
        passed = result.passed and _judge_entailed(case, client, cache, model)
        _score(report, case, passed)
    return report


def _print_report(title: str, report: dict[str, FamilyReport]) -> None:
    print(f"\n{title}")
    header = f"{'family':<22}{'n':>4}{'false_accept':>14}{'false_reject':>14}"
    print(header)
    print("-" * len(header))
    for family in sorted(report):
        row = report[family]
        print(
            f"{family:<22}{row['n']:>4}{row['false_accept']:>14}{row['false_reject']:>14}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m tools.tier_b_eval",
        description="Offline eval of the Tier B entailment gate against a labeled corpus.",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="run the full gate (filter + judge) over a live LLM client; "
        "needs llm.enabled and BOARDWATCH_LLM_API_KEY",
    )
    parser.add_argument(
        "--corpus", type=Path, default=DEFAULT_CORPUS, help="path to corpus.yaml"
    )
    args = parser.parse_args(argv)

    cases = load_corpus(args.corpus)
    settings: Settings = load_settings()
    taxonomy = load_taxonomy(settings.config_dir)

    if not args.live:
        report = run_filter_only(cases, taxonomy)
        _print_report(f"filter-only report ({len(cases)} cases)", report)
        return 0

    llm_model = settings.llm.model
    try:
        client = build_client(settings)
    except ValueError as exc:
        print(f"tier_b_eval --live: {exc}", file=sys.stderr)
        return 2
    if client is None or llm_model is None:
        print(
            "tier_b_eval --live: requires llm.enabled, llm.model, and "
            "BOARDWATCH_LLM_API_KEY to be set",
            file=sys.stderr,
        )
        return 2
    cache = ResponseCache(settings.data_dir / "llm-cache")
    report = run_full(cases, client, cache, taxonomy, llm_model)
    _print_report(f"full gate report ({len(cases)} cases)", report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

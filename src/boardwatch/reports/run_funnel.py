"""The per-run funnel artifact — PROGRAM.md §3.P0 **item 1**, the item that closes Gate P0.

Gate P0 asks for three consecutive runs where the funnel reconciles to 100%, per-rule
abstain for EVERY rule in the catalog, and *which source produced each lead and why every
non-lead was dropped* answerable **from the artifact alone, without reading code**. That
last clause is why this module renders Markdown as well as JSON, and why every stage carries
its drops by name rather than leaving the reader to subtract two numbers.

Three properties are load-bearing and each one exists because collapsing it destroys a
signal this program is built to preserve:

  * **A stage that is not instrumented reports `None`, never 0.** Same reasoning as
    `reports/abstain.abstain_rate`: a dedup stage that has never run and a dedup stage that
    dropped nothing are opposite conditions, and 0 reads as the healthy one.
  * **A stage whose drop bucket is a pure remainder is flagged `derived`.** Its
    reconciliation is bookkeeping, not evidence — it cannot fail by construction. Only the
    non-derived stages and the cross-checks are capable of catching a wrong number, and the
    artifact says which is which instead of presenting one uniform row of green ticks.
  * **`cache_hit_unattributed` is never folded into `cache_hit_prior_run`.** Per D-019 a
    NULL run_id means exactly one thing — the row predates attribution — and that population
    can only shrink. Folding it would erase the only evidence that no NULL leaked back in.

The stored verdict vocabulary is `eligible | ineligible | uncertain`; **there is no `abstain`
verdict**. The keystone invariant's ABSTAIN persists as `uncertain`, so this module renames
it on the way out and says so, rather than silently presenting a column the schema lacks.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from boardwatch.reports.abstain import AbstainReport
from boardwatch.store.run_funnel_queries import CorpusCounts, TailoredArtifactCounts

ARTIFACT_VERSION = 1

# The stored verdict that carries the keystone invariant's ABSTAIN. Named here once so the
# rename is visible rather than scattered through the renderers as a string literal.
STORED_ABSTAIN_VERDICT = "uncertain"


@dataclass(frozen=True)
class Drop:
    """A named reason postings left the funnel at a stage, and how many did."""

    reason: str
    count: int
    note: str = ""


@dataclass(frozen=True)
class Stage:
    """One funnel edge: what entered, what advanced, and every reason for the difference."""

    name: str
    entered: int | None
    advanced: int | None
    drops: tuple[Drop, ...] = ()
    note: str = ""
    # True when one drop bucket is the remainder of the others, so `reconciled` holds by
    # construction. Recorded so a reader never mistakes arithmetic for verification.
    derived: bool = False

    @property
    def instrumented(self) -> bool:
        return self.entered is not None and self.advanced is not None

    @property
    def dropped(self) -> int:
        return sum(drop.count for drop in self.drops)

    @property
    def reconciled(self) -> bool | None:
        """None when the stage is not instrumented — an uncomputable identity is not a pass."""
        if not self.instrumented:
            return None
        assert self.entered is not None and self.advanced is not None  # narrowed by instrumented
        return self.entered == self.advanced + self.dropped


@dataclass(frozen=True)
class CrossCheck:
    """The same quantity counted twice, by paths that share no code.

    `CLAUDE.md`: a component's self-report is not verification. `in_memory` is what the
    pipeline believed it did; `from_store` is what the database says on a read that never
    touched the pipeline's objects. Disagreement is recorded, never resolved by preferring
    one — the artifact's job is to make the disagreement visible.
    """

    name: str
    in_memory: int
    from_store: int
    note: str = ""

    @property
    def agrees(self) -> bool:
        return self.in_memory == self.from_store


@dataclass(frozen=True)
class Lead:
    """One tailored lead and the board it came from.

    The provenance fields are what make Gate P0's *"which source produced each lead"*
    answerable from the artifact alone.
    """

    posting_id: int
    title: str
    company: str
    provider: str
    board_slug: str
    company_source: str
    out_dir: str
    pdf_built: bool


@dataclass(frozen=True)
class ScanContext:
    """Scan throughput. Deliberately NOT a funnel edge.

    `postings_seen` counts postings a board LISTED this run — an unchanged board returns 304
    and lists none — while the funnel's head is every open posting in the store. Chaining one
    into the other would be arithmetic that is wrong on every run with an unchanged board,
    and on every `--no-scan` run it would be wrong by the entire corpus.
    """

    ran: bool
    boards_attempted: int = 0
    boards_complete: int = 0
    boards_failed: int = 0
    postings_seen: int = 0


@dataclass(frozen=True)
class RunFunnel:
    run_id: int
    started_at: datetime | None
    finished_at: datetime | None
    scan: ScanContext
    stages: tuple[Stage, ...]
    leads: tuple[Lead, ...]
    cross_checks: tuple[CrossCheck, ...]
    abstain: AbstainReport
    unattributed_evaluations: int
    errors: tuple[str, ...] = ()
    fatal: str | None = None

    @property
    def instrumented_stages(self) -> tuple[Stage, ...]:
        return tuple(stage for stage in self.stages if stage.instrumented)

    @property
    def unreconciled(self) -> tuple[Stage, ...]:
        return tuple(stage for stage in self.instrumented_stages if stage.reconciled is False)

    @property
    def disagreements(self) -> tuple[CrossCheck, ...]:
        return tuple(check for check in self.cross_checks if not check.agrees)

    @property
    def reconciles(self) -> bool:
        """Gate P0's "reconciles to 100%": every instrumented stage balances AND both
        independent recounts agree with what the pipeline reported."""
        return not self.unreconciled and not self.disagreements

    @property
    def rules_missing_abstain(self) -> int:
        """Gate P0 requires abstain for EVERY rule; the catalog enumeration guarantees a row
        for each, so this is 0 unless the catalog itself failed to load."""
        return 0 if self.abstain.rules else 1


def build_run_funnel(
    *,
    run_id: int,
    started_at: datetime | None,
    finished_at: datetime | None,
    scan: ScanContext,
    corpus: CorpusCounts,
    shortlisted: int,
    hidden_ineligible: int,
    hidden_non_swe: int,
    leads: Sequence[Lead],
    tailor_failed: int,
    tailored_artifacts: TailoredArtifactCounts,
    marked_applied: int,
    unattributed_evaluations: int,
    abstain: AbstainReport,
    errors: Sequence[str] = (),
    fatal: str | None = None,
) -> RunFunnel:
    """Assemble the funnel from counts. Pure: no engine, no clock, no filesystem."""
    verdicts = dict(corpus.by_verdict)
    eligible = verdicts.pop("eligible", 0)
    ineligible = verdicts.pop("ineligible", 0)
    abstained = verdicts.pop(STORED_ABSTAIN_VERDICT, 0)
    # Anything the CHECK constraint does not currently allow. Carried rather than dropped so
    # that widening the constraint cannot make rows vanish from the verdict stage and quietly
    # shrink its denominator — the same guard `RuleAbstain.other` exists for.
    other_verdicts = sum(verdicts.values())

    tailored = len(leads)
    with_pdf = sum(1 for lead in leads if lead.pdf_built)

    stages = (
        Stage(
            name="dedup",
            entered=None,
            advanced=None,
            note=(
                "NOT INSTRUMENTED. jobs and postings are 1:1, so grouping has never run and "
                "duplicate leakage is structurally unmeasurable. Owned by P6 — reported as "
                "unmeasured rather than as zero duplicates, which is the opposite claim."
            ),
        ),
        Stage(
            name="corpus",
            entered=corpus.open_postings,
            advanced=corpus.evaluated,
            drops=(
                Drop(
                    reason="no_current_evaluation",
                    count=corpus.no_current_evaluation,
                    note=(
                        "open posting with no version row, or whose current version has "
                        "never been judged under this profile+rules identity"
                    ),
                ),
            ),
            note="Head of the funnel: every OPEN posting in the store, not just those listed"
            " this run.",
        ),
        Stage(
            name="attribution",
            entered=corpus.evaluated,
            advanced=corpus.judged_this_run,
            drops=(
                Drop(
                    reason="cache_hit_prior_run",
                    count=corpus.cache_hit_prior_run,
                    note="already judged by an earlier run; no evaluation row written now",
                ),
                Drop(
                    reason="cache_hit_unattributed",
                    count=corpus.cache_hit_unattributed,
                    note=(
                        "judged before run attribution existed (run_id IS NULL). Its own "
                        "bucket by D-019 and never folded into the line above"
                    ),
                ),
            ),
            note="The stage D-016 exists for: 'judged this run' and 'cache hit' are the same"
            " number without run_id.",
        ),
        Stage(
            name="verdict",
            entered=corpus.evaluated,
            advanced=eligible,
            drops=(
                Drop(reason="ineligible", count=ineligible),
                Drop(
                    reason="abstained",
                    count=abstained,
                    note=f"stored as verdict {STORED_ABSTAIN_VERDICT!r}; there is no 'abstain'"
                    " verdict in the schema",
                ),
                Drop(
                    reason="verdict_out_of_vocabulary",
                    count=other_verdicts,
                    note="impossible while the CHECK constraint holds; carried so widening it"
                    " cannot shrink this stage silently",
                ),
            ),
        ),
        Stage(
            name="shortlist",
            entered=eligible,
            advanced=shortlisted,
            drops=(
                Drop(reason="hidden_ineligible", count=hidden_ineligible),
                Drop(reason="hidden_non_swe", count=hidden_non_swe, note="title role gate"),
                Drop(
                    reason="capped_by_top_n",
                    count=max(0, eligible - shortlisted - hidden_ineligible - hidden_non_swe),
                    note="remainder: ranked below the --top cutoff",
                ),
            ),
            derived=True,
            note=(
                "DERIVED. capped_by_top_n is the remainder, so this stage cannot fail to "
                "balance. The ranker's own population also differs from the verdict stage's "
                "(it needs an extraction row), which is why the remainder is clamped at 0."
            ),
        ),
        Stage(
            name="tailor",
            entered=shortlisted,
            advanced=tailored,
            drops=(Drop(reason="tailor_failed", count=tailor_failed),),
        ),
        Stage(
            name="pdf",
            entered=tailored,
            advanced=with_pdf,
            drops=(
                Drop(
                    reason="no_pdf",
                    count=tailored - with_pdf,
                    note="résumé source written but no PDF compiled — D-006's silent degrade",
                ),
            ),
            derived=True,
        ),
        Stage(
            name="applied",
            entered=with_pdf,
            advanced=marked_applied,
            drops=(
                Drop(
                    reason="not_marked_applied",
                    count=max(0, with_pdf - marked_applied),
                    note="snapshot at write time; marking applied is a later manual act",
                ),
            ),
            derived=True,
        ),
    )

    cross_checks = (
        CrossCheck(
            name="tailored",
            in_memory=tailored,
            from_store=tailored_artifacts.rows,
            note="pipeline's lead objects vs resume_tailored rows carrying this run_id",
        ),
        CrossCheck(
            name="leads_with_pdf",
            in_memory=with_pdf,
            from_store=tailored_artifacts.with_pdf,
            note=(
                "pipeline's pdf_built flags vs json_extract(meta_json,'$.typst_pdf_built'). "
                "artifacts.uri is the .typ path either way, so a row count would not do"
            ),
        ),
    )

    return RunFunnel(
        run_id=run_id,
        started_at=started_at,
        finished_at=finished_at,
        scan=scan,
        stages=stages,
        leads=tuple(leads),
        cross_checks=cross_checks,
        abstain=abstain,
        unattributed_evaluations=unattributed_evaluations,
        errors=tuple(errors),
        fatal=fatal,
    )


def _stage_json(stage: Stage) -> dict[str, object]:
    return {
        "name": stage.name,
        "entered": stage.entered,
        "advanced": stage.advanced,
        "drops": [
            {"reason": drop.reason, "count": drop.count, "note": drop.note}
            for drop in stage.drops
        ],
        "reconciled": stage.reconciled,
        "instrumented": stage.instrumented,
        "derived": stage.derived,
        "note": stage.note,
    }


def funnel_to_dict(funnel: RunFunnel) -> dict[str, object]:
    """The machine-readable half. Every stage keeps its drops; nothing is pre-summed away."""
    return {
        "artifact_version": ARTIFACT_VERSION,
        "run_id": funnel.run_id,
        "started_at": funnel.started_at.isoformat() if funnel.started_at else None,
        "finished_at": funnel.finished_at.isoformat() if funnel.finished_at else None,
        "reconciles": funnel.reconciles,
        "fatal": funnel.fatal,
        "errors": list(funnel.errors),
        "scan": {
            "ran": funnel.scan.ran,
            "boards_attempted": funnel.scan.boards_attempted,
            "boards_complete": funnel.scan.boards_complete,
            "boards_failed": funnel.scan.boards_failed,
            "postings_seen": funnel.scan.postings_seen,
        },
        "stages": [_stage_json(stage) for stage in funnel.stages],
        "cross_checks": [
            {
                "name": check.name,
                "in_memory": check.in_memory,
                "from_store": check.from_store,
                "agrees": check.agrees,
                "note": check.note,
            }
            for check in funnel.cross_checks
        ],
        "leads": [
            {
                "posting_id": lead.posting_id,
                "title": lead.title,
                "company": lead.company,
                "provider": lead.provider,
                "board_slug": lead.board_slug,
                "company_source": lead.company_source,
                "out_dir": lead.out_dir,
                "pdf_built": lead.pdf_built,
            }
            for lead in funnel.leads
        ],
        "unattributed_evaluations": funnel.unattributed_evaluations,
        "abstain": {
            "rules": [
                {
                    "rule_id": rule.rule_id,
                    "family": rule.family,
                    "observed": rule.observed,
                    "met": rule.met,
                    "unmet": rule.unmet,
                    "abstained": rule.unknown,
                    # None, never 0.0 — a rate over zero rows is undefined, and 0% would
                    # make a rule that has never fired the healthiest in the catalog.
                    "abstain_rate": rule.abstain_rate,
                    "never_fired": rule.never_fired,
                    "fully_abstaining": rule.fully_abstaining,
                }
                for rule in funnel.abstain.rules
            ],
            "rule_count": len(funnel.abstain.rules),
            "never_fired": len(funnel.abstain.never_fired),
            "fully_abstaining": len(funnel.abstain.fully_abstaining),
            "out_of_catalog": list(funnel.abstain.out_of_catalog),
            "out_of_catalog_rows": funnel.abstain.out_of_catalog_rows,
            "unattributed_rows": funnel.abstain.unattributed,
            "total_rows": funnel.abstain.total_rows,
        },
    }


def _fmt(value: int | None) -> str:
    return "not instrumented" if value is None else str(value)


def funnel_to_markdown(funnel: RunFunnel) -> str:
    """The half a human reads. Gate P0 requires the artifact to answer, on its own, which
    source produced each lead and why every non-lead was dropped — so every drop is named
    and counted here, and the leads table carries its board."""
    verdict = "RECONCILES" if funnel.reconciles else "DOES NOT RECONCILE"
    lines = [
        f"# boardwatch run {funnel.run_id} — funnel",
        "",
        f"- **started:** {funnel.started_at.isoformat() if funnel.started_at else '—'}",
        f"- **finished:** {funnel.finished_at.isoformat() if funnel.finished_at else '—'}",
        f"- **reconciliation:** {verdict}",
    ]
    if funnel.fatal:
        lines.append(f"- **FATAL:** {funnel.fatal}")
    lines += [
        "",
        "## Scan",
        "",
    ]
    if funnel.scan.ran:
        lines.append(
            f"{funnel.scan.boards_attempted} boards attempted · "
            f"{funnel.scan.boards_complete} complete · {funnel.scan.boards_failed} failed · "
            f"{funnel.scan.postings_seen} postings listed"
        )
        lines.append("")
        lines.append(
            "*Throughput, not a funnel edge: an unchanged board lists nothing, so this is a "
            "different population from the corpus below.*"
        )
    else:
        lines.append("skipped (`--no-scan`) — the corpus below is whatever was already stored.")

    lines += [
        "",
        "## Funnel",
        "",
        "| stage | entered | advanced | dropped | reconciled |",
        "|---|---:|---:|---:|---|",
    ]
    for stage in funnel.stages:
        if stage.reconciled is None:
            mark = "—"
        elif stage.reconciled:
            mark = "yes (derived)" if stage.derived else "**yes**"
        else:
            mark = "**NO**"
        lines.append(
            f"| {stage.name} | {_fmt(stage.entered)} | {_fmt(stage.advanced)} | "
            f"{stage.dropped if stage.instrumented else '—'} | {mark} |"
        )

    lines += [
        "",
        "`yes (derived)` means one drop bucket is the remainder of the others, so the stage "
        "cannot fail to balance — bookkeeping, not evidence. The cross-checks below are what "
        "can actually catch a wrong number in the tailor half.",
        "",
        "## Why every non-lead was dropped",
        "",
    ]
    for stage in funnel.stages:
        if not stage.instrumented:
            lines += [f"### {stage.name}", "", f"*{stage.note}*", ""]
            continue
        lines.append(f"### {stage.name} — {stage.entered} in, {stage.advanced} out")
        lines.append("")
        if stage.note:
            lines += [f"*{stage.note}*", ""]
        if not stage.drops:
            lines += ["nothing dropped here.", ""]
            continue
        for drop in stage.drops:
            suffix = f" — {drop.note}" if drop.note else ""
            lines.append(f"- **{drop.reason}**: {drop.count}{suffix}")
        lines.append("")

    lines += ["## Cross-checks", "", "| quantity | pipeline said | store says | agree |",
              "|---|---:|---:|---|"]
    for check in funnel.cross_checks:
        lines.append(
            f"| {check.name} | {check.in_memory} | {check.from_store} | "
            f"{'yes' if check.agrees else '**NO**'} |"
        )
    lines += [
        "",
        *[f"- *{check.name}*: {check.note}" for check in funnel.cross_checks if check.note],
        "",
        "## Leads",
        "",
    ]
    if funnel.leads:
        lines += [
            "| posting | title | company | source board | registry/user | PDF | folder |",
            "|---:|---|---|---|---|---|---|",
        ]
        for lead in funnel.leads:
            lines.append(
                f"| {lead.posting_id} | {lead.title} | {lead.company} | "
                f"{lead.provider}:{lead.board_slug} | {lead.company_source} | "
                f"{'yes' if lead.pdf_built else '**no**'} | {lead.out_dir} |"
            )
    else:
        lines.append("none.")

    never_fired = funnel.abstain.never_fired
    fully = funnel.abstain.fully_abstaining
    lines += [
        "",
        "## Per-rule abstain",
        "",
        f"{len(funnel.abstain.rules)} rules in the catalog · {len(never_fired)} never fired · "
        f"{len(fully)} fire but never decide · {funnel.abstain.total_rows} requirement rows",
        "",
        "A rule that has never fired reports `never fired`, **not 0%** — a rate over zero rows "
        "is undefined, and 0% would rank it as the healthiest rule in the catalog.",
        "",
        "| rule | family | observed | met | unmet | abstained | rate |",
        "|---|---|---:|---:|---:|---:|---|",
    ]
    for rule in funnel.abstain.rules:
        if rule.never_fired:
            rate = "never fired"
        elif rule.fully_abstaining:
            rate = "**100%**"
        else:
            # 1051/1052 rounds to "100%" and would then read identically to a rule that
            # never decides at all, collapsing the two states this report keeps apart.
            rounded = f"{rule.abstain_rate:.0%}"
            rate = ">99%" if rounded == "100%" else rounded
        lines.append(
            f"| {rule.rule_id} | {rule.family} | {rule.observed} | {rule.met} | "
            f"{rule.unmet} | {rule.unknown} | {rate} |"
        )

    if funnel.abstain.out_of_catalog:
        lines += [
            "",
            f"**FAILURE — closed catalog violated:** {funnel.abstain.out_of_catalog_rows} rows "
            f"carry rule_ids the catalog does not declare: "
            f"{', '.join(funnel.abstain.out_of_catalog)}",
        ]

    lines += [
        "",
        "## Unattributed",
        "",
        f"{funnel.unattributed_evaluations} evaluations in the whole store carry no run_id.",
        "",
        "Per D-019 that means exactly one thing — the row predates run attribution — and the "
        "number can only shrink. **If it grew since the last run, a NULL leaked back in.** It "
        "is never folded into this run's counts and never reported as 0.",
    ]

    if funnel.errors:
        lines += ["", "## Errors", ""] + [f"- {err}" for err in funnel.errors]

    return "\n".join(lines) + "\n"


@dataclass(frozen=True)
class WrittenArtifact:
    json_path: Path
    markdown_path: Path


def write_run_funnel(funnel: RunFunnel, out_dir: Path) -> WrittenArtifact:
    """Write both halves under `out_dir`, named by run so two runs a day cannot collide.

    Written OUTSIDE the git tree, as tailored résumés already are: generalization rule R7
    requires a sha256-pinned SHIPPED_DATA entry for any tracked `.json`, which a per-run
    artifact can never satisfy.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"funnel-{funnel.run_id}.json"
    markdown_path = out_dir / f"funnel-{funnel.run_id}.md"
    json_path.write_text(json.dumps(funnel_to_dict(funnel), indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(funnel_to_markdown(funnel), encoding="utf-8")
    return WrittenArtifact(json_path=json_path, markdown_path=markdown_path)


# Re-exported so callers assembling a funnel need one import, not four.
__all__ = [
    "ARTIFACT_VERSION",
    "CrossCheck",
    "Drop",
    "Lead",
    "RunFunnel",
    "ScanContext",
    "Stage",
    "WrittenArtifact",
    "build_run_funnel",
    "funnel_to_dict",
    "funnel_to_markdown",
    "write_run_funnel",
]

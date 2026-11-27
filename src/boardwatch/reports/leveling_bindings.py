"""Propose `leveling-bindings.yaml` entries from the final-gate judge's seniority readings (T369).

A bare trailing number ("Software Engineer 5") is a level only at a company that numbers its
ladder, and nothing in the title says which. The judge reads the whole posting and answers
`seniority_fit` for every lead it judges, so where it answers the same way for every posting a
company titles with the same number, that answer is evidence of what the number means there.

READ-ONLY by construction: the caller opens the store through `get_readonly_engine`, and nothing
here writes. The report proposes; the user decides what goes in their own config.

**What a proposal claims.** A scheme is proposed for a board (a binding is per provider and slug,
so evidence is never pooled across boards) only when it agrees with the judge's majority answer
for EVERY numeric token the board shows, however few readings: `yes` (in the target band) needs a
rung at or below the band, `no` (above it) needs one above. `min_n` decides only which groups are
listed. Where no shipped scheme agrees the group is UNMATCHED and is never forced into the nearest
scheme. Where several agree (the judge's answers cannot tell them apart) the first in catalog
order is proposed and the others are named beside it, so the choice stays the user's. Only a
reading of the posting's CURRENT version counts: an answer to a superseded JD says nothing about
a revised title.

Only titles the gate reads as plain entry today count: a title with a seniority word ("Senior
Engineer 3") is answered for the word, not for the number, and would bias a group above band.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from math import sqrt
from pathlib import Path

from sqlalchemy import Engine, func, select

from boardwatch.core.settings import Settings
from boardwatch.eligibility.facts import ProfileRowInvalid
from boardwatch.eligibility.final_gate import gate_effort_key
from boardwatch.eligibility.preflight import engine_facts
from boardwatch.eligibility.read import gate_judge_identity
from boardwatch.rank.leveling import LevelingCatalog, LevelScheme, field_tier, load_leveling
from boardwatch.rank.role_taxonomy import declared_field, load_role_taxonomy
from boardwatch.rank.seniority_gate import BAND_ORDER, parse_seniority, trailing_level_token
from boardwatch.store.queries import current_posting_version_ids, get_profile
from boardwatch.store.tables import (
    companies,
    eligibility_evaluations,
    eligibility_inputs,
    posting_versions,
    postings,
)

DEFAULT_MIN_N = 7
_Z = 1.96  # two-sided 95%


class LevelingReportError(ValueError):
    """The report cannot be built for this store, and the message says what to fix."""


def wilson_lower(successes: int, n: int) -> float:
    """The lower end of the 95% Wilson interval for `successes` of `n`."""
    if n == 0:
        return 0.0
    p = successes / n
    z2 = _Z * _Z
    centre = p + z2 / (2 * n)
    margin = _Z * sqrt(p * (1 - p) / n + z2 / (4 * n * n))
    return (centre - margin) / (1 + z2 / n)


@dataclass(frozen=True)
class Reading:
    """One posting's newest reading under the current judge identity."""

    provider: str
    slug: str
    company: str
    title: str
    seniority_fit: str  # the judge's `yes` / `no` / `unclear`


@dataclass(frozen=True)
class Group:
    """One board's postings that share a trailing level token."""

    company: str  # a label only: the group is keyed by `provider` and `slug`
    provider: str
    slug: str
    token: str
    n: int
    majority: str  # `yes`, `no`, or `unclear` (also the answer to a tie)
    majority_n: int
    lower: float  # Wilson lower bound on the majority's share
    schemes: tuple[str, ...]  # the shipped schemes that agree, in catalog order


@dataclass(frozen=True)
class Proposal:
    company: str
    provider: str
    slug: str
    scheme: str
    also: tuple[str, ...]


@dataclass(frozen=True)
class Report:
    readings: int
    target_band: str
    min_n: int
    groups: tuple[Group, ...]
    proposals: tuple[Proposal, ...]
    unmatched: tuple[Group, ...]


def _agrees(scheme: LevelScheme, group_token: str, majority: str, target_band: str) -> bool:
    band = scheme.levels.get(group_token)
    if band is None or majority == "unclear":
        return False
    return (BAND_ORDER[band] > BAND_ORDER[target_band]) == (majority == "no")


def _majority(answers: Counter[str]) -> tuple[str, int]:
    (top, top_n), *rest = answers.most_common()
    if rest and rest[0][1] == top_n:
        return "unclear", top_n
    return top, top_n


def build_report(
    readings: Iterable[Reading],
    catalog: LevelingCatalog,
    field: str | None,
    target_band: str,
    min_n: int = DEFAULT_MIN_N,
) -> Report:
    """Group `readings` by (board, trailing token) and propose a scheme per board.

    A binding is per `(provider, slug)`, so evidence is never pooled across boards, even ones that
    share a company name. `min_n` decides only which groups are LISTED: every token a board shows,
    however few readings, must agree with a scheme for it to be proposed.
    """
    tier = field_tier(catalog, field)
    if tier is None:
        raise LevelingReportError(
            "leveling.yaml has no seniority tier for your field, so the gate reads no titles "
            "and there is nothing to propose a binding for"
        )
    answers: dict[tuple[str, str, str], Counter[str]] = defaultdict(Counter)
    labels: dict[tuple[str, str], str] = {}
    total = 0
    for reading in readings:
        total += 1
        token = trailing_level_token(reading.title)
        if token is None:
            continue
        # The title reads as plain entry unbound: only the token could say otherwise.
        band, _ = parse_seniority(reading.title, None, tier, catalog)
        if band != "entry":
            continue
        answers[(reading.provider, reading.slug, token)][reading.seniority_fit] += 1
        labels[(reading.provider, reading.slug)] = reading.company

    # A LISTED group weaker than a unanimous one at `min_n` is mixed: no scheme agrees with it.
    # A group below `min_n` is not listed, but the scheme must agree with every one of its readings.
    bar = wilson_lower(min_n, min_n)
    groups: list[Group] = []
    common: dict[tuple[str, str], list[str]] = {}
    for (provider, slug, token), counts in answers.items():
        if not token.isdigit():
            continue  # a roman numeral is read without a binding: it can neither bind nor veto
        n = sum(counts.values())
        majority, majority_n = _majority(counts)
        lower = wilson_lower(majority_n, n)
        listed = n >= min_n
        if listed:
            agreeing = [
                s.name for s in catalog.schemes.values()
                if lower >= bar and _agrees(s, token, majority, target_band)
            ]
            groups.append(Group(
                labels[(provider, slug)], provider, slug, token, n, majority, majority_n, lower,
                tuple(agreeing),
            ))
        else:
            # Too few readings to call a majority, so the scheme must agree with every one of
            # them: any reading it contradicts rules the board out. `unclear` contradicts nothing.
            agreeing = [
                s.name for s in catalog.schemes.values()
                if all(
                    _agrees(s, token, answer, target_band)
                    for answer in counts if answer != "unclear"
                )
            ]
        key = (provider, slug)
        common[key] = [s for s in common.get(key, list(catalog.schemes)) if s in agreeing]
    groups.sort(key=lambda g: (-g.n, g.company, g.provider, g.slug, g.token))

    listed_keys = {(g.provider, g.slug) for g in groups}
    proposals: list[Proposal] = []
    unmatched: list[Group] = []
    for key in sorted(listed_keys):
        if common[key]:
            proposals.append(Proposal(
                labels[key], key[0], key[1], common[key][0], tuple(common[key][1:])
            ))
        else:
            unmatched.extend(g for g in groups if (g.provider, g.slug) == key)
    # Roman groups are listed beside the numbers, for the reader. They bind nothing.
    for (provider, slug, token), counts in answers.items():
        n = sum(counts.values())
        if token.isdigit() or n < min_n:
            continue
        majority, majority_n = _majority(counts)
        groups.append(Group(
            labels[(provider, slug)], provider, slug, token, n, majority, majority_n,
            wilson_lower(majority_n, n), (),
        ))
    groups.sort(key=lambda g: (-g.n, g.company, g.provider, g.slug, g.token))
    return Report(total, target_band, min_n, tuple(groups), tuple(proposals), tuple(unmatched))


def _scalar(value: str) -> str:
    """A YAML double-quoted scalar, so a slug like `on` or `1e3` loads as the string it is."""
    return json.dumps(value, ensure_ascii=False)


def render(report: Report) -> str:
    """The report as text: every group, the unmatched ones, then a block to paste."""
    lines = [
        f"{report.readings} readings under the current judge identity "
        f"(target band: {report.target_band}); groups with n >= {report.min_n}:",
        "",
        f"{'company':<24} {'token':<5} {'n':>4}  {'majority':<9} {'share':>9} {'lower95':>8}  "
        f"{'scheme':<20} board",
    ]
    for g in report.groups:
        answer = {"yes": "in band", "no": "above", "unclear": "unclear"}[g.majority]
        if not g.token.isdigit():
            fits = "(no binding needed)"
        elif g.schemes:
            fits = ", ".join(g.schemes)
        else:
            fits = "UNMATCHED"
        lines.append(
            f"{g.company[:24]:<24} {g.token:<5} {g.n:>4}  {answer:<9} "
            f"{g.majority_n:>4}/{g.n:<4} {g.lower:>8.2f}  {fits:<20} {g.provider}/{g.slug}"
        )
    if report.unmatched:
        lines += [
            "",
            "UNMATCHED (no shipped scheme agrees with every token the board shows; "
            "never forced):",
        ]
        lines += [f"  {g.company} {g.token} ({g.provider}/{g.slug})" for g in report.unmatched]
    lines += ["", "# leveling-bindings.yaml (review each line before pasting):", "bindings:"]
    for p in report.proposals:
        note = f"  # {p.company}" + (f"; also consistent: {', '.join(p.also)}" if p.also else "")
        lines.append(
            f"  - {{provider: {_scalar(p.provider)}, slug: {_scalar(p.slug)}, "
            f"scheme: {_scalar(p.scheme)}}}{note}"
        )
    if not report.proposals:
        lines.append("  []")
    return "\n".join(lines)


def current_readings(engine: Engine, settings: Settings) -> tuple[list[Reading], str]:
    """The newest reading per posting under the CURRENT judge identity, and the target band."""
    with engine.connect() as conn:
        profile = get_profile(conn)
        if profile is None:
            raise LevelingReportError("no profile in the store; nothing was judged for anyone")
        band = str(profile.target_seniority_band or "any")
        if band == "any":
            raise LevelingReportError(
                "target_seniority_band is `any`, so the judge was never asked about seniority"
            )
        try:
            facts = engine_facts(profile.eligibility_facts_json, settings.config_dir)
        except ProfileRowInvalid as exc:
            raise LevelingReportError(f"profile row unusable: {exc.column}: {exc.reason}") from exc
        scope = gate_judge_identity(
            facts, model=settings.gate.model, effort=gate_effort_key(settings.gate.effort),
            target_band=band,
        )
        e = eligibility_evaluations
        stmt = (
            select(
                postings.c.id, posting_versions.c.id, postings.c.title, companies.c.name,
                companies.c.provider, companies.c.slug,
                func.json_extract(e.c.raw_output_json, "$.gate_verdict.seniority_fit"),
            )
            .join(eligibility_inputs, e.c.input_id == eligibility_inputs.c.id)
            .join(
                posting_versions,
                eligibility_inputs.c.posting_version_id == posting_versions.c.id,
            )
            .join(postings, posting_versions.c.posting_id == postings.c.id)
            .join(companies, postings.c.company_id == companies.c.id)
            .where(*scope)
            .order_by(e.c.id.desc())
        )
        rows = conn.execute(stmt).all()
        current = current_posting_version_ids(conn, sorted({int(r[0]) for r in rows}))
        seen: set[int] = set()
        readings: list[Reading] = []
        for posting_id, version_id, title, name, provider, slug, fit in rows:
            if posting_id in seen or current.get(int(posting_id)) != version_id:
                continue
            seen.add(posting_id)
            if fit is not None:
                readings.append(Reading(provider, slug, name or "", title or "", str(fit)))
    return readings, band


def leveling_report(engine: Engine, settings: Settings, min_n: int = DEFAULT_MIN_N) -> str:
    """The whole report for a store opened read-only."""
    readings, band = current_readings(engine, settings)
    catalog = load_leveling(Path(settings.config_dir))
    field = declared_field(load_role_taxonomy(settings.config_dir))
    return render(build_report(readings, catalog, field, band, min_n))

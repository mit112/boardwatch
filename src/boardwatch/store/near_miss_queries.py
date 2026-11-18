"""The near-miss list (T303): postings blocked by exactly one unmet requirement, grouped by rule.

A NEAR-MISS is an open posting whose current deterministic evaluation holds exactly one blocking
unmet requirement row and no blocking abstain. "Blocking" is the engine's own test: the row is
`required` and its family is a `blocker` in the profile's policy (`engine.evaluate`'s roll-up), so
a `preferred` row or an `ignore`d family never counts. A posting with one blocking unmet row AND a
blocking abstain (`unknown`) is NOT a near-miss: an abstain is not a pass, so it is counted apart
(`with_abstain`) and never folded into the near-miss number.

The cohort is narrowed to postings that would be real leads but for that one requirement. Over all
770k open postings, one blocking unmet row alone matches 219,645, most of them roles the ranker
would never show (a senior title, a hardware job, an office abroad). The caller passes the
pipeline's own title and location decision as `gate`; a posting it vetoes is counted in
`gated_out` by clause and left out of every other number. The gate runs only on the postings that
already have one blocking unmet row (the same conjunction, in the order that reads the fewest
posting rows: a `postings` row carries the body text, and reading one costs a disk page).

Only `ineligible` evaluations can hold a blocking unmet row, so the first pass reads those and
nothing else. Requirement rows are read by `evaluation_id` in chunks; the quoted span is sliced from
the evaluated posting version's frozen body, as the audit view does, for the few sample rows only.

Read-only. No timestamp is compared here. "Current version" and "current evaluation" are
`run_funnel_queries._current_identity_evaluations`, the one definition the funnel counts with.

Cost, measured on the live store (50 GB, 770k open postings), cold: about 50 s for the current
evaluation of every open posting (the funnel's own join, three covering-index probes per posting;
it is the same with the verdict column dropped, so the cost is the probes), 7 s for the 733k
requirement rows of the 373k blocked evaluations, and the rest for the 219k posting rows the gate
reads. 95 to 125 s in all, which is why the result is held.

The result is memoised in process. Its key is the store file (path and inode), the latest finished
run, the newest evaluation id, the profile and rules hashes and the caller's `gate_key` (what the
gate was built from). Company NAMES are never memoised: they are read fresh for the rows shown.
"""

from __future__ import annotations

import os
import threading
from collections import Counter, defaultdict, deque
from collections.abc import Callable, Hashable, Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Connection, Engine, func, select

from boardwatch.store.param_chunks import id_chunks
from boardwatch.store.run_funnel_queries import _current_identity_evaluations
from boardwatch.store.tables import (
    companies,
    eligibility_evaluations,
    eligibility_requirements,
    posting_versions,
    postings,
    runs,
)

#: Rules shown, requirement texts shown per rule, and sample postings per rule.
RULES_SHOWN = 25
TEXTS_SHOWN = 4
SAMPLES = 3

#: (title, locations, remote_policy) -> the clause that vetoed the posting, or None when it passes.
Gate = Callable[[str, Sequence[str], str], str | None]


@dataclass(frozen=True)
class _Candidate:
    """An open posting with exactly one blocking unmet row."""

    posting_id: int
    company_id: int
    version_id: int
    requirement_id: int
    rule_id: str
    text: str
    abstains: bool


@dataclass(frozen=True)
class _Sample:
    candidate: _Candidate
    title: str


@dataclass(frozen=True)
class _Aggregate:
    """Everything keyed by id; no company name is held."""

    blocked: int
    one_unmet: int
    near_misses: int
    with_abstain: int
    gated_out: tuple[tuple[str, int], ...]
    rules: tuple[tuple[str, int, int, tuple[tuple[str, int], ...], tuple[_Sample, ...]], ...]
    quotes: tuple[tuple[int, str], ...]


def _family(rule_id: str | None) -> str:
    return (rule_id or "").split(":", 1)[0]


def _candidates(
    conn: Connection,
    *,
    profile_hash: str,
    rules_hash: str,
    engine_kind: str,
    engine_version: str,
    blocking: frozenset[str],
) -> tuple[int, list[_Candidate]]:
    """(open postings whose current verdict is `ineligible`, those with ONE blocking unmet row)."""
    stmt = (
        _current_identity_evaluations(
            profile_hash=profile_hash,
            rules_hash=rules_hash,
            engine_kind=engine_kind,
            engine_version=engine_version,
        )
        .add_columns(
            eligibility_evaluations.c.id.label("evaluation_id"),
            posting_versions.c.id.label("version_id"),
        )
        .where(eligibility_evaluations.c.verdict == "ineligible")
    )
    blocked = 0
    found: list[_Candidate] = []
    # Partitions of the cursor, never one list of 700k rows: each is joined to its requirements.
    for part in conn.execute(stmt).partitions(500):
        blocked += len(part)
        by_eval = {int(r.evaluation_id): r for r in part}
        unmet: dict[int, list[Any]] = defaultdict(list)
        abstains: set[int] = set()
        for chunk in id_chunks(list(by_eval)):
            for row in conn.execute(
                select(
                    eligibility_requirements.c.id,
                    eligibility_requirements.c.evaluation_id,
                    eligibility_requirements.c.rule_id,
                    eligibility_requirements.c.requirement_text,
                    eligibility_requirements.c.disposition,
                ).where(
                    eligibility_requirements.c.evaluation_id.in_(chunk),
                    eligibility_requirements.c.requiredness == "required",
                    eligibility_requirements.c.disposition.in_(("unmet", "unknown")),
                )
            ):
                if _family(row.rule_id) not in blocking:
                    continue
                if row.disposition == "unmet":
                    unmet[int(row.evaluation_id)].append(row)
                else:
                    abstains.add(int(row.evaluation_id))
        for evaluation_id, rows in unmet.items():
            if len(rows) != 1:
                continue
            row, src = rows[0], by_eval[evaluation_id]
            found.append(
                _Candidate(
                    posting_id=int(src.posting_id),
                    company_id=int(src.company_id),
                    version_id=int(src.version_id),
                    requirement_id=int(row.id),
                    rule_id=str(row.rule_id),
                    text=str(row.requirement_text),
                    abstains=evaluation_id in abstains,
                )
            )
    return blocked, found


def _aggregate(
    conn: Connection,
    *,
    profile_hash: str,
    rules_hash: str,
    engine_kind: str,
    engine_version: str,
    blocking: frozenset[str],
    gate: Gate,
) -> _Aggregate:
    blocked, candidates = _candidates(
        conn,
        profile_hash=profile_hash,
        rules_hash=rules_hash,
        engine_kind=engine_kind,
        engine_version=engine_version,
        blocking=blocking,
    )
    # Ascending posting id: neighbouring rows share disk pages, and the samples are then the
    # newest postings (ids only grow) rather than whatever the cursor happened to yield last.
    candidates.sort(key=lambda c: c.posting_id)
    gated_out: Counter[str] = Counter()
    clean: Counter[str] = Counter()
    abstaining: Counter[str] = Counter()
    texts: dict[str, Counter[str]] = defaultdict(Counter)
    samples: dict[str, deque[_Sample]] = defaultdict(lambda: deque(maxlen=SAMPLES))
    for chunk in id_chunks(candidates):
        wanted = {c.posting_id: c for c in chunk}
        for row in conn.execute(
            select(
                postings.c.id,
                postings.c.title,
                postings.c.locations_json,
                postings.c.remote_policy,
            ).where(postings.c.id.in_(list(wanted)))
        ):
            candidate = wanted[int(row.id)]
            locations = [str(loc) for loc in (row.locations_json or [])]
            veto = gate(str(row.title), locations, str(row.remote_policy))
            if veto is not None:
                gated_out[veto] += 1
            elif candidate.abstains:
                abstaining[candidate.rule_id] += 1
            else:
                clean[candidate.rule_id] += 1
                texts[candidate.rule_id][candidate.text] += 1
                samples[candidate.rule_id].append(_Sample(candidate, str(row.title)))

    rules = sorted(
        set(clean) | set(abstaining), key=lambda rule: (-clean[rule], -abstaining[rule], rule)
    )
    shown = rules[:RULES_SHOWN]
    quotes = _quotes(conn, [s for rule in shown for s in samples[rule]])
    return _Aggregate(
        blocked=blocked,
        one_unmet=len(candidates),
        near_misses=sum(clean.values()),
        with_abstain=sum(abstaining.values()),
        gated_out=tuple(sorted(gated_out.items(), key=lambda kv: (-kv[1], kv[0]))),
        rules=tuple(
            (
                rule,
                clean[rule],
                abstaining[rule],
                tuple(
                    sorted(texts[rule].items(), key=lambda kv: (-kv[1], kv[0]))[:TEXTS_SHOWN]
                ),
                tuple(reversed(samples[rule])),  # newest first
            )
            for rule in shown
        ),
        quotes=quotes,
    )


def _quotes(conn: Connection, shown: list[_Sample]) -> tuple[tuple[int, str], ...]:
    """requirement id -> the span of the evaluated version's frozen body that the row quotes."""
    out: list[tuple[int, str]] = []
    for sample in shown:
        c = sample.candidate
        locator = conn.execute(
            select(eligibility_requirements.c.jd_locator_json).where(
                eligibility_requirements.c.id == c.requirement_id
            )
        ).scalar_one()
        body = conn.execute(
            select(posting_versions.c.body_text).where(posting_versions.c.id == c.version_id)
        ).scalar_one()
        start, end = locator["span"]
        out.append((c.requirement_id, str(body)[int(start) : int(end)]))
    return tuple(out)


_Key = tuple[str, int | None, int | None, int | None, str, str, str, Hashable]
_memo: tuple[_Key, _Aggregate] | None = None
_compute_lock = threading.Lock()


def _inode(engine: Engine) -> int | None:
    """The store file's inode: a path alone cannot tell a replaced file from the one it replaced."""
    path = engine.url.database
    if not path or path == ":memory:":
        return None
    try:
        return os.stat(path.removeprefix("file:")).st_ino
    except OSError:
        return None


def _memo_key(
    conn: Connection, profile_hash: str, rules_hash: str, engine_version: str, gate_key: Hashable
) -> _Key:
    return (
        conn.engine.url.render_as_string(hide_password=True),
        _inode(conn.engine),
        conn.execute(select(func.max(runs.c.id)).where(runs.c.finished_at.is_not(None))).scalar(),
        conn.execute(select(func.max(eligibility_evaluations.c.id))).scalar(),
        profile_hash,
        rules_hash,
        engine_version,
        gate_key,
    )


def near_misses(
    conn: Connection,
    *,
    profile_hash: str,
    rules_hash: str,
    engine_kind: str,
    engine_version: str,
    blocking: frozenset[str],
    gate: Gate,
    gate_key: Hashable,
) -> dict[str, Any]:
    global _memo

    def compute() -> _Aggregate:
        return _aggregate(
            conn,
            profile_hash=profile_hash,
            rules_hash=rules_hash,
            engine_kind=engine_kind,
            engine_version=engine_version,
            blocking=blocking,
            gate=gate,
        )

    if _inode(conn.engine) is None:
        # No stat-able store file: nothing tells one store from another, so never memoise.
        base = compute()
    else:
        key = _memo_key(conn, profile_hash, rules_hash, engine_version, gate_key)
        # The lock makes a second page load wait for the first one's answer instead of starting
        # its own pass over the same rows. The key and the payload tested and returned are one
        # tuple, read once.
        with _compute_lock:
            held = _memo
            if held is not None and held[0] == key:
                base = held[1]
            else:
                base = compute()
                _memo = (key, base)

    quotes = dict(base.quotes)
    company_ids = sorted({s.candidate.company_id for _, _, _, _, ss in base.rules for s in ss})
    names = {
        int(r.id): str(r.name)
        for r in conn.execute(
            select(companies.c.id, companies.c.name).where(companies.c.id.in_(company_ids))
        )
    }
    return {
        "blocked": base.blocked,
        "one_unmet": base.one_unmet,
        "near_misses": base.near_misses,
        "with_abstain": base.with_abstain,
        "gated_out": [{"clause": clause, "count": n} for clause, n in base.gated_out],
        "rules": [
            {
                "rule_id": rule,
                "count": count,
                "with_abstain": abstain,
                "requirements": [{"text": text, "count": n} for text, n in texts],
                "samples": [
                    {
                        "posting_id": s.candidate.posting_id,
                        "title": s.title,
                        "company": names.get(s.candidate.company_id, ""),
                        "requirement": s.candidate.text,
                        "quote": quotes[s.candidate.requirement_id],
                    }
                    for s in samples
                ],
            }
            for rule, count, abstain, texts, samples in base.rules
        ],
    }

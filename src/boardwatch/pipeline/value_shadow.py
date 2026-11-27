"""T366: the value model's shadow — P(good) recorded beside every gate candidate, ordering nothing.

The judge has written thousands of readings under its current identity. At the start of a gate
run this trains `rank.value_model` on them, BEFORE the run's own judge calls, so what the run
then judges is out-of-sample. Each gate pool reports its candidates here (`observe_*`), and after
the run `finish` writes `value-shadow-<run>.json` beside the funnel: for every candidate its
existing position, P(good) and rank by P(good); the first-seen postings scored per board (the
rate T341's amendment reads); and, on the run's own judged items, the model's AUC and
precision against the existing order.

**Nothing reads the score back.** It is never an input to a rule, a lane, a disposition, a ledger
row or a hash, so it cannot become, change or count as a verdict or an abstain (the keystone
invariant), and the gate's order is the same with the model on or off. A user with too few
readings gets no model and no scores — the file says why — never a model that scores zeros.
Every method here is reporting: a failure is held and raised by `finish`, which the caller
records like the near-miss report's failure, and no method raises into the gate.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from time import perf_counter

from sqlalchemy import Connection, Engine, func, select
from sqlalchemy.sql.elements import ColumnElement

from boardwatch.core.settings import Settings
from boardwatch.eligibility.facts import ProfileRowInvalid
from boardwatch.eligibility.final_gate import (
    gate_effort_key,
    gate_engine_version,
    gate_facts_key,
)
from boardwatch.eligibility.preflight import engine_facts
from boardwatch.eligibility.read import gate_judge_identity
from boardwatch.rank.value_model import (
    BODY_CHARS,
    HASH_BUCKETS,
    Document,
    ValueModel,
    auc,
    feature_indices,
    top_half_precision,
    train,
)
from boardwatch.store.param_chunks import id_chunks
from boardwatch.store.queries import current_posting_versions, first_seen_since_clause, get_profile
from boardwatch.store.tables import (
    companies,
    eligibility_evaluations,
    eligibility_inputs,
    posting_versions,
    postings,
    runs,
)

VALUE_SHADOW_PREFIX = "value-shadow-"

#: How many candidates beyond the backlog's budget, in the backlog's own order, are scored too.
#: The backlog sends `gate.backlog_budget` of a list of tens of thousands; scoring only what it
#: sends could never say what a better pick of the same size would have held. Four budgets of
#: lookahead (600 at the 150 the maintainer runs) is the cheapest pool in which the model's top
#: `budget` can differ from the batch, at about a second of scoring.
BACKLOG_LOOKAHEAD_BUDGETS = 4
#: The model trains on at most this many of the NEWEST readings, so load plus fit stops growing
#: with the store's history. On the benchmark's time split the newest 8,000 give AUC 0.878 and
#: all 10,574 give the same; 4,000 give 0.865. A `gate.value_model_min_readings` above it
#: raises the cap to that minimum, so a configured floor can never make training impossible.
TRAIN_READINGS_CAP = 8_000
#: Below this many judged items in one pool the per-run precision comparison is not reported:
#: the benchmark skipped runs under 20 for the same reason.
MIN_ITEMS_FOR_PRECISION = 20
#: Scoring the postings first seen this run stops at this many seconds, and the file says so
#: (`arrivals.complete`): a fleet that grows by a hundred thousand postings must not turn a
#: shadow into a stage.
ARRIVAL_BUDGET_SECONDS = 120.0

_POOLS = ("slate", "refresh", "backlog")


@dataclass(frozen=True)
class Reading:
    """One posting's latest reading under the judge's current identity."""

    eval_id: int
    run_id: int | None
    posting_id: int
    good: bool
    indices: Sequence[int]


def _is_good(raw: object, target_band: str) -> bool | None:
    """The label: the judge cleared the posting (`eligible`) AND read its seniority `yes`. Under
    target band `any` the judge is not asked about seniority (`gate_judge`'s `seniority_asked`),
    so the label is `eligible` alone. None when the row carries no gate decision."""
    gate = raw.get("gate_verdict") if isinstance(raw, dict) else None
    if not isinstance(gate, dict) or gate.get("decision") is None:
        return None
    return gate["decision"] == "eligible" and (
        target_band == "any" or gate.get("seniority_fit") == "yes"
    )


def load_readings(
    conn: Connection, scope: Sequence[ColumnElement[bool]], target_band: str,
    *extra: ColumnElement[bool], limit: int | None = None,
) -> list[Reading]:
    """The newest reading per posting under `scope` (`gate_judge_identity`), oldest first, with
    its features, for at most the newest `limit` postings (the walk stops there, so neither the
    body reads nor the feature work grow past it). Streams, keeping only hashed indices, so a
    body never outlives its row."""
    e = eligibility_evaluations
    stmt = (
        select(
            e.c.id, e.c.run_id, e.c.raw_output_json, postings.c.id.label("posting_id"),
            postings.c.title, companies.c.name, companies.c.provider,
            func.substr(posting_versions.c.body_text, 1, BODY_CHARS).label("body"),
        )
        .join(eligibility_inputs, e.c.input_id == eligibility_inputs.c.id)
        .join(posting_versions, eligibility_inputs.c.posting_version_id == posting_versions.c.id)
        .join(postings, posting_versions.c.posting_id == postings.c.id)
        .join(companies, postings.c.company_id == companies.c.id)
        .where(*scope, *extra)
        .order_by(e.c.id.desc())
    )
    seen: set[int] = set()
    readings: list[Reading] = []
    for row in conn.execute(stmt):
        if limit is not None and len(readings) >= limit:
            break
        if row.posting_id in seen:
            continue
        seen.add(row.posting_id)
        good = _is_good(row.raw_output_json, target_band)
        if good is None:
            continue
        doc = Document(row.title or "", row.name or "", row.provider, row.body or "")
        readings.append(
            Reading(int(row.id), row.run_id, int(row.posting_id), good, feature_indices(doc))
        )
    readings.reverse()
    return readings


def judged_labels(
    conn: Connection, scope: Sequence[ColumnElement[bool]], target_band: str, run_id: int
) -> dict[int, bool]:
    """posting_id -> good, for the readings `run_id` itself wrote under `scope` (no bodies)."""
    e = eligibility_evaluations
    stmt = (
        select(e.c.raw_output_json, posting_versions.c.posting_id)
        .join(eligibility_inputs, e.c.input_id == eligibility_inputs.c.id)
        .join(posting_versions, eligibility_inputs.c.posting_version_id == posting_versions.c.id)
        .where(*scope, e.c.run_id == run_id)
        .order_by(e.c.id)
    )
    labels: dict[int, bool] = {}
    for row in conn.execute(stmt):
        good = _is_good(row.raw_output_json, target_band)
        if good is not None:
            labels[int(row.posting_id)] = good
    return labels


def _documents(conn: Connection, posting_ids: Sequence[int]) -> dict[int, Document]:
    """posting_id -> what the features read, from the posting's current version."""
    bodies = current_posting_versions(conn, list(posting_ids))
    out: dict[int, Document] = {}
    for chunk in id_chunks(list(posting_ids)):
        for row in conn.execute(
            select(postings.c.id, postings.c.title, companies.c.name, companies.c.provider)
            .join(companies, postings.c.company_id == companies.c.id)
            .where(postings.c.id.in_(chunk))
        ):
            version = bodies.get(int(row.id))
            if version is not None:
                out[int(row.id)] = Document(
                    row.title or "", row.name or "", row.provider, version.body_text
                )
    return out


class ValueShadow:
    """One run's shadow. `start` trains (or records why not); `observe_*` note each pool's
    candidates in the order the gate will send them and `sent_*` the ids each call actually
    carried; `finish` scores, measures and writes."""

    def __init__(self, settings: Settings, run_id: int) -> None:
        self._settings = settings
        self._run_id = run_id
        self._model: ValueModel | None = None
        self._scope: list[ColumnElement[bool]] = []
        self._target_band = ""
        self._header: dict[str, object] = {"trained": False}
        self._observed: dict[str, list[int]] = {}  # pool -> candidates, in the pool's own order
        self._sent: dict[str, list[int]] = {pool: [] for pool in _POOLS}
        self._walked: dict[str, int] = {pool: 0 for pool in _POOLS}  # candidates the gate consumed
        self._error: Exception | None = None

    # -- before the judge ---------------------------------------------------------------

    def start(self, engine: Engine) -> None:
        """Train on the readings written before this run began. Never raises."""
        try:
            self._train(engine)
        except Exception as exc:  # noqa: BLE001 - reporting must never reach the gate
            self._model = None
            self._error = exc

    def _train(self, engine: Engine) -> None:
        settings = self._settings
        began = perf_counter()
        with engine.connect() as conn:
            profile = get_profile(conn)
            if profile is None:
                self._header["reason"] = "no profile"
                return
            try:
                facts = engine_facts(profile.eligibility_facts_json, settings.config_dir)
            except ProfileRowInvalid:
                self._header["reason"] = "profile facts unreadable"
                return
            self._target_band = profile.target_seniority_band
            effort = gate_effort_key(settings.gate.effort)
            self._scope = gate_judge_identity(
                facts, model=settings.gate.model, effort=effort, target_band=self._target_band
            )
            self._header["identity"] = {
                "engine_version": gate_engine_version(),
                "model": settings.gate.model,
                "effort": effort,
                "target_band": self._target_band,
                "facts_key": gate_facts_key(facts),
            }
            started = conn.execute(
                select(runs.c.started_at).where(runs.c.id == self._run_id)
            ).scalar_one()
            minimum = settings.gate.value_model_min_readings
            cap = max(TRAIN_READINGS_CAP, minimum)
            readings = load_readings(
                conn, self._scope, self._target_band,
                eligibility_evaluations.c.created_at < started, limit=cap,
            )
        loaded = perf_counter()
        self._header["readings"] = len(readings)
        self._header["capped"] = len(readings) >= cap
        self._header["min_readings"] = minimum
        if len(readings) < minimum:
            self._header["reason"] = "too few readings under the current judge"
            return
        self._model = train([r.indices for r in readings], [r.good for r in readings])
        self._header.update(
            trained=True, good_readings=sum(r.good for r in readings), buckets=HASH_BUCKETS,
            load_seconds=round(loaded - began, 1), train_seconds=round(perf_counter() - loaded, 1),
        )

    # -- the gate's pools ---------------------------------------------------------------

    def observe_slate(self, posting_ids: Sequence[int]) -> None:
        self._observe("slate", posting_ids)

    def observe_refresh(self, posting_ids: Sequence[int]) -> None:
        self._observe("refresh", posting_ids)

    def observe_backlog(self, posting_ids: Sequence[int]) -> None:
        self._observe("backlog", posting_ids)

    def sent_slate(self, posting_ids: Sequence[int]) -> None:
        # No walk count: a slate lead the gate did not send was usually already judged, which is
        # not a refusal.
        self._note_sent("slate", posting_ids, 0)

    def sent_refresh(self, posting_ids: Sequence[int], walked: int) -> None:
        self._note_sent("refresh", posting_ids, walked)

    def sent_backlog(self, posting_ids: Sequence[int], walked: int) -> None:
        self._note_sent("backlog", posting_ids, walked)

    def _observe(self, pool: str, posting_ids: Sequence[int]) -> None:
        if self._model is None:
            return
        try:
            self._observed[pool] = [int(p) for p in posting_ids]
        except Exception as exc:  # noqa: BLE001 - reporting must never reach the gate
            self._error = self._error or exc

    def _note_sent(self, pool: str, posting_ids: Sequence[int], walked: int) -> None:
        if self._model is None:
            return
        try:
            self._sent[pool] += [int(p) for p in posting_ids]
            self._walked[pool] = max(self._walked[pool], int(walked))
        except Exception as exc:  # noqa: BLE001 - reporting must never reach the gate
            self._error = self._error or exc

    def _scored_pool(self, pool: str) -> tuple[list[int], set[int]]:
        """(the pool's candidates worth scoring, in the pool's order; those the gate passed over).

        Worth scoring: the slate whole, the refresh's budget and the backlog's budget plus its
        lookahead, as a prefix of the observed order, and every id the gate actually SENT, which
        can lie past the prefix when it refused items on the way. Passed over: a candidate the
        walk consumed (the first `walked` of the observed order) that was not sent, which the
        send boundary refused (a body it withholds, a lead with no current version) - wherever it
        sits, including after the last send. The model must not count it among its own top
        picks. A candidate the walk never reached is not passed over."""
        observed = self._observed.get(pool, [])
        settings = self._settings
        keep = {
            "slate": len(observed),
            "refresh": settings.gate.refresh_budget,
            "backlog": settings.gate.backlog_budget * (1 + BACKLOG_LOOKAHEAD_BUDGETS),
        }[pool]
        sent = set(self._sent[pool])
        passed_over = {p for p in observed[: self._walked[pool]] if p not in sent}
        return [p for i, p in enumerate(observed) if i < keep or p in sent], passed_over

    # -- after the run ------------------------------------------------------------------

    def finish(self, engine: Engine, day_dir: Path) -> Path | None:
        """Write `value-shadow-<run>.json` beside the funnel; None when this run has nothing to
        report. Raises what `start` or this method hit, for the caller to record."""
        if self._error is not None:
            raise self._error
        if "readings" not in self._header and "reason" not in self._header:
            return None  # `start` never ran
        report: dict[str, object] = {"version": 1, "run_id": self._run_id, **self._header}
        if self._model is None:
            detail = (
                f"{self._header['readings']} readings under the current judge "
                f"(need {self._header['min_readings']})"
                if "readings" in self._header
                else self._header["reason"]
            )
            report["summary_line"] = f"value model (shadow): not trained, {detail}"
        else:
            report.update(self._measure(engine))
        day_dir.mkdir(parents=True, exist_ok=True)
        target = day_dir / f"{VALUE_SHADOW_PREFIX}{self._run_id}.json"
        partial = target.with_suffix(".json.partial")
        partial.write_text(json.dumps(report) + "\n", encoding="utf-8")
        partial.replace(target)  # atomic: a reader never sees a half-written file
        return target

    def _measure(self, engine: Engine) -> dict[str, object]:
        model = self._model
        assert model is not None
        pools = {pool: self._scored_pool(pool) for pool in _POOLS}
        ids = sorted({p for members, _ in pools.values() for p in members})
        with engine.connect() as conn:
            documents = _documents(conn, ids)
            labels = judged_labels(conn, self._scope, self._target_band, self._run_id)
            started = conn.execute(
                select(runs.c.started_at).where(runs.c.id == self._run_id)
            ).scalar_one()
            arrivals = self._arrivals(conn, model, started)
        scores = {p: model.score(feature_indices(d)) for p, d in documents.items()}

        records: list[dict[str, object]] = []
        for pool, (members, passed_over) in pools.items():
            position = {p: i for i, p in enumerate(self._observed.get(pool, []))}
            scored = [p for p in members if p in scores]
            by_p = sorted(scored, key=lambda p: (-scores[p], position[p]))
            rank = {p: i + 1 for i, p in enumerate(by_p)}
            sent = set(self._sent[pool])
            records += [
                {
                    "posting_id": p, "pool": pool, "position": position[p],
                    "sent": p in sent, "passed_over": p in passed_over,
                    "p_good": round(scores[p], 4), "rank_by_p": rank[p],
                }
                for p in scored
            ]
        realized = self._realized(scores, labels, pools)
        return {
            "summary_line": _summary_line(self._header, realized),
            "realized": realized,
            "candidates": records,
            "arrivals": arrivals,
        }

    def _realized(
        self, scores: dict[int, float], labels: dict[int, bool],
        pools: dict[str, tuple[list[int], set[int]]],
    ) -> dict[str, object]:
        """The run's own judged items: what the model said before the judge answered."""
        judged = {p for p in labels if p in scores}
        out: dict[str, object] = {"judged": len(judged)}
        out["auc"] = (
            auc([scores[p] for p in sorted(judged)], [labels[p] for p in sorted(judged)])
            if judged else None
        )
        slate = [p for p in self._observed.get("slate", []) if p in judged]
        position = {p: i for i, p in enumerate(self._observed.get("slate", []))}
        half = (
            top_half_precision(
                [scores[p] for p in slate], [labels[p] for p in slate],
                [position[p] for p in slate],
            )
            if len(slate) >= MIN_ITEMS_FOR_PRECISION else None
        )
        out["slate"] = {
            "judged": len(slate),
            "top_half_model": half[0] if half else None,
            "top_half_existing_order": half[1] if half else None,
        }
        # The backlog: what its budget was SPENT on is the requests the gate actually sent, which
        # can be more than the readings that came back (a failed or partial answer) and is not a
        # prefix of the candidates (a refused item is passed over). The model's own top picks of
        # the same size are chosen from the scored pool, minus what the gate refused.
        members, passed_over = pools["backlog"]
        sent = [p for p in self._sent["backlog"] if p in scores]
        batch = [p for p in sent if p in judged]
        back_position = {p: i for i, p in enumerate(self._observed.get("backlog", []))}
        best = sorted(
            (p for p in members if p in scores and p not in passed_over),
            key=lambda p: (-scores[p], back_position[p]),
        )[: len(sent)]
        out["backlog"] = {
            "sent": len(sent),
            "judged": len(batch),
            "scored": len([p for p in members if p in scores]),
            "realized_good_rate": _mean([labels[p] for p in batch]),
            "predicted_for_batch": _mean([scores[p] for p in batch]),
            "top_n": len(sent),
            "model_top_picks": best,
            "predicted_for_model_top_n": _mean([scores[p] for p in best]),
        }
        return out

    def _arrivals(
        self, conn: Connection, model: ValueModel, started: datetime
    ) -> dict[str, object]:
        """Every posting first seen this run, scored, summed per board (the rate T341's
        amendment reads). Stops at `ARRIVAL_BUDGET_SECONDS`, and says so."""
        deadline = perf_counter() + ARRIVAL_BUDGET_SECONDS
        stmt = (
            select(
                postings.c.company_id, companies.c.provider, companies.c.slug, postings.c.title,
                companies.c.name, func.substr(postings.c.body_text, 1, BODY_CHARS).label("body"),
            )
            .join(companies, postings.c.company_id == companies.c.id)
            .where(first_seen_since_clause(started))
            .order_by(postings.c.id)
        )
        boards: dict[int, dict[str, object]] = defaultdict(dict)
        scored = 0
        complete = True
        for row in conn.execute(stmt):
            if perf_counter() > deadline:
                complete = False
                break
            p = model.score(
                feature_indices(Document(row.title or "", row.name or "", row.provider, row.body))
            )
            board = boards[int(row.company_id)]
            if not board:
                board.update(company_id=int(row.company_id), provider=row.provider,
                             slug=row.slug, n=0, p_sum=0.0)
            board["n"] = int(board["n"]) + 1  # type: ignore[call-overload]
            board["p_sum"] = float(board["p_sum"]) + p  # type: ignore[arg-type]
            scored += 1
        for board in boards.values():
            board["p_sum"] = round(float(board["p_sum"]), 4)  # type: ignore[arg-type]
        return {"scored": scored, "complete": complete, "boards": list(boards.values())}


def _mean(values: Sequence[bool | float]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


def _pct(value: object) -> str:
    return "n/a" if not isinstance(value, float) else f"{value:.0%}"


def _summary_line(header: dict[str, object], realized: dict[str, object]) -> str:
    """The one line the morning reader prints verbatim."""
    slate = realized["slate"]
    backlog = realized["backlog"]
    assert isinstance(slate, dict) and isinstance(backlog, dict)
    area = realized["auc"]
    area_text = f"{area:.3f}" if isinstance(area, float) else "n/a"
    return (
        f"value model (shadow): trained on {header['readings']} readings, "
        f"n={realized['judged']} judged, AUC {area_text}, "
        f"top half model {_pct(slate['top_half_model'])} vs "
        f"ranker {_pct(slate['top_half_existing_order'])}, "
        f"backlog top-{backlog['top_n']} predicted {_pct(backlog['predicted_for_model_top_n'])} "
        f"realized {_pct(backlog['realized_good_rate'])}"
    )

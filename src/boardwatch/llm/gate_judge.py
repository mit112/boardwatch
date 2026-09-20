"""T42: the headless final-eligibility-gate judge stage on the daily path (D-477's "lever").

Routes through the EXISTING handshake — `eligibility.gate_handshake.build_gate_request` /
`apply_gate_verdicts`, which itself calls `eligibility.final_gate.record_gate_verdict` — rather
than a parallel path. This module's own job is narrow: decide which leads still need judging
(never re-judge a lead with a current gate row), invoke headless `claude` in batches of
`settings.gate.batch_size`, parse its output into `OracleVerdict`s, and fail OPEN at every seam
(D-074): a missing binary, any other failure to launch the process, a non-zero exit, a timeout,
unparseable JSON, an envelope that is not an object, an out-of-vocabulary `decision` or
`confidence`, a wrong item count, or a response with no usable evidence all drop that BATCH's
verdicts — never a real job — and are counted so the run reports them rather than looking
silently clean. Nothing here may reach `run_pipeline`'s outer handler: that sets `summary.fatal`
and re-raises BEFORE tailoring, so one malformed response would cost the day's whole slate.

`gate.enabled` defaults False (multi-tenancy): a caller must opt in before this spawns a single
subprocess.
"""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol, TypeVar

from sqlalchemy import Engine

from boardwatch.core.settings import Settings
from boardwatch.eligibility.catalog import RulesCatalog, load_rules
from boardwatch.eligibility.facts import ProfileRowInvalid, parse_facts, parse_policy
from boardwatch.eligibility.final_gate import gate_engine_version, gate_facts_key
from boardwatch.eligibility.gate_handshake import apply_gate_verdicts, build_gate_request
from boardwatch.eligibility.oracle import (
    _CONFIDENCE,
    _VERDICTS,
    OracleVerdict,
    OracleVerdictError,
    accept_oracle_verdict,
)
from boardwatch.eligibility.preflight import current_identity
from boardwatch.eligibility.read import current_gate_verdicts
from boardwatch.store.queries import CurrentVersion, current_posting_versions, get_profile


class _HasPostingId(Protocol):
    @property
    def posting_id(self) -> int: ...


#: Bound rather than a bare Protocol return type, so a caller passing `list[RankedPosting]`
#: gets `list[RankedPosting]` back (with `.company`/`.title`/... intact) instead of widening
#: to the Protocol's one declared attribute.
_T = TypeVar("_T", bound=_HasPostingId)


@dataclass(frozen=True)
class GateStageResult:
    """One run's tally from the gate stage. All-zero and `excluded_ids=()` is the honest
    reading both when the gate is off and when it is on but nothing needed judging — the
    caller (the pipeline) is the one that knows which of those it is, from `settings.gate.
    enabled`, and reports that separately (mirroring `DeathProbeReport`'s `None`-means-
    unmeasured split living one level up rather than inside this object).
    """

    judged: int = 0
    eligible: int = 0
    ineligible: int = 0
    uncertain: int = 0
    # Batches, not items — a batch of 13 that fails open costs at most 13 unjudged leads, and
    # the funnel reports the batch count so a reader can tell "the judge never ran" (batches ==
    # total batches) from "one bad response" (batches == 1).
    failed_open_batches: int = 0
    # Posting ids this run persisted a gate `ineligible` verdict for — the ONLY ones the caller
    # must drop from the slate before tailoring. Everything else (eligible, uncertain, unjudged
    # because already current) stays exactly where the ranker put it.
    excluded_ids: tuple[int, ...] = ()
    errors: tuple[str, ...] = ()


def _chunks(items: list[dict[str, object]], size: int) -> list[list[dict[str, object]]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _prompt(judging_policy: str, batch: list[dict[str, object]]) -> str:
    """Byte-shape-compatible with the calibration harness's prompt (2026-09-08 session,
    `calib_judge.sh`), which was run successfully against real headless `claude`. `slim` drops
    `bucket` — the judge sees `label`/`facts`/`jd_text` ONLY, never a hint about which bucket a
    posting fell in."""
    slim = [{k: item[k] for k in ("label", "facts", "jd_text")} for item in batch]
    count = len(batch)
    return (
        f"{judging_policy}\n\n"
        "OUTPUT CONTRACT: Judge every item below from its jd_text and facts ONLY. Output ONLY "
        f"a JSON array with exactly {count} objects, one per item in the same order, each of "
        'the form {"label": <the item\'s label>, "decision": "eligible"|"ineligible"|'
        '"uncertain", "reason": <a reason_catalog family id or null>, "evidence": <verbatim '
        'substring of jd_text, required when ineligible, else "">, "confidence": '
        '"high"|"medium"|"low", "seniority_fit": "yes"|"no"|"unclear"}. No prose before or '
        "after, no code fences.\n\n"
        f"ITEMS:\n{json.dumps(slim)}"
    )


def _call_claude(
    prompt: str, *, model: str, claude_config_dir: object, timeout_s: int
) -> str:
    """One headless call. Exactly the argv the 2026-09-08 calibration harness proved works:
    `claude -p --model <m> --tools "" --max-turns 1 --output-format json`, stdin `/dev/null`
    (never read — a batch prompt is a CLI arg, not stdin), `CLAUDE_CONFIG_DIR` from settings.

    Returns the raw stdout text. Raises on any failure the caller must fail open on
    (`FileNotFoundError` — binary missing; `subprocess.TimeoutExpired`; a non-zero exit,
    raised here as `subprocess.CalledProcessError` via `check=True` so every failure mode
    the caller must catch is an exception, never a magic return value; and any other
    process-launch `OSError` — EACCES, E2BIG, ENOMEM — which the caller catches as a family
    rather than by member, since the list of ways a launch can fail is the platform's).
    """
    env = dict(os.environ)
    if claude_config_dir is not None:
        env["CLAUDE_CONFIG_DIR"] = str(claude_config_dir)
    result = subprocess.run(  # noqa: S603 - argv is a fixed shape, no shell, no user input in argv[0]
        ["claude", "-p", "--model", model, "--tools", "", "--max-turns", "1",
         "--output-format", "json", prompt],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        env=env,
        timeout=timeout_s,
        check=True,
    )
    return result.stdout


def _unfence(text: str) -> str:
    """Strip ONE markdown code fence around the verdict array.

    The output contract says "no code fences" and the model emits them anyway. Measured on
    run 4, the first armed run: all four haiku batches returned ```json\n[...]\n``` and all
    four failed open on a JSONDecodeError at character 0 — the backtick — so an armed judge
    judged nothing and reported itself armed. The suite could not have caught it: the fake
    `claude` returned `json.dumps(verdicts)` with no fence, a shape the real model does not
    reliably produce.

    NARROW on purpose. Only a leading fence line and a trailing fence line are removed, and
    anything else still raises: a response this stage cannot read must fail OPEN rather than
    be coerced towards a verdict, which is the direction that would silently drop a real job.
    """
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if len(lines) < 2 or not lines[-1].strip().startswith("```"):
        return stripped
    return "\n".join(lines[1:-1])


#: The closed vocabulary the judge may answer `seniority_fit` in. Out-of-catalog is `"unclear"`,
#: the inert value — NOT a raise. Every other field in this parser fails the whole batch open
#: because it decides a VERDICT; this one only decides which lane a lead is delivered to, and a
#: gate that answered the six families correctly must not have its whole batch thrown away over a
#: tenth field it spelled oddly. The direction is the safe one either way: an unreadable answer
#: withholds nothing.
_SENIORITY_FIT = frozenset({"yes", "no", "unclear"})


def _seniority_fit(value: object) -> str:
    return str(value) if str(value) in _SENIORITY_FIT else "unclear"


def _in_vocabulary(value: object, vocabulary: frozenset[str], field: str) -> str:
    """The opposite direction to `_seniority_fit`, for the two fields that decide a VERDICT.

    `OracleVerdict` has no validating constructor, so before T106 `decision` was carried out of
    the batch boundary raw and refused only later — by `accept_oracle_verdict`, inside
    `run_gate_stage`'s write transaction, where an `OracleVerdictError` aborted the whole RUN
    rather than the batch. `confidence` was validated nowhere at all and persisted verbatim.
    Raising here, inside the boundary, is what makes a malformed item cost its batch (D-074).

    Returns the value UNCHANGED, not folded to lower case: `accept_oracle_verdict` does its own
    `.strip().lower()`, and normalizing here would silently change what gets persisted.
    """
    text = str(value)
    if text.strip().lower() not in vocabulary:
        raise OracleVerdictError(f"{field} {text!r} not in {sorted(vocabulary)}")
    return text


def _parse_verdicts(
    stdout: str, expected_labels: Sequence[str]
) -> tuple[list[OracleVerdict], tuple[str, ...]]:
    """The two-stage envelope `--output-format json` wraps every headless response in: the
    outer JSON's `result` key holds the model's text, which is itself the JSON array this
    stage asked for (2026-09-08 calibration harness, `calib/*/batch-*.json`). Raises
    (`json.JSONDecodeError`, `KeyError`, `TypeError`, `ValueError`, `OracleVerdictError`) on
    anything that does not conform — the caller treats every one of those as fail-open.

    Returns the verdicts the response carried and the labels it did NOT carry. Keyed on
    `label`, not on position or count: runs 45 and 48 (2026-09-09, -12) each lost a whole
    batch of 13 because the model answered 12 — one lead skipped — and an exact count check
    failed all 13 open. Every verdict names its lead and `apply_gate_verdicts` binds on that
    name, never on position, so the 12 are as sound as any batch's and only the skipped lead
    is left unjudged. The WHOLE batch still fails open on a label the batch never asked
    about, a label answered twice, or more verdicts than items: those are responses this
    stage cannot trust, and coercing one is the direction that drops a real job.
    """
    envelope = json.loads(stdout)
    if not isinstance(envelope, Mapping):
        # Established BEFORE any key is read: a top-level `[]` or `null` used to reach
        # `.get("is_error")` and raise `AttributeError`, which the caller does not catch.
        raise TypeError(f"expected a JSON object envelope, got {type(envelope).__name__}")
    if envelope.get("is_error"):
        raise ValueError(f"claude reported is_error: {envelope.get('result')!r}")
    result_text = envelope["result"]
    if not isinstance(result_text, str):
        raise TypeError(f"expected envelope['result'] to be a string, got {type(result_text)}")
    parsed = json.loads(_unfence(result_text))
    if not isinstance(parsed, list) or len(parsed) > len(expected_labels):
        raise ValueError(
            f"expected a JSON array of at most {len(expected_labels)} verdicts, got "
            f"{len(parsed) if isinstance(parsed, list) else type(parsed).__name__}"
        )
    verdicts = [
        OracleVerdict(
            label=str(item["label"]),
            decision=_in_vocabulary(item["decision"], _VERDICTS, "decision"),
            reason=item.get("reason"),
            evidence=str(item["evidence"]),
            confidence=_in_vocabulary(item["confidence"], _CONFIDENCE, "confidence"),
            seniority_fit=_seniority_fit(item.get("seniority_fit")),
        )
        for item in parsed
    ]
    answered = [verdict.label for verdict in verdicts]
    unknown = sorted(set(answered) - set(expected_labels))
    if unknown:
        raise ValueError(f"verdicts for labels the batch did not contain: {unknown}")
    if len(set(answered)) != len(answered):
        raise ValueError("the same label was answered more than once")
    missing = tuple(label for label in expected_labels if label not in set(answered))
    return verdicts, missing


def _judge_batch(
    batch: list[dict[str, object]], judging_policy: str, settings: Settings
) -> tuple[list[OracleVerdict] | None, str | None]:
    """Run one batch through headless claude. `(verdicts, None)` on success, `(None, note)`
    on any failure this stage must fail open on — a note describing WHAT failed, never a
    traceback, so the run's soft alert and funnel error line are readable — and
    `(verdicts, note)` when the response answered SOME of the batch: the note names the
    leads it skipped, which stay unjudged and on the slate exactly as a failed batch's do."""
    prompt = _prompt(judging_policy, batch)
    try:
        stdout = _call_claude(
            prompt,
            model=settings.gate.model,
            claude_config_dir=settings.gate.claude_config_dir,
            timeout_s=settings.gate.call_timeout_s,
        )
    except FileNotFoundError:
        return None, "claude binary not found on PATH"
    except subprocess.TimeoutExpired:
        return None, f"claude timed out after {settings.gate.call_timeout_s}s"
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()[:300]
        return None, f"claude exited {exc.returncode}: {stderr}"
    except OSError as exc:
        # Everything else `subprocess.run` can raise launching a process: EACCES on a binary
        # that is not executable, E2BIG on a batch whose argv exceeds the platform limit,
        # ENOMEM under fork. `FileNotFoundError` is an `OSError` too, so it is handled above
        # and keeps its own note; this is the readable fallback, never an escape.
        return None, f"claude could not be launched ({type(exc).__name__}, errno {exc.errno})"
    try:
        verdicts, missing = _parse_verdicts(stdout, [str(item["label"]) for item in batch])
    except (json.JSONDecodeError, KeyError, TypeError, ValueError, OracleVerdictError) as exc:
        return None, f"unusable response ({type(exc).__name__}): {exc}"
    if not verdicts:
        # An empty array answers NOBODY: that is the "judge never ran" shape the batch count
        # exists to make visible, not a partial answer, so it fails the whole batch open.
        return None, f"unusable response: the array carried none of the {len(batch)} verdicts"
    if missing:
        return verdicts, (
            f"{len(missing)} of {len(batch)} verdicts missing (labels {', '.join(missing)}); "
            "those leads were left unchanged, never dropped"
        )
    return verdicts, None


def _accepted(
    verdicts: list[OracleVerdict],
    versions: dict[int, CurrentVersion],
    catalog: RulesCatalog,
) -> tuple[list[OracleVerdict], list[str]]:
    """Drop, item by item, any verdict `accept_oracle_verdict` refuses — BEFORE the write
    transaction opens.

    Two writers run that same function and neither catches it: `apply_gate_verdicts` inside
    `with engine.begin()`, and `_tally_eligible_and_uncertain` AFTER that transaction has
    committed. An `OracleVerdictError` from either escapes the stage and aborts the run, which
    is the reverse of D-074's direction — and from the second site it does so with the batch
    already persisted. Running acceptance here first means neither site can raise, and one
    refused item costs its own lead rather than the good batches beside it.

    The body text is resolved exactly as both writers resolve it, so this pass sees what they
    will; a verdict naming no known version is accepted against `""`, since the only thing
    that raises is `decision` and the writers skip such a verdict anyway. Acceptance is pure,
    so both of them re-running it afterwards cannot diverge from what is decided here.
    """
    kept: list[OracleVerdict] = []
    refused: list[str] = []
    for verdict in verdicts:
        try:
            body = versions[int(verdict.label)].body_text
        except (KeyError, ValueError):
            body = ""
        try:
            accept_oracle_verdict(verdict, body, catalog)
        except OracleVerdictError as exc:
            refused.append(f"gate: verdict for lead {verdict.label} refused: {exc}")
            continue
        kept.append(verdict)
    return kept, refused


def run_gate_stage(
    engine: Engine,
    settings: Settings,
    leads: list[_T],
    *,
    run_id: int | None,
    shortlist_ranks: Mapping[int, int] | None = None,
) -> tuple[list[_T], GateStageResult]:
    """The whole stage: filter to leads that still need judging, judge them in batches,
    persist through the existing handshake, and hand back the slate minus anything this run
    persisted `ineligible`. `leads` is returned UNCHANGED (same list, same order minus
    exclusions) on every fail-open path — `gate.enabled=False`, no profile, or nothing left
    to judge all return the identity slate with an all-zero result.

    `shortlist_ranks` is supplied BY THE CALLER rather than derived from `leads`' order here,
    and that is the point: by this stage `leads` has already had the liveness sweep's dead
    postings removed, so its index is short of the true ranker rank by however many leads
    above it were withheld. Enumerating here would silently record a rank the ranker never
    assigned, and the whole reason the rank is persisted is to read conversion BY BAND. The
    caller builds the map off `ranked.visible` before anything filters it.
    """
    if not settings.gate.enabled or not leads:
        return leads, GateStageResult()

    with engine.connect() as conn:
        profile_row = get_profile(conn)
        if profile_row is None:
            return leads, GateStageResult()
        try:
            facts = parse_facts(profile_row.eligibility_facts_json)
            policy = parse_policy(profile_row.eligibility_policy_json)
        except ProfileRowInvalid:
            # The ranker already refused an unusable profile row upstream of this stage
            # (`run_pipeline`'s own `ProfileRowInvalid` handler); reaching a second one here
            # would be a race with a profile edit mid-run, and fail-open is still correct.
            return leads, GateStageResult()
        catalog = load_rules(settings.config_dir)
        identity = current_identity(conn, settings)
        if identity is None:
            return leads, GateStageResult()
        versions = current_posting_versions(conn, [p.posting_id for p in leads])
        already_gated = current_gate_verdicts(
            conn, [v.posting_version_id for v in versions.values()], *identity,
            engine_version=gate_engine_version(), facts_key=gate_facts_key(facts),
        )
    # Never re-judge (D-477 point 5): a lead with a current gate row under this identity is
    # skipped entirely — it never enters a request, let alone a `claude` call.
    #
    # `facts_key` is computed off the SAME `facts` object that goes into `build_gate_request`
    # below, so what the freshness test compares is exactly what the judge would be sent. The
    # row identity cannot carry this: `profile_hash` drops a family the live policy `ignore`s,
    # while the judge reads every fact under an all-blocker policy, so a work_auth flip was
    # invisible here while changing the request (T99).
    #
    # `engine_version` is EXACT here, not the prefix the display readers use (D-512). "Current"
    # has to mean current POLICY, or a bump to `oracle.POLICY_VERSION` can never reach a lead that
    # was judged under the old one — which is what stranded 434 of 505 apply-lane leads on
    # `p5-oracle-1` after `seniority_fit` shipped. A superseded verdict stays readable everywhere
    # else; it just no longer counts as "already judged".
    to_judge = [p for p in leads if p.posting_id not in already_gated]
    if not to_judge:
        return leads, GateStageResult()

    request = build_gate_request(to_judge, versions, facts, catalog, request_id=f"run-{run_id}")
    items = request["items"]
    judging_policy = request["judging_policy"]
    verdicts: list[OracleVerdict] = []
    failed_batches = 0
    errors: list[str] = []
    batches = _chunks(items, max(1, settings.gate.batch_size))
    for index, batch in enumerate(batches):
        batch_verdicts, note = _judge_batch(batch, judging_policy, settings)
        if batch_verdicts is None:
            failed_batches += 1
            errors.append(f"gate: batch {index + 1}/{len(batches)} failed open: {note}")
            continue
        if note is not None:
            errors.append(f"gate: batch {index + 1}/{len(batches)} partly failed open: {note}")
        verdicts.extend(batch_verdicts)

    verdicts, refused = _accepted(verdicts, versions, catalog)
    errors.extend(refused)
    if not verdicts:
        return leads, GateStageResult(failed_open_batches=failed_batches, errors=tuple(errors))

    with engine.begin() as write_conn:
        result = apply_gate_verdicts(
            write_conn, verdicts, versions=versions, facts=facts, policy=policy,
            catalog=catalog, run_id=run_id, shortlist_ranks=shortlist_ranks,
        )
    eligible_count, uncertain_count = _tally_eligible_and_uncertain(verdicts, versions, catalog)
    excluded_ids = tuple(int(label) for label in result.demoted_labels)
    filtered = [p for p in leads if p.posting_id not in excluded_ids]
    return filtered, GateStageResult(
        judged=result.judged,
        eligible=eligible_count,
        ineligible=result.ineligible,
        uncertain=uncertain_count,
        failed_open_batches=failed_batches,
        excluded_ids=excluded_ids,
        errors=tuple(errors),
    )


def _tally_eligible_and_uncertain(
    verdicts: list[OracleVerdict],
    versions: dict[int, CurrentVersion],
    catalog: RulesCatalog,
) -> tuple[int, int]:
    """Read-only mirror of `apply_gate_verdicts`' own accept+keystone-span logic (that
    function's docstring already does the same thing for its `ineligible`/`downgraded`
    tally), so the funnel's eligible/uncertain split reflects what actually got PERSISTED
    rather than the judge's raw `decision`. Never writes; `apply_gate_verdicts` above is the
    one and only writer."""
    eligible = 0
    uncertain = 0
    for verdict in verdicts:
        try:
            posting_id = int(verdict.label)
        except ValueError:
            continue
        current = versions.get(posting_id)
        if current is None:
            continue
        accepted = accept_oracle_verdict(verdict, current.body_text, catalog)
        persisted = accepted.expected_verdict
        if persisted == "ineligible" and not accepted.spans:
            persisted = "uncertain"
        if persisted == "eligible":
            eligible += 1
        elif persisted == "uncertain":
            uncertain += 1
    return eligible, uncertain

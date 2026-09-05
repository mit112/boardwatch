"""T42: the headless final-eligibility-gate judge stage on the daily path (D-477's "lever").

Routes through the EXISTING handshake — `eligibility.gate_handshake.build_gate_request` /
`apply_gate_verdicts`, which itself calls `eligibility.final_gate.record_gate_verdict` — rather
than a parallel path. This module's own job is narrow: decide which leads still need judging
(never re-judge a lead with a current gate row), invoke headless `claude` in batches of
`settings.gate.batch_size`, parse its output into `OracleVerdict`s, and fail OPEN at every seam
(D-074): a missing binary, a non-zero exit, a timeout, unparseable JSON, a wrong item count, or
a response with no usable evidence all drop that BATCH's verdicts — never a real job — and are
counted so the run reports them rather than looking silently clean.

`gate.enabled` defaults False (multi-tenancy): a caller must opt in before this spawns a single
subprocess.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from typing import Protocol, TypeVar

from sqlalchemy import Engine

from boardwatch.core.settings import Settings
from boardwatch.eligibility.catalog import RulesCatalog, load_rules
from boardwatch.eligibility.facts import ProfileRowInvalid, parse_facts, parse_policy
from boardwatch.eligibility.gate_handshake import apply_gate_verdicts, build_gate_request
from boardwatch.eligibility.oracle import OracleVerdict, OracleVerdictError, accept_oracle_verdict
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
        '"high"|"medium"|"low"}. No prose before or after, no code fences.\n\n'
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
    the caller must catch is an exception, never a magic return value).
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


def _parse_verdicts(stdout: str, expected_count: int) -> list[OracleVerdict]:
    """The two-stage envelope `--output-format json` wraps every headless response in: the
    outer JSON's `result` key holds the model's text, which is itself the JSON array this
    stage asked for (2026-09-08 calibration harness, `calib/*/batch-*.json`). Raises
    (`json.JSONDecodeError`, `KeyError`, `TypeError`, `ValueError`, `OracleVerdictError`) on
    anything that does not conform — the caller treats every one of those as fail-open.
    """
    envelope = json.loads(stdout)
    if envelope.get("is_error"):
        raise ValueError(f"claude reported is_error: {envelope.get('result')!r}")
    result_text = envelope["result"]
    if not isinstance(result_text, str):
        raise TypeError(f"expected envelope['result'] to be a string, got {type(result_text)}")
    parsed = json.loads(result_text)
    if not isinstance(parsed, list) or len(parsed) != expected_count:
        raise ValueError(
            f"expected a JSON array of {expected_count} verdicts, got "
            f"{len(parsed) if isinstance(parsed, list) else type(parsed).__name__}"
        )
    return [
        OracleVerdict(
            label=str(item["label"]),
            decision=str(item["decision"]),
            reason=item.get("reason"),
            evidence=str(item["evidence"]),
            confidence=str(item["confidence"]),
        )
        for item in parsed
    ]


def _judge_batch(
    batch: list[dict[str, object]], judging_policy: str, settings: Settings
) -> tuple[list[OracleVerdict] | None, str | None]:
    """Run one batch through headless claude. `(verdicts, None)` on success, `(None, note)`
    on any failure this stage must fail open on — a note describing WHAT failed, never a
    traceback, so the run's soft alert and funnel error line are readable."""
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
    try:
        return _parse_verdicts(stdout, len(batch)), None
    except (json.JSONDecodeError, KeyError, TypeError, ValueError, OracleVerdictError) as exc:
        return None, f"unusable response ({type(exc).__name__}): {exc}"


def run_gate_stage(
    engine: Engine,
    settings: Settings,
    leads: list[_T],
    *,
    run_id: int | None,
) -> tuple[list[_T], GateStageResult]:
    """The whole stage: filter to leads that still need judging, judge them in batches,
    persist through the existing handshake, and hand back the slate minus anything this run
    persisted `ineligible`. `leads` is returned UNCHANGED (same list, same order minus
    exclusions) on every fail-open path — `gate.enabled=False`, no profile, or nothing left
    to judge all return the identity slate with an all-zero result.
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
            conn, [v.posting_version_id for v in versions.values()], *identity
        )
    # Never re-judge (D-477 point 5): a lead with a current gate row under this identity is
    # skipped entirely — it never enters a request, let alone a `claude` call.
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
        verdicts.extend(batch_verdicts)

    if not verdicts:
        return leads, GateStageResult(failed_open_batches=failed_batches, errors=tuple(errors))

    with engine.begin() as write_conn:
        result = apply_gate_verdicts(
            write_conn, verdicts, versions=versions, facts=facts, policy=policy,
            catalog=catalog, run_id=run_id,
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

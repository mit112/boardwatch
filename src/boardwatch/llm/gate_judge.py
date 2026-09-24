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
from dataclasses import dataclass, replace
from typing import Protocol, TypeVar

from sqlalchemy import Connection, Engine

from boardwatch.core.settings import Settings
from boardwatch.eligibility.catalog import RulesCatalog, load_rules
from boardwatch.eligibility.facts import Facts, ProfileRowInvalid, parse_facts, parse_policy
from boardwatch.eligibility.final_gate import gate_effort_key
from boardwatch.eligibility.gate_handshake import apply_gate_verdicts, build_gate_request
from boardwatch.eligibility.oracle import (
    _CONFIDENCE,
    _VERDICTS,
    OracleVerdict,
    OracleVerdictError,
    accept_oracle_verdict,
)
from boardwatch.eligibility.read import fresh_gate_verdicts, newest_gate_verdicts
from boardwatch.store.queries import CurrentVersion, current_posting_versions, get_profile

#: What this stage writes to the gate row's `provider` column: the `claude` CLI under the
#: operator's own subscription, no API key. The same name the agent tailor lane already
#: records (`tailor_cmd`'s `llm_provider_override`), so the ledger has ONE name for that
#: judge rather than two — `settings.gate.model` alone cannot say it, since the same alias
#: means a different thing through an API provider.
GATE_PROVIDER = "claude-code-agent"


class _HasPostingId(Protocol):
    @property
    def posting_id(self) -> int: ...


#: Bound rather than a bare Protocol return type, so a caller passing `list[RankedPosting]`
#: gets `list[RankedPosting]` back (with `.company`/`.title`/... intact) instead of widening
#: to the Protocol's one declared attribute.
_T = TypeVar("_T", bound=_HasPostingId)


@dataclass(frozen=True)
class GateStageResult:
    """One run's tally from the gate stage. An all-zero result with `excluded_ids=()` is the
    honest reading when the gate is OFF — the caller (the pipeline) is the one that knows
    that, from `settings.gate.enabled`, and reports it separately (mirroring
    `DeathProbeReport`'s `None`-means-unmeasured split living one level up rather than inside
    this object). An ARMED run that judged nothing no longer reads the same way: `candidates`
    and `cached` say whether nothing was DUE or nothing was ASKED (T107).
    """

    judged: int = 0
    eligible: int = 0
    ineligible: int = 0
    uncertain: int = 0
    # Batches, not items — a batch of 13 that fails open costs at most 13 unjudged leads, and
    # the funnel reports the batch count so a reader can tell "the judge never ran" (batches ==
    # total batches) from "one bad response" (batches == 1).
    failed_open_batches: int = 0
    # T107 — the ITEM-level reconciliation, because the batch count cannot see a PARTIAL
    # outage at all. `candidates` is what the stage was handed, `cached` how many already
    # carried a current row (`len(already_gated)` — never why one missed), `sent` how many
    # items a request actually carried (below `candidates - cached` when a lead has no current
    # version or a quarantined body, both of which `build_gate_request` drops), `missing_items`
    # how many sent labels no answer ever named, and `refused_items` how many WERE answered
    # and then refused by `_accepted`. The last two are deliberately separate: an item the
    # judge skipped and an item whose verdict could not be used need different fixes.
    #
    # These do NOT reconcile to `judged` on their own: `apply_gate_verdicts` also skips a
    # verdict whose posting closed mid-run or whose body the quarantine withheld. The point of
    # the split is that zero fresh judgments stops being ambiguous — `sent == 0` says nothing
    # was due, `missing_items == sent` says the judge answered nothing.
    candidates: int = 0
    cached: int = 0
    sent: int = 0
    missing_items: int = 0
    refused_items: int = 0
    # T107 — the FIELD-level split, three-way and never two. `_seniority_fit` folds an absent
    # or out-of-catalog answer to `"unclear"`, which is also what a judge that genuinely could
    # not tell returns: of 1,999 stored gate verdicts 215 carry an explicit `"unclear"`, so
    # counting the fold as malformed would report a real answer as a parse failure on a
    # seventh of the corpus. `seniority_answered` is `yes`/`no`, `seniority_unclear` the real
    # explicit one, `seniority_unreadable` the fold.
    seniority_answered: int = 0
    seniority_unclear: int = 0
    seniority_unreadable: int = 0
    # T188 — verdicts whose `seniority_fit` was NOT ASKED, because the profile's
    # `target_seniority_band` is `any`. Counted apart from the three above: each carries the inert
    # `"unclear"`, and neither a judge's real `unclear` nor an unreadable answer is what happened.
    seniority_skipped: int = 0
    # Posting ids this run persisted a gate `ineligible` verdict for — the ONLY ones the caller
    # must drop from the slate before tailoring. Everything else (eligible, uncertain, unjudged
    # because already current) stays exactly where the ranker put it.
    excluded_ids: tuple[int, ...] = ()
    errors: tuple[str, ...] = ()


def _chunks(items: list[dict[str, object]], size: int) -> list[list[dict[str, object]]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _prompt(
    judging_policy: str, batch: list[dict[str, object]], *, seniority_asked: bool = True
) -> str:
    """Byte-shape-compatible with the calibration harness's prompt (2026-09-08 session,
    `calib_judge.sh`), which was run successfully against real headless `claude`. `slim` drops
    `bucket` — the judge sees `label`/`facts`/`jd_text` ONLY, never a hint about which bucket a
    posting fell in. With `seniority_asked` off the contract does not name `seniority_fit`,
    matching a `judging_policy` rendered for band `any`."""
    slim = [{k: item[k] for k in ("label", "facts", "jd_text")} for item in batch]
    count = len(batch)
    seniority = ', "seniority_fit": "yes"|"no"|"unclear"' if seniority_asked else ""
    return (
        f"{judging_policy}\n\n"
        "OUTPUT CONTRACT: Judge every item below from its jd_text and facts ONLY. Output ONLY "
        f"a JSON array with exactly {count} objects, one per item in the same order, each of "
        'the form {"label": <the item\'s label>, "decision": "eligible"|"ineligible"|'
        '"uncertain", "reason": <a reason_catalog family id or null>, "evidence": <verbatim '
        'substring of jd_text, required when ineligible, else "">, "confidence": '
        '"high"|"medium"|"low"' f"{seniority}}}. No prose before or "
        "after, no code fences.\n\n"
        f"ITEMS:\n{json.dumps(slim)}"
    )


def _call_claude(
    prompt: str, *, model: str, claude_config_dir: object, timeout_s: int,
    effort: str | None = None,
) -> str:
    """One headless call. Exactly the argv the 2026-09-08 calibration harness proved works:
    `claude -p --model <m> --tools "" --max-turns 1 --output-format json`, stdin `/dev/null`
    (never read — a batch prompt is a CLI arg, not stdin), `CLAUDE_CONFIG_DIR` from settings.
    `--effort <level>` follows the model only when `gate.effort` is set; unset, the argv is
    byte-identical to the calibrated one.

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
    effort_args = [] if effort is None else ["--effort", effort]
    result = subprocess.run(  # noqa: S603 - argv is a fixed shape, no shell, no user input in argv[0]
        ["claude", "-p", "--model", model, *effort_args, "--tools", "", "--max-turns",
         "1", "--output-format", "json", prompt],
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

#: The closed catalog of ways one `seniority_fit` answer can READ, reported beside the value so
#: the run can tell the fold above apart from the value it folds to. `_seniority_fit` is the
#: only producer, so these three are exhaustive by construction.
_SENIORITY_ANSWERED = "answered"
_SENIORITY_UNCLEAR = "unclear"
_SENIORITY_UNREADABLE = "unreadable"
#: Not produced by `_seniority_fit`: the question was not asked (band `any`, T188), so whatever
#: the judge sent is not read at all.
_SENIORITY_SKIPPED = "skipped"


def _seniority_fit(value: object) -> tuple[str, str]:
    """The value the verdict will carry, and how the answer read (T107).

    The value is unchanged from before — an unreadable answer is still the inert `"unclear"`,
    which withholds nothing. What is new is the second element: without it a systematic
    omission of this field is indistinguishable from a judge answering `"unclear"` honestly,
    and the field that drives the seniority hold can stop arriving with no signal at all.
    """
    text = str(value)
    if text == _SENIORITY_UNCLEAR:
        return text, _SENIORITY_UNCLEAR
    if text in _SENIORITY_FIT:
        return text, _SENIORITY_ANSWERED
    return _SENIORITY_UNCLEAR, _SENIORITY_UNREADABLE


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
    stdout: str, expected_labels: Sequence[str], *, seniority_asked: bool = True
) -> tuple[list[OracleVerdict], tuple[str, ...], tuple[str, ...]]:
    """The two-stage envelope `--output-format json` wraps every headless response in: the
    outer JSON's `result` key holds the model's text, which is itself the JSON array this
    stage asked for (2026-09-08 calibration harness, `calib/*/batch-*.json`). Raises
    (`json.JSONDecodeError`, `KeyError`, `TypeError`, `ValueError`, `OracleVerdictError`) on
    anything that does not conform — the caller treats every one of those as fail-open.

    Returns the verdicts the response carried, the labels it did NOT carry, and one
    `_SENIORITY_*` token per verdict saying how that answer's `seniority_fit` read (T107).
    Keyed on `label`, not on position or count: runs 45 and 48 (2026-09-09, -12) each lost a whole
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
    verdicts: list[OracleVerdict] = []
    seniority: list[str] = []
    for item in parsed:
        # Subscripted BEFORE any `.get`, and that order is load-bearing: an ELEMENT that is not
        # a mapping raises `TypeError` here, which the caller catches and fails the batch open,
        # where `.get` would raise `AttributeError` and leave the stage entirely.
        label = str(item["label"])
        fit, quality = (
            _seniority_fit(item.get("seniority_fit"))
            if seniority_asked
            else (_SENIORITY_UNCLEAR, _SENIORITY_SKIPPED)
        )
        verdicts.append(
            OracleVerdict(
                label=label,
                decision=_in_vocabulary(item["decision"], _VERDICTS, "decision"),
                reason=item.get("reason"),
                evidence=str(item["evidence"]),
                confidence=_in_vocabulary(item["confidence"], _CONFIDENCE, "confidence"),
                seniority_fit=fit,
            )
        )
        seniority.append(quality)
    answered = [verdict.label for verdict in verdicts]
    unknown = sorted(set(answered) - set(expected_labels))
    if unknown:
        raise ValueError(f"verdicts for labels the batch did not contain: {unknown}")
    if len(set(answered)) != len(answered):
        raise ValueError("the same label was answered more than once")
    missing = tuple(label for label in expected_labels if label not in set(answered))
    return verdicts, missing, tuple(seniority)


def _judge_batch(
    batch: list[dict[str, object]], judging_policy: str, settings: Settings,
    *, seniority_asked: bool = True,
) -> tuple[list[OracleVerdict] | None, str | None, tuple[str, ...]]:
    """Run one batch through headless claude. `(verdicts, None, ...)` on success,
    `(None, note, ())` on any failure this stage must fail open on — a note describing WHAT
    failed, never a traceback, so the run's soft alert and funnel error line are readable —
    and `(verdicts, note, ...)` when the response answered SOME of the batch: the note names
    the leads it skipped, which stay unjudged and on the slate exactly as a failed batch's do.

    The third element is one `_SENIORITY_*` token per verdict returned (T107), and it is EMPTY
    on every fail-open path: a batch that answered nothing contributes nothing to the field
    coverage denominator, or a process outage would read as a parse-quality failure."""
    prompt = _prompt(judging_policy, batch, seniority_asked=seniority_asked)
    try:
        stdout = _call_claude(
            prompt,
            model=settings.gate.model,
            claude_config_dir=settings.gate.claude_config_dir,
            timeout_s=settings.gate.call_timeout_s,
            effort=settings.gate.effort,
        )
    except FileNotFoundError:
        return None, "claude binary not found on PATH", ()
    except subprocess.TimeoutExpired:
        return None, f"claude timed out after {settings.gate.call_timeout_s}s", ()
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()[:300]
        return None, f"claude exited {exc.returncode}: {stderr}", ()
    except OSError as exc:
        # Everything else `subprocess.run` can raise launching a process: EACCES on a binary
        # that is not executable, E2BIG on a batch whose argv exceeds the platform limit,
        # ENOMEM under fork. `FileNotFoundError` is an `OSError` too, so it is handled above
        # and keeps its own note; this is the readable fallback, never an escape.
        return (
            None,
            f"claude could not be launched ({type(exc).__name__}, errno {exc.errno})",
            (),
        )
    try:
        verdicts, missing, seniority = _parse_verdicts(
            stdout, [str(item["label"]) for item in batch], seniority_asked=seniority_asked
        )
    except (json.JSONDecodeError, KeyError, TypeError, ValueError, OracleVerdictError) as exc:
        return None, f"unusable response ({type(exc).__name__}): {exc}", ()
    if not verdicts:
        # An empty array answers NOBODY: that is the "judge never ran" shape the batch count
        # exists to make visible, not a partial answer, so it fails the whole batch open.
        return (
            None,
            f"unusable response: the array carried none of the {len(batch)} verdicts",
            (),
        )
    if missing:
        return verdicts, (
            f"{len(missing)} of {len(batch)} verdicts missing (labels {', '.join(missing)}); "
            "those leads were left unchanged, never dropped"
        ), seniority
    return verdicts, None, seniority


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


def _current_gate_rows(
    conn: Connection,
    settings: Settings,
    facts: Facts,
    target_band: str,
    versions: Mapping[int, CurrentVersion],
) -> dict[int, str | None]:
    """posting_id -> its CURRENT gate verdict under the freshness key: the one definition of
    "already judged" that `run_gate_stage` skips on and `run_gate_refresh` counts as done, so a
    narrowing added to the key reaches both. Why each argument is there is `run_gate_stage`'s
    comment below."""
    return fresh_gate_verdicts(
        conn, [v.posting_version_id for v in versions.values()], facts,
        model=settings.gate.model, effort=gate_effort_key(settings.gate.effort),
        target_band=target_band,
    )


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

    # T107. Set on every return below, including the fail-open aborts: a run that never got
    # past the profile read has `candidates > 0, cached = 0, sent = 0`, which reads as "nothing
    # was asked" rather than as the clean "nothing was due" that `cached == candidates` is.
    candidates = len(leads)
    with engine.connect() as conn:
        profile_row = get_profile(conn)
        if profile_row is None:
            return leads, GateStageResult(candidates=candidates)
        try:
            facts = parse_facts(profile_row.eligibility_facts_json)
            policy = parse_policy(profile_row.eligibility_policy_json)
        except ProfileRowInvalid:
            # The ranker already refused an unusable profile row upstream of this stage
            # (`run_pipeline`'s own `ProfileRowInvalid` handler); reaching a second one here
            # would be a race with a profile edit mid-run, and fail-open is still correct.
            return leads, GateStageResult(candidates=candidates)
        catalog = load_rules(settings.config_dir)
        versions = current_posting_versions(conn, [p.posting_id for p in leads])
        already_gated = _current_gate_rows(
            conn, settings, facts, profile_row.target_seniority_band, versions
        )
    # Never re-judge (D-477 point 5): a lead this judge, at this level, already answered on these
    # exact inputs is skipped entirely — it never enters a request, let alone a `claude` call.
    #
    # NOT scoped on the row identity (T161): the judge is never sent the catalog or the policy
    # severities, so a rules-only re-key would re-send byte-identical inputs, and before T161 it
    # did — the T113 refresh re-judged the standing queue at its budget per run, and the daily
    # gate re-sent its slate (D-547).
    #
    # `facts_key` is computed off the SAME `facts` object that goes into `build_gate_request`
    # below, so what the freshness test compares is exactly what the judge would be sent. The
    # row identity cannot carry this: `profile_hash` drops a family the live policy `ignore`s,
    # while the judge reads every fact under an all-blocker policy, so a work_auth flip was
    # invisible here while changing the request (T99).
    #
    # `model` is the third argument for the same reason and it is the one a judge SWITCH needs
    # (T108): nothing else here moves with `settings.gate.model`, so a verdict the previous judge
    # reached counted as current forever and the switch reached only leads nobody had judged yet.
    # A row written before this shipped names no model, so it misses and is re-judged once.
    #
    # `effort` is the fourth (T155), for the same reason one level down: `settings.gate.effort`
    # reaches the call and `config_hash`, but nothing here moved with it, so a change of level
    # reached only leads nobody had judged yet. A row that recorded no level misses under every
    # level, including the unset one, and is re-judged once.
    #
    # `target_band` is the fifth (T188b): the band changes the prompt, and under `any` the
    # seniority question is not asked at all, so a lead judged under `any` must be asked again
    # once the owner declares a band, or its reading stays the skipped `unclear` forever.
    #
    # `engine_version` is EXACT here, not the `final_gate:` prefix (D-512). "Current" has to mean
    # current POLICY, or a bump to `oracle.POLICY_VERSION` can never reach a lead that was judged
    # under the old one — which is what stranded 434 of 505 apply-lane leads on `p5-oracle-1`
    # after `seniority_fit` shipped. Since T161 the value reads match it exactly too, so a
    # superseded verdict is neither "already judged" nor read by any lane.
    to_judge = [p for p in leads if p.posting_id not in already_gated]
    if not to_judge:
        return leads, GateStageResult(candidates=candidates, cached=len(already_gated))

    request = build_gate_request(
        to_judge, versions, facts, catalog, request_id=f"run-{run_id}",
        target_band=profile_row.target_seniority_band,
    )
    items = request["items"]
    judging_policy = request["judging_policy"]
    seniority_asked = request["target_band"] != "any"
    verdicts: list[OracleVerdict] = []
    failed_batches = 0
    missing_items = 0
    seniority: list[str] = []
    errors: list[str] = []
    batches = _chunks(items, max(1, settings.gate.batch_size))
    for index, batch in enumerate(batches):
        batch_verdicts, note, batch_seniority = _judge_batch(
            batch, judging_policy, settings, seniority_asked=seniority_asked
        )
        # Derived rather than reported back out of the parser, which already guarantees the
        # arithmetic: no verdict names a label the batch did not carry and no label is answered
        # twice, so the shortfall IS the count of labels nobody answered. A failed batch
        # answered none of them.
        missing_items += len(batch) - (0 if batch_verdicts is None else len(batch_verdicts))
        seniority.extend(batch_seniority)
        if batch_verdicts is None:
            failed_batches += 1
            errors.append(f"gate: batch {index + 1}/{len(batches)} failed open: {note}")
            continue
        if note is not None:
            errors.append(f"gate: batch {index + 1}/{len(batches)} partly failed open: {note}")
        verdicts.extend(batch_verdicts)

    verdicts, refused = _accepted(verdicts, versions, catalog)
    errors.extend(refused)
    # Everything the stage measured about COVERAGE, whether or not a single verdict survived to
    # be written. The two return paths below differ only in the persisted tally, so the counters
    # are built once here and the write path `replace`s that tally onto them.
    coverage = GateStageResult(
        failed_open_batches=failed_batches,
        candidates=candidates,
        cached=len(already_gated),
        sent=len(items),
        missing_items=missing_items,
        refused_items=len(refused),
        seniority_answered=seniority.count(_SENIORITY_ANSWERED),
        seniority_unclear=seniority.count(_SENIORITY_UNCLEAR),
        seniority_unreadable=seniority.count(_SENIORITY_UNREADABLE),
        seniority_skipped=seniority.count(_SENIORITY_SKIPPED),
        errors=tuple(errors),
    )
    if not verdicts:
        return leads, coverage

    with engine.begin() as write_conn:
        result = apply_gate_verdicts(
            write_conn, verdicts, versions=versions, facts=facts, policy=policy,
            catalog=catalog, run_id=run_id, shortlist_ranks=shortlist_ranks,
            provider=GATE_PROVIDER, model=settings.gate.model,
            effort=gate_effort_key(settings.gate.effort), target_band=request["target_band"],
        )
    eligible_count, uncertain_count = _tally_eligible_and_uncertain(verdicts, versions, catalog)
    excluded_ids = tuple(int(label) for label in result.demoted_labels)
    filtered = [p for p in leads if p.posting_id not in excluded_ids]
    return filtered, replace(
        coverage,
        judged=result.judged,
        eligible=eligible_count,
        ineligible=result.ineligible,
        uncertain=uncertain_count,
        excluded_ids=excluded_ids,
    )


@dataclass(frozen=True)
class GateRefreshResult:
    """T113: one run's standing-queue refresh. All-zero when `gate.refresh_budget` is 0 — the
    caller knows that from the setting and the funnel reports the refresh as not armed.

    `candidates` is how many standing leads had NO current reading when the refresh began, `sent`
    how many items its requests carried (at most `gate.refresh_budget`), and `pending_after` how
    many still have none, RE-READ from the store after the last chunk committed rather than
    derived from what the chunks reported — a failed batch leaves its leads pending, and the read
    says so without trusting the stage's own tally. `pending_after` staying high run over run is
    the signal that the budget cannot keep up with the re-keys. A lead whose body the send boundary
    withholds (D-406) is stale and can never be sent, so it stays in both counts as a constant
    floor rather than being hidden by a restated send predicate; the live queue held none of them
    on 2026-09-22 (D-548 sent 833 of 833).
    """

    candidates: int = 0
    sent: int = 0
    pending_after: int = 0
    errors: tuple[str, ...] = ()


def _stale(engine: Engine, settings: Settings, leads: Sequence[_T]) -> list[_T] | None:
    """`leads` minus every lead with a current gate reading or no current version to judge,
    RELEASED holds first (T195): a lead whose newest gate row on its current version, under any
    key, reads `ineligible` was held until its key moved and is back in the apply lane until it is
    re-judged. The caller's order holds within each part. `None` when the profile is missing or its
    facts unreadable, `run_gate_stage`'s fail-open cases."""
    with engine.connect() as conn:
        profile_row = get_profile(conn)
        if profile_row is None:
            return None
        try:
            facts = parse_facts(profile_row.eligibility_facts_json)
        except ProfileRowInvalid:
            return None
        versions = current_posting_versions(conn, [p.posting_id for p in leads])
        current = _current_gate_rows(
            conn, settings, facts, profile_row.target_seniority_band, versions
        )
        newest = newest_gate_verdicts(conn, [v.posting_version_id for v in versions.values()])
    stale = [p for p in leads if p.posting_id in versions and p.posting_id not in current]
    released = [p for p in stale if newest.get(p.posting_id) == "ineligible"]
    return released + [p for p in stale if newest.get(p.posting_id) != "ineligible"]


def run_gate_refresh(
    engine: Engine, settings: Settings, leads: Sequence[_T], *, run_id: int | None
) -> GateRefreshResult:
    """T113: re-judge up to `gate.refresh_budget` of `leads` — the standing queue, in the order
    the caller wants them healed, released holds first (`_stale`) — whose gate reading is not
    current.

    Every lead goes through `run_gate_stage` itself, so the judge, the request, the acceptance
    rules and the write are the daily gate's own. It is called ONE BATCH AT A TIME because that
    stage commits once, at its end: a single call over the whole refresh would lose every verdict
    it had bought to a timeout or a kill in its last batch.

    The budget is spent on what the stage actually SENDS, and the walk continues past a lead it
    would not send: `build_gate_request` withholds a foreign body at the send boundary (D-406), and
    slicing the budget off the front of the stale list would let a prefix of those leads take the
    same slots every run while judgeable leads behind them stayed stale forever. The stage's own
    `sent` is the count, so the send predicate is never restated here.

    The slate the stage hands back is discarded — a standing lead is already delivered, and a
    fresh `ineligible` holds it for review through the lane read (T109) rather than dropping it
    here. No shortlist rank is recorded: these leads were not ranked this run.
    """
    budget = settings.gate.refresh_budget
    if not settings.gate.enabled or budget == 0 or not leads:
        return GateRefreshResult()
    stale = _stale(engine, settings, leads)
    if stale is None:
        return GateRefreshResult()
    size = max(1, settings.gate.batch_size)
    sent = 0
    position = 0
    calls = 0
    errors: list[str] = []
    while position < len(stale) and sent < budget:
        chunk = stale[position : position + min(size, budget - sent)]
        position += len(chunk)
        calls += 1
        _, result = run_gate_stage(engine, settings, chunk, run_id=run_id)
        sent += result.sent
        errors.extend(f"gate refresh batch {calls}: {note}" for note in result.errors)
    after = _stale(engine, settings, leads)
    return GateRefreshResult(
        candidates=len(stale),
        sent=sent,
        pending_after=len(stale) if after is None else len(after),
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

"""The run manifest's genuinely-new hashes — PROGRAM.md §3.P0 **item 4**, plus T111's sixth.

Item 4 is *reproducibility instrumentation*: two runs that share a manifest should turn the
same corpus into the same leads. Most of the manifest already existed and is reused, not
rebuilt — the code fingerprint is `engine_version()`, the rules version is `rules_hash`, the
profile-facts version is `profile_hash`, start/end are on the `runs` row and the exit status
is `runs.status` (D-029). This module supplies the parts that did not exist:

  * **`config_hash`** — over the `Settings` fields that decide *which* postings become leads.
    `METRICS.md` §"Session 7" enumerated all 13 `Settings` + 8 `LLMTier` fields and classified
    every one as IN (decision-relevant) or OUT (machine-local / throughput / delivery /
    budget). That classification is encoded below as closed sets, and `config_hash` **fails**
    if a field appears in neither — `CLAUDE.md`: out-of-catalog is a failure, never a new
    bucket. A `Settings` field added later cannot be silently swept into or out of the hash.

  * **`profile_row_hash`** — over the six profile columns the RANKER reads (`skills`,
    `target_titles`, `exclude_titles`, `locations`, `remote_only`, `target_seniority_band`).
    `profile_hash` is an eligibility-*facts* hash and covers none of them, yet
    `exclude_titles` alone drives the single largest drop in the funnel. Without this hash the
    manifest would say two runs were identical while the setting responsible for 11,517
    rejections had changed underneath it. This closes that gap rather than only documenting it.

`profile_row_hash` also carries the **leveling catalog's digest** (D-246). The catalog is
user-overridable at `{config_dir}/leveling.yaml` and decides a drop bucket, so without it an
operator could edit which titles are dropped and the manifest would still call two runs
identical — the same failure `exclude_titles` above describes.

It carries the **skill-taxonomy version** for exactly the same reason, and that closes the one
coverage gap this docstring used to state. `taxonomy.yaml` is user-overridable at
`{config_dir}/taxonomy.yaml`, and since the zero-signal veto it decides a drop bucket too:
"0 recognised requirement terms" is a taxonomy judgement, so editing the taxonomy changes which
postings are dropped. While the taxonomy only *scored* postings, leaving it out cost the
manifest some precision; once it *drops* them, leaving it out would let the manifest call two
runs identical across a change that removed thousands of leads — and would stamp a permanent
ledger disposition with a `policy_version` that does not describe the policy that produced it.

It is NOT covered indirectly by `skills`. That column is the taxonomy applied to the operator's
own profile text, so it moves only when the edited terms happen to appear there; every other
taxonomy edit changes which postings are dropped while `skills` sits still.

  * **`routing_hash`** (T111) — the manifest's SIXTH value, and the only one that is not about
    which postings become LEADS. It covers which LANE a delivered lead lands in: the knobs
    `config_hash` deliberately classifies OUT that can still move a lead between the apply queue
    and `_review`, plus the source of the five modules that decide the lane. Flipping
    `seniority_hold` leaves all five existing hashes byte-identical (measured), so two runs could
    carry identical manifests and route every lead differently — and B8's 14-day evidence is read
    against those manifests. It is ADDED beside them and folded into none of them, so a permanent
    disposition's identity is untouched and a hold flip reopens nothing.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from boardwatch.core.settings import GateTier, LLMTier, Settings
from boardwatch.eligibility.engine import digest_of_sources
from boardwatch.eligibility.hashing import digest

# The closed classification from METRICS.md §"Session 7". Every top-level Settings field is in
# exactly one of these three (the third being `llm`, whose own fields are classified below).
_CONFIG_RELEVANT: frozenset[str] = frozenset(
    {
        "weights",
        "recency_half_life_days",
        "zero_skill_coverage_prior",
        "location_filter_mode",
        # P6 slice 2: how long a surfaced-but-unbuilt job stays suppressed. Decision-relevant —
        # it changes which postings reach the lead list on any given run, which is the test this
        # set applies. Consequence, stated so it is not read as a bug: `policy_version` is
        # derived from `config_hash`, so changing the TTL marks every permanent disposition
        # stale. Harmless by design — stale is reported, never auto-reopened (design §2.4).
        "seen_ttl_days",
    }
)
_CONFIG_IRRELEVANT: frozenset[str] = frozenset(
    {
        "data_dir",            # machine-local
        "config_dir",          # machine-local
        "per_host_delay_seconds",  # throughput
        "pace_from_request_start",  # throughput: WHERE the same delay is measured from
        "retry_attempts",          # throughput
        "busy_timeout_ms",         # throughput
        "scan_workers",            # throughput
        "detail_fetch_budget",     # throughput
        "reap_stale_after_hours",  # run bookkeeping/liveness — never which postings become leads
        # Bounds how stale a board's cached validator may get before a forced unconditional
        # refetch. Throughput/liveness, same class as detail_fetch_budget/reap_stale_after_hours:
        # it changes WHEN a board is refetched, never how the corpus is judged. Classifying it IN
        # would stale every permanent disposition via policy_version the moment the TTL moved — a
        # corpus-wide drain from a knob that judged nothing.
        "validator_max_age_hours",
        "notify",              # delivery, post-selection: changes who is told, not which leads
        # The seven lane acquisition knobs are ACQUISITION, in the same class as
        # `detail_fetch_budget`:
        # they decide how much corpus arrives, not how the corpus is judged. Corpus membership
        # has never been in this hash — watching a board changes it too, and that lives in the
        # store, not in `Settings`.
        #
        # The deciding argument is downstream: `policy_version` is derived from `config_hash`,
        # so classifying these IN would mark every permanent `built`/`skipped` disposition
        # stale the moment a lane is armed or disarmed — a corpus-wide drain event triggered by
        # a knob that judged nothing. And the artifact is not silent about lanes either way:
        # the funnel's `lanes` section names every lane that ran, with its outcome counts.
        "lanes_enabled",
        "lane_new_companies_per_run",
        "lane_new_companies_per_run_overrides",
        "lane_posting_budget",
        "lane_search_pages",
        "lane_search_hubs",
        "lane_hub_combos_per_run",
        "lane_hub_distance_miles",
        # OUT for the same reason the seven above are: it decides how much corpus arrives, never
        # how the corpus is judged, and `policy_version` derives from `config_hash` -- so
        # classifying it IN would stale every permanent disposition the moment an operator armed
        # the company cells. No verdict moves when this changes.
        "lane_company_combos_per_run",
        # The Indeed lane's own two page knobs, OUT for exactly the reason the four above are.
        # They are acquisition — how much corpus arrives — and `policy_version` is derived from
        # `config_hash`, so classifying them IN would mark every permanent `built`/`skipped`
        # disposition stale the moment an operator changed a page ceiling: a corpus-wide drain
        # from a knob that judged nothing. The funnel's `lanes` section reports what the lane
        # actually read either way.
        "indeed_search_pages",
        "indeed_results_per_page",
        # D-385. WHERE a lane reads from, not how a posting is judged: the same record ingested
        # from a moved directory must not re-key every permanent disposition.
        "jobapps_discovery_dir",
        "jobapps_queue_dir",
        # D-325. OUT, on the same reasoning as `validator_max_age_hours`: these bound WHEN and
        # HOW OFTEN a posting is re-asked, never how the corpus is judged. What they can change
        # is corpus MEMBERSHIP — a proven-dead posting is closed — and membership has never been
        # in this hash: watching a board changes it too, and that lives in the store.
        #
        # The deciding argument is downstream, as it was for the lane knobs: `policy_version` is
        # derived from `config_hash`, so classifying these IN would mark every permanent
        # `built`/`skipped` disposition stale the moment an operator changed a probe budget — a
        # corpus-wide drain from a knob that judged nothing. And the artifact is not silent
        # either way: the funnel's `death_probe` section reports both sides of the budget.
        "death_probe_budget",
        # T89's company budget, OUT on the identical reasoning: it bounds how many BOARDS the
        # sweep may ask per run, never how a posting is judged.
        "death_probe_company_budget",
        "death_probe_ttl_hours",
        # T91. OUT, on exactly the reasoning the two above carry: it bounds HOW MANY application
        # forms are fetched, never how a posting is judged. The form fetch writes no verdict and
        # no requirement row -- it can only route a lead to the review lane -- and `policy_version`
        # derives from `config_hash`, so classifying it IN would mark every permanent
        # `built`/`skipped` disposition stale the moment an operator changed a fetch budget. The
        # queue sync reports both sides of the budget either way.
        "form_question_fetch_budget",
    }
)

_LLM_RELEVANT: frozenset[str] = frozenset(
    {
        "enabled",
        "provider",
        "model",
        "base_url",
        "eligibility_extraction",
        "resume_tailoring",
        "resume_tailoring_via_agent",
    }
)
_LLM_IRRELEVANT: frozenset[str] = frozenset(
    {"max_calls_per_run"}  # a pure cap; excluded deliberately (revisit if coverage is reported)
)

# T42. `gate` gets the SAME nested-tier treatment `llm` does, for the same reason: whether it
# is armed and which judge answers can change which postings become leads, but a run/cost knob
# cannot.
_GATE_RELEVANT: frozenset[str] = frozenset(
    {
        "enabled",  # whether the stage runs at all — the whole point of this hash
        "model",  # a different judge can return a different verdict for the same JD
        "effort",  # the same judge reasoning harder or less can too — `model`'s reason exactly
    }
)
_GATE_IRRELEVANT: frozenset[str] = frozenset(
    {
        "claude_config_dir",  # machine-local — which login answers, not which verdict
        "batch_size",  # pure batching, like max_calls_per_run
        "call_timeout_s",  # throughput, same class as retry_attempts/scan_workers
        # T63. Changes WHEN a posting is judged, never the verdict any posting receives: a
        # deeper slate reaches the same judge under the same identity and every verdict is
        # persisted the same way. Restamping `policy_version` for it would invalidate every
        # stored disposition for a scheduling knob.
        "depth",
        # T113. `depth`'s reasoning, applied to the standing queue: it decides how many already
        # delivered leads are RE-judged this run, under the same judge and identity, and creates
        # no lead and changes no verdict that is reached.
        "refresh_budget",
        # Changes which LANE a delivered lead lands in, never whether it is a lead. The rule
        # above is "can change which postings become leads"; a held lead is still delivered,
        # still carries a disposition, and still reaches the owner — it lands in `_review`
        # instead of the apply root. This is the same reasoning that kept 0-B's judge promotion
        # (D-503) out of this hash: it moves the same leads between lanes and creates none. A
        # relevant classification would also re-stamp every stored disposition the moment the
        # field was ADDED, at its inert default, for a routing knob nothing had yet turned on.
        "seniority_hold",
    }
)


class UnclassifiedSettingError(ValueError):
    """A Settings/LLMTier field is in neither the IN nor the OUT set for the config hash.

    Raised rather than defaulted, so adding a field to `Settings` without deciding whether it
    changes which postings become leads breaks the build instead of silently altering — or
    silently NOT altering — the config hash. The closed catalog is only closed if drift fails.
    """


def _assert_exhaustive() -> None:
    settings_fields = set(Settings.model_fields)
    expected_settings = _CONFIG_RELEVANT | _CONFIG_IRRELEVANT | {"llm", "gate"}
    if settings_fields != expected_settings:
        missing = settings_fields - expected_settings
        extra = expected_settings - settings_fields
        raise UnclassifiedSettingError(
            f"Settings fields not classified for config_hash: missing={sorted(missing)} "
            f"stale={sorted(extra)}"
        )
    llm_fields = set(LLMTier.model_fields)
    expected_llm = _LLM_RELEVANT | _LLM_IRRELEVANT
    if llm_fields != expected_llm:
        missing = llm_fields - expected_llm
        extra = expected_llm - llm_fields
        raise UnclassifiedSettingError(
            f"LLMTier fields not classified for config_hash: missing={sorted(missing)} "
            f"stale={sorted(extra)}"
        )
    gate_fields = set(GateTier.model_fields)
    expected_gate = _GATE_RELEVANT | _GATE_IRRELEVANT
    if gate_fields != expected_gate:
        missing = gate_fields - expected_gate
        extra = expected_gate - gate_fields
        raise UnclassifiedSettingError(
            f"GateTier fields not classified for config_hash: missing={sorted(missing)} "
            f"stale={sorted(extra)}"
        )


def config_hash(settings: Settings) -> str:
    """SHA-256 over exactly the decision-relevant `Settings` fields, in canonical form.

    Fails via `UnclassifiedSettingError` if any `Settings`/`LLMTier` field is unclassified, so
    the hash can never silently cover more or less than the closed list it claims to.
    """
    _assert_exhaustive()
    payload = {
        "settings": {
            name: _jsonable(getattr(settings, name)) for name in sorted(_CONFIG_RELEVANT)
        },
        "llm": {name: getattr(settings.llm, name) for name in sorted(_LLM_RELEVANT)},
        "gate": {name: getattr(settings.gate, name) for name in sorted(_GATE_RELEVANT)},
    }
    return digest(payload)


#: The modules that decide WHICH LANE a delivered lead lands in. Every one of them is outside
#: `eligibility/engine.digested_modules()`, which is checked rather than assumed: that function
#: returns `catalog.py`, `detect.py`, `resolve.py`, `engine.py`, all under `eligibility/`, and it
#: is deliberately scoped to what can change a VERDICT. Nothing in the five below can. They decide
#: where a lead with an unchanged verdict is put, and until now no value in the manifest covered
#: them at all.
#:
#: Paths relative to the `boardwatch` package root, read from disk for the reason
#: `digested_modules` gives for the same choice: a missing file must fail loudly rather than
#: silently shrink what the fingerprint claims to cover.
_ROUTING_MODULES: tuple[str, ...] = (
    # The lane classifier itself — `classify`, and the closed `ReviewReason` catalog.
    "delivery/review_gate.py",
    # The application-form surface catalog, which is what a `form_question_hard_stop` hold is.
    "delivery/form_questions.py",
    # `classify`'s two imported gates.
    "rank/location_gate.py",
    "rank/role_gate.py",
    # Where `seniority_above_band` comes from.
    "rank/title_band.py",
)

#: The knobs that move a DELIVERED lead between lanes, qualified by their tier so a name that
#: exists on two models (`model`, `enabled`) can never be classified once for both.
#:
#: The universe here is exactly the fields `config_hash` classified OUT, and that is the whole
#: design: a field already inside `config_hash` is already fingerprinted, and putting it here too
#: would buy nothing. What this covers is the gap — knobs no hash in the manifest could see.
#: Astra's probe measured the headline case: flipping `seniority_hold` leaves `config_hash`
#: byte-identical, so two runs could carry identical five-hash manifests and route every lead
#: differently, with B8's 14-day evidence read against those manifests.
#:
#: The test each member is classified by is `review_gate.classify`: is this an input to the lane
#: decision, or to a fact the lane decision reads?
_ROUTING_RELEVANT: frozenset[str] = frozenset(
    {
        # The knob F6 was raised on. It arms `judge_seniority_above_band`, one of `classify`'s
        # inputs, and nothing else — no verdict moves, which is exactly why `config_hash` is
        # right to leave it out and why it needs covering somewhere.
        "gate.seniority_hold",
        # The three knobs that decide which delivered leads carry a GATE VERDICT when the lane
        # split runs, and `judge_verdict` is a `classify` input. A batch that fails open (D-074)
        # leaves its whole batch with no verdict, so batch composition and the timeout that
        # abandons one both change where leads land; `depth` changes how much of the slate was
        # ever judged. None of the three changes any verdict that IS reached, which is why they
        # stay out of `config_hash`.
        "gate.batch_size",
        "gate.call_timeout_s",
        "gate.depth",
        # T113. The same question for the STANDING queue: how many delivered leads carry a current
        # gate verdict when `sync_queue` files them, and 0-B's promotion reads exactly that.
        "gate.refresh_budget",
        # T91. Decides which leads have a form to be hard-stopped BY. An unfetched form cannot
        # hold anything, so the budget is the difference between a lead in the apply lane and the
        # same lead in `_review` — and it creates and destroys no lead, so `config_hash` excludes
        # it correctly.
        "form_question_fetch_budget",
    }
)
_ROUTING_IRRELEVANT: frozenset[str] = frozenset(
    {
        # Machine-local. Which directory the store and the config live in, and which login
        # answers the headless call — none of them is read by any gate.
        "data_dir",
        "config_dir",
        "gate.claude_config_dir",
        # Throughput and bookkeeping: they change WHEN and HOW FAST something is fetched or
        # re-asked, never which lane a lead lands in once it is delivered.
        "per_host_delay_seconds",
        "pace_from_request_start",
        "retry_attempts",
        "busy_timeout_ms",
        "scan_workers",
        "detail_fetch_budget",
        "reap_stale_after_hours",
        "validator_max_age_hours",
        # Post-selection: who is told, not where a lead sits.
        "notify",
        # ACQUISITION — how much corpus arrives. Corpus membership has never been fingerprinted
        # anywhere in this manifest (watching a board changes it too, and that lives in the
        # store), and a lead that does not exist is not a lead in the wrong lane.
        "lanes_enabled",
        "lane_new_companies_per_run",
        "lane_new_companies_per_run_overrides",
        "lane_posting_budget",
        "lane_search_pages",
        "lane_search_hubs",
        "lane_hub_combos_per_run",
        "lane_hub_distance_miles",
        "lane_company_combos_per_run",
        "indeed_search_pages",
        "indeed_results_per_page",
        "jobapps_discovery_dir",
        "jobapps_queue_dir",
        # Membership again, through the other door: a proven-dead posting is CLOSED, and a closed
        # lead drains to `_closed` on the fact that it is gone rather than on any routing
        # decision. Same argument `_CONFIG_IRRELEVANT` makes for these three.
        "death_probe_budget",
        "death_probe_company_budget",
        "death_probe_ttl_hours",
        # A cap on the LLM tailoring budget and on the separate `eligibility extract` command.
        # Neither is an input to `classify` nor to any fact it reads.
        "llm.max_calls_per_run",
    }
)


class UnclassifiedRoutingFieldError(ValueError):
    """A knob `config_hash` excludes is in neither the IN nor the OUT set for `routing_hash`.

    Its own type rather than a reuse of `UnclassifiedSettingError`, because the two closures fail
    for different reasons and a caller that catches one must not silently absorb the other: that
    one means a `Settings` field was added without deciding whether it changes which postings
    become LEADS, and this one means a field was declared not to and then left undecided about
    whether it changes which LANE they land in. Folding them would let the second failure be read
    as the first and "fixed" by editing the wrong set.
    """


def _routing_universe() -> frozenset[str]:
    """Exactly the fields `config_hash` classified OUT, tier-qualified.

    DERIVED from those three sets rather than restated, which is what chains the two closures: a
    new `Settings` field must first be classified for `config_hash` (or that hash refuses), and
    the moment it is classified OUT it appears here and `routing_hash` refuses until it is
    classified again. A hand-copied list would go stale at the first addition and the second
    closure would quietly stop closing.
    """
    return frozenset(
        _CONFIG_IRRELEVANT
        | {f"llm.{name}" for name in _LLM_IRRELEVANT}
        | {f"gate.{name}" for name in _GATE_IRRELEVANT}
    )


def _assert_routing_exhaustive() -> None:
    universe = _routing_universe()
    classified = _ROUTING_RELEVANT | _ROUTING_IRRELEVANT
    if universe != classified:
        missing = universe - classified
        extra = classified - universe
        raise UnclassifiedRoutingFieldError(
            f"config-excluded fields not classified for routing_hash: missing={sorted(missing)} "
            f"stale={sorted(extra)}"
        )


def _routing_source(relative: str) -> str:
    path = Path(__file__).parent.parent / relative
    if not path.is_file():
        raise FileNotFoundError(
            f"{relative} is part of routing_hash but is not readable, so the fingerprint "
            "would silently cover less than it claims"
        )
    return path.read_text(encoding="utf-8")


def _routing_value(settings: Settings, qualified: str) -> object:
    tier, _, name = qualified.rpartition(".")
    owner = settings if tier == "" else getattr(settings, tier)
    return _jsonable(getattr(owner, name))


def routing_hash(settings: Settings) -> str:
    """The manifest's SIXTH value: which way this run ROUTED, for the knobs no hash covers.

    **It ADDS and changes nothing.** `policy_version` composes the five existing components and
    this is not one of them, so a permanent `built`/`skipped` disposition keeps its identity
    across a hold flip and NOTHING reopens. That is a requirement, not a side effect: every other
    candidate design — reclassifying `seniority_hold` as `config_hash`-relevant being the obvious
    one — would re-stamp every stored disposition the moment a routing knob moved, a corpus-wide
    drain from a knob that judged nothing (the owner's ruling, 2026-09-19).

    Two halves, because a routing change arrives through either and the manifest could see
    neither:

      * the knobs `config_hash` classifies OUT that can still move a lead between lanes, and
      * the SOURCE of the five modules that decide the lane (`_ROUTING_MODULES`), digested the
        same AST-canonical way `engine_version` digests its own four, so comments and formatting
        stay invisible and only a semantic edit moves it.

    **What it buys, and nothing more:** B8's evidence gains a field to segment on. Two runs whose
    five hashes agree and whose `routing_hash` differs are not comparable as apply-lane volume
    readings, and until now nothing in the artifact said so.

    **A stated gap.** `store/delivery_queries.py` assembles `classify`'s arguments and derives
    `revised_since_build`, and it is NOT digested: it is a 1,500-line store module whose every
    query edit would re-key this value, and the argument list is already pinned to one call site
    by `lane_decision`. An edit to the `revised_since_build_ids` derivation therefore moves no
    value here. Said rather than hidden.

    Fails via `UnclassifiedRoutingFieldError` if a knob `config_hash` excludes is unclassified
    here, so this fingerprint is as closed as the one it sits beside.
    """
    _assert_exhaustive()
    _assert_routing_exhaustive()
    return digest(
        {
            "knobs": {
                name: _routing_value(settings, name) for name in sorted(_ROUTING_RELEVANT)
            },
            "modules": digest_of_sources(
                [_routing_source(name) for name in _ROUTING_MODULES]
            ),
        }
    )


def _jsonable(value: object) -> object:
    """RankWeights (a pydantic model) canonicalises via model_dump; everything else is scalar."""
    dump = getattr(value, "model_dump", None)
    return dump(mode="json") if callable(dump) else value


def profile_row_hash(
    *,
    skills: Sequence[object] | None,
    target_titles: Sequence[object] | None,
    exclude_titles: Sequence[object] | None,
    locations: Sequence[object] | None,
    remote_only: bool,
    target_seniority_band: str = "any",
    leveling_digest: str = "",
    taxonomy_version: str = "",
    role_taxonomy_digest: str = "",
) -> str:
    """SHA-256 over the six profile columns the ranker reads, plus the three catalog versions.

    A missing list and an empty list are different inputs and hash differently — canonical form
    keeps an explicit null distinct from `[]`, the same guard `hashing.canonical` documents.

    The catalog arguments default to `""` in the convention this signature already set, so
    the guard against a caller forgetting one is NOT the signature: it is
    `test_taxonomy_drift_moves_both_identities`, which drives both production callers over two
    taxonomies and fails if either hash sits still.
    """
    payload = {
        "skills": list(skills) if skills is not None else None,
        "target_titles": list(target_titles) if target_titles is not None else None,
        "exclude_titles": list(exclude_titles) if exclude_titles is not None else None,
        "locations": list(locations) if locations is not None else None,
        "remote_only": remote_only,
        "target_seniority_band": target_seniority_band,
        # The catalog decides a drop bucket and is user-overridable, so it belongs in
        # the identity for the same reason the band does.
        "leveling_digest": leveling_digest,
        # And the skill taxonomy, for the same reason again: since the zero-signal veto,
        # "0 recognised requirement terms" is a taxonomy judgement that DROPS a posting.
        "taxonomy_version": taxonomy_version,
        # And the user's role taxonomy (P2 item 8): it decides the role gate's `not_swe` drop.
        # `""` is "no taxonomy", which no real digest can equal.
        "role_taxonomy_digest": role_taxonomy_digest,
    }
    return digest(payload)


def policy_version(
    *,
    code_fingerprint: str,
    config_hash: str,
    profile_row_hash: str | None,
    profile_facts_hash: str | None,
    rules_hash: str | None,
) -> str:
    """The stamp on a PERMANENT ledger disposition (P6 slice 2, design §2.4).

    Composed from the run manifest's own identity rather than a new hash, because "what would
    make us want to re-decide this" and "what makes two runs comparable" are the same question,
    and the manifest already answers it. Nothing new is hashed here.

    The three profile-derived components are `None` on a run with no profile — the same runs whose
    manifest reports them as `None`. That is a distinct stamp, not a missing one: a decision taken
    without a profile really was taken under a different policy than one taken with it.

    A stamp mismatch never re-opens a disposition on its own. Auto-expiry on mismatch would
    rebuild the whole shortlist on any settings tweak, and an automatic re-open cannot be
    reviewed before it happens; `ledger show --stale` lists them and `ledger reopen` releases
    them. It inherits `profile_row_hash`'s coverage, which now INCLUDES the skill-taxonomy
    version — necessarily, because a permanent disposition stamped under a taxonomy that no
    longer describes the rule that produced it is a stamp that answers the wrong question.
    """
    return digest(
        {
            "code": code_fingerprint,
            "config": config_hash,
            "profile_row": profile_row_hash,
            "profile_facts": profile_facts_hash,
            "rules": rules_hash,
        }
    )

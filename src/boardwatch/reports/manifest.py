"""The run manifest's two genuinely-new hashes — PROGRAM.md §3.P0 **item 4**.

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

The one coverage gap that remains, stated so the manifest never over-claims: neither hash
covers the **skill-taxonomy version** — `taxonomy.yaml` can change which postings score as
covered without moving either hash. It is called out in the manifest's own note.
"""

from __future__ import annotations

from collections.abc import Sequence

from boardwatch.core.settings import LLMTier, Settings
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
        "retry_attempts",          # throughput
        "busy_timeout_ms",         # throughput
        "scan_workers",            # throughput
        "detail_fetch_budget",     # throughput
        "reap_stale_after_hours",  # run bookkeeping/liveness — never which postings become leads
        "notify",              # delivery, post-selection: changes who is told, not which leads
        # The three lane knobs are ACQUISITION, in the same class as `detail_fetch_budget`:
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
        "lane_posting_budget",
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


class UnclassifiedSettingError(ValueError):
    """A Settings/LLMTier field is in neither the IN nor the OUT set for the config hash.

    Raised rather than defaulted, so adding a field to `Settings` without deciding whether it
    changes which postings become leads breaks the build instead of silently altering — or
    silently NOT altering — the config hash. The closed catalog is only closed if drift fails.
    """


def _assert_exhaustive() -> None:
    settings_fields = set(Settings.model_fields)
    expected_settings = _CONFIG_RELEVANT | _CONFIG_IRRELEVANT | {"llm"}
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
    }
    return digest(payload)


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
) -> str:
    """SHA-256 over the six profile columns the ranker reads, plus the leveling digest.

    A missing list and an empty list are different inputs and hash differently — canonical form
    keeps an explicit null distinct from `[]`, the same guard `hashing.canonical` documents.
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
    them. Inherits the manifest's one stated coverage gap — the skill-taxonomy version moves
    neither `config_hash` nor `profile_row_hash`.
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

"""Cross-provider migration suggestions: when a watched board is unhealthy, probe the other
simple-slug providers for the same company and suggest one that is live.

The logic is pure and takes an injected `probe`, so these exercise it without a network."""

from __future__ import annotations

from boardwatch.providers.base import BoardHealth
from boardwatch.scan.board_migration import (
    MIGRATION_TRIGGER,
    MigrationSuggestion,
    company_key,
    migration_candidates,
    suggest_migrations,
)


def test_company_key_is_tenant_for_workday_slug_for_others() -> None:
    # a workday slug is host/tenant/site; the tenant is the company handle other providers key on
    assert company_key("workday", "veeva.wd5.myworkdayjobs.com/veeva/veeva_external") == "veeva"
    assert (
        company_key("workday", "purestorage.wd1.myworkdayjobs.com/purestorage/purestoragecareers")
        == "purestorage"
    )
    # simple-slug providers: the slug already IS the handle
    assert company_key("greenhouse", "hubspot") == "hubspot"
    assert company_key("lever", "plaid") == "plaid"


def test_candidates_exclude_own_provider_workday_and_smartrecruiters() -> None:
    # a dead workday board -> probe the four confirmable simple-slug providers by tenant
    cands = migration_candidates("workday", "veeva.wd5.myworkdayjobs.com/veeva/veeva_external")
    assert cands == [("greenhouse", "veeva"), ("lever", "veeva"), ("ashby", "veeva"),
                     ("workable", "veeva")]
    # a dead greenhouse board -> the other three simple providers, own provider excluded
    got = {p for p, _ in migration_candidates("greenhouse", "acme")}
    assert got == {"lever", "ashby", "workable"}
    assert "greenhouse" not in got  # own provider excluded
    assert "workday" not in got  # a workday slug is not derivable from a company name
    assert "smartrecruiters" not in got  # returns EMPTY for unknown slugs -> false OKs


def test_suggests_the_provider_whose_probe_is_ok() -> None:
    # veeva migrated workday -> lever; only lever:veeva answers OK
    def probe(targets):
        return {t: (BoardHealth.OK if t == ("lever", "veeva") else BoardHealth.EMPTY)
                for t in targets}

    out = suggest_migrations(
        [("workday", "veeva.wd5.myworkdayjobs.com/veeva/veeva_external")], probe
    )
    assert out == [
        MigrationSuggestion(
            old_provider="workday",
            old_slug="veeva.wd5.myworkdayjobs.com/veeva/veeva_external",
            new_provider="lever",
            new_slug="veeva",
        )
    ]


def test_no_suggestion_when_no_candidate_is_ok() -> None:
    # a genuinely-empty board (snyk): reachable, but the company is nowhere else -> stay silent
    def probe(targets):
        return {t: BoardHealth.EMPTY for t in targets}

    assert suggest_migrations([("ashby", "snyk")], probe) == []


def test_only_ok_counts_not_empty_or_dead() -> None:
    # a candidate that is EMPTY or DEAD must never be suggested — only a live OK board is a move
    def probe(targets):
        return {t: (BoardHealth.DEAD if t[0] == "lever" else BoardHealth.EMPTY) for t in targets}

    assert suggest_migrations([("greenhouse", "acme")], probe) == []


def test_first_ok_in_target_order_wins_single_suggestion() -> None:
    # if two providers both answer OK, emit exactly one suggestion, the first in target order
    def probe(targets):
        return {t: BoardHealth.OK for t in targets}

    out = suggest_migrations([("workday", "h/acme/site")], probe)
    assert len(out) == 1
    assert out[0].new_provider == "greenhouse"  # first of (greenhouse, lever, ashby, workable)


def test_probe_runs_once_per_distinct_target() -> None:
    # two dead boards for the same company must not probe the same candidate twice
    seen: list[list[tuple[str, str]]] = []

    def probe(targets):
        seen.append(list(targets))
        return {t: BoardHealth.EMPTY for t in targets}

    suggest_migrations([("greenhouse", "acme"), ("workday", "h/acme/site")], probe)
    assert len(seen) == 1  # one batched probe
    assert len(seen[0]) == len(set(seen[0]))  # no duplicate targets


def test_already_watched_candidate_is_skipped() -> None:
    # if the company is already watched (and OK) elsewhere, do not suggest re-adding it
    def probe(targets):
        return {t: BoardHealth.OK for t in targets}

    out = suggest_migrations(
        [("workday", "h/veeva/site")], probe, skip={("lever", "veeva"), ("greenhouse", "veeva"),
                                                    ("ashby", "veeva"), ("workable", "veeva")}
    )
    assert out == []


def test_trigger_set_is_dead_error_empty_not_ok_or_unreachable() -> None:
    # UNREACHABLE is transient (network), not a migration signal; OK needs no check
    assert MIGRATION_TRIGGER == {BoardHealth.DEAD, BoardHealth.ERROR, BoardHealth.EMPTY}


def test_no_probe_at_all_when_no_board_is_unhealthy() -> None:
    # the "zero extra requests when every board is healthy" guarantee: probe must never be called
    def probe(_targets):
        raise AssertionError("probe must not run when there are no unhealthy boards")

    assert suggest_migrations([], probe) == []

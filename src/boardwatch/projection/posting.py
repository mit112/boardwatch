"""The posting-context seam: JD skills + the page budget for one posting, in one call.

The single route to those inputs. It composes, in order: preflight (so a posting whose
taxonomy version moved has an extraction row), the current taxonomy, the posting's current
OPEN version — the same two-line status/version check `reports.tailor` uses, but raised as
this package's own typed refusals (`POSTING_NO_CURRENT_VERSION`, `POSTING_NOT_OPEN`), since
they are first-class business outcomes of this seam, not an infra failure to leave as a
foreign `RuntimeError` — Task 16's `jd_skills_for` (a miss is `NO_JD_EXTRACTION`, never a
silent empty set), and the global page-budget column with the same `max(1, …)` floor
`run_tailor` applies at its call site.

`plan_tier_a` (reports/tailor.py:385) looks like this seam and is not usable: it requires a
`resume_path`, loads personas, and builds/applies/enforces a whole tailor plan — all of
which projection replaces.

Imports `boardwatch.reports.tailor` — legal in this direction only. `reports/tailor.py`
must never import `boardwatch.projection` back: `TAILOR_ROOTS`
(tests/profile_bundle/test_profile_bundle_tailor_isolation.py) walks the tailor closure
transitively, and `boardwatch.projection` imports `boardwatch.profile_bundle`, so a reverse
edge would drag `profile_bundle` into the tailor closure and fail that wall.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Engine, select

from boardwatch.core.settings import Settings
from boardwatch.extract.preflight import run_preflight
from boardwatch.extract.taxonomy import Taxonomy
from boardwatch.projection.errors import ProjectionIssue, raise_violation
from boardwatch.reports.tailor import jd_skills_for
from boardwatch.store.queries import current_posting_versions, get_profile
from boardwatch.store.tables import postings


@dataclass(frozen=True)
class PostingContext:
    posting_id: int
    posting_version_id: int
    jd_skills: frozenset[str]
    page_budget: int


def posting_context(
    engine: Engine, settings: Settings, posting_id: int, *, taxonomy: Taxonomy
) -> PostingContext:
    """`(jd_skills, page_budget)` for `posting_id`, resolved against its current OPEN
    version. Raises `ProjectionError` for every refusal: `POSTING_NO_CURRENT_VERSION` for
    a posting with no current version, `POSTING_NOT_OPEN` for one that is not open (the
    same two-line guard `reports/tailor.py:333-336` uses), and `NO_JD_EXTRACTION` when the
    taxonomy extraction that backs `jd_skills_for` is missing even after preflight.

    The taxonomy is injected rather than loaded here so that one run scores every posting under
    one taxonomy. Loading it per call let JD extraction for posting 2 run under a taxonomy that
    selection was not using — a stale *transformation*, invisible to every digest check.
    `resolve_projection_run` (`projection/run.py`) is what resolves it once per run.

    `run_preflight` stays: it is extraction preflight, not configuration — it backfills the
    extraction rows `jd_skills_for` then reads, and owns its own taxonomy load for that.
    """
    run_preflight(engine, settings)
    with engine.connect() as conn:
        cv = current_posting_versions(conn, [posting_id]).get(posting_id)
        if cv is None:
            raise_violation(
                ProjectionIssue.POSTING_NO_CURRENT_VERSION,
                f"posting {posting_id} has no current version",
                where=f"posting:{posting_id}",
            )
        status = conn.execute(
            select(postings.c.status).where(postings.c.id == posting_id)
        ).scalar_one()
        if status != "open":
            raise_violation(
                ProjectionIssue.POSTING_NOT_OPEN,
                f"posting {posting_id} is not open (status={status!r})",
                where=f"posting:{posting_id}",
            )
        found = jd_skills_for(conn, posting_id, taxonomy=taxonomy)
        if found is None:
            raise_violation(
                ProjectionIssue.NO_JD_EXTRACTION,
                f"no taxonomy extraction for posting {posting_id} at engine_version "
                f"{taxonomy.version!r}",
                where=f"posting:{posting_id}",
            )
        profile_row = get_profile(conn)
    # No floor on the stored column (reports/tailor.py:555's own note): a missing profile
    # row or a non-positive stored value both fall back to 1 rather than being trusted
    # verbatim — a 0 would make every projected résumé exceed the budget by definition.
    page_budget = max(1, profile_row.resume_max_pages) if profile_row is not None else 1
    return PostingContext(
        posting_id=cv.posting_id,
        posting_version_id=cv.posting_version_id,
        jd_skills=frozenset(found),
        page_budget=page_budget,
    )

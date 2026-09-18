"""The Greenhouse application form's hard stops — the requirements that are NOT in the JD.

**Measured live 2026-09-17.** Three apply-lane leads a hand pre-flight withdrew carried a
citizenship or export-control hard stop that appears ONLY on the Greenhouse application form. A
`body_text` grep for citizen/clearance/ITAR/export returned **0 hits on all three**, so nothing in
the eligibility engine, the judge or the ranker can reach this class: they all read the frozen JD,
and the requirement is not in it.

    tenet3/8810809002      "This position requires current U. S. citizenship in order to achieve
                            and maintain a security clearance. Are you currently a U. S. citizen?"
    relativity/8726261002  label "EXPORT COMPLIANCE", the requirement in its DESCRIPTION
                            ("... must either be a "U.S. person" as defined by those regulations")
    giftogram/4392576009   "Are you a US Citizen or Green Card Holder that can work onsite ..."

**GREENHOUSE-ONLY BY CONSTRUCTION, and that is not a coverage gap to close later.** Greenhouse's
public job endpoint returns the form when asked (`?questions=true`); Ashby's posting API and
Lever's do not expose it at all. Reach on 2026-09-17 is **22 of 400 apply-lane leads** — a small
share of the queue, and the entire form-only class, which nothing else in this repo can see.

**THIS MODULE NEVER WRITES A VERDICT.** A hit routes the lead to `_review` and stops. It does not
touch `eligibility/`, it does not touch `postings`, and it cannot produce `INELIGIBLE`: the
keystone requires a quoted span from the FROZEN JD, the form is not the frozen JD, and review is
the fail-open direction D-380 demands for a reading no rule can quote a span for. D-477 refused a
deterministic body-seniority verdict family for the same reason and that restraint applies here.

Nor does it read `eligibility_facts_json`. Which profile statuses does a hit hold? **All of them.**
The reader decides — a citizen answering the citizenship question is a two-second read — and that
is what keeps this module user-agnostic, which multi-tenancy requires.

**The catalog is deliberately NOT `rules.yaml`.** Editing that file moves `rules_hash`, which
re-keys every permanent disposition and restarts the 14-day confirm clock (the ROADMAP freeze
rule). These three surfaces are a question-form catalog, versioned as data here, and `rules.yaml`
owes them after 2026-09-19 when the freeze lifts.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from boardwatch.core.html_text import html_to_text
from boardwatch.lanes.dereference import parse_posting_target

if TYPE_CHECKING:  # pragma: no cover - typing only
    from sqlalchemy.engine import Connection

    from boardwatch.core.politeness import Fetcher

#: The one provider whose posting endpoint returns the application form.
PROVIDER = "greenhouse"

#: The quoted question's ceiling in `details.json` and on the page's reason chip. Truncated rather
#: than dropped: a cut question still names the requirement, and the longest of the three verified
#: labels is 122 characters, so nothing real is near this.
QUOTE_LIMIT = 300


class QuestionsUnreadable(ValueError):
    """A questions payload that could not be read as one.

    A typed violation at the raise site, so the sweep's fail-open arm can tell "no questions
    known" from a bug in this module without string-matching a message from `json`.
    """


@dataclass(frozen=True)
class FormQuestion:
    """One question on the form, as Greenhouse publishes it.

    `description` is HTML and may be absent; `options` are the `fields[].values[].label` strings.
    Kept as the three separate fields the payload carries rather than pre-joined, because the
    QUOTE the reader acts on is the label alone while the text the catalog matches is all three —
    relativity's label is the two words "EXPORT COMPLIANCE" and its requirement is in the
    description, so neither field can stand in for the other.
    """

    label: str
    description: str | None
    options: tuple[str, ...]

    @property
    def text(self) -> str:
        """Label + description (HTML stripped) + option labels, the text the catalog reads.

        The description is stripped rather than matched raw for two reasons that both bite on the
        live relativity payload: it arrives with `&ldquo;`/`&rdquo;` entities, and a `<br>` sits
        mid-sentence — so a pattern spanning two words would have to match across a tag.
        """
        parts = [self.label]
        if self.description:
            parts.append(html_to_text(self.description))
        parts.extend(self.options)
        return "\n".join(part for part in parts if part)


@dataclass(frozen=True)
class FormSurface:
    """One member of the closed catalog: its id, its pattern, and what it requires in words."""

    surface_id: str
    pattern: re.Pattern[str]
    requirement: str


@dataclass(frozen=True)
class FormQuestionHit:
    """Which surface fired, and the question it fired on — quoted, bounded, verbatim."""

    surface_id: str
    question: str


#: The CLOSED catalog. Three surfaces, versioned as data, local to this module. A question that
#: matches none of them is not a hit; out-of-catalog is never a new bucket.
#:
#: The members DO NOT OVERLAP, and the giftogram string is what forces that: "Are you a US Citizen
#: or Green Card Holder" satisfies `citizenship_required`'s "are you a US citizen" reading as well
#: as its own, so that member carries a negative lookahead for the "or green card / or permanent
#: resident" continuation. They are genuinely different questions — a green-card holder answering
#: the second one clears it — and a catalog that let both fire could not say which class a lead is
#: in.
CATALOG: tuple[FormSurface, ...] = (
    FormSurface(
        surface_id="citizenship_required",
        # Two alternatives, because the requirement is stated both ways and tenet3's label states
        # it BOTH ways in one sentence.
        #
        # `U\.?\s?S\.?` — the OPTIONAL SPACE AFTER THE PERIOD — is in both of them, and it is not
        # decoration. The live tenet3 label spells it "U. S." throughout, so without it the
        # "are you" alternative matches nothing there and the label is caught only by the
        # "requires ... citizenship" one. A form that asked the question WITHOUT restating the
        # requirement — "Are you currently a U. S. citizen?" and nothing else — would then be
        # missed entirely, which is the recall hole the second alternative hides.
        pattern=re.compile(
            r"\bare\s+you\s+(?:currently\s+)?(?:an?\s+)?"
            r"(?:U\.?\s?S\.?|United\s+States)\s+citizen\b"
            r"(?!\s*(?:or|/)\s*(?:a\s+)?(?:green\s*card|permanent\s+resident))"
            r"|requires?\s+(?:current\s+)?(?:U\.?\s?S\.?|United\s+States)\s+citizenship",
            re.IGNORECASE,
        ),
        requirement="US citizenship, on the application form only",
    ),
    FormSurface(
        surface_id="us_person_export_control",
        # BOTH conditions, in the SAME question — two lookaheads rather than two catalog members,
        # because "U.S. person" on its own is EEO-adjacent boilerplate and "export control" on its
        # own is a company description. It is the pair that is a hard stop. `persons?` rather than
        # `person`: the live relativity description says "U.S. Persons" before it says
        # "U.S. person", and a form that only used the plural would otherwise read as no hit.
        pattern=re.compile(
            r"(?=[\s\S]*\bU\.?S\.?\s+persons?\b)(?=[\s\S]*(?:\bITAR\b|export\s+control))",
            re.IGNORECASE,
        ),
        requirement="ITAR/export-control US-person status, on the application form only",
    ),
    FormSurface(
        surface_id="citizen_or_green_card",
        pattern=re.compile(
            r"citizen\s+or\s+(?:a\s+)?(?:green\s*card|permanent\s+resident)",
            re.IGNORECASE,
        ),
        requirement="US citizenship or permanent residency, on the application form only",
    ),
)


def questions_url(slug: str, posting_ref: str) -> str:
    """Greenhouse's public job endpoint, with the form attached."""
    return (
        f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs/{posting_ref}?questions=true"
    )


def greenhouse_target(apply_url: str | None) -> tuple[str, str] | None:
    """`(slug, posting_ref)` for a Greenhouse posting URL, or `None` for anything else.

    `parse_posting_target` is the one function in this repo that reads a posting reference back
    out of a board URL, and it is REUSED rather than re-implemented: a second URL parser here
    would be a second answer to "which posting is this", and the two would drift. It raises for a
    URL it does not recognise or cannot resolve, which for this gate is simply "not a Greenhouse
    posting we can ask about" — not a failure the run needs to hear about.
    """
    if apply_url is None:
        return None
    try:
        target = parse_posting_target(apply_url)
    except ValueError:  # UnknownBoardURL / UnresolvablePostingURL, both ValueError subclasses
        return None
    if target.provider != PROVIDER:
        return None
    return target.slug, target.posting_ref


def parse_questions(content: bytes) -> tuple[FormQuestion, ...]:
    """The payload's `questions[]`, and NOTHING else.

    **`compliance[]` is excluded structurally, not by pattern.** Every Greenhouse board carries
    four `type: eeoc` blocks — CC-305, VEVRAA and two self-identification statements — and a
    company's own equal-opportunity clause names citizenship status outright. Matching them would
    hold EVERY Greenhouse lead for review, which is worse than having no gate at all.
    `demographic_questions` and `location_questions` are out for the same reason: they are the
    same boilerplate on every board and belong to no requisition's requirements.

    `"questions": null` is a real answer Greenhouse gives for some boards — "this board publishes
    no form" — and reads as the empty tuple, never as an error.
    """
    try:
        payload = json.loads(content)
    except ValueError as exc:
        raise QuestionsUnreadable(f"not a JSON payload: {exc}") from exc
    if not isinstance(payload, dict):
        raise QuestionsUnreadable(f"payload is {type(payload).__name__}, not an object")
    raw = payload.get("questions")
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise QuestionsUnreadable(f"questions is {type(raw).__name__}, not a list")
    return tuple(_question(entry) for entry in raw)


def _question(entry: Any) -> FormQuestion:
    if not isinstance(entry, dict):
        raise QuestionsUnreadable(f"question is {type(entry).__name__}, not an object")
    label = entry.get("label")
    description = entry.get("description")
    if not isinstance(label, str) or not isinstance(description, (str, type(None))):
        raise QuestionsUnreadable(f"question {label!r} has no readable label or description")
    options: list[str] = []
    for field in entry.get("fields") or []:
        if not isinstance(field, dict):
            raise QuestionsUnreadable("fields entry is not an object")
        for value in field.get("values") or []:
            if isinstance(value, dict) and isinstance(value.get("label"), str):
                options.append(value["label"])
    return FormQuestion(label=label, description=description, options=tuple(options))


def match_questions(questions: tuple[FormQuestion, ...]) -> FormQuestionHit | None:
    """The FIRST question matching a catalog surface, in catalog order, or `None`.

    Per question rather than over the joined form, which is what the export surface needs: it
    requires "U.S. person" and ITAR/export control in the SAME question, and a form that mentions
    ITAR in a company blurb and "U.S. person" in an unrelated block is not a hard stop.

    First-match is safe precisely because the catalog members do not overlap (see :data:`CATALOG`),
    so "first" and "only" are the same answer on every real form; a future member that overlapped
    would be caught by the catalog test rather than silently ranked here.
    """
    for question in questions:
        for surface in CATALOG:
            if surface.pattern.search(question.text):
                return FormQuestionHit(
                    surface_id=surface.surface_id, question=question.label[:QUOTE_LIMIT]
                )
    return None


def encode_questions(questions: tuple[FormQuestion, ...]) -> list[dict[str, Any]]:
    """The fetched form, as the `questions_json` column holds it.

    The FETCHED payload is persisted, never the match, so the catalog is applied fresh on every
    read: adding a surface takes effect on the next reconcile without re-asking any board. Stored
    as the three fields Greenhouse published rather than as the joined text for the same reason —
    the quote the reader acts on is the label, and joining would lose which part was which.
    """
    return [
        {"label": q.label, "description": q.description, "options": list(q.options)}
        for q in questions
    ]


def decode_questions(raw: object) -> tuple[FormQuestion, ...]:
    """Inverse of :func:`encode_questions`.

    Raises :class:`QuestionsUnreadable` on a malformed row: this module wrote it, so a row it
    cannot read is a bug here rather than a fact about a board, and the caller's fail-open arm
    must not quietly absorb it as "no questions known".
    """
    if not isinstance(raw, list):
        raise QuestionsUnreadable(f"stored questions are {type(raw).__name__}, not a list")
    try:
        return tuple(
            FormQuestion(
                label=str(entry["label"]),
                description=entry["description"],
                options=tuple(str(option) for option in entry["options"]),
            )
            for entry in raw
        )
    except (KeyError, TypeError) as exc:
        raise QuestionsUnreadable(f"stored question is not readable: {exc}") from exc


def fetch_questions(
    fetcher: Fetcher, *, slug: str, posting_ref: str
) -> tuple[FormQuestion, ...] | None:
    """One GET for one posting's form. `None` means NO QUESTIONS KNOWN, for any reason.

    **Fail-open on ANY error** — timeout, non-200, a 200 that will not parse — and the return type
    is what enforces it: `None` (unfetched) and `()` (fetched, no form) are different values, and
    only the second is ever cached. An error must never cost the owner an application, and it must
    never raise into `sync_queue`, which holds COPIES of work the run already delivered.

    Through `Fetcher`, so `boards-api.greenhouse.io` — a host the board scan already hits every
    run — is paced under the SAME per-host lock rather than by a second client of our own.
    """
    try:
        result = fetcher.get(questions_url(slug, posting_ref))
        return parse_questions(result.content)
    except Exception:  # noqa: BLE001 - the fail-open direction; see the docstring
        return None


@dataclass(frozen=True)
class FormQuestionSweep:
    """What one run's fetch pass did. Reported, because an unfetched lead is an unasked question.

    `unfetched` and `budget_refused` are kept apart: the first is a board that would not answer
    and the second is work this run declined to do. Both mean "no questions known" at the lane,
    and they lead to different investigations — one is a provider fault, the other is a knob.
    """

    candidates: int = 0
    cached: int = 0
    fetched: int = 0
    unfetched: int = 0
    budget_refused: int = 0


def sweep_form_questions(
    conn: Connection, *, fetcher: Fetcher, budget: int
) -> FormQuestionSweep:
    """Fetch the form ONCE per `posting_version_id` for every delivered Greenhouse lead.

    Keyed on the VERSION, not the posting: a revised requisition is a new subject and its form may
    have changed with it, which is exactly when the question is worth re-asking. Everything already
    stored under the current version is free, so steady-state cost is the leads delivered since the
    last run and nothing else.

    **Not restricted to leads currently in the apply lane**, although that is where the class was
    measured. A form hard stop outranks every other review reason, so fetching only apply-lane
    leads would make a held lead's REPORTED reason depend on whether something else also held it —
    a `role_unconfirmed` lead with a citizenship question would be sent to the JD, which does not
    mention it. Closed postings ARE excluded: `classify` drains them above the form branch, so no
    answer could move them, and a GET for a dead requisition is a GET spent on nothing.

    `budget` bounds the GETs, never the cache reads. `0` disarms the sweep while still reporting
    the whole candidate population as refused, so a disarmed pass reads as declined work rather
    than as a clean queue. Each row commits on its own, so a fault mid-sweep keeps what landed.
    """
    # Function-local, like `delivery_queries.review_job_ids`' own import of `review_gate`: the
    # store module reads this module's catalog on every queue read, so the two can only meet at
    # call time. `delivered_unapplied` is the SAME read the lane, the folder tree and the page
    # derive from, which is what stops the sweep asking about a different set of leads than the
    # gate is going to judge (D-332).
    from boardwatch.store.delivery_queries import delivered_unapplied  # noqa: PLC0415
    from boardwatch.store.form_question_queries import (  # noqa: PLC0415
        cached_form_questions,
        record_form_questions,
    )
    from boardwatch.store.queries import current_posting_versions  # noqa: PLC0415

    rows = [
        row
        for row in delivered_unapplied(conn, skipped=set())
        if row.verdict != "ineligible" and not row.closed
    ]
    targets = {row.posting_id: greenhouse_target(row.apply_url) for row in rows}
    versions = current_posting_versions(
        conn, [row.posting_id for row in rows if targets[row.posting_id] is not None]
    )
    pending: list[tuple[int, str, str]] = []
    for row in rows:
        target = targets[row.posting_id]
        version = versions.get(row.posting_id)
        if target is None or version is None:
            continue
        pending.append((version.posting_version_id, *target))

    known = cached_form_questions(conn, [version_id for version_id, _, _ in pending])
    cached = fetched = unfetched = refused = 0
    for version_id, slug, posting_ref in pending:
        if version_id in known:
            cached += 1
            continue
        if fetched + unfetched >= budget:
            refused += 1
            continue
        questions = fetch_questions(fetcher, slug=slug, posting_ref=posting_ref)
        if questions is None:
            unfetched += 1
            continue
        record_form_questions(conn, version_id, encode_questions(questions))
        conn.commit()
        fetched += 1
    return FormQuestionSweep(
        candidates=len(pending),
        cached=cached,
        fetched=fetched,
        unfetched=unfetched,
        budget_refused=refused,
    )

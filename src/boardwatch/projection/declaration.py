"""`{config_dir}/projection.yaml` — the owner's editorial declaration.

It lives OUTSIDE the bundle on purpose: "which entries appear, in what order" is a rendering
decision, and the bundle design warns against encoding renderer decisions into the knowledge
schema.

`kind` is declared, never derived. A volunteer role is an `affiliation` in the bundle and belongs
under Experience on the page — entity type is knowledge, section placement is editorial.
"""

from __future__ import annotations

import hashlib
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from boardwatch.profile_bundle.models.base import PredicateId
from boardwatch.profile_bundle.yaml_writer import document_bytes
from boardwatch.projection.errors import ProjectionIssue, raise_violation


class EntryKind(StrEnum):
    """The closed catalog `Entry.kind` should have had.

    `tailor/model.py:38` types `kind` as an open `str` with a default, and BOTH renderer section
    filters are equality tests (`tailor/render/latex.py:155`, `:170`) — so a third value matches
    neither section and the entry is silently omitted from the PDF entirely. Nothing else in
    `src/` validates it. This enum is the only guard.
    """

    EXPERIENCE = "experience"
    PROJECT = "project"


class _Strict(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class SkillGroupDeclaration(_Strict):
    """`skills` are bundle skill IDs, not display strings.

    `tailor.model.SkillGroup` has `label` + `items: list[str]`, and `items` holds rendered text.
    The id-to-text mapping is `pool.py`'s, through `SkillRecord.canonical_name`.
    """

    label: str = Field(min_length=1)
    skills: tuple[str, ...] = Field(min_length=1)


class DateRangeDeclaration(_Strict):
    """A date range assembled from TWO facts, for the entity kinds whose catalog models dates as a
    start/end pair rather than as one `date_range` value.

    `project.start_date`/`project.end_date` and `education.start_date`/`education.end_date` are the
    catalog's only `year_month` predicates, and the pair is deliberate (D-177 finding 3):
    `YearMonthValue` holds one scalar, so a single extraction rule cannot yield both halves. The
    alternative shape — a `dates` template reading `'{project.start_date} – {project.end_date}'` —
    makes the owner retype the separator per entry, and cannot express an open range at all,
    because a missing end fact is a fatal unresolved placeholder.

    **Omitting `end` declares the range OPEN**, and it renders `open_range_label`. A NAMED `end`
    whose fact is missing stays fatal: the absence of a fact is not the owner saying "still going",
    and silently printing "Present" over work that ended would fabricate.
    """

    start: PredicateId
    end: PredicateId | None = None


class EntryDeclaration(_Strict):
    entity_id: str = Field(min_length=1)
    kind: EntryKind
    pinned: bool
    heading: str = Field(min_length=1)
    title: str | None = None
    subtitle: str | None = None
    #: Either a template/literal string, or a two-fact range the projection assembles itself.
    #: The union is not a convenience: the bundle genuinely holds dates in two shapes, so the
    #: declaration admits one form per shape rather than forcing every entity into one of them.
    dates: str | DateRangeDeclaration | None = None
    location: str | None = None
    #: A clickable heading link (project entries): the raw target URL and its display label. The
    #: URL is emitted verbatim into `\href{...}` (not LaTeX-escaped), so it must be a plain URL.
    link_url: str | None = None
    link_label: str | None = None
    claims: tuple[str, ...] = ()
    #: Predicate ids whose facts render as this entry's bullets, in this order (D-188). The
    #: bundle already holds the accomplishment/contribution text as multi-valued facts; naming the
    #: predicate here — declared, never derived, like `kind` — turns them into bullets without a
    #: ClaimRecord. Empty means the entry's bullets come only from `claims`.
    bullet_predicates: tuple[str, ...] = ()
    #: Declares that this entry renders with NO bullets — the "role + organisation + dates only"
    #: state (D-221). Declared, never inferred, for the same reason `kind` is: an entry that merely
    #: *happens* to resolve to zero bullets is an accident (a mistyped predicate, a source nobody
    #: named), and rendering it silently would drop the owner's accomplishments off the page with
    #: nothing on the page to reveal the loss. `BULLET_PREDICATE_NO_FACTS` is deliberately
    #: unaffected: a declared predicate that matches nothing stays fatal, which is why this flag
    #: forbids declaring a bullet source at all rather than excusing one that came up empty.
    bulletless: bool = False

    @model_validator(mode="after")
    def _bulletless_declares_no_bullet_source(self) -> EntryDeclaration:
        # `bulletless` asserts the entry has no bullets; `claims`/`bullet_predicates` name where
        # its bullets come from. Together they are a contradiction, and honouring either side
        # would make the declaration mean something its author did not write. Refuse both-ways
        # rather than pick a precedence.
        if self.bulletless and (self.claims or self.bullet_predicates):
            raise ValueError(
                "a bulletless entry must declare no bullet source: drop `claims` and "
                "`bullet_predicates`, or drop `bulletless`"
            )
        return self

    @model_validator(mode="after")
    def _link_fields_are_paired(self) -> EntryDeclaration:
        # A heading link needs both a target and a visible label: `link_url` without `link_label`
        # would render an invisible `\href{url}{\underline{}}`, and a label without a URL is dead
        # text. Refuse the half-declared case loudly rather than ship either.
        if (self.link_url is None) != (self.link_label is None):
            raise ValueError(
                "link_url and link_label must be set together (a heading link needs both a "
                "target URL and a visible label)"
            )
        return self


class ProjectionDeclaration(_Strict):
    projection_version: int
    #: Declared here, unresolved. `load_declaration` performs no filesystem check on this path;
    #: the projection pool resolves it against `config_dir`, which is only in scope there (R3).
    shell_source: Path
    open_range_label: str = Field(min_length=1)
    skill_groups: tuple[SkillGroupDeclaration, ...] = ()
    entries: tuple[EntryDeclaration, ...] = ()
    no_match_fallback: tuple[str, ...] = ()
    extracurricular: tuple[str, ...] = ()

    @property
    def pinned_ids(self) -> tuple[str, ...]:
        return tuple(e.entity_id for e in self.entries if e.pinned)

    @property
    def candidate_ids(self) -> tuple[str, ...]:
        return tuple(e.entity_id for e in self.entries if not e.pinned)


def load_declaration(path: Path) -> ProjectionDeclaration:
    """Parse and validate. Every refusal is typed and names the offending declaration."""
    if not path.is_file():
        raise_violation(
            ProjectionIssue.DECLARATION_UNREADABLE,
            "no projection declaration at this path",
            where=path.name,
        )
    try:
        raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise_violation(
            ProjectionIssue.MALFORMED_DECLARATION, f"invalid YAML: {exc}", where=path.name
        )
    except (OSError, UnicodeDecodeError) as exc:
        # `path.is_file()` above proves existence at a moment, not read-success: a
        # permission-denied file, a non-UTF-8 file, or one deleted in the gap still reaches
        # `read_text`. Built from `type(exc).__name__`, never `str(exc)` — `OSError.__str__`
        # embeds this path's own absolute form, which the bundle family's diagnostics never leak.
        raise_violation(
            ProjectionIssue.DECLARATION_UNREADABLE,
            f"the declaration could not be read ({type(exc).__name__})",
            where=path.name,
        )
    if not isinstance(raw, dict):
        raise_violation(
            ProjectionIssue.MALFORMED_DECLARATION,
            "the declaration must be a mapping",
            where=path.name,
        )

    # Checked before model validation so the owner gets the specific refusal rather than
    # pydantic's "field required" for a field whose absence is a deliberate design rule. Only a
    # genuinely absent, empty, or whitespace-only string counts as missing here — a wrong-typed
    # value such as `open_range_label: 0` is falsy but present, and its truthful refusal is
    # pydantic's own type error below, not this one.
    label = raw.get("open_range_label")
    if label is None or (isinstance(label, str) and not label.strip()):
        raise_violation(
            ProjectionIssue.MISSING_OPEN_RANGE_LABEL,
            "open_range_label has no default: the word for 'still going' is the owner's, "
            "not ours, and a date range with `end: null` cannot render without it",
            where=path.name,
        )

    _reject_unknown_kinds(raw, path)

    try:
        declaration = ProjectionDeclaration.model_validate(raw)
    except ValidationError as exc:
        raise_violation(ProjectionIssue.MALFORMED_DECLARATION, str(exc), where=path.name)

    _reject_duplicate_entities(declaration, path)
    _reject_duplicate_bullet_predicates(declaration, path)
    _reject_bad_fallback(declaration, path)
    return declaration


def _reject_unknown_kinds(raw: dict[str, Any], path: Path) -> None:
    """Pre-model, so the refusal can name the entity rather than a list index."""
    legal = {k.value for k in EntryKind}
    for declared in raw.get("entries") or []:
        if not isinstance(declared, dict):
            continue
        kind = declared.get("kind")
        if kind not in legal:
            raise_violation(
                ProjectionIssue.UNKNOWN_ENTRY_KIND,
                f"kind {kind!r} is not in the closed catalog {sorted(legal)}; the renderer "
                "filters sections by equality, so an out-of-catalog kind would drop this "
                "entry from the PDF with no error",
                where=f"{path.name}: {declared.get('entity_id')}",
            )


def _reject_duplicate_entities(declaration: ProjectionDeclaration, path: Path) -> None:
    """`entry_id = "entry." + entity_id` is only total if entity ids are unique here."""
    seen: set[str] = set()
    for entry in declaration.entries:
        if entry.entity_id in seen:
            raise_violation(
                ProjectionIssue.DUPLICATE_ENTITY_ID,
                f"{entry.entity_id} is declared more than once",
                where=f"{path.name}: {entry.entity_id}",
            )
        seen.add(entry.entity_id)


def _reject_duplicate_bullet_predicates(declaration: ProjectionDeclaration, path: Path) -> None:
    """A predicate listed twice on one entry would render every one of its facts twice, and each
    pair would share a `bullet_id` (the `fact_id`) — a collision the `bullet_id`-keyed pipeline
    downstream resolves by silently keeping one. Refused at authoring, like a duplicate entity."""
    for entry in declaration.entries:
        seen: set[str] = set()
        for predicate in entry.bullet_predicates:
            if predicate in seen:
                raise_violation(
                    ProjectionIssue.DUPLICATE_BULLET_PREDICATE,
                    f"{predicate} is listed more than once, so its facts would each render twice",
                    where=f"{path.name}: {entry.entity_id}",
                )
            seen.add(predicate)


def _reject_bad_fallback(declaration: ProjectionDeclaration, path: Path) -> None:
    """Without these three, a pinned id in the fallback duplicates an entry and fails late as
    the frozen model's bare `duplicate entry_id`, and an undeclared id is a KeyError."""
    candidates = set(declaration.candidate_ids)
    pinned = set(declaration.pinned_ids)
    seen: set[str] = set()
    for fid in declaration.no_match_fallback:
        if fid in seen:
            raise_violation(
                ProjectionIssue.FALLBACK_ID_DUPLICATED, f"{fid} appears twice", where=path.name
            )
        seen.add(fid)
        if fid in pinned:
            raise_violation(
                ProjectionIssue.FALLBACK_OVERLAPS_PINNED,
                f"{fid} is pinned, so it always renders; listing it as a fallback would "
                "emit it twice",
                where=path.name,
            )
        if fid not in candidates:
            raise_violation(
                ProjectionIssue.FALLBACK_ID_NOT_A_CANDIDATE,
                f"{fid} is not a declared candidate entry",
                where=path.name,
            )


#: Named for the diagnostic `document_bytes` produces on failure, not a real filesystem path.
_DIGEST_DOCUMENT = PurePosixPath("projection.yaml")


def projection_digest(declaration: ProjectionDeclaration) -> str:
    """`sha256:<hex>` over the declaration's parsed-model bytes.

    Hashes `yaml_writer.document_bytes`'s output rather than the source file's own bytes, so
    reflowing the YAML (whitespace, list style) does not move the digest — the input is
    `model_dump(mode="json")`, whose key order is pydantic's declaration order, not the order the
    owner happened to write the file in.

    This is deliberately NOT `profile_bundle.canonical.digest_of`: that module is private to the
    bundle package (`test_no_existing_module_imports_the_bundle_serializer`), and importing it
    from here would be the second, unsanctioned caller that test exists to catch. `document_bytes`
    is not a substitute canonicaliser either — it runs with `sort_keys=False` and performs no
    Unicode normalisation. What makes it safe here is its read-back verification through the
    restricted loader: anything the loader would retype, refuse, or silently alter fails at write
    time, before a digest is ever taken over it.

    One consequence worth stating: a future change to this emitter's own output style would move
    every existing digest and reopen the owner-approval gate. That is the fail-safe direction —
    the owner re-approves rather than an approval silently surviving a format change it never saw.
    """
    payload = declaration.model_dump(mode="json")
    return (
        "sha256:"
        + hashlib.sha256(document_bytes(payload, logical_path=_DIGEST_DOCUMENT)).hexdigest()
    )

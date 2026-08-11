"""Deterministic source enumeration: the four approved adapters (design §18, §18.1).

Gate B's denominator is `len(source-ledger.records)` — the set of `source_record` units enumerated
*before* any LLM candidate extraction. Everything in this module exists to make that number
reproducible from bytes alone:

- **Identity is derived, never proposed.** `source-record.<64hex>` comes from the canonical JSON of
  `["source-record", source_id, normalized_locator]`. An adapter cannot renumber the denominator,
  and neither can anything downstream of one.
- **Content digests are occurrence lineage, not identity.** Editing a paragraph changes that
  record's `record_content_digest` and nothing else: the ID, the ordering, and every other record
  stay exactly as they were, so a source edit does not churn the denominator.
- **Re-enumeration is byte-identical.** Locators, order, IDs, and digests are produced by ordered
  traversal only. Nothing here iterates a `set`, and every sort key is an explicit string.

The Boardwatch résumé source model below is a deliberate *duplicate* of `tailor/model.py`. The
frozen tailor package must not import `profile_bundle`, and `profile_bundle` must not import or
alter the tailor model or loader (§18.1), so the shape is restated rather than shared. One visible
consequence is load-bearing: the tailor `Bullet` collapses every whitespace run in `text` to a
single space, and this adapter must not, because the authored bytes are the datum whose digest
claims lineage over the source.
"""

from __future__ import annotations

import hashlib
import re
import string
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Final, Literal, Protocol

from pydantic import Field, ValidationError

from boardwatch.profile_bundle.canonical import canonical_json_bytes, digest_of
from boardwatch.profile_bundle.errors import ProfileBundleError, RestrictedYamlError
from boardwatch.profile_bundle.models.base import NonBlankStr, SourceRecordId, StrictModel
from boardwatch.profile_bundle.models.imports import ApprovedScope
from boardwatch.profile_bundle.models.policy import SourceKind
from boardwatch.profile_bundle.yaml_loader import load_yaml_bytes

BOARDWATCH_RESUME_V1: Final = "boardwatch-resume-v1"
MARKDOWN_BLOCKS_V1: Final = "markdown-blocks-v1"
STRUCTURED_OBJECTS_V1: Final = "structured-objects-v1"

ScopeKind = Literal["complete_file", "selected_sections"]

#: The locator segment used for blocks that appear before the first heading (§18.1).
ROOT_SEGMENT: Final = "_root"


class EnumerationError(ProfileBundleError):
    """A source cannot be enumerated deterministically, or a locator is out of contract.

    Raised rather than reported as a diagnostic: enumeration produces the denominator, and a
    partial denominator is worse than none. Every caller either gets every record or an error.
    """


# --------------------------------------------------------------------------------------
# Locators (§18)
# --------------------------------------------------------------------------------------

#: The characters left unescaped by the encoding loop: ASCII alphanumerics plus `._-` (§18). One
#: whole-segment exception follows: a body encoding to a reserved segment has its first character
#: escaped anyway, so `_` is unreserved everywhere except at the start of exactly `_root`.
_UNRESERVED: Final[frozenset[str]] = frozenset(string.ascii_letters + string.digits + "._-")

#: Segments that occupy a POSITION an encoded body could otherwise occupy. `_` is unreserved, so
#: without this the encoder returned `_root` unchanged for a heading literally named `_root` and
#: two logical sections shared one namespace — pre-heading content and that heading derived the
#: same record IDs.
#:
#: This is NOT the set of segments an adapter writes literally. `heading`, `paragraph-N`,
#: `objects`, `entries`, `metadata`, `bullets` and the rest are all emitted directly and must NOT
#: be listed here: each occupies a position no encoded body reaches, and reserving one would only
#: make `is_normalized_locator` accept it anywhere. Add a segment here when — and only when — it
#: shares a position with an encoded body, as `_root` shares the first segment of a heading path.
_RESERVED_SEGMENTS: Final[frozenset[str]] = frozenset({ROOT_SEGMENT})

#: Whole-segment spellings `_encode_text` never emits as themselves. Two reasons, one mechanism:
#: a reserved segment would collide with a synthetic one, and `.`/`..` are the traversal spellings
#: §18 forbids in a locator. Both are ESCAPED rather than refused. Refusing was the original
#: behaviour and it made `# .` and `# ..` hard enumeration errors — a legitimate document rendered
#: unenumerable, which is the same defect class as rounds one and three. `%2E` is not a `.` segment,
#: so §18's refusal is satisfied by the escape.
_ESCAPED_WHOLE_SEGMENTS: Final[frozenset[str]] = _RESERVED_SEGMENTS | frozenset({".", ".."})

#: The deterministic duplicate-path suffix `~2`, `~3`, … A `~1` is never emitted, so it is not
#: recognised either; recognising it would make two spellings of the first occurrence.
_DUPLICATE_SUFFIX_RE: Final = re.compile(r"^(?P<body>.*)~(?P<index>[2-9]|[1-9][0-9]+)$")

_ESCAPE_RE: Final = re.compile(r"%([0-9A-F]{2})")


def encode_locator_segment(raw: str, *, adapter: SourceEnumerator) -> str:
    """One locator segment: NFC, trimmed, case-preserved, percent-encoded from UTF-8 bytes.

    A segment is encoded whole, so a value containing `/` becomes `%2F` rather than silently
    becoming two segments and changing the record's identity.
    """
    text = unicodedata.normalize("NFC", raw).strip()
    if not text:
        raise EnumerationError(
            f"{adapter.id}: {raw!r} is not a usable locator segment; a blank body carries no "
            "assertion and has nothing to encode"
        )
    try:
        text.encode("utf-8")
    except UnicodeEncodeError as exc:
        # A JSON source may spell an astral character as a surrogate pair, and a lone half then
        # reaches the encoder. Typed at the raise site: the untyped `UnicodeEncodeError` this
        # replaces escaped `EnumerationError`'s contract that every caller gets every record or
        # a typed error.
        raise EnumerationError(
            f"{adapter.id}: {raw!r} contains an unpaired surrogate and is not encodable text"
        ) from exc
    return _encode_text(text)


def _canonical_encoding(text: str) -> str:
    """Exactly what `encode_locator_segment` produces for `text`, its refusals aside.

    The encoder NFC-normalises and trims *before* encoding, so the predicate has to do the same or
    it accepts spellings the encoder can never emit — `e%CC%81` for a composed `é`, `%20a` for a
    leading space. Each of those derives its own source-record ID, which inflates the Gate B
    denominator with a phantom record and no finding anywhere.
    """
    return _encode_text(unicodedata.normalize("NFC", text).strip())


def _encode_text(text: str) -> str:
    """The pure encoding: no normalisation, no trimming, no refusals.

    Split out so `is_emitted_segment` can be defined as this function's exact inverse rather than
    as a hand-written grammar. A grammar drifts from the encoder; a round trip cannot. Note that
    `is_normalized_locator` is deliberately *weaker* than that inverse — it also admits the `~N`
    suffix and the reserved segments, because it serves owner-authored scope locators too.

    A body that would land on a reserved segment has its first character escaped instead. Refusing
    it outright would make a document carrying such a heading unenumerable, which is the same
    "legitimate source is unimportable" defect the reservation exists to prevent. The escape is
    applied here, in the SHARED encoder, rather than in the Markdown adapter that owns the
    collision: `is_emitted_segment` and `is_normalized_locator` are adapter-blind by necessity, so
    a per-adapter reservation would mean two encoders and the drift this module exists to remove.
    The cost is that a structured key or a résumé identifier literally named `_root` is escaped as
    well, which moves it in §18.1's encoded-key sort order.
    """
    encoded: list[str] = []
    for character in text:
        if character in _UNRESERVED:
            encoded.append(character)
            continue
        encoded.extend(f"%{byte:02X}" for byte in character.encode("utf-8"))
    joined = "".join(encoded)
    if joined not in _ESCAPED_WHOLE_SEGMENTS:
        return joined
    escaped = "".join(f"%{byte:02X}" for byte in joined[0].encode("utf-8"))
    return escaped + joined[1:]


def _decoded_segment(segment: str) -> str | None:
    """The text `segment` encodes, or `None` if it is not a well-formed encoding.

    Only uppercase two-digit escapes are recognised, because that is all `_encode_text` emits, and
    the decoded bytes must be valid UTF-8 — a lone continuation byte is not something any adapter
    can produce.
    """
    raw = bytearray()
    index = 0
    while index < len(segment):
        if segment[index] == "%":
            match = _ESCAPE_RE.match(segment, index)
            if match is None:
                return None
            raw.append(int(match.group(1), 16))
            index = match.end()
            continue
        raw.extend(segment[index].encode("utf-8"))
        index += 1
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return None


def normalize_locator(raw: str, *, adapter: SourceEnumerator) -> str:
    """A complete POSIX-relative locator, normalized to the §18 contract.

    For an authoring tool holding a RAW path — segment bodies as a person typed them. It is not
    the inverse of `is_normalized_locator` and has no production caller: an already-resolved path
    must not be passed through it, because percent-encoding is not idempotent
    (`Alpha%20Beta` becomes `Alpha%2520Beta`) and a body of `_root` becomes `%5Froot`.

    A trailing `~2`/`~3` duplicate suffix on any segment is preserved rather than encoded. That
    suffix is applied *after* encoding when a Markdown heading path repeats (§18.1), so a raw path
    already carrying one keeps it. The cost is that a heading whose body literally ends in `~2`
    cannot be told apart from the second occurrence of the same heading without it; adapters
    encode their own bodies through `encode_locator_segment`, so only owner-authored input is
    affected.

    An absolute or empty locator has no guard of its own here, deliberately: `/a` splits to an
    empty leading segment and `""` splits to one empty segment, so `encode_locator_segment` is
    always the thing that refuses them. A second check would read as coverage it does not provide.

    A `.`/`..` COMPONENT does have a guard, and D-120's reason for deleting it has since inverted:
    `encode_locator_segment` now escapes such a body to `%2E` rather than refusing it, because a
    heading may legitimately be named `.`. In a raw *path* the same spelling means the traversal
    §18 forbids, and silently encoding it would turn "this directory" into a literal segment.
    """
    text = unicodedata.normalize("NFC", raw).strip()
    segments: list[str] = []
    for part in text.split("/"):
        if part in (".", ".."):
            raise EnumerationError(
                f"{adapter.id}: {raw!r} contains a {part!r} path component, which §18 forbids in "
                "a locator"
            )
        match = _DUPLICATE_SUFFIX_RE.match(part)
        if match is not None:
            segments.append(
                encode_locator_segment(match.group("body"), adapter=adapter)
                + f"~{match.group('index')}"
            )
            continue
        segments.append(encode_locator_segment(part, adapter=adapter))
    return "/".join(segments)


def is_emitted_segment(segment: str) -> bool:
    """Whether `segment` is exactly what `encode_locator_segment` produces for its own text.

    No duplicate-suffix exception, deliberately. `~N` is applied by the Markdown adapter to a
    resolved heading path *after* encoding, so it is meaningful there and nowhere else: every
    other adapter writes its segments through the encoder, which escapes `~` to `%7E`. An adapter
    grammar therefore asks this question directly, while `is_normalized_locator` — which is
    adapter-blind, because it also has to admit the scope locators an owner authors — allows the
    suffix. `objects/synthetic~2` is the difference: a normalized locator no adapter can emit.
    """
    if not segment or segment in (".", ".."):
        return False
    decoded = _decoded_segment(segment)
    return decoded is not None and _canonical_encoding(decoded) == segment


def is_normalized_locator(text: str) -> bool:
    """Whether every segment of `text` is a spelling the locator contract admits.

    Deliberately WEAKER than "exactly what an adapter emitted", which is what
    `emits_locator` answers per adapter. This predicate also has to accept the locators an owner
    authors into a `selected_sections` scope, so it admits the `~N` duplicate suffix on any segment
    and a reserved segment at any position. `objects/synthetic~2` is the gap that leaves: a
    normalized locator no adapter can emit, refused by the structured adapter's own grammar.

    Defined as a round trip through the encoder rather than as a grammar. A grammar that merely
    *admits* percent escapes accepts spellings no adapter can produce — `%41` for `A` is the
    obvious one — and a ledger written that way would validate while naming a locator that can
    never be re-derived from its source. Decoding and re-encoding cannot drift from the encoder,
    because it is the encoder.

    A predicate rather than a re-normalization: percent-encoding is not idempotent, so
    `normalize_locator(x) == x` would report every correctly encoded locator as wrong.

    Emptiness and `.`/`..` are refused explicitly; the round trip alone would accept both, since
    each encodes to itself. Unicode form and surrounding whitespace are handled by comparing
    against `_canonical_encoding`, which applies the encoder's own NFC and trim — comparing against
    the bare encoding accepted `e%CC%81` and `%20a`, because an already-escaped decomposed
    character round-trips to itself.
    """
    if not text:
        return False
    for part in text.split("/"):
        if part in _RESERVED_SEGMENTS:
            # Emitted by an adapter directly, so it is not the encoder's output and cannot be
            # compared against it. `_root~2` is refused: the suffix is a heading-path device and
            # a reserved segment is never a heading path.
            continue
        match = _DUPLICATE_SUFFIX_RE.match(part)
        if not is_emitted_segment(match.group("body") if match is not None else part):
            return False
    return True


# --------------------------------------------------------------------------------------
# Derived identity and digests (§18)
# --------------------------------------------------------------------------------------


def derive_source_record_id(source_id: str, normalized_locator: str) -> SourceRecordId:
    """`source-record.<64hex>` over the canonical JSON of `["source-record", id, locator]`."""
    payload = ["source-record", source_id, normalized_locator]
    return "source-record." + hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def source_content_digest(raw: bytes) -> str:
    """SHA256 over the raw source bytes, before any line-ending or Unicode normalization."""
    return "sha256:" + hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class EnumeratedSourceRecord:
    """One atomic unit of the Gate B denominator.

    `atomic_value` is the adapter-normalized value alone: no source or locator metadata, because
    `record_content_digest` must change when the material changes and not when the file it came
    from is renamed.
    """

    source_record_id: str
    source_id: str
    normalized_locator: str
    atomic_value: object
    record_content_digest: str


def _record(source_id: str, locator: str, value: object) -> EnumeratedSourceRecord:
    return EnumeratedSourceRecord(
        source_record_id=derive_source_record_id(source_id, locator),
        source_id=source_id,
        normalized_locator=locator,
        atomic_value=value,
        record_content_digest=digest_of(value),
    )


class SourceEnumerator(Protocol):
    """One versioned, deterministic adapter bound to the source it enumerates.

    `id` and `version` are read-only members rather than plain attributes because every adapter is
    a frozen dataclass: a settable protocol member would refuse them, and an adapter whose identity
    could be reassigned after construction is one whose records cannot be attributed.
    """

    @property
    def id(self) -> str: ...

    @property
    def version(self) -> int: ...

    def enumerate(
        self, source: bytes, *, scope: ApprovedScope
    ) -> tuple[EnumeratedSourceRecord, ...]: ...

    def emits_locator(self, locator: str) -> bool: ...


@dataclass(frozen=True)
class AdapterBinding:
    """One row of §18's closed source-kind / adapter table."""

    enumerator_id: str
    enumerator_version: int
    scope_kind: ScopeKind


#: The closed version-1 pairing (§18). Repository Markdown reuses the Markdown adapter and differs
#: only in the scope it is allowed to carry, which is what makes "widening the scope needs a new
#: owner approval" a property of the ledger rather than of a second enumerator.
SOURCE_KIND_ADAPTERS: Final[Mapping[SourceKind, AdapterBinding]] = {
    SourceKind.BOARDWATCH_RESUME: AdapterBinding(BOARDWATCH_RESUME_V1, 1, "complete_file"),
    SourceKind.MARKDOWN_DOCUMENT: AdapterBinding(MARKDOWN_BLOCKS_V1, 1, "complete_file"),
    SourceKind.STRUCTURED_OBJECTS: AdapterBinding(STRUCTURED_OBJECTS_V1, 1, "complete_file"),
    SourceKind.REPOSITORY_MARKDOWN: AdapterBinding(MARKDOWN_BLOCKS_V1, 1, "selected_sections"),
}


def _decoded(raw: bytes, adapter_id: str) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise EnumerationError(f"{adapter_id}: source is not valid UTF-8 ({exc.reason})") from exc


def _loaded(raw: bytes, adapter_id: str) -> object:
    """Parse a source through the one restricted loader, as typed data.

    Reuses `load_yaml_bytes` rather than `yaml.safe_load`: the same contract that keeps `01` from
    becoming octal inside the bundle must keep it from becoming octal on the way in, or a source
    record's digest would depend on YAML 1.1's implicit resolvers.
    """
    try:
        return load_yaml_bytes(raw, logical_path=PurePosixPath(adapter_id))
    except RestrictedYamlError as exc:
        raise EnumerationError(f"{adapter_id}: {exc}") from exc


# --------------------------------------------------------------------------------------
# boardwatch-resume-v1 (§18.1)
# --------------------------------------------------------------------------------------


class ResumeBullet(StrictModel):
    bullet_id: NonBlankStr
    text: str = Field(min_length=1)
    tech_tags: tuple[str, ...] = ()


class ResumeEntry(StrictModel):
    entry_id: NonBlankStr
    heading: str
    bullets: tuple[ResumeBullet, ...]
    kind: str = "experience"
    title: str | None = None
    dates: str | None = None
    subtitle: str | None = None
    location: str | None = None


class ResumeSkillGroup(StrictModel):
    label: str
    items: tuple[str, ...]


class ResumeSource(StrictModel):
    """Exactly Boardwatch's current logical résumé shape (§18.1), restated package-locally.

    `extra="forbid"` comes from `StrictModel` and is what makes "exactly" enforceable: a stray
    top-level key would otherwise be dropped and its content would never enter the denominator.
    """

    header: tuple[str, ...]
    education: tuple[str, ...]
    skill_groups: tuple[ResumeSkillGroup, ...]
    entries: tuple[ResumeEntry, ...]
    extracurricular: tuple[str, ...] = ()
    title: str | None = None


@dataclass(frozen=True)
class BoardwatchResumeEnumerator:
    """Enumerates a Boardwatch résumé document into its atomic authored values."""

    source_id: str
    id: str = BOARDWATCH_RESUME_V1
    version: int = 1

    def enumerate(
        self, source: bytes, *, scope: ApprovedScope
    ) -> tuple[EnumeratedSourceRecord, ...]:
        _require_complete_file(self, scope)
        try:
            resume = ResumeSource.model_validate(_loaded(source, self.id))
        except ValidationError as exc:
            raise EnumerationError(f"{self.id}: {exc.error_count()} field error(s)") from exc
        return self._records(resume)

    def _scalar(self, text: str, what: str) -> str:
        if not text.strip():
            raise EnumerationError(f"{self.id}: a blank {what} record carries no assertion")
        return unicodedata.normalize("NFC", text)

    def _locator(self, *segments: str) -> str:
        return "/".join(encode_locator_segment(part, adapter=self) for part in segments)

    def emits_locator(self, locator: str) -> bool:
        """Whether `locator` has a shape `_records` can produce, with no source bytes read.

        Validation cannot know WHICH entries a résumé holds without the file, but the seven
        emission stages are a closed set of shapes, so a locator that matches none of them is one
        no enumeration ever produced. Kept beside `_locator` deliberately: a grammar written
        anywhere else drifts from the emitter the first time a stage is added.

        Every variable segment goes through `_locator`, which is `encode_locator_segment` — so it
        is checked with `is_emitted_segment` rather than accepted as any string. This adapter has
        no duplicate-path rule, so `entries/entry~2/metadata` is a spelling it cannot produce even
        though the adapter-blind locator predicate accepts it.
        """
        parts = locator.split("/")
        head = parts[0]
        if head in ("header", "education", "extracurricular"):
            return len(parts) == 2 and _is_index(parts[1])
        if head == "title":
            return len(parts) == 1
        if head == "skill-groups":
            return len(parts) == 3 and is_emitted_segment(parts[1]) and _is_index(parts[2])
        if head == "entries":
            if len(parts) < 3 or not is_emitted_segment(parts[1]):
                return False
            return (len(parts) == 3 and parts[2] == "metadata") or (
                len(parts) == 4 and parts[2] == "bullets" and is_emitted_segment(parts[3])
            )
        return False

    def _records(self, resume: ResumeSource) -> tuple[EnumeratedSourceRecord, ...]:
        """The design's seven emission stages, in order.

        Stages 5 and 6 are separate passes, so every entry's metadata precedes every bullet. §18.1
        numbers them as distinct stages, and `sources[].source_record_ids` must equal this order
        exactly, so the reading is pinned by test rather than left to whichever loop came first.
        """
        records: list[EnumeratedSourceRecord] = []

        def emit(locator: str, value: object) -> None:
            records.append(_record(self.source_id, locator, value))

        for index, line in enumerate(resume.header, start=1):
            emit(self._locator("header", str(index)), self._scalar(line, "header"))

        if resume.title is not None:
            emit(self._locator("title"), self._scalar(resume.title, "title"))

        for index, row in enumerate(resume.education, start=1):
            emit(self._locator("education", str(index)), self._scalar(row, "education"))

        seen_labels: set[str] = set()
        for group in resume.skill_groups:
            label = unicodedata.normalize("NFC", group.label).strip()
            if not label:
                raise EnumerationError(f"{self.id}: a skill group has a blank label")
            if label in seen_labels:
                raise EnumerationError(f"{self.id}: duplicate skill-group label {label!r}")
            seen_labels.add(label)
            for index, item in enumerate(group.items, start=1):
                emit(
                    self._locator("skill-groups", label, str(index)),
                    {"label": label, "item": self._scalar(item, "skill item")},
                )

        _refuse_duplicate_resume_ids(self.id, resume)

        for entry in resume.entries:
            emit(
                self._locator("entries", entry.entry_id, "metadata"),
                entry.model_dump(mode="json", exclude={"bullets"}),
            )
        for entry in resume.entries:
            for bullet in entry.bullets:
                emit(
                    self._locator("entries", entry.entry_id, "bullets", bullet.bullet_id),
                    bullet.model_dump(mode="json"),
                )

        for index, row in enumerate(resume.extracurricular, start=1):
            emit(
                self._locator("extracurricular", str(index)),
                self._scalar(row, "extracurricular"),
            )
        return tuple(records)


def _refuse_duplicate_resume_ids(adapter_id: str, resume: ResumeSource) -> None:
    """Entry and bullet IDs must be unique globally (§18.1).

    Position-derived identity is allowed only where the source shape offers no stable row ID —
    header, education, skill items, extracurricular. Where it does offer one, a duplicate would
    silently collapse two records into one denominator unit.
    """
    entry_ids = [_identity(entry.entry_id) for entry in resume.entries]
    if len(set(entry_ids)) != len(entry_ids):
        raise EnumerationError(f"{adapter_id}: duplicate entry_id")
    bullet_ids = [
        _identity(bullet.bullet_id) for entry in resume.entries for bullet in entry.bullets
    ]
    if len(set(bullet_ids)) != len(bullet_ids):
        raise EnumerationError(f"{adapter_id}: duplicate bullet_id")


def _identity(authored_id: str) -> str:
    """The form an authored ID is compared in: exactly what its locator segment will use.

    Comparing raw strings let `e` and `" e "` through as two entries, and both then emitted
    `entries/e/metadata` — one derived ID for two records. The ledger model refuses that later, but
    by then the adapter has already handed extraction an immutable package violating its own
    contract.
    """
    return unicodedata.normalize("NFC", authored_id).strip()


# --------------------------------------------------------------------------------------
# markdown-blocks-v1 (§18.1)
# --------------------------------------------------------------------------------------

#: How deep Markdown headings nest. `_HEADING_RE` is BUILT from this and `emits_locator` READS it,
#: so the grammar's depth cap cannot drift from the syntax the parser accepts. Restating the number
#: in the grammar is what let a seven-level forged record pass every validation layer.
_MAX_HEADING_LEVEL: Final = 6

_HEADING_RE: Final = re.compile(rf"^(#{{1,{_MAX_HEADING_LEVEL}}})[ \t]+(.+?)[ \t]*$")
_FENCE_RE: Final = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_LIST_ITEM_RE: Final = re.compile(r"^ {0,3}(?:[-+*]|[0-9]+[.)])[ \t]+")


#: The block kinds `MarkdownBlocksEnumerator._blocks` emits with a 1-based index. `heading` is
#: deliberately absent: it is the one kind whose locator carries no number.
_NUMBERED_BLOCK_KINDS: Final[frozenset[str]] = frozenset({"paragraph", "fence", "list-item"})


def is_resolved_heading_path(locator: str) -> bool:
    """Whether `locator` is a path `_blocks` can resolve a heading stack to (§18.1).

    This is what a `selected_sections` scope locator must be — "Selected locators refer to these
    resolved paths, including any `~N` suffix" — and it is a strictly different shape from a record
    locator: no terminal segment, at most `_MAX_HEADING_LEVEL` segments, and never the reserved
    `_root`, which holds the blocks *before* the first heading and is therefore not a section.

    Lives beside the emitter for the same reason `emits_locator` does. `selected_sections` pairs
    with exactly one adapter in `SOURCE_KIND_ADAPTERS`, so a Markdown-specific predicate is the
    whole of the contract rather than one adapter's share of it.
    """
    segments = locator.split("/")
    if not 1 <= len(segments) <= _MAX_HEADING_LEVEL:
        return False
    return all(_is_heading_segment(segment) for segment in segments)


def _is_heading_segment(segment: str) -> bool:
    """One resolved heading path segment: an encoded body, optionally with the `~N` suffix.

    `_unique_segment` applies the suffix after encoding, so this is the one place a raw `~` is
    something an adapter emits. A reserved segment is not a heading path and is refused here.
    """
    match = _DUPLICATE_SUFFIX_RE.match(segment)
    return is_emitted_segment(match.group("body") if match is not None else segment)


def _is_numbered_terminal(terminal: str) -> bool:
    """`<kind>-<N>` for a closed block kind, which is what `_locator` emits for a non-heading."""
    kind, _, index = terminal.rpartition("-")
    return kind in _NUMBERED_BLOCK_KINDS and _is_index(index)


def _is_index(text: str) -> bool:
    """A 1-based decimal index with no sign, padding, or separator.

    `str.isdigit` is not enough — it admits superscripts and other Unicode digit forms, which would
    let two spellings of "1" name two records for one block.
    """
    return text.isascii() and text.isdigit() and not text.startswith("0")


def _indent_columns(line: str) -> int:
    """Leading indentation in columns: a space is one, a tab advances to the next multiple of 4."""
    column = 0
    for character in line:
        if character == " ":
            column += 1
        elif character == "\t":
            column += 4 - (column % 4)
        else:
            break
    return column


def _closes(line: str, character: str, length: int) -> bool:
    """Whether `line` closes a fence opened with `length` copies of `character`."""
    match = _FENCE_RE.match(line)
    if match is None:
        return False
    run = match.group(1)
    if run[0] != character or len(run) < length:
        return False
    return not line[match.end() :].strip()


@dataclass(frozen=True)
class _Block:
    heading_path: str
    kind: str
    text: str


@dataclass(frozen=True)
class MarkdownBlocksEnumerator:
    """Enumerates a Markdown document into heading, paragraph, list-item, and fence records."""

    source_id: str
    id: str = MARKDOWN_BLOCKS_V1
    version: int = 1

    def enumerate(
        self, source: bytes, *, scope: ApprovedScope
    ) -> tuple[EnumeratedSourceRecord, ...]:
        text = _decoded(source, self.id).replace("\r\n", "\n").replace("\r", "\n")
        blocks, heading_paths = self._blocks(text.split("\n"))
        if scope.kind == "selected_sections":
            blocks = self._selected(blocks, heading_paths, scope.locators)
        return tuple(
            _record(self.source_id, self._locator(block, index), block.text)
            for block, index in _numbered(blocks)
        )

    def _locator(self, block: _Block, index: int) -> str:
        if block.kind == "heading":
            return f"{block.heading_path}/heading"
        return f"{block.heading_path}/{block.kind}-{index}"

    def emits_locator(self, locator: str) -> bool:
        """Whether `locator` has a shape `_locator` can produce, with no source bytes read.

        Which heading path exists genuinely needs the file; its DEPTH and its segments' spelling do
        not. `_HEADING_RE` nests at most `_MAX_HEADING_LEVEL` levels, so a path deeper than that is
        one no enumeration of any Markdown source produced — the grammar used to accept any depth
        because it restated the emitter's rules instead of reading its constants.

        The terminal segment is `heading`, or one of the closed block kinds followed by a 1-based
        index. `_root` is the one path that is not a heading path: it holds the blocks before the
        first heading, so it stands alone and never carries `/heading`.
        """
        parts = locator.split("/")
        if len(parts) < 2 or len(parts) > _MAX_HEADING_LEVEL + 1:
            return False
        path, terminal = parts[:-1], parts[-1]
        if path == [ROOT_SEGMENT]:
            return _is_numbered_terminal(terminal)
        if not all(_is_heading_segment(part) for part in path):
            return False
        return terminal == "heading" or _is_numbered_terminal(terminal)

    def _blocks(self, lines: list[str]) -> tuple[list[_Block], list[str]]:
        """One ordered pass. Returns the blocks and every resolved heading path, in source order."""
        blocks: list[_Block] = []
        heading_paths: list[str] = []
        used: set[str] = set()
        stack: list[str] = []
        current = ROOT_SEGMENT
        paragraph: list[str] = []

        def flush() -> None:
            if paragraph:
                blocks.append(_Block(current, "paragraph", "\n".join(paragraph)))
                paragraph.clear()

        index = 0
        while index < len(lines):
            line = lines[index]

            heading = _HEADING_RE.match(line)
            if heading is not None:
                flush()
                # A blank body encodes to an empty segment, which `encode_locator_segment`
                # refuses below, so it is not checked a second time here.
                body = unicodedata.normalize("NFC", heading.group(2)).strip()
                parent = stack[: len(heading.group(1)) - 1]
                segment = _unique_segment(
                    parent, encode_locator_segment(body, adapter=self), used
                )
                stack = [*parent, segment]
                current = "/".join(stack)
                used.add(current)
                heading_paths.append(current)
                blocks.append(_Block(current, "heading", line))
                index += 1
                continue

            fence = _FENCE_RE.match(line)
            if fence is not None:
                flush()
                run = fence.group(1)
                end = index + 1
                while end < len(lines) and not _closes(lines[end], run[0], len(run)):
                    end += 1
                if end >= len(lines):
                    raise EnumerationError(
                        f"{self.id}: fence opened at line {index + 1} is never closed"
                    )
                blocks.append(_Block(current, "fence", "\n".join(lines[index : end + 1])))
                index = end + 1
                continue

            if _LIST_ITEM_RE.match(line) is not None:
                flush()
                opener = _indent_columns(line)
                end = index + 1
                while (
                    end < len(lines)
                    and lines[end].strip()
                    and _indent_columns(lines[end]) > opener
                ):
                    end += 1
                blocks.append(_Block(current, "list-item", "\n".join(lines[index:end])))
                index = end
                continue

            if not line.strip():
                flush()
                index += 1
                continue

            paragraph.append(line)
            index += 1

        flush()
        return blocks, heading_paths

    def _selected(
        self, blocks: list[_Block], heading_paths: list[str], locators: tuple[str, ...]
    ) -> list[_Block]:
        """An exact selected heading takes its own record and every descendant block (§18.1)."""
        known = set(heading_paths)
        prefixes: list[str] = []
        for raw in locators:
            # §18.1: "Selected locators refer to these resolved paths, including any `~N`
            # suffix." A resolved path is ALREADY normalized, so it is compared as given —
            # never re-encoded (`normalize_locator` turned `Alpha%20Beta` into `Alpha%2520Beta`
            # and left no route to any heading containing a space) and never repaired. An
            # earlier NFC-and-strip here accepted `" Overview "`, a string the ledger's own
            # locator predicate refuses and no enumeration can emit, so the scope and the records
            # it authorises stopped being the same string.
            if raw not in known:
                # One refusal, not two. A separate "is it normalized?" guard could never be the
                # thing that fired: `known` holds resolved paths, every one of which is already
                # normalized, so a non-normalized locator always misses this membership test.
                raise EnumerationError(
                    f"{self.id}: selected section {raw!r} names no heading in this source; a "
                    "scope locator is a resolved heading path and is already percent-encoded"
                )
            prefixes.append(raw)
        return [
            block
            for block in blocks
            if any(
                block.heading_path == prefix or block.heading_path.startswith(f"{prefix}/")
                for prefix in prefixes
            )
        ]


def _numbered(blocks: list[_Block]) -> list[tuple[_Block, int]]:
    """Per-heading, per-kind 1-based ordinals in source order."""
    counters: dict[tuple[str, str], int] = {}
    numbered: list[tuple[_Block, int]] = []
    for block in blocks:
        key = (block.heading_path, block.kind)
        counters[key] = counters.get(key, 0) + 1
        numbered.append((block, counters[key]))
    return numbered


def _unique_segment(parent: list[str], segment: str, used: set[str]) -> str:
    """`~2`, `~3`, … applied to the final ENCODED segment when a heading path repeats (§18.1)."""
    if "/".join([*parent, segment]) not in used:
        return segment
    index = 2
    while "/".join([*parent, f"{segment}~{index}"]) in used:
        index += 1
    return f"{segment}~{index}"


# --------------------------------------------------------------------------------------
# structured-objects-v1 (§18.1)
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class StructuredObjectsEnumerator:
    """Enumerates a restricted JSON or YAML mapping or list of identified objects."""

    source_id: str
    id: str = STRUCTURED_OBJECTS_V1
    version: int = 1

    def enumerate(
        self, source: bytes, *, scope: ApprovedScope
    ) -> tuple[EnumeratedSourceRecord, ...]:
        _require_complete_file(self, scope)
        parsed = _loaded(source, self.id)
        if isinstance(parsed, Mapping):
            rows = self._mapping_rows(parsed)
        elif isinstance(parsed, list):
            rows = self._list_rows(parsed)
        else:
            raise EnumerationError(
                f"{self.id}: the root must be a mapping or a list of identified objects, not "
                f"{type(parsed).__name__}"
            )
        return tuple(
            _record(self.source_id, f"objects/{encoded}", value)
            for encoded, value in sorted(rows, key=lambda row: row[0])
        )

    def emits_locator(self, locator: str) -> bool:
        """Whether `locator` has a shape `enumerate` can produce, with no source bytes read.

        Every record is one identified object under a fixed `objects/` prefix, so the shape is
        exactly two segments. Which keys exist needs the file; that there are never three segments,
        and that the key is exactly the encoder's own output, do not. This adapter has no duplicate
        rule at all, so a `~` reaches its locators only as `%7E`.
        """
        parts = locator.split("/")
        return len(parts) == 2 and parts[0] == "objects" and is_emitted_segment(parts[1])

    def _encoded(self, raw: object, what: str, seen: set[str]) -> str:
        if not isinstance(raw, str) or not raw.strip():
            raise EnumerationError(f"{self.id}: a {what} must be a nonblank string")
        encoded = encode_locator_segment(raw, adapter=self)
        if encoded in seen:
            raise EnumerationError(f"{self.id}: duplicate normalized {what}")
        seen.add(encoded)
        return encoded

    def _mapping_rows(self, parsed: Mapping[Any, Any]) -> list[tuple[str, object]]:
        seen: set[str] = set()
        rows: list[tuple[str, object]] = []
        for key, value in parsed.items():
            encoded = self._encoded(key, "top-level key", seen)
            rows.append((encoded, {"key": unicodedata.normalize("NFC", key), "value": value}))
        return rows

    def _list_rows(self, parsed: list[Any]) -> list[tuple[str, object]]:
        seen: set[str] = set()
        rows: list[tuple[str, object]] = []
        for element in parsed:
            if not isinstance(element, Mapping):
                raise EnumerationError(
                    f"{self.id}: every root list element must be a mapping carrying an `id`; "
                    "position-derived identity is refused"
                )
            encoded = self._encoded(element.get("id"), "list element `id`", seen)
            rows.append((encoded, dict(element)))
        return rows


# --------------------------------------------------------------------------------------
# Adapter selection
# --------------------------------------------------------------------------------------


def _require_complete_file(adapter: SourceEnumerator, scope: ApprovedScope) -> None:
    if scope.kind != "complete_file":
        raise EnumerationError(
            f"{adapter.id}: this adapter enumerates a complete file and has no sections to select"
        )


def enumerator_for(source_kind: SourceKind, *, source_id: str) -> SourceEnumerator:
    """The one approved adapter for `source_kind`, bound to the source it will enumerate."""
    binding = SOURCE_KIND_ADAPTERS[source_kind]
    if binding.enumerator_id == BOARDWATCH_RESUME_V1:
        return BoardwatchResumeEnumerator(source_id=source_id)
    if binding.enumerator_id == MARKDOWN_BLOCKS_V1:
        return MarkdownBlocksEnumerator(source_id=source_id)
    return StructuredObjectsEnumerator(source_id=source_id)

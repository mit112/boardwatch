from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SkillGroup(BaseModel):
    model_config = ConfigDict(frozen=True)
    label: str
    items: list[str]


class Bullet(BaseModel):
    model_config = ConfigDict(frozen=True)
    bullet_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    tech_tags: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _single_line(self) -> Bullet:
        # Spec L3 requires newline->space; this normalizes every whitespace run to one
        # space, which is strictly stronger. Deliberate: it makes the single-line invariant
        # hold for tabs and wrapped YAML too, and both master and tailored bullets pass
        # through it, so the entailment check compares like with like.
        norm = " ".join(self.text.split())
        if norm != self.text:
            object.__setattr__(self, "text", norm)
        return self


class Entry(BaseModel):
    model_config = ConfigDict(frozen=True)
    entry_id: str = Field(min_length=1)
    heading: str
    bullets: list[Bullet]
    # Structured fields for the LaTeX subheading emitter (Task 4). All optional with
    # backward-compatible defaults so existing fixtures that set only `heading` still
    # validate; `heading` remains the fallback for `title is None` entries + artifact-scan.
    kind: str = "experience"  # "experience" | "project"
    title: str | None = None
    dates: str | None = None
    subtitle: str | None = None
    location: str | None = None
    # A clickable heading link (project entries): the raw target URL and its display label. Both
    # optional; the link segment renders only when `link_url` is set.
    link_url: str | None = None
    link_label: str | None = None
    # Opt-in: render the link at the end of the FIRST bullet instead of in the heading (frees a
    # wide project heading from colliding with the date). `None`/`True` are the only values the
    # projection emits — like `bulletless`, `None` when undeclared so the projected document
    # (`serialize.resume_document_bytes`, `exclude_none=True`) drops it and every entry that does
    # not use it serializes exactly as before. The renderer treats `None` as false.
    link_in_first_bullet: bool | None = None
    # Declares this entry renders with NO bullets — "role + organisation + dates only" (D-221).
    # `None` (unset) and `True` are the only values the projection ever emits, deliberately: a
    # projected document drops None-valued optionals (`serialize.resume_document_bytes` passes
    # `exclude_none=True`), so every entry that is not declared bulletless serializes exactly as it
    # did before this field existed. `validate_slots` reads it to tell a DECLARED absence of
    # bullets from an accidental one; the renderer does not, because `_entry_block` already omits
    # an empty item list on its own.
    bulletless: bool | None = None


class Resume(BaseModel):
    model_config = ConfigDict(frozen=True)
    header: list[str]
    education: list[str]
    skill_groups: list[SkillGroup]
    entries: list[Entry]
    extracurricular: list[str] = Field(default_factory=list)
    # Persona headline title (P4 item 7). Optional and default None so existing resume.yaml
    # files and every existing Resume construction load unchanged; the render wires it into
    # the template's TITLE slot only when set. Distinct from `Entry.title` (a per-job title).
    title: str | None = None

    @model_validator(mode="after")
    def _unique_ids(self) -> Resume:
        eids = [e.entry_id for e in self.entries]
        if len(eids) != len(set(eids)):
            raise ValueError("duplicate entry_id")
        bids = [b.bullet_id for e in self.entries for b in e.bullets]
        if len(bids) != len(set(bids)):
            raise ValueError("duplicate bullet_id")
        return self

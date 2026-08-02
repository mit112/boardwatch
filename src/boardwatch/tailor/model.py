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
    def _single_line(self) -> "Bullet":
        norm = " ".join(self.text.split())
        if norm != self.text:
            object.__setattr__(self, "text", norm)
        return self


class Entry(BaseModel):
    model_config = ConfigDict(frozen=True)
    entry_id: str = Field(min_length=1)
    heading: str
    bullets: list[Bullet]


class Resume(BaseModel):
    model_config = ConfigDict(frozen=True)
    header: list[str]
    education: list[str]
    skill_groups: list[SkillGroup]
    entries: list[Entry]

    @model_validator(mode="after")
    def _unique_ids(self) -> "Resume":
        eids = [e.entry_id for e in self.entries]
        if len(eids) != len(set(eids)):
            raise ValueError("duplicate entry_id")
        bids = [b.bullet_id for e in self.entries for b in e.bullets]
        if len(bids) != len(set(bids)):
            raise ValueError("duplicate bullet_id")
        return self

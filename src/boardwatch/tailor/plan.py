from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class _Op(BaseModel):
    model_config = ConfigDict(frozen=True)


class Select(_Op):
    bullet_id: str
    keep: bool


class Reorder(_Op):
    entry_id: str
    order: tuple[str, ...]


class Delete(_Op):
    bullet_id: str


class EquivalenceSwap(_Op):
    bullet_id: str
    from_phrase: str
    to_phrase: str


Op = Select | Reorder | Delete | EquivalenceSwap


class TailorPlan(BaseModel):
    model_config = ConfigDict(frozen=True)
    ops: tuple[Op, ...]

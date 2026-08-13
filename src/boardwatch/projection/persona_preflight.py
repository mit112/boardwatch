"""Stage-2 preflight: refuse the whole persona registry, before any selection runs, if any
persona declares `entries`.

`apply_persona` (`tailor/persona.py`) raises `PersonaError` the moment a persona's declared
`entries` names an id absent from whatever résumé it is applied to. Stage 2's own entry selection
can legitimately omit any candidate entry it scores too low — that is the entire point of scoring
candidates against a JD — so a persona shaped `entries: [e1, e2]` collides with selection the
instant stage 2 drops one of them. Moving persona application later in the pipeline did not
remove that collision; it only moved WHERE it happens, from load time to render time, deep inside
`tailor run`, where the owner sees a crash instead of a diagnosis.

**v1 forbids the combination outright.** A persona that declares `entries` at all is refused
here, unconditionally — not only when its declared ids happen to miss this particular JD's
selection. A persona whose declared ids all survive today's selection could stop surviving the
next JD's, and this preflight exists to catch the *shape* of the collision, not one instance of
it.

Both bundled personas ship `entries: null` (`tailor/personas.yaml:31,37`), so nothing shipped is
affected; this only fires for an owner override that declares a subset.

A malformed registry (no default persona, duplicate ids, and so on) raises
`tailor.persona.PersonaError` unchanged — that failure already has its own typed exception, so
this preflight adds no second boundary around it.
"""

from __future__ import annotations

from pathlib import Path

from boardwatch.projection.errors import ProjectionIssue, raise_violation
from boardwatch.tailor.persona import load_personas


def reject_entry_declaring_personas(config_dir: Path) -> None:
    """Raise `ProjectionError(PERSONA_DECLARES_ENTRIES)` for the first persona (in registry
    order) in `config_dir`'s effective registry that declares a non-`null` `entries`. Returns
    `None` silently when every persona ships `entries: null`.
    """
    registry = load_personas(config_dir)
    for persona in registry.personas:
        if persona.entries is not None:
            raise_violation(
                ProjectionIssue.PERSONA_DECLARES_ENTRIES,
                f"persona {persona.id!r} declares entries {list(persona.entries)!r}; v1 "
                "forbids a persona from declaring entries at all, because stage 2's selection "
                "can drop any of them and apply_persona has no way to degrade gracefully",
                where=persona.id,
            )


__all__ = ["reject_entry_declaring_personas"]

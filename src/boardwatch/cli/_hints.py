"""Consistent forward "do this next" hints printed after a successful command.

The beginner path (init → scan → top → show → track) was half-wired: `init`
pointed to `scan`, then the trail went cold. These hints wire the rest so each
successful command names the next one.
"""

from __future__ import annotations

from rich.console import Console


def print_next_step(console: Console, *steps: str) -> None:
    """Print each forward step on its own line, prefixed with an arrow."""
    for step in steps:
        console.print(f"→ {step}")

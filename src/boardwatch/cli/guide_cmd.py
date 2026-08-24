"""`boardwatch guide` — the whole beginner journey on one screen.

A user who runs a command and does not know what comes next can run
`boardwatch guide` to see the canonical path from setup to tracking.
"""

from __future__ import annotations

from rich.console import Console

console = Console()

_STEPS: list[tuple[str, str]] = [
    ("boardwatch init", "Pick companies to watch and paste your profile. One-time setup."),
    ("boardwatch scan", "Fetch the watched boards for new and changed postings."),
    ("boardwatch top", "See your ranked shortlist, best matches first."),
    (
        "boardwatch show <#>",
        "Read a posting in full — with eligibility evidence quoted from the listing.",
    ),
    (
        "boardwatch track add <#>",
        "Record an application so it stops re-surfacing and your funnel updates.",
    ),
]


def guide() -> None:
    """Print the canonical boardwatch journey from setup to tracking."""
    console.print("The boardwatch journey — run these in order:\n")
    for command, description in _STEPS:
        console.print(f"  [bold]{command}[/bold]")
        console.print(f"    {description}\n")
    console.print(
        "Prefer one command? `boardwatch run` does scan → rank → tailor in a single "
        "unattended pass — schedule it for a shortlist every morning.\n"
    )
    console.print(
        "Why boardwatch: every eligibility verdict cites the exact span from the "
        "posting, and your data never leaves your machine."
    )

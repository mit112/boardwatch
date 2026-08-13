"""The owner-approval terminal seam, shared by every command that gates a write behind an exact
confirmation word typed on a controlling terminal.

A leaf module, the same shape as `cli/context.py`: it imports only the standard library and
`typer`, so any command module may import it with no cycle risk. `cli/profile_bundle_cmd.py` and
`cli/projection_cmd.py` both import from here — neither command module imports the other — which is
what lets both sides share one definition while `profile_bundle_cmd` still imports `projection_cmd`
one-way, only to register `approve-projection` onto its app.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Final, Protocol

import typer

#: What the owner types to approve. An exact word rather than a y/n, so a stray keypress cannot
#: file an approval — and not a digest itself, which is long enough that an owner would paste it
#: rather than read it.
CONFIRMATION_WORD: Final = "approve"


class ApprovalTerminal(Protocol):
    """The seam between the approval decision and the person making it.

    Exactly one implementation exists in production, and this protocol is the only thing a test
    replaces. Everything else on the approval path — the candidate digest, the derived decisions,
    the stamp, the bytes and where they land — is the production code, so a test cannot approve
    anything by a route a script could not also take.
    """

    def is_controlling(self) -> bool: ...

    def show(self, text: str) -> None: ...

    def ask(self, prompt: str) -> str: ...


@dataclass(frozen=True)
class _StandardTerminal:
    def is_controlling(self) -> bool:
        """Both streams, and anything that is not a plain "yes" counts as "no".

        A detached process has `sys.stdin is None` and a closed one raises from `isatty()`; this
        project runs unattended under a LaunchAgent, so both are states it actually reaches. The
        fail-safe direction is fixed by §13: a run that cannot establish it has the owner's
        attention has not got it.
        """
        for stream in (sys.stdin, sys.stdout):
            try:
                if stream is None or not stream.isatty():
                    return False
            except (AttributeError, ValueError):
                return False
        return True

    def show(self, text: str) -> None:
        """On stderr, because the operator interaction is not the command's own answer."""
        typer.echo(text, err=True)

    def ask(self, prompt: str) -> str:
        return str(typer.prompt(prompt, default="", show_default=False, err=True))


def approval_terminal() -> ApprovalTerminal:
    """The production terminal. There is no second way to reach the stamp writer."""
    return _StandardTerminal()

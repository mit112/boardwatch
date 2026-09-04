"""Refuse a stored profile row the parsers cannot read, the same way in every CLI path.

`parse_facts` / `parse_policy` raise `ProfileRowInvalid` rather than failing closed to the
empty model, because an empty `Policy` MATERIALISES the catalog defaults — only `work_auth`
is a `blocker` there and the other five families fall back to `preference`, which can never
yield `ineligible` (D-P2-1). A read command that swallowed that would print counts computed
under a policy the user never set.

The CLI's job is to say WHICH column and WHY, then exit 1. A traceback names a line in
pydantic, which is not the thing the operator has to edit.
"""

from __future__ import annotations

from typing import NoReturn

import typer
from rich.console import Console

from boardwatch.eligibility.facts import Facts, Policy, ProfileRowInvalid, parse_facts, parse_policy

console = Console()


def refuse_unusable_profile_row(exc: ProfileRowInvalid) -> NoReturn:
    console.print(f"profile row unusable — {exc.column}: {exc.reason}")
    console.print(
        "Correct the stored JSON in that column; every eligibility command reads it and "
        "none of them will guess at what it meant."
    )
    raise typer.Exit(code=1)


def facts_of(raw: object) -> Facts:
    try:
        return parse_facts(raw)
    except ProfileRowInvalid as exc:
        refuse_unusable_profile_row(exc)


def policy_of(raw: object) -> Policy:
    try:
        return parse_policy(raw)
    except ProfileRowInvalid as exc:
        refuse_unusable_profile_row(exc)

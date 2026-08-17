"""Entry point: `python -m tools.fixture_refresh`.

Exit codes: 0 clean or written, 1 drift found under --check, 2 the tool could not run.
Writing is never implicit: --check only reports, and a run with no mode is --check.

This is the WRITE side of R13-R15; the gate itself stays read-only, because a gate that can
repair what it measures cannot be trusted to have measured it. --check therefore does not
restate the rules, it calls them, so the tool and the gate can never disagree about what drift
is.

It deliberately does NOT fetch anything. Fixture-versus-live-API drift needs network and an
attended session; what this automates is the part a human cannot do by hand -- recomputing
seven content hashes and a row count -- plus the one-command drain for an overdue deadline.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import os
import sys
from datetime import date, timedelta
from pathlib import Path

from tools.fixture_refresh.rewrite import (
    PROVENANCE_MODULE,
    RewriteError,
    extend_deadline,
    record_pins,
)
from tools.generalization.discovery import (
    PRODUCTION_MINIMUM_FILES,
    DiscoveryError,
    discover,
    find_repo_root,
)
from tools.generalization.fixtures import (
    CORPUS_PATH,
    CORPUS_SYMBOL,
    FIXTURE_PROVENANCE,
    check_fixture_coverage,
    check_fixture_pins,
    check_fixture_review_due,
    readme_path,
)
from tools.generalization.model import Violation


def _measure(root: Path) -> tuple[dict[str, str], str, int]:
    """The values a human cannot compute by hand: seven hashes and a row count."""
    readmes = {
        provider: hashlib.sha256((root / readme_path(provider)).read_bytes()).hexdigest()
        for provider in sorted(FIXTURE_PROVENANCE)
    }
    corpus_bytes = (root / CORPUS_PATH).read_bytes()
    corpus_pin = hashlib.sha256(corpus_bytes).hexdigest()
    rows = 0
    for node in ast.parse(corpus_bytes.decode("utf-8")).body:
        if not isinstance(node, ast.AnnAssign):
            continue
        if not (isinstance(node.target, ast.Name) and node.target.id == CORPUS_SYMBOL):
            continue
        rows = len(node.value.elts) if isinstance(node.value, ast.List) else 0
    return readmes, corpus_pin, rows


def _report(violations: list[Violation]) -> int:
    if not violations:
        print("fixture-refresh: OK, every pin and deadline is current")
        return 0
    print(f"fixture-refresh: {len(violations)} finding(s)", file=sys.stderr)
    for violation in violations:
        print(f"  {violation.render()}", file=sys.stderr)
    print(
        "\nRe-record content pins with `python -m tools.fixture_refresh --record`. An overdue "
        "review needs --extend, which is an explicit, reasoned acceptance and not a refresh.",
        file=sys.stderr,
    )
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m tools.fixture_refresh",
        description="Re-record fixture provenance pins, or drain an overdue review deadline.",
    )
    parser.add_argument(
        "--check", action="store_true", help="report drift without writing (the default)"
    )
    parser.add_argument(
        "--record", action="store_true", help="rewrite the content pins from what is on disk"
    )
    parser.add_argument("--extend", metavar="PROVIDER", help="roll one review deadline forward")
    parser.add_argument("--days", type=int, default=90, help="days to extend by (default 90)")
    parser.add_argument("--reason", help="why the delay is acceptable; required with --extend")
    args = parser.parse_args(argv)

    if args.record and args.extend:
        parser.error("--record and --extend are separate decisions; run them one at a time")

    try:
        root = find_repo_root(Path.cwd().resolve())
        repo = discover(root, minimum_files=PRODUCTION_MINIMUM_FILES)
    except DiscoveryError as exc:
        print(f"fixture-refresh: FAILED, {exc}", file=sys.stderr)
        return 2

    if args.extend:
        if not args.reason or not args.reason.strip():
            parser.error("--extend requires a non-empty --reason: the reason IS the acceptance")
        if args.days <= 0:
            parser.error("--days must be positive; a deadline cannot be extended backwards")
        if args.extend not in FIXTURE_PROVENANCE:
            parser.error(
                f"unknown provider {args.extend!r}; known: {sorted(FIXTURE_PROVENANCE)}"
            )
        today = date.today()
        current = FIXTURE_PROVENANCE[args.extend].review_by
        new_deadline = max(current, today) + timedelta(days=args.days)
        try:
            _write(
                root / PROVENANCE_MODULE,
                extend_deadline(
                    (root / PROVENANCE_MODULE).read_text(encoding="utf-8"),
                    provider=args.extend,
                    on=today,
                    reason=args.reason.strip(),
                    new_review_by=new_deadline,
                ),
            )
        except (RewriteError, OSError) as exc:
            print(f"fixture-refresh: FAILED, {exc}", file=sys.stderr)
            return 2
        print(
            f"fixture-refresh: {args.extend} review_by {current} -> {new_deadline}, "
            f"recorded as an extension dated {today}"
        )
        return 0

    try:
        readmes, corpus_pin, rows = _measure(root)
    except (OSError, SyntaxError) as exc:
        print(f"fixture-refresh: FAILED, {exc}", file=sys.stderr)
        return 2

    if not args.record:
        return _report(
            check_fixture_coverage(repo)
            + check_fixture_pins(repo)
            + check_fixture_review_due(repo)
        )

    changes = [
        f"  {provider}: README {FIXTURE_PROVENANCE[provider].readme_pin[7:19]} -> {pin[:12]}"
        for provider, pin in readmes.items()
        if FIXTURE_PROVENANCE[provider].readme_pin.removeprefix("sha256:") != pin
    ]
    try:
        original = (root / PROVENANCE_MODULE).read_text(encoding="utf-8")
        updated = record_pins(original, readmes=readmes, corpus_pin=corpus_pin, rows=rows)
    except RewriteError as exc:
        print(f"fixture-refresh: FAILED, {exc}", file=sys.stderr)
        return 2
    if updated == original:
        print("fixture-refresh: OK, every content pin already matches what is on disk")
        return 0
    try:
        _write(root / PROVENANCE_MODULE, updated)
    except OSError as exc:
        print(f"fixture-refresh: FAILED, {exc}", file=sys.stderr)
        return 2
    print(f"fixture-refresh: re-recorded {PROVENANCE_MODULE}")
    for line in changes:
        print(line)
    print(f"  corpus: {rows} rows, pin {corpus_pin[:12]}")
    print("\nReview the diff before committing: a re-recorded pin is a reviewed pin.")
    return 0


def _write(path: Path, text: str) -> None:
    """Replace `path` atomically, after proving the new text is importable Python.

    Parsing first matters because this rewrites a module the GATE imports: a truncated write
    here would not fail this tool, it would crash `make check` for everyone with a SyntaxError
    that looks nothing like fixture drift.
    """
    ast.parse(text)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    os.replace(tmp, path)


if __name__ == "__main__":
    raise SystemExit(main())

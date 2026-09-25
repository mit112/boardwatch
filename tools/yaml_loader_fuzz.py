"""Differential fuzz: the profile-bundle loader's libyaml path against its pure loader.

`profile_bundle.yaml_loader.load_yaml_bytes` parses with libyaml when it can, and must still give
every input the pure loader's outcome: an equal value (compared by `repr`, so `True` is not `1`),
or the same exception class with the same `IssueCode` and message. This runs both over seeded
random short strings, over any files passed with `--corpus` and over edited snippets of them,
and prints every input whose outcomes differ. The suite runs a small slice of the same
generator; this is the full run.

    python -m tools.yaml_loader_fuzz --count 2000000 --workers 4
    python -m tools.yaml_loader_fuzz --corpus DIR --mutate 500000 --oracle-ref 2465a04c

`--oracle-ref` takes the oracle from `yaml_loader.py` at that git revision instead of the
in-tree pure path, which checks that the refactor left the pure loader itself unchanged.
`--no-screen` disables the text screen, to show what it catches.

Exit status: 0 when no input diverged, 1 when any did, 2 when the run could not start.
"""

from __future__ import annotations

import argparse
import contextlib
import random
import re
import subprocess
import sys
from collections.abc import Callable, Iterator
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path, PurePosixPath
from types import ModuleType
from unittest import mock

import yaml

from boardwatch.profile_bundle import yaml_loader
from boardwatch.profile_bundle.errors import ProfileBundleError, RestrictedYamlError

Outcome = tuple[str, ...]
Loader = Callable[[bytes], object]

_PATH = PurePosixPath("facts/identity.yaml")

#: Single characters: YAML indicators, the whitespace and line breaks the two parsers treat
#: differently, escapes, and a few letters and digits so scalars and keys can form.
CHARS = (
    list("-?:,[]{}#&*!|>'\"%@`\\ \n\r\t~.+_=<01aexuNbd/")
    + ["\ufeff", "\x85", "\u2028", "\u2029", "\xa0", "\u00e9", "\U0001f600", "\x00", "\x7f"]
    + ["\x80", "\x9f", "\ud7ff", "\ue000", "\ufffd", "\ufffe", "\U0010ffff", "\u3000"]
)

#: Multi-character pieces that reach deeper parser states than single characters do.
TOKENS = [
    "a", "b", "key", "x y", "_k", "a: ", "b: ", ": ", ":", "- ", "-", "? ", "?", ", ", ",",
    "[", "]", "{", "}", "\n", "\n  ", "  ", " ", "\t", "#", " # c", "#c", "|", ">", "|-", ">+",
    "|2", "'", "''", '"', '\\"', "\\", "\\u", "\\ud800", "\\U0001F600", "\\x41", "\\N", "\\_",
    "---", "...", "--- ", "%YAML 1.1\n", "%YAML 1.2\n", "%TAG ! tag:x,2000:\n", "!", "!!str ",
    "!x ", "&a ", "*a", "<<", "yes", "no", "1", "01", "0x1", "1.5", ".inf", "~", "null",
    "true", "True", "2026-08-10", "12:30", "\r\n", "\r", "\ufeff", "\x85", "\u2028", "\xa0",
    "\u00e9", "C#", "\u00e9: ", "@", "`", "%", '"\\\n  ', '"\\ ', "\\e", "\\0", "\\L", "\\/",
]


def outcome(load: Loader, raw: bytes) -> Outcome:
    """The value's `repr`, or the exception's class, issue code and message."""
    try:
        return ("value", repr(load(raw)))
    except RestrictedYamlError as exc:
        return ("RestrictedYamlError", str(exc.code), str(exc))
    except ProfileBundleError as exc:
        return (type(exc).__name__, str(exc))
    except Exception as exc:  # an escape is itself an outcome the two paths must share
        return ("escaped", type(exc).__name__, str(exc))


def routed(raw: bytes) -> object:
    """The loader under test: `load_yaml_bytes`, libyaml path included."""
    return yaml_loader.load_yaml_bytes(raw, logical_path=_PATH)


def pure(raw: bytes) -> object:
    """The same function with libyaml switched off, which leaves only the pure loader."""
    with mock.patch.object(yaml, "__with_libyaml__", False):
        return yaml_loader.load_yaml_bytes(raw, logical_path=_PATH)


def took_libyaml(raw: bytes) -> bool:
    """Whether `routed` would return libyaml's result for `raw` rather than re-read it."""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return False
    if not yaml.__with_libyaml__ or yaml_loader._PURE_ONLY.search(text):
        return False
    loader = yaml_loader._libyaml_loader()
    try:
        if not yaml_loader._libyaml_can_compose(text, loader):
            return False
        list(yaml.load_all(text, Loader=loader))
    except Exception:
        return False
    return True


def reference_module(ref: str) -> ModuleType:
    """`yaml_loader.py` as it was at git revision `ref`, imported under a private name."""
    root = Path(__file__).resolve().parent.parent
    source = subprocess.run(
        ["git", "-C", str(root), "show", f"{ref}:src/boardwatch/profile_bundle/yaml_loader.py"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    module = ModuleType("_yaml_loader_reference")
    exec(compile(source, f"{ref}:yaml_loader.py", "exec"), module.__dict__)
    return module


def generate(seed: int, count: int) -> Iterator[bytes]:
    """`count` short inputs from `seed`: alternately a run of characters and a run of tokens."""
    rng = random.Random(seed)
    for i in range(count):
        if i % 2:
            text = "".join(rng.choice(CHARS) for _ in range(rng.randint(1, 24)))
        else:
            text = "".join(rng.choice(TOKENS) for _ in range(rng.randint(1, 12)))
        yield text.encode("utf-8")


def mutate(seed: int, count: int, sources: list[str]) -> Iterator[bytes]:
    """`count` snippets of `sources` (1-12 consecutive lines), each edited 0-3 times.

    Real documents reach parser states that random strings rarely do, and a small edit to one
    is the kind of input an author actually produces.
    """
    rng = random.Random(seed)
    lines = [text.splitlines(keepends=True) for text in sources if text]
    for _ in range(count):
        source = rng.choice(lines)
        start = rng.randrange(len(source))
        text = "".join(source[start : start + rng.randint(1, 12)])
        for _ in range(rng.randint(0, 3)):
            at = rng.randint(0, len(text))
            edit = rng.randrange(3)
            if edit == 0:
                text = text[:at] + rng.choice(TOKENS + CHARS) + text[at:]
            elif edit == 1:
                text = text[:at] + text[at + rng.randint(1, 3) :]
            else:
                text = text[:at] + rng.choice(CHARS) + text[at + 1 :]
        yield text.encode("utf-8")


def _corpus_files(roots: list[Path]) -> list[Path]:
    return [p for root in roots for p in sorted(root.rglob("*")) if p.is_file()]


def _oracle(ref: str | None) -> Loader:
    if ref is None:
        return pure
    module = reference_module(ref)
    return lambda raw: module.load_yaml_bytes(raw, logical_path=_PATH)


def _screen(no_screen: bool) -> contextlib.AbstractContextManager[object]:
    if not no_screen:
        return contextlib.nullcontext()
    return mock.patch.object(yaml_loader, "_PURE_ONLY", re.compile(r"(?!)"))


def compare(inputs: list[bytes], ref: str | None, no_screen: bool) -> tuple[int, int, list[str]]:
    """(inputs compared, inputs that took the libyaml path, a line per divergence)."""
    oracle = _oracle(ref)
    took = 0
    found: list[str] = []
    with _screen(no_screen):
        for raw in inputs:
            took += took_libyaml(raw)
            expected, actual = outcome(oracle, raw), outcome(routed, raw)
            if expected != actual:
                found.append(f"{raw!r}\n    pure:    {expected}\n    libyaml: {actual}")
    return len(inputs), took, found


Job = tuple[str, int, int, str | None, bool, list[Path]]


def _fuzz_chunk(job: Job) -> tuple[int, int, list[str]]:
    kind, seed, count, ref, no_screen, roots = job
    if kind == "mutate":
        sources = [p.read_bytes().decode("utf-8", "replace") for p in _corpus_files(roots)]
        inputs = list(mutate(seed, count, sources))
    else:
        inputs = list(generate(seed, count))
    return compare(inputs, ref, no_screen)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tools.yaml_loader_fuzz")
    parser.add_argument("--count", type=int, default=0, help="random short strings to generate")
    parser.add_argument("--mutate", type=int, default=0, help="edited snippets of --corpus files")
    parser.add_argument("--seed", type=int, default=231)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--corpus", type=Path, action="append", default=[])
    parser.add_argument("--oracle-ref", default=None)
    parser.add_argument("--no-screen", action="store_true")
    args = parser.parse_args(argv)
    if not yaml.__with_libyaml__:
        print("libyaml is not installed: there is no second path to compare", file=sys.stderr)
        return 2
    files = _corpus_files(args.corpus)
    if args.mutate and not files:
        print("--mutate needs --corpus files to edit", file=sys.stderr)
        return 2

    total = took = 0
    found: list[str] = []
    if files:
        n, t, f = compare([p.read_bytes() for p in files], args.oracle_ref, args.no_screen)
        total, took, found = total + n, took + t, found + f
    chunk = 20_000
    jobs: list[Job] = [
        (kind, args.seed * 1_000_003 + offset + start, min(chunk, count - start),
         args.oracle_ref, args.no_screen, args.corpus)
        for kind, count, offset in (("generate", args.count, 0), ("mutate", args.mutate, 1 << 40))
        for start in range(0, count, chunk)
    ]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for n, t, f in pool.map(_fuzz_chunk, jobs):
            total, took, found = total + n, took + t, found + f
    for line in found:
        print(line)
    print(f"compared {total}  took-libyaml {took}  divergences {len(found)}")
    return 1 if found else 0


if __name__ == "__main__":
    raise SystemExit(main())

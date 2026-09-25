"""The restricted loader's libyaml path gives every input the pure loader's outcome (T231).

libyaml is there for speed only. For each input, `load_yaml_bytes` must return a value whose
`repr` equals the pure loader's, or raise the same class with the same `IssueCode` and message.
The pure oracle is the same function with libyaml switched off. `tools/yaml_loader_fuzz.py`
runs the same comparison over millions of generated inputs; a seeded slice of it runs here.

The inputs are every YAML file in the repository, T229's divergence record and its agreeing and
refused cases, and a hand list with one or more inputs per refusal.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any

import pytest
import yaml

from boardwatch.profile_bundle import yaml_loader
from boardwatch.profile_bundle.errors import RestrictedYamlError
from boardwatch.profile_bundle.yaml_loader import load_yaml_bytes
from tests.unit.test_yamlio import AGREEING, DIVERGENT, REFUSED_BY_BOTH
from tools.yaml_loader_fuzz import generate, outcome, pure, routed, took_libyaml

libyaml = pytest.mark.skipif(not yaml.__with_libyaml__, reason="libyaml is not installed")

ROOT = Path(__file__).resolve().parents[2]
REPO_YAML = sorted(
    {p for top in ("src", "tests", "tools", ".github") for p in (ROOT / top).rglob("*.y*ml")}
    | set(ROOT.glob("*.y*ml"))
)

DEEP = 400

HAND: dict[str, bytes] = {
    # aliases and anchors
    "alias": b"a: *x\n",
    "anchor": b"a: &x 1\n",
    "anchor then alias": b"a: &x 1\nb: *x\n",
    "anchor on a collection": b"a: &x [1]\n",
    # every tag form
    "core tag": b"a: !!str x\n",
    "core int tag": b"a: !!int '1'\n",
    "local tag": b"a: !x 1\n",
    "bare !": b"a: !\n",
    "bare ! on a value": b"a: ! b\n",
    "verbatim tag": b"a: !<tag:yaml.org,2002:str> b\n",
    "tag directive": b"%TAG ! tag:x,2000:\n---\na: !b c\n",
    "unused tag directive": b"%TAG ! tag:x,2000:\n---\na: b\n",
    "tag on a mapping": b"a: !!map {b: c}\n",
    "tag on a sequence": b"!!seq [a]\n",
    "python tag": b"!!python/object:os.system {}\n",
    "! inside prose": b"a: shipped it!\n",
    # merge keys
    "merge key": b"x: {<<: {a: 1}}\n",
    "merge key in block": b"<<: a\n",
    "merge as a value": b"a: <<\n",
    # out-of-contract implicit scalars
    **{
        f"plain {token}": f"a: {token}\n".encode()
        for token in [
            "no", "yes", "off", "on", "y", "n", "True", "NULL", "Null", "2026-08-10",
            "2026-08-10T12:00:00Z", "2026-08", "01", "0o17", "0x1f", "1_000", "1.5", ".inf",
            "-.inf", ".nan", "1e3", "12:30", "=", "123abc", "+", "-", ".x", "\u00e9t\u00e9",
            "-1", "+1", "0", "-0", "123456789012345678901234567890",
        ]
    },
    "accepted scalars": b"a: true\nb: false\nc: null\nd: ~\ne:\nf: 12\ng: -3\nh: text here\n",
    "quoted escape hatch": b"a: \"no\"\nb: '2026-08-10'\nc: \"1.5\"\n",
    # multi-document and empty
    "two documents": b"a: 1\n---\nb: 2\n",
    "two empty documents": b"---\n---\n",
    "explicit end then start": b"a\n...\n---\nb\n",
    "document end only": b"a: 1\n...\n",
    "empty": b"",
    "document start only": b"---\n",
    "comment only": b"# c\n",
    "blank lines": b"\n\n",
    "a space": b" ",
    # BOM
    "BOM at the start": b"\xef\xbb\xbfa: 1\n",
    "BOM alone": b"\xef\xbb\xbf",
    "BOM inside a quoted value": b'a: "x\xef\xbb\xbfy"\n',
    # invalid UTF-8 is refused before YAML
    "invalid byte": b"\xff",
    "truncated sequence": b"a: \xc3\n",
    "encoded surrogate": b"a: \xed\xa0\x80\n",
    "latin-1": "a: caf\xe9\n".encode("latin-1"),
    # keys
    "duplicate key": b"a: 1\na: 2\n",
    "duplicate nested key": b"r:\n  - a: 1\n    a: 2\n",
    "integer key": b"1: a\n",
    "null key": b"~: a\n",
    "bool key": b"true: a\n",
    "sequence key": b"? [1]\n: a\n",
    "explicit string key": b"? a\n: b\n",
    "empty key": b": a\n",
    # two violations: the pure loader's first one must be the one reported
    "alias then scalar": b"a: *x\nb: yes\n",
    "scalar then alias": b"a: yes\nb: *x\n",
    "tag then scalar": b"a: !x 1\nb: no\n",
    "scalar then tag": b"a: no\nb: !x 1\n",
    "duplicate then alias": b"a: 1\na: 2\nb: *x\n",
    "scalar then parse error": b"a: yes\nb: [\n",
    "parse error then scalar": b"a: [\nb: yes\n",
    "violation then second document": b"a: yes\n---\nb: 1\n",
    "second document with an alias": b"a: 1\n---\nb: *x\n",
    "second document broken": b"a: 1\n---\n: [\n",
    "tab then scalar": b"a:\tb\nc: yes\n",
    # nesting
    "nesting at the depth limit": b"[" * 64 + b"]" * 64,
    "nesting past the depth limit": b"[" * 65 + b"]" * 65,
    "deep flow nesting": b"[" * DEEP + b"]" * DEEP,
    "deep block nesting": b"".join(b"  " * i + b"k:\n" for i in range(DEEP)),
    # scanner limits and whitespace
    "1024-char key": b"k" * 1024 + b": v\n",
    "1025-char key": b"k" * 1025 + b": v\n",
    "long non-ASCII key": "\u00e9".encode() * 600 + b": v\n",
    "CRLF": b"a: 1\r\nb: x\r\n",
    "lone CR": b"a: 1\rb: x\r",
    "NEL": b"a: 1\xc2\x85b: x\n",
    "line separator": "a: 1\u2028b: x\n".encode(),
    "paragraph separator": "a: x\u2029y\n".encode(),
    "no-break space": "a: x\u00a0y\n".encode(),
    "control character": b"a: \x07\n",
    "NUL": b"a: \x00\n",
    "DEL": b"a: \x7f\n",
    # escapes
    "surrogate escape": b'a: "\\ud800"\n',
    "surrogate pair escape": b'a: "\\ud83d\\ude00"\n',
    "long escape": b'a: "\\U0001F600"\n',
    "out-of-range escape": b'a: "\\U00110000"\n',
    "hex escape": b'a: "\\x41"\n',
    "slash escape": b'a: "\\/"\n',
    "unknown escape": b'a: "\\q"\n',
    # the T229 classes, restated as bundle documents
    "tab after a colon": b"a:\tb\n",
    "tab inside a plain scalar": b"a: b\tc\n",
    "tab indentation": b"\ta: 1\n",
    "tab inside quotes": b'a: "x\ty"\n',
    "comment touching a block header": b"a: |#c\n  x\n",
    "? in a flow plain scalar": b"{a?}\n",
    "? mid flow scalar": b"[a?b]\n",
    "? in prose": b"a: why?\n",
    "BOM starting a later line": b"\n\xef\xbb\xbfb\n",
    "BOM before a later key": b"a: 1\n\xef\xbb\xbfb: 2\n",
    # directives
    "YAML 1.1 directive": b"%YAML 1.1\n---\na: 1\n",
    "YAML 1.2 directive": b"%YAML 1.2\n---\na: 1\n",
    "YAML 1.3 directive": b"%YAML 1.3\n---\na: 1\n",
    "YAML 2.0 directive": b"%YAML 2.0\n---\na: 1\n",
    "unknown directive": b"%FOO bar\n---\na: 1\n",
    # ordinary shapes
    "block scalars": b"a: |\n  x\nb: >\n  f\n\n  g\nc: |-\n  z\nd: |+\n  w\n\ne: |2\n    i\n",
    "flow mapping with an implicit null": b"{a, b: c}\n",
    "single-quoted": b"a: 'it''s'\n",
    "trailing comment": b"a: b # c\n",
    "hash inside a scalar": b"a: b#c\n",
    "comment after a quoted scalar": b'a: "x"#c\n',
    "C#": b"skill: C#\n",
    "multi-line plain scalar": b"a: one\n  two\n\n  three\n",
    "sequence of mappings": b"- a: 1\n  b: x\n- c: y\n",
}


def _cases() -> dict[str, bytes]:
    cases = {f"repo:{p.relative_to(ROOT).as_posix()}": p.read_bytes() for p in REPO_YAML}
    cases |= {f"t229-divergent:{k}": v[0].encode("utf-8", "surrogatepass") for k, v in DIVERGENT.items()}
    cases |= {f"t229-agreeing:{k}": v.encode() for k, v in AGREEING.items()}
    cases |= {f"t229-refused:{k}": v.encode() for k, v in REFUSED_BY_BOTH.items()}
    cases |= {f"hand:{k}": v for k, v in HAND.items()}
    return cases


CASES = _cases()


def test_the_repository_glob_found_the_yaml_files() -> None:
    names = {p.relative_to(ROOT).as_posix() for p in REPO_YAML}
    assert "src/boardwatch/profile_bundle/examples/comprehensive/manifest.yaml" in names
    assert "src/boardwatch/eligibility/rules.yaml" in names
    assert len(names) >= 55


@libyaml
@pytest.mark.parametrize("raw", CASES.values(), ids=CASES.keys())
def test_the_libyaml_path_gives_the_pure_loaders_outcome(raw: bytes) -> None:
    assert outcome(routed, raw) == outcome(pure, raw)


@libyaml
def test_a_seeded_fuzz_slice_gives_the_pure_loaders_outcome() -> None:
    inputs = list(generate(231, 15000))
    diverged = [raw for raw in inputs if outcome(routed, raw) != outcome(pure, raw)]
    assert diverged == []
    # Not vacuous: a fair share of the slice was parsed and returned by libyaml.
    assert sum(took_libyaml(raw) for raw in inputs) >= 1000


@libyaml
def test_every_unscreened_bundle_example_file_takes_the_libyaml_path() -> None:
    example = [p for p in REPO_YAML if "profile_bundle/examples" in p.as_posix()]
    screened = {p for p in example if yaml_loader._PURE_ONLY.search(p.read_text("utf-8"))}
    taken = {p for p in example if took_libyaml(p.read_bytes())}
    assert taken == set(example) - screened
    assert len(taken) >= 30


class _Refused(yaml.SafeLoader):
    def __init__(self, stream: Any) -> None:
        raise AssertionError("the pure loader ran")


@libyaml
def test_a_valid_document_is_read_by_libyaml_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(yaml_loader, "CareerProfileLoader", _Refused)
    parsed = load_yaml_bytes(b"a: text\nb: [1, true, null]\n", logical_path=PurePosixPath("m.yaml"))
    assert parsed == {"a": "text", "b": [1, True, None]}


@libyaml
@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (b"a: yes\nb: *x\n", "plain scalar 'yes'"),
        (b"a: *x\nb: yes\n", "aliases are not permitted"),
        (b"a: no\nb: !x 1\n", "plain scalar 'no'"),
        (b"a: !x 1\nb: no\n", "explicit YAML tag '!x'"),
    ],
)
def test_the_first_violation_in_document_order_is_the_one_reported(
    body: bytes, expected: str
) -> None:
    with pytest.raises(RestrictedYamlError) as excinfo:
        load_yaml_bytes(body, logical_path=PurePosixPath("m.yaml"))
    assert expected in str(excinfo.value)


def test_without_libyaml_the_pure_loader_reads_everything(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(yaml, "__with_libyaml__", False)
    monkeypatch.delattr(yaml, "CSafeLoader", raising=False)
    assert load_yaml_bytes(b"a: text\n", logical_path=PurePosixPath("m.yaml")) == {"a": "text"}
    with pytest.raises(RestrictedYamlError):
        load_yaml_bytes(b"a:\tb\n", logical_path=PurePosixPath("m.yaml"))
